from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_ops_repository, resolve_market_region
from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.core.config import settings
from app.models.launch import BuildFailureSummary, CatalogGrowthWorkflowSummary, DeploymentChecklist, FounderInsightsSummary, MarketCoverageSummary, MvpHealthDashboard, RuntimeHealthSummary
from app.models.ops import (
    AuthPrincipal,
    AutonomyJob,
    AutonomyQueue,
    DailyFounderReport,
    Neo4jCapacityReport,
    Neo4jOrphansResponse,
    Neo4jPruneExecuteRequest,
    Neo4jPruneExecuteResponse,
    Neo4jPrunePreviewRequest,
    Neo4jPrunePreviewResponse,
    OpsRunbook,
    SourceConfigStatus,
    SourceHealth,
    WorkerHealth,
)
from app.models.pricing import CPUDuplicateReport
from app.models.source_url import SourceMatrixEntry
from app.services.graph_integrity import GraphIntegrityService
from app.services.ops import OpsService
from app.services.launch_analytics import LaunchInsightsService
from app.services.performance_observer import performance_observer
from app.services.saudi_build_generator import SaudiLocalBuildService

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


@router.get("/query-performance")
def query_performance() -> dict:
    return performance_observer.query_performance()


@router.get("/performance-summary")
def performance_summary() -> dict:
    return performance_observer.performance_summary()


@router.get("/neo4j-capacity-report", response_model=Neo4jCapacityReport)
def neo4j_capacity_report(request: Request) -> Neo4jCapacityReport:
    return Neo4jOpsRepository(request.app.state.neo4j.driver).neo4j_capacity_report()


@router.post("/neo4j-prune-preview", response_model=Neo4jPrunePreviewResponse)
def neo4j_prune_preview(request_body: Neo4jPrunePreviewRequest, request: Request) -> Neo4jPrunePreviewResponse:
    if not request_body.dry_run:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prune preview must use dry_run=true.")
    return Neo4jOpsRepository(request.app.state.neo4j.driver).neo4j_prune_preview(request_body)


@router.post("/neo4j-prune-execute", response_model=Neo4jPruneExecuteResponse)
def neo4j_prune_execute(request_body: Neo4jPruneExecuteRequest, request: Request) -> Neo4jPruneExecuteResponse:
    if not request_body.approved:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approved=true is required.")
    return Neo4jOpsRepository(request.app.state.neo4j.driver).neo4j_prune_execute(request_body)


@router.get("/neo4j-orphans", response_model=Neo4jOrphansResponse)
def neo4j_orphans(request: Request) -> Neo4jOrphansResponse:
    return Neo4jOpsRepository(request.app.state.neo4j.driver).neo4j_orphans()


@router.get("/build-failure-summary", response_model=BuildFailureSummary)
def build_failure_summary(request: Request, region: str | None = "SA") -> BuildFailureSummary:
    resolved_region = resolve_market_region(region)
    return _launch_insights(request).build_failure_summary(region=resolved_region)


@router.get("/market-coverage-summary", response_model=MarketCoverageSummary)
def market_coverage_summary(request: Request, region: str | None = "SA") -> MarketCoverageSummary:
    resolved_region = resolve_market_region(region)
    return _launch_insights(request).market_coverage_summary(region=resolved_region)


@router.get("/runtime-health", response_model=RuntimeHealthSummary)
def runtime_health(request: Request) -> RuntimeHealthSummary:
    return _launch_insights(request).runtime_health()


@router.get("/founder-insights", response_model=FounderInsightsSummary)
def founder_insights(request: Request, region: str | None = "SA") -> FounderInsightsSummary:
    resolved_region = resolve_market_region(region)
    return _launch_insights(request).founder_insights(region=resolved_region)


@router.get("/mvp-health-dashboard", response_model=MvpHealthDashboard)
def mvp_health_dashboard(request: Request, region: str | None = "SA") -> MvpHealthDashboard:
    resolved_region = resolve_market_region(region)
    return _launch_insights(request).mvp_health_dashboard(region=resolved_region)


@router.get("/catalog-growth-workflow", response_model=CatalogGrowthWorkflowSummary)
def catalog_growth_workflow(request: Request, region: str | None = "SA") -> CatalogGrowthWorkflowSummary:
    resolved_region = resolve_market_region(region)
    return _launch_insights(request).catalog_growth_workflow(region=resolved_region)


@router.get("/deployment-checklist", response_model=DeploymentChecklist)
def deployment_checklist(request: Request, region: str | None = "SA") -> DeploymentChecklist:
    resolved_region = resolve_market_region(region)
    manager = request.app.state.neo4j
    connected = manager.verify()
    ops_repository = Neo4jOpsRepository(manager.driver)
    ops_service = OpsService(ops_repository)
    source_status = ops_service.source_config(region=resolved_region)
    readiness = None
    if connected:
        try:
            readiness = SaudiLocalBuildService(Neo4jPricingRepository(manager.driver)).data_completeness(
                region=resolved_region,
            )
        except Exception:
            readiness = None
    return _launch_insights(request).deployment_checklist(
        settings=settings,
        neo4j_connected=connected,
        neo4j_detail=manager.unavailable_reason,
        source_config=source_status,
        build_readiness=readiness,
        region=resolved_region,
    )


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


def _launch_insights(request: Request) -> LaunchInsightsService:
    return LaunchInsightsService(
        request.app.state.launch_analytics,
        pricing_repository=Neo4jPricingRepository(request.app.state.neo4j.driver),
        ops_service=OpsService(Neo4jOpsRepository(request.app.state.neo4j.driver)),
    )
