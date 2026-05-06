from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_ops_repository
from app.graph.ops_repository import Neo4jOpsRepository
from app.models.ops import DailyFounderReport, OpsRunbook, SourceHealth, WorkerHealth
from app.services.ops import OpsService

router = APIRouter(prefix="/ops", tags=["solo-founder-operations"])


@router.get("/daily-report", response_model=DailyFounderReport)
def daily_report(
    request: Request,
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> DailyFounderReport:
    manager = request.app.state.neo4j
    connected = manager.verify()
    return OpsService(repository).daily_report(neo4j_connected=connected, app_state=request.app.state)


@router.get("/sources", response_model=list[SourceHealth])
def source_status(repository: Neo4jOpsRepository = Depends(get_ops_repository)) -> list[SourceHealth]:
    return OpsService(repository).source_health()


@router.get("/workers", response_model=list[WorkerHealth])
def worker_status(
    request: Request,
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> list[WorkerHealth]:
    return OpsService(repository).worker_health(request.app.state)


@router.get("/runbook", response_model=OpsRunbook)
def ops_runbook(repository: Neo4jOpsRepository = Depends(get_ops_repository)) -> OpsRunbook:
    return OpsService(repository).runbook()


@router.get("/jobs")
def recent_jobs(
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
):
    try:
        return repository.recent_jobs(50)
    except Exception as error:  # noqa: BLE001 - ops surface should fail with sanitized detail.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve job monitor state.",
        ) from error
