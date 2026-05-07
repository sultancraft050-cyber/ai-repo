from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SupportedRegion = Literal["SA", "AE", "US", "EU", "UK"]


class ShippingRules(BaseModel):
    local_shipping_assumption: str
    imported_shipping_assumption: str
    unknown_shipping_policy: str = "Do not estimate hidden shipping; expose uncertainty."


class WarrantyRules(BaseModel):
    local_warranty_label: str
    imported_warranty_label: str
    unknown_warranty_label: str = "Unknown warranty"


class RegionConfig(BaseModel):
    region_code: SupportedRegion
    country_name: str
    default_city: str | None = None
    currency: str
    vat_rate: float | None = Field(default=None, ge=0, le=1)
    vat_name: str | None = None
    tax_model: str | None = None
    google_domain: str
    gl: str
    hl: str = "en"
    location: str
    local_vendors: list[str] = Field(default_factory=list)
    gcc_vendors: list[str] = Field(default_factory=list)
    international_vendors: list[str] = Field(default_factory=list)
    local_source_targets: list[str] = Field(default_factory=list)
    direct_source_targets_disabled_by_default: list[str] = Field(default_factory=list)
    preferred_sources: list[str] = Field(default_factory=list)
    shipping_rules: ShippingRules
    warranty_rules: WarrantyRules


class RegionalPriceSummary(BaseModel):
    region: SupportedRegion
    currency: str
    lowest_market_price: float | None = None
    best_new_price: float | None = None
    best_trusted_price: float | None = None
    best_used_price: float | None = None
    recommended_price: float | None = None
    recommended_vendor: str | None = None
    recommended_reason: str | None = None
    price_confidence: float | None = None
    region_price_status: Literal["active", "stale", "unavailable"] = "unavailable"
