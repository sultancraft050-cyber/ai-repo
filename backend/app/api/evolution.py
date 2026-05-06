from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_cognition_repository,
    get_evolution_repository,
    get_governance_repository,
    get_telemetry_repository,
)
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.evolution import (
    CognitivePolicy,
    EvolutionOrchestrationReport,
    EvolutionRefreshRequest,
    EvolutionRefreshResponse,
    PolicyCreateRequest,
    PolicyRollbackRequest,
    RollbackEvent,
)
from app.services.evolution_service import EvolutionOrchestrationService

router = APIRouter(prefix="/evolution", tags=["evolution-orchestration"])


def _service(
    evolution_repository: Neo4jEvolutionRepository,
    governance_repository: Neo4jGovernanceRepository,
    cognition_repository: Neo4jCognitionRepository,
    telemetry_repository: Neo4jTelemetryRepository,
) -> EvolutionOrchestrationService:
    return EvolutionOrchestrationService(
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    )


@router.get("/products/{product_id}", response_model=EvolutionOrchestrationReport)
def product_evolution(
    product_id: str,
    refresh: bool = Query(default=False),
    persist: bool = Query(default=True),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> EvolutionOrchestrationReport:
    return _service(
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).report(product_id, refresh=refresh, persist=persist)


@router.get("/policies/active", response_model=CognitivePolicy)
def active_policy(
    scope: str = Query(default="global"),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> CognitivePolicy:
    return _service(
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).active_policy(scope)


@router.post("/policies", response_model=CognitivePolicy)
def create_policy(
    request_body: PolicyCreateRequest,
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> CognitivePolicy:
    return _service(
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).create_policy(request_body)


@router.post("/refresh", response_model=EvolutionRefreshResponse)
def refresh_evolution(
    request_body: EvolutionRefreshRequest,
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> EvolutionRefreshResponse:
    return _service(
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).refresh(request_body)


@router.post("/rollback", response_model=RollbackEvent)
def rollback_policy(
    request_body: PolicyRollbackRequest,
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> RollbackEvent:
    return _service(
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).rollback(request_body)
