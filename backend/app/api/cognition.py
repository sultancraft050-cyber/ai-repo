from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import get_cognition_repository, get_telemetry_repository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.cognition import (
    CognitionRefreshRequest,
    CognitionRefreshResponse,
    HardwareCognitionReport,
    LearningJob,
    OutcomeValidationRequest,
    OutcomeValidationResponse,
    PredictionRecord,
)
from app.services.cognition_service import HardwareCognitionService

router = APIRouter(prefix="/cognition", tags=["adaptive-hardware-cognition"])


@router.get("/products/{product_id}", response_model=HardwareCognitionReport)
def product_cognition(
    product_id: str,
    refresh: bool = Query(default=False),
    persist: bool = Query(default=True),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> HardwareCognitionReport:
    return HardwareCognitionService(cognition_repository, telemetry_repository).report(
        product_id,
        refresh=refresh,
        persist=persist,
    )


@router.post("/products/{product_id}/predictions", response_model=list[PredictionRecord])
def generate_predictions(
    product_id: str,
    persist: bool = Query(default=True),
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> list[PredictionRecord]:
    return HardwareCognitionService(cognition_repository, telemetry_repository).generate_predictions(
        product_id,
        persist=persist,
    )


@router.post("/outcomes/validate", response_model=OutcomeValidationResponse)
def validate_outcome(
    request_body: OutcomeValidationRequest,
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> OutcomeValidationResponse:
    return HardwareCognitionService(cognition_repository, telemetry_repository).validate_outcome(request_body)


@router.post("/refresh", response_model=CognitionRefreshResponse)
def refresh_cognition(
    request_body: CognitionRefreshRequest,
    request: Request,
    cognition_repository: Neo4jCognitionRepository = Depends(get_cognition_repository),
    telemetry_repository: Neo4jTelemetryRepository = Depends(get_telemetry_repository),
) -> CognitionRefreshResponse:
    service = HardwareCognitionService(cognition_repository, telemetry_repository)
    if request_body.wait:
        count = 0
        for product_id in request_body.product_ids:
            service.report(product_id, refresh=True, persist=request_body.persist)
            count += 1
        return CognitionRefreshResponse(
            status="completed",
            message=f"refreshed cognition for {count} product(s)",
            refreshed_count=count,
        )
    job = LearningJob(
        kind="refresh_cognition",
        payload={
            "product_ids": request_body.product_ids,
            "persist": request_body.persist,
        },
    )
    worker = getattr(request.app.state, "cognition_worker", None)
    if worker:
        worker.enqueue(job)
    else:
        cognition_repository.create_job(job)
    return CognitionRefreshResponse(
        job_ids=[job.id],
        status="queued",
        message="adaptive cognition refresh queued",
    )
