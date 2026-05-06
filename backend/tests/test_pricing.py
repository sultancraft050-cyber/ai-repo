from __future__ import annotations

from datetime import UTC, datetime

import os

from app.models.pricing import SourceMetadata, SourceProductRecord, SourceTier, SourceType
from app.services.hardware_taxonomy import classify_category, discovery_queries
from app.services.pricing_ingestion import CanonicalizationValidationService, PricingIngestionService
from app.services.pricing_normalization import CanonicalProductEngine, compact_model
from app.services.pricing_quality import PriceQualityValidator
from app.services import pricing_sources
from app.services.pricing_sources import SerpApiShoppingSource


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
    offer = CanonicalProductEngine().normalize_record(_record(price=200))
    report = PriceQualityValidator().validate_offer(offer, previous_price=1000)
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


class FakePricingRepository:
    def __init__(self) -> None:
        self.persisted = False

    def previous_price(self, product_id_or_key: str, vendor_id: str | None = None) -> float | None:
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
    assert not repository.persisted


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
