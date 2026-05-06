from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_ops_repository
from app.core.security import has_role
from app.graph.ops_repository import Neo4jOpsRepository
from app.models.ops import ApprovalDecisionRequest, ApprovalDecisionResponse, ApprovalItem, AuthPrincipal
from app.services.ops import OpsService

router = APIRouter(prefix="/approvals", tags=["human-approval-workflow"])


def _principal(request: Request) -> AuthPrincipal:
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, AuthPrincipal):
        return principal
    return AuthPrincipal()


@router.get("/pending", response_model=list[ApprovalItem])
def pending_approvals(repository: Neo4jOpsRepository = Depends(get_ops_repository)) -> list[ApprovalItem]:
    return repository.pending_approvals()


@router.get("/{approval_id}", response_model=ApprovalItem)
def approval_detail(
    approval_id: str,
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> ApprovalItem:
    approval = repository.approval_by_id(approval_id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval item not found.")
    return approval


@router.post("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
def approve_item(
    approval_id: str,
    request_body: ApprovalDecisionRequest,
    request: Request,
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> ApprovalDecisionResponse:
    approval = repository.approval_by_id(approval_id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval item not found.")
    if approval.risk_level == "level_3":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Level 3 manual-only actions cannot be approved for autonomous execution.",
        )
    principal = _principal(request)
    if approval.action_type in {"evolution_rollback", "policy_escalation"} and not has_role(principal, "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="super_admin role required for this approval.")
    return OpsService(repository).decide_approval(
        approval,
        actor=principal,
        approved=True,
        note=request_body.note,
        trace_id=getattr(request.state, "trace_id", approval.trace_id),
    )


@router.post("/{approval_id}/reject", response_model=ApprovalDecisionResponse)
def reject_item(
    approval_id: str,
    request_body: ApprovalDecisionRequest,
    request: Request,
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> ApprovalDecisionResponse:
    approval = repository.approval_by_id(approval_id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval item not found.")
    principal = _principal(request)
    return OpsService(repository).decide_approval(
        approval,
        actor=principal,
        approved=False,
        note=request_body.note,
        trace_id=getattr(request.state, "trace_id", approval.trace_id),
    )


@router.post("/{approval_id}/defer", response_model=ApprovalDecisionResponse)
def defer_item(
    approval_id: str,
    request_body: ApprovalDecisionRequest,
    request: Request,
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> ApprovalDecisionResponse:
    approval = repository.approval_by_id(approval_id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval item not found.")
    return OpsService(repository).defer_approval(
        approval,
        actor=_principal(request),
        note=request_body.note,
        trace_id=getattr(request.state, "trace_id", approval.trace_id),
    )


@router.post("/{approval_id}/mark-reviewed", response_model=ApprovalDecisionResponse)
def mark_item_reviewed(
    approval_id: str,
    request_body: ApprovalDecisionRequest,
    request: Request,
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> ApprovalDecisionResponse:
    approval = repository.approval_by_id(approval_id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval item not found.")
    return OpsService(repository).mark_approval_reviewed(
        approval,
        actor=_principal(request),
        note=request_body.note,
        trace_id=getattr(request.state, "trace_id", approval.trace_id),
    )
