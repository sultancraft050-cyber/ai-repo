from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


CatalogCategory = Literal[
    "CPU",
    "GPU",
    "Motherboard",
    "RAM",
    "Storage",
    "PSU",
    "Case",
    "Cooler",
    "Monitor",
    "Keyboard",
    "Mouse",
    "Speaker",
    "Accessories",
]


class CatalogFeedImportRow(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    category: CatalogCategory | None = None
    brand: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)
    canonical_key: str | None = Field(default=None, max_length=240)
    image_url: str | None = Field(default=None, max_length=2048)
    processed_image_url: str | None = Field(default=None, max_length=2048)
    specs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("brand", "model", "canonical_key", "image_url", "processed_image_url", mode="before")
    @classmethod
    def blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class CatalogFeedImportRequest(BaseModel):
    source_name: str = Field(min_length=2, max_length=120)
    category: CatalogCategory
    region: str = Field(default="SA", min_length=2, max_length=8)
    dry_run: bool = True
    rows: list[CatalogFeedImportRow] = Field(default_factory=list, max_length=1000)


class CatalogFeedImportResponse(BaseModel):
    run_id: str
    source_name: str
    category: str
    region: str
    dry_run: bool
    status: str
    imported_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    sanitized_error: str | None = None


class CatalogFeedRunView(BaseModel):
    run_id: str
    source_name: str
    category: str
    region: str
    status: str
    imported_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    dry_run: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
    sanitized_error: str | None = None


class CatalogCategoryCoverage(BaseModel):
    category: str
    product_count: int
    priced_product_count: int
    trusted_listing_count: int
    stale_listing_count: int
    missing_processed_image_count: int
    missing_compatibility_spec_count: int
    duplicate_risk_count: int
    readiness_level: str
    next_best_action: str


class CatalogCoverageResponse(BaseModel):
    region: str
    category_count: int
    product_count: int
    priced_product_count: int
    stale_listing_count: int
    categories: list[CatalogCategoryCoverage]
