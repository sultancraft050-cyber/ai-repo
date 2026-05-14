from __future__ import annotations

from datetime import UTC, datetime

import os
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from app.main import _audit_metadata
from app.models.pricing import (
    CpuSpecsImportRow,
    PriceSnapshotView,
    ProductDiscoveryRequest,
    SourceMetadata,
    SourceProductRecord,
    SourceTier,
    SourceType,
)
from app.services.region_config import get_region_config, vendor_region_type, vendor_trust_profile
from app.services.hardware_taxonomy import classify_category, discovery_queries
from app.services.ops import OpsService
from app.services.pricing_ingestion import (
    CanonicalizationValidationService,
    PricingIngestionService,
    _apply_region_context,
    _target_model_rejections,
)
from app.services.pricing_classification import classify_listing_market, classify_product_type
from app.services.pricing_normalization import (
    CanonicalProductEngine,
    case_family_key_from_title,
    compact_model,
    cooler_family_key_from_title,
    motherboard_family_key_from_title,
    psu_family_key_from_title,
    ram_family_key_from_title,
    storage_model_key_from_title,
)
from app.services.pricing_quality import PriceQualityValidator
from app.services import pricing_sources
from app.services.pricing_sources import SerpApiShoppingSource
from app.graph.pricing_repository import (
    Neo4jPricingRepository,
    _cpu_product_first_results,
    _price_rollups,
    _search_result,
    _search_sort_key,
)
from app.graph.pricing_repository import _cpu_specs_import_product


def _record(price: float = 599.99) -> SourceProductRecord:
    timestamp = datetime.now(UTC)
    return SourceProductRecord(
        source_product_id="sku-1",
        title="NVIDIA GeForce RTX4070SUPER 12GB Graphics Card",
        brand="NVIDIA GeForce",
        category="GPU",
        price=price,
        currency="USD",
        availability="in_stock",
        vendor_name="BestBuy",
        source=SourceMetadata(
            source="BestBuy Products API",
            source_type=SourceType.RETAILER_API,
            tier=SourceTier.RETAILER_API,
            timestamp=timestamp,
            trust_score=0.9,
            freshness_score=1,
        ),
        specs={"vram_gb": 12},
    )


def _record_with_title(title: str, price: float = 599.99, brand: str | None = None) -> SourceProductRecord:
    record = _record(price=price)
    record.title = title
    record.brand = brand
    record.model = None
    record.specs = {}
    return record


def _cpu_record_with_title(title: str, price: float = 1599.0, brand: str | None = "AMD") -> SourceProductRecord:
    record = _record_with_title(title, price=price, brand=brand)
    record.category = "CPU"
    record.currency = "SAR"
    record.vendor_region = "SA"
    record.region = "SA"
    record.country_code = "SA"
    record.vendor_name = "Amazon.sa"
    return record


def _storage_record_with_title(title: str, price: float = 699.0, brand: str | None = "Samsung") -> SourceProductRecord:
    record = _record_with_title(title, price=price, brand=brand)
    record.category = "Storage"
    record.currency = "SAR"
    record.vendor_region = "SA"
    record.region = "SA"
    record.country_code = "SA"
    record.vendor_name = "Amazon.sa"
    return record


def _ram_record_with_title(title: str, price: float = 449.0, brand: str | None = None) -> SourceProductRecord:
    record = _record_with_title(title, price=price, brand=brand)
    record.category = "RAM"
    record.currency = "SAR"
    record.vendor_region = "SA"
    record.region = "SA"
    record.country_code = "SA"
    record.vendor_name = "Amazon.sa"
    return record


def _psu_record_with_title(title: str, price: float = 599.0, brand: str | None = None) -> SourceProductRecord:
    record = _record_with_title(title, price=price, brand=brand)
    record.category = "PSU"
    record.currency = "SAR"
    record.vendor_region = "SA"
    record.region = "SA"
    record.country_code = "SA"
    record.vendor_name = "Amazon.sa"
    return record


def _case_record_with_title(title: str, price: float = 399.0, brand: str | None = None) -> SourceProductRecord:
    record = _record_with_title(title, price=price, brand=brand)
    record.category = "Case"
    record.currency = "SAR"
    record.vendor_region = "SA"
    record.region = "SA"
    record.country_code = "SA"
    record.vendor_name = "Amazon.sa"
    return record


def _cooler_record_with_title(title: str, price: float = 399.0, brand: str | None = None) -> SourceProductRecord:
    record = _record_with_title(title, price=price, brand=brand)
    record.category = "Cooler"
    record.currency = "SAR"
    record.vendor_region = "SA"
    record.region = "SA"
    record.country_code = "SA"
    record.vendor_name = "Amazon.sa"
    return record


def _motherboard_record_with_title(title: str, price: float = 799.0, brand: str | None = None) -> SourceProductRecord:
    record = _record_with_title(title, price=price, brand=brand)
    record.category = "Motherboard"
    record.currency = "SAR"
    record.vendor_region = "SA"
    record.region = "SA"
    record.country_code = "SA"
    record.vendor_name = "Amazon.sa"
    return record


def _snapshot(
    *,
    vendor: str,
    price: float,
    condition: str,
    seller_type: str,
    risk: float,
    flags: list[str] | None = None,
    currency: str = "USD",
    region: str = "US",
    final_landed_price: float | None = None,
    is_local_stock: bool | None = None,
    is_imported: bool | None = None,
    final_landed_price_sar: float | None = None,
    item_price_sar: float | None = None,
    shipping_cost_sar: float | None = None,
    vat_status: str = "vat_unknown",
    shipping_status: str = "unknown_shipping",
    warranty_status: str = "unknown_warranty",
    local_stock_status: str = "unknown_stock",
    vendor_region_type: str = "unknown_vendor",
    recommended_saudi_price_candidate: bool = False,
    local_stock_confidence: float | None = None,
    warranty_confidence: float | None = None,
    delivery_confidence: float | None = None,
    trust_tier: str = "unknown",
) -> PriceSnapshotView:
    return PriceSnapshotView(
        id=f"snapshot-{vendor}-{price}",
        vendor_id=vendor.lower().replace(" ", "-"),
        vendor_name=vendor,
        price=price,
        currency=currency,
        region=region,
        country_code=region,
        final_landed_price=final_landed_price,
        final_landed_currency=currency,
        item_price_sar=item_price_sar,
        shipping_cost_sar=shipping_cost_sar,
        final_landed_price_sar=final_landed_price_sar,
        vat_status=vat_status,  # type: ignore[arg-type]
        shipping_status=shipping_status,  # type: ignore[arg-type]
        warranty_status=warranty_status,  # type: ignore[arg-type]
        local_stock_status=local_stock_status,  # type: ignore[arg-type]
        vendor_region_type=vendor_region_type,  # type: ignore[arg-type]
        is_local_stock=is_local_stock,
        local_warranty=is_local_stock,
        is_imported=is_imported if is_imported is not None else False if is_local_stock else None,
        region_rank_score=0.86 if is_local_stock else None,
        recommended_saudi_price_candidate=recommended_saudi_price_candidate,
        trust_tier=trust_tier,  # type: ignore[arg-type]
        local_stock_confidence=local_stock_confidence,
        warranty_confidence=warranty_confidence,
        delivery_confidence=delivery_confidence,
        availability="in_stock",
        timestamp=datetime.now(UTC),
        shipping_cost=0,
        source="unit-test",
        source_type=SourceType.RETAILER_API,
        source_tier=SourceTier.RETAILER_API,
        trust_score=0.9 if seller_type == "retailer" else 0.72,
        freshness_score=1,
        listing_condition=condition,  # type: ignore[arg-type]
        seller_type=seller_type,  # type: ignore[arg-type]
        marketplace_risk_score=risk,
        flags=flags or [],
    )


def test_model_aliases_collapse_to_same_compact_model() -> None:
    assert compact_model("RTX4070SUPER") == compact_model("RTX 4070 Super")


def test_gpu_brand_inference_collapses_required_rtx_4070_super_variants() -> None:
    engine = CanonicalProductEngine()
    keys = []
    for title in [
        "RTX4070SUPER",
        "RTX 4070 Super",
        "GeForce RTX 4070 SUPER",
        "NVIDIA GeForce RTX 4070 Super",
    ]:
        record = _record()
        record.title = title
        record.brand = None
        keys.append(engine.normalize_record(record).product.canonical_key)
    assert len(set(keys)) == 1


def test_canonical_engine_preserves_field_evidence() -> None:
    offer = CanonicalProductEngine().normalize_record(_record())
    assert offer.product.brand == "NVIDIA"
    assert offer.product.category == "GPU"
    assert any(evidence.field == "price" for evidence in offer.field_evidence)


def test_quality_rejects_impossible_gpu_price() -> None:
    offer = CanonicalProductEngine().normalize_record(_record(price=5))
    report = PriceQualityValidator().validate_offer(offer)
    assert not report.accepted
    assert "impossible_price_below_category_floor" in report.rejected_reasons


def test_quality_flags_large_price_drop_without_rejecting() -> None:
    offer = CanonicalProductEngine().normalize_record(_record(price=350))
    report = PriceQualityValidator().validate_offer(offer, previous_price=1200)
    assert report.accepted
    assert "suspicious_price_drop_over_70_percent" in report.flags


def test_classifier_supports_expanded_market_categories() -> None:
    assert classify_category("Alienware 27 inch 360Hz OLED gaming monitor") == "Monitor"
    assert classify_category("Logitech G Pro X Superlight wireless gaming mouse") == "Mouse"
    assert classify_category("Elgato 4K60 HDMI capture card") == "Capture Card"


def test_discovery_queries_expand_category_sweeps() -> None:
    plan = discovery_queries(categories=["GPU", "Monitor"])
    assert ("GPU", "NVIDIA GeForce RTX graphics card") in plan
    assert any(category == "Monitor" for category, _ in plan)


def test_serpapi_adapter_redacts_api_key_in_source_url() -> None:
    original_request_json = pricing_sources._request_json
    original_key = os.environ.get("SERPAPI_KEY")
    os.environ["SERPAPI_KEY"] = "test-key"

    def fake_request_json(*args, **kwargs):
        return {
            "shopping_results": [
                {
                    "product_id": "serp-1",
                    "title": "NVIDIA GeForce RTX 4070 Super 12GB",
                    "extracted_price": 599.99,
                    "source": "Example Store",
                    "link": "https://example.test/product",
                    "thumbnail": "https://example.test/image.jpg",
                }
            ]
        }

    pricing_sources._request_json = fake_request_json
    try:
        records = SerpApiShoppingSource().fetch_offers(
            query="RTX 4070 Super",
            category="GPU",
            region="US",
            limit=1,
        )
    finally:
        pricing_sources._request_json = original_request_json
        if original_key is None:
            os.environ.pop("SERPAPI_KEY", None)
        else:
            os.environ["SERPAPI_KEY"] = original_key

    assert records
    assert "test-key" not in (records[0].source.source_url or "")
    assert "api_key=REDACTED" in (records[0].source.source_url or "")


def test_region_config_defaults_and_supported_markets() -> None:
    sa = get_region_config("SA")
    us = get_region_config("US")

    assert sa.google_domain == "google.com.sa"
    assert sa.gl == "sa"
    assert sa.currency == "SAR"
    assert us.google_domain == "google.com"
    assert us.gl == "us"
    assert us.currency == "USD"


def test_missing_region_defaults_to_sa_and_unsupported_region_is_rejected() -> None:
    request = ProductDiscoveryRequest(category="GPU", query="RTX 4070 Super")
    assert request.region == "SA"

    try:
        ProductDiscoveryRequest(category="GPU", query="RTX 4070 Super", region="CA")
    except ValidationError:
        pass
    else:
        raise AssertionError("unsupported region should fail validation")


def test_serpapi_adapter_uses_region_config() -> None:
    original_request_json = pricing_sources._request_json
    original_key = os.environ.get("SERPAPI_KEY")
    os.environ["SERPAPI_KEY"] = "test-key"
    captured: dict[str, str] = {}

    def fake_request_json(url, *args, **kwargs):
        captured["url"] = url
        return {
            "shopping_results": [
                {
                    "product_id": "sa-serp-1",
                    "title": "ASUS Dual GeForce RTX 4070 Super Graphics Card",
                    "price": "SAR 2,399",
                    "source": "Amazon.sa",
                    "link": "https://example.test/product",
                    "thumbnail": "https://example.test/image.jpg",
                }
            ]
        }

    pricing_sources._request_json = fake_request_json
    try:
        records = SerpApiShoppingSource().fetch_offers(
            query="RTX 4070 Super graphics card",
            category="GPU",
            region="SA",
            limit=1,
        )
    finally:
        pricing_sources._request_json = original_request_json
        if original_key is None:
            os.environ.pop("SERPAPI_KEY", None)
        else:
            os.environ["SERPAPI_KEY"] = original_key

    params = parse_qs(urlsplit(captured["url"]).query)
    assert params["gl"] == ["sa"]
    assert params["google_domain"] == ["google.com.sa"]
    assert params["location"] == ["Riyadh, Saudi Arabia"]
    assert records[0].currency == "SAR"
    assert records[0].region == "SA"


class FakeRequest:
    query_params: dict[str, str] = {}


def test_audit_metadata_includes_region_without_secret_payload() -> None:
    body = b'{"region":"SA","providers":["SerpAPI"],"api_key":"should-not-appear"}'

    metadata = _audit_metadata(FakeRequest(), body)  # type: ignore[arg-type]

    assert metadata == {"region": "SA", "market_source": "SerpAPI"}
    assert "should-not-appear" not in str(metadata)


class FakePricingRepository:
    def __init__(self) -> None:
        self.persisted = False

    def previous_price(
        self,
        product_id_or_key: str,
        vendor_id: str | None = None,
        region: str | None = None,
    ) -> float | None:
        return None

    def find_product_id(self, identity) -> str | None:
        return None

    def upsert_offer(self, offer, accepted: bool = True) -> str:
        self.persisted = True
        return "product:test"


class FakeSource:
    name = "SerpAPI"

    def configured(self) -> bool:
        return True

    def fetch_offers(self, *, query: str, category: str, region: str, limit: int):
        return [_record()]


class FakeRegistry:
    def enabled(self, names=None):
        return [FakeSource()]


class FakeOpsRepository:
    def source_activity(self):
        return {}


def test_discovery_dry_run_normalizes_validates_without_persisting() -> None:
    repository = FakePricingRepository()
    service = PricingIngestionService(repository, sources=FakeRegistry())  # type: ignore[arg-type]

    result = service.preview_query(
        query="RTX 4070 Super",
        category="GPU",
        region="US",
        limit=1,
    )

    assert result.accepted_snapshots == 1
    assert result.preview
    assert result.preview[0].merge_decision == "new_product"
    assert result.preview[0].product_type == "standalone_gpu"
    assert result.preview[0].gpu_family_key == "NVIDIA_GEFORCE_RTX_4070_SUPER"
    assert not repository.persisted


def test_saudi_region_config_includes_requested_local_retailer_targets() -> None:
    config = get_region_config("SA")

    for retailer in [
        "Jarir",
        "Extra",
        "Amazon.sa",
        "Noon Saudi",
        "Microless Saudi",
        "MTC KSA",
        "PCZone Saudi",
        "GoldenTech Saudi",
        "InfiniArc",
    ]:
        assert retailer in config.local_source_targets


def test_source_config_exposes_saudi_local_targets_with_infiniarc_policy() -> None:
    statuses = OpsService(FakeOpsRepository()).source_config(region="SA")  # type: ignore[arg-type]
    by_name = {status.source_name: status for status in statuses}

    assert "SerpAPI Saudi" in by_name
    assert "InfiniArc" in by_name
    assert "Jarir" in by_name
    assert by_name["InfiniArc"].direct_access_enabled is False
    assert "disabled by default" in (by_name["InfiniArc"].source_policy or "")
    assert "SerpAPI Saudi" in (by_name["InfiniArc"].preferred_discovery_path or "")


def test_infiniarc_classified_as_saudi_local_vendor_with_uncertainty_flags() -> None:
    record = _record_with_title("InfiniArc GeForce RTX 4070 Super 12GB Graphics Card", price=2499, brand="InfiniArc")
    record.vendor_name = "InfiniArc"
    record.vendor_region = "SA"
    record.region = "SA"
    record.currency = "SAR"
    offer = CanonicalProductEngine().normalize_record(record)

    regional_offer = _apply_region_context(offer, region="SA", city="Riyadh")

    assert vendor_region_type("InfiniArc", "SA") == "local_saudi_vendor"
    assert regional_offer.serves_saudi is True
    assert regional_offer.is_local_stock is True
    assert "local_stock" in regional_offer.flags
    assert "local_warranty_available" in regional_offer.flags
    assert "unknown_shipping" in regional_offer.flags
    assert "delivery_unclear" in regional_offer.flags
    assert "warranty_unclear" in regional_offer.flags


def test_canonicalization_validation_reports_single_group_for_variants() -> None:
    response = CanonicalizationValidationService(FakePricingRepository()).validate(  # type: ignore[arg-type]
        category="GPU",
        names=[
            "RTX4070SUPER",
            "RTX 4070 Super",
            "GeForce RTX 4070 SUPER",
            "NVIDIA GeForce RTX 4070 Super",
        ],
    )

    assert len(response.groups) == 1


def test_gpu_category_guardrails_reject_prebuilts_and_bundles() -> None:
    rejected_titles = [
        "MXZ AMD Ryzen 7 RTX 4070 Super 1TB SSD 16GB DDR5 Memory",
        "MXZ Intel i5 RTX 4070 Super 1TB SSD 16GB DDR4 Memory",
        "RTX 4070 Super Gaming PC",
        "RTX 4070 Super Desktop Computer",
    ]

    for title in rejected_titles:
        classification = classify_product_type(_record_with_title(title), "GPU")
        assert not classification.accepted
        assert classification.product_type in {"prebuilt_pc", "bundle"}
        assert classification.rejected_reasons


def test_gpu_positive_matching_accepts_standalone_cards() -> None:
    accepted_titles = [
        "Zotac Gaming GeForce RTX 4070 Super 12GB GDDR6X Twin Edge Video Card",
        "ASUS Dual GeForce RTX 4070 Super Graphics Card",
        "NVIDIA GeForce RTX 4070 Super Founders Edition",
    ]

    for title in accepted_titles:
        classification = classify_product_type(_record_with_title(title), "GPU")
        assert classification.accepted
        assert classification.product_type == "standalone_gpu"
        assert classification.confidence >= 0.7


def test_gpu_canonicalization_keeps_board_partner_cards_separate_from_founders() -> None:
    engine = CanonicalProductEngine()
    zotac = engine.normalize_record(
        _record_with_title("Zotac Gaming GeForce RTX 4070 Super 12GB GDDR6X Twin Edge Video Card")
    )
    asus = engine.normalize_record(_record_with_title("ASUS Dual GeForce RTX 4070 Super Graphics Card"))
    founders = engine.normalize_record(_record_with_title("NVIDIA GeForce RTX 4070 Super Founders Edition"))

    assert zotac.product.canonical_key != founders.product.canonical_key
    assert asus.product.canonical_key != founders.product.canonical_key
    assert zotac.product.canonical_key != asus.product.canonical_key
    assert zotac.product.specs["gpu_family_key"] == founders.product.specs["gpu_family_key"]
    assert asus.product.specs["gpu_family_key"] == founders.product.specs["gpu_family_key"]


def test_gpu_canonicalization_prefers_board_partner_over_nvidia_chipset_brand() -> None:
    engine = CanonicalProductEngine()
    pny = engine.normalize_record(_record_with_title("PNY NVIDIA GeForce RTX 4070 Super XLR8 Gaming Graphics Card"))
    zotac = engine.normalize_record(_record_with_title("ZOTAC NVIDIA GeForce RTX 4070 Super Graphic Card"))

    assert pny.product.brand == "PNY"
    assert pny.product.canonical_key.startswith("GPU|PNY|")
    assert zotac.product.brand == "Zotac"
    assert zotac.product.canonical_key.startswith("GPU|ZOTAC|")


def test_gpu_family_price_window_flags_and_rejects_extreme_4070_super_prices() -> None:
    low_offer = CanonicalProductEngine().normalize_record(_record(price=350))
    low_report = PriceQualityValidator().validate_offer(low_offer)
    assert low_report.accepted
    assert "suspicious_price_below_gpu_family_market_range" in low_report.flags

    extreme_offer = CanonicalProductEngine().normalize_record(_record(price=1400))
    extreme_report = PriceQualityValidator().validate_offer(extreme_offer)
    assert not extreme_report.accepted
    assert "suspicious_price_outside_gpu_family_hard_bounds" in extreme_report.rejected_reasons


def test_cpu_category_guardrails_reject_systems_boards_bundles_and_coolers() -> None:
    cases = {
        "AMD Ryzen 7 7800X3D Gaming PC RTX 4070 1TB SSD 32GB RAM": "prebuilt_pc",
        "AMD Ryzen 7 7800X3D B650 Motherboard DDR5 Bundle": "bundle",
        "Ryzen 7 7800X3D B650 motherboard combo": "bundle",
        "Ryzen 7 7800X3D gaming PC": "prebuilt_pc",
        "7800X3D cooler": "cooler",
        "Ryzen 7 7800X3D DDR5 bundle": "bundle",
        "ASUS B650 AM5 Motherboard for Ryzen 7000 CPUs": "motherboard",
        "AIO Liquid CPU Cooler for Ryzen 7 7800X3D": "cooler",
    }

    for title, expected_type in cases.items():
        classification = classify_product_type(_cpu_record_with_title(title), "CPU")
        assert not classification.accepted
        assert classification.product_type == expected_type
        assert classification.rejected_reasons


def test_cpu_positive_matching_accepts_standalone_7800x3d_processor() -> None:
    classification = classify_product_type(
        _cpu_record_with_title("AMD Ryzen 7 7800X3D 8-Core AM5 Desktop Processor"),
        "CPU",
    )

    assert classification.accepted
    assert classification.product_type == "standalone_cpu"
    assert classification.confidence >= 0.7


def test_cpu_tray_or_engineering_sample_rejected_when_condition_unclear() -> None:
    for title in ("AMD Ryzen 7 7800X3D Tray CPU", "Ryzen 7 7800X3D engineering sample"):
        classification = classify_product_type(_cpu_record_with_title(title), "CPU")

        assert not classification.accepted
        assert classification.product_type == "unknown_low_confidence"
        assert "cpu_tray_or_engineering_sample_condition_unclear" in classification.rejected_reasons


def test_cpu_7800x3d_title_variants_share_canonical_key() -> None:
    engine = CanonicalProductEngine()
    titles = [
        "AMD Ryzen 7 7800X3D",
        "Ryzen 7 7800X3D Processor",
        "AMD R7 7800X3D",
        "7800X3D CPU",
        "AMD Ryzen 7 7800X3D 8-Core Processor",
    ]

    keys = [engine.normalize_record(_cpu_record_with_title(title, brand=None)).product.canonical_key for title in titles]

    assert set(keys) == {"CPU|AMD|RYZEN_7_7800X3D"}


def test_cpu_target_model_gate_rejects_non_matching_processor() -> None:
    matching = CanonicalProductEngine().normalize_record(
        _cpu_record_with_title("AMD Ryzen 7 7800X3D 8-Core AM5 Desktop Processor")
    )
    wrong = CanonicalProductEngine().normalize_record(
        _cpu_record_with_title("AMD Ryzen 7 7700X 8-Core AM5 Desktop Processor")
    )

    assert _target_model_rejections("Ryzen 7 7800X3D processor", "CPU", matching) == []
    assert _target_model_rejections("Ryzen 7 7800X3D processor", "CPU", wrong) == [
        "cpu_listing_does_not_match_requested_model"
    ]


def test_cpu_model_gate_handles_localized_7800x3d_titles_without_english_ryzen() -> None:
    localized = CanonicalProductEngine().normalize_record(
        _cpu_record_with_title("معالج كمبيوتر مكتبي اي ام دي رايزون 7-7800X3D بدون مروحة")
    )

    assert localized.product.specs["cpu_model_key"] == "AMD_RYZEN_7_7800X3D"
    assert _target_model_rejections("Ryzen 7 7800X3D processor", "CPU", localized) == []


def test_cpu_saudi_region_context_and_quality_preserve_uncertainty() -> None:
    offer = CanonicalProductEngine().normalize_record(
        _cpu_record_with_title("AMD Ryzen 7 7800X3D 8-Core AM5 Desktop Processor", price=1599)
    )
    regional_offer = _apply_region_context(offer, region="SA", city="Riyadh")
    quality = PriceQualityValidator().validate_offer(regional_offer)

    assert regional_offer.product.specs["cpu_model_key"] == "AMD_RYZEN_7_7800X3D"
    assert regional_offer.product.specs["product_type"] == "standalone_cpu"
    assert regional_offer.region == "SA"
    assert regional_offer.item_price_sar == 1599
    assert regional_offer.final_landed_price_sar == 1599
    assert regional_offer.recommended_saudi_price_candidate is False
    assert "vat_unknown" in regional_offer.flags
    assert "unknown_shipping" in regional_offer.flags
    assert quality.accepted


def test_storage_category_guardrails_accept_standalone_990_pro_2tb() -> None:
    accepted_titles = [
        "Samsung 990 Pro 2TB NVMe SSD",
        "Samsung 990 PRO 2TB PCIe 4.0 M.2",
        "Samsung 990 Pro 2TB Internal SSD",
        "Samsung 990 Pro 2TB NVMe M.2 2280",
    ]

    for title in accepted_titles:
        classification = classify_product_type(_storage_record_with_title(title), "Storage")
        assert classification.accepted
        assert classification.product_type == "standalone_storage"
        assert classification.confidence >= 0.7


def test_storage_category_guardrails_reject_external_systems_and_bundles() -> None:
    cases = {
        "Samsung 990 Pro 2TB external USB enclosure": "accessory",
        "Samsung 990 Pro 2TB laptop bundle": "prebuilt_pc",
        "Samsung 990 Pro 2TB B650 motherboard DDR5 bundle": "bundle",
        "Samsung 990 Pro 2TB hard drive HDD": "unknown_low_confidence",
        "Samsung 990 Pro 2TB refurbished NVMe SSD": "unknown_low_confidence",
    }

    for title, expected_type in cases.items():
        classification = classify_product_type(_storage_record_with_title(title), "Storage")
        assert not classification.accepted
        assert classification.product_type == expected_type
        assert classification.rejected_reasons


def test_storage_990_pro_2tb_variants_share_canonical_key_and_family() -> None:
    engine = CanonicalProductEngine()
    titles = [
        "Samsung 990 Pro 2TB NVMe SSD",
        "Samsung 990 PRO 2TB PCIe 4.0 M.2",
        "Samsung 990 Pro 2TB Internal SSD",
        "Samsung 990 Pro 2TB NVMe M.2 2280",
    ]

    offers = [engine.normalize_record(_storage_record_with_title(title)) for title in titles]

    assert {offer.product.canonical_key for offer in offers} == {"STORAGE|SAMSUNG|990_PRO|2TB|NVME|M2"}
    assert {offer.product.specs["storage_family_key"] for offer in offers} == {"SAMSUNG_990_PRO_2TB_NVME_M2"}


def test_storage_target_model_gate_rejects_wrong_capacity_model_and_heatsink_variant() -> None:
    matching = CanonicalProductEngine().normalize_record(_storage_record_with_title("Samsung 990 Pro 2TB NVMe SSD"))
    wrong_capacity = CanonicalProductEngine().normalize_record(_storage_record_with_title("Samsung 990 Pro 1TB NVMe SSD"))
    wrong_model = CanonicalProductEngine().normalize_record(_storage_record_with_title("Samsung 980 Pro 2TB NVMe SSD"))
    evo = CanonicalProductEngine().normalize_record(_storage_record_with_title("Samsung 990 Evo 2TB NVMe SSD"))
    heatsink = CanonicalProductEngine().normalize_record(_storage_record_with_title("Samsung 990 Pro 2TB with Heatsink NVMe SSD"))
    arabic_heatsink = CanonicalProductEngine().normalize_record(
        _storage_record_with_title("990 Pro \u0645\u0632\u0648\u062f \u0628\u0645\u0628\u062f\u062f \u062d\u0631\u0627\u0631\u064a NVMe M.2 SSD \u0628\u0633\u0639\u0629 2.0 \u062a\u064a\u0631\u0627\u0628\u0627\u064a\u062a 2.0 TB", brand=None)
    )

    assert storage_model_key_from_title("Samsung 990 Pro 2TB NVMe SSD") == "SAMSUNG_990_PRO_2TB_NVME_M2"
    assert _target_model_rejections("Samsung 990 Pro 2TB NVMe SSD", "Storage", matching) == []
    assert _target_model_rejections("Samsung 990 Pro 2TB NVMe SSD", "Storage", wrong_capacity) == [
        "storage_listing_does_not_match_requested_model"
    ]
    assert _target_model_rejections("Samsung 990 Pro 2TB NVMe SSD", "Storage", wrong_model) == [
        "storage_listing_does_not_match_requested_model"
    ]
    assert _target_model_rejections("Samsung 990 Pro 2TB NVMe SSD", "Storage", evo) == [
        "storage_listing_does_not_match_requested_model"
    ]
    assert _target_model_rejections("Samsung 990 Pro 2TB NVMe SSD", "Storage", heatsink) == [
        "storage_heatsink_variant_not_requested"
    ]
    assert _target_model_rejections("Samsung 990 Pro 2TB NVMe SSD", "Storage", arabic_heatsink) == [
        "storage_heatsink_variant_not_requested"
    ]
    assert arabic_heatsink.product.brand == "Samsung"
    assert arabic_heatsink.product.canonical_key == "STORAGE|SAMSUNG|990_PRO|2TB|NVME|M2|HEATSINK"


def test_storage_saudi_region_context_and_quality_preserve_uncertainty() -> None:
    offer = CanonicalProductEngine().normalize_record(
        _storage_record_with_title("Samsung 990 Pro 2TB NVMe M.2 2280 SSD", price=699)
    )
    regional_offer = _apply_region_context(offer, region="SA", city="Riyadh")
    quality = PriceQualityValidator().validate_offer(regional_offer)

    assert regional_offer.product.specs["storage_model_key"] == "SAMSUNG_990_PRO_2TB_NVME_M2"
    assert regional_offer.product.specs["product_type"] == "standalone_storage"
    assert regional_offer.region == "SA"
    assert regional_offer.item_price_sar == 699
    assert regional_offer.final_landed_price_sar == 699
    assert "vat_unknown" in regional_offer.flags
    assert "unknown_shipping" in regional_offer.flags
    assert quality.accepted


def test_storage_alternative_2tb_nvme_models_are_accepted_for_generic_query() -> None:
    titles = [
        ("WD Black SN850X 2TB NVMe SSD PCIe 4.0", "WD_BLACK_SN850X_2TB_NVME_M2"),
        ("Kingston KC3000 2TB NVMe M.2 SSD", "KINGSTON_KC3000_2TB_NVME_M2"),
        ("Crucial T500 2TB PCIe Gen4 NVMe SSD", "CRUCIAL_T500_2TB_NVME_M2"),
        ("Lexar NM790 2TB NVMe SSD", "LEXAR_NM790_2TB_NVME_M2"),
        ("Crucial P5 Plus 2TB NVMe SSD", "CRUCIAL_P5_PLUS_2TB_NVME_M2"),
    ]
    for title, expected_key in titles:
        offer = CanonicalProductEngine().normalize_record(_storage_record_with_title(title, brand=None))
        assert offer.product.specs["storage_model_key"] == expected_key
        assert _target_model_rejections("2TB NVMe SSD PCIe 4.0", "Storage", offer) == []


def test_storage_generic_2tb_nvme_query_rejects_wrong_capacity_external_and_sata() -> None:
    cases = [
        "WD Black SN850X 1TB NVMe SSD PCIe 4.0",
        "Samsung 990 Pro 4TB NVMe SSD",
        "Crucial MX500 2TB SATA SSD",
        "Samsung T7 2TB external USB SSD",
    ]
    for title in cases:
        record = _storage_record_with_title(title, brand=None)
        classification = classify_product_type(record, "Storage")
        offer = CanonicalProductEngine().normalize_record(record)
        rejected = [*classification.rejected_reasons, *_target_model_rejections("2TB NVMe SSD PCIe 4.0", "Storage", offer)]
        assert rejected


def test_ram_category_guardrails_accept_standalone_32gb_ddr5_6000_kits() -> None:
    accepted_titles = [
        "32GB DDR5 6000 RAM",
        "2x16GB DDR5 6000MHz Memory Kit",
        "DDR5 32GB 6000 CL30 Desktop Memory",
        "Corsair Vengeance 32GB DDR5 6000",
        "G.Skill Trident Z5 32GB DDR5 6000",
    ]

    for title in accepted_titles:
        classification = classify_product_type(_ram_record_with_title(title), "RAM")
        assert classification.accepted
        assert classification.product_type == "standalone_ram"
        assert classification.confidence >= 0.7


def test_ram_category_guardrails_reject_non_target_memory_and_bundles() -> None:
    cases = {
        "32GB DDR4 6000 RAM kit": "unknown_low_confidence",
        "32GB DDR5 6000 SO-DIMM laptop memory": "laptop",
        "32GB DDR5 6000 motherboard bundle": "bundle",
        "32GB DDR5 6000 Gaming PC": "prebuilt_pc",
        "DDR5 RGB controller accessory": "accessory",
        "32GB DDR5 6000 refurbished memory": "unknown_low_confidence",
    }

    for title, expected_type in cases.items():
        classification = classify_product_type(_ram_record_with_title(title), "RAM")
        assert not classification.accepted
        assert classification.product_type == expected_type
        assert classification.rejected_reasons


def test_ram_canonicalization_keeps_brand_variants_separate_but_links_family() -> None:
    engine = CanonicalProductEngine()
    generic = engine.normalize_record(_ram_record_with_title("32GB DDR5 6000 RAM kit", brand=None))
    corsair = engine.normalize_record(_ram_record_with_title("Corsair Vengeance 32GB DDR5 6000", brand="Corsair"))
    gskill = engine.normalize_record(_ram_record_with_title("G.Skill Trident Z5 32GB DDR5 6000", brand="G.Skill"))

    assert ram_family_key_from_title("32GB DDR5 6000 RAM kit") == "RAM_DDR5_32GB_6000"
    assert generic.product.canonical_key == "RAM|DDR5|32GB|6000"
    assert corsair.product.canonical_key == "RAM|CORSAIR|VENGEANCE|DDR5|32GB|6000"
    assert gskill.product.canonical_key == "RAM|GSKILL|TRIDENT_Z5|DDR5|32GB|6000"
    assert {offer.product.specs["ram_family_key"] for offer in (generic, corsair, gskill)} == {
        "RAM_DDR5_32GB_6000"
    }
    assert corsair.product.canonical_key != gskill.product.canonical_key


def test_ram_target_family_gate_rejects_wrong_memory_type_capacity_speed_and_laptop() -> None:
    matching = CanonicalProductEngine().normalize_record(
        _ram_record_with_title("Corsair Vengeance 32GB DDR5 6000 2x16GB Memory Kit", brand="Corsair")
    )
    ddr4 = CanonicalProductEngine().normalize_record(_ram_record_with_title("Corsair Vengeance 32GB DDR4 6000"))
    sixty_four = CanonicalProductEngine().normalize_record(_ram_record_with_title("Corsair Vengeance 64GB DDR5 6000"))
    sixteen = CanonicalProductEngine().normalize_record(_ram_record_with_title("Corsair Vengeance 16GB DDR5 6000"))
    slower = CanonicalProductEngine().normalize_record(_ram_record_with_title("Corsair Vengeance 32GB DDR5 5600"))
    sodimm = CanonicalProductEngine().normalize_record(_ram_record_with_title("Corsair 32GB DDR5 6000 SO-DIMM Laptop Memory"))

    assert _target_model_rejections("32GB DDR5 6000 RAM kit", "RAM", matching) == []
    for offer in (ddr4, sixty_four, sixteen, slower, sodimm):
        assert _target_model_rejections("32GB DDR5 6000 RAM kit", "RAM", offer)


def test_ram_compatibility_fields_and_saudi_quality_preserve_uncertainty() -> None:
    offer = CanonicalProductEngine().normalize_record(
        _ram_record_with_title("Corsair Vengeance 32GB DDR5 6000 CL30 2x16GB Desktop Memory Kit", price=449, brand="Corsair")
    )
    regional_offer = _apply_region_context(offer, region="SA", city="Riyadh")
    quality = PriceQualityValidator().validate_offer(regional_offer)

    assert regional_offer.product.specs["memory_type"] == "DDR5"
    assert regional_offer.product.specs["capacity_gb"] == 32
    assert regional_offer.product.specs["speed_mhz"] == 6000
    assert regional_offer.product.specs["speed_mt_s"] == 6000
    assert regional_offer.product.specs["kit_config"] == "2x16"
    assert regional_offer.product.specs["cas_latency"] == 30
    assert regional_offer.product.specs["desktop_or_laptop"] == "desktop"
    assert regional_offer.product.specs["ram_family_key"] == "RAM_DDR5_32GB_6000"
    assert regional_offer.product.specs["product_type"] == "standalone_ram"
    assert regional_offer.region == "SA"
    assert regional_offer.item_price_sar == 449
    assert regional_offer.final_landed_price_sar == 449
    assert "vat_unknown" in regional_offer.flags
    assert "unknown_shipping" in regional_offer.flags
    assert quality.accepted


def test_psu_category_guardrails_accept_standalone_850w_gold_power_supplies() -> None:
    accepted_titles = [
        "850W Gold fully modular PSU",
        "Corsair RM850x 850W Gold PSU",
        "Corsair RM850e 850W 80+ Gold Fully Modular",
        "Seasonic Focus GX-850",
        "MSI MAG A850GL PCIe5 850W Gold",
        "Thermaltake Toughpower GF 850W Gold",
    ]

    for title in accepted_titles:
        classification = classify_product_type(_psu_record_with_title(title), "PSU")
        assert classification.accepted
        assert classification.product_type == "standalone_psu"
        assert classification.confidence >= 0.7


def test_psu_category_guardrails_reject_ups_chargers_adapters_cables_and_case_bundles() -> None:
    cases = {
        "APC UPS battery backup 850VA": "accessory",
        "850W laptop charger power adapter": "accessory",
        "850W power adapter": "accessory",
        "Corsair PSU cable extension kit": "accessory",
        "RGB cable for power supply": "accessory",
        "ATX case with PSU included": "bundle",
        "850W Gold PSU refurbished": "unknown_low_confidence",
    }

    for title, expected_type in cases.items():
        classification = classify_product_type(_psu_record_with_title(title), "PSU")
        assert not classification.accepted
        assert classification.product_type == expected_type
        assert classification.rejected_reasons


def test_psu_canonicalization_keeps_vendor_models_separate_but_links_family() -> None:
    engine = CanonicalProductEngine()
    generic = engine.normalize_record(_psu_record_with_title("850W Gold fully modular PSU"))
    corsair = engine.normalize_record(_psu_record_with_title("Corsair RM850x 850W 80+ Gold Fully Modular", brand="Corsair"))
    seasonic = engine.normalize_record(_psu_record_with_title("Seasonic Focus GX-850", brand="Seasonic"))
    msi = engine.normalize_record(_psu_record_with_title("MSI MAG A850GL PCIe5 850W Gold", brand="MSI"))
    asus = engine.normalize_record(_psu_record_with_title("Asus Prime Ap-850G Fully Modular ATX Power Supply 850w 80 Plus Gold", brand="ASUS"))
    nzxt = engine.normalize_record(_psu_record_with_title("NZXT C850 80 Plus Gold Fully Modular Power Supply 850W", brand="NZXT"))

    assert psu_family_key_from_title("850W Gold fully modular PSU") == "PSU_850W_GOLD_FULLY_MODULAR"
    assert generic.product.canonical_key == "PSU|850W|80PLUS_GOLD|FULLY_MODULAR"
    assert corsair.product.canonical_key == "PSU|CORSAIR|RM850X|850W|GOLD|FULLY_MODULAR"
    assert seasonic.product.canonical_key == "PSU|SEASONIC|FOCUS_GX|850W|GOLD|FULLY_MODULAR"
    assert msi.product.canonical_key == "PSU|MSI|MAG_A850GL|850W|GOLD|PCIE5"
    assert asus.product.canonical_key == "PSU|ASUS|PRIME_AP850G|850W|GOLD|FULLY_MODULAR"
    assert nzxt.product.canonical_key == "PSU|NZXT|C850|850W|GOLD|FULLY_MODULAR"
    assert len({offer.product.canonical_key for offer in (generic, corsair, seasonic, msi, asus, nzxt)}) == 6
    assert {offer.product.specs["psu_family_key"] for offer in (generic, corsair, seasonic, msi, asus, nzxt)} == {
        "PSU_850W_GOLD_FULLY_MODULAR"
    }


def test_psu_target_family_gate_rejects_wrong_wattage_efficiency_and_modularity() -> None:
    matching = CanonicalProductEngine().normalize_record(
        _psu_record_with_title("Corsair RM850x 850W 80+ Gold Fully Modular PSU", brand="Corsair")
    )
    six_fifty = CanonicalProductEngine().normalize_record(_psu_record_with_title("Corsair RM650x 650W Gold Fully Modular PSU"))
    thousand = CanonicalProductEngine().normalize_record(_psu_record_with_title("Corsair RM1000x 1000W Gold Fully Modular PSU"))
    bronze = CanonicalProductEngine().normalize_record(_psu_record_with_title("850W 80+ Bronze Fully Modular PSU"))
    semi = CanonicalProductEngine().normalize_record(_psu_record_with_title("850W 80+ Gold Semi Modular PSU"))

    assert _target_model_rejections("850W Gold fully modular PSU", "PSU", matching) == []
    for offer in (six_fifty, thousand, bronze, semi):
        assert _target_model_rejections("850W Gold fully modular PSU", "PSU", offer)


def test_psu_compatibility_fields_and_saudi_quality_preserve_uncertainty() -> None:
    offer = CanonicalProductEngine().normalize_record(
        _psu_record_with_title("MSI MAG A850GL PCIe5 850W 80+ Gold Fully Modular ATX 3.0 PSU", price=599, brand="MSI")
    )
    regional_offer = _apply_region_context(offer, region="SA", city="Riyadh")
    quality = PriceQualityValidator().validate_offer(regional_offer)

    assert regional_offer.product.specs["wattage_w"] == 850
    assert regional_offer.product.specs["continuous_wattage"] == 850
    assert regional_offer.product.specs["efficiency_rating"] == "GOLD"
    assert regional_offer.product.specs["modularity"] == "FULLY_MODULAR"
    assert regional_offer.product.specs["atx_version"] == "ATX_3_0"
    assert regional_offer.product.specs["pcie_5_support"] is True
    assert regional_offer.product.specs["form_factor"] == "ATX"
    assert regional_offer.product.specs["psu_family_key"] == "PSU_850W_GOLD_FULLY_MODULAR"
    assert regional_offer.product.specs["product_type"] == "standalone_psu"
    assert regional_offer.region == "SA"
    assert regional_offer.item_price_sar == 599
    assert regional_offer.final_landed_price_sar == 599
    assert "vat_unknown" in regional_offer.flags
    assert "unknown_shipping" in regional_offer.flags
    assert quality.accepted


def test_case_category_guardrails_accept_standalone_pc_cases() -> None:
    accepted_titles = [
        "Corsair 4000D Airflow ATX Mid Tower Case",
        "Corsair 4000D Airflow Tempered Glass Case",
        "ATX Mid Tower PC Case",
        "Airflow Gaming Case",
    ]

    for title in accepted_titles:
        classification = classify_product_type(_case_record_with_title(title), "Case")
        assert classification.accepted
        assert classification.product_type == "standalone_case"
        assert classification.confidence >= 0.7


def test_case_category_guardrails_reject_systems_accessories_and_enclosures() -> None:
    cases = {
        "Corsair 4000D Airflow Gaming PC": "prebuilt_pc",
        "Corsair 4000D Airflow desktop pc": "prebuilt_pc",
        "Corsair case fan only": "accessory",
        "Corsair RGB controller for case": "accessory",
        "Corsair power supply only": "accessory",
        "Laptop bag case": "accessory",
        "External enclosure case": "accessory",
        "Server rack chassis": "accessory",
        "Corsair 4000D Airflow bundle with motherboard": "bundle",
    }

    for title, expected_type in cases.items():
        classification = classify_product_type(_case_record_with_title(title), "Case")
        assert not classification.accepted
        assert classification.product_type == expected_type
        assert classification.rejected_reasons


def test_case_4000d_airflow_canonicalization_and_model_separation() -> None:
    engine = CanonicalProductEngine()
    airflow = engine.normalize_record(
        _case_record_with_title("Corsair 4000D Airflow ATX Mid Tower Case", brand="Corsair")
    )
    glass = engine.normalize_record(
        _case_record_with_title("Corsair 4000D Airflow Tempered Glass Case", brand="Corsair")
    )
    rgb = engine.normalize_record(_case_record_with_title("Corsair 4000X RGB ATX Case", brand="Corsair"))
    icue_rgb_v2 = engine.normalize_record(_case_record_with_title("CORSAIR icue 4000D RGB Airflow V2 Mid-Tower Case", brand="Corsair"))
    five_thousand = engine.normalize_record(_case_record_with_title("Corsair 5000D Airflow ATX Case", brand="Corsair"))

    assert case_family_key_from_title("Corsair 4000D Airflow ATX case") == "CASE_CORSAIR_4000D_AIRFLOW"
    assert airflow.product.canonical_key == "CASE|CORSAIR|4000D_AIRFLOW|ATX|MID_TOWER"
    assert glass.product.canonical_key == "CASE|CORSAIR|4000D_AIRFLOW|ATX|MID_TOWER"
    assert airflow.product.specs["case_family_key"] == "CASE_CORSAIR_4000D_AIRFLOW"
    assert rgb.product.specs["case_family_key"] != airflow.product.specs["case_family_key"]
    assert icue_rgb_v2.product.specs["case_family_key"] != airflow.product.specs["case_family_key"]
    assert five_thousand.product.specs["case_family_key"] != airflow.product.specs["case_family_key"]


def test_case_target_gate_rejects_wrong_corsair_models() -> None:
    matching = CanonicalProductEngine().normalize_record(
        _case_record_with_title("Corsair 4000D Airflow ATX Mid Tower Case", brand="Corsair")
    )
    rgb = CanonicalProductEngine().normalize_record(_case_record_with_title("Corsair 4000X RGB ATX Case", brand="Corsair"))
    icue_rgb_v2 = CanonicalProductEngine().normalize_record(_case_record_with_title("CORSAIR icue 4000D RGB Airflow V2 Mid-Tower Case", brand="Corsair"))
    five_thousand = CanonicalProductEngine().normalize_record(_case_record_with_title("Corsair 5000D Airflow ATX Case", brand="Corsair"))

    assert _target_model_rejections("Corsair 4000D Airflow ATX case", "Case", matching) == []
    assert _target_model_rejections("Corsair 4000D Airflow ATX case", "Case", rgb) == [
        "case_listing_does_not_match_requested_model"
    ]
    assert _target_model_rejections("Corsair 4000D Airflow ATX case", "Case", icue_rgb_v2) == [
        "case_listing_does_not_match_requested_model"
    ]
    assert _target_model_rejections("Corsair 4000D Airflow ATX case", "Case", five_thousand) == [
        "case_listing_does_not_match_requested_model"
    ]


def test_case_compatibility_fields_and_saudi_quality_preserve_uncertainty() -> None:
    offer = CanonicalProductEngine().normalize_record(
        _case_record_with_title("Corsair 4000D Airflow ATX Mid Tower Tempered Glass Case Black", price=399, brand="Corsair")
    )
    regional_offer = _apply_region_context(offer, region="SA", city="Riyadh")
    quality = PriceQualityValidator().validate_offer(regional_offer)

    assert regional_offer.product.specs["supported_motherboard_form_factors"] == ["ATX", "mATX", "ITX"]
    assert regional_offer.product.specs["case_type"] == "mid_tower"
    assert regional_offer.product.specs["max_gpu_length_mm"] == 360
    assert regional_offer.product.specs["max_cpu_cooler_height_mm"] == 170
    assert regional_offer.product.specs["radiator_support_front_mm"] == 360
    assert regional_offer.product.specs["psu_form_factor"] == "ATX"
    assert regional_offer.product.specs["airflow_focus"] is True
    assert regional_offer.product.specs["tempered_glass"] is True
    assert regional_offer.product.specs["color"] == "black"
    assert regional_offer.product.specs["case_family_key"] == "CASE_CORSAIR_4000D_AIRFLOW"
    assert regional_offer.product.specs["product_type"] == "standalone_case"
    assert regional_offer.region == "SA"
    assert regional_offer.item_price_sar == 399
    assert "vat_unknown" in regional_offer.flags
    assert "unknown_shipping" in regional_offer.flags
    assert quality.accepted


def test_cooler_category_guardrails_accept_cpu_coolers() -> None:
    accepted = [
        "240mm AIO CPU cooler AM5",
        "Corsair H100i 240mm AIO Liquid CPU Cooler",
        "NZXT Kraken 240 RGB AIO CPU Cooler",
        "DeepCool LS520 240mm AIO Liquid Cooler",
        "Thermalright Peerless Assassin CPU Cooler AM5",
    ]
    for title in accepted:
        classification = classify_product_type(_cooler_record_with_title(title), "Cooler")
        assert classification.accepted, title
        assert classification.product_type == "standalone_cooler"


def test_cooler_category_guardrails_reject_accessories_and_wrong_cooling() -> None:
    rejected = {
        "Corsair 120mm case fan only": "accessory",
        "laptop cooling pad": "accessory",
        "Arctic MX-6 thermal paste": "accessory",
        "RGB fan controller": "accessory",
        "GPU cooler replacement": "accessory",
    }
    for title, expected_type in rejected.items():
        classification = classify_product_type(_cooler_record_with_title(title), "Cooler")
        assert not classification.accepted
        assert classification.product_type == expected_type
        assert classification.rejected_reasons


def test_cooler_canonicalization_and_family_separation() -> None:
    engine = CanonicalProductEngine()
    generic = engine.normalize_record(_cooler_record_with_title("240mm AIO CPU cooler AM5"))
    corsair = engine.normalize_record(_cooler_record_with_title("Corsair H100i 240mm AIO Liquid CPU Cooler", brand="Corsair"))
    nzxt = engine.normalize_record(_cooler_record_with_title("NZXT Kraken 240 AIO CPU Cooler", brand="NZXT"))
    gamertek = engine.normalize_record(_cooler_record_with_title("GamerTek Aqua Frost 240MM AIO Liquid Cooler"))
    air = engine.normalize_record(
        _cooler_record_with_title("Thermalright Peerless Assassin CPU Cooler AM5", brand="Thermalright")
    )
    aio_360 = engine.normalize_record(_cooler_record_with_title("Corsair H150i 360mm AIO CPU Cooler", brand="Corsair"))

    assert cooler_family_key_from_title("240mm AIO CPU cooler AM5") == "COOLER_AIO_240MM_AM5"
    assert generic.product.specs["cooler_family_key"] == "COOLER_AIO_240MM_AM5"
    assert corsair.product.specs["cooler_family_key"] == "COOLER_AIO_240MM_AM5"
    assert nzxt.product.specs["cooler_family_key"] == "COOLER_AIO_240MM_AM5"
    assert gamertek.product.canonical_key == "COOLER|GAMERTEK|AQUA_FROST|AIO|240MM"
    assert air.product.specs["cooler_family_key"] == "COOLER_AIR_DUAL_TOWER_AM5"
    assert aio_360.product.specs["cooler_family_key"] == "COOLER_AIO_360MM"
    assert air.product.canonical_key != corsair.product.canonical_key
    assert aio_360.product.specs["cooler_family_key"] != corsair.product.specs["cooler_family_key"]


def test_cooler_compatibility_fields_and_saudi_quality_preserve_uncertainty() -> None:
    aio = CanonicalProductEngine().normalize_record(
        _cooler_record_with_title("DeepCool LS520 240mm AIO Liquid CPU Cooler AM5", price=429, brand="DeepCool")
    )
    air = CanonicalProductEngine().normalize_record(
        _cooler_record_with_title("DeepCool AK620 CPU Air Cooler AM5", price=299, brand="DeepCool")
    )
    regional_offer = _apply_region_context(aio, region="SA", city="Riyadh")
    quality = PriceQualityValidator().validate_offer(regional_offer)

    assert aio.product.specs["cooler_type"] == "aio_liquid"
    assert aio.product.specs["radiator_size_mm"] == 240
    assert aio.product.specs["radiator_fan_count"] == 2
    assert "AM5" in aio.product.specs["supported_sockets"]
    assert aio.product.specs["tdp_rating_w"] >= 180
    assert air.product.specs["cooler_type"] == "air"
    assert air.product.specs["cooler_height_mm"] == 160
    assert regional_offer.product.specs["product_type"] == "standalone_cooler"
    assert quality.accepted
    assert "unknown_shipping" in quality.flags
    assert "unknown_vat" in quality.flags


def test_cooler_target_gate_rejects_wrong_aio_size_but_allows_air_alternative() -> None:
    aio_240 = CanonicalProductEngine().normalize_record(
        _cooler_record_with_title("DeepCool LS520 240mm AIO Liquid CPU Cooler AM5", brand="DeepCool")
    )
    aio_360 = CanonicalProductEngine().normalize_record(
        _cooler_record_with_title("Arctic Liquid Freezer III 360mm AIO CPU Cooler AM5", brand="Arctic")
    )
    air = CanonicalProductEngine().normalize_record(
        _cooler_record_with_title("Thermalright Peerless Assassin CPU Cooler AM5", brand="Thermalright")
    )

    assert _target_model_rejections("240mm AIO CPU cooler AM5", "Cooler", aio_240) == []
    assert _target_model_rejections("240mm AIO CPU cooler AM5", "Cooler", aio_360) == [
        "cooler_aio_radiator_size_does_not_match_requested_target"
    ]
    assert _target_model_rejections("240mm AIO CPU cooler AM5", "Cooler", air) == []


def test_motherboard_classification_accepts_b650_am5_ddr5_and_rejects_wrong_targets() -> None:
    accepted_titles = [
        "B650 AM5 DDR5 ATX Motherboard",
        "ASUS PRIME B650M-A WIFI II",
        "MSI B650 Tomahawk WiFi AM5 DDR5",
        "ASUS TUF Gaming B650-PLUS WiFi AM5",
        "Gigabyte B650 Aorus Elite AX AM5 DDR5",
        "ASRock B650 Steel Legend WiFi AM5 DDR5",
    ]
    for title in accepted_titles:
        classification = classify_product_type(_motherboard_record_with_title(title), "Motherboard")
        assert classification.accepted, title
        assert classification.product_type == "standalone_motherboard"

    rejected_titles = [
        "Intel LGA1700 Z790 DDR5 Motherboard",
        "ASUS B650 DDR4 Motherboard",
        "A620 AM5 DDR5 Motherboard",
        "Ryzen 7 7800X3D B650 motherboard bundle",
        "B650 AM5 DDR5 gaming PC",
        "B650 motherboard backplate accessory",
    ]
    for title in rejected_titles:
        classification = classify_product_type(_motherboard_record_with_title(title), "Motherboard")
        assert not classification.accepted, title
        assert classification.rejected_reasons


def test_motherboard_canonicalization_and_compatibility_fields() -> None:
    engine = CanonicalProductEngine()
    generic = engine.normalize_record(_motherboard_record_with_title("B650 AM5 DDR5 ATX Motherboard"))
    prime = engine.normalize_record(_motherboard_record_with_title("ASUS PRIME B650M-A WIFI II", brand="ASUS"))
    msi = engine.normalize_record(
        _motherboard_record_with_title("MSI B650 Tomahawk WiFi AM5 DDR5 ATX Motherboard", brand="MSI")
    )
    asus = engine.normalize_record(
        _motherboard_record_with_title("ASUS TUF Gaming B650-PLUS WiFi AM5 DDR5 ATX", brand="ASUS")
    )
    gigabyte = engine.normalize_record(
        _motherboard_record_with_title("Gigabyte B650 Aorus Elite AX AM5 DDR5 ATX", brand="Gigabyte")
    )

    assert motherboard_family_key_from_title("B650 AM5 DDR5 motherboard") == "MOTHERBOARD_B650_AM5_DDR5"
    assert generic.product.specs["motherboard_family_key"] == "MOTHERBOARD_B650_AM5_DDR5"
    assert prime.product.canonical_key == "MOTHERBOARD|ASUS|PRIME_B650M_A_WIFI_II|AM5|DDR5|MATX"
    assert prime.product.specs["socket"] == "AM5"
    assert prime.product.specs["memory_type"] == "DDR5"
    assert prime.product.specs["form_factor"] == "mATX"
    assert prime.product.specs["wifi"] is True
    assert msi.product.canonical_key == "MOTHERBOARD|MSI|B650_TOMAHAWK_WIFI|AM5|DDR5|ATX"
    assert asus.product.canonical_key == "MOTHERBOARD|ASUS|TUF_B650_PLUS_WIFI|AM5|DDR5|ATX"
    assert gigabyte.product.canonical_key == "MOTHERBOARD|GIGABYTE|B650_AORUS_ELITE_AX|AM5|DDR5|ATX"
    assert msi.product.specs["socket"] == "AM5"
    assert msi.product.specs["chipset"] == "B650"
    assert msi.product.specs["memory_type"] == "DDR5"
    assert msi.product.specs["form_factor"] == "ATX"
    assert msi.product.specs["m2_slots"] >= 1
    assert msi.product.specs["pcie_x16_slots"] >= 1
    assert msi.product.specs["wifi"] is True


def test_motherboard_target_gate_rejects_non_b650_am5_ddr5_boards() -> None:
    matching = CanonicalProductEngine().normalize_record(
        _motherboard_record_with_title("MSI B650 Tomahawk WiFi AM5 DDR5 ATX Motherboard", brand="MSI")
    )
    x670 = CanonicalProductEngine().normalize_record(
        _motherboard_record_with_title("ASUS X670 AM5 DDR5 ATX Motherboard", brand="ASUS")
    )
    intel = CanonicalProductEngine().normalize_record(
        _motherboard_record_with_title("MSI Z790 LGA1700 DDR5 ATX Motherboard", brand="MSI")
    )
    ddr4 = CanonicalProductEngine().normalize_record(
        _motherboard_record_with_title("ASUS B650 AM5 DDR4 ATX Motherboard", brand="ASUS")
    )

    assert _target_model_rejections("B650 AM5 DDR5 motherboard", "Motherboard", matching) == []
    assert _target_model_rejections("B650 AM5 DDR5 motherboard", "Motherboard", x670)
    assert _target_model_rejections("B650 AM5 DDR5 motherboard", "Motherboard", intel)
    assert _target_model_rejections("B650 AM5 DDR5 motherboard", "Motherboard", ddr4)


def test_motherboard_saudi_price_quality_preserves_uncertainty() -> None:
    offer = CanonicalProductEngine().normalize_record(
        _motherboard_record_with_title("MSI B650 Tomahawk WiFi AM5 DDR5 ATX Motherboard", price=899, brand="MSI")
    )
    regional_offer = _apply_region_context(offer, region="SA", city="Riyadh")
    quality = PriceQualityValidator().validate_offer(regional_offer)

    assert regional_offer.product.specs["product_type"] == "standalone_motherboard"
    assert regional_offer.product.specs["motherboard_family_key"] == "MOTHERBOARD_B650_AM5_DDR5"
    assert regional_offer.item_price_sar == 899
    assert quality.accepted
    assert "unknown_shipping" in quality.flags
    assert "unknown_vat" in quality.flags


def test_swappa_and_ebay_receive_marketplace_risk() -> None:
    swappa = _record_with_title("Zotac RTX 4070 Super 12GB Graphics Card")
    swappa.vendor_name = "Swappa"
    swappa.source.source = "SerpAPI Google Shopping"
    ebay = _record_with_title("ASUS Dual RTX 4070 Super Graphics Card")
    ebay.vendor_name = "eBay - new.techies"

    for record in (swappa, ebay):
        market = classify_listing_market(record)
        assert market.seller_type == "marketplace"
        assert market.listing_condition == "unknown"
        assert market.marketplace_risk_score >= 0.65
        assert "price_requires_review" in market.flags


def test_unknown_marketplace_price_does_not_become_recommended() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="Swappa",
                price=479,
                condition="unknown",
                seller_type="marketplace",
                risk=0.84,
                flags=["marketplace_listing", "condition_unknown", "price_requires_review"],
            )
        ]
    )

    assert rollups["lowest_market_price"] == 479
    assert rollups["current_recommended_price"] is None
    assert rollups["price_status"] == "active"


def test_unknown_condition_listing_does_not_become_recommended_automatically() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="Regional Store",
                price=620,
                condition="unknown",
                seller_type="unknown",
                risk=0.48,
                flags=["condition_unknown", "price_requires_review"],
            )
        ]
    )

    assert rollups["lowest_market_price"] == 620
    assert rollups["current_recommended_price"] is None


def test_new_trusted_retailer_outranks_cheaper_unknown_marketplace() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="eBay - seller",
                price=500,
                condition="unknown",
                seller_type="marketplace",
                risk=0.84,
                flags=["marketplace_listing", "condition_unknown", "price_requires_review"],
            ),
            _snapshot(vendor="BestBuy", price=540, condition="new", seller_type="retailer", risk=0.08),
        ]
    )

    assert rollups["lowest_market_price"] == 500
    assert rollups["current_recommended_price"] == 540
    assert rollups["current_recommended_vendor"] == "BestBuy"


def test_regional_price_summary_keeps_sa_and_us_currency_context_separate() -> None:
    sa_rollups = _price_rollups(
        [
            _snapshot(
                vendor="Amazon.sa",
                price=2399,
                condition="new",
                seller_type="retailer",
                risk=0.12,
                currency="SAR",
                region="SA",
                final_landed_price=2399,
                is_local_stock=True,
            )
        ],
        region="SA",
    )
    us_rollups = _price_rollups(
        [
            _snapshot(
                vendor="BestBuy",
                price=599,
                condition="new",
                seller_type="retailer",
                risk=0.08,
                currency="USD",
                region="US",
                final_landed_price=599,
                is_local_stock=True,
            )
        ],
        region="US",
    )

    assert sa_rollups["region"] == "SA"
    assert sa_rollups["current_recommended_currency"] == "SAR"
    assert us_rollups["region"] == "US"
    assert us_rollups["current_recommended_currency"] == "USD"


def test_saudi_local_vendor_outranks_cheaper_imported_unknown_shipping_listing() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="Newegg Global",
                price=2100,
                condition="new",
                seller_type="retailer",
                risk=0.24,
                currency="SAR",
                region="SA",
                final_landed_price=2100,
                final_landed_price_sar=2100,
                item_price_sar=2100,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="unknown_warranty",
                local_stock_status="imported_stock",
                vendor_region_type="international_vendor",
                flags=["imported_listing", "unknown_shipping", "unknown_vat"],
            ),
            _snapshot(
                vendor="Jarir",
                price=2450,
                condition="new",
                seller_type="retailer",
                risk=0.12,
                currency="SAR",
                region="SA",
                final_landed_price=2450,
                final_landed_price_sar=2450,
                item_price_sar=2450,
                shipping_cost_sar=0,
                is_local_stock=True,
                vat_status="vat_included",
                shipping_status="free_shipping",
                warranty_status="local_warranty",
                local_stock_status="local_stock",
                vendor_region_type="local_saudi_vendor",
                recommended_saudi_price_candidate=True,
                local_stock_confidence=0.92,
                warranty_confidence=0.78,
                delivery_confidence=0.86,
            ),
        ],
        region="SA",
    )

    assert rollups["lowest_market_price"] == 2100
    assert rollups["current_recommended_price"] == 2450
    assert rollups["current_recommended_vendor"] == "Jarir"


def test_saudi_unknown_vat_and_shipping_lower_price_confidence() -> None:
    clear_rollups = _price_rollups(
        [
            _snapshot(
                vendor="Amazon.sa",
                price=2399,
                condition="new",
                seller_type="retailer",
                risk=0.12,
                currency="SAR",
                region="SA",
                final_landed_price=2399,
                final_landed_price_sar=2399,
                item_price_sar=2399,
                is_local_stock=True,
                vat_status="vat_included",
                shipping_status="free_shipping",
                warranty_status="local_warranty",
                local_stock_status="local_stock",
                vendor_region_type="local_saudi_vendor",
                recommended_saudi_price_candidate=True,
                local_stock_confidence=0.92,
                warranty_confidence=0.78,
                delivery_confidence=0.86,
            )
        ],
        region="SA",
    )
    uncertain_rollups = _price_rollups(
        [
            _snapshot(
                vendor="Amazon.sa",
                price=2399,
                condition="new",
                seller_type="retailer",
                risk=0.12,
                currency="SAR",
                region="SA",
                final_landed_price=2399,
                final_landed_price_sar=2399,
                item_price_sar=2399,
                is_local_stock=True,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="local_warranty",
                local_stock_status="local_stock",
                vendor_region_type="local_saudi_vendor",
                local_stock_confidence=0.92,
                warranty_confidence=0.78,
                delivery_confidence=0.22,
            )
        ],
        region="SA",
    )

    assert clear_rollups["price_confidence"] is not None
    assert uncertain_rollups["price_confidence"] is not None
    assert clear_rollups["price_confidence"] > uncertain_rollups["price_confidence"]


def test_saudi_recommendation_uses_final_landed_price_sar() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="PCZone Saudi",
                price=2350,
                condition="new",
                seller_type="retailer",
                risk=0.16,
                currency="SAR",
                region="SA",
                final_landed_price=2400,
                final_landed_price_sar=2400,
                item_price_sar=2350,
                shipping_cost_sar=50,
                is_local_stock=True,
                vat_status="vat_included",
                shipping_status="paid_shipping",
                warranty_status="local_warranty",
                local_stock_status="local_stock",
                vendor_region_type="local_saudi_vendor",
                recommended_saudi_price_candidate=True,
            )
        ],
        region="SA",
    )

    assert rollups["current_recommended_price"] == 2400
    assert rollups["current_recommended_currency"] == "SAR"


def test_saudi_region_context_adds_field_evidence_for_market_quality() -> None:
    record = _record_with_title("ASUS Dual GeForce RTX 4070 Super Graphics Card", price=2399, brand="ASUS")
    record.vendor_name = "Amazon.sa"
    record.vendor_region = "SA"
    record.region = "SA"
    record.currency = "SAR"
    offer = CanonicalProductEngine().normalize_record(record)

    regional_offer = _apply_region_context(offer, region="SA", city="Riyadh")
    evidence_fields = {item.field for item in regional_offer.field_evidence}

    assert {"region", "vendor_region_type", "vat_status", "shipping_status", "warranty_status"}.issubset(
        evidence_fields
    )
    assert regional_offer.region == "SA"
    assert regional_offer.item_price_sar == 2399


def test_product_search_result_handles_missing_canonical_key() -> None:
    result = _search_result(
        {
            "id": "seed:4070-super",
            "canonical_key": None,
            "name": "NVIDIA GeForce RTX 4070 SUPER Founders Edition",
            "brand": "NVIDIA",
            "category": "GPU",
            "model": None,
            "image_url": None,
            "data_origin": "seed",
            "price_status": "unavailable",
            "flags": ["stale_seed_product"],
            "stale": True,
            "best_value": False,
            "previous_price": None,
        }
    )

    assert result.canonical_key is None
    assert result.price_status == "unavailable"
    assert result.stale


def test_stale_seed_product_ranks_below_live_priced_product() -> None:
    live = _search_result(
        {
            "id": "product-live",
            "canonical_key": "GPU|ZOTAC|NVIDIA_GEFORCE_RTX_4070_SUPER|TWINEDGE",
            "name": "Zotac RTX 4070 Super Twin Edge",
            "brand": "Zotac",
            "category": "GPU",
            "model": "RTX 4070 Super Twin Edge",
            "image_url": None,
            "data_origin": "live",
            "price_status": "active",
            "flags": [],
            "current_recommended_price": 549,
            "current_recommended_currency": "USD",
            "current_recommended_vendor": "BestBuy",
            "stale": False,
            "best_value": False,
            "previous_price": None,
        }
    )
    seed = _search_result(
        {
            "id": "seed",
            "canonical_key": None,
            "name": "NVIDIA GeForce RTX 4070 SUPER Founders Edition",
            "brand": "NVIDIA",
            "category": "GPU",
            "model": None,
            "image_url": None,
            "data_origin": "seed",
            "price_status": "unavailable",
            "flags": ["stale_seed_product"],
            "stale": True,
            "best_value": False,
            "previous_price": None,
        }
    )

    assert sorted([seed, live], key=_search_sort_key)[0].id == "product-live"


def test_cpu_product_first_results_keep_stable_product_and_cheapest_seller_price() -> None:
    image_rich = _search_result(
        {
            "id": "cpu-image",
            "canonical_key": "CPU|AMD|RYZEN_7_7800X3D",
            "name": "AMD Ryzen 7 7800X3D Processor",
            "brand": "AMD",
            "category": "CPU",
            "model": "Ryzen 7 7800X3D",
            "summary_specs": {"socket": "AM5", "cores": 8, "threads": 16, "boost_clock_ghz": 5.0},
            "image_url": "https://cdn.example.test/7800x3d.jpg",
            "data_origin": "live",
            "price_status": "active",
            "flags": [],
            "current_recommended_price": 1799,
            "current_recommended_currency": "SAR",
            "current_recommended_vendor": "OnlyPc-sa.com",
            "lowest_market_price": 1799,
            "lowest_market_currency": "SAR",
            "lowest_market_vendor": "OnlyPc-sa.com",
            "stale": False,
            "best_value": False,
            "previous_price": None,
        }
    )
    cheapest = _search_result(
        {
            "id": "cpu-cheapest",
            "canonical_key": "CPU|AMD|7800X3D|socket:AM5",
            "name": "7-7800X3D, 5.0, 104, 100100000910WOF",
            "brand": "AMD",
            "category": "CPU",
            "model": "7800X3D",
            "summary_specs": {},
            "image_url": None,
            "data_origin": "live",
            "price_status": "active",
            "flags": [],
            "current_recommended_price": 1499,
            "current_recommended_currency": "SAR",
            "current_recommended_vendor": "Computer Palace",
            "lowest_market_price": 1499,
            "lowest_market_currency": "SAR",
            "lowest_market_vendor": "Computer Palace",
            "stale": False,
            "best_value": False,
            "previous_price": None,
        }
    )

    grouped = _cpu_product_first_results([image_rich, cheapest])

    assert len(grouped) == 1
    assert grouped[0].id == "cpu-cheapest"
    assert grouped[0].canonical_key == "CPU|AMD|RYZEN_7_7800X3D"
    assert grouped[0].name == "AMD Ryzen 7 7800X3D"
    assert grouped[0].current_recommended_price == 1499
    assert grouped[0].current_recommended_vendor == "Computer Palace"
    assert grouped[0].image_url == "https://cdn.example.test/7800x3d.jpg"
    assert grouped[0].summary_specs["socket"] == "AM5"


def test_techpowerup_cpu_specs_import_ignores_codename_and_released() -> None:
    row = {
        "name": "Ryzen 7 7800X3D",
        "codename": "Raphael",
        "cores_threads": "8 / 16",
        "clock": "4.2 to 5 GHz",
        "socket": "Socket AM5",
        "process": "5 nm",
        "l3_cache": "96 MB",
        "tdp": "120 W",
        "released": "Jan 2023",
        "image_url": "https://cdn.example.test/7800x3d.jpg",
    }

    product = _cpu_specs_import_product(CpuSpecsImportRow.model_validate(row))

    assert product is not None
    assert product.canonical_key == "CPU|AMD|RYZEN_7_7800X3D"
    assert product.name == "AMD Ryzen 7 7800X3D"
    assert product.summary_specs == {
        "socket": "AM5",
        "cores": 8,
        "threads": 16,
        "base_clock_ghz": 4.2,
        "boost_clock_ghz": 5.0,
        "process_nm": 5.0,
        "l3_cache_mb": 96.0,
        "tdp_w": 120.0,
    }
    assert "codename" not in product.summary_specs
    assert "released" not in product.summary_specs


@pytest.mark.parametrize(
    ("name", "canonical_key"),
    [
        ("Core Ultra 7 270K Plus", "CPU|INTEL|CORE_ULTRA_7_270K_PLUS"),
        ("Core Ultra X7 358H", "CPU|INTEL|CORE_ULTRA_X7_358H"),
        ("Ryzen AI Max+ 395", "CPU|AMD|RYZEN_AI_MAX_395"),
        ("Ryzen AI 9 HX 370", "CPU|AMD|RYZEN_AI_9_HX_370"),
        ("Ryzen 5 PRO 4650G", "CPU|AMD|RYZEN_5_PRO_4650G"),
        ("Ryzen Threadripper PRO 9995WX", "CPU|AMD|THREADRIPPER_9995WX"),
        ("FX-8350", "CPU|AMD|FX_8350"),
        ("Processor N100", "CPU|INTEL|PROCESSOR_N100"),
        ("Core 2 Duo E8400", "CPU|INTEL|CORE_2_DUO_E8400"),
    ],
)
def test_cpu_specs_import_supports_wider_cpu_names(name: str, canonical_key: str) -> None:
    product = _cpu_specs_import_product(
        CpuSpecsImportRow(
            name=name,
            cores_threads="8 / 16",
            clock="3.4 to 4.6 GHz",
            socket="Socket AM5",
            process="5 nm",
            l3_cache="32 MB",
            tdp="65 W",
        )
    )

    assert product is not None
    assert product.canonical_key == canonical_key


class _CaptureDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute_query(self, query: str, **params: object):
        self.calls.append((query, params))
        return [{"id": params.get("product_id", "ok")}], None, None


def test_cpu_specs_import_links_brand_and_socket_nodes() -> None:
    driver = _CaptureDriver()

    response = Neo4jPricingRepository(driver).import_cpu_specs(
        rows=[
            CpuSpecsImportRow(
                name="Ryzen 7 7800X3D",
                cores_threads="8 / 16",
                clock="4.2 to 5 GHz",
                socket="Socket AM5",
                process="5 nm",
                l3_cache="96 MB",
                tdp="120 W",
            )
        ],
        dry_run=False,
    )

    assert response.imported_count == 1
    query, params = driver.calls[0]
    assert "MERGE (brand:Brand {name: $brand})" in query
    assert "MERGE (p)-[:MADE_BY]->(brand)" in query
    assert "MERGE (socket:Socket {name: $socket})" in query
    assert "MERGE (p)-[:REQUIRES_SOCKET]->(socket)" in query
    assert params["brand"] == "AMD"
    assert params["socket"] == "AM5"


def test_pricing_schema_includes_brand_and_socket_constraints() -> None:
    driver = _CaptureDriver()

    Neo4jPricingRepository(driver).apply_schema()
    statements = "\n".join(query for query, _ in driver.calls)

    assert "CREATE CONSTRAINT brand_name IF NOT EXISTS" in statements
    assert "CREATE CONSTRAINT socket_name IF NOT EXISTS" in statements


def test_saudi_trusted_local_listing_can_be_recommended_with_uncertainty() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="OnlyPc-sa.com",
                price=3399,
                condition="unknown",
                seller_type="unknown",
                risk=0.42,
                currency="SAR",
                region="SA",
                final_landed_price=3399,
                final_landed_price_sar=3399,
                item_price_sar=3399,
                is_local_stock=True,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="local_warranty",
                local_stock_status="local_stock",
                vendor_region_type="local_saudi_vendor",
            )
        ],
        region="SA",
    )

    assert rollups["current_recommended_price"] == 3399
    assert rollups["current_recommended_vendor"] == "OnlyPc-sa.com"
    assert rollups["recommended_level"] == "acceptable_with_risk"
    assert "shipping" in (rollups["recommended_reason"] or "").lower()


def test_saudi_lowest_and_recommended_price_can_differ() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="eBay",
                price=3100,
                condition="unknown",
                seller_type="marketplace",
                risk=0.86,
                currency="SAR",
                region="SA",
                final_landed_price=3100,
                final_landed_price_sar=3100,
                item_price_sar=3100,
                is_imported=True,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="seller_warranty",
                local_stock_status="imported_stock",
                vendor_region_type="international_vendor",
                flags=["marketplace_listing", "imported_listing", "price_requires_review"],
            ),
            _snapshot(
                vendor="Mahally",
                price=3399,
                condition="unknown",
                seller_type="unknown",
                risk=0.42,
                currency="SAR",
                region="SA",
                final_landed_price=3399,
                final_landed_price_sar=3399,
                item_price_sar=3399,
                is_local_stock=True,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="local_warranty",
                local_stock_status="local_stock",
                vendor_region_type="local_saudi_vendor",
            ),
        ],
        region="SA",
    )

    assert rollups["lowest_market_price"] == 3100
    assert rollups["current_recommended_price"] == 3399
    assert rollups["current_recommended_vendor"] == "Mahally"
    assert rollups["lowest_price_warning"]


def test_saudi_ebay_imported_listing_not_recommended_when_local_option_exists() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="eBay",
                price=3000,
                condition="unknown",
                seller_type="marketplace",
                risk=0.86,
                currency="SAR",
                region="SA",
                final_landed_price=3000,
                final_landed_price_sar=3000,
                item_price_sar=3000,
                is_imported=True,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="seller_warranty",
                local_stock_status="imported_stock",
                vendor_region_type="international_vendor",
                flags=["marketplace_listing", "imported_listing", "price_requires_review"],
            ),
            _snapshot(
                vendor="InfiniArc",
                price=3500,
                condition="unknown",
                seller_type="retailer",
                risk=0.28,
                currency="SAR",
                region="SA",
                final_landed_price=3500,
                final_landed_price_sar=3500,
                item_price_sar=3500,
                is_local_stock=True,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="local_warranty",
                local_stock_status="local_stock",
                vendor_region_type="local_saudi_vendor",
            ),
        ],
        region="SA",
    )

    assert rollups["current_recommended_vendor"] == "InfiniArc"
    assert rollups["current_recommended_vendor"] != "eBay"


def test_saudi_recommended_price_empty_only_when_all_options_too_uncertain() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="Unknown Store",
                price=3300,
                condition="unknown",
                seller_type="unknown",
                risk=0.5,
                currency="SAR",
                region="SA",
                final_landed_price=3300,
                final_landed_price_sar=None,
                item_price_sar=None,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="unknown_warranty",
                local_stock_status="unknown_stock",
                vendor_region_type="unknown_vendor",
            )
        ],
        region="SA",
    )

    assert rollups["lowest_market_price"] == 3300
    assert rollups["current_recommended_price"] is None


def test_saudi_listing_decision_exposes_unknown_vat_shipping_and_warranty_warnings() -> None:
    rollups = _price_rollups(
        [
            _snapshot(
                vendor="OnlyPc",
                price=3399,
                condition="unknown",
                seller_type="unknown",
                risk=0.42,
                currency="SAR",
                region="SA",
                final_landed_price=3399,
                final_landed_price_sar=3399,
                item_price_sar=3399,
                is_local_stock=True,
                vat_status="vat_unknown",
                shipping_status="unknown_shipping",
                warranty_status="unknown_warranty",
                local_stock_status="local_stock",
                vendor_region_type="local_saudi_vendor",
            )
        ],
        region="SA",
    )

    assert rollups["price_confidence"] is not None
    assert rollups["recommended_level"] == "acceptable_with_risk"
    assert "vat" in (rollups["recommended_reason"] or "").lower()


def test_saudi_vendor_trust_profiles_cover_local_gcc_and_marketplace_vendors() -> None:
    assert vendor_trust_profile("InfiniArc", "SA").vendor_region_type == "local_saudi_vendor"
    assert vendor_trust_profile("OnlyPc-sa.com", "SA").vendor_region_type == "local_saudi_vendor"
    mahally = vendor_trust_profile("Mahally", "SA")
    assert mahally.vendor_region_type == "local_saudi_vendor"
    assert mahally.marketplace_risk_default >= 0.35
    ebay = vendor_trust_profile("eBay", "SA")
    assert ebay.trust_tier == "low"
    assert ebay.marketplace_risk_default >= 0.8
    microless = vendor_trust_profile("Microless", "SA")
    assert microless.vendor_region_type == "gcc_vendor"
    assert microless.serves_saudi is True
