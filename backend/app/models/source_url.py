from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.pricing import (
    Availability,
    BuyRecommendationLevel,
    ListingCondition,
    ProductType,
    SellerType,
    ShippingStatus,
    VatStatus,
    VendorRegionType,
    WarrantyStatus,
)
from app.services.hardware_taxonomy import normalize_category
from app.services.region_config import normalize_region


KnownUrlRefreshSupport = Literal["true", "false", "policy_gated"]
SourcePolicyStatus = Literal["allowed", "policy_gated", "blocked", "unsupported"]


class ProductUrlSourcePolicy(BaseModel):
    source_name: str
    domains: list[str]
    region: str = "SA"
    manual_url_supported: bool = True
    known_url_refresh_supported: KnownUrlRefreshSupport = "true"
    broad_scraping_allowed: bool = False
    access_method: str = "public_product_url_preview"
    enabled: bool = True
    policy_status: SourcePolicyStatus = "allowed"
    notes: str


class SourceMatrixEntry(BaseModel):
    source_name: str
    region: str = "SA"
    manual_url_supported: bool
    known_url_refresh_supported: KnownUrlRefreshSupport
    broad_scraping_allowed: bool = False
    access_method: str
    enabled: bool
    policy_status: SourcePolicyStatus
    health: Literal["healthy", "configured", "not_configured", "degraded", "failed", "policy_gated"]
    last_success: datetime | None = None
    last_failure: datetime | None = None
    source_policy: str


class ProductUrlPreviewRequest(BaseModel):
    url: str
    region: str = "SA"
    category: str
    dry_run: bool = True

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        return normalize_region(value)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        return normalize_category(value)


class ProductUrlIngestRequest(BaseModel):
    url: str
    region: str = "SA"
    category: str
    approved: bool = False

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        return normalize_region(value)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        return normalize_category(value)


class ProductUrlRefreshRequest(BaseModel):
    region: str = "SA"
    category: str | None = None
    vendor: str | None = None
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        return normalize_region(value)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str | None) -> str | None:
        return normalize_category(value) if value else None


class ProductUrlPreviewResponse(BaseModel):
    raw_title: str | None = None
    normalized_name: str | None = None
    price: float | None = None
    currency: str | None = None
    image_url: str | None = None
    availability: Availability = "unknown"
    vendor_name: str | None = None
    product_url: str
    normalized_url: str
    category: str
    product_type: ProductType = "unknown_low_confidence"
    product_type_confidence: float = Field(default=0, ge=0, le=1)
    canonical_key: str | None = None
    region: str = "SA"
    source_name: str | None = None
    source_policy_status: SourcePolicyStatus = "unsupported"
    listing_condition: ListingCondition = "unknown"
    seller_type: SellerType = "unknown"
    vendor_region_type: VendorRegionType = "unknown_vendor"
    marketplace_risk_score: float = Field(default=0.5, ge=0, le=1)
    vat_status: VatStatus = "vat_unknown"
    shipping_status: ShippingStatus = "unknown_shipping"
    warranty_status: WarrantyStatus = "unknown_warranty"
    item_price_sar: float | None = None
    final_landed_price_sar: float | None = None
    price_confidence: float | None = None
    recommendation_level: BuyRecommendationLevel = "insufficient_data"
    accepted: bool = False
    rejected_reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProductUrlIngestResponse(BaseModel):
    status: Literal["ingested", "rejected"]
    product_id: str | None = None
    vendor_id: str | None = None
    price_snapshot_id: str | None = None
    product_url: str
    normalized_url: str
    audit_event_id: str | None = None
    preview: ProductUrlPreviewResponse
    trace_id: str


class KnownProductUrlView(BaseModel):
    url: str
    normalized_url: str
    source_name: str
    vendor_name: str
    region: str
    category: str
    approved: bool
    refresh_allowed: bool
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error_sanitized: str | None = None
    source_policy_status: SourcePolicyStatus = "allowed"
    last_price: float | None = None
    last_currency: str | None = None


class ProductUrlRefreshItem(BaseModel):
    normalized_url: str
    vendor_name: str
    category: str
    status: Literal["refreshed", "skipped", "failed"]
    price_snapshot_id: str | None = None
    error: str | None = None


class ProductUrlRefreshResponse(BaseModel):
    status: Literal["completed"]
    region: str
    refreshed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    items: list[ProductUrlRefreshItem] = Field(default_factory=list)
    trace_id: str
