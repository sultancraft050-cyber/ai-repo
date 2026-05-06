from __future__ import annotations

import logging
from dataclasses import dataclass

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import (
    CanonicalizationValidationItem,
    CanonicalizationValidationResponse,
    DiscoveryPreviewItem,
    PriceOffer,
    PricingRefreshResponse,
    PricingSyncResponse,
    ProductDiscoveryResponse,
)
from app.services.hardware_taxonomy import discovery_queries, normalize_category
from app.services.pricing_normalization import CanonicalProductEngine
from app.services.pricing_quality import PriceQualityValidator
from app.services.pricing_sources import SourceRegistry, SourceUnavailable


logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    accepted_snapshots: int = 0
    rejected_snapshots: int = 0
    stale_products: list[str] | None = None
    source_errors: list[str] | None = None
    preview: list[DiscoveryPreviewItem] | None = None

    def __post_init__(self) -> None:
        self.stale_products = self.stale_products or []
        self.source_errors = self.source_errors or []
        self.preview = self.preview or []


class PricingIngestionService:
    def __init__(
        self,
        repository: Neo4jPricingRepository,
        sources: SourceRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.sources = sources or SourceRegistry()
        self.normalizer = CanonicalProductEngine()
        self.validator = PriceQualityValidator()

    def refresh_product(
        self,
        *,
        product_id: str,
        region: str = "US",
        providers: list[str] | None = None,
    ) -> IngestionResult:
        target = self.repository.refresh_target(product_id)
        if not target:
            return IngestionResult(
                rejected_snapshots=1,
                stale_products=[product_id],
                source_errors=[f"unknown product {product_id}"],
            )
        query = " ".join(part for part in (target.get("name"), target.get("model")) if part)
        return self.sync_query(
            query=query,
            category=target.get("category") or "GPU",
            region=region,
            providers=providers,
            limit=10,
            stale_product_id=product_id,
        )

    def sync_query(
        self,
        *,
        query: str,
        category: str,
        region: str = "US",
        providers: list[str] | None = None,
        limit: int = 8,
        stale_product_id: str | None = None,
    ) -> IngestionResult:
        result = IngestionResult()
        sources = self.sources.enabled(providers)
        if not sources:
            if stale_product_id:
                self.repository.mark_product_stale(stale_product_id, "no configured pricing sources")
                result.stale_products.append(stale_product_id)
            result.source_errors.append("no configured pricing sources")
            logger.warning("pricing sync skipped: no configured sources for query=%s", query)
            return result

        for source in sources:
            try:
                records = source.fetch_offers(
                    query=query,
                    category=category,
                    region=region,
                    limit=limit,
                )
            except SourceUnavailable as error:
                result.source_errors.append(f"{source.name}: {error}")
                logger.warning("pricing source unavailable", extra={"source": source.name, "error": str(error)})
                continue
            except Exception as error:  # noqa: BLE001 - source isolation is intentional infrastructure code.
                result.source_errors.append(f"{source.name}: {error}")
                logger.exception("pricing source failed", extra={"source": source.name})
                continue

            for record in records:
                try:
                    offer = self.normalizer.normalize_record(record)
                    previous = self.repository.previous_price(
                        offer.product.canonical_key,
                        vendor_id=offer.vendor.id,
                    )
                    quality = self.validator.validate_offer(offer, previous_price=previous)
                    offer.flags = quality.flags
                    if not quality.accepted:
                        result.rejected_snapshots += 1
                        logger.info(
                            "pricing offer rejected",
                            extra={
                                "source": source.name,
                                "reasons": quality.rejected_reasons,
                                "canonical_key": offer.product.canonical_key,
                            },
                        )
                        continue
                    self._persist_offer(offer)
                    result.accepted_snapshots += 1
                except Exception as error:  # noqa: BLE001 - bad vendor records should not stop ingestion.
                    result.rejected_snapshots += 1
                    logger.exception("pricing record normalization failed", extra={"source": source.name})
                    result.source_errors.append(f"{source.name}: {error}")

        if result.accepted_snapshots == 0 and stale_product_id:
            self.repository.mark_product_stale(stale_product_id, "pricing sources returned no valid snapshots")
            result.stale_products.append(stale_product_id)
        return result

    def preview_query(
        self,
        *,
        query: str,
        category: str,
        region: str = "US",
        providers: list[str] | None = None,
        limit: int = 8,
    ) -> IngestionResult:
        result = IngestionResult()
        sources = self.sources.enabled(providers)
        if not sources:
            result.source_errors.append("no configured pricing sources")
            logger.warning("pricing dry run skipped: no configured sources for query=%s", query)
            return result

        for source in sources:
            try:
                records = source.fetch_offers(
                    query=query,
                    category=category,
                    region=region,
                    limit=limit,
                )
            except SourceUnavailable as error:
                result.source_errors.append(f"{source.name}: {error}")
                continue
            except Exception as error:  # noqa: BLE001 - source isolation is intentional.
                result.source_errors.append(f"{source.name}: {type(error).__name__}")
                continue

            for record in records[:limit]:
                try:
                    offer = self.normalizer.normalize_record(record)
                    try:
                        previous = self.repository.previous_price(
                            offer.product.canonical_key,
                            vendor_id=offer.vendor.id,
                        )
                    except Exception:
                        previous = None
                    quality = self.validator.validate_offer(offer, previous_price=previous)
                    try:
                        existing = self.repository.find_product_id(offer.product)
                    except Exception:
                        existing = None
                    if quality.accepted:
                        result.accepted_snapshots += 1
                    else:
                        result.rejected_snapshots += 1
                    result.preview.append(
                        DiscoveryPreviewItem(
                            raw_listing_name=record.title,
                            normalized_name=offer.product.model,
                            canonical_key=offer.product.canonical_key,
                            canonical_product_id=existing,
                            merge_decision="rejected"
                            if not quality.accepted
                            else "merge_existing"
                            if existing
                            else "new_product",
                            confidence=0.92 if existing else 0.82,
                            reason="Quality accepted and canonical identity resolved"
                            if quality.accepted
                            else "; ".join(quality.rejected_reasons),
                            vendor_name=offer.vendor.name,
                            price=offer.price,
                            currency=offer.currency,
                            availability=offer.availability,
                            accepted=quality.accepted,
                            rejected_reasons=quality.rejected_reasons,
                            flags=quality.flags,
                            source=offer.source.source,
                            source_type=offer.source.source_type,
                            trust_score=offer.source.trust_score,
                            freshness_score=offer.source.freshness_score,
                            product_url=offer.product_url,
                            image_url=offer.image_url,
                        )
                    )
                except Exception as error:  # noqa: BLE001
                    result.rejected_snapshots += 1
                    result.source_errors.append(f"{source.name}: {type(error).__name__}")
            break
        return result

    def _persist_offer(self, offer: PriceOffer) -> None:
        product_id = self.repository.upsert_offer(offer, accepted=True)
        logger.info(
            "pricing snapshot stored",
            extra={
                "product_id": product_id,
                "vendor": offer.vendor.name,
                "price": offer.price,
                "currency": offer.currency,
            },
        )


def refresh_response(job_ids: list[str], result: IngestionResult | None = None) -> PricingRefreshResponse:
    result = result or IngestionResult()
    return PricingRefreshResponse(
        job_ids=job_ids,
        status="completed" if result.accepted_snapshots or result.rejected_snapshots else "queued",
        message="pricing refresh accepted",
        accepted_snapshots=result.accepted_snapshots,
        rejected_snapshots=result.rejected_snapshots,
        stale_products=result.stale_products or [],
    )


def sync_response(job_ids: list[str], result: IngestionResult | None = None) -> PricingSyncResponse:
    result = result or IngestionResult()
    return PricingSyncResponse(
        job_ids=job_ids,
        status="completed" if result.accepted_snapshots or result.rejected_snapshots else "queued",
        message="pricing sync accepted",
        accepted_snapshots=result.accepted_snapshots,
        rejected_snapshots=result.rejected_snapshots,
    )


class ProductDiscoveryService:
    def __init__(self, ingestion: PricingIngestionService) -> None:
        self.ingestion = ingestion

    def discover(
        self,
        *,
        categories: list[str] | None = None,
        query: str | None = None,
        region: str = "US",
        providers: list[str] | None = None,
        limit_per_query: int = 8,
        max_queries: int = 24,
    ) -> tuple[IngestionResult, list[tuple[str, str]]]:
        plan = discovery_queries(categories=categories, query=query)[:max_queries]
        aggregate = IngestionResult()
        for category, discovery_query in plan:
            result = self.ingestion.sync_query(
                query=discovery_query,
                category=normalize_category(category),
                region=region,
                providers=providers,
                limit=limit_per_query,
            )
            aggregate.accepted_snapshots += result.accepted_snapshots
            aggregate.rejected_snapshots += result.rejected_snapshots
            aggregate.stale_products.extend(result.stale_products or [])
            aggregate.source_errors.extend(result.source_errors or [])
        return aggregate, plan


class CanonicalizationValidationService:
    def __init__(self, repository: Neo4jPricingRepository) -> None:
        self.repository = repository
        self.normalizer = CanonicalProductEngine()

    def validate(self, *, names: list[str], category: str) -> CanonicalizationValidationResponse:
        from app.models.pricing import SourceMetadata, SourceProductRecord, SourceTier, SourceType

        items: list[CanonicalizationValidationItem] = []
        groups: dict[str, list[str]] = {}
        for index, name in enumerate(names):
            record = SourceProductRecord(
                source_product_id=f"canonical-validation-{index}",
                title=name,
                category=category,
                price=599,
                currency="USD",
                availability="unknown",
                vendor_name="Canonicalization Validation",
                source=SourceMetadata(
                    source="canonicalization-validator",
                    source_type=SourceType.INFERRED,
                    tier=SourceTier.INFERRED,
                    trust_score=0.5,
                    freshness_score=1,
                ),
            )
            offer = self.normalizer.normalize_record(record)
            try:
                existing = self.repository.find_product_id(offer.product)
            except Exception:
                existing = None
            groups.setdefault(offer.product.canonical_key, []).append(name)
            items.append(
                CanonicalizationValidationItem(
                    raw_listing_name=name,
                    normalized_name=offer.product.model,
                    canonical_key=offer.product.canonical_key,
                    canonical_product_id=existing,
                    merge_decision="merge_existing" if existing else "new_product",
                    confidence=0.95 if len(offer.product.normalized_model) >= 8 else 0.72,
                    reason="Normalized brand/model/category generated the canonical identity.",
                )
            )
        return CanonicalizationValidationResponse(category=category, items=items, groups=groups)


def discovery_response(
    job_ids: list[str],
    categories: list[str],
    query_count: int,
    result: IngestionResult | None = None,
    dry_run: bool = False,
    trace_id: str | None = None,
) -> ProductDiscoveryResponse:
    result = result or IngestionResult()
    return ProductDiscoveryResponse(
        job_ids=job_ids,
        status="completed" if dry_run or result.accepted_snapshots or result.rejected_snapshots else "queued",
        message="product discovery accepted",
        query_count=query_count,
        categories=[normalize_category(category) for category in categories],
        accepted_snapshots=result.accepted_snapshots,
        rejected_snapshots=result.rejected_snapshots,
        dry_run=dry_run,
        trace_id=trace_id,
        source_errors=result.source_errors or [],
        preview=result.preview or [],
    )
