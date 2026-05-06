from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TelemetryResolution = Literal["1080p", "1440p", "4K", "ultrawide"]
TelemetryKind = Literal[
    "gaming",
    "workstation",
    "synthetic",
    "frame_time",
    "thermal",
    "power",
    "ai",
    "cad",
    "simulation",
    "compile",
]
TelemetrySourceType = Literal[
    "benchmark_database",
    "official_specs",
    "review_aggregator",
    "telemetry_dataset",
    "performance_api",
    "validated_public_dataset",
    "manual_validation",
]
BottleneckKind = Literal[
    "cpu",
    "gpu",
    "vram",
    "thermal",
    "driver",
    "memory",
    "bandwidth",
    "storage",
    "none",
]
ThermalRisk = Literal["low", "medium", "high", "unknown"]
TelemetryConfidence = Literal["high", "medium", "low"]
TelemetrySeverity = Literal["info", "warning", "critical"]
TelemetryAnomalyKind = Literal[
    "fps_drop",
    "frame_pacing",
    "thermal_throttling",
    "vram_pressure",
    "cpu_saturation",
    "driver_regression",
    "power_spike",
    "memory_pressure",
    "benchmark_outlier",
    "workload_bottleneck",
]
TelemetryPatternKind = Literal[
    "recurring_instability",
    "problematic_driver",
    "problematic_bios",
    "unstable_memory_configuration",
    "workload_incompatibility",
    "insufficient_cooling",
    "psu_instability_risk",
]


class TelemetrySourceTier(IntEnum):
    OFFICIAL_SPEC = 1
    BENCHMARK_DATABASE = 2
    REVIEW_AGGREGATOR = 3
    TELEMETRY_DATASET = 4
    MANUAL_VALIDATION = 5


class WorkloadProfile(BaseModel):
    name: str
    category: TelemetryKind
    engine: str | None = None
    api_dependencies: list[str] = Field(default_factory=list)
    cpu_sensitivity: float = Field(default=0.5, ge=0, le=1)
    gpu_sensitivity: float = Field(default=0.5, ge=0, le=1)
    vram_sensitivity: float = Field(default=0.5, ge=0, le=1)
    cache_sensitivity: float = Field(default=0.5, ge=0, le=1)
    driver_sensitivity: float = Field(default=0.4, ge=0, le=1)
    thermal_sensitivity: float = Field(default=0.45, ge=0, le=1)

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("workload name cannot be empty")
        return value


class DriverVersionInfo(BaseModel):
    vendor: str
    version: str
    release_date: datetime | None = None
    bios_version: str | None = None
    firmware_revision: str | None = None

    @field_validator("vendor", "version")
    @classmethod
    def non_empty_driver_field(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("driver vendor and version cannot be empty")
        return value


class TelemetryMetrics(BaseModel):
    average_fps: float | None = Field(default=None, ge=0, le=2000)
    one_percent_low_fps: float | None = Field(default=None, ge=0, le=2000)
    point_one_percent_low_fps: float | None = Field(default=None, ge=0, le=2000)
    average_frame_time_ms: float | None = Field(default=None, ge=0, le=200)
    p95_frame_time_ms: float | None = Field(default=None, ge=0, le=300)
    p99_frame_time_ms: float | None = Field(default=None, ge=0, le=400)
    frame_time_variance_ms: float | None = Field(default=None, ge=0, le=200)
    render_time_seconds: float | None = Field(default=None, ge=0, le=86400)
    ai_tokens_per_second: float | None = Field(default=None, ge=0, le=1_000_000)
    ai_images_per_minute: float | None = Field(default=None, ge=0, le=100_000)
    cad_score: float | None = Field(default=None, ge=0, le=1_000_000)
    simulation_steps_per_second: float | None = Field(default=None, ge=0, le=1_000_000)
    compile_time_seconds: float | None = Field(default=None, ge=0, le=86400)
    average_power_w: float | None = Field(default=None, ge=0, le=2500)
    peak_power_w: float | None = Field(default=None, ge=0, le=4000)
    average_temp_c: float | None = Field(default=None, ge=0, le=130)
    hotspot_temp_c: float | None = Field(default=None, ge=0, le=140)
    fan_noise_dba: float | None = Field(default=None, ge=0, le=100)
    vram_used_gb: float | None = Field(default=None, ge=0, le=256)
    system_memory_used_gb: float | None = Field(default=None, ge=0, le=1024)
    gpu_utilization_percent: float | None = Field(default=None, ge=0, le=100)
    cpu_utilization_percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def at_least_one_metric(self) -> "TelemetryMetrics":
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("telemetry snapshot must include at least one metric")
        return self


class TelemetryBottleneckBreakdown(BaseModel):
    cpu_percent: float = Field(default=0, ge=0, le=100)
    gpu_percent: float = Field(default=0, ge=0, le=100)
    vram_percent: float = Field(default=0, ge=0, le=100)
    thermal_percent: float = Field(default=0, ge=0, le=100)
    driver_percent: float = Field(default=0, ge=0, le=100)
    memory_percent: float = Field(default=0, ge=0, le=100)
    bandwidth_percent: float = Field(default=0, ge=0, le=100)
    storage_percent: float = Field(default=0, ge=0, le=100)


class TelemetryLimitReason(BaseModel):
    kind: BottleneckKind
    percent: float = Field(ge=0, le=100)
    reason: str


class TelemetrySnapshotIn(BaseModel):
    product_ids: list[str] = Field(min_length=1, max_length=16)
    benchmark_name: str
    kind: TelemetryKind
    resolution: TelemetryResolution
    workload: WorkloadProfile
    metrics: TelemetryMetrics
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    settings_preset: str | None = None
    driver_version: DriverVersionInfo | None = None
    source: str
    source_url: str | None = None
    source_type: TelemetrySourceType
    source_tier: TelemetrySourceTier
    trust_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    notes: str | None = None

    @field_validator("benchmark_name", "source")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("benchmark name and source cannot be empty")
        return value

    @field_validator("product_ids")
    @classmethod
    def clean_product_ids(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one product id is required")
        return sorted(set(cleaned))


class TelemetrySnapshotView(TelemetrySnapshotIn):
    id: str
    bottleneck: TelemetryBottleneckBreakdown
    primary_limiter: BottleneckKind
    frame_time_instability_score: float = Field(ge=0, le=100)
    thermal_throttling_risk: ThermalRisk
    limit_reasons: list[TelemetryLimitReason] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    accepted: bool = True


class TelemetryIngestRejected(BaseModel):
    index: int
    reasons: list[str]


class TelemetryIngestRequest(BaseModel):
    snapshots: list[TelemetrySnapshotIn] = Field(min_length=1, max_length=250)
    persist: bool = True
    validate_only: bool = False


class TelemetryIngestResponse(BaseModel):
    accepted_count: int
    rejected_count: int
    snapshots: list[TelemetrySnapshotView] = Field(default_factory=list)
    rejected: list[TelemetryIngestRejected] = Field(default_factory=list)


class TelemetrySummary(BaseModel):
    product_id: str
    sample_count: int
    confidence: TelemetryConfidence
    average_fps: float | None = None
    one_percent_low_fps: float | None = None
    average_frame_time_ms: float | None = None
    frame_time_instability_score: float | None = None
    average_power_w: float | None = None
    peak_power_w: float | None = None
    average_temp_c: float | None = None
    hotspot_temp_c: float | None = None
    bottleneck: TelemetryBottleneckBreakdown
    primary_limiter: BottleneckKind
    thermal_throttling_risk: ThermalRisk
    covered_resolutions: list[str] = Field(default_factory=list)
    covered_workloads: list[str] = Field(default_factory=list)
    latest_driver_versions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TelemetryEvidencePoint(BaseModel):
    metric: str
    value: float | str
    threshold: float | str | None = None
    source: str
    snapshot_id: str | None = None
    timestamp: datetime | None = None


class TelemetryAnomaly(BaseModel):
    id: str
    kind: TelemetryAnomalyKind
    severity: TelemetrySeverity
    title: str
    explanation: str
    confidence_score: float = Field(ge=0, le=1)
    sample_size: int = Field(ge=0)
    evidence: list[TelemetryEvidencePoint] = Field(default_factory=list)
    affected_workloads: list[str] = Field(default_factory=list)
    affected_resolutions: list[str] = Field(default_factory=list)
    likely_causes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class DriverRegressionFinding(BaseModel):
    id: str
    driver_from: str
    driver_to: str
    workload: str
    resolution: str
    fps_delta_percent: float | None = None
    instability_delta: float | None = None
    thermal_delta_c: float | None = None
    severity: TelemetrySeverity
    confidence_score: float = Field(ge=0, le=1)
    explanation: str
    evidence_sources: list[str] = Field(default_factory=list)


class TelemetryPatternFinding(BaseModel):
    id: str
    kind: TelemetryPatternKind
    severity: TelemetrySeverity
    title: str
    explanation: str
    confidence_score: float = Field(ge=0, le=1)
    sample_size: int = Field(ge=0)
    evidence_sources: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class PredictiveTelemetryInsight(BaseModel):
    id: str
    horizon: str
    predicted_limitation: BottleneckKind
    risk_score: float = Field(ge=0, le=100)
    confidence_score: float = Field(ge=0, le=1)
    explanation: str
    evidence_sources: list[str] = Field(default_factory=list)
    mitigation: list[str] = Field(default_factory=list)


class TelemetryReasoningReport(BaseModel):
    id: str
    product_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence_score: float = Field(ge=0, le=1)
    sample_size: int = Field(ge=0)
    evidence_sources: list[str] = Field(default_factory=list)
    ai_explanation: str | None = None
    summary: list[str] = Field(default_factory=list)
    workload_reasoning: list[str] = Field(default_factory=list)
    bottleneck_explanations: list[TelemetryLimitReason] = Field(default_factory=list)
    anomalies: list[TelemetryAnomaly] = Field(default_factory=list)
    driver_regressions: list[DriverRegressionFinding] = Field(default_factory=list)
    patterns: list[TelemetryPatternFinding] = Field(default_factory=list)
    predictions: list[PredictiveTelemetryInsight] = Field(default_factory=list)
    recommended_for: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
