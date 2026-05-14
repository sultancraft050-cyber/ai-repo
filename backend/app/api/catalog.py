from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_pricing_repository, resolve_market_region
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.api import CatalogCompletenessResponse
from app.models.catalog import (
    CatalogCoverageResponse,
    CatalogFeedImportRequest,
    CatalogFeedImportResponse,
    CatalogFeedRunView,
)
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


@router.post("/feeds/import", response_model=CatalogFeedImportResponse)
def import_catalog_feed(
    request_body: CatalogFeedImportRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CatalogFeedImportResponse:
    return repository.import_catalog_feed(
        rows=request_body.rows,
        source_name=request_body.source_name,
        category=request_body.category,
        region=resolve_market_region(request_body.region),
        dry_run=request_body.dry_run,
    )


@router.get("/feeds/runs", response_model=list[CatalogFeedRunView])
def catalog_feed_runs(
    limit: int = Query(default=50, ge=1, le=200),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[CatalogFeedRunView]:
    return repository.catalog_feed_runs(limit=limit)


@router.get("/coverage", response_model=CatalogCoverageResponse)
def catalog_coverage(
    region: str | None = "SA",
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CatalogCoverageResponse:
    return repository.catalog_coverage(region=resolve_market_region(region))
