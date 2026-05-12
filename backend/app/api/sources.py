from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_pricing_repository
from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.launch import AnalyticsEventCreate
from app.models.ops import AuditEvent, AuthPrincipal
from app.models.source_url import (
    KnownProductUrlView,
    ProductUrlIngestRequest,
    ProductUrlIngestResponse,
    ProductUrlPreviewRequest,
    ProductUrlPreviewResponse,
    ProductUrlRefreshRequest,
    ProductUrlRefreshResponse,
    PublicDealSubmissionRequest,
    PublicDealSubmissionResponse,
)
from app.services.launch_analytics import record_launch_event
from app.services.product_url_sources import ProductUrlIngestionService, ProductUrlPolicyError, ProductUrlPolicyRegistry

router = APIRouter(prefix="/sources", tags=["known-product-url-sources"])


def _public_rate_limited(request: Request, key: str, limit_hint: str) -> None:
    client = request.client.host if request.client else "unknown"
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter and not limiter.allow(f"public:{key}:{client}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Too many {limit_hint}. Try again later.")


@router.get("/product-url/known", response_model=list[KnownProductUrlView])
def known_product_urls(
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
    region: str = "SA",
    category: str | None = None,
    vendor: str | None = None,
    limit: int = 20,
) -> list[KnownProductUrlView]:
    return [
        KnownProductUrlView.model_validate(item)
        for item in repository.known_product_urls(region=region, category=category, vendor=vendor, limit=limit)
    ]


@router.post("/product-url/preview", response_model=ProductUrlPreviewResponse)
def preview_product_url(
    request_body: ProductUrlPreviewRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> ProductUrlPreviewResponse:
    preview = ProductUrlIngestionService(repository).preview(request_body)
    if preview.source_policy_status in {"blocked", "unsupported"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product URL is not allowed by source policy.",
        )
    return preview


@router.post("/product-url/ingest", response_model=ProductUrlIngestResponse)
def ingest_product_url(
    request_body: ProductUrlIngestRequest,
    request: Request,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> ProductUrlIngestResponse:
    if not request_body.approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="approved=true is required for product URL ingest.",
        )
    principal = getattr(request.state, "principal", AuthPrincipal())
    trace_id = getattr(request.state, "trace_id", "trace-product-url-ingest")
    response = ProductUrlIngestionService(repository).ingest(
        request_body,
        actor=principal.actor,
        role=principal.role,
        trace_id=trace_id,
    )
    if response.status != "ingested":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=response.preview.rejected_reasons)
    audit = AuditEvent(
        actor=principal.actor,
        role=principal.role,
        action="sources.product_url.ingest",
        endpoint="/sources/product-url/ingest",
        method="POST",
        target=response.product_id,
        result="succeeded",
        status_code=200,
        trace_id=trace_id,
        approval_required=False,
        risk_level="level_1",
        metadata={
            "region": response.preview.region,
            "market_source": response.preview.source_name or "",
            "normalized_url": response.normalized_url,
            "category": response.preview.category,
        },
    )
    try:
        Neo4jOpsRepository(request.app.state.neo4j.driver).create_audit_event(audit)
        repository.link_product_url_audit(normalized_url=response.normalized_url, audit_id=audit.id)
        response.audit_event_id = audit.id
    except Exception:
        response.audit_event_id = None
    return response


@router.post("/product-url/refresh", response_model=ProductUrlRefreshResponse)
def refresh_product_urls(
    request_body: ProductUrlRefreshRequest,
    request: Request,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> ProductUrlRefreshResponse:
    trace_id = getattr(request.state, "trace_id", "trace-product-url-refresh")
    return ProductUrlIngestionService(repository).refresh(request_body, trace_id=trace_id)


@router.post("/deal-submissions", response_model=PublicDealSubmissionResponse)
def submit_public_deal(request_body: PublicDealSubmissionRequest, request: Request) -> PublicDealSubmissionResponse:
    _public_rate_limited(request, "deal-submissions", "deal submissions")
    try:
        policy, normalized = ProductUrlPolicyRegistry().identify(request_body.url)
    except ProductUrlPolicyError as error:
        store = getattr(request.app.state, "launch_analytics", None)
        if store:
            record_launch_event(
                request.app.state,
                AnalyticsEventCreate(
                    event_type="deal_submission",
                    region=request_body.region,
                    anonymous_session_id=request.headers.get("X-Session-ID"),
                    category=request_body.category,
                    metadata={"status": "rejected", "reason": str(error)[:160]},
                )
            )
        return PublicDealSubmissionResponse(
            status="rejected",
            region=request_body.region,
            category=request_body.category,
            message=f"Deal URL rejected: {error}. Use a supported public product page.",
        )
    store = getattr(request.app.state, "launch_analytics", None)
    if store:
        record_launch_event(
            request.app.state,
            AnalyticsEventCreate(
                event_type="deal_submission",
                region=request_body.region,
                anonymous_session_id=request.headers.get("X-Session-ID"),
                category=request_body.category,
                metadata={"status": "accepted", "source_name": policy.source_name},
            )
        )
    return PublicDealSubmissionResponse(
        status="accepted",
        normalized_url=normalized,
        source_name=policy.source_name,
        region=request_body.region,
        category=request_body.category,
        message="Deal URL accepted for founder review. No ingestion was run.",
    )
