from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.governance import GovernanceSeverity, GovernanceStatus


AlignmentStatus = Literal["aligned", "watch", "misaligned", "violated"]
AlignmentViolationKind = Literal[
    "objective_drift",
    "safety_ignored",
    "uncertainty_hidden",
    "benchmark_overfit",
    "confidence_without_evidence",
    "popularity_over_correctness",
    "policy_incoherence",
    "governance_fragmentation",
]
ObjectiveName = Literal[
    "correctness",
    "safety_stability",
    "evidence_quality",
    "transparency",
    "optimization_quality",
    "performance_maximization",
]


class ObjectivePriority(BaseModel):
    name: ObjectiveName
    rank: int = Field(ge=1)
    weight: float = Field(ge=0, le=1)
    description: str
    protected: bool = True


class CognitiveConstitution(BaseModel):
    id: str = "cognitive-constitution-v1"
    version: str = "1.0.0"
    immutable: bool = True
    non_overridable_constraints: list[str] = Field(default_factory=list)
    protected_governance_rules: list[str] = Field(default_factory=list)
    safety_principles: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SystemIdentity(BaseModel):
    id: str = "hardware-cognition-identity"
    version: str = "1.0.0"
    purpose: str
    core_reasoning_principles: list[str]
    optimization_priorities: list[ObjectivePriority]
    trust_boundaries: list[str]
    recommendation_ethics: list[str]
    uncertainty_handling: list[str]
    optimizes_for: list[str]
    avoids: list[str]
    acceptable_tradeoffs: list[str]
    constitution: CognitiveConstitution
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ObjectiveTradeoff(BaseModel):
    id: str = Field(default_factory=lambda: f"objective-tradeoff-{uuid4()}")
    primary_objective: ObjectiveName
    competing_objective: ObjectiveName
    resolution: str
    acceptable: bool
    confidence_score: float = Field(ge=0, le=1)


class AlignmentViolation(BaseModel):
    id: str = Field(default_factory=lambda: f"alignment-violation-{uuid4()}")
    kind: AlignmentViolationKind
    severity: GovernanceSeverity
    confidence_score: float = Field(ge=0, le=1)
    explanation: str
    affected_objectives: list[ObjectiveName] = Field(default_factory=list)
    mitigation: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecommendationEthicsAssessment(BaseModel):
    misleading_confidence_risk: float = Field(ge=0, le=1)
    unsafe_recommendation_risk: float = Field(ge=0, le=1)
    unstable_configuration_risk: float = Field(ge=0, le=1)
    biased_optimization_risk: float = Field(ge=0, le=1)
    ethics_passed: bool
    notes: list[str] = Field(default_factory=list)


class AlignmentHealthIndex(BaseModel):
    identity_stability: float = Field(ge=0, le=1)
    objective_coherence: float = Field(ge=0, le=1)
    optimization_consistency: float = Field(ge=0, le=1)
    governance_alignment: float = Field(ge=0, le=1)
    confidence_integrity: float = Field(ge=0, le=1)
    transparency_score: float = Field(ge=0, le=1)
    safety_priority_score: float = Field(ge=0, le=1)
    overall_alignment: float = Field(ge=0, le=1)


class AlignmentAuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"alignment-audit-{uuid4()}")
    event_type: Literal[
        "identity_evaluated",
        "objective_audited",
        "ethics_checked",
        "violation_detected",
        "rollback_supported",
        "constitution_enforced",
    ]
    severity: GovernanceSeverity
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AlignmentRollbackEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"alignment-rollback-{uuid4()}")
    status: Literal["not_required", "recommended", "requires_approval", "applied"]
    trigger: str
    target_policy_id: str | None = None
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AlignmentInspectionReport(BaseModel):
    id: str = Field(default_factory=lambda: f"alignment-report-{uuid4()}")
    product_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: AlignmentStatus
    identity: SystemIdentity
    health: AlignmentHealthIndex
    tradeoffs: list[ObjectiveTradeoff] = Field(default_factory=list)
    violations: list[AlignmentViolation] = Field(default_factory=list)
    ethics: RecommendationEthicsAssessment
    rollback: list[AlignmentRollbackEvent] = Field(default_factory=list)
    audit_trail: list[AlignmentAuditEvent] = Field(default_factory=list)
    alignment_summary: list[str] = Field(default_factory=list)


class AlignmentRefreshRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    persist: bool = True


class AlignmentRefreshResponse(BaseModel):
    status: Literal["completed"]
    message: str
    refreshed_count: int = 0
    reports: list[AlignmentInspectionReport] = Field(default_factory=list)
