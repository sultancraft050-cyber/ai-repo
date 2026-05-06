from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


Role = Literal["anonymous", "viewer", "analyst", "admin", "super_admin"]
AutonomyLevel = Literal["level_0", "level_1", "level_2", "level_3"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "executed", "deferred", "reviewed"]
OpsJobStatus = Literal["queued", "running", "succeeded", "failed", "retrying", "cancelled", "requires_approval"]


class AuthPrincipal(BaseModel):
    actor: str = "anonymous"
    role: Role = "anonymous"
    authenticated: bool = False


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"audit-{uuid4()}")
    actor: str
    role: Role
    action: str
    endpoint: str
    method: str
    target: str | None = None
    request_payload_hash: str | None = None
    idempotency_key: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result: str
    status_code: int | None = None
    trace_id: str
    approval_required: bool = False
    approval_status: ApprovalStatus | None = None
    risk_level: AutonomyLevel = "level_0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalItem(BaseModel):
    id: str = Field(default_factory=lambda: f"approval-{uuid4()}")
    action_type: str
    affected_entities: list[str] = Field(default_factory=list)
    risk_level: AutonomyLevel
    reasoning: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    rollback_plan: str
    recommended_decision: Literal["approve", "reject", "defer", "review"] = "defer"
    status: ApprovalStatus = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_note: str | None = None
    trace_id: str = Field(default_factory=lambda: f"trace-{uuid4()}")


class ApprovalDecisionRequest(BaseModel):
    note: str | None = None


class ApprovalDecisionResponse(BaseModel):
    approval: ApprovalItem
    audit_event: AuditEvent


class SourceHealth(BaseModel):
    source: str
    configured: bool
    status: Literal["healthy", "degraded", "paused", "not_configured", "quota_limited", "unknown"]
    last_successful_request: datetime | None = None
    last_failure: datetime | None = None
    quota_status: Literal["ok", "near_limit", "limited", "unknown", "not_configured"] = "unknown"
    reliability_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    message: str


class WorkerHealth(BaseModel):
    name: str
    enabled: bool
    running: bool
    queue_depth: int = Field(ge=0)
    last_heartbeat: datetime | None = None
    repeated_failures: int = Field(default=0, ge=0)
    status: Literal["healthy", "idle", "degraded", "stopped"]
    message: str


class JobMonitorItem(BaseModel):
    job_id: str
    job_type: str
    status: OpsJobStatus
    attempts: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    trace_id: str
    risk_level: AutonomyLevel
    approval_required: bool = False
    error: str | None = None


class GraphHealth(BaseModel):
    status: Literal["healthy", "watch", "degraded", "unavailable"]
    neo4j_connected: bool
    product_count: int = 0
    stale_product_count: int = 0
    pending_approval_count: int = 0
    recent_audit_count: int = 0
    message: str


class FounderAlert(BaseModel):
    id: str = Field(default_factory=lambda: f"founder-alert-{uuid4()}")
    severity: Literal["info", "warning", "critical"]
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str
    approval_id: str | None = None


class DailyFounderReport(BaseModel):
    id: str = Field(default_factory=lambda: f"daily-founder-report-{uuid4()}")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    system_health: Literal["healthy", "watch", "degraded", "critical"]
    neo4j_health: GraphHealth
    workers: list[WorkerHealth] = Field(default_factory=list)
    failed_jobs: list[JobMonitorItem] = Field(default_factory=list)
    successful_refreshes: int = 0
    new_products_discovered: int = 0
    stale_sources: list[SourceHealth] = Field(default_factory=list)
    source_health: list[SourceHealth] = Field(default_factory=list)
    pricing_anomalies: list[str] = Field(default_factory=list)
    telemetry_gaps: list[str] = Field(default_factory=list)
    cognition_risks: list[str] = Field(default_factory=list)
    approval_items_waiting: list[ApprovalItem] = Field(default_factory=list)
    alerts: list[FounderAlert] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    recent_audit_events: list[AuditEvent] = Field(default_factory=list)


class OpsRunbook(BaseModel):
    autonomy_levels: dict[AutonomyLevel, list[str]]
    schedules: dict[str, list[str]]
    safe_defaults: list[str]
