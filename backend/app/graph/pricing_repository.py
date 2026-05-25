from __future__ import annotations

import csv
from datetime import UTC, datetime
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from neo4j import Driver

from app.core.config import settings
from app.models.catalog import (
    CanonicalEvidenceRequest,
    CanonicalEvidenceResponse,
    CanonicalImportCommitRequest,
    CanonicalImportCommitResponse,
    CanonicalImportConflictView,
    CanonicalImportReasonCount,
    CanonicalImportStageRequest,
    CanonicalImportStageResponse,
    CanonicalStagedClearResponse,
    CanonicalStagedSummaryResponse,
    CatalogCategoryCoverage,
    CatalogCoverageResponse,
    CatalogExpansionCategorySummary,
    CatalogExpansionTargetFamily,
    CatalogExpansionTargetsResponse,
    CatalogFeedImportResponse,
    CatalogFeedImportRow,
    CatalogFeedRunView,
    ConfirmedCpuSpecEnrichmentItem,
    ConfirmedCpuSpecEnrichmentRequest,
    ConfirmedCpuSpecEnrichmentResponse,
    ConfirmedSpecEnrichmentItem,
    ConfirmedSpecEnrichmentRequest,
    ConfirmedSpecEnrichmentResponse,
    HybridGraphIntegrityResponse,
    HybridImportReviewItem,
    HybridImportReviewResponse,
    HybridIntegrityCheck,
    MarketEvidenceLinkItem,
    MarketEvidenceLinkRequest,
    MarketEvidenceLinkResponse,
    SpecAuditCategoryMissingFields,
    SpecAuditEvidenceSummary,
    SpecAuditPriceCountSnapshot,
    SpecAuditProductAction,
    SpecAuditProductListResponse,
    SpecAuditRunRequest,
    SpecAuditRunResponse,
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
from app.services.import_adapters.pc_part_dataset_adapter import load_pc_part_dataset_records
from app.services.catalog_expansion import (
    CATALOG_PRODUCT_STATES,
    PRIORITY_TIER_WEIGHTS,
    annotate_expansion_target,
    expansion_state,
    load_expansion_manifest,
    manifest_categories,
    match_expansion_target,
    near_expansion_target_count,
)
from app.services.region_config import get_region_config, normalize_region, vendor_region_type, vendor_trust_profile


logger = logging.getLogger("pc_builder.pricing_repository")

ACTIVE_PRICE_AVAILABILITY = {"in_stock", "preorder", "backorder"}
ACTIVE_BUILD_CATEGORIES = {"CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"}
SPEC_AUDIT_CATEGORIES = ("CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler")
SPEC_AUDIT_REQUIRED_FIELDS = {
    "CPU": ("socket", "cores", "threads", "tdp_w"),
    "Motherboard": ("socket", "chipset", "memory_type", "form_factor", "m2_slots", "pcie_x16_slots"),
    "RAM": ("memory_type", "capacity_gb", "speed_mhz", "kit_config"),
    "Storage": ("capacity_gb", "interface", "protocol", "form_factor"),
    "PSU": ("wattage_w", "efficiency_rating", "modularity"),
    "Case": ("supported_motherboard_form_factors", "max_gpu_length_mm", "max_cpu_cooler_height_mm"),
    "Cooler": ("socket_support", "radiator_size_mm", "height_mm"),
}
SPEC_AUDIT_GPU_FAMILY_FIELDS = ("chip_family", "vram_gb", "pcie_generation", "reference_tdp_w")
SPEC_AUDIT_GPU_EXACT_FIELDS = ("board_power_w", "length_mm", "slots", "power_connectors")
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
APPROVED_CANONICAL_IMPORT_SOURCES = {
    ("BuildCores/OpenDB", "canonical_specs"),
    ("pc-part-dataset", "community_repository"),
    ("Kaggle PC Parts Dataset", "kaggle_dataset"),
    ("Kaggle PC Parts Dataset", "benchmark_metadata"),
    ("Kaggle PC parts datasets", "kaggle_dataset"),
    ("Kaggle PC parts datasets", "benchmark_metadata"),
    ("Community Hardware Repository", "community_repository"),
    ("community hardware repositories", "community_repository"),
    ("Community repositories", "community_repository"),
}
CONFIRMED_SPEC_REQUIRED_FIELDS = {
    "CPU": ("socket", "cores", "threads", "tdp_w"),
    "GPU": ("vram_gb", "tdp_w", "length_mm", "pcie_generation"),
    "Motherboard": ("chipset", "socket", "memory_type", "form_factor", "m2_slots", "pcie_x16_slots"),
    "RAM": ("memory_type", "capacity_gb", "speed_mhz", "kit_config"),
    "Storage": ("capacity_gb", "interface", "protocol", "form_factor"),
    "PSU": ("wattage_w", "efficiency_rating", "modularity"),
    "Case": ("supported_motherboard_form_factors", "max_gpu_length_mm", "max_cpu_cooler_height_mm"),
    "Cooler": ("socket_support", "radiator_size_mm", "height_mm"),
}
GPU_FAMILY_REQUIRED_FIELDS = ("chip_family", "vram_gb", "pcie_generation", "reference_tdp_w")
GPU_EXACT_CARD_REQUIRED_FIELDS = ("vram_gb", "pcie_generation", "length_mm", "slots", "power_connectors")
CANONICAL_IDENTITY_CONFIDENCE_MIN = 0.8
SUPPORTED_CANONICAL_IMPORT_EXTENSIONS = {".json", ".csv", ".ndjson"}
BUNDLE_REJECTION_MARKERS = (
    "bundle",
    "combo",
    "prebuilt",
    "gaming pc",
    "desktop pc",
    "laptop",
    "mini pc",
    "accessory",
)


def _default_canonical_import_dir() -> Path:
    """Resolve the local-only import root for both Docker and source checkouts."""
    module_path = Path(__file__).resolve()
    candidates = (
        # Docker/Railway backend image: /app/app/graph/pricing_repository.py -> /app/data/imports
        module_path.parents[2] / "data" / "imports",
        # Source checkout root used by earlier local workflows: <repo>/data/imports
        module_path.parents[3] / "data" / "imports",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


ALLOWED_CANONICAL_IMPORT_DIR = _default_canonical_import_dir()


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
        r"\b(AMD|Intel|NVIDIA|ASUS|MSI|Gigabyte|ASRock|Corsair|Kingston|Samsung|WD|Crucial|DeepCool|NZXT|Seasonic|Thermalright|Cooler Master)\b",
        name,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _record_get(record: dict[str, Any], *keys: str) -> Any:
    lowered = {re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_"): value for key, value in record.items()}
    for key in keys:
        normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
        if normalized in lowered and lowered[normalized] not in (None, "", []):
            return lowered[normalized]
    return None


def _as_int(value: Any) -> int | None:
    if value in (None, "", []):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value).replace(",", ""))
    return int(match.group(0)) if match else None


def _as_float(value: Any) -> float | None:
    if value in (None, "", []):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else None


def _split_aliases(value: Any) -> list[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[,|;/]", str(value)) if item.strip()]


def _normalize_socket(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    text = str(value).upper().replace("SOCKET", "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_memory_type(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    match = re.search(r"DDR[345]", str(value), flags=re.IGNORECASE)
    return match.group(0).upper() if match else str(value).upper().strip()


def _normalize_form_factor(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    text = str(value).strip().lower()
    if text in {"micro-atx", "micro atx", "matx", "m-atx"}:
        return "mATX"
    if text in {"mini-itx", "mini itx", "itx"}:
        return "ITX"
    return str(value).upper().strip()


def _normalize_canonical_stage_record(raw: dict[str, Any], category: str, license_note: str) -> dict[str, Any]:
    name = str(_record_get(raw, "name", "product_name", "title", "model_name") or "").strip()
    brand = str(_record_get(raw, "brand", "manufacturer", "chip_vendor") or _brand_from_name(name) or "").strip()
    model = str(_record_get(raw, "model", "model_number") or name).strip()
    specs = _normalize_stage_specs(raw, category)
    canonical_key = str(_record_get(raw, "canonical_key", "key") or _catalog_canonical_key(category, name, brand, model)).strip()
    confidence = _stage_identity_confidence(name=name, brand=brand, model=model, category=category, specs=specs)
    aliases = _split_aliases(_record_get(raw, "aliases", "alias", "alternate_names"))
    inferred_field_names = {
        str(item.get("field"))
        for item in (raw.get("inferred_fields") or [])
        if isinstance(item, dict) and item.get("field")
    }
    gpu_exact_ready = _gpu_exact_ready(specs) if category == "GPU" else bool(raw.get("compatibility_ready"))
    gpu_family_ready = _gpu_family_ready(specs) if category == "GPU" else False
    if category == "GPU" and inferred_field_names.intersection({"tdp_w", "board_power_w", "pcie_generation", "reference_tdp_w"}):
        gpu_exact_ready = False
        gpu_family_ready = False
    gpu_missing_exact = _gpu_exact_missing_fields(specs) if category == "GPU" else []
    readiness_state = _gpu_readiness_state(
        category=category,
        specs=specs,
        record={
            "compatibility_ready": raw.get("compatibility_ready"),
            "compatibility_ready_exact": raw.get("compatibility_ready_exact") or gpu_exact_ready,
            "compatibility_ready_family": raw.get("compatibility_ready_family") or gpu_family_ready,
        },
    )
    return _clean_properties(
        {
            "source_name": "",
            "source_type": "",
            "license_note": license_note,
            "category": category,
            "raw_name": name,
            "name": name,
            "normalized_name": name.upper(),
            "canonical_key": canonical_key,
            "brand": brand or None,
            "model": model or None,
            "specs": specs,
            "aliases": aliases,
            "identity_confidence": confidence,
            "required_specs_present": _catalog_row_has_required_specs(category, specs),
            "compatibility_ready": raw.get("compatibility_ready"),
            "compatibility_ready_exact": (raw.get("compatibility_ready_exact") or gpu_exact_ready) if category == "GPU" else raw.get("compatibility_ready"),
            "compatibility_ready_family": (raw.get("compatibility_ready_family") or gpu_family_ready) if category == "GPU" else False,
            "readiness_state": raw.get("readiness_state") or readiness_state,
            "compatibility_completeness_score": raw.get("compatibility_completeness_score"),
            "missing_compatibility_fields": raw.get("missing_compatibility_fields"),
            "missing_exact_card_fields": raw.get("missing_exact_card_fields") or gpu_missing_exact,
            "inferred_fields": raw.get("inferred_fields"),
            "validation_status": "pending",
            "rejected_reasons": [],
            "warning_reasons": raw.get("warning_reasons") or [],
        }
    )


def _normalize_stage_specs(raw: dict[str, Any], category: str) -> dict[str, Any]:
    raw_specs = raw.get("specs")
    if isinstance(raw_specs, dict):
        return _clean_properties(raw_specs)
    if category == "CPU":
        cores = _as_int(_record_get(raw, "cores", "core_count", "total_cores"))
        threads = _as_int(_record_get(raw, "threads", "thread_count"))
        cores_threads = _record_get(raw, "cores_threads", "cores / threads", "cores/threads")
        if isinstance(cores_threads, str) and "/" in cores_threads:
            parts = [part.strip() for part in cores_threads.split("/", 1)]
            cores = cores or _as_int(parts[0])
            threads = threads or _as_int(parts[1])
        return _clean_properties(
            {
                "socket": _normalize_socket(_record_get(raw, "socket")),
                "cores": cores,
                "threads": threads,
                "tdp_w": _as_int(_record_get(raw, "tdp_w", "tdp")),
                "base_clock_ghz": _as_float(_record_get(raw, "base_clock_ghz", "clock", "base_clock")),
                "boost_clock_ghz": _as_float(_record_get(raw, "boost_clock_ghz", "boost_clock")),
                "generation": _record_get(raw, "generation", "family"),
            }
        )
    if category == "GPU":
        chip_family = _record_get(raw, "chip_family", "gpu_family", "chipset", "model")
        return _clean_properties(
            {
                "chip_vendor": _record_get(raw, "chip_vendor", "gpu_vendor", "brand"),
                "chip_family": chip_family,
                "vram_gb": _as_int(_record_get(raw, "vram_gb", "memory_gb", "vram")),
                "reference_tdp_w": _as_int(_record_get(raw, "reference_tdp_w")),
                "board_power_w": _as_int(_record_get(raw, "board_power_w")),
                "tdp_w": _as_int(_record_get(raw, "tdp_w", "tdp", "board_power_w")),
                "length_mm": _as_int(_record_get(raw, "length_mm", "card_length_mm")),
                "slots": _as_float(_record_get(raw, "slots", "slot_width")),
                "power_connectors": _record_get(raw, "power_connectors", "connectors"),
                "pcie_generation": _record_get(raw, "pcie_generation", "pcie", "interface"),
            }
        )
    if category == "Motherboard":
        return _clean_properties(
            {
                "chipset": _record_get(raw, "chipset"),
                "socket": _normalize_socket(_record_get(raw, "socket")),
                "memory_type": _normalize_memory_type(_record_get(raw, "memory_type", "memory")),
                "form_factor": _normalize_form_factor(_record_get(raw, "form_factor", "size")),
                "m2_slots": _as_int(_record_get(raw, "m2_slots", "m.2_slots")),
                "pcie_x16_slots": _as_int(_record_get(raw, "pcie_x16_slots", "pcie_slots")),
            }
        )
    if category == "RAM":
        return _clean_properties(
            {
                "memory_type": _normalize_memory_type(_record_get(raw, "memory_type", "type")),
                "capacity_gb": _as_int(_record_get(raw, "capacity_gb", "capacity")),
                "speed_mhz": _as_int(_record_get(raw, "speed_mhz", "speed_mt_s", "speed")),
                "kit_config": _record_get(raw, "kit_config", "configuration"),
                "cas_latency": _record_get(raw, "cas_latency", "cl"),
            }
        )
    if category == "Storage":
        return _clean_properties(
            {
                "capacity_tb": _as_float(_record_get(raw, "capacity_tb")),
                "capacity_gb": _as_int(_record_get(raw, "capacity_gb", "capacity")),
                "interface": _record_get(raw, "interface"),
                "form_factor": _record_get(raw, "form_factor"),
                "protocol": _record_get(raw, "protocol"),
            }
        )
    if category == "PSU":
        return _clean_properties(
            {
                "wattage_w": _as_int(_record_get(raw, "wattage_w", "wattage", "power_w")),
                "efficiency_rating": _record_get(raw, "efficiency_rating", "efficiency", "80_plus"),
                "modularity": _record_get(raw, "modularity", "modular"),
            }
        )
    if category == "Case":
        return _clean_properties(
            {
                "supported_motherboard_form_factors": _split_aliases(_record_get(raw, "form_factor_support", "supported_form_factors")),
                "max_gpu_length_mm": _as_int(_record_get(raw, "max_gpu_length_mm", "gpu_clearance_mm")),
                "max_cpu_cooler_height_mm": _as_int(_record_get(raw, "max_cpu_cooler_height_mm", "cpu_cooler_clearance_mm")),
            }
        )
    if category == "Cooler":
        return _clean_properties(
            {
                "cooler_type": _record_get(raw, "cooler_type", "type"),
                "socket_support": _split_aliases(_record_get(raw, "socket_support", "supported_sockets")),
                "radiator_size_mm": _as_int(_record_get(raw, "radiator_size_mm", "radiator")),
                "height_mm": _as_int(_record_get(raw, "height_mm", "cooler_height_mm")),
            }
        )
    return {}


def _stage_identity_confidence(
    *,
    name: str,
    brand: str,
    model: str,
    category: str,
    specs: dict[str, Any],
) -> float:
    if not name:
        return 0.0
    if category == "GPU" and brand and model:
        return 0.86
    if brand and model and _catalog_row_has_required_specs(category, specs):
        return 0.92
    if _catalog_row_has_required_specs(category, specs):
        return 0.84
    return 0.55


def _component_bundle_rejection(name: str) -> str | None:
    lowered = name.lower()
    for marker in BUNDLE_REJECTION_MARKERS:
        if marker in lowered:
            return "record looks like a bundle/prebuilt/accessory"
    return None


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
        catalog_state=data.get("catalog_state"),
        compatibility_ready=data.get("compatibility_ready"),
        compatibility_ready_exact=data.get("compatibility_ready_exact"),
        compatibility_ready_family=data.get("compatibility_ready_family"),
        readiness_state=data.get("readiness_state"),
        missing_exact_card_fields=_staged_string_list(data.get("missing_exact_card_fields")),
        missing_compatibility_fields=_staged_string_list(data.get("missing_compatibility_fields")),
        inferred_fields=_staged_string_list(data.get("inferred_fields")),
        market_linked_count=int(data.get("market_linked_count") or 0),
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


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
    if data.get("category") == "GPU":
        exact_ready = bool(data.get("compatibility_ready_exact") or data.get("compatibility_ready"))
        family_ready = bool(data.get("compatibility_ready_family"))
        data["readiness_state"] = (
            "compatibility_ready_exact"
            if exact_ready
            else "compatibility_ready_family"
            if family_ready
            else data.get("readiness_state") or "metadata_only"
        )
        data["compatibility_ready"] = exact_ready or family_ready
    else:
        data["readiness_state"] = "compatibility_ready_exact" if data.get("compatibility_ready") else data.get("readiness_state")
    seed_without_price = not data.get("canonical_key") and data["price_status"] == "unavailable"
    data["data_origin"] = data.get("data_origin") or ("seed" if seed_without_price else "live")
    if data["price_status"] != "unavailable" and data.get("cheapest_price_sar"):
        data["catalog_state"] = "saudi_priced"
    elif (
        data.get("readiness_state") in {"metadata_only", None}
        and (data.get("compatibility_ready") is False or _staged_string_list(data.get("missing_compatibility_fields")))
    ):
        data["catalog_state"] = "needs_spec_confirmation"
    else:
        data["catalog_state"] = "catalog_only"
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
    if category == "GPU":
        return _gpu_exact_ready({key.removeprefix("spec_"): value for key, value in props.items()})
    required = {
        "CPU": ("spec_socket", "spec_cores", "spec_threads", "spec_tdp_w"),
        "Motherboard": ("spec_socket", "spec_memory_type", "spec_form_factor", "spec_m2_slots", "spec_pcie_x16_slots"),
        "RAM": ("spec_memory_type", "spec_capacity_gb", "spec_speed_mhz", "spec_kit_config"),
        "Storage": ("spec_capacity_gb", "spec_interface", "spec_protocol", "spec_form_factor"),
        "PSU": ("spec_wattage_w", "spec_efficiency_rating", "spec_modularity"),
        "Case": ("spec_supported_motherboard_form_factors", "spec_max_gpu_length_mm", "spec_max_cpu_cooler_height_mm"),
        "Cooler": ("spec_socket_support", "spec_radiator_size_mm", "spec_height_mm"),
    }.get(category, ())
    return all(props.get(key) not in (None, "", []) for key in required)


def _catalog_row_has_required_specs(category: str, specs: dict[str, Any]) -> bool:
    props = {f"spec_{key}": value for key, value in specs.items()}
    return _catalog_has_required_specs(category, props)


def _gpu_exact_missing_fields(specs: dict[str, Any]) -> list[str]:
    missing = [field for field in GPU_EXACT_CARD_REQUIRED_FIELDS if specs.get(field) in (None, "", [])]
    if specs.get("board_power_w") in (None, "", []) and specs.get("tdp_w") in (None, "", []):
        missing.append("board_power_w")
    return list(dict.fromkeys(missing))


def _gpu_family_missing_fields(specs: dict[str, Any]) -> list[str]:
    return [field for field in GPU_FAMILY_REQUIRED_FIELDS if specs.get(field) in (None, "", [])]


def _gpu_exact_ready(specs: dict[str, Any]) -> bool:
    return not _gpu_exact_missing_fields(specs)


def _gpu_family_ready(specs: dict[str, Any]) -> bool:
    return not _gpu_family_missing_fields(specs)


def _is_gpu_family_spec_record(category: str, canonical_key: str) -> bool:
    return category == "GPU" and str(canonical_key).upper().startswith("GPU|FAMILY|")


def _gpu_family_name_from_confirmed_spec(canonical_key: str, specs: dict[str, Any]) -> str:
    chip_family = str(specs.get("chip_family") or "").strip()
    if chip_family:
        return re.sub(r"\s+", " ", chip_family.replace("GeForce ", "").replace("Radeon ", "")).strip()
    parts = str(canonical_key or "").split("|", 2)
    family = parts[2] if len(parts) == 3 else str(canonical_key or "")
    return re.sub(r"\s+", " ", family.replace("_", " ")).strip()


def _gpu_family_target_key(family_name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(family_name or "").upper()).strip("_")
    return f"GPU|{normalized}" if normalized else ""


def _gpu_readiness_state(*, category: str, specs: dict[str, Any], record: dict[str, Any] | None = None) -> str:
    record = record or {}
    if category != "GPU":
        if bool(record.get("compatibility_ready")) or _catalog_row_has_required_specs(category, specs):
            return "compatibility_ready_exact"
        return "metadata_only"
    if bool(record.get("compatibility_ready_exact")) or _gpu_exact_ready(specs):
        return "compatibility_ready_exact"
    if bool(record.get("compatibility_ready_family")) or _gpu_family_ready(specs):
        return "compatibility_ready_family"
    return "metadata_only"


def _confirmed_spec_evidence_field(category: str, specs: dict[str, Any]) -> str:
    if category == "GPU":
        if _gpu_exact_ready(specs):
            return "confirmed_gpu_card_specs"
        if _gpu_family_ready(specs):
            return "confirmed_gpu_family_specs"
    return f"confirmed_{category.lower()}_specs"


def _canonical_value_equal(left: Any, right: Any) -> bool:
    if left in (None, "", []) or right in (None, "", []):
        return True
    return str(left).strip().lower() == str(right).strip().lower()


def _canonical_conflict_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> list[str]:
    guarded_fields = {
        "brand",
        "model",
        "category",
        "spec_socket",
        "spec_chipset",
        "spec_memory_type",
        "spec_form_factor",
        "spec_capacity_gb",
        "spec_wattage_w",
        "spec_efficiency_rating",
        "spec_cores",
        "spec_threads",
        "spec_tdp_w",
    }
    conflicts: list[str] = []
    for key in sorted(guarded_fields):
        if key not in incoming:
            continue
        if not _canonical_value_equal(existing.get(key), incoming.get(key)):
            conflicts.append(key)
    return conflicts


def _extract_staged_specs(record: dict[str, Any]) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    raw_specs = record.get("specs")
    if isinstance(raw_specs, str):
        try:
            decoded = json.loads(raw_specs)
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            specs.update(decoded)
    elif isinstance(raw_specs, dict):
        specs.update(raw_specs)
    for key, value in record.items():
        if key.startswith("spec_") and value not in (None, "", []):
            specs[key.removeprefix("spec_")] = value
    return specs


def _catalog_row_from_staged_record(record: dict[str, Any], category: str) -> CatalogFeedImportRow:
    return CatalogFeedImportRow(
        name=str(record.get("name") or record.get("product_name") or ""),
        category=record.get("category") or category,
        brand=record.get("brand"),
        model=record.get("model"),
        canonical_key=record.get("canonical_key"),
        image_url=record.get("image_url") or record.get("imageUrl"),
        processed_image_url=record.get("processed_image_url"),
        specs=_extract_staged_specs(record),
    )


def _canonical_import_skip_reason(
    *,
    record: dict[str, Any],
    row: CatalogFeedImportRow,
    request: CanonicalImportCommitRequest,
) -> str | None:
    if (request.source_name, request.source_type) not in APPROVED_CANONICAL_IMPORT_SOURCES:
        return "unsupported canonical source"
    if str(record.get("source_name") or request.source_name) != request.source_name:
        return "source attribution mismatch"
    if str(record.get("source_type") or request.source_type) != request.source_type:
        return "source type mismatch"
    if not str(record.get("license_note") or "").strip():
        return "missing license/usage note"
    if row.category != request.category:
        return "category mismatch"
    try:
        confidence = float(record.get("identity_confidence") or 0)
    except (TypeError, ValueError):
        return "invalid identity confidence"
    if confidence < CANONICAL_IDENTITY_CONFIDENCE_MIN:
        return "identity confidence below import threshold"
    if not row.canonical_key:
        return "missing canonical key"
    if request.category == "GPU":
        specs = dict(row.specs)
        exact_ready = bool(record.get("compatibility_ready_exact")) or _gpu_exact_ready(specs)
        family_ready = bool(record.get("compatibility_ready_family")) or _gpu_family_ready(specs)
        if _staged_inferred_field_names(record.get("inferred_fields")).intersection(
            {"tdp_w", "board_power_w", "pcie_generation", "reference_tdp_w"}
        ):
            exact_ready = False
            family_ready = False
        if exact_ready:
            exact_missing = _gpu_exact_missing_fields(specs)
            if exact_missing:
                return f"missing exact GPU card specs: {', '.join(exact_missing)}"
            return None
        if family_ready:
            family_missing = _gpu_family_missing_fields(specs)
            if family_missing:
                return f"missing GPU family specs: {', '.join(family_missing)}"
            return None
        return "GPU needs family specs or exact card specs"
    if record.get("compatibility_ready") is False:
        return "not compatibility-ready"
    if not _catalog_row_has_required_specs(request.category, row.specs):
        return "missing required compatibility specs"
    return None


def _resolve_import_dataset_path(dataset_path: str) -> Path:
    candidate = Path(dataset_path)
    if candidate.is_absolute():
        raise ValueError("dataset_path must be relative to data/imports; absolute paths are not allowed")
    if any(part == ".." for part in candidate.parts):
        raise ValueError("dataset_path cannot contain path traversal")
    allowed_root = ALLOWED_CANONICAL_IMPORT_DIR.resolve()
    if candidate.parts[:2] == ("data", "imports"):
        candidate = Path(*candidate.parts[2:]) if len(candidate.parts) > 2 else Path()
    resolved = (allowed_root / candidate).resolve()
    if allowed_root != resolved and allowed_root not in resolved.parents:
        raise ValueError("dataset_path must stay under data/imports")
    if resolved.suffix.lower() not in SUPPORTED_CANONICAL_IMPORT_EXTENSIONS:
        raise ValueError("unsupported dataset file type")
    if not resolved.exists() or not resolved.is_file():
        raise ValueError(
            "dataset file not found: "
            f"requested dataset_path='{dataset_path}', "
            f"allowed_base_directory='{allowed_root}', "
            "hint='Railway images must include backend/data fixtures copied to /app/data.'"
        )
    return resolved


def _load_canonical_dataset_file(path: Path, limit: int) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("records") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("JSON dataset must contain a list or a records list")
        return [dict(row) for row in rows[:limit] if isinstance(row, dict)]
    if suffix == ".ndjson":
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if len(rows) >= limit:
                break
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(dict(item))
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for index, row in enumerate(reader) if index < limit]


def _count_reasons(rows: list[str]) -> list[CanonicalImportReasonCount]:
    counts: dict[str, int] = {}
    for reason in rows:
        counts[reason] = counts.get(reason, 0) + 1
    return [
        CanonicalImportReasonCount(reason=reason, count=count)
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]


def _stage_preselection_sort_key(record: dict[str, Any]) -> tuple[int, int, int, str]:
    category = str(record.get("category") or "")
    match = match_expansion_target(record, category)
    if match:
        missing_count = len(_missing_required_specs_for_stage(record))
        return (
            PRIORITY_TIER_WEIGHTS.get(match.priority_tier, 9000),
            missing_count,
            match.priority,
            str(record.get("normalized_name") or record.get("name") or ""),
        )
    near_count = int(record.get("near_match_count") or near_expansion_target_count(record, category))
    return (
        8000 if near_count else 9000,
        999,
        9000,
        str(record.get("normalized_name") or record.get("name") or ""),
    )


def _missing_required_specs_for_stage(record: dict[str, Any]) -> list[str]:
    category = str(record.get("category") or "")
    specs = _extract_staged_specs(record)
    required_fields = {
        "CPU": ("socket", "cores", "threads", "tdp_w"),
        "GPU": ("vram_gb", "tdp_w", "length_mm", "pcie_generation"),
        "Motherboard": ("socket", "memory_type", "form_factor", "chipset", "m2_slots", "pcie_x16_slots"),
        "RAM": ("memory_type", "capacity_gb", "speed_mhz", "kit_config"),
        "Storage": ("capacity_gb", "interface", "protocol", "form_factor"),
        "PSU": ("wattage_w", "efficiency_rating", "modularity"),
        "Case": ("supported_motherboard_form_factors", "max_gpu_length_mm", "max_cpu_cooler_height_mm"),
        "Cooler": ("socket_support", "radiator_size_mm", "height_mm"),
    }.get(category, ())
    inferred_names = _staged_inferred_field_names(record.get("inferred_fields"))
    return [
        field
        for field in required_fields
        if specs.get(field) in (None, "", []) or field in inferred_names
    ]


def _property_list(value: Any) -> list[Any]:
    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        if isinstance(decoded, list):
            return decoded
        if isinstance(decoded, dict):
            return [decoded]
    return [value]


def _staged_string_list(value: Any) -> list[str]:
    strings: list[str] = []
    for item in _property_list(value):
        if isinstance(item, dict):
            field = item.get("field") or item.get("inferred_value") or item.get("warning_reason")
            if field not in (None, "", []):
                strings.append(str(field))
        elif item not in (None, "", []):
            strings.append(str(item))
    return list(dict.fromkeys(strings))


def _staged_inferred_field_names(value: Any) -> set[str]:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = value
        value = decoded
    if not isinstance(value, list):
        return set()
    names: set[str] = set()
    for item in value:
        if isinstance(item, dict) and item.get("field"):
            names.add(str(item["field"]))
        elif isinstance(item, str):
            names.add(item)
    return names


def _hybrid_review_next_action(classification: str, missing_fields: list[str], conflicts: list[str], market_linked: bool) -> str:
    if classification == "reject":
        return "Fix rejected staged data, source attribution, or category before retrying."
    if classification == "conflict_requires_founder_review":
        return f"Review founder approval before merging conflicting field(s): {', '.join(conflicts[:4])}."
    if classification == "metadata_only_needs_enrichment":
        missing = ", ".join(missing_fields[:4]) if missing_fields else "confirmed compatibility evidence"
        return f"Attach confirmed spec evidence for {missing} before commit."
    if market_linked:
        return "Eligible for clean canonical commit; Saudi price evidence is already linked by identity."
    return "Eligible for clean canonical commit; add approved Saudi URLs later for local pricing."


def _coverage_next_action(category: str, priced_count: int, missing_specs: int, stale_count: int) -> str:
    if priced_count == 0:
        return f"Add trusted Saudi product URLs or structured price rows for {category}."
    if missing_specs:
        return f"Import compatibility-grade specs for {missing_specs} {category} product(s)."
    if stale_count:
        return f"Refresh approved known URLs for {category} to reduce stale prices."
    return "Keep normal price refresh monitoring."


def _initial_expansion_family_stats(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for category, config in dict(manifest.get("categories") or {}).items():
        for rank, family_entry in enumerate(config.get("families") or [], start=1):
            family_name = _expansion_family_name(family_entry)
            priority_tier = _expansion_family_tier(family_entry)
            priority = PRIORITY_TIER_WEIGHTS.get(priority_tier, 0) + rank
            key = f"{category}|{str(family_name).upper().replace('-', ' ').replace(' ', '_')}"
            stats[key] = {
                "category": category,
                "family_key": key,
                "family_name": str(family_name),
                "priority": priority,
                "priority_tier": priority_tier,
                "required_specs": tuple(str(item) for item in config.get("required_specs") or []),
                "canonical_count": 0,
                "compatibility_ready_count": 0,
                "saudi_priced_count": 0,
                "trusted_vendor_count": 0,
                "staged_count": 0,
                "metadata_only_count": 0,
                "conflict_count": 0,
                "missing_required_specs": set(),
            }
    return stats


def _expansion_family_name(family_entry: Any) -> str:
    if isinstance(family_entry, dict):
        return str(family_entry.get("name") or "").strip()
    return str(family_entry).strip()


def _expansion_family_tier(family_entry: Any) -> str:
    if isinstance(family_entry, dict):
        tier = str(family_entry.get("priority_tier") or "current_gen_priority").strip()
    else:
        tier = "current_gen_priority"
    return tier if tier in PRIORITY_TIER_WEIGHTS else "current_gen_priority"


def _initial_expansion_category_stats(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    family_stats = _initial_expansion_family_stats(manifest)
    stats: dict[str, dict[str, Any]] = {}
    for category, config in dict(manifest.get("categories") or {}).items():
        stats[category] = {
            "target_min": int(config.get("target_min") or 0),
            "target_max": int(config.get("target_max") or 0),
            "safe_stage_batch_size": int(config.get("safe_stage_batch_size") or 100),
            "safe_commit_batch_size": int(config.get("safe_commit_batch_size") or 100),
            "canonical_count": 0,
            "compatibility_ready_count": 0,
            "saudi_priced_count": 0,
            "trusted_vendor_count": 0,
            "staged_count": 0,
            "metadata_only_count": 0,
            "conflict_count": 0,
            "missing_required_specs": set(),
            "family_keys": [key for key, value in family_stats.items() if value["category"] == category],
        }
    return stats


def _target_key_for_props(props: dict[str, Any], category: str) -> str | None:
    existing = str(props.get("target_family_key") or "").strip()
    if existing:
        return existing
    record = _record_from_product_props(props, category)
    match = match_expansion_target(record, category)
    return match.family_key if match else None


def _record_from_product_props(props: dict[str, Any], category: str) -> dict[str, Any]:
    specs = {
        key.removeprefix("spec_"): value
        for key, value in props.items()
        if str(key).startswith("spec_") and value not in (None, "", [])
    }
    return {
        "category": category,
        "raw_name": props.get("name"),
        "name": props.get("name"),
        "normalized_name": props.get("normalized_name"),
        "canonical_key": props.get("canonical_key"),
        "brand": props.get("brand"),
        "model": props.get("model"),
        "specs": specs,
    }


def _product_category_from_props(props: dict[str, Any], labels: Any, categories: list[str]) -> str | None:
    category = str(props.get("category") or "")
    if category in categories:
        return category
    label_set = {str(label) for label in labels or []}
    for candidate in categories:
        if candidate in label_set:
            return candidate
    return None


def _product_missing_required_specs(props: dict[str, Any], required_specs: tuple[str, ...]) -> list[str]:
    missing = []
    for field in required_specs:
        if props.get(f"spec_{field}") in (None, "", []):
            missing.append(field)
    return missing


def _expansion_next_action(
    *,
    canonical_count: int,
    staged_count: int,
    compatibility_ready_count: int,
    saudi_priced_count: int,
    conflict_count: int,
    missing_required_specs: list[str],
    family_name: str,
    priority_tier: str = "current_gen_priority",
) -> str:
    if conflict_count:
        return f"Review founder conflicts for {family_name} before merging."
    if priority_tier == "legacy_deprioritized" and saudi_priced_count == 0:
        return f"Deprioritized legacy family; continue only if strong Saudi price evidence appears for {family_name}."
    if canonical_count == 0 and staged_count == 0:
        if priority_tier == "value_fallback":
            return f"Stage {family_name} only after current-gen coverage or when value pricing is strong."
        return f"Stage current-generation curated metadata for {family_name}."
    if compatibility_ready_count == 0:
        fields = ", ".join(missing_required_specs[:4]) if missing_required_specs else "confirmed compatibility specs"
        return f"Attach confirmed evidence for {fields}."
    if saudi_priced_count == 0:
        prefix = "Value fallback: " if priority_tier == "value_fallback" else ""
        return f"{prefix}Preview exact Saudi product URLs for {family_name}."
    return "Keep price refresh monitoring and add second-vendor coverage when available."


def _expansion_category_next_action(category: str, stats: dict[str, Any]) -> str:
    if int(stats["conflict_count"]):
        return f"Resolve {category} founder review conflicts before larger imports."
    if int(stats["canonical_count"]) < max(1, int(stats["target_min"]) // 4):
        if category in {"RAM", "Storage", "PSU"}:
            return f"Run faster 50-item curated {category} staging batches from current-generation targets first."
        if category in {"Motherboard", "Case", "Cooler"}:
            return f"Run cautious 10-20 item {category} staging batches from current-generation targets first."
        return f"Run small curated {category} staging batches from current-generation targets first."
    if int(stats["compatibility_ready_count"]) < int(stats["canonical_count"]):
        return f"Attach confirmed compatibility evidence to metadata-only {category} products."
    if int(stats["saudi_priced_count"]) < int(stats["compatibility_ready_count"]):
        return f"Add approved Saudi product URLs for the ready {category} families."
    return f"{category} is on track; expand the next priority category."


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


def _spec_audit_fixture_evidence() -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    base = Path(__file__).resolve().parents[2] / "data" / "canonical_specs"
    if not base.exists():
        return evidence
    for path in base.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_name = str(payload.get("source_name") or path.stem)
        for key, value in payload.items():
            if not key.endswith("_records") or not isinstance(value, list):
                continue
            for row in value:
                if not isinstance(row, dict):
                    continue
                canonical_key = str(row.get("canonical_key") or "").strip()
                specs = row.get("specs")
                if canonical_key and isinstance(specs, dict):
                    evidence.setdefault(canonical_key, {})
                    for field, spec_value in specs.items():
                        evidence[canonical_key].setdefault(field, []).append(
                            {
                                "value": spec_value,
                                "source_name": source_name,
                                "field": str(field),
                                "trust_score": 0.95,
                                "approval_state": "approved",
                            }
                        )
    return evidence


def _spec_audit_category(product: dict[str, Any], selected_categories: list[str]) -> str:
    category = str(product.get("category") or "").strip()
    if category in selected_categories:
        return category
    labels = product.get("labels") or []
    if isinstance(labels, list):
        for label in labels:
            if str(label) in selected_categories:
                return str(label)
    return category


def _spec_audit_specs(product: dict[str, Any]) -> dict[str, Any]:
    specs: dict[str, Any] = {}
    summary = product.get("summary_specs")
    if isinstance(summary, str):
        try:
            decoded = json.loads(summary)
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            specs.update(decoded)
    elif isinstance(summary, dict):
        specs.update(summary)
    for key, value in product.items():
        if str(key).startswith("spec_"):
            specs[str(key).removeprefix("spec_")] = value
    for field in {
        *SPEC_AUDIT_GPU_FAMILY_FIELDS,
        *SPEC_AUDIT_GPU_EXACT_FIELDS,
        "socket",
        "cores",
        "threads",
        "tdp_w",
        "chipset",
        "memory_type",
        "form_factor",
        "m2_slots",
        "pcie_x16_slots",
        "capacity",
        "capacity_gb",
        "interface",
        "protocol",
        "wattage_w",
        "efficiency_rating",
        "modularity",
        "supported_motherboard_form_factors",
        "max_gpu_length_mm",
        "max_cpu_cooler_height_mm",
        "socket_support",
        "radiator_size_mm",
        "height_mm",
    }:
        if field in product and field not in specs:
            specs[field] = product[field]
    if "capacity_gb" not in specs and "capacity" in specs:
        specs["capacity_gb"] = specs["capacity"]
    return {key: value for key, value in specs.items() if value not in (None, "", [])}


def _spec_audit_required_fields(category: str) -> tuple[str, ...]:
    if category == "GPU":
        return (*SPEC_AUDIT_GPU_FAMILY_FIELDS, *SPEC_AUDIT_GPU_EXACT_FIELDS)
    if category == "Cooler":
        return ("socket_support", "radiator_size_or_height")
    return SPEC_AUDIT_REQUIRED_FIELDS.get(category, ())


def _spec_audit_value(specs: dict[str, Any], field: str) -> Any:
    if field == "radiator_size_or_height":
        return specs.get("radiator_size_mm") or specs.get("height_mm")
    if field == "capacity_gb":
        return specs.get("capacity_gb") or specs.get("capacity")
    if field == "board_power_w":
        return specs.get("board_power_w") or specs.get("tdp_w")
    return specs.get(field)


def _spec_audit_missing(value: Any) -> bool:
    return value in (None, "", [])


def _spec_audit_normalized(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str).upper()
    return re.sub(r"\s+", " ", str(value)).strip().upper()


def _spec_audit_values_match(left: Any, right: Any) -> bool:
    return _spec_audit_normalized(left) == _spec_audit_normalized(right)


def _spec_audit_inferred_fields(product: dict[str, Any]) -> list[str]:
    raw_values = [
        product.get("inferred_fields"),
        product.get("spec_inferred_fields"),
        product.get("inferred_compatibility_fields"),
    ]
    fields: list[str] = []
    for raw in raw_values:
        if isinstance(raw, str):
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                decoded = [raw]
        else:
            decoded = raw
        if isinstance(decoded, list):
            for item in decoded:
                if isinstance(item, dict) and item.get("field"):
                    fields.append(str(item["field"]))
                elif isinstance(item, str):
                    fields.append(item)
    return list(dict.fromkeys(fields))


def _spec_audit_evidence_by_field(
    canonical_key: str | None,
    evidence_rows: list[dict[str, Any]],
    fixture_evidence: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_field: dict[str, list[dict[str, Any]]] = {}
    for evidence in evidence_rows:
        trust_score = _optional_float(evidence.get("trust_score"))
        if trust_score is not None and trust_score < 0.7:
            continue
        if str(evidence.get("evidence_type") or "canonical_spec") != "canonical_spec":
            continue
        field = str(evidence.get("field") or "").strip()
        value_json = evidence.get("value_json")
        value = None
        if isinstance(value_json, str):
            try:
                value = json.loads(value_json)
            except json.JSONDecodeError:
                value = value_json
        if isinstance(value, dict) and isinstance(value.get("specs"), dict):
            for spec_field, spec_value in value["specs"].items():
                by_field.setdefault(str(spec_field), []).append({**evidence, "field": str(spec_field), "value": spec_value})
        elif field:
            by_field.setdefault(field, []).append({**evidence, "value": value})
    if canonical_key and canonical_key in fixture_evidence:
        for field, values in fixture_evidence[canonical_key].items():
            by_field.setdefault(field, []).extend(values)
    return by_field


def _spec_audit_evidence_summary(evidence_by_field: dict[str, list[dict[str, Any]]]) -> list[SpecAuditEvidenceSummary]:
    summaries: list[SpecAuditEvidenceSummary] = []
    seen: set[tuple[str, str]] = set()
    for field, rows in evidence_by_field.items():
        for row in rows:
            source_name = str(row.get("source_name") or "unknown")
            key = (source_name, field)
            if key in seen:
                continue
            seen.add(key)
            summaries.append(
                SpecAuditEvidenceSummary(
                    source_name=source_name,
                    field=field,
                    trust_score=_optional_float(row.get("trust_score")),
                    approval_state=row.get("approval_state"),
                )
            )
    return summaries[:12]


def _spec_audit_status(
    *,
    category: str,
    product: dict[str, Any],
    specs: dict[str, Any],
    required_fields: tuple[str, ...],
    evidence_by_field: dict[str, list[dict[str, Any]]],
) -> tuple[str, list[str], list[str], list[str], list[str], str | None]:
    inferred_fields = _spec_audit_inferred_fields(product)
    missing_fields: list[str] = []
    conflicting_fields: list[str] = []
    safe_fix_fields: list[str] = []
    unbacked_fields: list[str] = []

    for field in required_fields:
        value = _spec_audit_value(specs, field)
        evidence_values = evidence_by_field.get(field, [])
        has_evidence = bool(evidence_values)
        if field in inferred_fields:
            missing_fields.append(field)
            continue
        if _spec_audit_missing(value):
            missing_fields.append(field)
            if has_evidence:
                safe_fix_fields.append(field)
            continue
        if not has_evidence:
            unbacked_fields.append(field)
            continue
        if not any(_spec_audit_values_match(value, row.get("value")) for row in evidence_values):
            conflicting_fields.append(field)

    stale_reason = _spec_audit_stale_reason(category, product, specs)
    if conflicting_fields:
        return "spec_conflict_requires_review", missing_fields, conflicting_fields, inferred_fields, safe_fix_fields, stale_reason
    if safe_fix_fields:
        return "safe_fix_available", missing_fields, conflicting_fields, inferred_fields, safe_fix_fields, stale_reason
    if missing_fields or unbacked_fields:
        return "missing_trusted_evidence", list(dict.fromkeys([*missing_fields, *unbacked_fields])), conflicting_fields, inferred_fields, safe_fix_fields, stale_reason
    if stale_reason:
        return "stale_or_deprioritized", missing_fields, conflicting_fields, inferred_fields, safe_fix_fields, stale_reason
    return "verified_current", missing_fields, conflicting_fields, inferred_fields, safe_fix_fields, stale_reason


def _spec_audit_stale_reason(category: str, product: dict[str, Any], specs: dict[str, Any]) -> str | None:
    record = {
        "name": product.get("name"),
        "raw_name": product.get("name"),
        "brand": product.get("brand"),
        "model": product.get("model"),
        "canonical_key": product.get("canonical_key"),
        "specs": specs,
    }
    match = match_expansion_target(record, category)
    if match and match.priority_tier == "legacy_deprioritized":
        return f"Phase 2 target tier is legacy_deprioritized: {match.family_name}"
    return None


def _spec_audit_next_action(status: str, missing: list[str], conflicts: list[str], safe_fixes: list[str], stale_reason: str | None) -> str:
    if status == "verified_current":
        return "No action needed."
    if status == "safe_fix_available":
        return f"Review trusted evidence and apply safe enrichment for {', '.join(safe_fixes[:4])}."
    if status == "spec_conflict_requires_review":
        return f"Founder review required for conflicting fields: {', '.join(conflicts[:4])}."
    if status == "stale_or_deprioritized":
        return stale_reason or "Review whether this legacy product should stay prioritized."
    return f"Attach trusted spec evidence for {', '.join(missing[:4])}."


def _spec_audit_fallback_action(product: dict[str, Any], category: str) -> SpecAuditProductAction:
    canonical_key = product.get("canonical_key")
    missing = list(_spec_audit_required_fields(category))
    return SpecAuditProductAction(
        product_id=str(product.get("id") or canonical_key or product.get("name") or "unknown"),
        canonical_key=str(canonical_key) if canonical_key else None,
        name=str(product.get("name") or canonical_key or "Unknown product"),
        category=category,
        status="missing_trusted_evidence",
        missing_fields=missing,
        next_action="Review product metadata and attach trusted spec evidence.",
    )


def _spec_audit_item_id(audit_id: str, action: SpecAuditProductAction) -> str:
    source_key = action.canonical_key or action.product_id or action.name
    digest = hashlib.sha256(f"{audit_id}|{source_key}".encode("utf-8")).hexdigest()[:32]
    return f"spec-audit-item:{digest}"


def _intelligence_from_record(data: dict[str, Any]) -> HardwareIntelligence:
    return HardwareIntelligence.model_validate_json(data["payload_json"])


class Neo4jPricingRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT product_canonical_key IF NOT EXISTS "
            "FOR (n:Product) REQUIRE n.canonical_key IS UNIQUE",
            "CREATE CONSTRAINT canonical_product_key IF NOT EXISTS "
            "FOR (n:CanonicalProduct) REQUIRE n.canonical_key IS UNIQUE",
            "CREATE CONSTRAINT brand_name IF NOT EXISTS FOR (n:Brand) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT socket_name IF NOT EXISTS FOR (n:Socket) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT memory_type_name IF NOT EXISTS FOR (n:MemoryType) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT chipset_name IF NOT EXISTS FOR (n:Chipset) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT form_factor_name IF NOT EXISTS FOR (n:FormFactor) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT efficiency_rating_name IF NOT EXISTS FOR (n:EfficiencyRating) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT product_family_key IF NOT EXISTS FOR (n:ProductFamily) REQUIRE n.family_key IS UNIQUE",
            "CREATE CONSTRAINT catalog_feed_run_id IF NOT EXISTS FOR (n:CatalogFeedRun) REQUIRE n.run_id IS UNIQUE",
            "CREATE CONSTRAINT canonical_import_run_id IF NOT EXISTS "
            "FOR (n:CanonicalImportRun) REQUIRE n.run_id IS UNIQUE",
            "CREATE CONSTRAINT staged_canonical_record_id IF NOT EXISTS "
            "FOR (n:StagedCanonicalRecord) REQUIRE n.staged_id IS UNIQUE",
            "CREATE CONSTRAINT canonical_source_name IF NOT EXISTS FOR (n:CanonicalSource) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT canonical_evidence_id IF NOT EXISTS FOR (n:CanonicalEvidence) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT community_evidence_id IF NOT EXISTS FOR (n:CommunityEvidence) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT founder_approval_state_id IF NOT EXISTS "
            "FOR (n:FounderApprovalState) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT vendor_id IF NOT EXISTS FOR (n:Vendor) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT price_snapshot_id IF NOT EXISTS "
            "FOR (n:PriceSnapshot) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT regional_price_snapshot_id IF NOT EXISTS "
            "FOR (n:RegionalPriceSnapshot) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT pricing_job_id IF NOT EXISTS "
            "FOR (n:PricingJob) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT product_url_normalized IF NOT EXISTS "
            "FOR (n:ProductURL) REQUIRE n.normalized_url IS UNIQUE",
            "CREATE CONSTRAINT hardware_intelligence_id IF NOT EXISTS "
            "FOR (n:HardwareIntelligence) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT spec_audit_run_id IF NOT EXISTS "
            "FOR (n:SpecAuditRun) REQUIRE n.audit_id IS UNIQUE",
            "CREATE CONSTRAINT spec_audit_item_id IF NOT EXISTS "
            "FOR (n:SpecAuditItem) REQUIRE n.id IS UNIQUE",
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
            "CREATE INDEX regional_price_snapshot_region IF NOT EXISTS "
            "FOR (n:RegionalPriceSnapshot) ON (n.region)",
            "CREATE INDEX product_url_region IF NOT EXISTS "
            "FOR (n:ProductURL) ON (n.region, n.category)",
            "CREATE INDEX canonical_evidence_source IF NOT EXISTS "
            "FOR (n:CanonicalEvidence) ON (n.source_name, n.evidence_type)",
            "CREATE INDEX staged_canonical_record_lookup IF NOT EXISTS "
            "FOR (n:StagedCanonicalRecord) ON (n.source_name, n.source_type, n.category)",
            "CREATE INDEX hardware_intelligence_generated_at IF NOT EXISTS "
            "FOR (n:HardwareIntelligence) ON (n.generated_at)",
            "CREATE INDEX spec_audit_run_created_at IF NOT EXISTS "
            "FOR (n:SpecAuditRun) ON (n.created_at)",
            "CREATE INDEX spec_audit_item_lookup IF NOT EXISTS "
            "FOR (n:SpecAuditItem) ON (n.audit_id, n.status, n.category)",
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
                SET p:Product:CanonicalProduct
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
                MERGE (p:Product:CanonicalProduct {canonical_key: $canonical_key})
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
            CREATE (snapshot:PriceSnapshot:RegionalPriceSnapshot)
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
                MERGE (p:Product:CanonicalProduct {canonical_key: $canonical_key})
                ON CREATE SET p.id = $product_id,
                              p.created_at = datetime()
                SET p:CPU:CanonicalProduct,
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
                    MERGE (p:Product:CanonicalProduct {{canonical_key: $canonical_key}})
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

    def stage_canonical_import(self, request: CanonicalImportStageRequest) -> CanonicalImportStageResponse:
        if (request.source_name, request.source_type) not in APPROVED_CANONICAL_IMPORT_SOURCES:
            raise ValueError("unsupported canonical source")
        dataset_path = _resolve_import_dataset_path(request.dataset_path)
        if request.adapter == "pc_part_dataset":
            rows = load_pc_part_dataset_records(dataset_path, request.category, None)
        elif request.adapter is not None:
            raise ValueError("unsupported canonical import adapter")
        else:
            rows = _load_canonical_dataset_file(dataset_path, request.batch_limit)
        run_id = f"canonical-stage-{uuid4()}"
        staged = 0
        rejected = 0
        duplicate_candidates = 0
        conflict_candidates = 0
        categories: set[str] = set()
        rejection_reasons: list[str] = []
        warning_reasons: list[str] = []
        seen_keys: set[str] = set()
        prepared_records: list[dict[str, Any]] = []
        deferred = 0
        near_match_count = 0
        accepted_current_gen_count = 0
        accepted_value_fallback_count = 0

        candidate_records: list[dict[str, Any]] = []
        for raw in rows:
            record = _normalize_canonical_stage_record(raw, request.category, request.license_note)
            record["source_name"] = request.source_name
            record["source_type"] = request.source_type
            record["stage_run_id"] = run_id
            target_match = annotate_expansion_target(record, request.category)
            record["near_match_count"] = near_expansion_target_count(record, request.category) if target_match is None else 0
            categories.add(str(record.get("category") or request.category))
            candidate_records.append(record)

        if request.adapter == "pc_part_dataset" and request.category in manifest_categories():
            candidate_records = sorted(candidate_records, key=_stage_preselection_sort_key)[: request.batch_limit]

        for record in candidate_records:
            target_match = match_expansion_target(record, request.category)
            reasons = self._stage_record_rejection_reasons(record, request)
            if target_match is not None and "low_identity_confidence" in reasons:
                # A curated manifest match is enough to stage a metadata-only
                # candidate for enrichment review, but not enough to commit it.
                reasons = [reason for reason in reasons if reason != "low_identity_confidence"]
            if request.category in manifest_categories() and target_match is None:
                if int(record.get("near_match_count") or 0) > 0:
                    reasons.append("target_alias_missing")
                    near_match_count += 1
                else:
                    reasons.append("outside_manifest")
            if (
                request.target_priority_tier
                and target_match is not None
                and target_match.priority_tier != request.target_priority_tier
            ):
                reasons.append("outside_manifest")
            warnings = self._stage_record_warning_reasons(record, request)
            canonical_key = str(record.get("canonical_key") or "")
            duplicates = []
            if canonical_key in seen_keys:
                duplicates.append(canonical_key)
            if canonical_key and self._staged_duplicate_count(canonical_key, request) > 0:
                duplicates.append(canonical_key)
            conflict_fields: list[str] = []
            existing = self._canonical_product_by_key(canonical_key) if canonical_key else None
            if existing:
                row = _catalog_row_from_staged_record(record, request.category)
                props = _catalog_product_properties(row, request.category, request.source_name)
                props["canonical_key"] = canonical_key
                conflict_fields = _canonical_conflict_fields(dict(existing.get("properties") or {}), props)
            if duplicates:
                duplicate_candidates += 1
                warnings.append("duplicate_candidate")
            if conflict_fields:
                conflict_candidates += 1
                warnings.append("conflict_candidate")
            seen_keys.add(canonical_key)

            deferred_missing_specs = (
                target_match is not None
                and not reasons
                and not bool(record.get("required_specs_present"))
                and not (request.category == "GPU" and _gpu_family_ready(_extract_staged_specs(record)))
            )
            if deferred_missing_specs:
                warnings.append("missing_required_specs")
            record["validation_status"] = "deferred" if deferred_missing_specs else "valid" if not reasons else "rejected"
            record["rejected_reasons"] = reasons
            record["warning_reasons"] = warnings
            record["duplicate_candidates"] = list(dict.fromkeys(duplicates))
            record["conflict_candidates"] = conflict_fields
            record["staged_id"] = f"staged:{request.source_name}:{request.category}:{canonical_key or uuid4()}"
            prepared_records.append(record)

            if reasons:
                rejected += 1
                rejection_reasons.extend(reasons)
            elif deferred_missing_specs:
                deferred += 1
                warning_reasons.append("missing_required_specs")
            else:
                staged += 1
                if target_match and target_match.priority_tier == "current_gen_priority":
                    accepted_current_gen_count += 1
                if target_match and target_match.priority_tier == "value_fallback":
                    accepted_value_fallback_count += 1
            warning_reasons.extend(warnings)

        if not request.dry_run:
            self._record_canonical_stage_run(
                run_id=run_id,
                request=request,
                status="running",
                staged=0,
                rejected=0,
                duplicate_candidates=0,
                conflict_candidates=0,
                warning_summary=None,
                finished=False,
            )
            for record in prepared_records:
                self._upsert_staged_canonical_record(record)
            top_warnings = _count_reasons(warning_reasons)
            self._record_canonical_stage_run(
                run_id=run_id,
                request=request,
                status="completed",
                staged=staged,
                rejected=rejected,
                duplicate_candidates=duplicate_candidates,
                conflict_candidates=conflict_candidates,
                warning_summary="; ".join(item.reason for item in top_warnings[:3]) if top_warnings else None,
                finished=True,
            )

        return CanonicalImportStageResponse(
            run_id=run_id,
            source_name=request.source_name,
            source_type=request.source_type,
            category=request.category,
            dataset_path=request.dataset_path,
            dry_run=request.dry_run,
            status="dry_run" if request.dry_run else "completed",
            total_records_seen=len(rows),
            staged_records=staged,
            rejected_records=rejected,
            true_rejected_count=rejected,
            deferred_records=deferred,
            near_match_count=near_match_count,
            accepted_current_gen_count=accepted_current_gen_count,
            accepted_value_fallback_count=accepted_value_fallback_count,
            duplicate_candidates=duplicate_candidates,
            conflict_candidates=conflict_candidates,
            categories=sorted(categories),
            top_rejection_reasons=_count_reasons(rejection_reasons),
            top_warning_reasons=_count_reasons(warning_reasons),
            recommended_next_action=self._stage_recommended_next_action(staged, rejected, conflict_candidates),
        )

    def commit_canonical_import(
        self,
        request: CanonicalImportCommitRequest,
        *,
        region: str = "SA",
    ) -> CanonicalImportCommitResponse:
        region = normalize_region(region)
        run_id = f"canonical-import-{uuid4()}"
        warnings: list[str] = []
        conflicts: list[CanonicalImportConflictView] = []
        imported = 0
        updated = 0
        skipped = 0
        approvals_created = 0
        duplicate_risk = 0

        if (request.source_name, request.source_type) not in APPROVED_CANONICAL_IMPORT_SOURCES:
            warnings.append("Source is not approved for controlled canonical import.")
            integrity = self.hybrid_graph_integrity(region=region)
            return CanonicalImportCommitResponse(
                run_id=run_id,
                source_name=request.source_name,
                source_type=request.source_type,
                category=request.category,
                commit=request.commit,
                batch_limit=request.batch_limit,
                status="blocked",
                imported_count=0,
                updated_count=0,
                skipped_count=0,
                conflict_count=0,
                approvals_created=0,
                duplicate_risk=0,
                categories_improved=[],
                graph_integrity_status=self._overall_integrity_status(integrity),
                conflicts=[],
                warnings=warnings,
            )

        staged_records = self._staged_canonical_records(request)
        if not staged_records:
            warnings.append("No staged canonical records matched this controlled import request.")
        canonical_keys = [str(record.get("canonical_key") or "") for record in staged_records if record.get("canonical_key")]
        duplicate_risk = len(canonical_keys) - len(set(canonical_keys))

        if request.commit:
            self._record_canonical_import_run(
                run_id=run_id,
                request=request,
                status="running",
                imported=0,
                updated=0,
                skipped=0,
                conflicts=0,
                approvals=0,
                warnings=warnings,
                finished=False,
            )

        for staged in staged_records:
            try:
                row = _catalog_row_from_staged_record(staged, request.category)
            except Exception:
                skipped += 1
                warnings.append("Skipped one staged record because it could not be parsed safely.")
                continue

            skip_reason = _canonical_import_skip_reason(record=staged, row=row, request=request)
            if skip_reason:
                skipped += 1
                warnings.append(f"Skipped {row.name}: {skip_reason}.")
                if request.commit:
                    self._mark_staged_canonical_record(staged, "skipped", skip_reason)
                continue

            canonical_key = str(row.canonical_key)
            props = _catalog_product_properties(row, request.category, request.source_name)
            if request.category == "GPU":
                exact_ready = bool(staged.get("compatibility_ready_exact")) or _gpu_exact_ready(row.specs)
                family_ready = bool(staged.get("compatibility_ready_family")) or _gpu_family_ready(row.specs)
                readiness_state = "compatibility_ready_exact" if exact_ready else "compatibility_ready_family" if family_ready else "metadata_only"
                props.update(
                    _clean_properties(
                        {
                            "compatibility_ready": exact_ready,
                            "compatibility_ready_exact": exact_ready,
                            "compatibility_ready_family": family_ready,
                            "readiness_state": readiness_state,
                            "missing_exact_card_fields": _gpu_exact_missing_fields(row.specs),
                            "card_dimension_missing": row.specs.get("length_mm") in (None, "", []),
                            "spec_reference_tdp_w": row.specs.get("reference_tdp_w"),
                            "spec_board_power_w": row.specs.get("board_power_w"),
                            "spec_chip_family": row.specs.get("chip_family"),
                        }
                    )
                )
            props.update(
                _clean_properties(
                    {
                        "canonical_key": canonical_key,
                        "data_origin": "canonical_import",
                        "spec_source_type": request.source_type,
                        "spec_license_note": staged.get("license_note"),
                        "identity_confidence": staged.get("identity_confidence"),
                        "expansion_phase": staged.get("expansion_phase"),
                        "target_family_key": staged.get("target_family_key"),
                        "target_family_name": staged.get("target_family_name"),
                        "expansion_priority": staged.get("expansion_priority"),
                    }
                )
            )
            existing = self._canonical_product_by_key(canonical_key)
            conflict_fields = _canonical_conflict_fields(existing.get("properties", {}) if existing else {}, props)
            if existing and conflict_fields and request.approval_required_for_conflicts:
                evidence_id = approval_id = None
                if request.commit:
                    evidence_id, approval_id = self._create_canonical_conflict_approval(
                        product_id=str(existing["id"]),
                        request=request,
                        canonical_key=canonical_key,
                        incoming_name=row.name,
                        conflict_fields=conflict_fields,
                        incoming_properties=props,
                        existing_properties=dict(existing.get("properties") or {}),
                    )
                    self._mark_staged_canonical_record(staged, "conflict", ",".join(conflict_fields))
                    approvals_created += 1
                conflicts.append(
                    CanonicalImportConflictView(
                        canonical_key=canonical_key,
                        incoming_name=row.name,
                        existing_product_id=str(existing["id"]),
                        conflict_fields=conflict_fields,
                        evidence_id=evidence_id,
                        approval_id=approval_id,
                    )
                )
                continue

            if not request.commit:
                continue

            product_id, created = self._upsert_canonical_product_from_import(
                canonical_key=canonical_key,
                category=request.category,
                properties=props,
            )
            if created:
                imported += 1
            else:
                updated += 1
            self._apply_catalog_shape(
                product_id=product_id,
                category=request.category,
                brand=row.brand or _brand_from_name(row.name),
                specs=row.specs,
            )
            self._upsert_product_family(product_id, request.category, row.specs, canonical_key)
            self._attach_import_canonical_evidence(
                product_id=product_id,
                request=request,
                field="canonical_record",
                value={"canonical_key": canonical_key, "name": row.name, "specs": row.specs},
                trust_score=float(staged.get("identity_confidence") or CANONICAL_IDENTITY_CONFIDENCE_MIN),
                approval_state="approved",
                note=str(staged.get("license_note") or ""),
            )
            confirmed_source_name = str(staged.get("confirmed_spec_source_name") or "").strip()
            if confirmed_source_name:
                self._attach_confirmed_spec_evidence(
                    canonical_key=canonical_key,
                    category=request.category,
                    source_name=confirmed_source_name,
                    license_note=str(staged.get("confirmed_spec_license_note") or staged.get("license_note") or ""),
                    evidence_note=str(staged.get("confirmed_spec_note") or "confirmed compatibility specs"),
                    specs=row.specs,
                )
            self._mark_staged_canonical_record(staged, "imported", None)

        status = "preview" if not request.commit else "completed"
        if request.commit and conflicts:
            status = "completed_with_conflicts"
        if request.commit:
            self._record_canonical_import_run(
                run_id=run_id,
                request=request,
                status=status,
                imported=imported,
                updated=updated,
                skipped=skipped,
                conflicts=len(conflicts),
                approvals=approvals_created,
                warnings=warnings,
                finished=True,
            )
        integrity = self.hybrid_graph_integrity(region=region)
        return CanonicalImportCommitResponse(
            run_id=run_id,
            source_name=request.source_name,
            source_type=request.source_type,
            category=request.category,
            commit=request.commit,
            batch_limit=request.batch_limit,
            status=status,
            imported_count=imported,
            updated_count=updated,
            skipped_count=skipped,
            conflict_count=len(conflicts),
            approvals_created=approvals_created,
            duplicate_risk=max(0, duplicate_risk),
            categories_improved=[request.category] if request.commit and (imported or updated) else [],
            graph_integrity_status=self._overall_integrity_status(integrity),
            conflicts=conflicts,
            warnings=list(dict.fromkeys(warnings))[:25],
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

    def _stage_record_rejection_reasons(
        self,
        record: dict[str, Any],
        request: CanonicalImportStageRequest,
    ) -> list[str]:
        reasons: list[str] = []
        if not str(request.license_note or "").strip():
            reasons.append("missing license/usage note")
        if not str(record.get("raw_name") or record.get("name") or "").strip():
            reasons.append("missing product name")
        if not str(record.get("canonical_key") or "").strip():
            reasons.append("missing canonical key")
        if record.get("category") != request.category:
            reasons.append("category mismatch")
        if float(record.get("identity_confidence") or 0) < CANONICAL_IDENTITY_CONFIDENCE_MIN:
            reasons.append("low_identity_confidence")
        specs = _extract_staged_specs(record)
        inferred_names = _staged_inferred_field_names(record.get("inferred_fields"))
        family_ready_gpu = (
            record.get("category") == "GPU"
            and _gpu_family_ready(specs)
            and not inferred_names.intersection({"reference_tdp_w", "pcie_generation"})
        )
        if not bool(record.get("required_specs_present")) and request.adapter != "pc_part_dataset" and not family_ready_gpu:
            reasons.append("missing_required_specs")
        bundle_reason = _component_bundle_rejection(str(record.get("raw_name") or record.get("name") or ""))
        if bundle_reason:
            reasons.append(bundle_reason)
        return reasons

    def _stage_record_warning_reasons(
        self,
        record: dict[str, Any],
        request: CanonicalImportStageRequest,
    ) -> list[str]:
        specs = _extract_staged_specs(record)
        warnings: list[str] = []
        warnings.extend(str(reason) for reason in record.get("warning_reasons") or [])
        for field in record.get("missing_compatibility_fields") or []:
            warnings.append(f"missing compatibility field: {field}")
        if record.get("compatibility_ready") is False:
            warnings.append("metadata-only record is not compatibility-ready")
        if record.get("inferred_fields"):
            warnings.append("one or more compatibility fields are inferred")
        optional_fields = {
            "CPU": ("tdp_w", "base_clock_ghz", "boost_clock_ghz"),
            "GPU": ("vram_gb", "pcie_generation", "reference_tdp_w", "board_power_w", "length_mm", "slots", "power_connectors"),
            "Motherboard": ("m2_slots", "pcie_x16_slots"),
            "RAM": ("speed_mhz", "kit_config", "cas_latency"),
            "Storage": ("form_factor", "protocol"),
            "PSU": ("modularity",),
            "Case": ("max_gpu_length_mm", "max_cpu_cooler_height_mm"),
            "Cooler": ("socket_support",),
        }.get(request.category, ())
        for field in optional_fields:
            if specs.get(field) in (None, "", []):
                warnings.append(f"optional {field} missing")
        return warnings

    def _staged_duplicate_count(self, canonical_key: str, request: CanonicalImportStageRequest) -> int:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord {canonical_key: $canonical_key})
            WHERE record.source_name = $source_name
              AND record.source_type = $source_type
              AND record.category = $category
            RETURN count(record) AS count
            """,
            canonical_key=canonical_key,
            source_name=request.source_name,
            source_type=request.source_type,
            category=request.category,
            database_=settings.neo4j_database,
        )
        return int(records[0]["count"] or 0) if records else 0

    def _upsert_staged_canonical_record(self, record: dict[str, Any]) -> None:
        properties = _clean_properties(record)
        canonical_key = str(record.get("canonical_key") or "").strip()
        if canonical_key:
            canonical_properties = dict(properties)
            canonical_properties.pop("staged_id", None)
            self.driver.execute_query(
                """
                MERGE (record:StagedCanonicalRecord {canonical_key: $canonical_key})
                ON CREATE SET record.created_at = datetime()
                SET record += $properties,
                    record.staged_id = coalesce(record.staged_id, $staged_id),
                    record.updated_at = datetime(),
                    record.import_status = "pending"
                """,
                canonical_key=canonical_key,
                staged_id=str(record["staged_id"]),
                properties=canonical_properties,
                database_=settings.neo4j_database,
            )
            return
        self.driver.execute_query(
            """
            MERGE (record:StagedCanonicalRecord {staged_id: $staged_id})
            ON CREATE SET record.created_at = datetime()
            SET record += $properties,
                record.updated_at = datetime(),
                record.import_status = "pending"
            """,
            staged_id=str(record["staged_id"]),
            properties=properties,
            database_=settings.neo4j_database,
        )

    def _record_canonical_stage_run(
        self,
        *,
        run_id: str,
        request: CanonicalImportStageRequest,
        status: str,
        staged: int,
        rejected: int,
        duplicate_candidates: int,
        conflict_candidates: int,
        warning_summary: str | None,
        finished: bool,
    ) -> None:
        try:
            self.driver.execute_query(
                """
                MERGE (run:CanonicalStageRun {run_id: $run_id})
                ON CREATE SET run.started_at = datetime()
                SET run.source_name = $source_name,
                    run.source_type = $source_type,
                    run.category = $category,
                    run.dataset_path = $dataset_path,
                    run.dry_run = $dry_run,
                    run.status = $status,
                    run.staged_records = $staged,
                    run.rejected_records = $rejected,
                    run.duplicate_candidates = $duplicate_candidates,
                    run.conflict_candidates = $conflict_candidates,
                    run.warning_summary = $warning_summary,
                    run.finished_at = CASE WHEN $finished THEN datetime() ELSE run.finished_at END
                """,
                run_id=run_id,
                source_name=request.source_name,
                source_type=request.source_type,
                category=request.category,
                dataset_path=request.dataset_path,
                dry_run=request.dry_run,
                status=status,
                staged=staged,
                rejected=rejected,
                duplicate_candidates=duplicate_candidates,
                conflict_candidates=conflict_candidates,
                warning_summary=warning_summary,
                finished=finished,
                database_=settings.neo4j_database,
            )
        except Exception as error:  # noqa: BLE001 - audit/run summaries must not block staging.
            logger.warning(
                "canonical_stage_run_record_failed",
                extra={"run_id": run_id, "error_type": type(error).__name__},
            )

    def _stage_recommended_next_action(self, staged: int, rejected: int, conflicts: int) -> str:
        if staged == 0 and rejected > 0:
            return "Fix rejected dataset rows, then run staging again before commit."
        if conflicts:
            return "Review conflict candidates; clean records can be committed, conflicts require founder approval."
        if staged:
            return "Run /catalog/import/commit for this source/category to import clean staged records."
        return "No staged records were created. Check dataset path, source, category, and required specs."

    def _staged_canonical_records(self, request: CanonicalImportCommitRequest) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord)
            WHERE record.source_name = $source_name
              AND record.source_type = $source_type
              AND record.category = $category
              AND coalesce(record.import_status, "pending") <> "imported"
              AND record.validation_status = "valid"
            RETURN properties(record) AS record
            ORDER BY coalesce(record.created_at, datetime("1970-01-01T00:00:00Z")) ASC,
                     record.canonical_key ASC
            LIMIT $limit
            """,
            source_name=request.source_name,
            source_type=request.source_type,
            category=request.category,
            limit=request.batch_limit,
            database_=settings.neo4j_database,
        )
        return [dict(record.data().get("record") or {}) for record in records]

    def _canonical_product_by_key(self, canonical_key: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p:Product {canonical_key: $canonical_key})
            RETURN p.id AS id, properties(p) AS properties
            LIMIT 1
            """,
            canonical_key=canonical_key,
            database_=settings.neo4j_database,
        )
        if not records:
            return None
        data = records[0].data()
        return {"id": data.get("id"), "properties": dict(data.get("properties") or {})}

    def _upsert_canonical_product_from_import(
        self,
        *,
        canonical_key: str,
        category: str,
        properties: dict[str, Any],
    ) -> tuple[str, bool]:
        label = _category_label(category)
        records, _, _ = self.driver.execute_query(
            f"""
            MERGE (p:Product:CanonicalProduct {{canonical_key: $canonical_key}})
            ON CREATE SET p.id = $product_id,
                          p.created_at = datetime(),
                          p._canonical_import_created = true
            ON MATCH SET p._canonical_import_created = false
            SET p:{label},
                p += $properties,
                p.updated_at = datetime()
            WITH p, coalesce(p._canonical_import_created, false) AS created
            REMOVE p._canonical_import_created
            RETURN p.id AS id, created
            """,
            canonical_key=canonical_key,
            product_id=f"canonical:{canonical_key}",
            properties=properties,
            database_=settings.neo4j_database,
        )
        data = records[0].data()
        return str(data["id"]), bool(data["created"])

    def _attach_import_canonical_evidence(
        self,
        *,
        product_id: str,
        request: CanonicalImportCommitRequest,
        field: str,
        value: Any,
        trust_score: float,
        approval_state: str,
        note: str | None,
    ) -> tuple[str, str]:
        evidence_id = f"evidence:{uuid4()}"
        approval_id = f"approval:{evidence_id}"
        self.driver.execute_query(
            """
            MATCH (p:Product {id: $product_id})
            MERGE (source:CanonicalSource {name: $source_name})
            SET source.source_type = $source_type,
                source.updated_at = datetime()
            CREATE (e:CanonicalEvidence)
            SET e.id = $evidence_id,
                e.source_name = $source_name,
                e.source_type = $source_type,
                e.evidence_type = "canonical_spec",
                e.field = $field,
                e.value_json = $value_json,
                e.trust_score = $trust_score,
                e.note = $note,
                e.created_at = datetime()
            MERGE (p)-[:HAS_CANONICAL_EVIDENCE]->(e)
            MERGE (e)-[:FROM_SOURCE]->(source)
            MERGE (approval:FounderApprovalState {id: $approval_id})
            SET approval.status = $approval_state,
                approval.source_name = $source_name,
                approval.updated_at = datetime()
            MERGE (e)-[:HAS_APPROVAL_STATE]->(approval)
            """,
            product_id=product_id,
            source_name=request.source_name,
            source_type=request.source_type,
            evidence_id=evidence_id,
            field=field,
            value_json=json.dumps(value, sort_keys=True, default=str),
            trust_score=min(max(trust_score, 0), 1),
            note=note,
            approval_id=approval_id,
            approval_state=approval_state,
            database_=settings.neo4j_database,
        )
        return evidence_id, approval_id

    def _create_canonical_conflict_approval(
        self,
        *,
        product_id: str,
        request: CanonicalImportCommitRequest,
        canonical_key: str,
        incoming_name: str,
        conflict_fields: list[str],
        incoming_properties: dict[str, Any],
        existing_properties: dict[str, Any],
    ) -> tuple[str, str]:
        return self._attach_import_canonical_evidence(
            product_id=product_id,
            request=request,
            field="canonical_conflict",
            value={
                "canonical_key": canonical_key,
                "incoming_name": incoming_name,
                "conflict_fields": conflict_fields,
                "incoming": {field: incoming_properties.get(field) for field in conflict_fields},
                "existing": {field: existing_properties.get(field) for field in conflict_fields},
            },
            trust_score=0.5,
            approval_state="pending_review",
            note="Canonical import conflict requires founder approval before merge.",
        )

    def _mark_staged_canonical_record(
        self,
        record: dict[str, Any],
        status: str,
        sanitized_error: str | None,
    ) -> None:
        canonical_key = record.get("canonical_key")
        if not canonical_key:
            return
        self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord {canonical_key: $canonical_key})
            WHERE record.source_name = $source_name
              AND record.source_type = $source_type
              AND record.category = $category
            SET record.import_status = $status,
                record.last_import_attempt_at = datetime(),
                record.last_error_sanitized = $sanitized_error
            """,
            canonical_key=canonical_key,
            source_name=record.get("source_name"),
            source_type=record.get("source_type"),
            category=record.get("category"),
            status=status,
            sanitized_error=sanitized_error,
            database_=settings.neo4j_database,
        )

    def _record_canonical_import_run(
        self,
        *,
        run_id: str,
        request: CanonicalImportCommitRequest,
        status: str,
        imported: int,
        updated: int,
        skipped: int,
        conflicts: int,
        approvals: int,
        warnings: list[str],
        finished: bool,
    ) -> None:
        self.driver.execute_query(
            """
            MERGE (run:CanonicalImportRun {run_id: $run_id})
            ON CREATE SET run.started_at = datetime()
            SET run.source_name = $source_name,
                run.source_type = $source_type,
                run.category = $category,
                run.commit = $commit,
                run.batch_limit = $batch_limit,
                run.status = $status,
                run.imported_count = $imported,
                run.updated_count = $updated,
                run.skipped_count = $skipped,
                run.conflict_count = $conflicts,
                run.approvals_created = $approvals,
                run.warning_summary = $warning_summary,
                run.finished_at = CASE WHEN $finished THEN datetime() ELSE run.finished_at END
            """,
            run_id=run_id,
            source_name=request.source_name,
            source_type=request.source_type,
            category=request.category,
            commit=request.commit,
            batch_limit=request.batch_limit,
            status=status,
            imported=imported,
            updated=updated,
            skipped=skipped,
            conflicts=conflicts,
            approvals=approvals,
            warning_summary="; ".join(warnings[:5]) if warnings else None,
            finished=finished,
            database_=settings.neo4j_database,
        )

    def staged_canonical_import_summary(
        self,
        *,
        source_name: str | None = None,
        category: str | None = None,
    ) -> CanonicalStagedSummaryResponse:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord)
            WHERE ($source_name IS NULL OR record.source_name = $source_name)
              AND ($category IS NULL OR record.category = $category)
            WITH collect(record) AS records,
                 collect(DISTINCT record.category) AS category_values,
                 collect(DISTINCT record.source_type) AS source_type_values
            RETURN size(records) AS staged_count,
                   size([item IN records WHERE item.validation_status = "valid"]) AS valid_count,
                   size([item IN records WHERE item.validation_status <> "valid"]) AS invalid_count,
                   size([item IN records WHERE size(coalesce(item.duplicate_candidates, [])) > 0]) AS duplicate_candidate_count,
                   size([item IN records WHERE size(coalesce(item.conflict_candidates, [])) > 0]) AS conflict_candidate_count,
                   [category IN category_values WHERE category IS NOT NULL] AS categories,
                   [source_type IN source_type_values WHERE source_type IS NOT NULL][0] AS source_type
            """,
            source_name=source_name,
            category=category,
            database_=settings.neo4j_database,
        )
        data = records[0].data() if records else {}
        valid_count = int(data.get("valid_count") or 0)
        conflict_count = int(data.get("conflict_candidate_count") or 0)
        if valid_count == 0:
            readiness = "not_ready"
        elif conflict_count:
            readiness = "ready_with_conflicts"
        else:
            readiness = "ready_for_commit"
        return CanonicalStagedSummaryResponse(
            source_name=source_name,
            source_type=data.get("source_type"),
            category=category,
            staged_count=int(data.get("staged_count") or 0),
            valid_count=valid_count,
            invalid_count=int(data.get("invalid_count") or 0),
            duplicate_candidate_count=int(data.get("duplicate_candidate_count") or 0),
            conflict_candidate_count=conflict_count,
            categories=[str(item) for item in data.get("categories") or []],
            readiness_for_commit=readiness,
        )

    def hybrid_import_review(
        self,
        *,
        source_name: str,
        category: str,
        region: str = "SA",
    ) -> HybridImportReviewResponse:
        region = normalize_region(region)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord)
            WHERE record.source_name = $source_name
              AND record.category = $category
            OPTIONAL MATCH (market:Product)
            WHERE market.canonical_key = record.canonical_key
               OR (
                    market.category = record.category
                    AND toLower(coalesce(market.brand, "")) = toLower(coalesce(record.brand, ""))
                    AND toLower(coalesce(market.model, "")) = toLower(coalesce(record.model, ""))
                    AND coalesce(record.model, "") <> ""
                  )
            OPTIONAL MATCH (market)-[:HAS_PRICE]->(snapshot:PriceSnapshot)-[:FROM_VENDOR]->(vendor:Vendor)
            WHERE snapshot.region = $region AND snapshot.currency = "SAR"
            WITH record, market, snapshot, vendor
            ORDER BY coalesce(snapshot.price, 999999999) ASC
            WITH record,
                 collect(DISTINCT market.id) AS market_ids,
                 count(DISTINCT snapshot) AS price_snapshot_count,
                 collect(
                   CASE
                     WHEN snapshot IS NULL THEN NULL
                     ELSE {
                       price: snapshot.price,
                       item_price_sar: snapshot.item_price_sar,
                       final_landed_price_sar: snapshot.final_landed_price_sar,
                       vendor_name: vendor.name
                     }
                   END
                 ) AS price_rows
            RETURN properties(record) AS record,
                   [id IN market_ids WHERE id IS NOT NULL][0] AS market_product_id,
                   price_snapshot_count,
                   [row IN price_rows WHERE row IS NOT NULL][0] AS cheapest
            ORDER BY coalesce(record.created_at, datetime("1970-01-01T00:00:00Z")) ASC,
                     record.canonical_key ASC
            LIMIT 250
            """,
            source_name=source_name,
            category=category,
            region=region,
            database_=settings.neo4j_database,
        )

        items: list[HybridImportReviewItem] = []
        missing_fields: list[str] = []
        missing_exact_card_fields: list[str] = []
        inferred_fields: list[str] = []
        classification_counts: dict[str, int] = {}
        for row in records:
            data = row.data()
            record = dict(data.get("record") or {})
            specs = _extract_staged_specs(record)
            missing = _staged_string_list(record.get("missing_compatibility_fields"))
            exact_missing = _staged_string_list(record.get("missing_exact_card_fields"))
            if category == "GPU":
                exact_missing = _gpu_exact_missing_fields(specs)
            inferred = _staged_string_list(record.get("inferred_fields"))
            inferred_field_names = _staged_inferred_field_names(record.get("inferred_fields"))
            conflicts = _staged_string_list(record.get("conflict_candidates"))
            duplicates = _staged_string_list(record.get("duplicate_candidates"))
            rejected = _staged_string_list(record.get("rejected_reasons"))
            warnings = _staged_string_list(record.get("warning_reasons"))
            exact_ready = bool(record.get("compatibility_ready_exact"))
            family_ready = bool(record.get("compatibility_ready_family"))
            if category == "GPU":
                exact_ready = exact_ready or _gpu_exact_ready(specs)
                family_ready = family_ready or _gpu_family_ready(specs)
                if inferred_field_names.intersection({"tdp_w", "board_power_w", "pcie_generation", "reference_tdp_w"}):
                    exact_ready = False
                    family_ready = False
            else:
                exact_ready = bool(record.get("compatibility_ready"))
            compatibility_ready = exact_ready or family_ready
            readiness_state = (
                "compatibility_ready_exact"
                if exact_ready
                else "compatibility_ready_family"
                if family_ready
                else "metadata_only"
            )
            market_linked = bool(data.get("market_product_id")) and int(data.get("price_snapshot_count") or 0) > 0
            cheapest = data.get("cheapest") or {}
            cheapest_price = (
                cheapest.get("final_landed_price_sar")
                or cheapest.get("item_price_sar")
                or cheapest.get("price")
            )

            validation_status = str(record.get("validation_status") or "")
            if validation_status == "deferred" and not rejected:
                classification = "metadata_only_needs_enrichment"
                commit_eligible = False
            elif validation_status != "valid" or rejected:
                classification = "reject"
                commit_eligible = False
            elif conflicts:
                classification = "conflict_requires_founder_review"
                commit_eligible = False
                readiness_state = "conflict_requires_review"
            elif not compatibility_ready:
                classification = "metadata_only_needs_enrichment"
                commit_eligible = False
            elif market_linked:
                classification = "canonical_ready_and_market_linked"
                commit_eligible = True
            else:
                classification = "canonical_ready_no_saudi_price"
                commit_eligible = True

            missing_fields.extend(missing)
            missing_exact_card_fields.extend(exact_missing)
            inferred_fields.extend(inferred)
            classification_counts[classification] = classification_counts.get(classification, 0) + 1
            items.append(
                HybridImportReviewItem(
                    staged_id=record.get("staged_id"),
                    raw_name=str(record.get("raw_name") or record.get("name") or ""),
                    normalized_name=record.get("normalized_name") or record.get("name"),
                    canonical_key=record.get("canonical_key"),
                    category=str(record.get("category") or category),
                    classification=classification,
                    identity_confidence=_optional_float(record.get("identity_confidence")),
                    compatibility_ready=compatibility_ready,
                    compatibility_ready_exact=exact_ready,
                    compatibility_ready_family=family_ready,
                    readiness_state=readiness_state,
                    market_linked=market_linked,
                    saudi_price_sar=_optional_float(cheapest_price),
                    saudi_vendor=cheapest.get("vendor_name"),
                    missing_compatibility_fields=missing,
                    missing_exact_card_fields=exact_missing,
                    inferred_fields=inferred,
                    conflict_candidates=conflicts,
                    duplicate_candidates=duplicates,
                    rejected_reasons=rejected,
                    warning_reasons=warnings,
                    target_family_key=record.get("target_family_key"),
                    target_family_name=record.get("target_family_name"),
                    expansion_priority=_optional_int(record.get("expansion_priority")),
                    commit_eligible=commit_eligible,
                    next_action=_hybrid_review_next_action(classification, missing, conflicts, market_linked),
                )
            )

        return HybridImportReviewResponse(
            source_name=source_name,
            category=category,
            region=region,
            total_staged=len(items),
            classification_counts=classification_counts,
            market_linked_count=sum(1 for item in items if item.market_linked),
            metadata_only_count=classification_counts.get("metadata_only_needs_enrichment", 0),
            conflict_count=classification_counts.get("conflict_requires_founder_review", 0),
            reject_count=classification_counts.get("reject", 0),
            exact_ready_count=sum(1 for item in items if item.compatibility_ready_exact),
            family_ready_count=sum(1 for item in items if item.compatibility_ready_family and not item.compatibility_ready_exact),
            card_dimension_missing_count=sum(1 for item in items if "length_mm" in item.missing_exact_card_fields),
            commit_eligible_count=sum(1 for item in items if item.commit_eligible),
            top_missing_compatibility_fields=_count_reasons(missing_fields),
            top_missing_exact_card_fields=_count_reasons(missing_exact_card_fields),
            top_inferred_fields=_count_reasons(inferred_fields),
            items=items[:100],
        )

    def clear_staged_canonical_import(self, *, source_name: str, category: str) -> CanonicalStagedClearResponse:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord)
            WHERE record.source_name = $source_name
              AND record.category = $category
            WITH collect(record) AS records, count(record) AS deleted_count
            FOREACH (record IN records | DETACH DELETE record)
            RETURN deleted_count
            """,
            source_name=source_name,
            category=category,
            database_=settings.neo4j_database,
        )
        deleted = int(records[0]["deleted_count"] or 0) if records else 0
        return CanonicalStagedClearResponse(
            source_name=source_name,
            category=category,
            deleted_count=deleted,
            status="cleared",
        )

    def catalog_expansion_targets(self, *, region: str = "SA") -> CatalogExpansionTargetsResponse:
        region = normalize_region(region)
        manifest = load_expansion_manifest()
        categories_config = dict(manifest.get("categories") or {})
        category_order = [str(item) for item in manifest.get("category_order") or categories_config.keys()]
        family_stats = _initial_expansion_family_stats(manifest)
        category_stats = _initial_expansion_category_stats(manifest)
        categories = list(categories_config.keys())

        try:
            product_records, _, _ = self.driver.execute_query(
                """
                MATCH (p:Product)
                WHERE (p:CanonicalProduct OR p.data_origin = "canonical_import")
                  AND (p.category IN $categories OR any(label IN labels(p) WHERE label IN $categories))
                OPTIONAL MATCH (p)-[:HAS_PRICE]->(price:PriceSnapshot)-[:FROM_VENDOR]->(vendor:Vendor)
                WHERE price.region = $region
                  AND price.currency = "SAR"
                  AND coalesce(price.accepted, true) = true
                RETURN properties(p) AS product,
                       labels(p) AS labels,
                       count(DISTINCT price) AS price_count,
                       count(DISTINCT CASE
                         WHEN price IS NOT NULL AND coalesce(price.marketplace_risk_score, 0.5) < 0.45 THEN vendor.name
                         ELSE null
                       END) AS trusted_vendor_count
                """,
                categories=categories,
                region=region,
                database_=settings.neo4j_database,
            )
        except Exception as error:  # noqa: BLE001 - target manifest should still load if live coverage is sparse.
            logger.warning("catalog_expansion_product_query_failed", extra={"error_type": type(error).__name__})
            product_records = []
        for row in product_records:
            data = row.data()
            props = dict(data.get("product") or {})
            category = _product_category_from_props(props, data.get("labels"), categories)
            if not category:
                continue
            target_key = _target_key_for_props(props, category)
            if not target_key or target_key not in family_stats:
                continue
            stats = family_stats[target_key]
            cat = category_stats[category]
            price_count = int(data.get("price_count") or 0)
            trusted_count = int(data.get("trusted_vendor_count") or 0)
            missing_specs = _product_missing_required_specs(props, tuple(stats["required_specs"]))
            compatibility_ready = bool(props.get("compatibility_ready")) or not missing_specs
            stats["canonical_count"] += 1
            stats["compatibility_ready_count"] += 1 if compatibility_ready else 0
            stats["saudi_priced_count"] += 1 if price_count > 0 else 0
            stats["trusted_vendor_count"] += trusted_count
            stats["missing_required_specs"].update(missing_specs)
            cat["canonical_count"] += 1
            cat["compatibility_ready_count"] += 1 if compatibility_ready else 0
            cat["saudi_priced_count"] += 1 if price_count > 0 else 0
            cat["trusted_vendor_count"] += trusted_count
            cat["missing_required_specs"].update(missing_specs)

        try:
            staged_records, _, _ = self.driver.execute_query(
                """
                MATCH (record:StagedCanonicalRecord)
                WHERE record.category IN $categories
                  AND coalesce(record.import_status, "pending") <> "imported"
                RETURN properties(record) AS record
                """,
                categories=categories,
                database_=settings.neo4j_database,
            )
        except Exception as error:  # noqa: BLE001 - endpoint remains useful as manifest even if staging read fails.
            logger.warning("catalog_expansion_staged_query_failed", extra={"error_type": type(error).__name__})
            staged_records = []
        for row in staged_records:
            record = dict(row.data().get("record") or {})
            category = str(record.get("category") or "")
            target_key = str(record.get("target_family_key") or "")
            if (not target_key or target_key not in family_stats) and category:
                match = match_expansion_target(record, category)
                target_key = match.family_key if match else ""
            if not target_key or target_key not in family_stats:
                continue
            stats = family_stats[target_key]
            cat = category_stats[str(stats["category"])]
            conflicts = bool(_staged_string_list(record.get("conflict_candidates")))
            metadata_only = not bool(record.get("compatibility_ready")) and not conflicts
            missing = _staged_string_list(record.get("missing_compatibility_fields"))
            stats["staged_count"] += 1
            stats["conflict_count"] += 1 if conflicts else 0
            stats["metadata_only_count"] += 1 if metadata_only else 0
            stats["missing_required_specs"].update(missing)
            cat["staged_count"] += 1
            cat["conflict_count"] += 1 if conflicts else 0
            cat["metadata_only_count"] += 1 if metadata_only else 0
            cat["missing_required_specs"].update(missing)

        category_views: list[CatalogExpansionCategorySummary] = []
        for order, category in enumerate(category_order, start=1):
            if category not in category_stats:
                continue
            cat = category_stats[category]
            family_views: list[CatalogExpansionTargetFamily] = []
            for key in cat["family_keys"]:
                stats = family_stats[key]
                state = expansion_state(
                    compatibility_ready=bool(stats["compatibility_ready_count"]),
                    metadata_only_count=int(stats["metadata_only_count"]),
                    conflict_count=int(stats["conflict_count"]),
                )
                missing = sorted(stats["missing_required_specs"])
                family_views.append(
                    CatalogExpansionTargetFamily(
                        category=category,
                        family_key=key,
                        family_name=str(stats["family_name"]),
                        priority=int(stats["priority"]),
                        priority_tier=str(stats.get("priority_tier") or "current_gen_priority"),  # type: ignore[arg-type]
                        target_min=int(cat["target_min"]),
                        target_max=int(cat["target_max"]),
                        canonical_count=int(stats["canonical_count"]),
                        compatibility_ready_count=int(stats["compatibility_ready_count"]),
                        saudi_priced_count=int(stats["saudi_priced_count"]),
                        trusted_vendor_count=int(stats["trusted_vendor_count"]),
                        staged_count=int(stats["staged_count"]),
                        metadata_only_count=int(stats["metadata_only_count"]),
                        conflict_count=int(stats["conflict_count"]),
                        missing_required_specs=missing,
                        readiness_state=state,
                        next_action=_expansion_next_action(
                            canonical_count=int(stats["canonical_count"]),
                            staged_count=int(stats["staged_count"]),
                            compatibility_ready_count=int(stats["compatibility_ready_count"]),
                            saudi_priced_count=int(stats["saudi_priced_count"]),
                            conflict_count=int(stats["conflict_count"]),
                            missing_required_specs=missing,
                            family_name=str(stats["family_name"]),
                            priority_tier=str(stats.get("priority_tier") or "current_gen_priority"),
                        ),
                    )
                )
            category_state = expansion_state(
                compatibility_ready=bool(cat["compatibility_ready_count"]),
                metadata_only_count=int(cat["metadata_only_count"]),
                conflict_count=int(cat["conflict_count"]),
            )
            category_views.append(
                CatalogExpansionCategorySummary(
                    category=category,
                    priority_order=order,
                    target_min=int(cat["target_min"]),
                    target_max=int(cat["target_max"]),
                    safe_stage_batch_size=int(cat["safe_stage_batch_size"]),
                    safe_commit_batch_size=int(cat["safe_commit_batch_size"]),
                    canonical_count=int(cat["canonical_count"]),
                    compatibility_ready_count=int(cat["compatibility_ready_count"]),
                    saudi_priced_count=int(cat["saudi_priced_count"]),
                    trusted_vendor_count=int(cat["trusted_vendor_count"]),
                    staged_count=int(cat["staged_count"]),
                    metadata_only_count=int(cat["metadata_only_count"]),
                    conflict_count=int(cat["conflict_count"]),
                    missing_required_specs=sorted(cat["missing_required_specs"]),
                    readiness_state=category_state,
                    next_action=_expansion_category_next_action(category, cat),
                    families=family_views,
                )
            )

        milestone = dict(manifest.get("milestone") or {})
        return CatalogExpansionTargetsResponse(
            region=region,
            phase=str(manifest.get("phase") or "phase2_saudi_core"),
            first_milestone_min=int(milestone.get("first_min") or 500),
            first_milestone_max=int(milestone.get("first_max") or 700),
            final_milestone_min=int(milestone.get("final_min") or 500),
            final_milestone_max=int(milestone.get("final_max") or 2000),
            total_canonical_count=sum(item.canonical_count for item in category_views),
            total_compatibility_ready_count=sum(item.compatibility_ready_count for item in category_views),
            total_saudi_priced_count=sum(item.saudi_priced_count for item in category_views),
            total_trusted_vendor_count=sum(item.trusted_vendor_count for item in category_views),
            product_states=list(CATALOG_PRODUCT_STATES),
            categories=category_views,
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
        if category == "GPU" and specs.get("chip_family"):
            self.driver.execute_query(
                """
                MATCH (p:Product {id: $product_id})
                MERGE (family:GPUFamily {family_key: $family_key})
                SET family.name = $family_name,
                    family.vram_gb = $vram_gb,
                    family.pcie_generation = $pcie_generation,
                    family.reference_tdp_w = $reference_tdp_w,
                    family.updated_at = datetime()
                MERGE (p)-[:HAS_GPU_FAMILY]->(family)
                """,
                product_id=product_id,
                family_key=str(specs.get("chip_family")).upper().replace(" ", "_"),
                family_name=str(specs.get("chip_family")),
                vram_gb=specs.get("vram_gb"),
                pcie_generation=specs.get("pcie_generation"),
                reference_tdp_w=specs.get("reference_tdp_w"),
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

    def hybrid_graph_integrity(self, *, region: str = "SA") -> HybridGraphIntegrityResponse:
        region = normalize_region(region)
        canonical_count = self._count_query("MATCH (p:CanonicalProduct) RETURN count(p) AS count")
        regional_count = self._count_query(
            "MATCH (s:RegionalPriceSnapshot) WHERE s.region = $region RETURN count(s) AS count",
            region=region,
        )
        telemetry_count = self._count_query("MATCH (e) WHERE e:TelemetryEvidence OR e:TelemetrySnapshot RETURN count(e) AS count")
        community_count = self._count_query("MATCH (e:CommunityEvidence) RETURN count(e) AS count")
        approval_count = self._count_query("MATCH (s:FounderApprovalState) RETURN count(s) AS count")
        checks = [
            self._integrity_check(
                name="regional_price_snapshots_are_region_labeled",
                count=self._count_query(
                    "MATCH (s:PriceSnapshot) WHERE s.region = $region AND NOT s:RegionalPriceSnapshot RETURN count(s) AS count",
                    region=region,
                ),
                pass_detail="Regional price snapshots carry the RegionalPriceSnapshot label.",
                fail_detail="Some regional PriceSnapshot nodes are missing the RegionalPriceSnapshot label.",
            ),
            self._integrity_check(
                name="saudi_prices_are_sar",
                count=self._count_query(
                    """
                    MATCH (s:PriceSnapshot)
                    WHERE s.region = $region AND coalesce(s.currency, s.final_landed_currency) <> "SAR"
                    RETURN count(s) AS count
                    """,
                    region=region,
                ),
                pass_detail="Saudi price snapshots use SAR currency.",
                fail_detail="Some Saudi price snapshots are not SAR and must be reviewed.",
            ),
            self._integrity_check(
                name="product_urls_map_to_products",
                count=self._count_query(
                    """
                    MATCH (url:ProductURL)
                    WHERE url.region = $region AND NOT (url)-[:FOR_PRODUCT]->(:Product)
                    RETURN count(url) AS count
                    """,
                    region=region,
                ),
                pass_detail="Known Saudi product URLs map into canonical products.",
                fail_detail="Some Saudi ProductURL nodes are orphaned and may create duplicate imports.",
            ),
            self._integrity_check(
                name="canonical_products_have_keys",
                count=self._count_query(
                    "MATCH (p:CanonicalProduct) WHERE p.canonical_key IS NULL OR p.canonical_key = '' RETURN count(p) AS count"
                ),
                pass_detail="Canonical products have stable canonical keys.",
                fail_detail="Canonical products without keys weaken duplicate control.",
            ),
        ]
        if canonical_count == 0:
            checks.append(
                HybridIntegrityCheck(
                    name="canonical_product_seed",
                    status="warn",
                    detail="No CanonicalProduct nodes exist yet; import approved specs before relying on catalog-scale filtering.",
                    count=0,
                )
            )
        return HybridGraphIntegrityResponse(
            region=region,
            canonical_product_count=canonical_count,
            regional_price_snapshot_count=regional_count,
            telemetry_evidence_count=telemetry_count,
            community_evidence_count=community_count,
            founder_approval_state_count=approval_count,
            checks=checks,
        )

    def enrich_staged_cpu_specs(self, request: ConfirmedCpuSpecEnrichmentRequest) -> ConfirmedCpuSpecEnrichmentResponse:
        items: list[ConfirmedCpuSpecEnrichmentItem] = []
        matched = 0
        enriched = 0
        skipped = 0
        evidence_created = 0

        for incoming in request.records:
            staged = self._staged_record_by_canonical_key(incoming.canonical_key)
            confirmed_fields = ["socket", "cores", "threads"]
            specs = {
                "socket": incoming.socket,
                "cores": incoming.cores,
                "threads": incoming.threads,
            }
            if incoming.tdp_w is not None:
                confirmed_fields.append("tdp_w")
                specs["tdp_w"] = incoming.tdp_w

            if not staged:
                skipped += 1
                items.append(
                    ConfirmedCpuSpecEnrichmentItem(
                        canonical_key=incoming.canonical_key,
                        status="skipped",
                        staged_record_found=False,
                        reason="staged CPU record not found",
                        confirmed_fields=confirmed_fields,
                    )
                )
                continue
            if str(staged.get("category") or "") != "CPU":
                skipped += 1
                items.append(
                    ConfirmedCpuSpecEnrichmentItem(
                        canonical_key=incoming.canonical_key,
                        status="skipped",
                        staged_record_found=True,
                        reason="staged record is not CPU category",
                        confirmed_fields=confirmed_fields,
                    )
                )
                continue

            matched += 1
            merged_specs = _extract_staged_specs(staged)
            merged_specs.update(specs)
            missing = [field for field in ("socket", "cores", "threads") if merged_specs.get(field) in (None, "", [])]
            if missing:
                skipped += 1
                items.append(
                    ConfirmedCpuSpecEnrichmentItem(
                        canonical_key=incoming.canonical_key,
                        status="skipped",
                        staged_record_found=True,
                        reason=f"confirmed evidence is missing required field(s): {', '.join(missing)}",
                        confirmed_fields=confirmed_fields,
                    )
                )
                continue

            if request.dry_run:
                items.append(
                    ConfirmedCpuSpecEnrichmentItem(
                        canonical_key=incoming.canonical_key,
                        status="would_enrich",
                        staged_record_found=True,
                        confirmed_fields=confirmed_fields,
                    )
                )
                continue

            self._apply_confirmed_cpu_specs_to_staged_record(
                canonical_key=incoming.canonical_key,
                specs=merged_specs,
                source_name=request.source_name,
                license_note=request.license_note,
                evidence_note=incoming.evidence_note,
                confirmed_fields=confirmed_fields,
            )
            attached = self._attach_confirmed_cpu_spec_evidence(
                canonical_key=incoming.canonical_key,
                source_name=request.source_name,
                license_note=request.license_note,
                evidence_note=incoming.evidence_note,
                specs=specs,
            )
            if attached:
                evidence_created += 1
            enriched += 1
            items.append(
                ConfirmedCpuSpecEnrichmentItem(
                    canonical_key=incoming.canonical_key,
                    status="enriched",
                    staged_record_found=True,
                    evidence_attached=attached,
                    confirmed_fields=confirmed_fields,
                )
            )

        return ConfirmedCpuSpecEnrichmentResponse(
            source_name=request.source_name,
            dry_run=request.dry_run,
            total_records=len(request.records),
            matched_staged_records=matched,
            enriched_records=enriched,
            skipped_records=skipped,
            evidence_created=evidence_created,
            items=items,
        )

    def enrich_staged_specs(self, request: ConfirmedSpecEnrichmentRequest) -> ConfirmedSpecEnrichmentResponse:
        items: list[ConfirmedSpecEnrichmentItem] = []
        required_fields = CONFIRMED_SPEC_REQUIRED_FIELDS.get(request.category, ())
        matched = 0
        enriched = 0
        skipped = 0
        conflicts = 0
        evidence_created = 0

        for incoming in request.records:
            confirmed_specs = _clean_properties(incoming.specs)
            confirmed_fields = [key for key, value in confirmed_specs.items() if value not in (None, "", [])]
            required_for_record = (
                GPU_FAMILY_REQUIRED_FIELDS
                if _is_gpu_family_spec_record(request.category, incoming.canonical_key)
                else required_fields
            )
            missing_required = [field for field in required_for_record if confirmed_specs.get(field) in (None, "", [])]
            staged_records = self._staged_records_for_confirmed_spec(
                category=request.category,
                canonical_key=incoming.canonical_key,
                specs=confirmed_specs,
            )

            if not staged_records:
                skipped += 1
                items.append(
                    ConfirmedSpecEnrichmentItem(
                        canonical_key=incoming.canonical_key,
                        status="skipped",
                        staged_record_found=False,
                        reason="staged canonical record not found",
                        confirmed_fields=confirmed_fields,
                        missing_required_fields=list(missing_required),
                    )
                )
                continue

            for staged in staged_records:
                staged_canonical_key = str(staged.get("canonical_key") or incoming.canonical_key)
                if str(staged.get("category") or "") != request.category:
                    skipped += 1
                    items.append(
                        ConfirmedSpecEnrichmentItem(
                            canonical_key=staged_canonical_key,
                            status="skipped",
                            staged_record_found=True,
                            reason=f"staged record is {staged.get('category')}, not {request.category}",
                            confirmed_fields=confirmed_fields,
                            missing_required_fields=list(missing_required),
                        )
                    )
                    continue

                matched += 1
                staged_conflicts = _staged_string_list(staged.get("conflict_candidates"))
                if staged_conflicts:
                    conflicts += 1
                    items.append(
                        ConfirmedSpecEnrichmentItem(
                            canonical_key=staged_canonical_key,
                            status="conflict_requires_founder_review",
                            staged_record_found=True,
                            reason="staged record already has canonical conflicts",
                            confirmed_fields=confirmed_fields,
                        )
                    )
                    continue

                merged_specs = _extract_staged_specs(staged)
                merged_specs.update(confirmed_specs)
                readiness_state = _gpu_readiness_state(category=request.category, specs=merged_specs, record=staged)
                exact_ready = request.category != "GPU" and not [
                    field for field in required_fields if merged_specs.get(field) in (None, "", [])
                ]
                family_ready = False
                missing_exact_card = []
                if request.category == "GPU":
                    exact_ready = _gpu_exact_ready(merged_specs)
                    family_ready = _gpu_family_ready(merged_specs)
                    missing_exact_card = _gpu_exact_missing_fields(merged_specs)
                    if exact_ready:
                        readiness_state = "compatibility_ready_exact"
                    elif family_ready:
                        readiness_state = "compatibility_ready_family"
                    else:
                        readiness_state = "metadata_only"
                    missing_after_merge = [] if exact_ready or family_ready else _gpu_family_missing_fields(merged_specs)
                else:
                    missing_after_merge = [
                        field for field in required_fields if merged_specs.get(field) in (None, "", [])
                    ]
                if missing_after_merge:
                    skipped += 1
                    items.append(
                        ConfirmedSpecEnrichmentItem(
                            canonical_key=staged_canonical_key,
                            status="skipped",
                            staged_record_found=True,
                            reason=f"confirmed evidence is missing required field(s): {', '.join(missing_after_merge)}",
                            confirmed_fields=confirmed_fields,
                            missing_required_fields=missing_after_merge,
                        )
                    )
                    continue

                if request.dry_run:
                    items.append(
                        ConfirmedSpecEnrichmentItem(
                            canonical_key=staged_canonical_key,
                            status="would_enrich",
                            staged_record_found=True,
                            confirmed_fields=confirmed_fields,
                        )
                    )
                    continue

                self._apply_confirmed_specs_to_staged_record(
                    canonical_key=staged_canonical_key,
                    category=request.category,
                    specs=merged_specs,
                    source_name=request.source_name,
                    license_note=request.license_note,
                    evidence_note=incoming.evidence_note,
                    confirmed_fields=confirmed_fields,
                    readiness_state=readiness_state,
                    compatibility_ready_exact=exact_ready,
                    compatibility_ready_family=family_ready,
                    missing_compatibility_fields=[] if exact_ready else missing_exact_card if family_ready else missing_after_merge,
                    missing_exact_card_fields=missing_exact_card,
                )
                attached = self._attach_confirmed_spec_evidence(
                    canonical_key=staged_canonical_key,
                    category=request.category,
                    source_name=request.source_name,
                    license_note=request.license_note,
                    evidence_note=incoming.evidence_note,
                    specs=confirmed_specs,
                )
                if attached:
                    evidence_created += 1
                enriched += 1
                items.append(
                    ConfirmedSpecEnrichmentItem(
                        canonical_key=staged_canonical_key,
                        status="enriched",
                        staged_record_found=True,
                        evidence_attached=attached,
                        confirmed_fields=confirmed_fields,
                    )
                )

        return ConfirmedSpecEnrichmentResponse(
            source_name=request.source_name,
            category=request.category,
            dry_run=request.dry_run,
            total_records=len(request.records),
            matched_staged_records=matched,
            enriched_records=enriched,
            skipped_records=skipped,
            conflict_count=conflicts,
            evidence_created=evidence_created,
            items=items,
        )

    def link_market_evidence(self, request: MarketEvidenceLinkRequest) -> MarketEvidenceLinkResponse:
        region = normalize_region(request.region)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p:Product)
            WHERE p.canonical_key IS NOT NULL
              AND ($category IS NULL OR p.category = $category OR $category IN labels(p))
              AND (size($canonical_keys) = 0 OR p.canonical_key IN $canonical_keys)
            MATCH (p)-[:HAS_PRICE]->(snapshot:PriceSnapshot)-[:FROM_VENDOR]->(vendor:Vendor)
            WHERE snapshot.region = $region AND snapshot.currency = "SAR"
            WITH p, snapshot, vendor
            ORDER BY snapshot.price ASC
            WITH p,
                 count(DISTINCT snapshot) AS price_snapshot_count,
                 collect({price: snapshot.price, vendor_name: vendor.name})[0] AS cheapest
            RETURN p.id AS product_id,
                   p.name AS product_name,
                   p.canonical_key AS canonical_key,
                   coalesce(p.identity_confidence, 1.0) AS confidence,
                   price_snapshot_count,
                   cheapest.price AS cheapest_price_sar,
                   cheapest.vendor_name AS cheapest_vendor
            ORDER BY p.name ASC
            LIMIT $limit
            """,
            region=region,
            category=request.category,
            canonical_keys=request.canonical_keys,
            limit=request.limit,
            database_=settings.neo4j_database,
        )

        items: list[MarketEvidenceLinkItem] = []
        linked = 0
        skipped = 0
        for row in records:
            data = row.data()
            confidence = float(data.get("confidence") or 0)
            if confidence < request.confidence_threshold:
                skipped += 1
                items.append(
                    MarketEvidenceLinkItem(
                        canonical_key=str(data.get("canonical_key") or ""),
                        product_id=data.get("product_id"),
                        product_name=data.get("product_name"),
                        confidence=confidence,
                        status="skipped",
                        reason="identity confidence below threshold",
                        price_snapshot_count=int(data.get("price_snapshot_count") or 0),
                        cheapest_price_sar=_optional_float(data.get("cheapest_price_sar")),
                        cheapest_vendor=data.get("cheapest_vendor"),
                    )
                )
                continue

            if not request.dry_run:
                self.driver.execute_query(
                    """
                    MATCH (p:Product {id: $product_id})
                    SET p.market_evidence_linked = true,
                        p.market_evidence_region = $region,
                        p.market_evidence_source_name = $source_name,
                        p.market_evidence_linked_at = datetime()
                    """,
                    product_id=data.get("product_id"),
                    region=region,
                    source_name=request.source_name,
                    database_=settings.neo4j_database,
                )
                linked += 1
            items.append(
                MarketEvidenceLinkItem(
                    canonical_key=str(data.get("canonical_key") or ""),
                    product_id=data.get("product_id"),
                    product_name=data.get("product_name"),
                    confidence=confidence,
                    status="linked" if not request.dry_run else "would_link",
                    price_snapshot_count=int(data.get("price_snapshot_count") or 0),
                    cheapest_price_sar=_optional_float(data.get("cheapest_price_sar")),
                    cheapest_vendor=data.get("cheapest_vendor"),
                )
            )

        return MarketEvidenceLinkResponse(
            region=region,
            dry_run=request.dry_run,
            matched_count=len(records),
            linked_count=linked,
            skipped_count=skipped,
            price_mutation_count=0,
            items=items,
        )

    def run_spec_audit(self, request: SpecAuditRunRequest) -> SpecAuditRunResponse:
        region = normalize_region(request.region)
        categories = [str(category) for category in request.categories if str(category) in SPEC_AUDIT_CATEGORIES]
        before_price = self._count_query("MATCH (s:PriceSnapshot) RETURN count(s) AS count")
        before_regional = self._count_query("MATCH (s:RegionalPriceSnapshot) RETURN count(s) AS count")
        fixture_evidence = _spec_audit_fixture_evidence()
        product_rows = self._spec_audit_product_rows(categories=categories, limit=request.limit)
        product_actions: list[SpecAuditProductAction] = []
        missing_by_category: dict[str, dict[str, int]] = {}

        for row in product_rows:
            product = dict(row.get("product") or {})
            category = str(row.get("category") or _spec_audit_category(product, categories))
            if category not in categories:
                continue
            try:
                evidence = [dict(item) for item in row.get("evidence") or [] if isinstance(item, dict)]
                action = self._spec_audit_action(
                    product=product,
                    category=category,
                    evidence=evidence,
                    fixture_evidence=fixture_evidence,
                )
            except Exception as exc:
                logger.warning(
                    "spec_audit_product_evaluation_failed",
                    extra={
                        "category": category,
                        "canonical_key": product.get("canonical_key"),
                        "error_type": type(exc).__name__,
                    },
                )
                action = _spec_audit_fallback_action(product=product, category=category)
            product_actions.append(action)
            if action.missing_fields:
                bucket = missing_by_category.setdefault(category, {})
                for field in action.missing_fields:
                    bucket[field] = bucket.get(field, 0) + 1

        after_price = self._count_query("MATCH (s:PriceSnapshot) RETURN count(s) AS count")
        after_regional = self._count_query("MATCH (s:RegionalPriceSnapshot) RETURN count(s) AS count")
        audit_id = f"spec-audit:{uuid4()}"
        response = SpecAuditRunResponse(
            audit_id=audit_id,
            region=region,
            mode=request.mode,
            source_policy=request.source_policy,
            categories=categories,
            limit=request.limit,
            audited_product_count=len(product_actions),
            verified_count=sum(1 for action in product_actions if action.status == "verified_current"),
            missing_evidence_count=sum(1 for action in product_actions if action.status == "missing_trusted_evidence"),
            conflict_count=sum(1 for action in product_actions if action.status == "spec_conflict_requires_review"),
            stale_or_deprioritized_count=sum(1 for action in product_actions if action.status == "stale_or_deprioritized"),
            safe_fixes_available_count=sum(1 for action in product_actions if action.status == "safe_fix_available"),
            per_category_missing_fields=[
                SpecAuditCategoryMissingFields(
                    category=category,
                    fields=[
                        CanonicalImportReasonCount(reason=field, count=count)
                        for field, count in sorted(fields.items(), key=lambda item: (-item[1], item[0]))
                    ],
                )
                for category, fields in sorted(missing_by_category.items())
            ],
            product_actions=product_actions,
            price_snapshot_count=SpecAuditPriceCountSnapshot(
                before=before_price,
                after=after_price,
                unchanged=before_price == after_price,
            ),
            regional_price_snapshot_count=SpecAuditPriceCountSnapshot(
                before=before_regional,
                after=after_regional,
                unchanged=before_regional == after_regional,
            ),
        )
        self._persist_spec_audit_response(response)
        return response

    def spec_audit_report(self, audit_id: str) -> SpecAuditRunResponse | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (run:SpecAuditRun {audit_id: $audit_id})
            RETURN run.payload_json AS payload_json
            LIMIT 1
            """,
            audit_id=audit_id,
            database_=settings.neo4j_database,
        )
        if not records:
            return None
        return SpecAuditRunResponse.model_validate_json(str(records[0]["payload_json"]))

    def spec_audit_products(self, status: str | None = None, category: str | None = None) -> SpecAuditProductListResponse:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (run:SpecAuditRun)
            WITH run
            ORDER BY run.created_at DESC
            LIMIT 1
            OPTIONAL MATCH (run)-[:HAS_SPEC_AUDIT_ITEM]->(item:SpecAuditItem)
            WHERE ($status IS NULL OR item.status = $status)
              AND ($category IS NULL OR item.category = $category)
            RETURN run.audit_id AS audit_id,
                   item.payload_json AS payload_json
            ORDER BY item.category ASC, item.name ASC
            """,
            status=status,
            category=category,
            database_=settings.neo4j_database,
        )
        audit_id: str | None = None
        products: list[SpecAuditProductAction] = []
        for record in records:
            if record.get("audit_id"):
                audit_id = str(record["audit_id"])
            payload = record.get("payload_json")
            if payload:
                products.append(SpecAuditProductAction.model_validate_json(str(payload)))
        return SpecAuditProductListResponse(audit_id=audit_id, status=status, category=category, products=products)

    def _spec_audit_product_rows(self, *, categories: list[str], limit: int) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p:Product:CanonicalProduct)
            WITH p, [label IN labels(p) WHERE label IN $categories][0] AS label_category
            WITH p, coalesce(p.category, label_category) AS category
            WHERE category IN $categories
            OPTIONAL MATCH (p)-[:HAS_CANONICAL_EVIDENCE]->(e:CanonicalEvidence)
            WITH p, category, collect(e {.*}) AS evidence
            RETURN p {.*, labels: labels(p)} AS product,
                   category,
                   evidence
            ORDER BY category ASC, coalesce(p.name, p.canonical_key) ASC
            LIMIT $limit
            """,
            categories=categories,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [record.data() for record in records]

    def _spec_audit_action(
        self,
        *,
        product: dict[str, Any],
        category: str,
        evidence: list[dict[str, Any]],
        fixture_evidence: dict[str, dict[str, Any]],
    ) -> SpecAuditProductAction:
        canonical_key = product.get("canonical_key")
        specs = _spec_audit_specs(product)
        required_fields = _spec_audit_required_fields(category)
        evidence_by_field = _spec_audit_evidence_by_field(
            str(canonical_key) if canonical_key else None,
            evidence,
            fixture_evidence,
        )
        status, missing, conflicts, inferred, safe_fixes, stale_reason = _spec_audit_status(
            category=category,
            product=product,
            specs=specs,
            required_fields=required_fields,
            evidence_by_field=evidence_by_field,
        )
        return SpecAuditProductAction(
            product_id=str(product.get("id") or canonical_key or product.get("name") or "unknown"),
            canonical_key=str(canonical_key) if canonical_key else None,
            name=str(product.get("name") or canonical_key or "Unknown product"),
            category=category,
            status=status,  # type: ignore[arg-type]
            missing_fields=missing,
            conflicting_fields=conflicts,
            inferred_fields=inferred,
            safe_fix_fields=safe_fixes,
            stale_reason=stale_reason,
            evidence_summary=_spec_audit_evidence_summary(evidence_by_field),
            next_action=_spec_audit_next_action(status, missing, conflicts, safe_fixes, stale_reason),
        )

    def _persist_spec_audit_response(self, response: SpecAuditRunResponse) -> None:
        payload_json = response.model_dump_json()
        self.driver.execute_query(
            """
            MERGE (run:SpecAuditRun {audit_id: $audit_id})
            SET run.region = $region,
                run.mode = $mode,
                run.source_policy = $source_policy,
                run.categories = $categories,
                run.limit = $limit,
                run.audited_product_count = $audited_product_count,
                run.verified_count = $verified_count,
                run.missing_evidence_count = $missing_evidence_count,
                run.conflict_count = $conflict_count,
                run.stale_or_deprioritized_count = $stale_or_deprioritized_count,
                run.safe_fixes_available_count = $safe_fixes_available_count,
                run.price_snapshot_before = $price_snapshot_before,
                run.price_snapshot_after = $price_snapshot_after,
                run.regional_price_snapshot_before = $regional_price_snapshot_before,
                run.regional_price_snapshot_after = $regional_price_snapshot_after,
                run.payload_json = $payload_json,
                run.created_at = datetime()
            """,
            audit_id=response.audit_id,
            region=response.region,
            mode=response.mode,
            source_policy=response.source_policy,
            categories=response.categories,
            limit=response.limit,
            audited_product_count=response.audited_product_count,
            verified_count=response.verified_count,
            missing_evidence_count=response.missing_evidence_count,
            conflict_count=response.conflict_count,
            stale_or_deprioritized_count=response.stale_or_deprioritized_count,
            safe_fixes_available_count=response.safe_fixes_available_count,
            price_snapshot_before=response.price_snapshot_count.before,
            price_snapshot_after=response.price_snapshot_count.after,
            regional_price_snapshot_before=response.regional_price_snapshot_count.before,
            regional_price_snapshot_after=response.regional_price_snapshot_count.after,
            payload_json=payload_json,
            database_=settings.neo4j_database,
        )
        for action in response.product_actions:
            self.driver.execute_query(
                """
                MATCH (run:SpecAuditRun {audit_id: $audit_id})
                MERGE (item:SpecAuditItem {id: $item_id})
                SET item.audit_id = $audit_id,
                    item.product_id = $product_id,
                    item.canonical_key = $canonical_key,
                    item.name = $name,
                    item.category = $category,
                    item.status = $status,
                    item.payload_json = $payload_json,
                    item.created_at = datetime()
                MERGE (run)-[:HAS_SPEC_AUDIT_ITEM]->(item)
                """,
                audit_id=response.audit_id,
                item_id=_spec_audit_item_id(response.audit_id, action),
                product_id=action.product_id,
                canonical_key=action.canonical_key,
                name=action.name,
                category=action.category,
                status=action.status,
                payload_json=action.model_dump_json(),
                database_=settings.neo4j_database,
            )

    def attach_canonical_evidence(self, request: CanonicalEvidenceRequest) -> CanonicalEvidenceResponse:
        evidence_id = f"evidence:{uuid4()}"
        approval_state = "approved" if request.approved_by_founder else "pending_review"
        labels = ":CanonicalEvidence"
        if request.evidence_type == "community_hint":
            labels += ":CommunityEvidence"
        if request.evidence_type == "performance_hint":
            labels += ":TelemetryEvidence"
        records, _, _ = self.driver.execute_query(
            f"""
            MATCH (p:Product)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            WITH p LIMIT 1
            MERGE (source:CanonicalSource {{name: $source_name}})
            SET source.updated_at = datetime()
            CREATE (e{labels})
            SET e.id = $evidence_id,
                e.source_name = $source_name,
                e.evidence_type = $evidence_type,
                e.field = $field,
                e.value_json = $value_json,
                e.trust_score = $trust_score,
                e.note = $note,
                e.created_at = datetime()
            MERGE (p)-[:HAS_CANONICAL_EVIDENCE]->(e)
            MERGE (e)-[:FROM_SOURCE]->(source)
            MERGE (approval:FounderApprovalState {{id: $approval_id}})
            SET approval.status = $approval_state,
                approval.source_name = $source_name,
                approval.updated_at = datetime()
            MERGE (e)-[:HAS_APPROVAL_STATE]->(approval)
            RETURN p.id AS product_id
            """,
            product_id=request.product_id,
            source_name=request.source_name,
            evidence_id=evidence_id,
            evidence_type=request.evidence_type,
            field=request.field,
            value_json=json.dumps(request.value, sort_keys=True),
            trust_score=request.trust_score,
            note=request.note,
            approval_id=f"approval:{evidence_id}",
            approval_state=approval_state,
            database_=settings.neo4j_database,
        )
        if not records:
            return CanonicalEvidenceResponse(
                product_id=request.product_id,
                evidence_id=evidence_id,
                evidence_type=request.evidence_type,
                source_name=request.source_name,
                attached=False,
                approval_state="product_not_found",
            )
        return CanonicalEvidenceResponse(
            product_id=str(records[0]["product_id"]),
            evidence_id=evidence_id,
            evidence_type=request.evidence_type,
            source_name=request.source_name,
            attached=True,
            approval_state=approval_state,
        )

    def _staged_record_by_canonical_key(self, canonical_key: str) -> dict[str, Any] | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord)
            WHERE record.canonical_key = $canonical_key
               OR toUpper(record.canonical_key) = toUpper($canonical_key)
            RETURN properties(record) AS record
            LIMIT 1
            """,
            canonical_key=canonical_key,
            database_=settings.neo4j_database,
        )
        if not records:
            return None
        return dict(records[0].data().get("record") or {})

    def _staged_records_for_confirmed_spec(
        self,
        *,
        category: str,
        canonical_key: str,
        specs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if _is_gpu_family_spec_record(category, canonical_key):
            family_name = _gpu_family_name_from_confirmed_spec(canonical_key, specs)
            target_family_key = _gpu_family_target_key(family_name)
            family_text = family_name.upper()
            spec_family_values = [
                json.dumps({"chip_family": value}, sort_keys=True)[1:-1]
                for value in (family_name, f"GeForce {family_name}", f"Radeon {family_name}")
            ]
            records, _, _ = self.driver.execute_query(
                """
                MATCH (record:StagedCanonicalRecord)
                WHERE record.category = "GPU"
                  AND (
                    record.target_family_key = $target_family_key
                    OR toUpper(coalesce(record.target_family_name, "")) = $family_text
                    OR any(value IN $spec_family_values WHERE coalesce(record.specs, "") CONTAINS value)
                  )
                RETURN properties(record) AS record
                ORDER BY record.canonical_key ASC
                LIMIT 100
                """,
                target_family_key=target_family_key,
                family_text=family_text,
                spec_family_values=spec_family_values,
                database_=settings.neo4j_database,
            )
            return [dict(row.data().get("record") or {}) for row in records]
        staged = self._staged_record_by_canonical_key(canonical_key)
        return [staged] if staged else []

    def _apply_confirmed_specs_to_staged_record(
        self,
        *,
        canonical_key: str,
        category: str,
        specs: dict[str, Any],
        source_name: str,
        license_note: str,
        evidence_note: str,
        confirmed_fields: list[str],
        readiness_state: str | None = None,
        compatibility_ready_exact: bool | None = None,
        compatibility_ready_family: bool | None = None,
        missing_compatibility_fields: list[str] | None = None,
        missing_exact_card_fields: list[str] | None = None,
    ) -> None:
        if category == "GPU":
            exact_ready = bool(compatibility_ready_exact)
            family_ready = bool(compatibility_ready_family)
            missing = [] if exact_ready or family_ready else _gpu_family_missing_fields(specs)
            required_specs_present = exact_ready or family_ready
            compatibility_ready = exact_ready
            readiness = readiness_state or ("compatibility_ready_exact" if exact_ready else "compatibility_ready_family" if family_ready else "metadata_only")
        else:
            missing = [field for field in CONFIRMED_SPEC_REQUIRED_FIELDS.get(category, ()) if specs.get(field) in (None, "", [])]
            exact_ready = not missing
            family_ready = False
            required_specs_present = exact_ready
            compatibility_ready = exact_ready
            readiness = readiness_state or ("compatibility_ready_exact" if exact_ready else "metadata_only")
        if missing:
            raise ValueError(f"confirmed specs still missing required fields: {', '.join(missing)}")
        records, _, _ = self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord {canonical_key: $canonical_key})
            SET record.specs = $specs_json,
                record.compatibility_ready = $compatibility_ready,
                record.compatibility_ready_exact = $compatibility_ready_exact,
                record.compatibility_ready_family = $compatibility_ready_family,
                record.readiness_state = $readiness_state,
                record.compatibility_completeness_score = $compatibility_completeness_score,
                record.required_specs_present = $required_specs_present,
                record.missing_compatibility_fields = $missing_compatibility_fields,
                record.missing_exact_card_fields = $missing_exact_card_fields,
                record.confirmed_compatibility_fields = $confirmed_fields,
                record.confirmed_spec_source_name = $source_name,
                record.confirmed_spec_license_note = $license_note,
                record.confirmed_spec_note = $evidence_note,
                record.confirmed_spec_updated_at = datetime(),
                record.import_status = "pending",
                record.updated_at = datetime()
            RETURN count(record) AS count
            """,
            canonical_key=canonical_key,
            specs_json=json.dumps(specs, sort_keys=True),
            compatibility_ready=compatibility_ready,
            compatibility_ready_exact=exact_ready,
            compatibility_ready_family=family_ready,
            readiness_state=readiness,
            compatibility_completeness_score=1.0 if exact_ready else 0.72 if family_ready else 0.0,
            required_specs_present=required_specs_present,
            missing_compatibility_fields=missing_compatibility_fields if missing_compatibility_fields is not None else [],
            missing_exact_card_fields=missing_exact_card_fields if missing_exact_card_fields is not None else [],
            confirmed_fields=confirmed_fields,
            source_name=source_name,
            license_note=license_note,
            evidence_note=evidence_note,
            database_=settings.neo4j_database,
        )
        if not records or int(records[0]["count"] or 0) < 1:
            raise ValueError("staged canonical record not found during enrichment")

    def _attach_confirmed_spec_evidence(
        self,
        *,
        canonical_key: str,
        category: str,
        source_name: str,
        license_note: str,
        evidence_note: str,
        specs: dict[str, Any],
    ) -> bool:
        evidence_field = _confirmed_spec_evidence_field(category, specs)
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p:Product {canonical_key: $canonical_key})
            WITH p LIMIT 1
            MERGE (source:CanonicalSource {name: $source_name})
            SET source.updated_at = datetime(),
                source.source_type = "confirmed_specs",
                source.license_note = $license_note
            WITH p, source
            OPTIONAL MATCH (p)-[:HAS_CANONICAL_EVIDENCE]->(
                existing:CanonicalEvidence {
                    source_name: $source_name,
                    evidence_type: "canonical_spec",
                    field: $field
                }
            )
            WITH p, source, existing
            WHERE existing IS NULL
            CREATE (e:CanonicalEvidence)
            SET e.id = $evidence_id,
                e.source_name = $source_name,
                e.evidence_type = "canonical_spec",
                e.field = $field,
                e.value_json = $value_json,
                e.trust_score = 0.95,
                e.note = $evidence_note,
                e.approval_state = "approved",
                e.created_at = datetime()
            MERGE (p)-[:HAS_CANONICAL_EVIDENCE]->(e)
            MERGE (e)-[:FROM_SOURCE]->(source)
            RETURN e.id AS evidence_id
            """,
            canonical_key=canonical_key,
            source_name=source_name,
            license_note=license_note,
            evidence_note=evidence_note,
            evidence_id=f"evidence:{uuid4()}",
            field=evidence_field,
            value_json=json.dumps({"canonical_key": canonical_key, "category": category, "specs": specs}, sort_keys=True),
            database_=settings.neo4j_database,
        )
        return bool(records)

    def _apply_confirmed_cpu_specs_to_staged_record(
        self,
        *,
        canonical_key: str,
        specs: dict[str, Any],
        source_name: str,
        license_note: str,
        evidence_note: str,
        confirmed_fields: list[str],
    ) -> None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (record:StagedCanonicalRecord {canonical_key: $canonical_key})
            SET record.specs = $specs_json,
                record.compatibility_ready = true,
                record.compatibility_completeness_score = 1.0,
                record.required_specs_present = true,
                record.missing_compatibility_fields = [],
                record.confirmed_compatibility_fields = $confirmed_fields,
                record.confirmed_spec_source_name = $source_name,
                record.confirmed_spec_license_note = $license_note,
                record.confirmed_spec_note = $evidence_note,
                record.confirmed_spec_updated_at = datetime(),
                record.import_status = "pending",
                record.updated_at = datetime()
            RETURN count(record) AS count
            """,
            canonical_key=canonical_key,
            specs_json=json.dumps(specs, sort_keys=True),
            confirmed_fields=confirmed_fields,
            source_name=source_name,
            license_note=license_note,
            evidence_note=evidence_note,
            database_=settings.neo4j_database,
        )
        if not records or int(records[0]["count"] or 0) < 1:
            raise ValueError("staged CPU record not found during enrichment")

    def _attach_confirmed_cpu_spec_evidence(
        self,
        *,
        canonical_key: str,
        source_name: str,
        license_note: str,
        evidence_note: str,
        specs: dict[str, Any],
    ) -> bool:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p:Product {canonical_key: $canonical_key})
            WITH p LIMIT 1
            MERGE (source:CanonicalSource {name: $source_name})
            SET source.updated_at = datetime(),
                source.source_type = "confirmed_cpu_specs",
                source.license_note = $license_note
            CREATE (e:CanonicalEvidence)
            SET e.id = $evidence_id,
                e.source_name = $source_name,
                e.evidence_type = "canonical_spec",
                e.field = "confirmed_cpu_specs",
                e.value_json = $value_json,
                e.trust_score = 0.95,
                e.note = $evidence_note,
                e.approval_state = "approved",
                e.created_at = datetime()
            MERGE (p)-[:HAS_CANONICAL_EVIDENCE]->(e)
            MERGE (e)-[:FROM_SOURCE]->(source)
            RETURN e.id AS evidence_id
            """,
            canonical_key=canonical_key,
            source_name=source_name,
            license_note=license_note,
            evidence_note=evidence_note,
            evidence_id=f"evidence:{uuid4()}",
            value_json=json.dumps({"canonical_key": canonical_key, "specs": specs}, sort_keys=True),
            database_=settings.neo4j_database,
        )
        return bool(records)

    def _count_query(self, statement: str, **parameters: Any) -> int:
        records, _, _ = self.driver.execute_query(
            statement,
            **parameters,
            database_=settings.neo4j_database,
        )
        return int(records[0]["count"] or 0) if records else 0

    def _overall_integrity_status(self, integrity: HybridGraphIntegrityResponse) -> str:
        statuses = {check.status for check in integrity.checks}
        if "fail" in statuses:
            return "fail"
        if "warn" in statuses:
            return "warn"
        return "pass"

    def _integrity_check(
        self,
        *,
        name: str,
        count: int,
        pass_detail: str,
        fail_detail: str,
    ) -> HybridIntegrityCheck:
        return HybridIntegrityCheck(
            name=name,
            status="pass" if count == 0 else "fail",
            detail=pass_detail if count == 0 else fail_detail,
            count=count,
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
                     efficiency_rating: p.spec_efficiency_rating,
                     chip_family: p.spec_chip_family,
                     vram_gb: p.spec_vram_gb,
                     pcie_generation: p.spec_pcie_generation,
                     reference_tdp_w: p.spec_reference_tdp_w,
                     board_power_w: p.spec_board_power_w,
                     gpu_length_mm: p.spec_length_mm,
                     slots: p.spec_slots,
                     power_connectors: p.spec_power_connectors
                   } AS summary_specs,
                   coalesce(p.imageUrl, p.image_url) AS image_url,
                   p.processed_image_url AS processed_image_url,
                   p.compatibility_ready AS compatibility_ready,
                   p.compatibility_ready_exact AS compatibility_ready_exact,
                   p.compatibility_ready_family AS compatibility_ready_family,
                   p.readiness_state AS readiness_state,
                   p.missing_compatibility_fields AS missing_compatibility_fields,
                   p.missing_exact_card_fields AS missing_exact_card_fields,
                   p.inferred_fields AS inferred_fields,
                   CASE WHEN p.market_evidence_linked = true THEN 1 ELSE 0 END AS market_linked_count,
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
