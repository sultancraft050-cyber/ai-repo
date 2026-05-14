from __future__ import annotations

from datetime import UTC, datetime

from app.models.pricing import (
    PriceOffer,
    ProductIdentity,
    SourceMetadata,
    SourceTier,
    SourceType,
    VendorIdentity,
)
from app.services.product_image_processing import (
    ProcessedProductImage,
    ProductImageProcessor,
    attach_processed_image,
)


def _offer() -> PriceOffer:
    source = SourceMetadata(
        source="Unit Test",
        source_type=SourceType.RETAILER_API,
        tier=SourceTier.RETAILER_API,
        trust_score=0.8,
        freshness_score=0.8,
        timestamp=datetime.now(UTC),
    )
    return PriceOffer(
        product=ProductIdentity(
            canonical_key="CPU|AMD|RYZEN_7_7800X3D",
            name="AMD Ryzen 7 7800X3D",
            brand="AMD",
            category="CPU",
            model="RYZEN_7_7800X3D",
            normalized_model="RYZEN77800X3D",
            image_url="https://cdn.example.test/raw.jpg",
        ),
        vendor=VendorIdentity(id="vendor", name="Vendor", api_type=SourceType.RETAILER_API, trust_score=0.8),
        price=1499,
        currency="SAR",
        availability="in_stock",
        timestamp=source.timestamp,
        source=source,
        image_url="https://cdn.example.test/raw.jpg",
    )


def test_image_processor_noops_when_disabled() -> None:
    processor = ProductImageProcessor(
        enabled=False,
        storage_dir="/tmp/unused",
        public_base_url="https://cdn.example.test/processed",
        max_bytes=1000,
    )

    assert processor.process("https://cdn.example.test/raw.jpg", canonical_key="CPU|AMD|TEST") is None


class _FakeProcessor:
    def process(self, image_url: str | None, *, canonical_key: str | None = None):
        assert image_url == "https://cdn.example.test/raw.jpg"
        assert canonical_key == "CPU|AMD|RYZEN_7_7800X3D"
        return ProcessedProductImage(
            source_url=image_url,
            processed_image_url="https://cdn.example.test/processed/cpu.png",
            storage_path="/tmp/cpu.png",
            background_removed=True,
        )


def test_attach_processed_image_sets_offer_and_product_url() -> None:
    offer = attach_processed_image(_offer(), processor=_FakeProcessor())  # type: ignore[arg-type]

    assert offer.processed_image_url == "https://cdn.example.test/processed/cpu.png"
    assert offer.product.processed_image_url == "https://cdn.example.test/processed/cpu.png"
