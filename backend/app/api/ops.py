from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_ops_repository, resolve_market_region
from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.ops import AuthPrincipal, AutonomyJob, AutonomyQueue, DailyFounderReport, OpsRunbook, SourceConfigStatus, SourceHealth, WorkerHealth
from app.models.pricing import CPUDuplicateReport
from app.models.source_url import SourceMatrixEntry
from app.services.graph_integrity import GraphIntegrityService
from app.services.ops import OpsService

router = APIRouter(prefix="/ops", tags=["solo-founder-operations"])


@router.get("/daily-report", response_model=DailyFounderReport)
def daily_report(
    request: Request,
    region: str | None = None,
) -> DailyFounderReport:
    manager = request.app.state.neo4j
    connected = manager.verify()
    repository = Neo4jOpsRepository(manager.driver)
    return OpsService(repository).daily_report(
        neo4j_connected=connected,
        app_state=request.app.state,
        region=resolve_market_region(region),
    )


@router.get("/sources", response_model=list[SourceHealth])
def source_status(request: Request) -> list[SourceHealth]:
    repository = Neo4jOpsRepository(request.app.state.neo4j.driver)
    return OpsService(repository).source_health()


@router.get("/source-config", response_model=list[SourceConfigStatus])
def source_config(request: Request, region: str | None = None) -> list[SourceConfigStatus]:
    repository = Neo4jOpsRepository(request.app.state.neo4j.driver)
    return OpsService(repository).source_config(region=resolve_market_region(region))


@router.get("/source-matrix", response_model=list[SourceMatrixEntry])
def source_matrix(request: Request, region: str | None = None) -> list[SourceMatrixEntry]:
    repository = Neo4jOpsRepository(request.app.state.neo4j.driver)
    return OpsService(repository).source_matrix(region=resolve_market_region(region))


@router.get("/graph-integrity/cpu-duplicates", response_model=CPUDuplicateReport)
def cpu_duplicate_candidates(request: Request, region: str | None = "SA") -> CPUDuplicateReport:
    resolved_region = resolve_market_region(region)
    pricing_repository = Neo4jPricingRepository(request.app.state.neo4j.driver)
    ops_repository = Neo4jOpsRepository(request.app.state.neo4j.driver)
    return GraphIntegrityService(pricing_repository, ops_repository).cpu_duplicates(
        region=resolved_region,
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.get("/workers", response_model=list[WorkerHealth])
def worker_status(
    request: Request,
) -> list[WorkerHealth]:
    repository = Neo4jOpsRepository(request.app.state.neo4j.driver)
    return OpsService(repository).worker_health(request.app.state)


@router.get("/runbook", response_model=OpsRunbook)
def ops_runbook(request: Request) -> OpsRunbook:
    repository = Neo4jOpsRepository(request.app.state.neo4j.driver)
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


@router.get("/autonomy-queue", response_model=AutonomyQueue)
def autonomy_queue(request: Request) -> AutonomyQueue:
    repository = Neo4jOpsRepository(request.app.state.neo4j.driver)
    return OpsService(repository).autonomy_queue()


@router.post("/autonomy-queue/{job_id}/cancel", response_model=AutonomyJob)
def cancel_autonomy_job(
    job_id: str,
    request: Request,
    repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> AutonomyJob:
    principal = getattr(request.state, "principal", AuthPrincipal())
    job = OpsService(repository).cancel_job(
        job_id,
        actor=principal,
        trace_id=getattr(request.state, "trace_id", job_id),
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Autonomy job not found.")
    if job.status != "cancelled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Autonomy job is not cancellable.")
    return job
