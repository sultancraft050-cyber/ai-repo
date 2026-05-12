from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request

from app.api.dependencies import get_pricing_repository, get_repository, resolve_market_region
from app.graph.repository import Neo4jComponentRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.api import (
    BuildGenerateRequest,
    BuildGenerateResponse,
    SaudiBuildDataCompleteness,
    SaudiBuildRequest,
    SaudiBuildResponse,
    SaudiBuildValidationRequest,
    SaudiBuildValidationResponse,
)
from app.services.build_solver import BuildSolver
from app.services.launch_analytics import analytics_from_build_response, record_launch_event
from app.services.saudi_build_generator import SaudiLocalBuildService

router = APIRouter(prefix="/build", tags=["build-generator"])


@router.post("/generate", response_model=BuildGenerateResponse)
def generate_build(
    request: BuildGenerateRequest,
    fastapi_request: Request,
    repository: Neo4jComponentRepository = Depends(get_repository),
) -> BuildGenerateResponse:
    return BuildSolver(repository).generate(
        request,
        trace_id=getattr(fastapi_request.state, "trace_id", None),
    )


@router.get("/data-completeness", response_model=SaudiBuildDataCompleteness)
def build_data_completeness(
    region: str | None = "SA",
    city: str = "Riyadh",
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> SaudiBuildDataCompleteness:
    resolved_region = resolve_market_region(region)
    try:
        return SaudiLocalBuildService(repository).data_completeness(region=resolved_region, city=city)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/generate-local", response_model=SaudiBuildResponse)
def generate_local_build(
    request_body: SaudiBuildRequest,
    request: Request,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> SaudiBuildResponse:
    client = request.client.host if request.client else "unknown"
    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter and not limiter.allow(f"public:build-generate-local:{client}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many build requests. Try again later.")
    resolve_market_region(request_body.region)
    try:
        response = SaudiLocalBuildService(repository).generate_local(
            request_body,
            trace_id=getattr(request.state, "trace_id", None),
        )
        store = getattr(request.app.state, "launch_analytics", None)
        if store:
            session_id = request.headers.get("X-Session-ID")
            user_id = request.headers.get("X-User-ID")
            for event in analytics_from_build_response(
                response=response,
                request_body=request_body,
                session_id=session_id,
                user_id=user_id,
            ):
                record_launch_event(request.app.state, event)
        return response
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/validate", response_model=SaudiBuildValidationResponse)
def validate_local_build(
    request_body: SaudiBuildValidationRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> SaudiBuildValidationResponse:
    resolve_market_region(request_body.region)
    try:
        return SaudiLocalBuildService(repository).validate_local_build(request_body)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
