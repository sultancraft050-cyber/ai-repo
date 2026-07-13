from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CatalogSpecResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    specification_key: str
    normalized_value: str
    display_value: str
    unit: str | None = None


class CatalogImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_url: str | None = None
    storage_key: str | None = None
    source_name: str
    width: int | None = None
    height: int | None = None
    format: str | None = None


class CatalogStoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    country: str
    website: str | None = None


class CatalogOfferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    store_id: int
    store_sku: str
    product_url: str
    currency: str
    regular_price: Decimal | None = None
    sale_price: Decimal | None = None
    stock_status: str
    observed_at: datetime
    expires_at: datetime | None = None
    store: CatalogStoreResponse | None = None


class CatalogProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: str
    brand: str
    manufacturer_part_number: str
    exact_model: str | None = None
    variant: str | None = None
    canonical_name: str
    slug: str
    lifecycle_status: str
    approval_status: str
    created_at: datetime
    updated_at: datetime


class CatalogProductDetail(CatalogProductResponse):
    specifications: list[CatalogSpecResponse] = []
    images: list[CatalogImageResponse] = []
    offers: list[CatalogOfferResponse] = []
    cheapest_sar_offer: CatalogOfferResponse | None = None
