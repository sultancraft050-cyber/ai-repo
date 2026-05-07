from __future__ import annotations

import logging
from dataclasses import dataclass

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import (
    CanonicalizationValidationItem,
    CanonicalizationValidationResponse,
    DiscoveryPreviewItem,
    FieldEvidence,
    PriceOffer,
    PricingRefreshResponse,
    PricingSyncResponse,
    ProductDiscoveryResponse,
)
from app.services.hardware_taxonomy import discovery_queries, normalize_category
from app.services.pricing_classification import ProductTypeClassification, classify_product_type
from app.services.pricing_normalization import (
    CanonicalProductEngine,
    case_family_key_from_title,
    cpu_model_key_from_title,
    cooler_family_key_from_title,
    gpu_family_key_from_title,
    motherboard_family_key_from_title,
    psu_family_key_from_title,
    ram_family_key_from_title,
    storage_model_key_from_title,
)
from app.services.pricing_quality import PriceQualityValidator
from app.services.pricing_sources import SourceRegistry, SourceUnavailable
from app.services.region_config import (
    get_region_config,
    normalize_region,
    serves_saudi,
    vendor_region_type,
    vendor_trust_profile,
)


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
        region: str = "SA",
        city: str | None = None,
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
            city=city,
            providers=providers,
            limit=10,
            stale_product_id=product_id,
        )

    def sync_query(
        self,
        *,
        query: str,
        category: str,
        region: str = "SA",
        city: str | None = None,
        providers: list[str] | None = None,
        limit: int = 8,
        stale_product_id: str | None = None,
    ) -> IngestionResult:
        region = normalize_region(region)
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
                    classification = classify_product_type(record, category)
                    offer = self.normalizer.normalize_record(record)
                    offer = _apply_region_context(offer, region=region, city=city)
                    previous = self.repository.previous_price(
                        offer.product.canonical_key,
                        vendor_id=offer.vendor.id,
                        region=region,
                    )
                    quality = self.validator.validate_offer(offer, previous_price=previous)
                    family_rejections = _target_model_rejections(query, category, offer)
                    rejected_reasons = _unique(
                        [*classification.rejected_reasons, *quality.rejected_reasons, *family_rejections]
                    )
                    offer.flags = _unique([*offer.flags, *classification.flags, *quality.flags])
                    if not classification.accepted or not quality.accepted or family_rejections:
                        result.rejected_snapshots += 1
                        logger.info(
                            "pricing offer rejected",
                            extra={
                                "source": source.name,
                                "reasons": rejected_reasons,
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
        region: str = "SA",
        city: str | None = None,
        providers: list[str] | None = None,
        limit: int = 8,
    ) -> IngestionResult:
        region = normalize_region(region)
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
                    classification = classify_product_type(record, category)
                    offer = self.normalizer.normalize_record(record)
                    offer = _apply_region_context(offer, region=region, city=city)
                    try:
                        previous = self.repository.previous_price(
                            offer.product.canonical_key,
                            vendor_id=offer.vendor.id,
                            region=region,
                        )
                    except Exception:
                        previous = None
                    quality = self.validator.validate_offer(offer, previous_price=previous)
                    try:
                        existing = self.repository.find_product_id(offer.product)
                    except Exception:
                        existing = None
                    rejected_reasons = _unique([*classification.rejected_reasons, *quality.rejected_reasons])
                    family_rejections = _target_model_rejections(query, category, offer)
                    rejected_reasons = _unique([*rejected_reasons, *family_rejections])
                    flags = _unique([*offer.flags, *classification.flags, *quality.flags])
                    accepted = classification.accepted and quality.accepted and not family_rejections
                    if accepted:
                        result.accepted_snapshots += 1
                    else:
                        result.rejected_snapshots += 1
                    result.preview.append(
                        _preview_item(
                            record_title=record.title,
                            offer=offer,
                            classification=classification,
                            accepted=accepted,
                            rejected_reasons=rejected_reasons,
                            flags=flags,
                            existing=existing,
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


def _preview_item(
    *,
    record_title: str,
    offer: PriceOffer,
    classification: ProductTypeClassification,
    accepted: bool,
    rejected_reasons: list[str],
    flags: list[str],
    existing: str | None,
) -> DiscoveryPreviewItem:
    merge_decision = "rejected" if not accepted else "merge_existing" if existing else "new_product"
    reason = (
        "Quality accepted and canonical identity resolved"
        if accepted
        else "; ".join(rejected_reasons or ["listing rejected by classification or quality rules"])
    )
    confidence = min(
        0.99,
        classification.confidence * 0.65 + (0.27 if existing else 0.17),
    )
    return DiscoveryPreviewItem(
        raw_listing_name=record_title,
        category=offer.product.category,
        product_type=classification.product_type,  # type: ignore[arg-type]
        product_type_confidence=classification.confidence,
        normalized_name=offer.product.model,
        gpu_family_key=offer.product.specs.get("gpu_family_key"),
        ram_family_key=offer.product.specs.get("ram_family_key"),
        psu_family_key=offer.product.specs.get("psu_family_key"),
        case_family_key=offer.product.specs.get("case_family_key"),
        cooler_family_key=offer.product.specs.get("cooler_family_key"),
        motherboard_family_key=offer.product.specs.get("motherboard_family_key"),
        canonical_product_key=offer.product.canonical_key,
        canonical_key=offer.product.canonical_key,
        canonical_product_id=existing,
        merge_decision=merge_decision,
        confidence=round(confidence, 2),
        reason=reason,
        vendor_name=offer.vendor.name,
        price=offer.price,
        currency=offer.currency,
        region=offer.region,
        city=offer.city,
        item_price_sar=offer.item_price_sar,
        shipping_cost_sar=offer.shipping_cost_sar,
        final_landed_price=offer.final_landed_price,
        final_landed_currency=offer.final_landed_currency,
        final_landed_price_sar=offer.final_landed_price_sar,
        is_local_stock=offer.is_local_stock,
        is_imported=offer.is_imported,
        serves_saudi=offer.serves_saudi,
        vendor_region_type=offer.vendor_region_type,  # type: ignore[arg-type]
        vat_included=offer.vat_included,
        vat_status=offer.vat_status,  # type: ignore[arg-type]
        shipping_status=offer.shipping_status,  # type: ignore[arg-type]
        warranty_status=offer.warranty_status,  # type: ignore[arg-type]
        local_stock_status=offer.local_stock_status,  # type: ignore[arg-type]
        estimated_vat=offer.estimated_vat,
        warranty_type=offer.warranty_type,
        region_rank_score=offer.region_rank_score,
        recommended_candidate=offer.recommended_saudi_price_candidate,
        recommended_saudi_price_candidate=offer.recommended_saudi_price_candidate,
        final_landed_price_confidence=offer.final_landed_price_confidence,
        price_completeness_score=offer.price_completeness_score,
        trust_tier=offer.trust_tier,
        local_stock_confidence=offer.local_stock_confidence,
        warranty_confidence=offer.warranty_confidence,
        delivery_confidence=offer.delivery_confidence,
        availability=offer.availability,
        listing_condition=offer.listing_condition,  # type: ignore[arg-type]
        seller_type=offer.seller_type,  # type: ignore[arg-type]
        marketplace_risk_score=offer.marketplace_risk_score,
        accepted=accepted,
        rejected_reasons=rejected_reasons,
        flags=flags,
        source=offer.source.source,
        source_type=offer.source.source_type,
        trust_score=offer.source.trust_score,
        freshness_score=offer.source.freshness_score,
        product_url=offer.product_url,
        image_url=offer.image_url,
    )


def _apply_region_context(offer: PriceOffer, *, region: str, city: str | None = None) -> PriceOffer:
    config = get_region_config(region)
    trust_profile = vendor_trust_profile(offer.vendor.name, config.region_code)
    region_type = trust_profile.vendor_region_type or vendor_region_type(offer.vendor.name, config.region_code)
    is_local = region_type in {"local", "local_saudi_vendor"} or (
        config.region_code == "US" and offer.currency == "USD" and region_type in {"unknown_vendor", "local"}
    )
    is_gcc = region_type == "gcc_vendor"
    is_marketplace = region_type == "marketplace_vendor"
    is_imported = region_type in {"international_vendor", "marketplace_vendor"} or (
        config.region_code != "US" and offer.currency != config.currency
    )
    is_infiniarc = "INFINIARC" in offer.vendor.name.upper().replace(" ", "")
    serves_saudi_flag = trust_profile.serves_saudi or serves_saudi(offer.vendor.name, config.region_code)
    vat_status = _vat_status(offer)
    vat_included = True if vat_status == "vat_included" else False if vat_status == "vat_excluded" else None
    shipping_status = _shipping_status(offer)
    warranty_status = _warranty_status(offer, is_local=is_local, is_gcc=is_gcc, is_marketplace=is_marketplace)
    local_stock_status = (
        "local_stock"
        if is_local
        else "gcc_stock"
        if is_gcc
        else "imported_stock"
        if is_imported
        else "unknown_stock"
    )
    item_price_sar = offer.price if config.region_code == "SA" and offer.currency == "SAR" else None
    shipping_cost_sar = (
        offer.shipping_cost
        if item_price_sar is not None and shipping_status in {"free_shipping", "paid_shipping"}
        else None
    )
    final_landed_price_sar = (
        round(item_price_sar + (shipping_cost_sar or 0), 2)
        if item_price_sar is not None
        else None
    )
    final_landed_incomplete = config.region_code == "SA" and (
        item_price_sar is None or vat_status == "vat_unknown" or shipping_status == "unknown_shipping"
    )
    estimated_vat = None
    if vat_included and config.vat_rate:
        estimated_vat = round(offer.price * (config.vat_rate / (1 + config.vat_rate)), 2)
    elif vat_status == "vat_excluded" and config.vat_rate:
        estimated_vat = round(offer.price * config.vat_rate, 2)

    flags = list(offer.flags)
    if is_local:
        flags.append("local_stock")
        flags.append("local_stock_likely")
    if is_imported:
        flags.append("imported_listing")
    if vat_status == "vat_unknown":
        flags.append("vat_unknown")
        flags.append("unknown_vat")
    if shipping_status == "unknown_shipping":
        flags.append("unknown_shipping")
        flags.append("shipping_unknown")
        flags.append("delivery_unclear")
    if warranty_status == "unknown_warranty":
        flags.append("unknown_warranty")
        flags.append("warranty_unknown")
        flags.append("warranty_unclear")
    if warranty_status == "local_warranty":
        flags.append("local_warranty_available")
        flags.append("local_warranty_likely")
    if final_landed_incomplete:
        flags.append("final_landed_price_incomplete")
        flags.append("price_not_final")
    if offer.currency != config.currency:
        flags.append("currency_not_local")
    if offer.seller_type == "marketplace":
        flags.append("marketplace_seller")
    if offer.listing_condition == "unknown":
        flags.append("used_or_unknown_condition")
    if is_infiniarc:
        if offer.listing_condition == "unknown" or offer.seller_type == "unknown":
            flags.append("warranty_unclear")
        if offer.shipping_cost == 0:
            flags.append("unknown_shipping")
            flags.append("delivery_unclear")

    local_warranty = True if warranty_status == "local_warranty" else None
    warranty_type = (
        "local"
        if warranty_status == "local_warranty"
        else "manufacturer"
        if warranty_status == "manufacturer_warranty"
        else "seller"
        if warranty_status == "seller_warranty"
        else "unknown"
    )
    local_stock_confidence = max(_local_stock_confidence(local_stock_status), trust_profile.local_stock_confidence)
    warranty_confidence = max(_warranty_confidence(warranty_status), trust_profile.warranty_confidence)
    delivery_confidence = max(_delivery_confidence(shipping_status), trust_profile.shipping_confidence)
    price_completeness_score = _price_completeness_score(
        item_price_sar=item_price_sar,
        vat_status=vat_status,
        shipping_status=shipping_status,
        warranty_status=warranty_status,
        is_imported=is_imported,
        listing_condition=offer.listing_condition,
        marketplace_risk_score=offer.marketplace_risk_score,
    )
    final_landed_price_confidence = price_completeness_score
    if final_landed_price_sar is None and config.region_code == "SA":
        final_landed_price_confidence = min(final_landed_price_confidence, 0.35)
    recommended_candidate = (
        config.region_code == "SA"
        and bool(item_price_sar)
        and not is_marketplace
        and not is_imported
        and shipping_status != "unknown_shipping"
        and vat_status != "vat_unknown"
        and warranty_status != "unknown_warranty"
        and offer.marketplace_risk_score < 0.65
    )

    rank = 0.42
    if is_local:
        rank += 0.25
    if is_gcc:
        rank += 0.14
    if offer.currency == config.currency:
        rank += 0.1
    if vat_status != "vat_unknown":
        rank += 0.08
    if shipping_status != "unknown_shipping":
        rank += 0.08
    if warranty_status == "local_warranty":
        rank += 0.06
    rank += (local_stock_confidence + warranty_confidence + delivery_confidence) * 0.03
    if final_landed_incomplete:
        rank -= 0.1
    rank -= min(0.22, offer.marketplace_risk_score * 0.18)

    field_evidence = [
        *offer.field_evidence,
        *[
            FieldEvidence(
                field=field,
                value=value,
                source=offer.source.source,
                timestamp=offer.timestamp,
                trust_score=offer.source.trust_score,
                freshness_score=offer.source.freshness_score,
                source_tier=offer.source.tier,
            )
            for field, value in {
                "region": config.region_code,
                "vendor_region_type": region_type,
                "vat_status": vat_status,
                "shipping_status": shipping_status,
                "warranty_status": warranty_status,
                "local_stock_status": local_stock_status,
                "final_landed_price_sar": final_landed_price_sar,
            }.items()
            if value is not None
        ],
    ]

    return offer.model_copy(
        update={
            "region": config.region_code,
            "country_code": config.region_code,
            "city": city or offer.city or config.default_city,
            "raw_price": offer.raw_price or offer.price,
            "item_price": offer.item_price or offer.price,
            "item_price_sar": item_price_sar,
            "shipping_cost_sar": shipping_cost_sar,
            "final_landed_price": final_landed_price_sar if final_landed_price_sar is not None else offer.final_landed_price or (offer.price + offer.shipping_cost),
            "final_landed_currency": "SAR" if final_landed_price_sar is not None else offer.final_landed_currency or offer.currency,
            "final_landed_price_sar": final_landed_price_sar,
            "vat_included": vat_included,
            "vat_status": vat_status,
            "shipping_status": shipping_status,
            "warranty_status": warranty_status,
            "local_stock_status": local_stock_status,
            "vendor_region_type": region_type,
            "estimated_vat": estimated_vat,
            "import_fee": None,
            "seller_country": offer.seller_country,
            "is_local_stock": is_local,
            "is_imported": is_imported,
            "serves_saudi": serves_saudi_flag,
            "warranty_type": warranty_type,
            "local_warranty": local_warranty,
            "region_rank_score": round(max(0.0, min(rank, 1.0)), 2),
            "recommended_saudi_price_candidate": recommended_candidate,
            "final_landed_price_confidence": round(max(0.0, min(final_landed_price_confidence, 1.0)), 2),
            "price_completeness_score": round(max(0.0, min(price_completeness_score, 1.0)), 2),
            "trust_tier": trust_profile.trust_tier,
            "local_stock_confidence": local_stock_confidence,
            "warranty_confidence": warranty_confidence,
            "delivery_confidence": delivery_confidence,
            "field_evidence": field_evidence,
            "flags": _unique(flags),
            "vendor": offer.vendor.model_copy(update={"region": config.region_code}),
        }
    )


def _vat_status(offer: PriceOffer) -> str:
    text = _quality_text(offer)
    if "vat excluded" in text or "excluding vat" in text or "excl vat" in text:
        return "vat_excluded"
    if "vat included" in text or "including vat" in text or "incl vat" in text:
        return "vat_included"
    return "vat_unknown"


def _shipping_status(offer: PriceOffer) -> str:
    text = _quality_text(offer)
    if "pickup only" in text or "collection only" in text:
        return "pickup_only"
    if offer.shipping_cost > 0:
        return "paid_shipping"
    if "free shipping" in text or "free delivery" in text:
        return "free_shipping"
    return "unknown_shipping"


def _warranty_status(offer: PriceOffer, *, is_local: bool, is_gcc: bool, is_marketplace: bool) -> str:
    text = _quality_text(offer)
    if "manufacturer warranty" in text:
        return "manufacturer_warranty"
    if "seller warranty" in text:
        return "seller_warranty"
    if "local warranty" in text or "saudi warranty" in text:
        return "local_warranty"
    if is_marketplace:
        return "seller_warranty"
    if is_local or is_gcc:
        return "local_warranty"
    return "unknown_warranty"


def _quality_text(offer: PriceOffer) -> str:
    values = [
        offer.product.name,
        offer.vendor.name,
        str(offer.product.specs.get("delivery_text") or ""),
        str(offer.product.specs.get("raw_price_text") or ""),
    ]
    return " ".join(values).lower()


def _local_stock_confidence(status: str) -> float:
    return {
        "local_stock": 0.92,
        "gcc_stock": 0.76,
        "imported_stock": 0.35,
        "unknown_stock": 0.25,
    }.get(status, 0.25)


def _warranty_confidence(status: str) -> float:
    return {
        "local_warranty": 0.78,
        "manufacturer_warranty": 0.68,
        "seller_warranty": 0.46,
        "unknown_warranty": 0.24,
    }.get(status, 0.24)


def _delivery_confidence(status: str) -> float:
    return {
        "free_shipping": 0.86,
        "paid_shipping": 0.82,
        "pickup_only": 0.62,
        "unknown_shipping": 0.22,
    }.get(status, 0.22)


def _price_completeness_score(
    *,
    item_price_sar: float | None,
    vat_status: str,
    shipping_status: str,
    warranty_status: str,
    is_imported: bool,
    listing_condition: str,
    marketplace_risk_score: float,
) -> float:
    score = 1.0
    if item_price_sar is None:
        score -= 0.28
    if vat_status == "vat_unknown":
        score -= 0.16
    if shipping_status == "unknown_shipping":
        score -= 0.2
    if warranty_status == "unknown_warranty":
        score -= 0.14
    if is_imported:
        score -= 0.14
    if listing_condition == "unknown":
        score -= 0.1
    score -= min(0.16, marketplace_risk_score * 0.12)
    return round(max(0.0, min(score, 1.0)), 2)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _target_model_rejections(query: str, category: str, offer: PriceOffer) -> list[str]:
    normalized_category = normalize_category(category)
    if normalized_category == "GPU":
        requested_family = gpu_family_key_from_title(query)
        if not requested_family:
            return []
        offer_family = offer.product.specs.get("gpu_family_key")
        if offer_family == requested_family:
            return []
        return ["gpu_listing_does_not_match_requested_family"]
    if normalized_category == "CPU":
        requested_cpu = cpu_model_key_from_title(query)
        if not requested_cpu:
            return []
        offer_cpu = offer.product.specs.get("cpu_model_key") or cpu_model_key_from_title(
            f"{offer.product.name} {offer.product.model}"
        )
        if offer_cpu == requested_cpu:
            return []
        return ["cpu_listing_does_not_match_requested_model"]
    if normalized_category == "Storage":
        requested_storage = storage_model_key_from_title(query)
        if not requested_storage:
            return _generic_storage_target_rejections(query, offer)
        offer_storage = offer.product.specs.get("storage_model_key") or storage_model_key_from_title(
            f"{offer.product.name} {offer.product.model}"
        )
        if offer_storage != requested_storage:
            return ["storage_listing_does_not_match_requested_model"]
        query_has_heatsink = "HEATSINK" in query.upper()
        offer_has_heatsink = bool(offer.product.specs.get("heatsink"))
        if offer_has_heatsink and not query_has_heatsink:
            return ["storage_heatsink_variant_not_requested"]
        return []
    if normalized_category == "RAM":
        requested_ram = ram_family_key_from_title(query)
        if not requested_ram:
            return []
        offer_ram = offer.product.specs.get("ram_family_key") or ram_family_key_from_title(
            f"{offer.product.name} {offer.product.model}"
        )
        if offer_ram != requested_ram:
            return ["ram_listing_does_not_match_requested_family"]
        if offer.product.specs.get("desktop_or_laptop") == "laptop":
            return ["ram_listing_is_laptop_sodimm_memory"]
        return []
    if normalized_category == "PSU":
        requested_psu = psu_family_key_from_title(query)
        if not requested_psu:
            return []
        offer_psu = offer.product.specs.get("psu_family_key") or psu_family_key_from_title(
            f"{offer.product.name} {offer.product.model}"
        )
        if offer_psu != requested_psu:
            return ["psu_listing_does_not_match_requested_family"]
        if offer.product.specs.get("wattage_w") != 850:
            return ["psu_listing_does_not_match_requested_wattage"]
        return []
    if normalized_category == "Case":
        requested_case = case_family_key_from_title(query)
        if not requested_case:
            return []
        offer_case = offer.product.specs.get("case_family_key") or case_family_key_from_title(
            f"{offer.product.name} {offer.product.model}"
        )
        if offer_case != requested_case:
            return ["case_listing_does_not_match_requested_model"]
        return []
    if normalized_category == "Cooler":
        query_radiator = _cooler_radiator_size_from_query(query)
        offer_radiator = offer.product.specs.get("radiator_size_mm")
        if query_radiator and offer.product.specs.get("cooler_type") == "aio_liquid" and offer_radiator != query_radiator:
            return ["cooler_aio_radiator_size_does_not_match_requested_target"]
        requested_cooler = cooler_family_key_from_title(query)
        offer_cooler = offer.product.specs.get("cooler_family_key") or cooler_family_key_from_title(
            f"{offer.product.name} {offer.product.model}"
        )
        if requested_cooler and offer_cooler:
            offer_is_air = str(offer_cooler).startswith("COOLER_AIR")
            requested_base = str(requested_cooler).removesuffix("_AM5")
            offer_base = str(offer_cooler).removesuffix("_AM5")
            if not offer_is_air and offer_base != requested_base:
                return ["cooler_listing_does_not_match_requested_family"]
        return []
    if normalized_category == "Motherboard":
        requested_motherboard = motherboard_family_key_from_title(query)
        offer_motherboard = offer.product.specs.get("motherboard_family_key") or motherboard_family_key_from_title(
            f"{offer.product.name} {offer.product.model}"
        )
        if requested_motherboard and offer_motherboard != requested_motherboard:
            return ["motherboard_listing_does_not_match_requested_b650_am5_ddr5_family"]
        if offer.product.specs.get("socket") != "AM5":
            return ["motherboard_listing_does_not_match_requested_am5_socket"]
        if offer.product.specs.get("chipset") != "B650":
            return ["motherboard_listing_does_not_match_requested_b650_chipset"]
        if offer.product.specs.get("memory_type") != "DDR5":
            return ["motherboard_listing_does_not_match_requested_ddr5_memory"]
        return []
    return []


def _generic_storage_target_rejections(query: str, offer: PriceOffer) -> list[str]:
    import re

    reasons: list[str] = []
    query_text = query.upper()
    title_text = f"{offer.product.name} {offer.product.model}".upper()
    if re.search(r"\b2\s?TB\b", query_text):
        if offer.product.specs.get("capacity_gb") != 2048:
            reasons.append("storage_listing_does_not_match_requested_capacity")
    if "NVME" in query_text and offer.product.specs.get("interface") != "NVMe":
        reasons.append("storage_listing_is_not_nvme_target")
    if re.search(r"\bSATA\b", title_text):
        reasons.append("storage_listing_is_sata_not_nvme")
    if offer.product.specs.get("storage_model_key") is None:
        reasons.append("storage_listing_model_not_in_allowed_alternative_set")
    return reasons


def _cooler_radiator_size_from_query(query: str) -> int | None:
    import re

    match = re.search(r"\b(120|140|240|280|360|420)\s?mm\b", query, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


class ProductDiscoveryService:
    def __init__(self, ingestion: PricingIngestionService) -> None:
        self.ingestion = ingestion

    def discover(
        self,
        *,
        categories: list[str] | None = None,
        query: str | None = None,
        region: str = "SA",
        city: str | None = None,
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
                city=city,
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
