from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Query

from app.catalog.database import catalog_database
from app.catalog.repository import CatalogRepository
from app.catalog.schemas import CatalogOfferResponse, CatalogProductDetail, CatalogProductResponse, CatalogStoreResponse

router = APIRouter(prefix="/catalog", tags=["catalog-v2"])


@contextmanager
def _session() -> Iterator:
    if not catalog_database.enabled:
        raise HTTPException(status_code=404, detail="Catalog V2 is not enabled.")
    if not catalog_database.url:
        raise HTTPException(status_code=503, detail="Catalog V2 is unavailable.")
    with catalog_database.session() as session:
        yield session


def _page(offset: int, limit: int) -> tuple[int, int]:
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="offset must be non-negative and limit must be between 1 and 100.")
    return offset, limit


@router.get("/products", response_model=list[CatalogProductResponse])
def list_products(offset: int = Query(0), limit: int = Query(50), category: str | None = None, search: str | None = None):
    offset, limit = _page(offset, limit)
    with _session() as session:
        return CatalogRepository(session).list_products(offset=offset, limit=limit, category=category, search=search)


@router.get("/products/{product_id}", response_model=CatalogProductDetail)
def get_product(product_id: int):
    with _session() as session:
        repository = CatalogRepository(session)
        product = repository.get_product(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Catalog product not found.")
        return CatalogProductDetail(
            id=product.id,
            category=product.category,
            brand=product.brand,
            manufacturer_part_number=product.manufacturer_part_number,
            exact_model=product.exact_model,
            variant=product.variant,
            canonical_name=product.canonical_name,
            slug=product.slug,
            lifecycle_status=product.lifecycle_status,
            approval_status=product.approval_status,
            created_at=product.created_at,
            updated_at=product.updated_at,
            specifications=product.specifications,
            images=repository.list_approved_images(product_id),
            offers=repository.list_current_offers(product_id),
            cheapest_sar_offer=repository.cheapest_sar_offer(product_id),
        )


@router.get("/products/{product_id}/offers", response_model=list[CatalogOfferResponse])
def get_offers(product_id: int):
    with _session() as session:
        return CatalogRepository(session).list_current_offers(product_id)


@router.get("/products/{product_id}/images")
def get_images(product_id: int):
    with _session() as session:
        return CatalogRepository(session).list_approved_images(product_id)


@router.get("/stores", response_model=list[CatalogStoreResponse])
def list_stores(offset: int = Query(0), limit: int = Query(50)):
    offset, limit = _page(offset, limit)
    with _session() as session:
        return CatalogRepository(session).list_stores(offset=offset, limit=limit)
