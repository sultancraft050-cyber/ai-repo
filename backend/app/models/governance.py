from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


GovernanceStatus = Literal["healthy", "watch", "degraded", "unstable", "quarantined"]
GovernanceSeverity = Literal["info", "warning", "critical"]
EvidenceGovernanceStatus = Literal["active", "decayed", "stale", "quarantined"]
GraphHygieneKind = Literal[
    "polluted_node",
    "corrupted_inference_chain",
    "unstable_telemetry_cluster",
    "low_trust_reasoning_path",
    "circular_evidence",
    "stale_telemetry_dominance",
]
StabilizationActionKind = Literal[
    "confidence_damping",
    "evidence_decay",
    "evidence_quarantine",
    "revalidation_job",
    "recommendation_downgrade",
    "graph_hygiene_review",
]


class ReasoningHealthMetrics(BaseModel):
    reasoning_quality: float = Field(ge=0, le=1)
    confidence_drift: float = Field(ge=0, le=1)
    confidence_oscillation: float = Field(ge=0, le=1)
    calibration_risk: float = Field(ge=0, le=1)
    contradiction_density: float = Field(ge=0, le=1)
    telemetry_freshness: float = Field(ge=0, le=1)
    evidence_decay_pressure: float = Field(ge=0, le=1)
    graph_integrity: float = Field(ge=0, le=1)
    recursive_feedback_risk: float = Field(ge=0, le=1)
    anomaly_density: float = Field(ge=0, le=1)
    coverage_gap_score: float = Field(ge=0, le=1)
    overall_health: float = Field(ge=0, le=1)


class EvidenceDecayRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"evidence-decay-{uuid4()}")
    source: str
    age_days: float = Field(ge=0)
    original_weight: float = Field(ge=0, le=1)
    decayed_weight: float = Field(ge=0, le=1)
    validation_support: int = Field(ge=0)
    statistical_stability: float = Field(ge=0, le=1)
    status: EvidenceGovernanceStatus
    reason: str


class GraphHygieneSignal(BaseModel):
    id: str = Field(default_factory=lambda: f"governance-signal-{uuid4()}")
    kind: GraphHygieneKind
    severity: GovernanceSeverity
    confidence_score: float = Field(ge=0, le=1)
    affected_nodes: list[str] = Field(default_factory=list)
    explanation: str
    mitigation: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConsensusStrategyScore(BaseModel):
    strategy: Literal["telemetry_weighted", "validation_calibrated", "decay_adjusted", "contradiction_adverse"]
    confidence_score: float = Field(ge=0, le=1)
    evidence_weight: float = Field(ge=0, le=1)
    disagreement_score: float = Field(ge=0, le=1)
    rationale: str


class StabilityControl(BaseModel):
    original_confidence: float = Field(ge=0, le=1)
    governed_confidence: float = Field(ge=0, le=1)
    confidence_ceiling: float = Field(ge=0, le=1)
    dampening_factor: float = Field(ge=0, le=1)
    decay_rate: float = Field(ge=0, le=1)
    quarantine_threshold: float = Field(ge=0, le=1)
    revalidation_required: bool
    downgrade_reasons: list[str] = Field(default_factory=list)


class StabilizationAction(BaseModel):
    id: str = Field(default_factory=lambda: f"stabilization-action-{uuid4()}")
    kind: StabilizationActionKind
    severity: GovernanceSeverity
    status: Literal["recommended", "queued", "applied"] = "recommended"
    target: str
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReasoningAuditTrail(BaseModel):
    evidence_sources: list[str] = Field(default_factory=list)
    reasoning_paths: list[str] = Field(default_factory=list)
    confidence_evolution: list[str] = Field(default_factory=list)
    anomaly_history: list[str] = Field(default_factory=list)
    contradiction_history: list[str] = Field(default_factory=list)


class ReasoningGovernanceReport(BaseModel):
    id: str = Field(default_factory=lambda: f"governance-report-{uuid4()}")
    product_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: GovernanceStatus
    metrics: ReasoningHealthMetrics
    stability: StabilityControl
    evidence_decay: list[EvidenceDecayRecord] = Field(default_factory=list)
    graph_hygiene: list[GraphHygieneSignal] = Field(default_factory=list)
    consensus: list[ConsensusStrategyScore] = Field(default_factory=list)
    stabilization_actions: list[StabilizationAction] = Field(default_factory=list)
    audit_trail: ReasoningAuditTrail
    governance_summary: list[str] = Field(default_factory=list)


class GovernanceRefreshRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    wait: bool = False
    persist: bool = True


class GovernanceRefreshResponse(BaseModel):
    status: Literal["queued", "completed"]
    message: str
    refreshed_count: int = 0
    reports: list[ReasoningGovernanceReport] = Field(default_factory=list)
