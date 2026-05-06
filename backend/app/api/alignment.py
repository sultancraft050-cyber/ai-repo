from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_alignment_repository,
    get_cognition_repository,
    get_evolution_repository,
    get_governance_repository,
    get_telemetry_repository,
)
from app.graph.alignment_repository import Neo4jAlignmentRepository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.alignment import AlignmentInspectionReport, AlignmentRefreshRequest, AlignmentRefreshResponse, SystemIdentity
from app.services.alignment_service import CognitiveAlignmentService

router = APIRouter(prefix="/alignment", tags=["cognitive-alignment"])


def _service(
    alignment_repository: Neo4jAlignmentRepository,
    evolution_repository: Neo4jEvolutionRepository,
    governance_repository: Neo4jGovernanceRepository,
    cognition_repository: Neo4jCognitionRepository,
    telemetry_repository: Neo4jTelemetryRepository,
) -> CognitiveAlignmentService:
    return CognitiveAlignmentService(
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    )


@router.get("/identity", response_model=SystemIdentity)
def system_identity(
    alignment_repository: Neo4jAlignmentRepository = Depends(get_alignment_repository),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> SystemIdentity:
    return _service(
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).identity()


@router.get("/products/{product_id}", response_model=AlignmentInspectionReport)
def product_alignment(
    product_id: str,
    refresh: bool = Query(default=False),
    persist: bool = Query(default=True),
    alignment_repository: Neo4jAlignmentRepository = Depends(get_alignment_repository),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> AlignmentInspectionReport:
    return _service(
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).report(product_id, refresh=refresh, persist=persist)


@router.post("/refresh", response_model=AlignmentRefreshResponse)
def refresh_alignment(
    request_body: AlignmentRefreshRequest,
    alignment_repository: Neo4jAlignmentRepository = Depends(get_alignment_repository),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> AlignmentRefreshResponse:
    return _service(
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).refresh(request_body)
