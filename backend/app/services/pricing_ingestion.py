from __future__ import annotations

import logging
from dataclasses import dataclass

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import (
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

    def __post_init__(self) -> None:
        self.stale_products = self.stale_products or []
        self.source_errors = self.source_errors or []


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


def discovery_response(
    job_ids: list[str],
    categories: list[str],
    query_count: int,
    result: IngestionResult | None = None,
) -> ProductDiscoveryResponse:
    result = result or IngestionResult()
    return ProductDiscoveryResponse(
        job_ids=job_ids,
        status="completed" if result.accepted_snapshots or result.rejected_snapshots else "queued",
        message="product discovery accepted",
        query_count=query_count,
        categories=[normalize_category(category) for category in categories],
        accepted_snapshots=result.accepted_snapshots,
        rejected_snapshots=result.rejected_snapshots,
    )
