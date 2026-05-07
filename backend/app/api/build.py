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
from app.services.saudi_build_generator import SaudiLocalBuildService

router = APIRouter(prefix="/build", tags=["build-generator"])


@router.post("/generate", response_model=BuildGenerateResponse)
def generate_build(
    request: BuildGenerateRequest,
    repository: Neo4jComponentRepository = Depends(get_repository),
) -> BuildGenerateResponse:
    return BuildSolver(repository).generate(request)


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
    resolve_market_region(request_body.region)
    try:
        return SaudiLocalBuildService(repository).generate_local(
            request_body,
            trace_id=getattr(request.state, "trace_id", None),
        )
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
