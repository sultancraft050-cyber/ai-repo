from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import (
    get_alignment_repository,
    get_autonomy_repository,
    get_cognition_repository,
    get_evolution_repository,
    get_governance_repository,
    get_ops_repository,
    get_telemetry_repository,
)
from app.graph.alignment_repository import Neo4jAlignmentRepository
from app.graph.autonomy_repository import Neo4jAutonomyRepository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.autonomy import (
    AgentDefinition,
    AutonomyRunRequest,
    AutonomyRunResponse,
    AutonomousCognitionReport,
    CognitionEventIngestRequest,
    CognitionEventIngestResponse,
)
from app.services.autonomy_service import AutonomousCognitionService
from app.services.ops import OpsService

router = APIRouter(prefix="/autonomy", tags=["autonomous-cognition"])


def _service(
    autonomy_repository: Neo4jAutonomyRepository,
    alignment_repository: Neo4jAlignmentRepository,
    evolution_repository: Neo4jEvolutionRepository,
    governance_repository: Neo4jGovernanceRepository,
    cognition_repository: Neo4jCognitionRepository,
    telemetry_repository: Neo4jTelemetryRepository,
) -> AutonomousCognitionService:
    return AutonomousCognitionService(
        autonomy_repository,
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    )


@router.get("/agents", response_model=list[AgentDefinition])
def active_agents(
    autonomy_repository: Neo4jAutonomyRepository = Depends(get_autonomy_repository),
    alignment_repository: Neo4jAlignmentRepository = Depends(get_alignment_repository),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> list[AgentDefinition]:
    return _service(
        autonomy_repository,
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).agents()


@router.get("/products/{product_id}", response_model=AutonomousCognitionReport)
def product_autonomy(
    product_id: str,
    refresh: bool = Query(default=False),
    persist: bool = Query(default=True),
    autonomy_repository: Neo4jAutonomyRepository = Depends(get_autonomy_repository),
    alignment_repository: Neo4jAlignmentRepository = Depends(get_alignment_repository),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> AutonomousCognitionReport:
    return _service(
        autonomy_repository,
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).report(product_id, refresh=refresh, persist=persist)


@router.post("/run", response_model=AutonomyRunResponse)
def run_autonomous_cognition(
    request_body: AutonomyRunRequest,
    autonomy_repository: Neo4jAutonomyRepository = Depends(get_autonomy_repository),
    alignment_repository: Neo4jAlignmentRepository = Depends(get_alignment_repository),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
    ops_repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> AutonomyRunResponse:
    response = _service(
        autonomy_repository,
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).run(request_body)
    if request_body.persist:
        ops = OpsService(ops_repository)
        for report in response.reports:
            ops.create_approval_from_autonomy(report)
    return response


@router.post("/events", response_model=CognitionEventIngestResponse)
def ingest_cognition_event(
    request_body: CognitionEventIngestRequest,
    autonomy_repository: Neo4jAutonomyRepository = Depends(get_autonomy_repository),
    alignment_repository: Neo4jAlignmentRepository = Depends(get_alignment_repository),
    evolution_repository: Neo4jEvolutionRepository = Depends(get_evolution_repository),
    governance_repository: Neo4jGovernanceRepository = Depends(get_governance_repository),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
    ops_repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> CognitionEventIngestResponse:
    response = _service(
        autonomy_repository,
        alignment_repository,
        evolution_repository,
        governance_repository,
        cognition_repository,
        telemetry_repository,
    ).ingest_event(request_body)
    if request_body.persist and response.report:
        OpsService(ops_repository).create_approval_from_autonomy(response.report)
    return response
