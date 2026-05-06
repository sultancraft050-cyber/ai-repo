from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.api.dependencies import get_pricing_repository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import (
    CanonicalizationValidationRequest,
    CanonicalizationValidationResponse,
    ProductDiscoveryRequest,
    ProductDiscoveryResponse,
    PricingJob,
    PricingRefreshRequest,
    PricingRefreshResponse,
    PricingSyncRequest,
    PricingSyncResponse,
)
from app.services.hardware_taxonomy import discovery_queries
from app.services.pricing_ingestion import (
    CanonicalizationValidationService,
    PricingIngestionService,
    ProductDiscoveryService,
    discovery_response,
    refresh_response,
    sync_response,
)

router = APIRouter(prefix="/pricing", tags=["pricing"])


class _NoopPricingRepository:
    def previous_price(self, product_id_or_key: str, vendor_id: str | None = None) -> None:
        return None

    def find_product_id(self, identity) -> None:
        return None


@router.post("/refresh", response_model=PricingRefreshResponse)
def refresh_pricing(
    request_body: PricingRefreshRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> PricingRefreshResponse:
    payload = request_body.model_dump()
    if request_body.wait:
        service = PricingIngestionService(repository)
        if request_body.product_ids:
            aggregate = None
            for product_id in request_body.product_ids:
                result = service.refresh_product(
                    product_id=product_id,
                    region=request_body.region,
                    providers=request_body.providers,
                )
                if aggregate is None:
                    aggregate = result
                else:
                    aggregate.accepted_snapshots += result.accepted_snapshots
                    aggregate.rejected_snapshots += result.rejected_snapshots
                    aggregate.stale_products.extend(result.stale_products or [])
            return refresh_response([], aggregate)
        result = service.sync_query(
            query=request_body.query or "",
            category=request_body.category or "GPU",
            region=request_body.region,
            providers=request_body.providers,
        )
        return refresh_response([], result)

    job = PricingJob(kind="refresh", payload=payload)
    worker = getattr(request.app.state, "pricing_worker", None)
    if worker:
        worker.enqueue(job)
    else:
        repository.create_job(job)
        background_tasks.add_task(_run_refresh_job, repository, job)
    return PricingRefreshResponse(
        job_ids=[job.id],
        status="queued",
        message="pricing refresh queued; existing valid snapshots remain active until new data is accepted",
    )


@router.post("/sync", response_model=PricingSyncResponse)
def sync_pricing(
    request_body: PricingSyncRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> PricingSyncResponse:
    payload = request_body.model_dump()
    if request_body.wait:
        service = PricingIngestionService(repository)
        aggregate = None
        for query in request_body.queries:
            result = service.sync_query(
                query=query,
                category=request_body.category,
                region=request_body.region,
                providers=request_body.providers,
                limit=request_body.limit_per_query,
            )
            if aggregate is None:
                aggregate = result
            else:
                aggregate.accepted_snapshots += result.accepted_snapshots
                aggregate.rejected_snapshots += result.rejected_snapshots
        return sync_response([], aggregate)

    job = PricingJob(kind="sync", payload=payload)
    worker = getattr(request.app.state, "pricing_worker", None)
    if worker:
        worker.enqueue(job)
    else:
        repository.create_job(job)
        background_tasks.add_task(_run_sync_job, repository, job)
    return PricingSyncResponse(
        job_ids=[job.id],
        status="queued",
        message="pricing sync queued; product and price data will be merged into Neo4j",
    )


@router.post("/discover", response_model=ProductDiscoveryResponse)
def discover_products(
    request_body: ProductDiscoveryRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> ProductDiscoveryResponse:
    manager = request.app.state.neo4j
    repository = Neo4jPricingRepository(manager.driver)
    payload = request_body.model_dump()
    plan = discovery_queries(
        categories=request_body.resolved_categories(),
        query=request_body.query,
    )[: request_body.max_queries]
    categories = sorted({category for category, _ in plan})
    controlled_sync = bool(request_body.dry_run or request_body.category or request_body.limit)
    if request_body.dry_run:
        job = PricingJob(kind="discover", payload={**payload, "mode": "dry_run"})
        job.trace_id = getattr(request.state, "trace_id", job.trace_id)
        preview_repository = repository if manager.unavailable_reason is None else _NoopPricingRepository()
        if manager.unavailable_reason is None:
            repository.create_job(job)
        ingestion = PricingIngestionService(preview_repository)  # type: ignore[arg-type]
        result = ingestion.preview_query(
            query=request_body.query or (plan[0][1] if plan else ""),
            category=request_body.category or (request_body.resolved_categories() or ["GPU"])[0],
            region=request_body.region,
            providers=request_body.providers,
            limit=request_body.resolved_limit(),
        )
        job.status = "completed"
        job.accepted_snapshots = result.accepted_snapshots
        job.rejected_snapshots = result.rejected_snapshots
        if manager.unavailable_reason is None:
            repository.update_job(job)
        return discovery_response(
            [job.id],
            categories,
            len(plan) or 1,
            result,
            dry_run=True,
            trace_id=job.trace_id,
        )

    if request_body.wait or controlled_sync:
        if not manager.verify():
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Neo4j is unavailable: {manager.unavailable_reason}",
            )
        job = PricingJob(kind="discover", payload=payload)
        job.trace_id = getattr(request.state, "trace_id", job.trace_id)
        repository.create_job(job)
        ingestion = PricingIngestionService(repository)
        result, plan = ProductDiscoveryService(ingestion).discover(
            categories=request_body.resolved_categories(),
            query=request_body.query,
            region=request_body.region,
            providers=request_body.providers,
            limit_per_query=request_body.resolved_limit(),
            max_queries=request_body.max_queries,
        )
        job.status = "completed"
        job.accepted_snapshots = result.accepted_snapshots
        job.rejected_snapshots = result.rejected_snapshots
        job.error = "; ".join(result.source_errors or []) or None
        repository.update_job(job)
        return discovery_response([job.id], categories, len(plan), result, trace_id=job.trace_id)

    job = PricingJob(kind="discover", payload=payload)
    worker = getattr(request.app.state, "pricing_worker", None)
    if worker:
        worker.enqueue(job)
    else:
        repository.create_job(job)
        background_tasks.add_task(_run_discover_job, repository, job)
    return ProductDiscoveryResponse(
        job_ids=[job.id],
        status="queued",
        message="product discovery queued; new products will be normalized and merged into Neo4j",
        query_count=len(plan),
        categories=categories,
    )


def _run_refresh_job(repository: Neo4jPricingRepository, job: PricingJob) -> None:
    service = PricingIngestionService(repository)
    product_ids = job.payload.get("product_ids") or []
    if product_ids:
        for product_id in product_ids:
            result = service.refresh_product(
                product_id=product_id,
                region=job.payload.get("region", "US"),
                providers=job.payload.get("providers") or [],
            )
            job.accepted_snapshots += result.accepted_snapshots
            job.rejected_snapshots += result.rejected_snapshots
    else:
        result = service.sync_query(
            query=job.payload.get("query") or "",
            category=job.payload.get("category") or "GPU",
            region=job.payload.get("region", "US"),
            providers=job.payload.get("providers") or [],
        )
        job.accepted_snapshots = result.accepted_snapshots
        job.rejected_snapshots = result.rejected_snapshots
    job.status = "completed"
    repository.update_job(job)


def _run_sync_job(repository: Neo4jPricingRepository, job: PricingJob) -> None:
    service = PricingIngestionService(repository)
    for query in job.payload.get("queries") or []:
        result = service.sync_query(
            query=query,
            category=job.payload.get("category") or "GPU",
            region=job.payload.get("region", "US"),
            providers=job.payload.get("providers") or [],
            limit=job.payload.get("limit_per_query", 8),
        )
        job.accepted_snapshots += result.accepted_snapshots
        job.rejected_snapshots += result.rejected_snapshots
    job.status = "completed"
    repository.update_job(job)


def _run_discover_job(repository: Neo4jPricingRepository, job: PricingJob) -> None:
    service = PricingIngestionService(repository)
    result, _ = ProductDiscoveryService(service).discover(
        categories=job.payload.get("categories") or ([job.payload.get("category")] if job.payload.get("category") else []),
        query=job.payload.get("query"),
        region=job.payload.get("region", "US"),
        providers=job.payload.get("providers") or [],
        limit_per_query=job.payload.get("limit") or job.payload.get("limit_per_query", 8),
        max_queries=job.payload.get("max_queries", 24),
    )
    job.accepted_snapshots = result.accepted_snapshots
    job.rejected_snapshots = result.rejected_snapshots
    job.status = "completed"
    repository.update_job(job)


@router.post("/canonicalize", response_model=CanonicalizationValidationResponse)
def canonicalize_products(
    request_body: CanonicalizationValidationRequest,
    request: Request,
) -> CanonicalizationValidationResponse:
    manager = request.app.state.neo4j
    repository = Neo4jPricingRepository(manager.driver) if manager.unavailable_reason is None else _NoopPricingRepository()
    return CanonicalizationValidationService(repository).validate(
        names=request_body.names,
        category=request_body.category,
    )
