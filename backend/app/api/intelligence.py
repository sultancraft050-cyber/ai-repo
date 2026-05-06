from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.api.dependencies import get_pricing_repository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.intelligence import (
    EnrichmentRequest,
    EnrichmentResponse,
    HardwareIntelligence,
    IntelligenceRefreshResponse,
)
from app.models.pricing import PricingJob
from app.services.hardware_enrichment import HardwareEnrichmentService

router = APIRouter(prefix="/intelligence", tags=["hardware-intelligence"])


@router.get("/products/{product_id}", response_model=HardwareIntelligence)
def product_intelligence(
    product_id: str,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> HardwareIntelligence:
    intelligence = HardwareEnrichmentService(repository).get_or_create(product_id)
    if not intelligence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return intelligence


@router.post("/enrich", response_model=EnrichmentResponse)
def enrich_products(
    request_body: EnrichmentRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> EnrichmentResponse:
    return HardwareEnrichmentService(repository).enrich(request_body)


@router.post("/refresh", response_model=IntelligenceRefreshResponse)
def refresh_intelligence(
    request_body: EnrichmentRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> IntelligenceRefreshResponse:
    payload = request_body.model_dump()
    job = PricingJob(kind="enrich", payload=payload)
    worker = getattr(request.app.state, "pricing_worker", None)
    if worker:
        worker.enqueue(job)
    else:
        repository.create_job(job)
        background_tasks.add_task(_run_enrichment_job, repository, job)
    return IntelligenceRefreshResponse(
        job_ids=[job.id],
        status="queued",
        message="hardware intelligence enrichment queued",
    )


def _run_enrichment_job(repository: Neo4jPricingRepository, job: PricingJob) -> None:
    result = HardwareEnrichmentService(repository).enrich(EnrichmentRequest(**job.payload))
    job.accepted_snapshots = result.enriched_count
    job.rejected_snapshots = result.skipped_count
    job.status = "completed"
    repository.update_job(job)
