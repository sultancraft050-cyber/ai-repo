from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.domain import BuildPreferences, ComponentOption, SelectedComponents


class CompatibilityRequest(BaseModel):
    selection: SelectedComponents
    preferences: BuildPreferences = Field(default_factory=BuildPreferences)
    qvl_required: bool = True


class ConstraintCheck(BaseModel):
    id: str
    label: str
    status: Literal["pass", "fail", "warning", "unknown"]
    severity: Literal["info", "warning", "critical"]
    details: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class CompatibilityResponse(BaseModel):
    valid: bool
    state: Literal["partial", "valid_configuration", "invalid_configuration"]
    checks: list[ConstraintCheck]
    total_power_draw_w: float | None = None
    required_psu_w: float | None = None
    selected_component_count: int
    missing_component_ids: list[str] = Field(default_factory=list)


class PerformanceRequest(BaseModel):
    selection: SelectedComponents
    preferences: BuildPreferences = Field(default_factory=BuildPreferences)
    display_refresh_hz: int = Field(default=144, ge=30, le=1000)


class BottleneckBreakdown(BaseModel):
    cpu_percent: float
    gpu_percent: float
    memory_percent: float
    display_percent: float


class PerformanceResponse(BaseModel):
    expected_fps: float
    one_percent_low_fps: float
    frame_time_ms: float
    frame_time_variance_ms: float
    bottleneck: BottleneckBreakdown
    confidence: Literal["high", "medium", "low"]
    model_inputs: dict[str, float]
    reasoning: list[str]


class ComponentOptionsResponse(BaseModel):
    options: list[ComponentOption]
    degraded: bool = False
    message: str | None = None


class BuildGenerateRequest(BaseModel):
    budget_usd: float = Field(ge=0)
    purpose: str = "gaming"
    resolution: str = "1440p"
    preferences: BuildPreferences = Field(default_factory=BuildPreferences)
    max_candidates_per_type: int = Field(default=80, ge=1, le=300)


class GeneratedPart(BaseModel):
    kind: str
    id: str
    name: str
    brand: str | None = None
    price_usd: float
    price_source: str | None = None
    price_vendor: str | None = None
    price_freshness_score: float | None = None
    price_trust_score: float | None = None
    price_stale: bool = False
    reasoning: str


class GeneratedBuild(BaseModel):
    label: Literal["best_performance", "best_value", "balanced", "closest_valid"]
    parts: list[GeneratedPart]
    selection: SelectedComponents
    total_cost_usd: float
    score: float
    performance: PerformanceResponse
    compatibility: CompatibilityResponse
    bottleneck_breakdown: BottleneckBreakdown
    reasoning_summary: list[str]


class BuildGenerateResponse(BaseModel):
    builds: list[GeneratedBuild]
    compatibility_status: Literal["valid", "closest_valid", "no_solution"]
    explored_configurations: int
    pruned_configurations: int
    fallback_explanation: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
