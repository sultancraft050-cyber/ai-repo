from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.api import catalog_v2
from app.catalog.image_review import ImageReviewConfig, ImageReviewService, evaluate_metadata_payload
from app.catalog.import_pipeline import CatalogImportPipeline
from app.catalog.models import (
    ApprovalStatus,
    Base,
    ImageQualityStatus,
    ImageRightsStatus,
    ImportValidationStatus,
    Product,
    ProductImage,
    ProductImageReview,
    ReviewStatus,
)
from app.catalog.repository import CatalogRepository
from app.core.config import Settings

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "catalog_image_review" / "metadata_cases.json"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value


@pytest.fixture(autouse=True)
def review_enabled(monkeypatch):
    monkeypatch.setenv("CATALOG_IMAGE_REVIEW_ENABLED", "true")
    monkeypatch.delenv("CATALOG_WRITES_ENABLED", raising=False)
    monkeypatch.setenv("CATALOG_IMAGE_ALLOWED_HOSTS", "synthetic.example.test")


def product(session: Session, category: str = "GPU") -> Product:
    now = datetime.now(timezone.utc)
    value = Product(category=category, brand="Synthetic Fixture Labs", normalized_brand="synthetic fixture labs", manufacturer_part_number=f"SYN-{category}-001", canonical_name=f"Synthetic {category}", slug=f"synthetic-{category.lower()}-001", approval_status=ApprovalStatus.APPROVED.value, created_at=now, updated_at=now)
    session.add(value)
    session.commit()
    return value


def image_payload(**changes):
    payload = {
        "source_url": "https://synthetic.example.test/image.webp",
        "source_name": "Synthetic Fixture Source",
        "source_type": "SYNTHETIC_FIXTURE",
        "width": 1200,
        "height": 600,
        "format": "WEBP",
        "file_size": 100_000,
        "checksum": "synthetic-checksum-001",
        "rights_status": "APPROVED",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "is_primary": False,
    }
    payload.update(changes)
    return payload


def image(session: Session, product_id: int, **changes) -> ProductImage:
    now = datetime.now(timezone.utc)
    payload = image_payload(**changes)
    payload["source_url"] = changes.get("source_url", f"https://synthetic.example.test/{payload['checksum']}.webp")
    value = ProductImage(product_id=product_id, source_url=payload["source_url"], source_name=payload["source_name"], source_type=payload["source_type"].lower(), width=payload.get("width"), height=payload.get("height"), format=payload.get("format", "").lower(), file_size=payload.get("file_size"), checksum=payload.get("checksum"), rights_status=payload["rights_status"].lower(), quality_status=payload.get("quality_status", ImageQualityStatus.PENDING.value), review_status=payload.get("review_status", ReviewStatus.PENDING.value), is_primary=payload.get("is_primary", False), verified_at=now, created_at=now, updated_at=now)
    session.add(value)
    session.commit()
    return value


def test_configuration_defaults_bounds_and_empty_host_policy(monkeypatch):
    for key in ("CATALOG_V2_ENABLED", "CATALOG_IMPORT_ENABLED", "CATALOG_WRITES_ENABLED", "CATALOG_IMAGE_REVIEW_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings.from_env()
    assert not settings.catalog_v2_enabled and not settings.catalog_import_enabled and not settings.catalog_writes_enabled and not settings.catalog_image_review_enabled
    monkeypatch.setenv("CATALOG_IMAGE_MIN_WIDTH", "0")
    with pytest.raises(ValueError):
        ImageReviewConfig()
    monkeypatch.setenv("CATALOG_IMAGE_MIN_WIDTH", "320")
    monkeypatch.delenv("CATALOG_IMAGE_ALLOWED_HOSTS", raising=False)
    result = evaluate_metadata_payload(image_payload(), "GPU")
    assert "HOST_NOT_APPROVED" in result.reason_codes


def test_synthetic_fixture_catalog_is_metadata_only():
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert len(cases) >= 10
    assert all(item["name"].startswith("synthetic-") for item in cases)
    assert all("synthetic" in item.get("source_url", "") or "example.test" in item.get("source_url", "") or item.get("source_url", "").startswith("/") for item in cases)


@pytest.mark.parametrize(("url", "code"), [
    ("https://user:pass@synthetic.example.test/image.webp", "URL_INVALID"),
    ("javascript:alert(1)", "URL_INVALID"),
    ("file:///tmp/image.webp", "URL_INVALID"),
    ("https://unapproved.example.test/image.webp", "HOST_NOT_APPROVED"),
    ("https://synthetic.example.test/" + "x" * 2050, "URL_INVALID"),
])
def test_url_validation(url, code):
    result = evaluate_metadata_payload(image_payload(source_url=url), "GPU")
    assert code in result.reason_codes


def test_url_policy_accepts_exact_synthetic_host_and_local_reference(monkeypatch):
    assert evaluate_metadata_payload(image_payload(), "GPU").classification == "ACCEPTABLE"
    local = evaluate_metadata_payload(image_payload(source_url="/synthetic/image.webp"), "GPU")
    assert local.results["host_policy_result"] == "LOCAL_REFERENCE"
    monkeypatch.setenv("CATALOG_IMAGE_ALLOW_HTTP", "true")
    http = evaluate_metadata_payload(image_payload(source_url="http://synthetic.example.test/image.webp"), "GPU")
    assert http.results["url_result"] == "PASS"


@pytest.mark.parametrize(("rights", "code", "classification"), [
    ("PENDING", "RIGHTS_PENDING", "REVIEW_REQUIRED"),
    ("UNKNOWN", "RIGHTS_PENDING", "REVIEW_REQUIRED"),
    ("REJECTED", "RIGHTS_REJECTED", "REJECTED"),
    ("EXPIRED", "RIGHTS_EXPIRED", "REJECTED"),
])
def test_rights_gate_public_eligibility(rights, code, classification):
    result = evaluate_metadata_payload(image_payload(rights_status=rights), "GPU")
    assert result.classification == classification and code in result.reason_codes


@pytest.mark.parametrize(("changes", "code"), [
    ({"width": None, "height": None}, "DIMENSIONS_MISSING"),
    ({"width": 100, "height": 100}, "DIMENSIONS_TOO_SMALL"),
    ({"width": 5000, "height": 5000}, "DIMENSIONS_TOO_LARGE"),
    ({"file_size": 6_000_000}, "FILE_SIZE_EXCEEDED"),
    ({"format": "GIF"}, "FORMAT_UNSUPPORTED"),
    ({"checksum": None}, "CHECKSUM_MISSING"),
    ({"verified_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()}, "VERIFICATION_STALE"),
])
def test_quality_metadata_reason_codes(changes, code):
    result = evaluate_metadata_payload(image_payload(**changes), "GPU")
    assert code in result.reason_codes


def test_category_aspect_heuristics():
    assert evaluate_metadata_payload(image_payload(width=2400, height=500), "GPU").classification == "ACCEPTABLE"
    assert "ASPECT_RATIO_REVIEW" in evaluate_metadata_payload(image_payload(width=500, height=2400), "CPU").reason_codes
    assert evaluate_metadata_payload(image_payload(width=500, height=2400), "CASE").results["aspect_ratio_result"] == "PASS"
    assert "CATEGORY_UNKNOWN" in evaluate_metadata_payload(image_payload(), "UNKNOWN").reason_codes


def test_duplicate_detection_same_cross_product_and_conflicting_metadata(session):
    first = product(session, "GPU")
    second = product(session, "CPU")
    existing = image(session, first.id, checksum="same-checksum")
    same = evaluate_metadata_payload(image_payload(checksum="same-checksum"), "GPU", session=session, product_id=first.id)
    cross = evaluate_metadata_payload(image_payload(checksum="same-checksum"), "CPU", session=session, product_id=second.id)
    assert "DUPLICATE_SAME_PRODUCT" in same.reason_codes
    assert "DUPLICATE_CROSS_PRODUCT" in cross.reason_codes
    assert existing.id


def test_review_decisions_are_guarded_append_only_and_primary_safe(session, monkeypatch):
    first = product(session, "GPU")
    old = image(session, first.id, checksum="old-primary", quality_status="acceptable", review_status="approved", is_primary=True)
    candidate = image(session, first.id, checksum="new-primary")
    service = ImageReviewService(session)
    with pytest.raises(RuntimeError, match="writes"):
        service.record_decision(candidate.id, "APPROVE", reason_code="RIGHTS_VERIFIED", safe_reason="Synthetic approval", reviewer_identifier="fixture-reviewer")
    monkeypatch.setenv("CATALOG_WRITES_ENABLED", "true")
    audit = service.record_decision(candidate.id, "APPROVE", reason_code="RIGHTS_VERIFIED", safe_reason="Synthetic approval", reviewer_identifier="fixture-reviewer")
    assert audit.decision == "APPROVE"
    primary_audit = service.record_decision(candidate.id, "APPROVE_PRIMARY", reason_code="PRIMARY_SELECTED", safe_reason="Explicit synthetic primary selection", reviewer_identifier="fixture-reviewer")
    session.refresh(old)
    assert primary_audit.proposed_primary and not old.is_primary and candidate.is_primary
    history = service.review_history(candidate.id)
    assert [entry.decision for entry in history] == ["APPROVE", "APPROVE_PRIMARY"]
    service.record_decision(candidate.id, "EXPIRE_RIGHTS", reason_code="RIGHTS_EXPIRED", safe_reason="Synthetic expiry", reviewer_identifier="fixture-reviewer")
    assert len(service.review_history(candidate.id)) == 3


def test_public_visibility_filters_review_results(session):
    first = product(session, "GPU")
    public = image(session, first.id, checksum="public", quality_status="acceptable", review_status="approved")
    pending = image(session, first.id, checksum="pending", rights_status="pending", quality_status="pending", review_status="pending")
    visible = CatalogRepository(session).list_approved_images(first.id)
    assert [item.id for item in visible] == [public.id]
    session.refresh(public)
    public.verified_at = datetime.now(timezone.utc)
    public.source_url = "https://synthetic.example.test/public.webp"
    public.rights_status, public.quality_status, public.review_status = "approved", "acceptable", "approved"
    session.commit()
    visible = CatalogRepository(session).list_approved_images(first.id)
    assert [item.id for item in visible] == [public.id]


def test_import_pipeline_integration_requires_review(monkeypatch, session):
    first = product(session, "GPU")
    monkeypatch.setenv("CATALOG_IMPORT_ENABLED", "true")
    result = CatalogImportPipeline(session).dry_run(json.dumps([{**image_payload(product_id=str(first.id), rights_status="PENDING")}]).encode(), file_format="json", entity_type="PRODUCT_IMAGE_METADATA")
    row = result.rows[0]
    assert row.validation_status == ImportValidationStatus.VALID
    assert row.review_status.value == "PENDING"
    assert row.error_code in {"RIGHTS_PENDING", "VERIFICATION_STALE"}


def test_review_table_indexes_and_no_public_write_routes(session):
    schema = inspect(session.bind)
    assert "catalog_product_image_reviews" in schema.get_table_names()
    assert {"ix_catalog_image_review_image", "ix_catalog_image_review_decision", "ix_catalog_image_review_created"} <= {item["name"] for item in schema.get_indexes("catalog_product_image_reviews")}
    assert all(route.methods <= {"GET"} for route in catalog_v2.router.routes)
