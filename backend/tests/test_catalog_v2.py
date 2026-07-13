from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.models import ApprovalStatus, Base, ImageRightsStatus, Product, ProductCategory, ProductImage, ReviewStatus, StockStatus, Store, StoreOffer, PriceHistory
from app.catalog.repository import CatalogRepository
from app.api.catalog_v2 import list_products
from fastapi import HTTPException


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    Base.metadata.drop_all(engine)


def fixture_catalog(session: Session) -> tuple[Product, Product, StoreOffer]:
    now = datetime.now(timezone.utc)
    cpu = Product(category=ProductCategory.CPU.value, brand="Fixture Labs", normalized_brand="fixture labs", manufacturer_part_number="CPU-001", canonical_name="Fixture CPU 001", slug="fixture-cpu-001", approval_status=ApprovalStatus.APPROVED.value, created_at=now, updated_at=now)
    gpu = Product(category=ProductCategory.GPU.value, brand="Fixture Labs", normalized_brand="fixture labs", manufacturer_part_number="GPU-001", canonical_name="Fixture GPU 001", slug="fixture-gpu-001", approval_status=ApprovalStatus.APPROVED.value, created_at=now, updated_at=now)
    board = Product(category=ProductCategory.MOTHERBOARD.value, brand="Fixture Labs", normalized_brand="fixture labs", manufacturer_part_number="BOARD-001", canonical_name="Fixture Motherboard 001", slug="fixture-board-001", approval_status=ApprovalStatus.APPROVED.value, created_at=now, updated_at=now)
    ram = Product(category=ProductCategory.RAM.value, brand="Fixture Labs", normalized_brand="fixture labs", manufacturer_part_number="RAM-001", canonical_name="Fixture RAM 001", slug="fixture-ram-001", approval_status=ApprovalStatus.APPROVED.value, created_at=now, updated_at=now)
    store_a = Store(name="Fixture Saudi Store A", slug="fixture-store-a", country="SA", status="active", created_at=now, updated_at=now)
    store_b = Store(name="Fixture Saudi Store B", slug="fixture-store-b", country="SA", status="active", created_at=now, updated_at=now)
    session.add_all([cpu, gpu, board, ram, store_a, store_b])
    session.flush()
    image = ProductImage(product_id=cpu.id, source_url="/fixture/cpu.svg", source_name="fixture", source_type="manual", rights_status=ImageRightsStatus.APPROVED.value, review_status=ReviewStatus.APPROVED.value, is_primary=True, created_at=now, updated_at=now)
    pending = ProductImage(product_id=cpu.id, source_url="/fixture/pending.svg", source_name="fixture", source_type="manual", rights_status=ImageRightsStatus.REVIEW.value, review_status=ReviewStatus.PENDING.value, created_at=now, updated_at=now)
    offer = StoreOffer(product_id=cpu.id, store_id=store_a.id, store_sku="CPU-001-A", product_url="https://fixture.example/cpu", currency="SAR", regular_price=Decimal("500"), sale_price=Decimal("450"), stock_status=StockStatus.IN_STOCK.value, observed_at=now, created_at=now, updated_at=now)
    second = StoreOffer(product_id=cpu.id, store_id=store_b.id, store_sku="CPU-001-B", product_url="https://fixture.example/cpu-b", currency="SAR", regular_price=Decimal("475"), stock_status=StockStatus.OUT_OF_STOCK.value, observed_at=now, created_at=now, updated_at=now)
    session.add_all([image, pending, offer, second])
    session.flush()
    session.add_all([PriceHistory(offer_id=offer.id, price=Decimal("500"), currency="SAR", availability=StockStatus.IN_STOCK.value, observed_at=now - timedelta(days=1), created_at=now - timedelta(days=1)), PriceHistory(offer_id=offer.id, price=Decimal("450"), currency="SAR", availability=StockStatus.IN_STOCK.value, observed_at=now, created_at=now)])
    session.commit()
    return cpu, gpu, offer


def test_schema_tables_and_indexes(session):
    cpu, _, _ = fixture_catalog(session)
    names = set(inspect(session.bind).get_table_names())
    assert {"catalog_products", "catalog_product_specifications", "catalog_product_images", "catalog_stores", "catalog_store_offers", "catalog_price_history", "catalog_import_sources", "catalog_import_batches", "catalog_import_errors"} <= names
    assert CatalogRepository(session).list_products(offset=0, limit=10)[0].id == cpu.id


def test_catalog_repository_filters_images_and_selects_cheapest_sar(session):
    cpu, _, offer = fixture_catalog(session)
    repository = CatalogRepository(session)
    assert len(repository.list_approved_images(cpu.id)) == 1
    assert repository.cheapest_sar_offer(cpu.id).id == offer.id
    assert len(repository.list_price_history(offer.id)) == 2


def test_duplicate_slug_and_gtin_rejected(session):
    now = datetime.now(timezone.utc)
    first = Product(category="CPU", brand="Fixture", normalized_brand="fixture", manufacturer_part_number="A", canonical_name="A", slug="same", gtin="fixture-gtin", created_at=now, updated_at=now)
    session.add(first)
    session.commit()
    duplicate = Product(category="GPU", brand="Fixture", normalized_brand="fixture2", manufacturer_part_number="B", canonical_name="B", slug="same", gtin="fixture-gtin", created_at=now, updated_at=now)
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()


def test_catalog_api_is_disabled_without_flag(monkeypatch):
    monkeypatch.delenv("CATALOG_V2_ENABLED", raising=False)
    with pytest.raises(HTTPException) as error:
        list_products(offset=0, limit=50)
    assert error.value.status_code == 404


def test_catalog_api_reports_missing_database_without_connection(monkeypatch):
    monkeypatch.setenv("CATALOG_V2_ENABLED", "true")
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    with pytest.raises(HTTPException) as error:
        list_products(offset=0, limit=50)
    assert error.value.status_code == 503
