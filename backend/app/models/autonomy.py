from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.governance import GovernanceSeverity


AgentKind = Literal[
    "telemetry",
    "benchmark_validation",
    "anomaly_investigation",
    "confidence_audit",
    "governance_stability",
    "evolution_monitoring",
    "alignment_integrity",
    "recommendation_verification",
]
AgentStatus = Literal["active", "idle", "investigating", "degraded", "paused"]
AutonomyStatus = Literal["active", "watch", "degraded", "blocked"]
EventKind = Literal[
    "scheduled_tick",
    "new_telemetry",
    "driver_regression",
    "benchmark_contradiction",
    "anomaly_spike",
    "policy_drift",
    "stale_evidence",
    "confidence_inflation",
    "alignment_drift",
    "recommendation_risk",
    "graph_pollution",
]
TaskKind = Literal[
    "monitor_telemetry",
    "refresh_telemetry",
    "validate_benchmark",
    "investigate_anomaly",
    "audit_confidence",
    "stabilize_governance",
    "monitor_evolution",
    "enforce_alignment",
    "verify_recommendation",
    "request_revalidation",
]
TaskStatus = Literal["queued", "running", "completed", "blocked", "failed", "requires_approval"]
InterventionKind = Literal[
    "confidence_reduction",
    "telemetry_refresh",
    "evidence_quarantine",
    "revalidation_request",
    "recommendation_downgrade",
    "policy_escalation",
    "evolution_rollback",
    "constitution_guardrail",
]
InterventionStatus = Literal["recommended", "queued", "applied", "blocked", "requires_approval"]
SignalChannel = Literal["event_queue", "governance_signal", "graph_event", "reasoning_notification"]


class AgentDefinition(BaseModel):
    id: str
    kind: AgentKind
    name: str
    status: AgentStatus = "active"
    priority_weight: float = Field(ge=0, le=1)
    cadence_seconds: int = Field(ge=30)
    governed_by: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    allowed_actions: list[TaskKind] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CognitionEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"cognition-event-{uuid4()}")
    kind: EventKind
    severity: GovernanceSeverity
    product_id: str | None = None
    source: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority_score: float = Field(ge=0, le=1)
    handled: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: f"agent-task-{uuid4()}")
    agent_kind: AgentKind
    kind: TaskKind
    status: TaskStatus = "queued"
    priority_score: float = Field(ge=0, le=1)
    product_id: str | None = None
    triggered_by_event_id: str | None = None
    reason: str
    expected_actions: list[str] = Field(default_factory=list)
    requires_human_approval: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class AgentSignal(BaseModel):
    id: str = Field(default_factory=lambda: f"agent-signal-{uuid4()}")
    from_agent: AgentKind
    to_agent: AgentKind
    channel: SignalChannel
    event_id: str | None = None
    message: str
    priority_score: float = Field(ge=0, le=1)
    acknowledged: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InvestigationRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"investigation-{uuid4()}")
    product_id: str | None = None
    agent_kind: AgentKind
    status: Literal["open", "correlating", "resolved", "escalated"] = "open"
    hypothesis: str
    evidence_sources: list[str] = Field(default_factory=list)
    correlated_signals: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    recommended_resolution: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0, le=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AutonomousIntervention(BaseModel):
    id: str = Field(default_factory=lambda: f"autonomous-intervention-{uuid4()}")
    kind: InterventionKind
    status: InterventionStatus
    agent_kind: AgentKind
    target: str
    severity: GovernanceSeverity
    reason: str
    alignment_checked: bool = True
    confidence_delta: float = Field(default=0, ge=-1, le=1)
    requires_human_approval: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HumanOversightAction(BaseModel):
    id: str = Field(default_factory=lambda: f"oversight-action-{uuid4()}")
    action_type: Literal[
        "inspect_agent_action",
        "override_autonomous_decision",
        "approve_policy_escalation",
        "review_investigation",
        "approve_rollback",
    ]
    status: Literal["available", "required", "completed"] = "available"
    target: str
    reason: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AutonomousHealthIndex(BaseModel):
    agent_availability: float = Field(ge=0, le=1)
    queue_pressure: float = Field(ge=0, le=1)
    safety_stability_score: float = Field(ge=0, le=1)
    contradiction_resolution_score: float = Field(ge=0, le=1)
    telemetry_freshness_score: float = Field(ge=0, le=1)
    governance_compliance_score: float = Field(ge=0, le=1)
    intervention_effectiveness: float = Field(ge=0, le=1)
    overall_autonomy_health: float = Field(ge=0, le=1)


class AutonomousCognitionReport(BaseModel):
    id: str = Field(default_factory=lambda: f"autonomy-report-{uuid4()}")
    product_id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: AutonomyStatus
    agents: list[AgentDefinition] = Field(default_factory=list)
    events: list[CognitionEvent] = Field(default_factory=list)
    tasks: list[AgentTask] = Field(default_factory=list)
    signals: list[AgentSignal] = Field(default_factory=list)
    investigations: list[InvestigationRecord] = Field(default_factory=list)
    interventions: list[AutonomousIntervention] = Field(default_factory=list)
    oversight: list[HumanOversightAction] = Field(default_factory=list)
    health: AutonomousHealthIndex
    autonomy_summary: list[str] = Field(default_factory=list)


class AutonomyRunRequest(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    persist: bool = True
    refresh: bool = True


class AutonomyRunResponse(BaseModel):
    status: Literal["completed"]
    message: str
    evaluated_count: int = 0
    reports: list[AutonomousCognitionReport] = Field(default_factory=list)


class CognitionEventIngestRequest(BaseModel):
    event: CognitionEvent
    persist: bool = True
    trigger_analysis: bool = True


class CognitionEventIngestResponse(BaseModel):
    status: Literal["recorded", "analyzed"]
    event_id: str
    report: AutonomousCognitionReport | None = None
