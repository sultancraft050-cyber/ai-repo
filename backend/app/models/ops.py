from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field


Role = Literal["anonymous", "viewer", "analyst", "admin", "super_admin"]
AutonomyLevel = Literal["level_0", "level_1", "level_2", "level_3"]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "executed", "deferred", "reviewed"]
OpsJobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "retrying",
    "cancelled",
    "requires_approval",
    "blocked",
    "deferred",
]
Severity = Literal["info", "watch", "warning", "critical"]


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

    @computed_field
    @property
    def audit_id(self) -> str:
        return self.id


class ApprovalItem(BaseModel):
    id: str = Field(default_factory=lambda: f"approval-{uuid4()}")
    action_type: str
    title: str | None = None
    description: str | None = None
    affected_entities: list[str] = Field(default_factory=list)
    target_entities: list[str] = Field(default_factory=list)
    affected_count: int = 0
    risk_level: AutonomyLevel
    reasoning: str
    evidence_summary: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    risk_explanation: str | None = None
    expected_impact: str | None = None
    rollback_plan: str
    requested_by_agent: str | None = None
    recommended_decision: Literal["approve", "reject", "defer", "review"] = "defer"
    status: ApprovalStatus = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_note: str | None = None
    trace_id: str = Field(default_factory=lambda: f"trace-{uuid4()}")

    @computed_field
    @property
    def approval_id(self) -> str:
        return self.id

    def model_post_init(self, __context: Any) -> None:
        if not self.target_entities:
            self.target_entities = list(self.affected_entities)
        if self.affected_count <= 0:
            self.affected_count = len(self.target_entities or self.affected_entities)
        if self.title is None:
            self.title = self.action_type.replace("_", " ").title()
        if self.description is None:
            self.description = self.reasoning
        if self.evidence_summary is None and self.evidence:
            self.evidence_summary = ", ".join(sorted(self.evidence.keys())) or "Evidence attached"
        if self.risk_explanation is None:
            self.risk_explanation = (
                "Requires founder approval before execution."
                if self.risk_level == "level_2"
                else "Manual-only action; autonomous execution is blocked."
                if self.risk_level == "level_3"
                else "Low-risk autonomous action."
            )
        if self.expected_impact is None:
            self.expected_impact = "No mutation is executed until the approval decision is recorded."


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


class SourceConfigStatus(BaseModel):
    source_name: str
    region: str = "SA"
    configured: bool
    health: Literal["configured", "not_configured", "degraded", "healthy", "quota_limited", "failed"]
    last_success: datetime | None = None
    last_failure: datetime | None = None
    last_error_sanitized: str | None = None
    quota_status: Literal["ok", "near_limit", "limited", "unknown", "not_configured"] = "unknown"
    source_kind: str = "api_source"
    discovery_enabled: bool = False
    direct_access_enabled: bool = False
    preferred_discovery_path: str | None = None
    source_policy: str | None = None


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


class AutonomyJob(BaseModel):
    job_id: str
    job_type: str
    title: str
    description: str
    status: OpsJobStatus
    risk_level: AutonomyLevel
    approval_required: bool
    agent_name: str | None = None
    target_entity_id: str | None = None
    target_entity_type: str | None = None
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    trace_id: str
    last_error: str | None = None
    next_retry_at: datetime | None = None
    summary: str
    cancellable: bool = False


class AutonomyQueue(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    running_now: list[AutonomyJob] = Field(default_factory=list)
    waiting_approval: list[AutonomyJob] = Field(default_factory=list)
    failed_needs_attention: list[AutonomyJob] = Field(default_factory=list)
    recently_completed: list[AutonomyJob] = Field(default_factory=list)
    scheduled_next: list[AutonomyJob] = Field(default_factory=list)
    all_jobs: list[AutonomyJob] = Field(default_factory=list)


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
    severity: Severity
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str
    approval_id: str | None = None


class RecommendedAction(BaseModel):
    id: str = Field(default_factory=lambda: f"recommended-action-{uuid4()}")
    reason: str
    severity: Severity
    suggested_action: str
    approval_required: bool = False
    approval_id: str | None = None


class SystemHealthSummary(BaseModel):
    backend_status: Literal["healthy", "watch", "degraded", "critical"] = "healthy"
    neo4j_status: Literal["healthy", "watch", "degraded", "unavailable"] = "healthy"
    worker_status: Literal["healthy", "watch", "degraded", "stopped"] = "healthy"
    frontend_configured: bool = True
    external_source_status: Literal["healthy", "watch", "degraded", "not_configured"] = "watch"
    severity: Severity = "info"


class AutonomySummary(BaseModel):
    completed_jobs: int = 0
    failed_jobs: int = 0
    retries: int = 0
    pending_approvals: int = 0
    interventions_proposed: int = 0
    high_risk_alerts: int = 0


class DataOpsSummary(BaseModel):
    new_products_discovered: int = 0
    price_snapshots_updated: int = 0
    stale_prices_detected: int = 0
    telemetry_snapshots_ingested: int = 0
    telemetry_gaps_detected: int = 0
    enrichment_jobs_completed: int = 0
    saudi_listings_ingested: int = 0
    saudi_listings_with_recommended_option: int = 0
    saudi_risky_only_products: int = 0
    saudi_local_listing_count: int = 0
    saudi_imported_listing_count: int = 0
    saudi_suspicious_price_count: int = 0
    saudi_products_needing_review: int = 0
    saudi_unknown_vat_vendors: list[str] = Field(default_factory=list)
    saudi_unknown_shipping_vendors: list[str] = Field(default_factory=list)
    saudi_build_readiness_score: float = Field(default=0, ge=0, le=1)
    saudi_build_ready_categories: list[str] = Field(default_factory=list)
    saudi_build_missing_categories: list[str] = Field(default_factory=list)
    saudi_build_request_count: int = 0
    failed_build_generations: int = 0
    common_missing_build_components: list[str] = Field(default_factory=list)
    recommended_build_discovery_jobs: list[dict[str, Any]] = Field(default_factory=list)


class CognitionOpsSummary(BaseModel):
    low_confidence_products: int = 0
    governance_risks: int = 0
    alignment_warnings: int = 0
    evolution_drift_warnings: int = 0
    anomaly_spikes: int = 0
    contradiction_increases: int = 0


class SourceHealthSummary(BaseModel):
    configured_sources: int = 0
    missing_api_keys: list[str] = Field(default_factory=list)
    degraded_sources: list[str] = Field(default_factory=list)
    quota_warnings: list[str] = Field(default_factory=list)
    last_successful_sync_by_source: dict[str, datetime | None] = Field(default_factory=dict)


class DailyFounderReport(BaseModel):
    id: str = Field(default_factory=lambda: f"daily-founder-report-{uuid4()}")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    region: str = "SA"
    region_currency: str | None = None
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
    recommended_next_actions: list[RecommendedAction] = Field(default_factory=list)
    recent_audit_events: list[AuditEvent] = Field(default_factory=list)
    system_summary: SystemHealthSummary = Field(default_factory=SystemHealthSummary)
    autonomy_summary: AutonomySummary = Field(default_factory=AutonomySummary)
    data_summary: DataOpsSummary = Field(default_factory=DataOpsSummary)
    cognition_summary: CognitionOpsSummary = Field(default_factory=CognitionOpsSummary)
    source_summary: SourceHealthSummary = Field(default_factory=SourceHealthSummary)
    handled_automatically: list[str] = Field(default_factory=list)
    needs_attention: list[FounderAlert] = Field(default_factory=list)


class OpsRunbook(BaseModel):
    autonomy_levels: dict[AutonomyLevel, list[str]]
    schedules: dict[str, list[str]]
    safe_defaults: list[str]
