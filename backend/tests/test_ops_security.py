from __future__ import annotations

from app.core.security import authenticate_api_key, endpoint_rule, has_role, payload_hash
from app.models.autonomy import AutonomousIntervention
from app.models.ops import ApprovalItem, AuditEvent, AuthPrincipal
from app.services.ops import OpsService


class MemoryOpsRepository:
    def __init__(self) -> None:
        self.approvals: list[ApprovalItem] = []
        self.audit_events: list[AuditEvent] = []

    def upsert_approval(self, approval: ApprovalItem) -> ApprovalItem:
        self.approvals.append(approval)
        return approval

    def update_approval(self, approval: ApprovalItem) -> ApprovalItem:
        return approval

    def create_audit_event(self, event: AuditEvent) -> AuditEvent:
        self.audit_events.append(event)
        return event


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

    assert pricing and pricing.role == "analyst" and pricing.risk_level == "level_0"
    assert rollback and rollback.role == "super_admin" and rollback.approval_required
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
