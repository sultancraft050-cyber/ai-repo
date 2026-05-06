from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_telemetry_repository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.telemetry import (
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    TelemetryReasoningReport,
    TelemetrySnapshotView,
    TelemetrySummary,
)
from app.services.telemetry_analysis import TelemetryAnalysisEngine, TelemetryIngestionService
from app.services.telemetry_reasoning import TelemetryReasoningEngine

router = APIRouter(prefix="/telemetry", tags=["real-world-telemetry"])


@router.post("/ingest", response_model=TelemetryIngestResponse)
def ingest_telemetry(
    request_body: TelemetryIngestRequest,
    repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> TelemetryIngestResponse:
    return TelemetryIngestionService(repository).ingest(request_body)


@router.get("/products/{product_id}", response_model=list[TelemetrySnapshotView])
def product_telemetry(
    product_id: str,
    resolution: str | None = Query(default=None),
    workload: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> list[TelemetrySnapshotView]:
    return repository.snapshots_for_product(
        product_id,
        resolution=resolution,
        workload=workload,
        limit=limit,
    )


@router.get("/products/{product_id}/summary", response_model=TelemetrySummary)
def product_telemetry_summary(
    product_id: str,
    repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> TelemetrySummary:
    snapshots = repository.snapshots_for_product(product_id, limit=300)
    return TelemetryAnalysisEngine().summarize(product_id, snapshots)


@router.get("/products/{product_id}/reasoning", response_model=TelemetryReasoningReport)
def product_telemetry_reasoning(
    product_id: str,
    refresh: bool = Query(default=False),
    persist: bool = Query(default=True),
    repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> TelemetryReasoningReport:
    if not refresh:
        existing = repository.latest_reasoning(product_id)
        if existing:
            return existing
    snapshots = repository.snapshots_for_product(product_id, limit=500)
    summary = TelemetryAnalysisEngine().summarize(product_id, snapshots)
    report = TelemetryReasoningEngine().reason(product_id, snapshots, summary)
    if persist and snapshots:
        repository.upsert_reasoning(report)
    return report


@router.post("/products/{product_id}/reason", response_model=TelemetryReasoningReport)
def recompute_product_telemetry_reasoning(
    product_id: str,
    persist: bool = Query(default=True),
    repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> TelemetryReasoningReport:
    snapshots = repository.snapshots_for_product(product_id, limit=500)
    summary = TelemetryAnalysisEngine().summarize(product_id, snapshots)
    report = TelemetryReasoningEngine().reason(product_id, snapshots, summary)
    if persist and snapshots:
        repository.upsert_reasoning(report)
    return report
