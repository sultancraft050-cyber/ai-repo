from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum, IntEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceTier(IntEnum):
    MANUFACTURER = 1
    RETAILER_API = 2
    AGGREGATOR_API = 3
    VERIFIED_SCRAPING = 4
    INFERRED = 5


class SourceType(str, Enum):
    MANUFACTURER = "manufacturer"
    RETAILER_API = "retailer_api"
    AGGREGATOR_API = "aggregator_api"
    VERIFIED_SCRAPING = "verified_scraping"
    INFERRED = "inferred"


Availability = Literal["in_stock", "out_of_stock", "preorder", "backorder", "unknown"]
ListingCondition = Literal["new", "used", "refurbished", "open_box", "unknown"]
SellerType = Literal["retailer", "manufacturer", "marketplace", "third_party", "unknown"]
PriceStatus = Literal["active", "stale", "unavailable"]
DataOrigin = Literal["live", "seed", "demo", "canonical_import", "community_dataset", "unknown"]
BuyRecommendationLevel = Literal[
    "recommended",
    "good_if_price_matters",
    "acceptable_with_risk",
    "not_recommended",
    "insufficient_data",
]
TrustTier = Literal["high", "medium", "low", "unknown"]
VatStatus = Literal["vat_included", "vat_excluded", "vat_unknown"]
ShippingStatus = Literal["free_shipping", "paid_shipping", "unknown_shipping", "pickup_only"]
WarrantyStatus = Literal["local_warranty", "seller_warranty", "manufacturer_warranty", "unknown_warranty"]
VendorRegionType = Literal[
    "local_saudi_vendor",
    "gcc_vendor",
    "international_vendor",
    "marketplace_vendor",
    "unknown_vendor",
    "local",
]
LocalStockStatus = Literal["local_stock", "gcc_stock", "imported_stock", "unknown_stock"]
ProductType = Literal[
    "standalone_gpu",
    "standalone_cpu",
    "standalone_storage",
    "standalone_ram",
    "standalone_psu",
    "standalone_case",
    "standalone_cooler",
    "standalone_motherboard",
    "prebuilt_pc",
    "laptop",
    "bundle",
    "motherboard",
    "cooler",
    "accessory",
    "unknown_low_confidence",
    "hardware_product",
]
PricingJobStatus = Literal[
    "queued",
    "running",
    "completed",
    "succeeded",
    "failed",
    "retrying",
    "cancelled",
    "requires_approval",
    "stale",
]
PricingJobKind = Literal["refresh", "sync", "discover", "enrich"]


class SourceMetadata(BaseModel):
    source: str
    source_type: SourceType
    tier: SourceTier
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trust_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    source_url: str | None = None


class FieldEvidence(BaseModel):
    field: str
    value: Any
    source: str
    timestamp: datetime
    trust_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    source_tier: SourceTier


class VendorIdentity(BaseModel):
    id: str
    name: str
    region: str = "US"
    api_type: SourceType
    trust_score: float = Field(ge=0, le=1)


class ProductIdentity(BaseModel):
    canonical_key: str
    name: str
    brand: str
    category: str
    model: str
    normalized_model: str
    specs: dict[str, Any] = Field(default_factory=dict)
    msrp: float | None = Field(default=None, ge=0)
    image_url: str | None = None
    processed_image_url: str | None = None

    @field_validator("name", "brand", "category", "model", "canonical_key")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("product identity fields cannot be empty")
        return value


class SourceProductRecord(BaseModel):
    source_product_id: str
    title: str
    brand: str | None = None
    category: str
    model: str | None = None
    price: float
    currency: str
    availability: Availability = "unknown"
    vendor_name: str
    vendor_region: str = "US"
    region: str = "US"
    city: str | None = None
    country_code: str | None = None
    product_url: str | None = None
    image_url: str | None = None
    processed_image_url: str | None = None
    shipping_cost: float = Field(default=0, ge=0)
    seller: str | None = None
    condition: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    specs: dict[str, Any] = Field(default_factory=dict)
    source: SourceMetadata


class PriceOffer(BaseModel):
    id: str = Field(default_factory=lambda: f"price-{uuid4()}")
    product: ProductIdentity
    vendor: VendorIdentity
    price: float = Field(gt=0)
    currency: str
    region: str = "US"
    country_code: str | None = None
    city: str | None = None
    raw_price: float | None = None
    item_price: float | None = None
    item_price_sar: float | None = None
    shipping_cost_sar: float | None = None
    final_landed_price: float | None = None
    final_landed_currency: str | None = None
    final_landed_price_sar: float | None = None
    vat_included: bool | None = None
    vat_status: VatStatus = "vat_unknown"
    shipping_status: ShippingStatus = "unknown_shipping"
    warranty_status: WarrantyStatus = "unknown_warranty"
    local_stock_status: LocalStockStatus = "unknown_stock"
    vendor_region_type: VendorRegionType = "unknown_vendor"
    estimated_vat: float | None = Field(default=None, ge=0)
    import_fee: float | None = Field(default=None, ge=0)
    estimated_delivery_days: int | None = Field(default=None, ge=0)
    seller_country: str | None = None
    is_local_stock: bool | None = None
    is_imported: bool | None = None
    serves_saudi: bool | None = None
    warranty_type: str | None = None
    local_warranty: bool | None = None
    region_rank_score: float | None = Field(default=None, ge=0, le=1)
    recommended_saudi_price_candidate: bool = False
    final_landed_price_confidence: float | None = Field(default=None, ge=0, le=1)
    price_completeness_score: float | None = Field(default=None, ge=0, le=1)
    trust_tier: TrustTier = "unknown"
    local_stock_confidence: float | None = Field(default=None, ge=0, le=1)
    warranty_confidence: float | None = Field(default=None, ge=0, le=1)
    delivery_confidence: float | None = Field(default=None, ge=0, le=1)
    availability: Availability
    timestamp: datetime
    shipping_cost: float = Field(default=0, ge=0)
    product_url: str | None = None
    image_url: str | None = None
    processed_image_url: str | None = None
    source_product_id: str | None = None
    seller: str | None = None
    condition: str | None = None
    listing_condition: ListingCondition = "unknown"
    seller_type: SellerType = "unknown"
    marketplace_risk_score: float = Field(default=0.5, ge=0, le=1)
    rating: float | None = Field(default=None, ge=0, le=5)
    source: SourceMetadata
    field_evidence: list[FieldEvidence] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)

    @field_validator("currency")
    @classmethod
    def iso_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value

    @field_validator("final_landed_currency")
    @classmethod
    def optional_iso_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        return value


class DataQualityReport(BaseModel):
    accepted: bool
    rejected_reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    anomaly_score: float = Field(default=0, ge=0, le=1)


class DiscoveryPreviewItem(BaseModel):
    raw_listing_name: str
    category: str
    product_type: ProductType
    product_type_confidence: float = Field(ge=0, le=1)
    normalized_name: str
    gpu_family_key: str | None = None
    ram_family_key: str | None = None
    psu_family_key: str | None = None
    case_family_key: str | None = None
    cooler_family_key: str | None = None
    motherboard_family_key: str | None = None
    canonical_product_key: str
    canonical_key: str
    canonical_product_id: str | None = None
    merge_decision: Literal["new_product", "merge_existing", "rejected"]
    confidence: float = Field(ge=0, le=1)
    reason: str
    vendor_name: str
    price: float
    currency: str
    region: str = "US"
    city: str | None = None
    final_landed_price: float | None = None
    final_landed_currency: str | None = None
    item_price_sar: float | None = None
    shipping_cost_sar: float | None = None
    final_landed_price_sar: float | None = None
    is_local_stock: bool | None = None
    is_imported: bool | None = None
    serves_saudi: bool | None = None
    vendor_region_type: VendorRegionType = "unknown_vendor"
    vat_included: bool | None = None
    vat_status: VatStatus = "vat_unknown"
    shipping_status: ShippingStatus = "unknown_shipping"
    warranty_status: WarrantyStatus = "unknown_warranty"
    local_stock_status: LocalStockStatus = "unknown_stock"
    estimated_vat: float | None = None
    warranty_type: str | None = None
    region_rank_score: float | None = None
    recommended_candidate: bool = False
    recommended_saudi_price_candidate: bool = False
    final_landed_price_confidence: float | None = Field(default=None, ge=0, le=1)
    price_completeness_score: float | None = Field(default=None, ge=0, le=1)
    trust_tier: TrustTier = "unknown"
    local_stock_confidence: float | None = None
    warranty_confidence: float | None = None
    delivery_confidence: float | None = None
    availability: Availability
    listing_condition: ListingCondition = "unknown"
    seller_type: SellerType = "unknown"
    marketplace_risk_score: float = Field(default=0.5, ge=0, le=1)
    accepted: bool
    rejected_reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    source: str
    source_type: SourceType
    trust_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    product_url: str | None = None
    image_url: str | None = None
    processed_image_url: str | None = None


class PriceSnapshotView(BaseModel):
    id: str
    vendor_id: str
    vendor_name: str
    price: float
    currency: str
    region: str = "US"
    country_code: str | None = None
    city: str | None = None
    raw_price: float | None = None
    item_price: float | None = None
    item_price_sar: float | None = None
    shipping_cost_sar: float | None = None
    final_landed_price: float | None = None
    final_landed_currency: str | None = None
    final_landed_price_sar: float | None = None
    vat_included: bool | None = None
    vat_status: VatStatus = "vat_unknown"
    shipping_status: ShippingStatus = "unknown_shipping"
    warranty_status: WarrantyStatus = "unknown_warranty"
    local_stock_status: LocalStockStatus = "unknown_stock"
    vendor_region_type: VendorRegionType = "unknown_vendor"
    estimated_vat: float | None = None
    import_fee: float | None = None
    estimated_delivery_days: int | None = None
    seller_country: str | None = None
    is_local_stock: bool | None = None
    is_imported: bool | None = None
    serves_saudi: bool | None = None
    warranty_type: str | None = None
    local_warranty: bool | None = None
    region_rank_score: float | None = None
    recommended_saudi_price_candidate: bool = False
    final_landed_price_confidence: float | None = None
    price_completeness_score: float | None = None
    trust_tier: TrustTier = "unknown"
    delivery_status: ShippingStatus = "unknown_shipping"
    confidence_score: float | None = None
    buy_recommendation_level: BuyRecommendationLevel = "insufficient_data"
    buy_recommendation_reason: str | None = None
    recommendation_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    local_stock_confidence: float | None = None
    warranty_confidence: float | None = None
    delivery_confidence: float | None = None
    availability: Availability
    timestamp: datetime
    shipping_cost: float = 0
    product_url: str | None = None
    source: str
    source_type: SourceType
    source_tier: SourceTier
    trust_score: float
    freshness_score: float
    stale: bool = False
    accepted: bool = True
    listing_condition: ListingCondition = "unknown"
    seller_type: SellerType = "unknown"
    marketplace_risk_score: float = Field(default=0.5, ge=0, le=1)
    flags: list[str] = Field(default_factory=list)


class ProductSearchResult(BaseModel):
    id: str
    canonical_key: str | None = None
    name: str
    brand: str | None = None
    category: str
    model: str | None = None
    summary_specs: dict[str, Any] = Field(default_factory=dict)
    image_url: str | None = None
    processed_image_url: str | None = None
    seller_count: int = 0
    cheapest_vendor: str | None = None
    cheapest_price_sar: float | None = None
    compatibility_tags: list[str] = Field(default_factory=list)
    catalog_state: Literal["saudi_priced", "catalog_only", "needs_spec_confirmation"] | None = None
    compatibility_ready: bool | None = None
    missing_compatibility_fields: list[str] = Field(default_factory=list)
    inferred_fields: list[str] = Field(default_factory=list)
    market_linked_count: int = 0
    data_origin: DataOrigin = "unknown"
    price_status: PriceStatus = "unavailable"
    flags: list[str] = Field(default_factory=list)
    region: str = "US"
    region_currency: str | None = None
    region_price_status: PriceStatus | None = None
    recommended_reason: str | None = None
    recommended_level: BuyRecommendationLevel | None = None
    price_confidence: float | None = None
    lowest_price_warning: str | None = None
    current_best_price: float | None = None
    current_best_currency: str | None = None
    current_best_vendor: str | None = None
    current_recommended_price: float | None = None
    current_recommended_currency: str | None = None
    current_recommended_vendor: str | None = None
    current_recommended_condition: ListingCondition | None = None
    current_recommended_seller_type: SellerType | None = None
    current_recommended_marketplace_risk_score: float | None = None
    lowest_market_price: float | None = None
    lowest_market_currency: str | None = None
    lowest_market_vendor: str | None = None
    lowest_market_condition: ListingCondition | None = None
    lowest_market_seller_type: SellerType | None = None
    lowest_marketplace_risk_score: float | None = None
    best_new_price: float | None = None
    best_new_currency: str | None = None
    best_new_vendor: str | None = None
    best_trusted_price: float | None = None
    best_trusted_currency: str | None = None
    best_trusted_vendor: str | None = None
    best_local_price: float | None = None
    best_local_currency: str | None = None
    best_local_vendor: str | None = None
    best_used_price: float | None = None
    best_used_currency: str | None = None
    best_used_vendor: str | None = None
    current_price_freshness_score: float | None = None
    current_price_trust_score: float | None = None
    current_price_timestamp: datetime | None = None
    stale: bool = False
    best_value: bool = False
    price_drop_percent: float | None = None


class ProductDetail(ProductSearchResult):
    specs: dict[str, Any] = Field(default_factory=dict)
    msrp: float | None = None
    field_evidence: list[FieldEvidence] = Field(default_factory=list)
    latest_prices: list[PriceSnapshotView] = Field(default_factory=list)


class ProductImageUpdateRequest(BaseModel):
    image_url: str = Field(min_length=8, max_length=2048)
    source_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("image_url must be an absolute http(s) URL")
        lowered = normalized.lower()
        if not any(
            lowered.split("?", 1)[0].endswith(extension)
            for extension in (".jpg", ".jpeg", ".png", ".webp", ".avif")
        ):
            raise ValueError("image_url must point to a common image file")
        return normalized


class ProductImageUpdateResponse(BaseModel):
    product_id: str
    image_url: str
    image_source_name: str | None = None
    updated: bool = True


class CpuSpecsImportRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=2, max_length=200)
    cores: int | None = Field(default=None, ge=1, le=512)
    threads: int | None = Field(default=None, ge=1, le=1024)
    cores_threads: str | None = Field(default=None, max_length=40)
    clock: str | None = Field(default=None, max_length=80)
    base_clock_ghz: float | None = Field(default=None, ge=0, le=10)
    boost_clock_ghz: float | None = Field(default=None, ge=0, le=10)
    socket: str | None = Field(default=None, max_length=80)
    process: str | None = Field(default=None, max_length=80)
    l3_cache: str | None = Field(default=None, max_length=80)
    tdp: str | None = Field(default=None, max_length=80)
    image_url: str | None = Field(default=None, max_length=2048)


class CpuSpecsImportRequest(BaseModel):
    rows: list[CpuSpecsImportRow] = Field(min_length=1, max_length=500)
    source_name: str = Field(default="TechPowerUp CPU Database", max_length=120)
    dry_run: bool = False


class CpuSpecsImportedProduct(BaseModel):
    canonical_key: str
    name: str
    brand: str
    model: str
    summary_specs: dict[str, Any] = Field(default_factory=dict)
    image_url: str | None = None


class CpuSpecsImportResponse(BaseModel):
    imported_count: int = 0
    skipped_count: int = 0
    ignored_fields: list[str] = Field(default_factory=lambda: ["codename", "released"])
    products: list[CpuSpecsImportedProduct] = Field(default_factory=list)
    skipped_rows: list[str] = Field(default_factory=list)
    dry_run: bool = False


class PriceHistoryPoint(BaseModel):
    timestamp: datetime
    vendor_name: str
    price: float
    currency: str
    availability: Availability
    trust_score: float
    freshness_score: float


class PricingRefreshRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    query: str | None = None
    category: str | None = None
    region: str = "SA"
    city: str | None = None
    providers: list[str] = Field(default_factory=list)
    wait: bool = False

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        from app.services.region_config import normalize_region

        return normalize_region(value)


class PricingRefreshResponse(BaseModel):
    job_ids: list[str]
    status: PricingJobStatus
    message: str
    accepted_snapshots: int = 0
    rejected_snapshots: int = 0
    stale_products: list[str] = Field(default_factory=list)


class PricingSyncRequest(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=50)
    category: str
    region: str = "SA"
    city: str | None = None
    providers: list[str] = Field(default_factory=list)
    limit_per_query: int = Field(default=8, ge=1, le=25)
    wait: bool = False

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        from app.services.region_config import normalize_region

        return normalize_region(value)


class PricingSyncResponse(BaseModel):
    job_ids: list[str]
    status: PricingJobStatus
    message: str
    accepted_snapshots: int = 0
    rejected_snapshots: int = 0


class ProductCategoryResponse(BaseModel):
    categories: list[str]
    build_critical_categories: list[str]


class ProductDiscoveryRequest(BaseModel):
    categories: list[str] = Field(default_factory=list)
    category: str | None = None
    query: str | None = None
    region: str = "SA"
    city: str | None = None
    providers: list[str] = Field(default_factory=list)
    limit_per_query: int = Field(default=8, ge=1, le=25)
    limit: int | None = Field(default=None, ge=1, le=25)
    max_queries: int = Field(default=24, ge=1, le=100)
    wait: bool = False
    dry_run: bool = False

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        from app.services.region_config import normalize_region

        return normalize_region(value)

    def resolved_categories(self) -> list[str]:
        if self.categories:
            return self.categories
        return [self.category] if self.category else []

    def resolved_limit(self) -> int:
        return self.limit if self.limit is not None else self.limit_per_query


class ProductDiscoveryResponse(BaseModel):
    job_ids: list[str]
    status: PricingJobStatus
    message: str
    query_count: int
    categories: list[str]
    accepted_snapshots: int = 0
    rejected_snapshots: int = 0
    dry_run: bool = False
    trace_id: str | None = None
    source_errors: list[str] = Field(default_factory=list)
    preview: list[DiscoveryPreviewItem] = Field(default_factory=list)


class CanonicalizationValidationRequest(BaseModel):
    category: str = "GPU"
    names: list[str] = Field(min_length=1, max_length=50)


class CanonicalizationValidationItem(BaseModel):
    raw_listing_name: str
    normalized_name: str
    canonical_key: str
    canonical_product_id: str | None = None
    merge_decision: Literal["new_product", "merge_existing"]
    confidence: float = Field(ge=0, le=1)
    reason: str


class CanonicalizationValidationResponse(BaseModel):
    category: str
    items: list[CanonicalizationValidationItem]
    groups: dict[str, list[str]]


DuplicateConfidence = Literal["high", "medium", "low"]


class CPUDuplicateCandidate(BaseModel):
    canonical_cpu_key: str
    region: str = "SA"
    suspected_duplicate_product_ids: list[str]
    product_names: list[str]
    vendors: list[str] = Field(default_factory=list)
    prices: list[dict[str, Any]] = Field(default_factory=list)
    confidence: DuplicateConfidence
    reason: str
    recommended_action: str
    approval_required: bool = False
    approval_id: str | None = None


class CPUDuplicateReport(BaseModel):
    region: str = "SA"
    candidates: list[CPUDuplicateCandidate] = Field(default_factory=list)
    approval_items_created: int = 0
    trace_id: str | None = None


class CanonicalMergePreviewRequest(BaseModel):
    product_ids: list[str] = Field(min_length=2, max_length=25)
    region: str = "SA"


class CanonicalMergePreviewResponse(BaseModel):
    proposed_canonical_product: dict[str, Any]
    relationships_to_preserve: dict[str, int]
    price_snapshots_to_preserve: int
    vendors_to_preserve: int
    field_evidence_to_preserve: int
    audit_events_to_preserve: int
    risks: list[str] = Field(default_factory=list)
    rollback_plan: str
    would_execute: bool = False
    approval_required: bool = True
    approval_id: str | None = None


class PricingJob(BaseModel):
    id: str = Field(default_factory=lambda: f"pricing-job-{uuid4()}")
    status: PricingJobStatus = "queued"
    kind: PricingJobKind
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None
    accepted_snapshots: int = 0
    rejected_snapshots: int = 0
    attempts: int = 0
    max_attempts: int = 3
    trace_id: str = Field(default_factory=lambda: f"trace-{uuid4()}")
    risk_level: str = "level_0"
    approval_required: bool = False
