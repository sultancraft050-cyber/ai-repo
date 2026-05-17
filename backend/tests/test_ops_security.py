from __future__ import annotations

from app.core.security import authenticate_api_key, endpoint_rule, has_role, payload_hash
from app.models.autonomy import AutonomousIntervention
from app.models.ops import ApprovalItem, AuditEvent, AuthPrincipal, AutonomyJob, WorkerHealth
from app.services.ops import OpsService


class MemoryOpsRepository:
    def __init__(self) -> None:
        self.approvals: list[ApprovalItem] = []
        self.audit_events: list[AuditEvent] = []
        self.jobs: list[AutonomyJob] = []

    def upsert_approval(self, approval: ApprovalItem) -> ApprovalItem:
        self.approvals = [item for item in self.approvals if item.id != approval.id]
        self.approvals.append(approval)
        return approval

    def unresolved_approval_exists(self, approval_id: str) -> bool:
        return any(item.id == approval_id and item.status in {"pending", "deferred"} for item in self.approvals)

    def approval_by_id(self, approval_id: str) -> ApprovalItem | None:
        return next((item for item in self.approvals if item.id == approval_id), None)

    def update_approval(self, approval: ApprovalItem) -> ApprovalItem:
        self.approvals = [item for item in self.approvals if item.id != approval.id]
        self.approvals.append(approval)
        return approval

    def create_audit_event(self, event: AuditEvent) -> AuditEvent:
        self.audit_events.append(event)
        return event

    def pending_approvals(self) -> list[ApprovalItem]:
        return [item for item in self.approvals if item.status == "pending"]

    def recent_jobs(self, limit: int = 30):
        return []

    def recent_audit_events(self, limit: int = 25) -> list[AuditEvent]:
        return self.audit_events[-limit:]

    def successful_refresh_count(self) -> int:
        return 0

    def new_products_24h(self) -> int:
        return 0

    def graph_counts(self) -> dict[str, int]:
        return {
            "product_count": 0,
            "stale_product_count": 0,
            "pending_approval_count": len(self.pending_approvals()),
            "recent_audit_count": len(self.audit_events),
        }

    def upsert_daily_report(self, report):
        return report

    def autonomy_jobs(self, limit: int = 75) -> list[AutonomyJob]:
        return self.jobs[:limit]

    def cancel_autonomy_job(self, job_id: str):
        return None


def test_role_permissions_are_hierarchical() -> None:
    key_map = {"viewer-key": "viewer", "admin-key": "admin", "super-key": "super_admin"}

    viewer = authenticate_api_key("viewer-key", key_map)  # type: ignore[arg-type]
    admin = authenticate_api_key("admin-key", key_map)  # type: ignore[arg-type]
    super_admin = authenticate_api_key("super-key", key_map)  # type: ignore[arg-type]

    assert has_role(admin, "analyst")
    assert has_role(super_admin, "admin")
    assert not has_role(viewer, "analyst")


def test_protected_endpoint_rules_classify_mutations() -> None:
    pricing = endpoint_rule("POST", "/pricing/refresh")
    rollback = endpoint_rule("POST", "/evolution/rollback")
    public = endpoint_rule("GET", "/products/search")
    hybrid_integrity = endpoint_rule("GET", "/catalog/hybrid/integrity")
    canonical_evidence = endpoint_rule("POST", "/catalog/canonical/evidence")

    assert pricing and pricing.role == "analyst" and pricing.risk_level == "level_0"
    assert rollback and rollback.role == "super_admin" and rollback.approval_required
    assert hybrid_integrity and hybrid_integrity.role == "analyst"
    assert canonical_evidence and canonical_evidence.role == "admin" and canonical_evidence.risk_level == "level_1"
    assert public is None


def test_payload_hash_is_deterministic() -> None:
    body = b'{"product_ids":["gpu:test"]}'

    assert payload_hash(body) == payload_hash(body)
    assert payload_hash(body) != payload_hash(b"{}")


def test_approval_decision_writes_audit_event() -> None:
    repository = MemoryOpsRepository()
    service = OpsService(repository)  # type: ignore[arg-type]
    approval = ApprovalItem(
        action_type="evidence_quarantine",
        affected_entities=["gpu:test"],
        risk_level="level_2",
        reasoning="test approval flow",
        rollback_plan="restore prior evidence status",
    )

    response = service.decide_approval(
        approval,
        actor=AuthPrincipal(actor="admin:test", role="admin", authenticated=True),
        approved=True,
        note="ok",
        trace_id="trace-test",
    )

    assert response.approval.status == "approved"
    assert repository.audit_events[0].action == "approval.approve"
    assert repository.audit_events[0].approval_required


def test_approval_rejection_writes_audit_event() -> None:
    repository = MemoryOpsRepository()
    service = OpsService(repository)  # type: ignore[arg-type]
    approval = ApprovalItem(
        action_type="source_trust_downgrade",
        affected_entities=["source:test"],
        risk_level="level_2",
        reasoning="test rejection flow",
        rollback_plan="leave source trust unchanged",
    )

    response = service.decide_approval(
        approval,
        actor=AuthPrincipal(actor="admin:test", role="admin", authenticated=True),
        approved=False,
        note="not enough evidence",
        trace_id="trace-test",
    )

    assert response.approval.status == "rejected"
    assert repository.audit_events[0].action == "approval.reject"


def test_level_3_action_cannot_be_approved_for_auto_execution() -> None:
    repository = MemoryOpsRepository()
    service = OpsService(repository)  # type: ignore[arg-type]
    approval = ApprovalItem(
        action_type="database_deletion",
        affected_entities=["graph"],
        risk_level="level_3",
        reasoning="manual only",
        rollback_plan="restore from external backup",
    )

    response = service.decide_approval(
        approval,
        actor=AuthPrincipal(actor="super:test", role="super_admin", authenticated=True),
        approved=True,
        note="blocked",
        trace_id="trace-test",
    )

    assert response.approval.status == "pending"
    assert response.audit_event.result == "blocked"
    assert response.audit_event.action == "approval.blocked_level_3"


def test_autonomy_intervention_creates_approval_item() -> None:
    repository = MemoryOpsRepository()
    service = OpsService(repository)  # type: ignore[arg-type]

    class Report:
        id = "autonomy:test"
        product_id = "gpu:test"
        interventions = [
            AutonomousIntervention(
                kind="evidence_quarantine",
                status="requires_approval",
                agent_kind="governance_stability",
                target="evidence:test",
                severity="critical",
                reason="high risk graph mutation",
                requires_human_approval=True,
            )
        ]

    approvals = service.create_approval_from_autonomy(Report())  # type: ignore[arg-type]

    assert approvals
    assert approvals[0].risk_level == "level_2"
    assert approvals[0].status == "pending"


def test_autonomy_intervention_does_not_duplicate_unresolved_approval() -> None:
    repository = MemoryOpsRepository()
    service = OpsService(repository)  # type: ignore[arg-type]

    class Report:
        id = "autonomy:test"
        product_id = "gpu:test"
        interventions = [
            AutonomousIntervention(
                kind="evidence_quarantine",
                status="requires_approval",
                agent_kind="governance_stability",
                target="evidence:test",
                severity="critical",
                reason="high risk graph mutation",
                requires_human_approval=True,
            )
        ]

    service.create_approval_from_autonomy(Report())  # type: ignore[arg-type]
    service.create_approval_from_autonomy(Report())  # type: ignore[arg-type]

    assert len(repository.approvals) == 1


def test_daily_report_returns_partial_data_when_subsystems_are_missing() -> None:
    repository = MemoryOpsRepository()
    service = OpsService(repository)  # type: ignore[arg-type]

    report = service.daily_report(neo4j_connected=True, app_state=object())

    assert report.neo4j_health.neo4j_connected
    assert isinstance(report.workers[0], WorkerHealth)
    assert report.recommended_next_actions


def test_autonomy_queue_groups_jobs() -> None:
    repository = MemoryOpsRepository()
    repository.jobs = [
        AutonomyJob(
            job_id="job-running",
            job_type="price_refresh",
            title="Price refresh",
            description="Refresh prices",
            status="running",
            risk_level="level_0",
            approval_required=False,
            attempts=0,
            max_attempts=3,
            trace_id="trace-running",
            summary="running",
        ),
        AutonomyJob(
            job_id="job-approval",
            job_type="evidence_quarantine",
            title="Evidence quarantine",
            description="Quarantine evidence",
            status="requires_approval",
            risk_level="level_2",
            approval_required=True,
            attempts=0,
            max_attempts=3,
            trace_id="trace-approval",
            summary="approval",
        ),
    ]
    service = OpsService(repository)  # type: ignore[arg-type]

    queue = service.autonomy_queue()

    assert queue.running_now[0].job_id == "job-running"
    assert queue.waiting_approval[0].job_id == "job-approval"
    assert queue.scheduled_next
