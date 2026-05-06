from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.telemetry import TelemetrySummary


WorkloadName = Literal[
    "gaming",
    "workstation",
    "simulation",
    "rendering",
    "ai",
    "streaming",
    "cad",
    "video_editing",
]

Confidence = Literal["high", "medium", "low"]
WarningSeverity = Literal["info", "warning", "critical"]


class BenchmarkScores(BaseModel):
    gaming: float = Field(ge=0, le=100)
    productivity: float = Field(ge=0, le=100)
    ai_ml: float = Field(ge=0, le=100)
    rendering: float = Field(ge=0, le=100)
    simulation: float = Field(ge=0, le=100)
    rasterization: float = Field(ge=0, le=100)
    ray_tracing: float = Field(ge=0, le=100)
    vram_efficiency: float = Field(ge=0, le=100)
    tensor_capability: float = Field(ge=0, le=100)
    single_core: float = Field(ge=0, le=100)
    multi_core: float = Field(ge=0, le=100)
    cache_efficiency: float = Field(ge=0, le=100)
    thermal_efficiency: float = Field(ge=0, le=100)


class WorkloadSuitability(BaseModel):
    workload: WorkloadName
    score: float = Field(ge=0, le=100)
    label: Literal["excellent", "strong", "usable", "limited"]
    reasons: list[str] = Field(default_factory=list)


class PowerThermalProfile(BaseModel):
    tdp_w: float | None = None
    peak_power_w: float | None = None
    thermal_efficiency: float = Field(ge=0, le=100)
    expected_cooling_requirement: str
    recommended_psu_w: int | None = None
    power_spike_risk: Literal["low", "medium", "high"]
    warnings: list[str] = Field(default_factory=list)


class LongevityProfile(BaseModel):
    upgrade_longevity: float = Field(ge=0, le=100)
    future_proof_score: float = Field(ge=0, le=100)
    platform_lifespan_years: float = Field(ge=0, le=10)
    limiting_factors: list[str] = Field(default_factory=list)


class CompatibilityEnrichment(BaseModel):
    bios_requirements: list[str] = Field(default_factory=list)
    chipset_limitations: list[str] = Field(default_factory=list)
    pcie_generation_support: str | None = None
    memory_overclock_stability: Literal["unknown", "low", "medium", "high"] = "unknown"
    cooling_recommendations: list[str] = Field(default_factory=list)


class MarketIntelligence(BaseModel):
    price_performance_ratio: float | None = None
    market_popularity: float = Field(ge=0, le=100)
    value_score: float = Field(ge=0, le=100)
    price_trend: Literal["falling", "stable", "rising", "insufficient_history"]
    best_value_badge: bool = False


class IntelligenceWarning(BaseModel):
    severity: WarningSeverity
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class HardwareIntelligence(BaseModel):
    product_id: str
    product_name: str
    category: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: Confidence
    benchmark: BenchmarkScores
    workloads: list[WorkloadSuitability]
    power_thermal: PowerThermalProfile
    longevity: LongevityProfile
    compatibility: CompatibilityEnrichment
    market: MarketIntelligence
    telemetry: TelemetrySummary | None = None
    recommendation_summary: list[str]
    warnings: list[IntelligenceWarning] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class EnrichmentRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    category: str | None = None
    limit: int = Field(default=50, ge=1, le=300)
    persist: bool = True


class EnrichmentResponse(BaseModel):
    enriched_count: int
    skipped_count: int = 0
    intelligence: list[HardwareIntelligence] = Field(default_factory=list)


class IntelligenceRefreshResponse(BaseModel):
    job_ids: list[str]
    status: Literal["queued", "completed"]
    message: str
    enriched_count: int = 0
