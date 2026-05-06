from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.models.telemetry import BottleneckKind, TelemetryBottleneckBreakdown, TelemetrySeverity


PredictionKind = Literal["fps", "bottleneck", "thermal", "power", "stability", "upgrade_limit"]
ValidationStatus = Literal["validated", "partially_validated", "contradicted", "insufficient_evidence"]
LearningJobKind = Literal["generate_predictions", "validate_outcome", "refresh_cognition"]
LearningJobStatus = Literal[
    "queued",
    "running",
    "completed",
    "succeeded",
    "failed",
    "retrying",
    "cancelled",
    "requires_approval",
]


class EvidenceQuality(BaseModel):
    source: str
    methodology: str | None = None
    benchmark_conditions: dict[str, Any] = Field(default_factory=dict)
    hardware_configuration: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trust_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    repeatability_score: float = Field(default=0.5, ge=0, le=1)
    evidence_rank: Literal[
        "validated_telemetry",
        "repeated_benchmark_consistency",
        "official_specification",
        "historical_trend",
        "inferred_estimation",
    ] = "inferred_estimation"


class ConfidenceVector(BaseModel):
    confidence_score: float = Field(ge=0, le=1)
    evidence_strength: float = Field(ge=0, le=1)
    sample_size: int = Field(ge=0)
    workload_consistency: float = Field(ge=0, le=1)
    telemetry_stability: float = Field(ge=0, le=1)
    contradiction_count: int = Field(ge=0)
    uncertainty_score: float = Field(ge=0, le=1)
    assumptions: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)


class PredictionRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"prediction-{uuid4()}")
    product_id: str
    reasoning_report_id: str | None = None
    kind: PredictionKind
    workload: str | None = None
    resolution: str | None = None
    predicted_value: float | None = None
    predicted_unit: str | None = None
    predicted_limiter: BottleneckKind | None = None
    horizon: str = "current telemetry window"
    confidence: ConfidenceVector
    evidence: list[EvidenceQuality] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def value_or_limiter_required(self) -> "PredictionRecord":
        if self.predicted_value is None and self.predicted_limiter is None:
            raise ValueError("prediction requires a predicted value or limiter")
        return self


class OutcomeObservation(BaseModel):
    id: str = Field(default_factory=lambda: f"outcome-{uuid4()}")
    product_id: str
    prediction_id: str | None = None
    telemetry_snapshot_id: str | None = None
    workload: str | None = None
    resolution: str | None = None
    observed_fps: float | None = Field(default=None, ge=0)
    observed_one_percent_low_fps: float | None = Field(default=None, ge=0)
    observed_limiter: BottleneckKind | None = None
    observed_average_temp_c: float | None = Field(default=None, ge=0)
    observed_peak_power_w: float | None = Field(default=None, ge=0)
    observed_instability_score: float | None = Field(default=None, ge=0, le=100)
    evidence: EvidenceQuality
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PredictionValidation(BaseModel):
    id: str = Field(default_factory=lambda: f"validation-{uuid4()}")
    prediction_id: str
    outcome_id: str
    product_id: str
    kind: PredictionKind
    status: ValidationStatus
    absolute_error: float | None = None
    relative_error: float | None = None
    confidence_error: float | None = None
    calibrated_confidence: float = Field(ge=0, le=1)
    correctness_score: float = Field(ge=0, le=1)
    severity: TelemetrySeverity
    explanation: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConfidenceState(BaseModel):
    id: str
    scope: Literal["global", "product", "workload", "hardware_family", "inference_path"]
    key: str
    reliability_score: float = Field(ge=0, le=1)
    calibration_error: float = Field(ge=0, le=1)
    validation_count: int = Field(ge=0)
    contradiction_rate: float = Field(ge=0, le=1)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    downgrade_reasons: list[str] = Field(default_factory=list)


class ContradictionSignal(BaseModel):
    id: str = Field(default_factory=lambda: f"contradiction-{uuid4()}")
    product_id: str
    kind: Literal["fps_spread", "thermal_conflict", "power_efficiency", "driver_instability", "source_disagreement"]
    severity: TelemetrySeverity
    confidence_score: float = Field(ge=0, le=1)
    explanation: str
    evidence_sources: list[str] = Field(default_factory=list)
    affected_workloads: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetaReasoningReport(BaseModel):
    id: str = Field(default_factory=lambda: f"meta-reasoning-{uuid4()}")
    product_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    uncertainty_score: float = Field(ge=0, le=1)
    evidence_strength: float = Field(ge=0, le=1)
    weak_evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    telemetry_gaps: list[str] = Field(default_factory=list)
    contradiction_density: float = Field(ge=0, le=1)
    self_corrections: list[str] = Field(default_factory=list)


class HardwareCognitionReport(BaseModel):
    product_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: ConfidenceVector
    reliability: ConfidenceState
    meta_reasoning: MetaReasoningReport
    active_predictions: list[PredictionRecord] = Field(default_factory=list)
    recent_validations: list[PredictionValidation] = Field(default_factory=list)
    contradictions: list[ContradictionSignal] = Field(default_factory=list)
    bottleneck_memory: TelemetryBottleneckBreakdown
    learning_summary: list[str] = Field(default_factory=list)
    audit_events: list[str] = Field(default_factory=list)


class OutcomeValidationRequest(BaseModel):
    outcome: OutcomeObservation
    prediction_ids: list[str] = Field(default_factory=list)
    persist: bool = True


class OutcomeValidationResponse(BaseModel):
    outcome_id: str
    validations: list[PredictionValidation]
    updated_confidence: list[ConfidenceState]
    contradictions: list[ContradictionSignal] = Field(default_factory=list)
    message: str


class CognitionRefreshRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    wait: bool = False
    persist: bool = True


class CognitionRefreshResponse(BaseModel):
    job_ids: list[str] = Field(default_factory=list)
    status: LearningJobStatus
    message: str
    refreshed_count: int = 0


class LearningJob(BaseModel):
    id: str = Field(default_factory=lambda: f"learning-job-{uuid4()}")
    kind: LearningJobKind
    status: LearningJobStatus = "queued"
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    trace_id: str = Field(default_factory=lambda: f"trace-{uuid4()}")
    risk_level: str = "level_1"
    approval_required: bool = False
