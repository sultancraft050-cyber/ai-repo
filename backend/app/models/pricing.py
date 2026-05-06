from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum, IntEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


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
    product_url: str | None = None
    image_url: str | None = None
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
    availability: Availability
    timestamp: datetime
    shipping_cost: float = Field(default=0, ge=0)
    product_url: str | None = None
    image_url: str | None = None
    source_product_id: str | None = None
    seller: str | None = None
    condition: str | None = None
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


class DataQualityReport(BaseModel):
    accepted: bool
    rejected_reasons: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    anomaly_score: float = Field(default=0, ge=0, le=1)


class PriceSnapshotView(BaseModel):
    id: str
    vendor_id: str
    vendor_name: str
    price: float
    currency: str
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
    flags: list[str] = Field(default_factory=list)


class ProductSearchResult(BaseModel):
    id: str
    canonical_key: str | None = None
    name: str
    brand: str | None = None
    category: str
    model: str | None = None
    image_url: str | None = None
    current_best_price: float | None = None
    current_best_currency: str | None = None
    current_best_vendor: str | None = None
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
    region: str = "US"
    providers: list[str] = Field(default_factory=list)
    wait: bool = False


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
    region: str = "US"
    providers: list[str] = Field(default_factory=list)
    limit_per_query: int = Field(default=8, ge=1, le=25)
    wait: bool = False


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
    query: str | None = None
    region: str = "US"
    providers: list[str] = Field(default_factory=list)
    limit_per_query: int = Field(default=8, ge=1, le=25)
    max_queries: int = Field(default=24, ge=1, le=100)
    wait: bool = False


class ProductDiscoveryResponse(BaseModel):
    job_ids: list[str]
    status: PricingJobStatus
    message: str
    query_count: int
    categories: list[str]
    accepted_snapshots: int = 0
    rejected_snapshots: int = 0


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
