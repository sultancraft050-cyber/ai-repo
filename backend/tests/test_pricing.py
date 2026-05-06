from __future__ import annotations

from datetime import UTC, datetime

from app.models.pricing import SourceMetadata, SourceProductRecord, SourceTier, SourceType
from app.services.hardware_taxonomy import classify_category, discovery_queries
from app.services.pricing_normalization import CanonicalProductEngine, compact_model
from app.services.pricing_quality import PriceQualityValidator


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
