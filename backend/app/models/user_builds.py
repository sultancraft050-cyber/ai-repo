from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UserAccountCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str | None = Field(default=None, max_length=80)
    region: str = "SA"


class UserAccountView(BaseModel):
    user_id: str
    email: str
    display_name: str | None = None
    region: str = "SA"
    created_at: str | None = None
    last_active_at: str | None = None


class SavedBuildCreateRequest(BaseModel):
    user_id: str | None = None
    guest_id: str | None = None
    title: str | None = Field(default=None, max_length=120)
    region: str = "SA"
    build_mode: str
    total_price_sar: float | None = None
    confidence_level: str = "low"
    warning_summary: list[str] = Field(default_factory=list, max_length=30)
    component_ids: list[str] = Field(default_factory=list)
    price_snapshot_ids: list[str] = Field(default_factory=list)
    build_summary: dict[str, Any] = Field(default_factory=dict)
    build_payload: dict[str, Any] = Field(default_factory=dict)
    public_visibility: bool = True
    favorite: bool = False


class SavedBuildUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    public_visibility: bool | None = None
    favorite: bool | None = None


class SavedBuildView(BaseModel):
    build_id: str
    user_id: str | None = None
    guest_id: str | None = None
    title: str
    region: str
    created_at: str | None = None
    updated_at: str | None = None
    build_mode: str
    total_price_sar: float | None = None
    confidence_level: str
    warning_summary: list[str] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)
    price_snapshot_ids: list[str] = Field(default_factory=list)
    build_summary: dict[str, Any] = Field(default_factory=dict)
    build_payload: dict[str, Any] = Field(default_factory=dict)
    share_slug: str
    public_visibility: bool
    favorite: bool = False


class SavedBuildListResponse(BaseModel):
    builds: list[SavedBuildView] = Field(default_factory=list)


class BuildComparisonRequest(BaseModel):
    build_ids: list[str] = Field(min_length=2, max_length=4)
    user_id: str | None = None
    guest_id: str | None = None


class BuildComparisonMetric(BaseModel):
    build_id: str
    title: str
    total_price_sar: float | None = None
    confidence_level: str
    warning_count: int
    budget_status: str | None = None
    risk_summary: list[str] = Field(default_factory=list)
    upgrade_path: list[str] = Field(default_factory=list)
    cheapest: bool = False
    safest: bool = False
    strongest: bool = False
    more_upgradeable: bool = False


class BuildComparisonResponse(BaseModel):
    comparison_id: str
    compared_builds: list[BuildComparisonMetric]
    highlights: list[str] = Field(default_factory=list)


class WatchlistAddRequest(BaseModel):
    product_id: str
    target_price_sar: float | None = None
    region: str = "SA"


class WatchlistItemView(BaseModel):
    item_id: str
    user_id: str | None = None
    guest_id: str | None = None
    product_id: str
    product_name: str | None = None
    region: str = "SA"
    vendor: str | None = None
    target_price_sar: float | None = None
    last_seen_price: float | None = None
    current_price_sar: float | None = None
    last_price_change: float | None = None
    status: Literal["tracking", "target_met", "price_unavailable"] = "tracking"
    created_at: str | None = None
    updated_at: str | None = None


class WatchlistResponse(BaseModel):
    items: list[WatchlistItemView] = Field(default_factory=list)
