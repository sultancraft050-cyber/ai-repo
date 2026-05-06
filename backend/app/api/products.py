from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_pricing_repository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import (
    PriceHistoryPoint,
    PriceSnapshotView,
    ProductCategoryResponse,
    ProductDetail,
    ProductSearchResult,
)
from app.services.hardware_taxonomy import BUILD_CRITICAL_CATEGORIES

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/search", response_model=list[ProductSearchResult])
def search_products(
    q: str = "",
    category: str | None = None,
    region: str | None = "US",
    limit: int = Query(default=25, ge=1, le=100),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[ProductSearchResult]:
    return repository.search_products(q=q, category=category, region=region, limit=limit)


@router.get("/categories", response_model=ProductCategoryResponse)
def product_categories(
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> ProductCategoryResponse:
    return ProductCategoryResponse(
        categories=repository.product_categories(),
        build_critical_categories=sorted(BUILD_CRITICAL_CATEGORIES),
    )


@router.get("/{product_id}", response_model=ProductDetail)
def product_detail(
    product_id: str,
    region: str | None = "US",
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> ProductDetail:
    product = repository.product_detail(product_id, region=region)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.get("/{product_id}/prices", response_model=list[PriceSnapshotView])
def product_prices(
    product_id: str,
    region: str | None = "US",
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[PriceSnapshotView]:
    return repository.vendor_prices(product_id, region=region)


@router.get("/{product_id}/history", response_model=list[PriceHistoryPoint])
def product_history(
    product_id: str,
    region: str | None = "US",
    limit: int = Query(default=200, ge=1, le=1000),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[PriceHistoryPoint]:
    return repository.price_history(product_id, region=region, limit=limit)
