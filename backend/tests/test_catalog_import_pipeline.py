from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.catalog.import_pipeline import (
    CatalogImportPipeline,
    ImportLimits,
    assert_commit_allowed,
    commit_batch,
    stage_result,
)
from app.catalog.models import (
    Base,
    ImageRightsStatus,
    ImportBatchStatus,
    ImportError,
    ImportProposedAction,
    ImportRecord,
    ImportReviewStatus,
    ImportSource,
    ImportValidationStatus,
    PriceHistory,
    Product,
    ProductImage,
    ProductSpecification,
    ReviewStatus,
    SourceType,
    Store,
    StoreOffer,
)
from app.api import catalog_v2
from app.core.config import Settings
from app.main import app

FIXTURES = Path(__file__).parent / "fixtures" / "catalog_import"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value


@pytest.fixture(autouse=True)
def import_enabled(monkeypatch):
    monkeypatch.setenv("CATALOG_IMPORT_ENABLED", "true")
    monkeypatch.delenv("CATALOG_WRITES_ENABLED", raising=False)


def seed_catalog(session: Session):
    now = datetime.now(timezone.utc)
    first = Product(category="CPU", brand="Synthetic Fixture Labs", normalized_brand="synthetic fixture labs", manufacturer_part_number="SYN-CPU-001", gtin="1234567890128", canonical_name="Synthetic Fixture Processor", slug="synthetic-fixture-processor", approval_status="approved", created_at=now, updated_at=now)
    second = Product(category="GPU", brand="Synthetic Other Labs", normalized_brand="synthetic other labs", manufacturer_part_number="SYN-GPU-002", gtin="1234567890135", canonical_name="Synthetic Fixture GPU", slug="synthetic-fixture-gpu", approval_status="approved", created_at=now, updated_at=now)
    store = Store(name="Synthetic Fixture Store", slug="synthetic-fixture-store", country="SA", status="active", created_at=now, updated_at=now)
    session.add_all([first, second, store])
    session.flush()
    offer = StoreOffer(product_id=first.id, store_id=store.id, store_sku="SYN-SKU-1", product_url="https://synthetic.invalid/product", currency="SAR", regular_price=Decimal("100.00"), sale_price=Decimal("90.00"), stock_status="in_stock", observed_at=now, created_at=now, updated_at=now)
    session.add(offer)
    session.flush()
    session.add(PriceHistory(offer_id=offer.id, price=Decimal("90.00"), currency="SAR", availability="in_stock", observed_at=now, created_at=now))
    session.commit()
    return first, second, store, offer


def run(pipeline: CatalogImportPipeline, rows, entity, *, fmt="json"):
    if fmt == "json":
        content = json.dumps(rows).encode()
    else:
        content = rows
    return pipeline.dry_run(content, file_format=fmt, entity_type=entity)


def product_row(**updates):
    row = {"brand": " Synthetic   Fixture Labs ", "manufacturer_part_number": " SYN-CPU-001 ", "gtin": "1234 5678 9012 8", "canonical_name": " Synthetic Fixture Processor ", "category": " cpu "}
    row.update(updates)
    return row


def test_parses_csv_json_array_and_records_object_with_utf8():
    pipeline = CatalogImportPipeline()
    csv_result = pipeline.dry_run((FIXTURES / "valid_products.csv").read_bytes(), file_format="csv", entity_type="PRODUCT")
    array_result = run(pipeline, [product_row(canonical_name="Synthetic UTF-8 معالج")], "PRODUCT")
    object_result = pipeline.dry_run((FIXTURES / "valid_products.json").read_bytes(), file_format="json", entity_type="PRODUCT")
    assert [len(value.rows) for value in (csv_result, array_result, object_result)] == [1, 1, 1]
    assert array_result.rows[0].normalized_payload["canonical_name"] == "Synthetic UTF-8 معالج"


@pytest.mark.parametrize(("content", "fmt", "code"), [
    (b'{"records":', "json", "MALFORMED_FILE"),
    (b"a,b\n\"unterminated", "csv", "MALFORMED_FILE"),
    (b"[]", "xml", "UNSUPPORTED_FORMAT"),
    (b"\xff", "json", "UNSUPPORTED_ENCODING"),
    (b'{"records":[{"nested":{"x":1}}]}', "json", "UNEXPECTED_PAYLOAD"),
])
def test_rejects_malformed_unsupported_and_nested_inputs(content, fmt, code):
    with pytest.raises(ValueError, match=code):
        CatalogImportPipeline().dry_run(content, file_format=fmt, entity_type="PRODUCT")


def test_enforces_file_row_field_and_dependent_limits():
    with pytest.raises(ValueError, match="FILE_SIZE_EXCEEDED"):
        CatalogImportPipeline(limits=ImportLimits(max_file_size=1)).dry_run(b"[]", file_format="json", entity_type="PRODUCT")
    with pytest.raises(ValueError, match="ROW_LIMIT_EXCEEDED"):
        run(CatalogImportPipeline(limits=ImportLimits(max_rows=1)), [product_row(), product_row(gtin="1234567890135")], "PRODUCT")
    with pytest.raises(ValueError, match="FIELD_LENGTH_EXCEEDED"):
        run(CatalogImportPipeline(limits=ImportLimits(max_field_length=2)), [product_row()], "PRODUCT")


def test_normalizes_product_codes_identity_and_slug():
    row = run(CatalogImportPipeline(), [product_row()], "PRODUCT").rows[0]
    expected = {"brand": "Synthetic Fixture Labs", "normalized_brand": "synthetic fixture labs", "normalized_mpn": "SYNCPU001", "gtin": "1234567890128", "category": "CPU", "slug": "synthetic-fixture-processor"}
    assert expected.items() <= row.normalized_payload.items()


def test_product_matching_order_conflicts_and_title_only_behavior(session):
    first, second, *_ = seed_catalog(session)
    pipeline = CatalogImportPipeline(session)
    assert run(pipeline, [product_row()], "PRODUCT").rows[0].matched_product_id == first.id
    by_id = product_row(product_id=str(first.id), gtin="")
    assert run(pipeline, [by_id], "PRODUCT").rows[0].matched_product_id == first.id
    conflict = product_row(product_id=str(second.id))
    assert run(pipeline, [conflict], "PRODUCT").rows[0].validation_status == ImportValidationStatus.AMBIGUOUS
    incompatible_brand = product_row(brand="Synthetic Different Labs", gtin="")
    assert run(pipeline, [incompatible_brand], "PRODUCT").rows[0].validation_status == ImportValidationStatus.AMBIGUOUS
    title_only = product_row(manufacturer_part_number="SYN-NEW", gtin="", canonical_name=first.canonical_name)
    assert run(pipeline, [title_only], "PRODUCT").rows[0].matched_product_id is None


def test_batch_duplicate_and_conflicting_identity_handling():
    exact = product_row()
    result = run(CatalogImportPipeline(), [exact, exact], "PRODUCT")
    assert result.rows[1].proposed_action == ImportProposedAction.SKIP
    conflict = run(CatalogImportPipeline(), [product_row(variant="A"), product_row(variant="B")], "PRODUCT")
    assert all(row.validation_status == ImportValidationStatus.AMBIGUOUS for row in conflict.rows)


def test_store_matching_is_exact_and_requires_country(session):
    *_, store, _ = seed_catalog(session)
    pipeline = CatalogImportPipeline(session)
    by_slug = run(pipeline, [{"name": "Different Display", "slug": "synthetic-fixture-store", "country": "SA"}], "STORE").rows[0]
    by_name = run(pipeline, [{"name": " Synthetic  Fixture Store ", "country": "sa"}], "STORE").rows[0]
    missing = run(pipeline, [{"name": "Synthetic Fixture Store"}], "STORE").rows[0]
    assert by_slug.matched_store_id == by_name.matched_store_id == store.id
    assert missing.error_code == "REQUIRED_FIELD_MISSING"


def offer_row(product_id, store_id, **updates):
    row = {"product_id": str(product_id), "store_id": str(store_id), "store_sku": "SYN-SKU-NEW", "product_url": "https://synthetic.invalid/new", "currency": "sar", "regular_price": "110.00", "sale_price": "100.00", "stock_status": "in_stock", "observed_at": "2026-07-13T10:00:00Z"}
    row.update(updates)
    return row


def test_offers_resolve_dependencies_and_propose_create_or_update(session):
    product, _, store, offer = seed_catalog(session)
    created = run(CatalogImportPipeline(session), [offer_row(product.id, store.id)], "STORE_OFFER").rows[0]
    updated = run(CatalogImportPipeline(session), [offer_row(product.id, store.id, store_sku=offer.store_sku)], "STORE_OFFER").rows[0]
    unchanged = run(CatalogImportPipeline(session), [offer_row(product.id, store.id, store_sku=offer.store_sku, product_url=offer.product_url, regular_price="100.00", sale_price="90.00", observed_at=offer.observed_at.replace(tzinfo=timezone.utc).isoformat())], "STORE_OFFER").rows[0]
    unknown_product = run(CatalogImportPipeline(session), [offer_row(9999, store.id)], "STORE_OFFER").rows[0]
    unknown_store = run(CatalogImportPipeline(session), [offer_row(product.id, 9999)], "STORE_OFFER").rows[0]
    assert created.proposed_action == ImportProposedAction.CREATE
    assert updated.proposed_action == ImportProposedAction.UPDATE
    assert unchanged.proposed_action == ImportProposedAction.SKIP
    assert (unknown_product.error_code, unknown_store.error_code) == ("PRODUCT_NOT_FOUND", "STORE_NOT_FOUND")


@pytest.mark.parametrize(("updates", "code"), [
    ({"regular_price": "-1"}, "INVALID_PRICE"),
    ({"regular_price": "100", "sale_price": "101"}, "INVALID_PRICE"),
    ({"currency": "USD"}, "INVALID_CURRENCY"),
    ({"product_url": "file:///tmp/a"}, "INVALID_URL"),
    ({"observed_at": "not-a-date"}, "INVALID_TIMESTAMP"),
])
def test_offer_validation(session, updates, code):
    product, _, store, _ = seed_catalog(session)
    assert run(CatalogImportPipeline(session), [offer_row(product.id, store.id, **updates)], "STORE_OFFER").rows[0].error_code == code


def test_image_metadata_rights_duplicates_primary_conflicts_and_no_download(session, monkeypatch):
    product, *_ = seed_catalog(session)
    now = datetime.now(timezone.utc)
    session.add(ProductImage(product_id=product.id, source_url="https://synthetic.invalid/old.png", source_name="synthetic", source_type="manual", checksum="old", rights_status=ImageRightsStatus.APPROVED.value, review_status=ReviewStatus.APPROVED.value, is_primary=True, created_at=now, updated_at=now))
    session.commit()
    base = {"product_id": str(product.id), "source_url": "https://synthetic.invalid/new.png", "source_name": "synthetic fixture", "rights_status": "approved", "checksum": "new"}
    approved = run(CatalogImportPipeline(session), [base], "PRODUCT_IMAGE_METADATA").rows[0]
    pending = run(CatalogImportPipeline(session), [{**base, "checksum": "pending", "rights_status": "unknown"}], "PRODUCT_IMAGE_METADATA").rows[0]
    duplicate = run(CatalogImportPipeline(session), [{**base, "checksum": "old"}], "PRODUCT_IMAGE_METADATA").rows[0]
    primary = run(CatalogImportPipeline(session), [{**base, "checksum": "primary", "is_primary": "true"}], "PRODUCT_IMAGE_METADATA").rows[0]
    malformed = run(CatalogImportPipeline(session), [{**base, "source_url": "ftp://synthetic.invalid/a"}], "PRODUCT_IMAGE_METADATA").rows[0]
    assert approved.validation_status == ImportValidationStatus.VALID
    assert pending.error_code == "RIGHTS_REVIEW_REQUIRED"
    assert duplicate.proposed_action == ImportProposedAction.SKIP
    assert primary.error_code == "PRIMARY_IMAGE_CONFLICT"
    assert malformed.error_code == "INVALID_URL"


def test_specification_resolution_normalization_duplicate_and_conflict(session):
    product, *_ = seed_catalog(session)
    now = datetime.now(timezone.utc)
    session.add(ProductSpecification(product_id=product.id, specification_key="boost_clock", normalized_value="5.0", display_value="5.0 GHz", unit="ghz", verified_at=now, created_at=now, updated_at=now))
    session.commit()
    base = {"product_id": str(product.id), "specification_key": " Boost Clock ", "normalized_value": "5.0", "display_value": "5.0 GHz", "unit": " GHz ", "confidence": "0.9"}
    duplicate = run(CatalogImportPipeline(session), [base], "PRODUCT_SPECIFICATION").rows[0]
    conflict = run(CatalogImportPipeline(session), [{**base, "normalized_value": "5.1"}], "PRODUCT_SPECIFICATION").rows[0]
    valid = run(CatalogImportPipeline(session), [{**base, "specification_key": "Core Count", "normalized_value": "8", "source_id": "1"}], "PRODUCT_SPECIFICATION").rows[0]
    assert duplicate.proposed_action == ImportProposedAction.SKIP
    assert conflict.proposed_action == ImportProposedAction.REVIEW
    assert valid.normalized_payload["unit"] == "ghz" and valid.normalized_payload["source_id"] == "1"


def test_price_observations_are_append_only_and_duplicate_safe(session, monkeypatch):
    *_, offer = seed_catalog(session)
    observed = offer.observed_at.replace(tzinfo=timezone.utc).isoformat()
    duplicate = run(CatalogImportPipeline(session), [{"offer_id": str(offer.id), "price": "90.00", "currency": "SAR", "availability": "IN_STOCK", "observed_at": observed}], "PRICE_OBSERVATION").rows[0]
    older = run(CatalogImportPipeline(session), [{"offer_id": str(offer.id), "price": "95", "currency": "SAR", "availability": "IN_STOCK", "observed_at": (offer.observed_at - timedelta(days=1)).replace(tzinfo=timezone.utc).isoformat()}], "PRICE_OBSERVATION").rows[0]
    assert duplicate.proposed_action == ImportProposedAction.SKIP
    assert older.proposed_action == ImportProposedAction.CREATE
    assert offer.regular_price == Decimal("100.00")


def test_staging_persists_safe_counts_errors_and_review_state(session):
    now = datetime.now(timezone.utc)
    source = ImportSource(name="synthetic-fixture", source_type=SourceType.JSON.value, rights_status=ImageRightsStatus.REVIEW.value, active=True, created_at=now, updated_at=now)
    session.add(source)
    session.flush()
    result = run(CatalogImportPipeline(session), [product_row(), product_row()], "PRODUCT")
    batch = stage_result(session, source, result)
    records = session.scalars(select(ImportRecord).where(ImportRecord.batch_id == batch.id)).all()
    errors = session.scalars(select(ImportError).where(ImportError.batch_id == batch.id)).all()
    assert batch.status == ImportBatchStatus.REVIEW_REQUIRED.value
    assert batch.entity_type == "PRODUCT"
    assert (batch.received_count, batch.duplicate_count, batch.staged_count) == (2, 1, 2)
    assert len(records) == 2 and len({row.record_checksum for row in records}) == 2
    assert errors[0].safe_message and "password" not in errors[0].safe_message.lower()


def test_commit_guards_flags_review_invalid_and_is_idempotent(session, monkeypatch):
    now = datetime.now(timezone.utc)
    source = ImportSource(name="synthetic-commit", source_type="json", rights_status="review", active=True, created_at=now, updated_at=now)
    store = Store(name="Synthetic Existing Store", slug="synthetic-existing-store", country="SA", status="active", created_at=now, updated_at=now)
    session.add_all([source, store])
    session.commit()
    result = run(CatalogImportPipeline(session), [{"store_id": str(store.id), "name": store.name, "slug": store.slug, "country": "SA"}], "STORE")
    batch = stage_result(session, source, result)
    batch.status = ImportBatchStatus.READY.value
    session.commit()
    rows = session.scalars(select(ImportRecord).where(ImportRecord.batch_id == batch.id)).all()
    with pytest.raises(RuntimeError, match="disabled"):
        assert_commit_allowed(batch, rows)
    monkeypatch.setenv("CATALOG_WRITES_ENABLED", "true")
    assert commit_batch(session, batch) == 1
    assert batch.status == ImportBatchStatus.COMPLETED.value
    assert commit_batch(session, batch) == 0


def test_older_offer_commit_appends_history_without_replacing_current(session, monkeypatch):
    product, _, store, offer = seed_catalog(session)
    now = datetime.now(timezone.utc)
    source = ImportSource(name="synthetic-older-offer", source_type="json", rights_status="review", active=True, created_at=now, updated_at=now)
    session.add(source)
    session.commit()
    original_observed = offer.observed_at
    original_price = offer.sale_price
    older = offer_row(product.id, store.id, store_sku=offer.store_sku, product_url=offer.product_url, regular_price="100.00", sale_price="80.00", observed_at=(offer.observed_at - timedelta(days=2)).replace(tzinfo=timezone.utc).isoformat())
    batch = stage_result(session, source, run(CatalogImportPipeline(session), [older], "STORE_OFFER"))
    assert batch.status == ImportBatchStatus.READY.value
    monkeypatch.setenv("CATALOG_WRITES_ENABLED", "true")
    before = len(session.scalars(select(PriceHistory).where(PriceHistory.offer_id == offer.id)).all())
    assert commit_batch(session, batch) == 1
    session.refresh(offer)
    after = len(session.scalars(select(PriceHistory).where(PriceHistory.offer_id == offer.id)).all())
    assert (offer.observed_at, offer.sale_price) == (original_observed, original_price)
    assert after == before + 1


def test_flags_default_off_and_no_new_public_import_route(monkeypatch):
    monkeypatch.delenv("CATALOG_IMPORT_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="disabled"):
        run(CatalogImportPipeline(), [product_row()], "PRODUCT")
    routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
    assert not any(path.startswith("/catalog/v2/import") for _, path in routes)
    assert all(route.methods <= {"GET"} for route in catalog_v2.router.routes)
    monkeypatch.delenv("CATALOG_V2_ENABLED", raising=False)
    monkeypatch.delenv("CATALOG_WRITES_ENABLED", raising=False)
    settings = Settings.from_env()
    assert not settings.catalog_v2_enabled and not settings.catalog_import_enabled and not settings.catalog_writes_enabled


def test_unknown_sensitive_fields_are_rejected_and_not_staged():
    result = run(CatalogImportPipeline(), [{**product_row(), "authorization": "synthetic-secret-value"}], "PRODUCT")
    row = result.rows[0]
    assert row.error_code == "UNEXPECTED_FIELD"
    assert "authorization" not in row.normalized_payload
    assert "synthetic-secret-value" not in json.dumps(row.normalized_payload)


def test_staging_schema_has_constraints_and_index(session):
    schema = inspect(session.bind)
    assert "catalog_import_records" in schema.get_table_names()
    uniques = {tuple(item["column_names"]) for item in schema.get_unique_constraints("catalog_import_records")}
    indexes = {item["name"] for item in schema.get_indexes("catalog_import_records")}
    assert {("batch_id", "row_number"), ("batch_id", "record_checksum")} <= uniques
    assert "ix_catalog_import_record_batch_status" in indexes
