from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_cognition_repository, get_governance_repository, get_telemetry_repository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.governance import GovernanceRefreshRequest, GovernanceRefreshResponse, ReasoningGovernanceReport
from app.services.governance_service import ReasoningGovernanceService

router = APIRouter(prefix="/governance", tags=["reasoning-governance"])


@router.get("/products/{product_id}", response_model=ReasoningGovernanceReport)
def product_governance(
    product_id: str,
    refresh: bool = Query(default=False),
    persist: bool = Query(default=True),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> ReasoningGovernanceReport:
    return ReasoningGovernanceService(
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).report(product_id, refresh=refresh, persist=persist)


@router.post("/refresh", response_model=GovernanceRefreshResponse)
def refresh_governance(
    request_body: GovernanceRefreshRequest,
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> GovernanceRefreshResponse:
    return ReasoningGovernanceService(
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).refresh(request_body)
