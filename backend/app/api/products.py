from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.dependencies import get_ops_repository, get_pricing_repository, resolve_market_region
from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import (
    CanonicalMergePreviewRequest,
    CanonicalMergePreviewResponse,
    PriceHistoryPoint,
    PriceSnapshotView,
    ProductCategoryResponse,
    ProductDetail,
    ProductSearchResult,
)
from app.services.graph_integrity import GraphIntegrityService
from app.services.hardware_taxonomy import BUILD_CRITICAL_CATEGORIES

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/search", response_model=list[ProductSearchResult])
def search_products(
    q: str = "",
    category: str | None = None,
    region: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[ProductSearchResult]:
    return repository.search_products(q=q, category=category, region=resolve_market_region(region), limit=limit)


@router.get("/categories", response_model=ProductCategoryResponse)
def product_categories(
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> ProductCategoryResponse:
    return ProductCategoryResponse(
        categories=repository.product_categories(),
        build_critical_categories=sorted(BUILD_CRITICAL_CATEGORIES),
    )


@router.post("/canonical-merge-preview", response_model=CanonicalMergePreviewResponse)
def canonical_merge_preview(
    request_body: CanonicalMergePreviewRequest,
    request: Request,
    pricing_repository: Neo4jPricingRepository = Depends(get_pricing_repository),
    ops_repository: Neo4jOpsRepository = Depends(get_ops_repository),
) -> CanonicalMergePreviewResponse:
    return GraphIntegrityService(pricing_repository, ops_repository).merge_preview(
        product_ids=request_body.product_ids,
        region=resolve_market_region(request_body.region),
        trace_id=getattr(request.state, "trace_id", None),
    )


@router.get("/{product_id}", response_model=ProductDetail)
def product_detail(
    product_id: str,
    region: str | None = None,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> ProductDetail:
    product = repository.product_detail(product_id, region=resolve_market_region(region))
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.get("/{product_id}/prices", response_model=list[PriceSnapshotView])
def product_prices(
    product_id: str,
    region: str | None = None,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[PriceSnapshotView]:
    return repository.vendor_prices(product_id, region=resolve_market_region(region))


@router.get("/{product_id}/history", response_model=list[PriceHistoryPoint])
def product_history(
    product_id: str,
    region: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[PriceHistoryPoint]:
    return repository.price_history(product_id, region=resolve_market_region(region), limit=limit)
