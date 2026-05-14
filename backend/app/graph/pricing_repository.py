from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from typing import Any
from uuid import uuid4

from neo4j import Driver

from app.core.config import settings
from app.models.catalog import (
    CatalogCategoryCoverage,
    CatalogCoverageResponse,
    CatalogFeedImportResponse,
    CatalogFeedImportRow,
    CatalogFeedRunView,
)
from app.models.pricing import (
    CpuSpecsImportResponse,
    CpuSpecsImportRow,
    CpuSpecsImportedProduct,
    FieldEvidence,
    PriceHistoryPoint,
    PriceOffer,
    PriceSnapshotView,
    PricingJob,
    ProductDetail,
    ProductIdentity,
    ProductSearchResult,
    SourceTier,
    SourceType,
)
from app.models.intelligence import HardwareIntelligence
from app.services.hardware_taxonomy import GLOBAL_HARDWARE_CATEGORIES
from app.services.pricing_classification import infer_listing_market
from app.services.pricing_normalization import cpu_model_key_from_title
from app.services.region_config import get_region_config, normalize_region, vendor_region_type, vendor_trust_profile


ACTIVE_PRICE_AVAILABILITY = {"in_stock", "preorder", "backorder"}
ACTIVE_BUILD_CATEGORIES = {"CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"}
CATALOG_CATEGORY_LABELS = {
    "CPU": "CPU",
    "GPU": "GPU",
    "Motherboard": "Motherboard",
    "RAM": "RAM",
    "Storage": "Storage",
    "PSU": "PSU",
    "Case": "Case",
    "Cooler": "Cooler",
    "Monitor": "Monitor",
    "Keyboard": "Keyboard",
    "Mouse": "Mouse",
    "Speaker": "Speaker",
    "Accessories": "Accessories",
}


def _refresh_priority_for_category(category: str) -> int:
    return 90 if category in ACTIVE_BUILD_CATEGORIES else 50


def _legacy_us_region_condition(alias: str = "snapshot") -> str:
    return f"({alias}.region = $region OR ($region = \"US\" AND {alias}.region IS NULL))"


def _clean_properties(values: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool, datetime)):
            clean[key] = value
        elif isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
            clean[key] = value
        else:
            clean[key] = json.dumps(value, sort_keys=True)
    return clean


def _category_label(category: str | None) -> str:
    return CATALOG_CATEGORY_LABELS.get(str(category or "").strip(), "Accessories")


def _catalog_canonical_key(category: str, name: str, brand: str | None, model: str | None) -> str:
    parts = [category, brand or _brand_from_name(name) or "UNKNOWN", model or name]
    normalized = [
        re.sub(r"[^A-Z0-9]+", "_", str(part).upper()).strip("_")
        for part in parts
        if str(part).strip()
    ]
    return "|".join(normalized)


def _brand_from_name(name: str) -> str | None:
    match = re.search(
        r"\b(AMD|Intel|NVIDIA|ASUS|MSI|Gigabyte|Corsair|Kingston|Samsung|WD|Crucial|DeepCool|NZXT|Seasonic|Thermalright|Cooler Master)\b",
        name,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _product_properties(identity: ProductIdentity) -> dict[str, Any]:
    props = {
        "name": identity.name,
        "brand": identity.brand,
        "category": identity.category,
        "model": identity.model,
        "normalized_model": identity.normalized_model,
        "canonical_key": identity.canonical_key,
        "data_origin": "live",
        "msrp": identity.msrp,
        "imageUrl": identity.image_url,
        "processed_image_url": identity.processed_image_url,
        "updated_at": datetime.now(UTC),
    }
    for key, value in identity.specs.items():
        props[f"spec_{key}"] = value
    return _clean_properties(props)


def _evidence_payload(evidence: FieldEvidence) -> dict[str, Any]:
    return _clean_properties(
        {
            "field": evidence.field,
            "value_json": json.dumps(evidence.value, sort_keys=True),
            "source": evidence.source,
            "timestamp": evidence.timestamp,
            "trust_score": evidence.trust_score,
            "freshness_score": evidence.freshness_score,
            "source_tier": int(evidence.source_tier),
        }
    )


def _snapshot_view(data: dict[str, Any]) -> PriceSnapshotView:
    inferred = infer_listing_market(
        vendor_name=data.get("vendor_name"),
        source=data.get("source"),
        seller=data.get("seller"),
        condition=data.get("listing_condition") or data.get("condition"),
    )
    listing_condition = data.get("listing_condition") or inferred.listing_condition
    seller_type = data.get("seller_type") or inferred.seller_type
    marketplace_risk_score = data.get("marketplace_risk_score")
    flags = list(dict.fromkeys([*(data.get("flags") or []), *inferred.flags]))
    region = data.get("region") or "US"
    currency = data["currency"]
    is_local_stock = data.get("is_local_stock")
    if is_local_stock is None:
        is_local_stock = region == "US" and currency == "USD"
    is_imported = data.get("is_imported")
    if is_imported is None:
        is_imported = not bool(is_local_stock)
    serves_saudi_value = data.get("serves_saudi")
    view = PriceSnapshotView(
        id=data["id"],
        vendor_id=data["vendor_id"],
        vendor_name=data["vendor_name"],
        price=float(data["price"]),
        currency=currency,
        region=region,
        country_code=data.get("country_code") or region,
        city=data.get("city"),
        raw_price=_optional_float(data.get("raw_price")),
        item_price=_optional_float(data.get("item_price")),
        item_price_sar=_optional_float(data.get("item_price_sar")),
        shipping_cost_sar=_optional_float(data.get("shipping_cost_sar")),
        final_landed_price=_optional_float(data.get("final_landed_price")),
        final_landed_currency=data.get("final_landed_currency"),
        final_landed_price_sar=_optional_float(data.get("final_landed_price_sar")),
        vat_included=data.get("vat_included"),
        vat_status=data.get("vat_status") or "vat_unknown",
        shipping_status=data.get("shipping_status") or "unknown_shipping",
        warranty_status=data.get("warranty_status") or "unknown_warranty",
        local_stock_status=data.get("local_stock_status") or "unknown_stock",
        vendor_region_type=data.get("vendor_region_type") or "unknown_vendor",
        estimated_vat=_optional_float(data.get("estimated_vat")),
        import_fee=_optional_float(data.get("import_fee")),
        estimated_delivery_days=data.get("estimated_delivery_days"),
        seller_country=data.get("seller_country"),
        is_local_stock=bool(is_local_stock),
        is_imported=bool(is_imported),
        serves_saudi=bool(serves_saudi_value) if serves_saudi_value is not None else None,
        warranty_type=data.get("warranty_type"),
        local_warranty=data.get("local_warranty"),
        region_rank_score=_optional_float(data.get("region_rank_score")),
        recommended_saudi_price_candidate=bool(data.get("recommended_saudi_price_candidate", False)),
        final_landed_price_confidence=_optional_float(data.get("final_landed_price_confidence")),
        price_completeness_score=_optional_float(data.get("price_completeness_score")),
        trust_tier=data.get("trust_tier") or vendor_trust_profile(data.get("vendor_name"), region).trust_tier,
        delivery_status=data.get("delivery_status") or data.get("shipping_status") or "unknown_shipping",
        local_stock_confidence=_optional_float(data.get("local_stock_confidence")),
        warranty_confidence=_optional_float(data.get("warranty_confidence")),
        delivery_confidence=_optional_float(data.get("delivery_confidence")),
        availability=data["availability"],
        timestamp=_to_datetime(data["timestamp"]),
        shipping_cost=float(data.get("shipping_cost") or 0),
        product_url=data.get("product_url"),
        source=data["source"],
        source_type=SourceType(data["source_type"]),
        source_tier=SourceTier(int(data["source_tier"])),
        trust_score=float(data["trust_score"]),
        freshness_score=float(data["freshness_score"]),
        stale=bool(data.get("stale", False)),
        accepted=bool(data.get("accepted", True)),
        listing_condition=listing_condition,
        seller_type=seller_type,
        marketplace_risk_score=float(
            marketplace_risk_score if marketplace_risk_score is not None else inferred.marketplace_risk_score
        ),
        flags=flags,
    )
    return _with_listing_decision(view)


def _search_result(data: dict[str, Any]) -> ProductSearchResult:
    current = data.get("current_recommended_price")
    previous = data.get("previous_price")
    drop = None
    if current and previous and previous > 0 and current < previous:
        drop = round((previous - current) / previous * 100, 2)
    return ProductSearchResult(
        id=data["id"],
        canonical_key=data.get("canonical_key"),
        name=data["name"],
        brand=data.get("brand"),
        category=data["category"],
        model=data.get("model"),
        summary_specs=dict(data.get("summary_specs") or {}),
        image_url=data.get("image_url"),
        processed_image_url=data.get("processed_image_url"),
        seller_count=int(data.get("seller_count") or 0),
        cheapest_vendor=data.get("cheapest_vendor"),
        cheapest_price_sar=_optional_float(data.get("cheapest_price_sar")),
        compatibility_tags=list(data.get("compatibility_tags") or []),
        data_origin=data.get("data_origin") or "unknown",
        price_status=data.get("price_status") or "unavailable",
        flags=list(data.get("flags") or []),
        region=data.get("region") or "US",
        region_currency=data.get("region_currency"),
        region_price_status=data.get("region_price_status") or data.get("price_status"),
        recommended_reason=data.get("recommended_reason"),
        recommended_level=data.get("recommended_level"),
        price_confidence=data.get("price_confidence"),
        lowest_price_warning=data.get("lowest_price_warning"),
        current_best_price=float(current) if current is not None else None,
        current_best_currency=data.get("current_recommended_currency"),
        current_best_vendor=data.get("current_recommended_vendor"),
        current_recommended_price=float(current) if current is not None else None,
        current_recommended_currency=data.get("current_recommended_currency"),
        current_recommended_vendor=data.get("current_recommended_vendor"),
        current_recommended_condition=data.get("current_recommended_condition"),
        current_recommended_seller_type=data.get("current_recommended_seller_type"),
        current_recommended_marketplace_risk_score=data.get("current_recommended_marketplace_risk_score"),
        lowest_market_price=_optional_float(data.get("lowest_market_price")),
        lowest_market_currency=data.get("lowest_market_currency"),
        lowest_market_vendor=data.get("lowest_market_vendor"),
        lowest_market_condition=data.get("lowest_market_condition"),
        lowest_market_seller_type=data.get("lowest_market_seller_type"),
        lowest_marketplace_risk_score=data.get("lowest_marketplace_risk_score"),
        best_new_price=_optional_float(data.get("best_new_price")),
        best_new_currency=data.get("best_new_currency"),
        best_new_vendor=data.get("best_new_vendor"),
        best_trusted_price=_optional_float(data.get("best_trusted_price")),
        best_trusted_currency=data.get("best_trusted_currency"),
        best_trusted_vendor=data.get("best_trusted_vendor"),
        best_local_price=_optional_float(data.get("best_local_price")),
        best_local_currency=data.get("best_local_currency"),
        best_local_vendor=data.get("best_local_vendor"),
        best_used_price=_optional_float(data.get("best_used_price")),
        best_used_currency=data.get("best_used_currency"),
        best_used_vendor=data.get("best_used_vendor"),
        current_price_freshness_score=data.get("current_price_freshness_score"),
        current_price_trust_score=data.get("current_price_trust_score"),
        current_price_timestamp=_to_datetime(data.get("current_price_timestamp")),
        stale=bool(data.get("stale", False)),
        best_value=bool(data.get("best_value", False)),
        price_drop_percent=drop,
    )


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_native"):
        return value.to_native()
    return value


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(value, 1.0)), 2)


def _price_total(price: PriceSnapshotView) -> float:
    if price.region == "SA" and price.final_landed_price_sar is not None:
        return price.final_landed_price_sar
    if price.final_landed_price is not None:
        return price.final_landed_price
    return price.price + price.shipping_cost


def _requires_price_review(price: PriceSnapshotView) -> bool:
    return (
        "price_requires_review" in price.flags
        or price.listing_condition == "unknown"
        or price.marketplace_risk_score >= 0.65
        or (
            price.listing_condition == "unknown"
            and price.seller_type in {"marketplace", "third_party"}
        )
    )


def _is_suspicious_price(price: PriceSnapshotView) -> bool:
    return bool(
        {
            "unusually_low_price",
            "unusually_high_price",
            "suspicious_low_price",
            "suspicious_high_price",
            "suspicious_price_below_gpu_family_market_range",
            "suspicious_price_above_gpu_family_market_range",
            "suspicious_price_below_cpu_model_market_range",
            "suspicious_price_above_cpu_model_market_range",
            "suspicious_price_below_storage_model_market_range",
            "suspicious_price_above_storage_model_market_range",
            "suspicious_price_below_ram_family_market_range",
            "suspicious_price_above_ram_family_market_range",
            "suspicious_price_below_psu_family_market_range",
            "suspicious_price_above_psu_family_market_range",
        }.intersection(price.flags)
    )


def _price_completeness(price: PriceSnapshotView) -> float:
    if price.price_completeness_score is not None:
        return price.price_completeness_score
    score = 1.0
    has_sa_price = price.item_price_sar is not None or (price.region == "SA" and price.currency == "SAR")
    if price.region == "SA" and not has_sa_price:
        score -= 0.28
    if price.vat_status == "vat_unknown":
        score -= 0.16
    if price.shipping_status == "unknown_shipping":
        score -= 0.2
    if price.warranty_status == "unknown_warranty":
        score -= 0.14
    if price.is_imported:
        score -= 0.14
    if price.listing_condition == "unknown":
        score -= 0.1
    score -= min(0.16, price.marketplace_risk_score * 0.12)
    return _clamp_score(score)


def _listing_warnings(price: PriceSnapshotView) -> list[str]:
    warnings: list[str] = []
    if price.vat_status == "vat_unknown":
        warnings.append("VAT unclear")
    if price.shipping_status == "unknown_shipping":
        warnings.append("Shipping unclear")
    if price.warranty_status == "unknown_warranty":
        warnings.append("Warranty unclear")
    if price.is_imported or price.local_stock_status == "imported_stock":
        warnings.append("Imported listing")
    if price.seller_type == "marketplace" or "marketplace_listing" in price.flags:
        warnings.append("Marketplace seller")
    if price.listing_condition == "unknown":
        warnings.append("Condition unknown")
    if _is_suspicious_price(price):
        warnings.append("Price outside normal market range")
    if "final_landed_price_incomplete" in price.flags or "price_not_final" in price.flags:
        warnings.append("Final landed price is not fully proven")
    return list(dict.fromkeys(warnings))


def _trust_tier_rank(tier: str | None) -> int:
    return {"high": 0, "medium": 1, "unknown": 2, "low": 3}.get(tier or "unknown", 2)


def _trust_tier_score(tier: str | None) -> float:
    return {"high": 0.92, "medium": 0.74, "unknown": 0.48, "low": 0.28}.get(tier or "unknown", 0.48)


def _recommendation_level(price: PriceSnapshotView, confidence: float) -> str:
    has_sa_price = price.item_price_sar is not None or (price.region == "SA" and price.currency == "SAR")
    local_or_gcc = price.vendor_region_type in {"local_saudi_vendor", "local", "gcc_vendor"} or bool(price.is_local_stock)
    trusted = price.trust_tier in {"high", "medium"} or price.seller_type in {"retailer", "manufacturer"}
    marketplace_or_imported = (
        bool(price.is_imported)
        or price.seller_type in {"marketplace", "third_party"}
        or price.marketplace_risk_score >= 0.65
        or price.vendor_region_type in {"international_vendor", "marketplace_vendor"}
    )
    if price.availability not in ACTIVE_PRICE_AVAILABILITY or _is_suspicious_price(price):
        return "not_recommended"
    if price.region == "SA" and not has_sa_price:
        return "insufficient_data"
    if marketplace_or_imported:
        return "not_recommended" if price.marketplace_risk_score >= 0.72 else "acceptable_with_risk"
    if local_or_gcc and trusted:
        clean = (
            price.vat_status != "vat_unknown"
            and price.shipping_status != "unknown_shipping"
            and price.warranty_status in {"local_warranty", "manufacturer_warranty"}
            and price.listing_condition == "new"
        )
        if clean and confidence >= 0.72:
            return "recommended"
        if confidence >= 0.55:
            return "acceptable_with_risk"
        return "insufficient_data"
    if trusted and confidence >= 0.6:
        return "good_if_price_matters"
    return "insufficient_data"


def _listing_reason(price: PriceSnapshotView, level: str, warnings: list[str]) -> str:
    if level == "recommended":
        return "Trusted Saudi/GCC option with clear enough price, delivery, and warranty signals."
    if level == "good_if_price_matters":
        return "Price is competitive and source trust is acceptable, but it is not the safest local option."
    if level == "acceptable_with_risk":
        return "Local or local-serving vendor looks usable, but some VAT, shipping, condition, or warranty evidence is incomplete."
    if level == "not_recommended":
        return "Cheaper option carries marketplace/import/imported or suspicious-price risk and should not be the default buy choice."
    if warnings:
        return "Not enough evidence to recommend because " + ", ".join(warnings[:3]).lower() + "."
    return "Not enough listing evidence to recommend this option."


def _with_listing_decision(price: PriceSnapshotView) -> PriceSnapshotView:
    trust_profile = vendor_trust_profile(price.vendor_name, price.region)
    trust_tier = price.trust_tier if price.trust_tier != "unknown" else trust_profile.trust_tier
    completeness = _price_completeness(price)
    confidence = _clamp_score(
        price.trust_score * 0.28
        + price.freshness_score * 0.18
        + (1 - price.marketplace_risk_score) * 0.18
        + _trust_tier_score(trust_tier) * 0.18
        + completeness * 0.18
    )
    if price.is_local_stock:
        confidence = _clamp_score(confidence + 0.04)
    if price.vat_status == "vat_unknown":
        confidence = _clamp_score(confidence - 0.05)
    if price.shipping_status == "unknown_shipping":
        confidence = _clamp_score(confidence - 0.06)
    if price.warranty_status == "unknown_warranty":
        confidence = _clamp_score(confidence - 0.04)
    warnings = _listing_warnings(price)
    decision_price = price.model_copy(update={"trust_tier": trust_tier})
    level = _recommendation_level(decision_price, confidence)
    reason = _listing_reason(price, level, warnings)
    flags = list(price.flags)
    if trust_tier in {"high", "medium"} and price.vendor_region_type in {"local_saudi_vendor", "local", "gcc_vendor"}:
        flags.append("trusted_local_vendor")
    if price.is_local_stock:
        flags.append("local_stock_likely")
    if price.local_warranty:
        flags.append("local_warranty_likely")
    if price.vat_status == "vat_unknown":
        flags.append("vat_unknown")
    if price.shipping_status == "unknown_shipping":
        flags.append("shipping_unknown")
    if price.warranty_status == "unknown_warranty":
        flags.append("warranty_unknown")
    if price.seller_type == "marketplace":
        flags.append("marketplace_seller")
    if price.is_imported:
        flags.append("imported_listing")
    if price.listing_condition == "unknown":
        flags.append("used_or_unknown_condition")
    if "final_landed_price_incomplete" in flags:
        flags.append("price_not_final")
    if level == "recommended":
        flags.append("recommended_saudi_buy")
    if level in {"recommended", "acceptable_with_risk"} and price.vendor_region_type in {"local_saudi_vendor", "gcc_vendor"}:
        flags.append("good_local_deal")
    return price.model_copy(
        update={
            "trust_tier": trust_tier,
            "delivery_status": price.shipping_status,
            "final_landed_price_confidence": price.final_landed_price_confidence
            if price.final_landed_price_confidence is not None
            else completeness,
            "price_completeness_score": completeness,
            "confidence_score": confidence,
            "buy_recommendation_level": level,
            "buy_recommendation_reason": reason,
            "recommendation_reason": reason,
            "warnings": warnings,
            "flags": list(dict.fromkeys(flags)),
        }
    )


def _price_map(price: PriceSnapshotView | None) -> dict[str, Any]:
    if not price:
        return {}
    return {
        "price": _price_total(price),
        "currency": price.final_landed_currency or price.currency,
        "vendor": price.vendor_name,
        "condition": price.listing_condition,
        "seller_type": price.seller_type,
        "marketplace_risk_score": price.marketplace_risk_score,
        "recommendation_level": price.buy_recommendation_level,
        "recommendation_reason": price.recommendation_reason,
        "confidence_score": price.confidence_score,
        "warnings": price.warnings,
        "trust_score": price.trust_score,
        "freshness_score": price.freshness_score,
        "timestamp": price.timestamp,
        "is_local_stock": price.is_local_stock,
        "is_imported": price.is_imported,
        "region_rank_score": price.region_rank_score,
    }


def _best_by_price(prices: list[PriceSnapshotView], *, currency: str = "USD") -> PriceSnapshotView | None:
    return min(
        prices,
        key=lambda price: (
            0 if (price.final_landed_currency or price.currency) == currency else 1,
            _price_total(price),
            price.marketplace_risk_score,
            -price.trust_score,
            -price.freshness_score,
        ),
        default=None,
    )


def _best_recommended(
    prices: list[PriceSnapshotView],
    *,
    currency: str = "USD",
    region: str | None = None,
) -> PriceSnapshotView | None:
    region_code = normalize_region(region)
    if region_code == "SA":
        candidates = [
            price
            for price in prices
            if price.buy_recommendation_level in {"recommended", "good_if_price_matters", "acceptable_with_risk"}
        ]
    else:
        candidates = [price for price in prices if not _requires_price_review(price)]
    if not candidates:
        return None
    level_rank = {
        "recommended": 0,
        "good_if_price_matters": 1,
        "acceptable_with_risk": 2,
        "insufficient_data": 3,
        "not_recommended": 4,
    }
    return sorted(
        candidates,
        key=lambda price: (
            level_rank.get(price.buy_recommendation_level, 3),
            0 if price.recommended_saudi_price_candidate else 1,
            _local_stock_rank(price.local_stock_status),
            _vendor_region_rank(price.vendor_region_type),
            _trust_tier_rank(price.trust_tier),
            0 if price.vat_status != "vat_unknown" else 1,
            0 if price.shipping_status != "unknown_shipping" else 1,
            0 if price.warranty_status == "local_warranty" else 1,
            0 if price.is_local_stock else 1,
            0 if price.local_warranty else 1,
            0 if (price.final_landed_currency or price.currency) == currency else 1,
            0 if price.listing_condition == "new" else 1,
            0 if price.seller_type in {"retailer", "manufacturer"} else 1,
            price.marketplace_risk_score,
            -(price.confidence_score or 0),
            -(price.price_completeness_score or 0),
            -(price.region_rank_score or 0),
            -price.trust_score,
            -price.freshness_score,
            _price_total(price),
        ),
    )[0]


def _best_local_price(prices: list[PriceSnapshotView], *, currency: str = "USD") -> PriceSnapshotView | None:
    return _best_by_price(
        [
            price
            for price in prices
            if price.vendor_region_type in {"local_saudi_vendor", "local", "gcc_vendor"} or bool(price.is_local_stock)
        ],
        currency=currency,
    )


def _best_trusted_price(prices: list[PriceSnapshotView], *, currency: str = "USD", region: str | None = None) -> PriceSnapshotView | None:
    if normalize_region(region) == "SA":
        return _best_by_price(
            [
                price
                for price in prices
                if price.trust_tier in {"high", "medium"}
                and price.vendor_region_type in {"local_saudi_vendor", "local", "gcc_vendor"}
                and price.marketplace_risk_score < 0.65
            ],
            currency=currency,
        )
    return _best_by_price(
        [
            price
            for price in prices
            if price.seller_type in {"retailer", "manufacturer"} and not _requires_price_review(price)
        ],
        currency=currency,
    )


def _local_stock_rank(status: str | None) -> int:
    return {
        "local_stock": 0,
        "gcc_stock": 1,
        "unknown_stock": 2,
        "imported_stock": 3,
    }.get(status or "unknown_stock", 2)


def _vendor_region_rank(vendor_region_type: str | None) -> int:
    return {
        "local_saudi_vendor": 0,
        "local": 0,
        "gcc_vendor": 1,
        "unknown_vendor": 2,
        "international_vendor": 3,
        "marketplace_vendor": 4,
    }.get(vendor_region_type or "unknown_vendor", 2)


def _price_rollups(prices: list[PriceSnapshotView], *, region: str | None = None) -> dict[str, Any]:
    resolved_region = normalize_region(region if region is not None else (prices[0].region if prices else None))
    config = get_region_config(resolved_region)
    active = [
        _with_listing_decision(price)
        for price in prices
        if price.accepted and not price.stale and price.availability in ACTIVE_PRICE_AVAILABILITY
    ]
    stale = [price for price in prices if price.accepted and price.stale]
    lowest = _best_by_price(active, currency=config.currency)
    recommended = _best_recommended(active, currency=config.currency, region=config.region_code)
    best_new = _best_by_price([price for price in active if price.listing_condition == "new"], currency=config.currency)
    best_trusted = _best_trusted_price(active, currency=config.currency, region=config.region_code)
    best_local = _best_local_price(active, currency=config.currency)
    best_used = _best_by_price(
        [price for price in active if price.listing_condition in {"used", "refurbished", "open_box"}],
        currency=config.currency,
    )
    flags: list[str] = []
    for price in active[:8]:
        flags.extend(price.flags)
    price_status = "active" if active else "stale" if stale else "unavailable"
    low = _price_map(lowest)
    rec = _price_map(recommended)
    new = _price_map(best_new)
    trusted = _price_map(best_trusted)
    local = _price_map(best_local)
    used = _price_map(best_used)
    lowest_warning = _lowest_price_warning(lowest, recommended)
    if lowest_warning:
        flags.append("cheapest_but_risky")
    if recommended:
        flags.append("recommended_saudi_buy")
    return {
        "price_status": price_status,
        "seller_count": len({price.vendor_id for price in active}),
        "cheapest_vendor": low.get("vendor"),
        "cheapest_price_sar": low.get("price") if low.get("currency") == "SAR" else None,
        "region": config.region_code,
        "region_currency": config.currency,
        "region_price_status": price_status,
        "recommended_reason": _recommended_reason(recommended, config.currency),
        "recommended_level": recommended.buy_recommendation_level if recommended else None,
        "price_confidence": _price_confidence(recommended),
        "lowest_price_warning": lowest_warning,
        "flags": list(dict.fromkeys(flags)),
        "current_recommended_price": rec.get("price"),
        "current_recommended_currency": rec.get("currency"),
        "current_recommended_vendor": rec.get("vendor"),
        "current_recommended_condition": rec.get("condition"),
        "current_recommended_seller_type": rec.get("seller_type"),
        "current_recommended_marketplace_risk_score": rec.get("marketplace_risk_score"),
        "lowest_market_price": low.get("price"),
        "lowest_market_currency": low.get("currency"),
        "lowest_market_vendor": low.get("vendor"),
        "lowest_market_condition": low.get("condition"),
        "lowest_market_seller_type": low.get("seller_type"),
        "lowest_marketplace_risk_score": low.get("marketplace_risk_score"),
        "best_new_price": new.get("price"),
        "best_new_currency": new.get("currency"),
        "best_new_vendor": new.get("vendor"),
        "best_trusted_price": trusted.get("price"),
        "best_trusted_currency": trusted.get("currency"),
        "best_trusted_vendor": trusted.get("vendor"),
        "best_local_price": local.get("price"),
        "best_local_currency": local.get("currency"),
        "best_local_vendor": local.get("vendor"),
        "best_used_price": used.get("price"),
        "best_used_currency": used.get("currency"),
        "best_used_vendor": used.get("vendor"),
        "current_price_freshness_score": rec.get("freshness_score"),
        "current_price_trust_score": rec.get("trust_score"),
        "current_price_timestamp": rec.get("timestamp"),
    }


def _lowest_price_warning(lowest: PriceSnapshotView | None, recommended: PriceSnapshotView | None) -> str | None:
    if not lowest:
        return None
    if recommended and lowest.id == recommended.id:
        return None
    warnings = _listing_warnings(lowest)
    if lowest.buy_recommendation_level in {"not_recommended", "insufficient_data"} or warnings:
        return "Cheapest listing is not the safest buy option: " + ", ".join((warnings or ["insufficient evidence"])[:3]).lower() + "."
    return None


def _recommended_reason(price: PriceSnapshotView | None, currency: str) -> str | None:
    if not price:
        return None
    if price.recommendation_reason:
        return price.recommendation_reason
    reasons = ["quality-passed snapshot"]
    if price.is_local_stock:
        reasons.append("local stock")
    if price.local_warranty:
        reasons.append("local warranty")
    if (price.final_landed_currency or price.currency) == currency:
        reasons.append(f"{currency} market price")
    return ", ".join(reasons)


def _price_confidence(price: PriceSnapshotView | None) -> float | None:
    if not price:
        return None
    if price.confidence_score is not None:
        return price.confidence_score
    confidence = price.trust_score * 0.45 + price.freshness_score * 0.3 + (1 - price.marketplace_risk_score) * 0.2
    if price.is_local_stock:
        confidence += 0.05
    for value in (price.local_stock_confidence, price.warranty_confidence, price.delivery_confidence):
        if value is not None:
            confidence += value * 0.025
    if price.vat_status == "vat_unknown":
        confidence -= 0.08
    if price.shipping_status == "unknown_shipping":
        confidence -= 0.08
    if price.warranty_status == "unknown_warranty":
        confidence -= 0.06
    return round(max(0.0, min(confidence, 1.0)), 2)


def _finalize_search_data(data: dict[str, Any], rollups: dict[str, Any]) -> dict[str, Any]:
    data = {**data, **rollups}
    data["compatibility_tags"] = _compatibility_tags(data.get("category"), data.get("summary_specs") or {})
    seed_without_price = not data.get("canonical_key") and data["price_status"] == "unavailable"
    data["data_origin"] = data.get("data_origin") or ("seed" if seed_without_price else "live")
    if seed_without_price:
        data["stale"] = True
        data["flags"] = list(dict.fromkeys([*(data.get("flags") or []), "stale_seed_product"]))
    return data


def _compatibility_tags(category: str | None, specs: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    category = str(category or "")
    for key in ("socket", "chipset", "memory_type", "form_factor", "efficiency_rating"):
        value = specs.get(key)
        if isinstance(value, str) and value.strip():
            tags.append(value.strip())
    if category == "CPU" and specs.get("tdp_w"):
        tags.append(f"{specs['tdp_w']}W TDP")
    if category == "RAM":
        capacity = specs.get("capacity_gb")
        speed = specs.get("speed_mhz") or specs.get("speed_mt_s")
        if capacity:
            tags.append(f"{capacity}GB")
        if speed:
            tags.append(f"{speed}MT/s")
    if category == "Storage":
        capacity = specs.get("capacity_gb")
        interface = specs.get("interface")
        if capacity:
            tags.append(f"{capacity}GB")
        if interface:
            tags.append(str(interface))
    if category == "PSU":
        wattage = specs.get("wattage_w") or specs.get("wattage")
        if wattage:
            tags.append(f"{wattage}W")
    return list(dict.fromkeys(tags[:8]))


def _form_factors_for_category(category: str, specs: dict[str, Any]) -> list[str]:
    if category == "Motherboard":
        return [str(specs.get("form_factor") or "").strip()]
    if category == "Case":
        values = specs.get("supported_motherboard_form_factors") or specs.get("supported_form_factors") or []
        if isinstance(values, str):
            values = re.split(r"[,/|]", values)
        if isinstance(values, list):
            return [str(value).strip() for value in values if str(value).strip()]
    return []


def _catalog_product_properties(row: CatalogFeedImportRow, category: str, source_name: str) -> dict[str, Any]:
    brand = row.brand or _brand_from_name(row.name)
    props: dict[str, Any] = {
        "name": row.name,
        "brand": brand,
        "category": category,
        "model": row.model,
        "normalized_model": row.model,
        "data_origin": "spec_feed",
        "spec_source_name": source_name,
        "spec_source_type": "catalog_feed",
        "spec_updated_at": datetime.now(UTC),
        "imageUrl": row.image_url,
        "image_url": row.image_url,
        "processed_image_url": row.processed_image_url,
    }
    for key, value in row.specs.items():
        props[f"spec_{key}"] = value
    return _clean_properties(props)


def _catalog_has_required_specs(category: str, props: dict[str, Any]) -> bool:
    required = {
        "CPU": ("spec_socket", "spec_cores", "spec_threads"),
        "Motherboard": ("spec_socket", "spec_memory_type", "spec_form_factor"),
        "RAM": ("spec_memory_type", "spec_capacity_gb"),
        "Storage": ("spec_capacity_gb", "spec_interface"),
        "PSU": ("spec_wattage_w", "spec_efficiency_rating"),
        "Case": ("spec_supported_motherboard_form_factors",),
        "Cooler": ("spec_cooler_type",),
        "GPU": (),
    }.get(category, ())
    return all(props.get(key) not in (None, "", []) for key in required)


def _coverage_next_action(category: str, priced_count: int, missing_specs: int, stale_count: int) -> str:
    if priced_count == 0:
        return f"Add trusted Saudi product URLs or structured price rows for {category}."
    if missing_specs:
        return f"Import compatibility-grade specs for {missing_specs} {category} product(s)."
    if stale_count:
        return f"Refresh approved known URLs for {category} to reduce stale prices."
    return "Keep normal price refresh monitoring."


def _search_sort_key(product: ProductSearchResult) -> tuple[int, float, float, str]:
    live = product.data_origin == "live"
    if live and product.price_status == "active" and product.current_recommended_price is not None:
        bucket = 0
    elif live and product.price_status == "active":
        bucket = 1
    elif live and product.price_status == "stale":
        bucket = 2
    else:
        bucket = 3
    canonical_penalty = _canonical_search_penalty(product)
    price = product.current_recommended_price or product.lowest_market_price or float("inf")
    return bucket, canonical_penalty, price, product.name.lower()


def _search_product_sort_key(product: ProductSearchResult, sort: str) -> tuple[Any, ...]:
    price = product.cheapest_price_sar or product.current_recommended_price or product.lowest_market_price
    if sort == "cheapest":
        return (price is None, price or float("inf"), product.name.lower())
    if sort == "newest":
        timestamp = product.current_price_timestamp.timestamp() if product.current_price_timestamp else 0
        return (-timestamp, product.name.lower())
    if sort == "name":
        return (product.name.lower(),)
    return _search_sort_key(product)


def _search_product_filter(
    product: ProductSearchResult,
    *,
    min_price_sar: float | None,
    max_price_sar: float | None,
    in_stock_priced_only: bool,
) -> bool:
    price = product.cheapest_price_sar or product.current_recommended_price or product.lowest_market_price
    if in_stock_priced_only and price is None:
        return False
    if min_price_sar is not None and (price is None or price < min_price_sar):
        return False
    if max_price_sar is not None and (price is None or price > max_price_sar):
        return False
    return True


def _canonical_search_penalty(product: ProductSearchResult) -> float:
    if product.category != "CPU":
        return 0
    text = f"{product.canonical_key or ''} {product.model or ''} {product.name}".upper().replace(" ", "")
    if "7800X3D" in text and "RYZEN_7_7800X3D" not in (product.canonical_key or ""):
        return 1
    return 0


def _cpu_product_first_results(products: list[ProductSearchResult]) -> list[ProductSearchResult]:
    grouped: dict[str, list[ProductSearchResult]] = {}
    passthrough: list[ProductSearchResult] = []
    for product in products:
        key = _cpu_canonical_key(product)
        if not key:
            passthrough.append(product)
            continue
        grouped.setdefault(key, []).append(product)

    canonical_products = [_stable_cpu_product(key, group) for key, group in grouped.items()]
    return [*canonical_products, *passthrough]


def _stable_cpu_product(key: str, group: list[ProductSearchResult]) -> ProductSearchResult:
    cheapest = min(group, key=_cpu_price_sort_value)
    processed_image_source = next((product for product in group if product.processed_image_url), cheapest)
    image_source = next((product for product in group if product.image_url), cheapest)
    specs_source = max(group, key=lambda product: len(_present_specs(product.summary_specs)))
    brand, model = _cpu_brand_model_from_key(key)
    stable_name = _cpu_display_name(key)
    summary_specs = _present_specs(specs_source.summary_specs)
    return cheapest.model_copy(
        update={
            "canonical_key": key,
            "name": stable_name,
            "brand": brand,
            "model": model,
            "processed_image_url": cheapest.processed_image_url or processed_image_source.processed_image_url,
            "image_url": cheapest.image_url or image_source.image_url,
            "summary_specs": summary_specs,
            "flags": list(dict.fromkeys([*cheapest.flags, "cpu_product_first_view"])),
        }
    )


def _cpu_canonical_key(product: ProductSearchResult) -> str | None:
    for value in (product.canonical_key, product.model, product.name):
        if not value:
            continue
        key = cpu_model_key_from_title(value)
        if key:
            brand = "AMD" if key.startswith("AMD_") else "Intel" if key.startswith("INTEL_") else product.brand or "Unknown"
            model = key.removeprefix(f"{brand.upper()}_")
            return f"CPU|{brand.upper()}|{model}"
    return None


def _cpu_display_name(key: str) -> str:
    brand, model = _cpu_brand_model_from_key(key)
    model_text = model.replace("_", " ").title()
    model_text = model_text.replace("Ryzen ", "Ryzen ").replace("Core I", "Core i")
    model_text = model_text.replace("Ryzen Ai ", "Ryzen AI ")
    model_text = model_text.replace(" Max ", " Max+ ")
    model_text = model_text.replace(" Hx ", " HX ")
    model_text = model_text.replace(" Pro ", " PRO ")
    model_text = model_text.replace("Fx ", "FX ")
    for token in ("X3D", "XT", "X", "K", "F"):
        model_text = model_text.replace(token.title(), token)
    return f"{brand} {model_text}".strip()


def _cpu_brand_model_from_key(key: str) -> tuple[str, str]:
    parts = key.split("|")
    brand = parts[1].title() if len(parts) > 1 else "CPU"
    model = parts[2] if len(parts) > 2 else key
    if brand.upper() == "AMD":
        brand = "AMD"
    elif brand.upper() == "INTEL":
        brand = "Intel"
    return brand, model


def _present_specs(specs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in specs.items() if value is not None and value != ""}


def _cpu_price_sort_value(product: ProductSearchResult) -> tuple[float, str]:
    prices = [
        product.lowest_market_price,
        product.best_local_price,
        product.best_trusted_price,
        product.current_recommended_price,
        product.current_best_price,
    ]
    price = min((value for value in prices if value is not None and value > 0), default=float("inf"))
    return price, product.name.lower()


def _cpu_specs_import_product(row: CpuSpecsImportRow) -> CpuSpecsImportedProduct | None:
    model_key = cpu_model_key_from_title(row.name)
    if not model_key:
        return None
    brand = "AMD" if model_key.startswith("AMD_") else "Intel" if model_key.startswith("INTEL_") else "Unknown"
    model = model_key.removeprefix(f"{brand.upper()}_")
    canonical_key = f"CPU|{brand.upper()}|{model}"
    cores, threads = _parse_cores_threads(row)
    base_clock, boost_clock = _parse_cpu_clock(row)
    summary_specs = _present_specs(
        {
            "socket": _normalize_cpu_socket(row.socket),
            "cores": cores,
            "threads": threads,
            "base_clock_ghz": base_clock,
            "boost_clock_ghz": boost_clock,
            "process_nm": _parse_number(row.process),
            "l3_cache_mb": _parse_number(row.l3_cache),
            "tdp_w": _parse_number(row.tdp),
        }
    )
    return CpuSpecsImportedProduct(
        canonical_key=canonical_key,
        name=_cpu_display_name(canonical_key),
        brand=brand,
        model=model,
        summary_specs=summary_specs,
        image_url=row.image_url,
    )


def _parse_cores_threads(row: CpuSpecsImportRow) -> tuple[int | None, int | None]:
    if row.cores and row.threads:
        return row.cores, row.threads
    text = row.cores_threads or ""
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return row.cores, row.threads


def _parse_cpu_clock(row: CpuSpecsImportRow) -> tuple[float | None, float | None]:
    if row.base_clock_ghz and row.boost_clock_ghz:
        return row.base_clock_ghz, row.boost_clock_ghz
    values = [_parse_number(value) for value in re.findall(r"\d+(?:\.\d+)?", row.clock or "")]
    values = [value for value in values if value is not None]
    if len(values) >= 2:
        return values[0], values[-1]
    if len(values) == 1:
        return row.base_clock_ghz or values[0], row.boost_clock_ghz
    return row.base_clock_ghz, row.boost_clock_ghz


def _parse_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group(0)) if match else None


def _normalize_cpu_socket(value: str | None) -> str | None:
    if not value:
        return None
    text = value.upper().replace("SOCKET", "").strip()
    return re.sub(r"\s+", " ", text)


def _cpu_specs_evidence(product: CpuSpecsImportedProduct) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for field, value in product.summary_specs.items():
        evidence.append(
            {
                "id": f"evidence:{product.canonical_key}:techpowerup:{field}",
                "field": field,
                "value_json": json.dumps(value, sort_keys=True),
            }
        )
    if product.image_url:
        evidence.append(
            {
                "id": f"evidence:{product.canonical_key}:techpowerup:image_url",
                "field": "image_url",
                "value_json": json.dumps(product.image_url, sort_keys=True),
            }
        )
    return evidence


def _intelligence_from_record(data: dict[str, Any]) -> HardwareIntelligence:
    return HardwareIntelligence.model_validate_json(data["payload_json"])


class Neo4jPricingRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT product_canonical_key IF NOT EXISTS "
            "FOR (n:Product) REQUIRE n.canonical_key IS UNIQUE",
            "CREATE CONSTRAINT brand_name IF NOT EXISTS FOR (n:Brand) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT socket_name IF NOT EXISTS FOR (n:Socket) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT memory_type_name IF NOT EXISTS FOR (n:MemoryType) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT chipset_name IF NOT EXISTS FOR (n:Chipset) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT form_factor_name IF NOT EXISTS FOR (n:FormFactor) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT efficiency_rating_name IF NOT EXISTS FOR (n:EfficiencyRating) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT product_family_key IF NOT EXISTS FOR (n:ProductFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE CONSTRAINT catalog_feed_run_id IF NOT EXISTS FOR (n:CatalogFeedRun) REQUIRE n.run_id IS UNIQUE",
            "CREATE CONSTRAINT vendor_id IF NOT EXISTS FOR (n:Vendor) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT price_snapshot_id IF NOT EXISTS "
            "FOR (n:PriceSnapshot) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT pricing_job_id IF NOT EXISTS "
            "FOR (n:PricingJob) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT product_url_normalized IF NOT EXISTS "
            "FOR (n:ProductURL) REQUIRE n.normalized_url IS UNIQUE",
            "CREATE CONSTRAINT hardware_intelligence_id IF NOT EXISTS "
            "FOR (n:HardwareIntelligence) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT gpu_family_key IF NOT EXISTS "
            "FOR (n:GPUFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE CONSTRAINT cpu_family_key IF NOT EXISTS "
            "FOR (n:CPUFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE CONSTRAINT storage_family_key IF NOT EXISTS "
            "FOR (n:StorageFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE CONSTRAINT ram_family_key IF NOT EXISTS "
            "FOR (n:RAMFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE CONSTRAINT psu_family_key IF NOT EXISTS "
            "FOR (n:PSUFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE CONSTRAINT case_family_key IF NOT EXISTS "
            "FOR (n:CaseFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE CONSTRAINT cooler_family_key IF NOT EXISTS "
            "FOR (n:CoolerFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE INDEX product_name IF NOT EXISTS FOR (n:Product) ON (n.name)",
            "CREATE INDEX product_category IF NOT EXISTS FOR (n:Product) ON (n.category)",
            "CREATE INDEX product_current_price_timestamp IF NOT EXISTS "
            "FOR (n:Product) ON (n.current_price_timestamp)",
            "CREATE INDEX price_snapshot_timestamp IF NOT EXISTS "
            "FOR (n:PriceSnapshot) ON (n.timestamp)",
            "CREATE INDEX price_snapshot_vendor IF NOT EXISTS "
            "FOR (n:PriceSnapshot) ON (n.vendor_id)",
            "CREATE INDEX price_snapshot_region IF NOT EXISTS "
            "FOR (n:PriceSnapshot) ON (n.region)",
            "CREATE INDEX product_url_region IF NOT EXISTS "
            "FOR (n:ProductURL) ON (n.region, n.category)",
            "CREATE INDEX hardware_intelligence_generated_at IF NOT EXISTS "
            "FOR (n:HardwareIntelligence) ON (n.generated_at)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def find_product_id(self, identity: ProductIdentity) -> str | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (candidate)
            WHERE (candidate:Product OR candidate:Component)
              AND (
                candidate.canonical_key = $canonical_key
                OR toUpper(candidate.name) = toUpper($name)
              )
            RETURN candidate.id AS id,
                   CASE
                     WHEN candidate.canonical_key = $canonical_key THEN 0
                     WHEN toUpper(candidate.name) = toUpper($name) THEN 1
                   END AS rank
            ORDER BY rank
            LIMIT 1
            """,
            canonical_key=identity.canonical_key,
            name=identity.name,
            database_=settings.neo4j_database,
        )
        return records[0]["id"] if records else None

    def previous_price(
        self,
        product_id_or_key: str,
        vendor_id: str | None = None,
        region: str | None = None,
    ) -> float | None:
        region = normalize_region(region)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)
            WHERE (p.id = $product_id_or_key OR p.canonical_key = $product_id_or_key)
              AND ($vendor_id IS NULL OR snapshot.vendor_id = $vendor_id)
              AND (snapshot.region = $region OR ($region = "US" AND snapshot.region IS NULL))
              AND snapshot.accepted = true
            RETURN snapshot.price AS price
            ORDER BY snapshot.timestamp DESC
            LIMIT 1
            """,
            product_id_or_key=product_id_or_key,
            vendor_id=vendor_id,
            region=region,
            database_=settings.neo4j_database,
        )
        return float(records[0]["price"]) if records else None

    def upsert_offer(self, offer: PriceOffer, accepted: bool = True) -> str:
        target_id = self.find_product_id(offer.product)
        if target_id:
            records, _, _ = self.driver.execute_query(
                """
                MATCH (p {id: $target_id})
                SET p:Product
                SET p += $product_properties
                RETURN p.id AS id
                """,
                target_id=target_id,
                product_properties=_product_properties(offer.product),
                database_=settings.neo4j_database,
            )
            product_id = records[0]["id"]
        else:
            product_id = f"product-{uuid4()}"
            records, _, _ = self.driver.execute_query(
                """
                MERGE (p:Product {canonical_key: $canonical_key})
                ON CREATE SET p.id = $product_id,
                              p.created_at = datetime()
                SET p += $product_properties
                RETURN p.id AS id
                """,
                canonical_key=offer.product.canonical_key,
                product_id=product_id,
                product_properties=_product_properties(offer.product),
                database_=settings.neo4j_database,
            )
            product_id = records[0]["id"]

        snapshot = _clean_properties(
            {
                "id": offer.id,
                "price": offer.price,
                "currency": offer.currency,
                "region": offer.region,
                "country_code": offer.country_code,
                "city": offer.city,
                "raw_price": offer.raw_price,
                "item_price": offer.item_price,
                "item_price_sar": offer.item_price_sar,
                "shipping_cost_sar": offer.shipping_cost_sar,
                "final_landed_price": offer.final_landed_price,
                "final_landed_currency": offer.final_landed_currency,
                "final_landed_price_sar": offer.final_landed_price_sar,
                "vat_included": offer.vat_included,
                "vat_status": offer.vat_status,
                "shipping_status": offer.shipping_status,
                "warranty_status": offer.warranty_status,
                "local_stock_status": offer.local_stock_status,
                "vendor_region_type": offer.vendor_region_type,
                "estimated_vat": offer.estimated_vat,
                "import_fee": offer.import_fee,
                "estimated_delivery_days": offer.estimated_delivery_days,
                "seller_country": offer.seller_country,
                "is_local_stock": offer.is_local_stock,
                "is_imported": offer.is_imported,
                "serves_saudi": offer.serves_saudi,
                "warranty_type": offer.warranty_type,
                "local_warranty": offer.local_warranty,
                "region_rank_score": offer.region_rank_score,
                "recommended_saudi_price_candidate": offer.recommended_saudi_price_candidate,
                "final_landed_price_confidence": offer.final_landed_price_confidence,
                "price_completeness_score": offer.price_completeness_score,
                "trust_tier": offer.trust_tier,
                "delivery_status": offer.shipping_status,
                "local_stock_confidence": offer.local_stock_confidence,
                "warranty_confidence": offer.warranty_confidence,
                "delivery_confidence": offer.delivery_confidence,
                "availability": offer.availability,
                "timestamp": offer.timestamp,
                "shipping_cost": offer.shipping_cost,
                "product_url": offer.product_url,
                "imageUrl": offer.image_url,
                "processed_image_url": offer.processed_image_url,
                "source_product_id": offer.source_product_id,
                "seller": offer.seller,
                "condition": offer.condition,
                "listing_condition": offer.listing_condition,
                "seller_type": offer.seller_type,
                "marketplace_risk_score": offer.marketplace_risk_score,
                "rating": offer.rating,
                "source": offer.source.source,
                "source_type": offer.source.source_type.value,
                "source_tier": int(offer.source.tier),
                "trust_score": offer.source.trust_score,
                "freshness_score": offer.source.freshness_score,
                "source_url": offer.source.source_url,
                "vendor_id": offer.vendor.id,
                "accepted": accepted,
                "stale": False,
                "flags": offer.flags,
            }
        )
        vendor = _clean_properties(
            {
                "id": offer.vendor.id,
                "name": offer.vendor.name,
                "region": offer.vendor.region,
                "country_code": offer.country_code,
                "vendor_region_type": vendor_region_type(offer.vendor.name, offer.region),
                "trust_tier": offer.trust_tier,
                "serves_saudi": offer.serves_saudi,
                "local_stock_confidence": offer.local_stock_confidence,
                "warranty_confidence": offer.warranty_confidence,
                "delivery_confidence": offer.delivery_confidence,
                "serves_regions": [offer.region],
                "local_regions": [offer.region] if offer.is_local_stock else [],
                "apiType": offer.vendor.api_type.value,
                "trust_score": offer.vendor.trust_score,
                "updated_at": datetime.now(UTC),
            }
        )
        evidence = [_evidence_payload(item) for item in offer.field_evidence]
        self.driver.execute_query(
            """
            MATCH (p {id: $product_id})
            MERGE (vendor:Vendor {id: $vendor.id})
            SET vendor += $vendor
            MERGE (p)-[:SOLD_BY]->(vendor)
            SET p.supported_regions = CASE
                  WHEN $region IN coalesce(p.supported_regions, []) THEN p.supported_regions
                  ELSE coalesce(p.supported_regions, []) + $region
                END,
                p.region_availability = CASE
                  WHEN $region IN coalesce(p.region_availability, []) THEN p.region_availability
                  ELSE coalesce(p.region_availability, []) + $region
                END
            CREATE (snapshot:PriceSnapshot)
            SET snapshot += $snapshot
            MERGE (p)-[:HAS_PRICE]->(snapshot)
            MERGE (snapshot)-[:FROM_VENDOR]->(vendor)
            WITH p, snapshot
            UNWIND $evidence AS evidence
            CREATE (field:FieldEvidence)
            SET field += evidence,
                field.id = randomUUID()
            MERGE (p)-[:HAS_FIELD_EVIDENCE]->(field)
            WITH DISTINCT p
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(candidate:PriceSnapshot)
            WHERE candidate.accepted = true
              AND (candidate.region = $region OR ($region = "US" AND candidate.region IS NULL))
              AND candidate.availability IN ["in_stock", "preorder", "backorder"]
            OPTIONAL MATCH (candidate)-[:FROM_VENDOR]->(candidateVendor:Vendor)
            WITH p, candidate, candidateVendor,
                 coalesce(candidate.listing_condition, candidate.condition, "unknown") AS listingCondition,
                 coalesce(candidate.seller_type,
                   CASE
                     WHEN toLower(coalesce(candidateVendor.name, "")) CONTAINS "swappa"
                       OR toLower(coalesce(candidateVendor.name, "")) CONTAINS "ebay"
                       OR toLower(coalesce(candidate.source, "")) CONTAINS "ebay"
                       THEN "marketplace"
                     WHEN coalesce(candidateVendor.name, "") CONTAINS " - " THEN "third_party"
                     WHEN toLower(coalesce(candidateVendor.name, "")) CONTAINS "bestbuy"
                       OR toLower(coalesce(candidateVendor.name, "")) CONTAINS "best buy"
                       OR toLower(coalesce(candidateVendor.name, "")) CONTAINS "amazon"
                       OR toLower(coalesce(candidateVendor.name, "")) CONTAINS "micro center"
                       OR toLower(coalesce(candidateVendor.name, "")) CONTAINS "newegg"
                       THEN "retailer"
                     ELSE "unknown"
                   END
                 ) AS sellerType,
                 coalesce(candidate.marketplace_risk_score,
                   CASE
                     WHEN toLower(coalesce(candidateVendor.name, "")) CONTAINS "swappa"
                       OR toLower(coalesce(candidateVendor.name, "")) CONTAINS "ebay"
                       THEN 0.84
                     WHEN coalesce(candidateVendor.name, "") CONTAINS " - " THEN 0.74
                     WHEN toLower(coalesce(candidateVendor.name, "")) CONTAINS "bestbuy"
                       OR toLower(coalesce(candidateVendor.name, "")) CONTAINS "best buy"
                       OR toLower(coalesce(candidateVendor.name, "")) CONTAINS "amazon"
                       THEN 0.24
                     ELSE 0.5
                   END
                 ) AS risk,
                 coalesce(candidate.flags, []) AS flags
            WITH p, candidate, candidateVendor, listingCondition, sellerType, risk, flags,
                 CASE
                   WHEN candidate IS NULL THEN 1
                   WHEN "price_requires_review" IN flags THEN 1
                   WHEN listingCondition = "unknown" THEN 1
                   WHEN risk >= 0.65 THEN 1
                   WHEN listingCondition = "unknown" AND sellerType IN ["marketplace", "third_party"] THEN 1
                   ELSE 0
                 END AS reviewRank
            ORDER BY
              reviewRank,
              CASE listingCondition WHEN "new" THEN 0 WHEN "unknown" THEN 1 ELSE 2 END,
              CASE WHEN sellerType IN ["retailer", "manufacturer"] THEN 0 WHEN sellerType = "unknown" THEN 1 ELSE 2 END,
              risk,
              CASE coalesce(candidate.final_landed_currency, candidate.currency) WHEN $region_currency THEN 0 ELSE 1 END,
              candidate.source_tier,
              candidate.trust_score DESC,
              candidate.freshness_score DESC,
              coalesce(candidate.final_landed_price, candidate.price + coalesce(candidate.shipping_cost, 0))
            WITH p, [item IN collect({
              snapshot: candidate,
              vendor: candidateVendor,
              reviewRank: reviewRank
            }) WHERE item.snapshot IS NOT NULL AND item.reviewRank = 0][0] AS best
            SET p.current_best_price = CASE WHEN best IS NULL THEN null ELSE coalesce(best.snapshot.final_landed_price, best.snapshot.price) END,
                p.current_best_currency = CASE WHEN best IS NULL THEN null ELSE coalesce(best.snapshot.final_landed_currency, best.snapshot.currency) END,
                p.current_best_vendor = CASE WHEN best IS NULL THEN null ELSE best.vendor.name END,
                p.current_price_timestamp = CASE WHEN best IS NULL THEN null ELSE best.snapshot.timestamp END,
                p.current_price_freshness_score = CASE WHEN best IS NULL THEN null ELSE best.snapshot.freshness_score END,
                p.current_price_trust_score = CASE WHEN best IS NULL THEN null ELSE best.snapshot.trust_score END,
                p.current_price_source = CASE WHEN best IS NULL THEN null ELSE best.snapshot.source END,
                p.stale = false,
                p.price_usd = CASE
                  WHEN $region = "US" AND best IS NOT NULL AND coalesce(best.snapshot.final_landed_currency, best.snapshot.currency) = "USD"
                    THEN coalesce(best.snapshot.final_landed_price, best.snapshot.price)
                  ELSE p.price_usd
                END
            """,
            product_id=product_id,
            vendor=vendor,
            snapshot=snapshot,
            evidence=evidence,
            region=offer.region,
            region_currency=get_region_config(offer.region).currency,
            database_=settings.neo4j_database,
        )
        self._upsert_gpu_family_link(product_id, offer.product.specs)
        self._apply_catalog_shape(
            product_id=product_id,
            category=offer.product.category,
            brand=offer.product.brand,
            specs=offer.product.specs,
        )
        self._upsert_cpu_family_link(product_id, offer.product.specs)
        self._upsert_storage_family_link(product_id, offer.product.specs)
        self._upsert_ram_family_link(product_id, offer.product.specs)
        self._upsert_psu_family_link(product_id, offer.product.specs)
        self._upsert_case_family_link(product_id, offer.product.specs)
        self._upsert_cooler_family_link(product_id, offer.product.specs)
        return product_id

    def upsert_product_url(
        self,
        *,
        normalized_url: str,
        url: str,
        source_name: str,
        vendor_name: str,
        region: str,
        category: str,
        product_id: str,
        vendor_id: str,
        approved: bool,
        refresh_allowed: bool,
        source_policy_status: str,
        last_price: float | None = None,
        last_currency: str | None = None,
    ) -> None:
        self.driver.execute_query(
            """
            MATCH (product:Product {id: $product_id})
            MATCH (vendor:Vendor {id: $vendor_id})
            MERGE (url:ProductURL {normalized_url: $normalized_url})
            ON CREATE SET url.created_at = datetime()
            SET url.url = $url,
                url.source_name = $source_name,
                url.vendor_name = $vendor_name,
                url.region = $region,
                url.category = $category,
                url.approved = $approved,
                url.refresh_allowed = $refresh_allowed,
                url.last_checked_at = datetime(),
                url.last_success_at = datetime(),
                url.last_failure_at = null,
                url.last_error_sanitized = null,
                url.source_policy_status = $source_policy_status,
                url.last_price = $last_price,
                url.last_currency = $last_currency,
                url.last_price_hash = $last_price_hash,
                url.refresh_failure_count = 0,
                url.refresh_priority = coalesce(url.refresh_priority, $refresh_priority),
                url.next_refresh_at = datetime() + duration({hours: 12}),
                url.updated_at = datetime()
            MERGE (url)-[:FOR_PRODUCT]->(product)
            MERGE (url)-[:FROM_VENDOR]->(vendor)
            """,
            normalized_url=normalized_url,
            url=url,
            source_name=source_name,
            vendor_name=vendor_name,
            region=region,
            category=category,
            product_id=product_id,
            vendor_id=vendor_id,
            approved=approved,
            refresh_allowed=refresh_allowed,
            source_policy_status=source_policy_status,
            last_price=last_price,
            last_currency=last_currency,
            last_price_hash=f"{last_currency}:{float(last_price):.2f}" if last_price is not None else None,
            refresh_priority=_refresh_priority_for_category(category),
            database_=settings.neo4j_database,
        )

    def known_product_urls(
        self,
        *,
        region: str = "SA",
        category: str | None = None,
        vendor: str | None = None,
        limit: int = 20,
        due_only: bool = False,
    ) -> list[dict[str, Any]]:
        region = normalize_region(region)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (url:ProductURL)
            WHERE url.approved = true
              AND url.refresh_allowed = true
              AND url.region = $region
              AND (
                $due_only = false
                OR coalesce(url.next_refresh_at, datetime("1970-01-01T00:00:00Z")) <= datetime()
              )
              AND ($category IS NULL OR url.category = $category)
              AND ($vendor IS NULL OR toLower(url.vendor_name) CONTAINS toLower($vendor))
            RETURN url.url AS url,
                   url.normalized_url AS normalized_url,
                   url.source_name AS source_name,
                   url.vendor_name AS vendor_name,
                   url.region AS region,
                   url.category AS category,
                   coalesce(url.approved, false) AS approved,
                   coalesce(url.refresh_allowed, false) AS refresh_allowed,
                   url.last_checked_at AS last_checked_at,
                   url.last_success_at AS last_success_at,
                   url.last_failure_at AS last_failure_at,
                   url.last_error_sanitized AS last_error_sanitized,
                   coalesce(url.source_policy_status, "allowed") AS source_policy_status,
                   url.last_price AS last_price,
                   url.last_currency AS last_currency,
                   url.next_refresh_at AS next_refresh_at,
                   coalesce(url.refresh_priority, 50) AS refresh_priority,
                   coalesce(url.refresh_failure_count, 0) AS refresh_failure_count,
                   url.last_price_hash AS last_price_hash
            ORDER BY coalesce(url.refresh_priority, 50) DESC,
                     coalesce(url.last_checked_at, datetime("1970-01-01T00:00:00Z")) ASC
            LIMIT $limit
            """,
            region=region,
            category=category,
            vendor=vendor,
            limit=limit,
            due_only=due_only,
            database_=settings.neo4j_database,
        )
        return [record.data() for record in records]

    def update_product_url_refresh_status(self, *, normalized_url: str, success: bool, error: str | None = None) -> None:
        self.driver.execute_query(
            """
            MERGE (url:ProductURL {normalized_url: $normalized_url})
            SET url.last_checked_at = datetime(),
                url.last_success_at = CASE WHEN $success THEN datetime() ELSE url.last_success_at END,
                url.last_failure_at = CASE WHEN $success THEN url.last_failure_at ELSE datetime() END,
                url.last_error_sanitized = CASE WHEN $success THEN null ELSE $error END,
                url.refresh_failure_count = CASE
                    WHEN $success THEN 0
                    ELSE coalesce(url.refresh_failure_count, 0) + 1
                END,
                url.next_refresh_at = CASE
                    WHEN $success THEN datetime() + duration({hours: 12})
                    WHEN coalesce(url.refresh_failure_count, 0) >= 3 THEN datetime() + duration({hours: 24})
                    WHEN coalesce(url.refresh_failure_count, 0) = 2 THEN datetime() + duration({hours: 18})
                    WHEN coalesce(url.refresh_failure_count, 0) = 1 THEN datetime() + duration({hours: 12})
                    ELSE datetime() + duration({hours: 6})
                END,
                url.updated_at = datetime()
            """,
            normalized_url=normalized_url,
            success=success,
            error=error,
            database_=settings.neo4j_database,
        )

    def link_product_url_audit(self, *, normalized_url: str, audit_id: str) -> None:
        self.driver.execute_query(
            """
            MATCH (url:ProductURL {normalized_url: $normalized_url})
            MATCH (event:AuditEvent {id: $audit_id})
            MERGE (url)-[:AUDITED_BY]->(event)
            """,
            normalized_url=normalized_url,
            audit_id=audit_id,
            database_=settings.neo4j_database,
        )

    def _upsert_gpu_family_link(self, product_id: str, specs: dict[str, Any]) -> None:
        family_key = specs.get("gpu_family_key")
        if not family_key:
            return
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (family:GPUFamily {family_key: $family_key})
            SET family.name = $family_name,
                family.chipset = $chipset,
                family.updated_at = datetime()
            MERGE (p)-[:VARIANT_OF]->(family)
            """,
            product_id=product_id,
            family_key=family_key,
            family_name=specs.get("gpu_family_name") or family_key,
            chipset=specs.get("chipset"),
            database_=settings.neo4j_database,
        )

    def _apply_catalog_shape(
        self,
        *,
        product_id: str,
        category: str,
        brand: str | None,
        specs: dict[str, Any],
    ) -> None:
        label = _category_label(category)
        self.driver.execute_query(
            f"""
            MATCH (p:Product {{id: $product_id}})
            SET p:{label}
            WITH p
            CALL {{
              WITH p
              WITH p WHERE $brand IS NOT NULL
              MERGE (brand:Brand {{name: $brand}})
              SET brand.normalized_name = toUpper($brand),
                  brand.updated_at = datetime()
              MERGE (p)-[:MADE_BY]->(brand)
              RETURN count(*) AS brand_count
            }}
            WITH p
            CALL {{
              WITH p
              WITH p WHERE $cpu_socket IS NOT NULL
              MERGE (socket:Socket {{name: $cpu_socket}})
              SET socket.normalized_name = $cpu_socket,
                  socket.updated_at = datetime()
              MERGE (p)-[:REQUIRES_SOCKET]->(socket)
              RETURN count(*) AS cpu_socket_count
            }}
            WITH p
            CALL {{
              WITH p
              WITH p WHERE $board_socket IS NOT NULL
              MERGE (socket:Socket {{name: $board_socket}})
              SET socket.normalized_name = $board_socket,
                  socket.updated_at = datetime()
              MERGE (p)-[:HAS_SOCKET]->(socket)
              RETURN count(*) AS board_socket_count
            }}
            WITH p
            CALL {{
              WITH p
              WITH p WHERE $memory_type IS NOT NULL
              MERGE (memory:MemoryType {{name: $memory_type}})
              SET memory.normalized_name = $memory_type,
                  memory.updated_at = datetime()
              MERGE (p)-[:SUPPORTS_MEMORY]->(memory)
              RETURN count(*) AS memory_count
            }}
            WITH p
            CALL {{
              WITH p
              WITH p WHERE $chipset IS NOT NULL
              MERGE (chipset:Chipset {{name: $chipset}})
              SET chipset.normalized_name = $chipset,
                  chipset.updated_at = datetime()
              MERGE (p)-[:HAS_CHIPSET]->(chipset)
              RETURN count(*) AS chipset_count
            }}
            WITH p
            CALL {{
              WITH p
              UNWIND $form_factors AS factor
              WITH p, factor WHERE factor IS NOT NULL AND factor <> ""
              MERGE (form:FormFactor {{name: factor}})
              SET form.normalized_name = factor,
                  form.updated_at = datetime()
              MERGE (p)-[:SUPPORTS_FORM_FACTOR]->(form)
              RETURN count(*) AS form_count
            }}
            WITH p
            CALL {{
              WITH p
              WITH p WHERE $efficiency_rating IS NOT NULL
              MERGE (eff:EfficiencyRating {{name: $efficiency_rating}})
              SET eff.normalized_name = $efficiency_rating,
                  eff.updated_at = datetime()
              MERGE (p)-[:HAS_EFFICIENCY_RATING]->(eff)
              RETURN count(*) AS efficiency_count
            }}
            RETURN p.id AS id
            """,
            product_id=product_id,
            brand=brand,
            cpu_socket=specs.get("socket") if category == "CPU" else None,
            board_socket=specs.get("socket") if category == "Motherboard" else None,
            memory_type=specs.get("memory_type"),
            chipset=specs.get("chipset"),
            form_factors=_form_factors_for_category(category, specs),
            efficiency_rating=specs.get("efficiency_rating"),
            database_=settings.neo4j_database,
        )

    def _upsert_cpu_family_link(self, product_id: str, specs: dict[str, Any]) -> None:
        family_key = specs.get("cpu_family_key") or specs.get("cpu_model_key")
        if not family_key:
            return
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (family:CPUFamily {family_key: $family_key})
            SET family.name = $family_name,
                family.socket = $socket,
                family.updated_at = datetime()
            MERGE (p)-[:VARIANT_OF]->(family)
            """,
            product_id=product_id,
            family_key=family_key,
            family_name=specs.get("cpu_family_name") or str(family_key).replace("_", " "),
            socket=specs.get("socket"),
            database_=settings.neo4j_database,
        )

    def _upsert_storage_family_link(self, product_id: str, specs: dict[str, Any]) -> None:
        family_key = specs.get("storage_family_key") or specs.get("storage_model_key")
        if not family_key:
            return
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (family:StorageFamily {family_key: $family_key})
            SET family.name = $family_name,
                family.capacity_gb = $capacity_gb,
                family.interface = $interface,
                family.form_factor = $form_factor,
                family.updated_at = datetime()
            MERGE (p)-[:VARIANT_OF]->(family)
            """,
            product_id=product_id,
            family_key=family_key,
            family_name=specs.get("storage_family_name") or str(family_key).replace("_", " "),
            capacity_gb=specs.get("capacity_gb"),
            interface=specs.get("interface"),
            form_factor=specs.get("form_factor"),
            database_=settings.neo4j_database,
        )

    def _upsert_ram_family_link(self, product_id: str, specs: dict[str, Any]) -> None:
        family_key = specs.get("ram_family_key")
        if not family_key:
            return
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (family:RAMFamily {family_key: $family_key})
            SET family.name = $family_name,
                family.memory_type = $memory_type,
                family.capacity_gb = $capacity_gb,
                family.speed_mhz = $speed_mhz,
                family.updated_at = datetime()
            MERGE (p)-[:VARIANT_OF]->(family)
            """,
            product_id=product_id,
            family_key=family_key,
            family_name=specs.get("ram_family_name") or str(family_key).replace("_", " "),
            memory_type=specs.get("memory_type"),
            capacity_gb=specs.get("capacity_gb"),
            speed_mhz=specs.get("speed_mhz") or specs.get("speed_mt_s"),
            database_=settings.neo4j_database,
        )

    def _upsert_psu_family_link(self, product_id: str, specs: dict[str, Any]) -> None:
        family_key = specs.get("psu_family_key")
        if not family_key:
            return
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (family:PSUFamily {family_key: $family_key})
            SET family.name = $family_name,
                family.wattage_w = $wattage_w,
                family.efficiency_rating = $efficiency_rating,
                family.modularity = $modularity,
                family.pcie_5_support = $pcie_5_support,
                family.updated_at = datetime()
            MERGE (p)-[:VARIANT_OF]->(family)
            """,
            product_id=product_id,
            family_key=family_key,
            family_name=specs.get("psu_family_name") or str(family_key).replace("_", " "),
            wattage_w=specs.get("wattage_w") or specs.get("wattage"),
            efficiency_rating=specs.get("efficiency_rating"),
            modularity=specs.get("modularity"),
            pcie_5_support=specs.get("pcie_5_support"),
            database_=settings.neo4j_database,
        )

    def _upsert_case_family_link(self, product_id: str, specs: dict[str, Any]) -> None:
        family_key = specs.get("case_family_key")
        if not family_key:
            return
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (family:CaseFamily {family_key: $family_key})
            SET family.name = $family_name,
                family.supported_motherboard_form_factors = $supported_motherboard_form_factors,
                family.case_type = $case_type,
                family.max_gpu_length_mm = $max_gpu_length_mm,
                family.max_cpu_cooler_height_mm = $max_cpu_cooler_height_mm,
                family.radiator_support_top_mm = $radiator_support_top_mm,
                family.radiator_support_front_mm = $radiator_support_front_mm,
                family.updated_at = datetime()
            MERGE (p)-[:VARIANT_OF]->(family)
            """,
            product_id=product_id,
            family_key=family_key,
            family_name=specs.get("case_family_name") or str(family_key).replace("_", " "),
            supported_motherboard_form_factors=specs.get("supported_motherboard_form_factors"),
            case_type=specs.get("case_type"),
            max_gpu_length_mm=specs.get("max_gpu_length_mm"),
            max_cpu_cooler_height_mm=specs.get("max_cpu_cooler_height_mm"),
            radiator_support_top_mm=specs.get("radiator_support_top_mm"),
            radiator_support_front_mm=specs.get("radiator_support_front_mm"),
            database_=settings.neo4j_database,
        )

    def _upsert_cooler_family_link(self, product_id: str, specs: dict[str, Any]) -> None:
        family_key = specs.get("cooler_family_key")
        if not family_key:
            return
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (family:CoolerFamily {family_key: $family_key})
            SET family.name = $family_name,
                family.cooler_type = $cooler_type,
                family.supported_sockets = $supported_sockets,
                family.radiator_size_mm = $radiator_size_mm,
                family.radiator_fan_count = $radiator_fan_count,
                family.fan_size_mm = $fan_size_mm,
                family.cooler_height_mm = $cooler_height_mm,
                family.tdp_rating_w = $tdp_rating_w,
                family.updated_at = datetime()
            MERGE (p)-[:VARIANT_OF]->(family)
            """,
            product_id=product_id,
            family_key=family_key,
            family_name=specs.get("cooler_family_name") or str(family_key).replace("_", " "),
            cooler_type=specs.get("cooler_type"),
            supported_sockets=specs.get("supported_sockets"),
            radiator_size_mm=specs.get("radiator_size_mm"),
            radiator_fan_count=specs.get("radiator_fan_count"),
            fan_size_mm=specs.get("fan_size_mm"),
            cooler_height_mm=specs.get("cooler_height_mm") or specs.get("height_mm"),
            tdp_rating_w=specs.get("tdp_rating_w") or specs.get("cooling_capacity_w"),
            database_=settings.neo4j_database,
        )

    def mark_product_stale(self, product_id: str, reason: str) -> None:
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            SET p.stale = true,
                p.stale_reason = $reason,
                p.stale_at = datetime()
            """,
            product_id=product_id,
            reason=reason,
            database_=settings.neo4j_database,
        )

    def update_product_image_url(
        self,
        product_id: str,
        *,
        image_url: str,
        source_name: str | None = None,
        note: str | None = None,
    ) -> bool:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND (p:Product OR p:Component)
            SET p.imageUrl = $image_url,
                p.image_url = $image_url,
                p.image_source_name = $source_name,
                p.image_note = $note,
                p.image_updated_at = datetime()
            RETURN p.id AS id
            LIMIT 1
            """,
            product_id=product_id,
            image_url=image_url,
            source_name=source_name,
            note=note,
            database_=settings.neo4j_database,
        )
        return bool(records)

    def import_cpu_specs(
        self,
        *,
        rows: list[CpuSpecsImportRow],
        source_name: str = "TechPowerUp CPU Database",
        dry_run: bool = False,
    ) -> CpuSpecsImportResponse:
        products: list[CpuSpecsImportedProduct] = []
        skipped: list[str] = []
        for row in rows:
            normalized = _cpu_specs_import_product(row)
            if not normalized:
                skipped.append(row.name)
                continue
            products.append(normalized)
            if dry_run:
                continue
            self.driver.execute_query(
                """
                MERGE (p:Product {canonical_key: $canonical_key})
                ON CREATE SET p.id = $product_id,
                              p.created_at = datetime()
                SET p:CPU,
                    p.name = $name,
                    p.brand = $brand,
                    p.category = "CPU",
                    p.model = $model,
                    p.normalized_model = $model,
                    p.data_origin = "live",
                    p.spec_source_name = $source_name,
                    p.spec_source_type = "cpu_specs_database",
                    p.spec_updated_at = datetime(),
                    p.spec_socket = $socket,
                    p.spec_cores = $cores,
                    p.spec_core_count = $cores,
                    p.spec_threads = $threads,
                    p.spec_thread_count = $threads,
                    p.spec_base_clock_ghz = $base_clock_ghz,
                    p.spec_boost_clock_ghz = $boost_clock_ghz,
                    p.spec_process_nm = $process_nm,
                    p.spec_l3_cache_mb = $l3_cache_mb,
                    p.spec_tdp_w = $tdp_w,
                    p.imageUrl = coalesce(p.imageUrl, $image_url),
                    p.image_url = coalesce(p.image_url, $image_url),
                    p.updated_at = datetime()
                WITH p
                MERGE (brand:Brand {name: $brand})
                SET brand.normalized_name = $brand_key,
                    brand.updated_at = datetime()
                MERGE (p)-[:MADE_BY]->(brand)
                WITH p
                CALL {
                    WITH p
                    WITH p WHERE $socket IS NOT NULL
                    MERGE (socket:Socket {name: $socket})
                    SET socket.normalized_name = $socket,
                        socket.updated_at = datetime()
                    MERGE (p)-[:REQUIRES_SOCKET]->(socket)
                    RETURN count(*) AS socket_relationship_count
                }
                WITH p
                UNWIND $evidence AS evidence
                MERGE (field:FieldEvidence {id: evidence.id})
                SET field.field = evidence.field,
                    field.value_json = evidence.value_json,
                    field.source = $source_name,
                    field.timestamp = datetime(),
                    field.trust_score = 0.82,
                    field.freshness_score = 0.7,
                    field.source_tier = 1
                MERGE (p)-[:HAS_FIELD_EVIDENCE]->(field)
                RETURN p.id AS id
                """,
                canonical_key=normalized.canonical_key,
                product_id=f"cpu-spec:{normalized.canonical_key}",
                name=normalized.name,
                brand=normalized.brand,
                brand_key=normalized.brand.upper(),
                model=normalized.model,
                source_name=source_name,
                socket=normalized.summary_specs.get("socket"),
                cores=normalized.summary_specs.get("cores"),
                threads=normalized.summary_specs.get("threads"),
                base_clock_ghz=normalized.summary_specs.get("base_clock_ghz"),
                boost_clock_ghz=normalized.summary_specs.get("boost_clock_ghz"),
                process_nm=normalized.summary_specs.get("process_nm"),
                l3_cache_mb=normalized.summary_specs.get("l3_cache_mb"),
                tdp_w=normalized.summary_specs.get("tdp_w"),
                image_url=normalized.image_url,
                evidence=_cpu_specs_evidence(normalized),
                database_=settings.neo4j_database,
            )
        return CpuSpecsImportResponse(
            imported_count=len(products),
            skipped_count=len(skipped),
            products=products,
            skipped_rows=skipped,
            dry_run=dry_run,
        )

    def import_catalog_feed(
        self,
        *,
        rows: list[CatalogFeedImportRow],
        source_name: str,
        category: str,
        region: str = "SA",
        dry_run: bool = True,
    ) -> CatalogFeedImportResponse:
        region = normalize_region(region)
        run_id = f"feed-{uuid4()}"
        imported = 0
        updated = 0
        skipped = 0
        failed = 0
        sanitized_error: str | None = None
        if dry_run:
            return CatalogFeedImportResponse(
                run_id=run_id,
                source_name=source_name,
                category=category,
                region=region,
                dry_run=True,
                status="dry_run",
                imported_count=len(rows),
                updated_count=0,
                skipped_count=0,
                failed_count=0,
            )

        self._record_catalog_feed_run(
            run_id=run_id,
            source_name=source_name,
            category=category,
            region=region,
            dry_run=False,
            status="running",
            imported=0,
            updated=0,
            skipped=0,
            failed=0,
            sanitized_error=None,
            finished=False,
        )
        for row in rows:
            try:
                row_category = row.category or category
                canonical_key = row.canonical_key or _catalog_canonical_key(
                    row_category,
                    row.name,
                    row.brand,
                    row.model,
                )
                props = _catalog_product_properties(row, row_category, source_name)
                label = _category_label(row_category)
                records, _, _ = self.driver.execute_query(
                    f"""
                    MERGE (p:Product {{canonical_key: $canonical_key}})
                    ON CREATE SET p.id = $product_id,
                                  p.created_at = datetime(),
                                  p._catalog_feed_created = true
                    ON MATCH SET p._catalog_feed_created = false
                    SET p:{label},
                        p += $properties,
                        p.updated_at = datetime()
                    WITH p, coalesce(p._catalog_feed_created, false) AS created
                    REMOVE p._catalog_feed_created
                    RETURN p.id AS id, created
                    """,
                    canonical_key=canonical_key,
                    product_id=f"catalog:{canonical_key}",
                    properties=props,
                    database_=settings.neo4j_database,
                )
                product_id = str(records[0]["id"])
                if records[0]["created"]:
                    imported += 1
                else:
                    updated += 1
                self._apply_catalog_shape(
                    product_id=product_id,
                    category=row_category,
                    brand=row.brand or _brand_from_name(row.name),
                    specs=row.specs,
                )
                self._upsert_product_family(product_id, row_category, row.specs, canonical_key)
            except Exception as error:  # noqa: BLE001 - one bad row should not stop the feed.
                failed += 1
                sanitized_error = type(error).__name__
        status = "completed" if failed == 0 else "completed_with_errors"
        self._record_catalog_feed_run(
            run_id=run_id,
            source_name=source_name,
            category=category,
            region=region,
            dry_run=False,
            status=status,
            imported=imported,
            updated=updated,
            skipped=skipped,
            failed=failed,
            sanitized_error=sanitized_error,
            finished=True,
        )
        return CatalogFeedImportResponse(
            run_id=run_id,
            source_name=source_name,
            category=category,
            region=region,
            dry_run=False,
            status=status,
            imported_count=imported,
            updated_count=updated,
            skipped_count=skipped,
            failed_count=failed,
            sanitized_error=sanitized_error,
        )

    def catalog_feed_runs(self, *, limit: int = 50) -> list[CatalogFeedRunView]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (run:CatalogFeedRun)
            RETURN run.run_id AS run_id,
                   run.source_name AS source_name,
                   run.category AS category,
                   run.region AS region,
                   run.status AS status,
                   coalesce(run.imported_count, 0) AS imported_count,
                   coalesce(run.updated_count, 0) AS updated_count,
                   coalesce(run.skipped_count, 0) AS skipped_count,
                   coalesce(run.failed_count, 0) AS failed_count,
                   coalesce(run.dry_run, false) AS dry_run,
                   run.started_at AS started_at,
                   run.finished_at AS finished_at,
                   run.sanitized_error AS sanitized_error
            ORDER BY coalesce(run.finished_at, run.started_at, datetime("1970-01-01T00:00:00Z")) DESC
            LIMIT $limit
            """,
            limit=limit,
            database_=settings.neo4j_database,
        )
        runs: list[CatalogFeedRunView] = []
        for record in records:
            data = record.data()
            data["started_at"] = _to_datetime(data.get("started_at")) if data.get("started_at") else None
            data["finished_at"] = _to_datetime(data.get("finished_at")) if data.get("finished_at") else None
            runs.append(CatalogFeedRunView(**data))
        return runs

    def _record_catalog_feed_run(
        self,
        *,
        run_id: str,
        source_name: str,
        category: str,
        region: str,
        dry_run: bool,
        status: str,
        imported: int,
        updated: int,
        skipped: int,
        failed: int,
        sanitized_error: str | None,
        finished: bool,
    ) -> None:
        self.driver.execute_query(
            """
            MERGE (run:CatalogFeedRun {run_id: $run_id})
            ON CREATE SET run.started_at = datetime()
            SET run.source_name = $source_name,
                run.category = $category,
                run.region = $region,
                run.dry_run = $dry_run,
                run.status = $status,
                run.imported_count = $imported,
                run.updated_count = $updated,
                run.skipped_count = $skipped,
                run.failed_count = $failed,
                run.sanitized_error = $sanitized_error,
                run.finished_at = CASE WHEN $finished THEN datetime() ELSE run.finished_at END
            """,
            run_id=run_id,
            source_name=source_name,
            category=category,
            region=region,
            dry_run=dry_run,
            status=status,
            imported=imported,
            updated=updated,
            skipped=skipped,
            failed=failed,
            sanitized_error=sanitized_error,
            finished=finished,
            database_=settings.neo4j_database,
        )

    def _upsert_product_family(self, product_id: str, category: str, specs: dict[str, Any], canonical_key: str) -> None:
        family_key = specs.get("product_family_key") or specs.get("family_key") or canonical_key
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (family:ProductFamily {family_key: $family_key})
            SET family.name = $family_name,
                family.category = $category,
                family.updated_at = datetime()
            MERGE (p)-[:VARIANT_OF]->(family)
            """,
            product_id=product_id,
            family_key=str(family_key),
            family_name=specs.get("product_family_name") or str(family_key).replace("_", " "),
            category=category,
            database_=settings.neo4j_database,
        )

    def catalog_coverage(self, *, region: str = "SA") -> CatalogCoverageResponse:
        region = normalize_region(region)
        categories = list(ACTIVE_BUILD_CATEGORIES)
        records, _, _ = self.driver.execute_query(
            """
            UNWIND $categories AS category
            OPTIONAL MATCH (p:Product)
            WHERE p.category = category OR category IN labels(p)
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(price:PriceSnapshot)
            WHERE price.region = $region AND price.accepted = true
            WITH category, p, collect(DISTINCT price) AS product_prices
            WITH category,
                 collect({
                   props: CASE WHEN p IS NULL THEN null ELSE properties(p) END,
                   key: CASE WHEN p IS NULL THEN null ELSE coalesce(p.canonical_key, p.id) END,
                   priced: size([price IN product_prices WHERE price IS NOT NULL]) > 0,
                   missing_image: CASE WHEN p IS NULL THEN false ELSE p.processed_image_url IS NULL END
                 }) AS product_rows,
                 sum(size([price IN product_prices WHERE price IS NOT NULL AND coalesce(price.marketplace_risk_score, 0.5) < 0.45])) AS trusted_listing_count,
                 sum(size([price IN product_prices WHERE price IS NOT NULL AND coalesce(price.stale, false) = true])) AS stale_listing_count
            RETURN category,
                   [row IN product_rows WHERE row.props IS NOT NULL | row.props] AS product_properties,
                   size([row IN product_rows WHERE row.props IS NOT NULL]) AS product_count,
                   size([row IN product_rows WHERE row.props IS NOT NULL AND row.priced]) AS priced_product_count,
                   trusted_listing_count,
                   stale_listing_count,
                   size([row IN product_rows WHERE row.props IS NOT NULL AND row.missing_image]) AS missing_processed_image_count,
                   [row IN product_rows WHERE row.key IS NOT NULL | row.key] AS identity_keys
            ORDER BY category
            """,
            categories=categories,
            region=region,
            database_=settings.neo4j_database,
        )
        coverage: list[CatalogCategoryCoverage] = []
        for record in records:
            data = record.data()
            product_count = int(data["product_count"] or 0)
            priced_count = int(data["priced_product_count"] or 0)
            product_properties = list(data.get("product_properties") or [])
            missing_specs = sum(
                1
                for props in product_properties
                if not _catalog_has_required_specs(str(data["category"]), dict(props or {}))
            )
            stale_count = int(data["stale_listing_count"] or 0)
            identity_keys = [str(key) for key in data.get("identity_keys") or [] if key]
            duplicate_risk = len(identity_keys) - len(set(identity_keys))
            readiness = "ready" if priced_count >= 2 and missing_specs == 0 else "usable_with_warnings" if priced_count >= 1 else "not_ready"
            coverage.append(
                CatalogCategoryCoverage(
                    category=str(data["category"]),
                    product_count=product_count,
                    priced_product_count=priced_count,
                    trusted_listing_count=int(data["trusted_listing_count"] or 0),
                    stale_listing_count=stale_count,
                    missing_processed_image_count=int(data["missing_processed_image_count"] or 0),
                    missing_compatibility_spec_count=missing_specs,
                    duplicate_risk_count=max(0, duplicate_risk),
                    readiness_level=readiness,
                    next_best_action=_coverage_next_action(str(data["category"]), priced_count, missing_specs, stale_count),
                )
            )
        return CatalogCoverageResponse(
            region=region,
            category_count=len(coverage),
            product_count=sum(item.product_count for item in coverage),
            priced_product_count=sum(item.priced_product_count for item in coverage),
            stale_listing_count=sum(item.stale_listing_count for item in coverage),
            categories=coverage,
        )

    def search_products(
        self,
        *,
        q: str = "",
        category: str | None = None,
        region: str | None = None,
        limit: int = 25,
        offset: int = 0,
        brand: str | None = None,
        socket: str | None = None,
        chipset: str | None = None,
        memory_type: str | None = None,
        min_price_sar: float | None = None,
        max_price_sar: float | None = None,
        in_stock_priced_only: bool = False,
        sort: str = "recommended",
    ) -> list[ProductSearchResult]:
        region = normalize_region(region)
        candidate_limit = min(max((limit + offset) * 5, 100), 1000)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND ($category IS NULL OR p.category = $category OR $category IN labels(p))
              AND (
                $q = ""
                OR toLower(p.name) CONTAINS toLower($q)
                OR toLower(coalesce(p.brand, "")) CONTAINS toLower($q)
                OR toLower(coalesce(p.model, "")) CONTAINS toLower($q)
              )
              AND ($brand IS NULL OR toLower(coalesce(p.brand, "")) = toLower($brand))
              AND ($socket IS NULL OR toLower(coalesce(p.spec_socket, "")) = toLower($socket))
              AND ($chipset IS NULL OR toLower(coalesce(p.spec_chipset, "")) = toLower($chipset))
              AND ($memory_type IS NULL OR toLower(coalesce(p.spec_memory_type, "")) = toLower($memory_type))
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(s:PriceSnapshot)
            WHERE (s IS NULL OR s.region = $region OR ($region = "US" AND s.region IS NULL))
            WITH p, s
            ORDER BY s.timestamp DESC
            WITH p, collect(s)[0..2] AS latest
            RETURN p.id AS id,
                   p.canonical_key AS canonical_key,
                   p.name AS name,
                   p.brand AS brand,
                   coalesce(p.category, head([label IN labels(p) WHERE label <> "Component" AND label <> "Product"])) AS category,
                   p.model AS model,
                   {
                     socket: p.spec_socket,
                     cores: coalesce(p.spec_cores, p.spec_core_count),
                     threads: coalesce(p.spec_threads, p.spec_thread_count),
                     base_clock_ghz: coalesce(p.spec_base_clock_ghz, p.spec_base_clock),
                     boost_clock_ghz: coalesce(p.spec_boost_clock_ghz, p.spec_boost_clock),
                     process_nm: p.spec_process_nm,
                     l3_cache_mb: p.spec_l3_cache_mb,
                     tdp_w: coalesce(p.spec_tdp_w, p.spec_tdp),
                     chipset: p.spec_chipset,
                     memory_type: p.spec_memory_type,
                     form_factor: p.spec_form_factor,
                     capacity_gb: p.spec_capacity_gb,
                     speed_mhz: coalesce(p.spec_speed_mhz, p.spec_speed_mt_s),
                     speed_mt_s: p.spec_speed_mt_s,
                     interface: p.spec_interface,
                     wattage_w: coalesce(p.spec_wattage_w, p.spec_wattage),
                     efficiency_rating: p.spec_efficiency_rating
                   } AS summary_specs,
                   coalesce(p.imageUrl, p.image_url) AS image_url,
                   p.processed_image_url AS processed_image_url,
                   p.data_origin AS data_origin,
                   coalesce(p.stale, false) AS stale,
                   coalesce(p.best_value, false) AS best_value,
                   latest[1].price AS previous_price
            ORDER BY
              CASE WHEN p.canonical_key IS NULL AND latest[0] IS NULL THEN 1 ELSE 0 END,
              p.name
            LIMIT $candidate_limit
            """,
            q=q,
            category=category,
            region=region,
            brand=brand,
            socket=socket,
            chipset=chipset,
            memory_type=memory_type,
            candidate_limit=candidate_limit,
            database_=settings.neo4j_database,
        )
        products: list[ProductSearchResult] = []
        for record in records:
            data = record.data()
            prices = self.vendor_prices(str(data["id"]), region=region)
            rollups = _price_rollups(prices, region=region)
            products.append(_search_result(_finalize_search_data(data, rollups)))
        if category == "CPU":
            products = _cpu_product_first_results(products)
        products = [
            product
            for product in products
            if _search_product_filter(
                product,
                min_price_sar=min_price_sar,
                max_price_sar=max_price_sar,
                in_stock_priced_only=in_stock_priced_only,
            )
        ]
        return sorted(products, key=lambda product: _search_product_sort_key(product, sort))[offset : offset + limit]

    def product_categories(self) -> list[str]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE p:Product OR p:Component
            WITH collect(DISTINCT p.category) AS storedCategories,
                 collect(DISTINCT head([label IN labels(p) WHERE label <> "Product" AND label <> "Component"])) AS labelCategories
            UNWIND storedCategories + labelCategories AS category
            WITH DISTINCT category
            WHERE category IS NOT NULL
            RETURN category
            ORDER BY category
            """,
            database_=settings.neo4j_database,
        )
        stored = {str(record["category"]) for record in records}
        return sorted(set(GLOBAL_HARDWARE_CATEGORIES) | stored)

    def product_facts(self, product_id: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND (p:Product OR p:Component)
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)
            OPTIONAL MATCH (p)-[:SOLD_BY]->(vendor:Vendor)
            WITH p, collect(DISTINCT snapshot) AS snapshots, count(DISTINCT vendor) AS vendor_count
            RETURN p.id AS id,
                   labels(p) AS labels,
                   properties(p) AS properties,
                   vendor_count AS vendor_count,
                   [snapshot IN snapshots | properties(snapshot)] AS price_snapshots
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        if not records:
            return None
        data = records[0].data()
        properties = dict(data["properties"])
        specs = {
            key.removeprefix("spec_"): value
            for key, value in properties.items()
            if str(key).startswith("spec_")
        }
        power = {
            key.removeprefix("power_"): value
            for key, value in properties.items()
            if str(key).startswith("power_")
        }
        bandwidth = {
            key.removeprefix("bandwidth_"): value
            for key, value in properties.items()
            if str(key).startswith("bandwidth_")
        }
        dimensions = {
            key.removeprefix("dim_"): value
            for key, value in properties.items()
            if str(key).startswith("dim_")
        }
        category = properties.get("category") or next(
            (
                label
                for label in data["labels"]
                if label not in {"Product", "Component"}
            ),
            "Accessories",
        )
        prices = sorted(
            [snapshot for snapshot in data.get("price_snapshots", []) if snapshot],
            key=lambda snapshot: snapshot.get("timestamp") or datetime.fromtimestamp(0, UTC),
        )
        return {
            "id": data["id"],
            "labels": data["labels"],
            "name": properties.get("name", data["id"]),
            "brand": properties.get("brand"),
            "category": category,
            "model": properties.get("model"),
            "price": properties.get("current_best_price") or properties.get("price_usd"),
            "currency": properties.get("current_best_currency") or "USD",
            "vendor_count": int(data.get("vendor_count") or 0),
            "specs": specs,
            "power": power,
            "bandwidth": bandwidth,
            "dimensions": dimensions,
            "raw": properties,
            "price_snapshots": prices,
        }

    def product_merge_facts(self, product_id: str, region: str | None = None) -> dict[str, Any] | None:
        region = normalize_region(region)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND (p:Product OR p:Component)
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)
            WHERE snapshot IS NULL OR snapshot.region = $region OR ($region = "US" AND snapshot.region IS NULL)
            OPTIONAL MATCH (snapshot)-[:FROM_VENDOR]->(vendor:Vendor)
            OPTIONAL MATCH (p)-[:HAS_FIELD_EVIDENCE]->(evidence:FieldEvidence)
            OPTIONAL MATCH (event:AuditEvent)
            WHERE event.target = p.id
            WITH p,
                 collect(DISTINCT snapshot) AS snapshots,
                 collect(DISTINCT vendor.name) AS vendors,
                 count(DISTINCT evidence) AS evidence_count,
                 count(DISTINCT event) AS audit_count
            RETURN p.id AS id,
                   p.canonical_key AS canonical_key,
                   p.name AS name,
                   p.brand AS brand,
                   p.category AS category,
                   p.model AS model,
                   size([snapshot IN snapshots WHERE snapshot IS NOT NULL]) AS price_snapshot_count,
                   [vendor IN vendors WHERE vendor IS NOT NULL] AS vendors,
                   evidence_count AS field_evidence_count,
                   audit_count AS audit_event_count,
                   [snapshot IN snapshots WHERE snapshot IS NOT NULL | {
                     id: snapshot.id,
                     region: snapshot.region,
                     vendor_id: snapshot.vendor_id,
                     price: snapshot.price,
                     currency: snapshot.currency,
                     timestamp: toString(snapshot.timestamp)
                   }] AS prices
            LIMIT 1
            """,
            product_id=product_id,
            region=region,
            database_=settings.neo4j_database,
        )
        return records[0].data() if records else None

    def products_for_enrichment(
        self,
        *,
        category: str | None = None,
        limit: int = 50,
    ) -> list[str]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND p.id IS NOT NULL
              AND ($category IS NULL OR p.category = $category OR $category IN labels(p))
            OPTIONAL MATCH (p)-[:HAS_INTELLIGENCE]->(intel:HardwareIntelligence)
            WITH p, intel
            ORDER BY intel.generated_at ASC
            RETURN p.id AS id
            ORDER BY
              CASE WHEN intel IS NULL THEN 0 ELSE 1 END,
              coalesce(intel.generated_at, datetime("1970-01-01T00:00:00Z")),
              p.name
            LIMIT $limit
            """,
            category=category,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [str(record["id"]) for record in records if record["id"]]

    def upsert_intelligence(self, intelligence: HardwareIntelligence) -> None:
        payload_json = intelligence.model_dump_json()
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            MERGE (intel:HardwareIntelligence {id: $intelligence_id})
            SET intel.product_id = $product_id,
                intel.category = $category,
                intel.confidence = $confidence,
                intel.generated_at = $generated_at,
                intel.payload_json = $payload_json,
                intel.workload_scores_json = $workload_scores_json,
                intel.value_score = $value_score,
                intel.future_proof_score = $future_proof_score,
                intel.thermal_efficiency = $thermal_efficiency
            MERGE (p)-[:HAS_INTELLIGENCE]->(intel)
            SET p.intelligence_value_score = $value_score,
                p.intelligence_future_proof_score = $future_proof_score,
                p.intelligence_confidence = $confidence,
                p.best_value = $best_value_badge
            """,
            product_id=intelligence.product_id,
            intelligence_id=f"intel:{intelligence.product_id}",
            category=intelligence.category,
            confidence=intelligence.confidence,
            generated_at=intelligence.generated_at,
            payload_json=payload_json,
            workload_scores_json=json.dumps(
                {item.workload: item.score for item in intelligence.workloads},
                sort_keys=True,
                default=_json_default,
            ),
            value_score=intelligence.market.value_score,
            future_proof_score=intelligence.longevity.future_proof_score,
            thermal_efficiency=intelligence.power_thermal.thermal_efficiency,
            best_value_badge=intelligence.market.best_value_badge,
            database_=settings.neo4j_database,
        )

    def latest_intelligence(self, product_id: str) -> HardwareIntelligence | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_INTELLIGENCE]->(intel:HardwareIntelligence)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN intel.payload_json AS payload_json
            ORDER BY intel.generated_at DESC
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return _intelligence_from_record(records[0].data()) if records else None

    def product_detail(self, product_id: str, region: str | None = None) -> ProductDetail | None:
        region = normalize_region(region)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            OPTIONAL MATCH (p)-[:HAS_PRICE]->(s:PriceSnapshot)
            WHERE (s IS NULL OR s.region = $region OR ($region = "US" AND s.region IS NULL))
            WITH p, s
            ORDER BY s.timestamp DESC
            WITH p, collect(s)[0..2] AS latest
            OPTIONAL MATCH (p)-[:HAS_FIELD_EVIDENCE]->(e:FieldEvidence)
            RETURN p.id AS id,
                   p.canonical_key AS canonical_key,
                   p.name AS name,
                   p.brand AS brand,
                   coalesce(p.category, head([label IN labels(p) WHERE label <> "Component" AND label <> "Product"])) AS category,
                   p.model AS model,
                   coalesce(p.imageUrl, p.image_url) AS image_url,
                   p.processed_image_url AS processed_image_url,
                   p.data_origin AS data_origin,
                   coalesce(p.stale, false) AS stale,
                   coalesce(p.best_value, false) AS best_value,
                   latest[1].price AS previous_price,
                   properties(p) AS properties,
                   collect(properties(e))[0..30] AS evidence
            LIMIT 1
            """,
            product_id=product_id,
            region=region,
            database_=settings.neo4j_database,
        )
        if not records:
            return None
        prices = self.vendor_prices(product_id, region=region)
        product = _search_result(_finalize_search_data(records[0].data(), _price_rollups(prices, region=region)))
        props = records[0]["properties"] if records else {}
        specs = {
            key.removeprefix("spec_"): value
            for key, value in props.items()
            if str(key).startswith("spec_")
        }
        evidence = []
        for item in records[0]["evidence"] if records else []:
            if not item:
                continue
            evidence.append(
                FieldEvidence(
                    field=item["field"],
                    value=json.loads(item["value_json"]),
                    source=item["source"],
                    timestamp=_to_datetime(item["timestamp"]),
                    trust_score=float(item["trust_score"]),
                    freshness_score=float(item["freshness_score"]),
                    source_tier=SourceTier(int(item["source_tier"])),
                )
            )
        return ProductDetail(
            **product.model_dump(),
            specs=specs,
            msrp=props.get("msrp"),
            field_evidence=evidence,
            latest_prices=prices,
        )

    def vendor_prices(self, product_id: str, region: str | None = None) -> list[PriceSnapshotView]:
        region = normalize_region(region)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)-[:FROM_VENDOR]->(vendor:Vendor)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND (snapshot.region = $region OR ($region = "US" AND snapshot.region IS NULL))
            WITH vendor, snapshot
            ORDER BY snapshot.timestamp DESC
            WITH vendor, collect(snapshot)[0] AS latest
            RETURN latest.id AS id,
                   vendor.id AS vendor_id,
                   vendor.name AS vendor_name,
                   latest.price AS price,
                   latest.currency AS currency,
                   coalesce(latest.region, "US") AS region,
                   latest.country_code AS country_code,
                   latest.city AS city,
                   latest.raw_price AS raw_price,
                   latest.item_price AS item_price,
                   latest.item_price_sar AS item_price_sar,
                   latest.shipping_cost_sar AS shipping_cost_sar,
                   latest.final_landed_price AS final_landed_price,
                   latest.final_landed_currency AS final_landed_currency,
                   latest.final_landed_price_sar AS final_landed_price_sar,
                   latest.vat_included AS vat_included,
                   latest.vat_status AS vat_status,
                   latest.shipping_status AS shipping_status,
                   latest.warranty_status AS warranty_status,
                   latest.local_stock_status AS local_stock_status,
                   latest.vendor_region_type AS vendor_region_type,
                   latest.estimated_vat AS estimated_vat,
                   latest.import_fee AS import_fee,
                   latest.estimated_delivery_days AS estimated_delivery_days,
                   latest.seller_country AS seller_country,
                   latest.is_local_stock AS is_local_stock,
                   latest.is_imported AS is_imported,
                   latest.serves_saudi AS serves_saudi,
                   latest.warranty_type AS warranty_type,
                   latest.local_warranty AS local_warranty,
                   latest.region_rank_score AS region_rank_score,
                   latest.recommended_saudi_price_candidate AS recommended_saudi_price_candidate,
                   latest.final_landed_price_confidence AS final_landed_price_confidence,
                   latest.price_completeness_score AS price_completeness_score,
                   latest.trust_tier AS trust_tier,
                   latest.delivery_status AS delivery_status,
                   latest.local_stock_confidence AS local_stock_confidence,
                   latest.warranty_confidence AS warranty_confidence,
                   latest.delivery_confidence AS delivery_confidence,
                   latest.availability AS availability,
                   latest.timestamp AS timestamp,
                   coalesce(latest.shipping_cost, 0) AS shipping_cost,
                   latest.product_url AS product_url,
                   latest.seller AS seller,
                   latest.condition AS condition,
                   latest.listing_condition AS listing_condition,
                   latest.seller_type AS seller_type,
                   latest.marketplace_risk_score AS marketplace_risk_score,
                   latest.source AS source,
                   latest.source_type AS source_type,
                   latest.source_tier AS source_tier,
                   latest.trust_score AS trust_score,
                   latest.freshness_score AS freshness_score,
                   coalesce(latest.stale, false) AS stale,
                   coalesce(latest.accepted, true) AS accepted,
                   coalesce(latest.flags, []) AS flags
            ORDER BY
              CASE latest.availability WHEN "in_stock" THEN 0 ELSE 1 END,
              coalesce(latest.final_landed_price, latest.price + coalesce(latest.shipping_cost, 0))
            """,
            product_id=product_id,
            region=region,
            database_=settings.neo4j_database,
        )
        return [_snapshot_view(record.data()) for record in records]

    def price_history(
        self,
        product_id: str,
        region: str | None = None,
        limit: int = 200,
    ) -> list[PriceHistoryPoint]:
        region = normalize_region(region)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)-[:FROM_VENDOR]->(vendor:Vendor)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND (snapshot.region = $region OR ($region = "US" AND snapshot.region IS NULL))
            RETURN snapshot.timestamp AS timestamp,
                   vendor.name AS vendor_name,
                   coalesce(snapshot.final_landed_price, snapshot.price + coalesce(snapshot.shipping_cost, 0)) AS price,
                   coalesce(snapshot.final_landed_currency, snapshot.currency) AS currency,
                   snapshot.availability AS availability,
                   snapshot.trust_score AS trust_score,
                   snapshot.freshness_score AS freshness_score
            ORDER BY snapshot.timestamp ASC
            LIMIT $limit
            """,
            product_id=product_id,
            region=region,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [
            PriceHistoryPoint(
                timestamp=_to_datetime(record["timestamp"]),
                vendor_name=record["vendor_name"],
                price=float(record["price"]),
                currency=record["currency"],
                availability=record["availability"],
                trust_score=float(record["trust_score"]),
                freshness_score=float(record["freshness_score"]),
            )
            for record in records
        ]

    def refresh_target(self, product_id: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN p.id AS id,
                   p.name AS name,
                   coalesce(p.category, head([label IN labels(p) WHERE label <> "Component" AND label <> "Product"])) AS category,
                   p.model AS model
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return records[0].data() if records else None

    def products_due_for_refresh(self, *, limit: int = 50, top_only: bool = False) -> list[str]:
        stale_hours = 1 if top_only else 6
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND p.name IS NOT NULL
              AND (
                p.stale = true
                OR p.current_price_timestamp IS NULL
                OR p.current_price_timestamp < datetime() - duration({hours: $stale_hours})
              )
            RETURN p.id AS id
            ORDER BY
              CASE WHEN p.current_best_price IS NOT NULL THEN 0 ELSE 1 END,
              coalesce(p.current_price_timestamp, datetime("1970-01-01T00:00:00Z")),
              p.name
            LIMIT $limit
            """,
            limit=limit,
            stale_hours=stale_hours,
            database_=settings.neo4j_database,
        )
        return [str(record["id"]) for record in records if record["id"]]

    def create_job(self, job: PricingJob) -> None:
        self.driver.execute_query(
            """
            MERGE (job:PricingJob {id: $id})
            SET job.status = $status,
                job.kind = $kind,
                job.payload_json = $payload_json,
                job.created_at = $created_at,
                job.updated_at = $updated_at,
                job.attempts = $attempts,
                job.max_attempts = $max_attempts,
                job.trace_id = $trace_id,
                job.risk_level = $risk_level,
                job.approval_required = $approval_required
            """,
            id=job.id,
            status=job.status,
            kind=job.kind,
            payload_json=json.dumps(job.payload, sort_keys=True),
            created_at=job.created_at,
            updated_at=job.updated_at,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            trace_id=job.trace_id,
            risk_level=job.risk_level,
            approval_required=job.approval_required,
            database_=settings.neo4j_database,
        )

    def update_job(self, job: PricingJob) -> None:
        self.driver.execute_query(
            """
            MATCH (job:PricingJob {id: $id})
            SET job.status = $status,
                job.updated_at = $updated_at,
                job.error = $error,
                job.accepted_snapshots = $accepted_snapshots,
                job.rejected_snapshots = $rejected_snapshots,
                job.attempts = $attempts,
                job.trace_id = $trace_id,
                job.risk_level = $risk_level,
                job.approval_required = $approval_required
            """,
            id=job.id,
            status=job.status,
            updated_at=datetime.now(UTC),
            error=job.error,
            accepted_snapshots=job.accepted_snapshots,
            rejected_snapshots=job.rejected_snapshots,
            attempts=job.attempts,
            trace_id=job.trace_id,
            risk_level=job.risk_level,
            approval_required=job.approval_required,
            database_=settings.neo4j_database,
        )
