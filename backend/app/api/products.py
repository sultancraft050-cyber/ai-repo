from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.dependencies import get_ops_repository, get_pricing_repository, resolve_market_region
from app.graph.ops_repository import Neo4jOpsRepository
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import (
    CanonicalMergePreviewRequest,
    CanonicalMergePreviewResponse,
    CpuSpecsImportRequest,
    CpuSpecsImportResponse,
    PriceHistoryPoint,
    PriceSnapshotView,
    ProductCategoryResponse,
    ProductDetail,
    ProductImageUpdateRequest,
    ProductImageUpdateResponse,
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
    offset: int = Query(default=0, ge=0, le=10000),
    brand: str | None = None,
    socket: str | None = None,
    chipset: str | None = None,
    memory_type: str | None = None,
    min_price_sar: float | None = Query(default=None, ge=0),
    max_price_sar: float | None = Query(default=None, ge=0),
    in_stock_priced_only: bool = False,
    sort: str = Query(default="recommended", pattern="^(recommended|cheapest|newest|name)$"),
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> list[ProductSearchResult]:
    return repository.search_products(
        q=q,
        category=category,
        region=resolve_market_region(region),
        limit=limit,
        offset=offset,
        brand=brand,
        socket=socket,
        chipset=chipset,
        memory_type=memory_type,
        min_price_sar=min_price_sar,
        max_price_sar=max_price_sar,
        in_stock_priced_only=in_stock_priced_only,
        sort=sort,
    )


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


@router.post("/cpu-specs/import", response_model=CpuSpecsImportResponse)
def import_cpu_specs(
    request_body: CpuSpecsImportRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> CpuSpecsImportResponse:
    return repository.import_cpu_specs(
        rows=request_body.rows,
        source_name=request_body.source_name,
        dry_run=request_body.dry_run,
    )


@router.post("/{product_id}/image", response_model=ProductImageUpdateResponse)
def update_product_image(
    product_id: str,
    request_body: ProductImageUpdateRequest,
    repository: Neo4jPricingRepository = Depends(get_pricing_repository),
) -> ProductImageUpdateResponse:
    updated = repository.update_product_image_url(
        product_id,
        image_url=request_body.image_url,
        source_name=request_body.source_name,
        note=request_body.note,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ProductImageUpdateResponse(
        product_id=product_id,
        image_url=request_body.image_url,
        image_source_name=request_body.source_name,
        updated=True,
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
