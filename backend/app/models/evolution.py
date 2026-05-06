from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.governance import GovernanceSeverity, GovernanceStatus


PolicyStatus = Literal["active", "candidate", "superseded", "rolled_back", "archived"]
PolicyDecisionStatus = Literal["allow", "throttle", "block", "escalate"]
PromotionStatus = Literal["promote", "hold", "reject", "quarantine"]
RollbackStatus = Literal["not_required", "recommended", "requires_approval", "applied"]


class CognitivePolicy(BaseModel):
    id: str = Field(default_factory=lambda: f"cognitive-policy-{uuid4()}")
    version: str = "1.0.0"
    status: PolicyStatus = "active"
    scope: str = "global"
    confidence_ceiling_max: float = Field(default=0.86, ge=0, le=1)
    evidence_freshness_min: float = Field(default=0.42, ge=0, le=1)
    contradiction_tolerance: float = Field(default=0.18, ge=0, le=1)
    anomaly_escalation_threshold: float = Field(default=0.32, ge=0, le=1)
    adaptation_rate_limit: float = Field(default=0.12, ge=0, le=1)
    recommendation_aggressiveness: float = Field(default=0.48, ge=0, le=1)
    self_generated_trust_cap: float = Field(default=0.55, ge=0, le=1)
    telemetry_trust_growth_rate: float = Field(default=0.08, ge=0, le=1)
    policy_drift_limit: float = Field(default=0.22, ge=0, le=1)
    requires_human_approval: bool = True
    created_by: str = "system"
    change_reason: str = "default governed evolution policy"
    supersedes_policy_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CognitiveHealthIndex(BaseModel):
    reasoning_stability: float = Field(ge=0, le=1)
    graph_health: float = Field(ge=0, le=1)
    evidence_freshness: float = Field(ge=0, le=1)
    contradiction_resilience: float = Field(ge=0, le=1)
    anomaly_pressure: float = Field(ge=0, le=1)
    adaptation_volatility: float = Field(ge=0, le=1)
    policy_alignment: float = Field(ge=0, le=1)
    index: float = Field(ge=0, le=1)


class EvolutionMetrics(BaseModel):
    evolution_velocity: float = Field(ge=0, le=1)
    graph_mutation_velocity: float = Field(ge=0, le=1)
    anomaly_growth: float = Field(ge=0, le=1)
    contradiction_propagation: float = Field(ge=0, le=1)
    policy_drift: float = Field(ge=0, le=1)
    adaptation_pressure: float = Field(ge=0, le=1)
    confidence_volatility: float = Field(ge=0, le=1)
    intervention_rate: float = Field(ge=0, le=1)


class PolicyEnforcementDecision(BaseModel):
    id: str = Field(default_factory=lambda: f"policy-decision-{uuid4()}")
    rule: Literal[
        "confidence_ceiling",
        "evidence_freshness",
        "contradiction_tolerance",
        "anomaly_escalation",
        "adaptation_rate",
        "self_generated_trust",
        "policy_drift",
    ]
    status: PolicyDecisionStatus
    severity: GovernanceSeverity
    observed_value: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    action: str


class SandboxEvaluation(BaseModel):
    id: str = Field(default_factory=lambda: f"sandbox-evaluation-{uuid4()}")
    model_id: str
    policy_id: str
    isolated: bool = True
    stability_score: float = Field(ge=0, le=1)
    prediction_accuracy_score: float = Field(ge=0, le=1)
    contradiction_impact: float = Field(ge=0, le=1)
    telemetry_consistency: float = Field(ge=0, le=1)
    promotion_ready: bool
    rationale: str


class ModelPromotionDecision(BaseModel):
    id: str = Field(default_factory=lambda: f"promotion-decision-{uuid4()}")
    model_id: str
    status: PromotionStatus
    stability_delta: float = Field(ge=-1, le=1)
    contradiction_delta: float = Field(ge=-1, le=1)
    prediction_accuracy: float = Field(ge=0, le=1)
    reason: str
    requires_approval: bool


class RollbackEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"rollback-event-{uuid4()}")
    status: RollbackStatus
    from_policy_id: str
    to_policy_id: str | None = None
    trigger: str
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LongTermMemoryDecision(BaseModel):
    id: str = Field(default_factory=lambda: f"memory-decision-{uuid4()}")
    target: str
    status: Literal["strengthen", "decay", "archive", "retain"]
    support_score: float = Field(ge=0, le=1)
    reason: str


class EvolutionAuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evolution-audit-{uuid4()}")
    event_type: Literal[
        "policy_evaluated",
        "adaptation_throttled",
        "sandbox_evaluated",
        "promotion_reviewed",
        "rollback_recommended",
        "memory_governed",
    ]
    severity: GovernanceSeverity
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvolutionOrchestrationReport(BaseModel):
    id: str = Field(default_factory=lambda: f"evolution-report-{uuid4()}")
    product_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: GovernanceStatus
    active_policy: CognitivePolicy
    health_index: CognitiveHealthIndex
    metrics: EvolutionMetrics
    enforcement: list[PolicyEnforcementDecision] = Field(default_factory=list)
    sandbox_evaluations: list[SandboxEvaluation] = Field(default_factory=list)
    promotion_decisions: list[ModelPromotionDecision] = Field(default_factory=list)
    rollback_events: list[RollbackEvent] = Field(default_factory=list)
    memory_decisions: list[LongTermMemoryDecision] = Field(default_factory=list)
    audit_trail: list[EvolutionAuditEvent] = Field(default_factory=list)
    orchestration_summary: list[str] = Field(default_factory=list)


class PolicyCreateRequest(BaseModel):
    policy: CognitivePolicy
    activate: bool = False
    approval_note: str | None = None


class PolicyRollbackRequest(BaseModel):
    product_id: str
    target_policy_id: str | None = None
    approval_note: str | None = None
    persist: bool = True


class EvolutionRefreshRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    persist: bool = True


class EvolutionRefreshResponse(BaseModel):
    status: Literal["completed"]
    message: str
    refreshed_count: int = 0
    reports: list[EvolutionOrchestrationReport] = Field(default_factory=list)
