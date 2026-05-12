from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_pricing_repository, resolve_market_region
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.api import CatalogCompletenessResponse
from app.services.saudi_build_generator import SaudiLocalBuildService

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/completeness", response_model=CatalogCompletenessResponse)
def catalog_completeness(
    region: str | None = "SA",
    city: str = "Riyadh",
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CatalogCompletenessResponse:
    resolved_region = resolve_market_region(region)
    try:
        return SaudiLocalBuildService(repository).catalog_completeness(region=resolved_region, city=city)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

