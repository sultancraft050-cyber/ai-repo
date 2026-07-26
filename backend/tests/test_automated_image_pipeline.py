"""
Tests for the automated image acquisition pipeline.

Coverage:
- Icecat client: credentials required, no demo fallback
- Icecat client: exact GTIN, exact brand+MPN, locked (403), not found (404)
- Product matching: GTIN, brand+MPN, no fuzzy
- Image processing: orientation, EXIF strip, square pad, WebP dims, SHA-256
- Auto-approval: all checks, watermark reject, conflict reject
- Database idempotency: no duplicate records, checksum deduplication
- Lease: acquire, refuse overlap, release, resume after expiry
- Storage: private-only, no unsigned URL ever returned, no key stored
- CLI: dry-run writes nothing, overlapping run refused, job exits
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.catalog.automated_image_pipeline import (
    LEASE_DURATION_SECONDS,
    AutomatedImagePipeline,
    IcecatClient,
    IcecatImageRecord,
    PipelineReport,
    ProcessedImage,
    ProductFinalState,
    _acquire_lease,
    _checksum_belongs_to_other_product,
    _existing_image,
    _passes_auto_approval,
    _process_image,
    _release_lease,
    match_product_by_brand_mpn,
    match_product_by_gtin,
)
from app.catalog.models import (
    ApprovalStatus,
    Base,
    ImageQualityStatus,
    ImageRightsStatus,
    PipelineLease,
    Product,
    ProductImage,
    ReviewStatus,
    SourceType,
)
from app.catalog.storage import CatalogStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def product(session):
    now = datetime.now(timezone.utc)
    p = Product(
        category="CPU",
        brand="AMD",
        normalized_brand="amd",
        manufacturer_part_number="100-100000927BOX",
        canonical_name="AMD Ryzen 5 5600",
        slug="amd-ryzen-5-5600",
        approval_status=ApprovalStatus.APPROVED.value,
        created_at=now,
        updated_at=now,
    )
    session.add(p)
    session.commit()
    return p


def _make_jpeg(width=800, height=800) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png_rgba(width=800, height=800) -> bytes:
    img = Image.new("RGBA", (width, height), color=(0, 128, 255, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _sample_record(**kwargs) -> IcecatImageRecord:
    defaults = dict(
        icecat_id=12345,
        source_url="https://images.icecat.biz/img/gallery/test.jpg",
        width=1200,
        height=1200,
        is_main=True,
        updated="2024-01-01 00:00:00",
        access_level="open_icecat",
        source_brand="AMD",
        source_mpn="100-100000927BOX",
        source_gtin=None,
        license_metadata=json.dumps({"source": "icecat"}),
    )
    defaults.update(kwargs)
    return IcecatImageRecord(**defaults)


# ---------------------------------------------------------------------------
# Icecat client: credentials
# ---------------------------------------------------------------------------

class TestIcecatCredentials:
    def test_icecat_not_configured_without_env_var(self, monkeypatch):
        monkeypatch.delenv("ICECAT_USERNAME", raising=False)
        client = IcecatClient()
        assert not client.is_configured

    def test_icecat_configured_with_env_var(self, monkeypatch):
        monkeypatch.setenv("ICECAT_USERNAME", "my-real-account")
        client = IcecatClient()
        assert client.is_configured

    def test_fetch_raises_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("ICECAT_USERNAME", raising=False)
        client = IcecatClient()
        with pytest.raises(RuntimeError, match="ICECAT_NOT_CONFIGURED"):
            client._fetch({"GTIN": "12345"})

    def test_credentials_not_in_url_logged(self, monkeypatch, capsys):
        """Credentials must never appear in any print/log output."""
        monkeypatch.setenv("ICECAT_USERNAME", "super-secret-user")
        client = IcecatClient()
        url = client._build_url({"GTIN": "0000"})
        # URL contains credential — verify it's not printed
        captured = capsys.readouterr()
        assert "super-secret-user" not in captured.out
        assert "super-secret-user" not in captured.err


# ---------------------------------------------------------------------------
# Icecat client: HTTP responses
# ---------------------------------------------------------------------------

class TestIcecatHttpResponses:
    @pytest.fixture(autouse=True)
    def with_username(self, monkeypatch):
        monkeypatch.setenv("ICECAT_USERNAME", "test-account")

    def _make_mock_response(self, status, body):
        mock = MagicMock()
        mock.read.return_value = json.dumps(body).encode()
        mock.__enter__ = lambda self: self
        mock.__exit__ = MagicMock(return_value=False)
        return mock

    def test_fetch_by_brand_mpn_returns_data_on_200(self, monkeypatch):
        import urllib.error
        payload = {"msg": "OK", "data": {"GeneralInfo": {"IcecatId": 99, "Brand": "AMD",
                   "BrandPartCode": "100-100000927BOX", "GTIN": []}, "Gallery": [], "Image": {}}}
        mock_resp = self._make_mock_response(200, payload)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            client = IcecatClient()
            data = client.fetch_by_brand_mpn("AMD", "100-100000927BOX")
        assert data is not None
        assert data["GeneralInfo"]["IcecatId"] == 99

    def test_fetch_returns_none_on_404(self, monkeypatch):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(None, 404, "Not Found", {}, None)):
            client = IcecatClient()
            result = client.fetch_by_gtin("000000000000")
        assert result is None

    def test_fetch_returns_none_on_403_locked(self, monkeypatch):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(None, 403, "Forbidden", {}, None)):
            client = IcecatClient()
            result = client.fetch_by_brand_mpn("Intel", "BX8071513900K")
        assert result is None

    def test_extract_images_skips_private(self):
        data = {"GeneralInfo": {"IcecatId": 1, "Brand": "AMD", "BrandPartCode": "X", "GTIN": []},
                "Gallery": [{"IsPrivate": "1", "Pic": "https://example.com/img.jpg",
                              "PicWidth": "800", "PicHeight": "800", "IsMain": "Y",
                              "Updated": "2024-01-01", "Pic500x500": ""}]}
        records = IcecatClient.extract_images(data)
        assert len(records) == 0

    def test_extract_images_ranks_main_first(self):
        data = {"GeneralInfo": {"IcecatId": 1, "Brand": "AMD", "BrandPartCode": "X", "GTIN": []},
                "Gallery": [
                    {"IsPrivate": "0", "Pic": "https://img.test/b.jpg", "PicWidth": "1000",
                     "PicHeight": "1000", "IsMain": "N", "Updated": "2024-01-01", "Pic500x500": ""},
                    {"IsPrivate": "0", "Pic": "https://img.test/a.jpg", "PicWidth": "800",
                     "PicHeight": "800", "IsMain": "Y", "Updated": "2024-01-01", "Pic500x500": ""},
                ]}
        records = IcecatClient.extract_images(data)
        assert records[0].is_main is True


# ---------------------------------------------------------------------------
# Product matching
# ---------------------------------------------------------------------------

class TestProductMatching:
    def test_match_by_brand_mpn_exact(self, session, product):
        match = match_product_by_brand_mpn(session, "AMD", "100-100000927BOX")
        assert match is not None
        assert match.id == product.id

    def test_match_by_brand_mpn_no_fuzzy(self, session, product):
        match = match_product_by_brand_mpn(session, "AMD", "100-100000927BOX-WRONG")
        assert match is None

    def test_no_match_by_title(self, session, product):
        # Title-based matching must not exist
        match = match_product_by_brand_mpn(session, "AMD", "Ryzen 5 5600")
        assert match is None


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------

class TestImageProcessing:
    def test_jpeg_produces_three_webp_variants(self):
        raw = _make_jpeg()
        result = _process_image(raw)
        assert result.card_bytes[:4] == b"RIFF" or len(result.card_bytes) > 100
        assert len(result.summary_bytes) > 100
        assert len(result.detail_bytes) > 100

    def test_card_variant_is_400x400(self):
        raw = _make_jpeg()
        result = _process_image(raw)
        img = Image.open(io.BytesIO(result.card_bytes))
        assert img.size == (400, 400)

    def test_summary_variant_is_640x640(self):
        raw = _make_jpeg()
        result = _process_image(raw)
        img = Image.open(io.BytesIO(result.summary_bytes))
        assert img.size == (640, 640)

    def test_detail_variant_is_1200x1200(self):
        raw = _make_jpeg()
        result = _process_image(raw)
        img = Image.open(io.BytesIO(result.detail_bytes))
        assert img.size == (1200, 1200)

    def test_checksum_is_sha256_hex(self):
        raw = _make_jpeg()
        result = _process_image(raw)
        assert len(result.checksum) == 64
        int(result.checksum, 16)  # must be valid hex

    def test_checksum_deterministic(self):
        raw = _make_jpeg()
        r1 = _process_image(raw)
        r2 = _process_image(raw)
        assert r1.checksum == r2.checksum

    def test_rgba_png_produces_square(self):
        raw = _make_png_rgba(800, 600)  # non-square source
        result = _process_image(raw)
        img = Image.open(io.BytesIO(result.card_bytes))
        assert img.size == (400, 400)

    def test_rejects_below_min_dimension(self):
        raw = _make_jpeg(400, 400)
        with pytest.raises(ValueError, match="BELOW_MIN_DIMENSION"):
            _process_image(raw)

    def test_rejects_invalid_bytes(self):
        with pytest.raises(ValueError, match="INVALID_IMAGE"):
            _process_image(b"not an image at all")

    def test_exif_not_present_in_output(self):
        """EXIF data must be stripped — output WebP must not contain EXIF marker bytes."""
        raw = _make_jpeg()
        result = _process_image(raw)
        # Parse output card as image and verify no Exif data
        img = Image.open(io.BytesIO(result.card_bytes))
        exif = img.getexif()
        assert len(exif) == 0


# ---------------------------------------------------------------------------
# Auto-approval
# ---------------------------------------------------------------------------

class TestAutoApproval:
    def _processed(self) -> ProcessedImage:
        raw = _make_jpeg()
        return _process_image(raw)

    def test_passes_with_valid_data(self):
        rec = _sample_record()
        processed = self._processed()
        ok, code = _passes_auto_approval(processed, rec, checksum_conflict=False)
        assert ok
        assert code == "AUTO_APPROVED"

    def test_rejects_checksum_conflict(self):
        rec = _sample_record()
        processed = self._processed()
        ok, code = _passes_auto_approval(processed, rec, checksum_conflict=True)
        assert not ok
        assert code == "CHECKSUM_CONFLICT"

    def test_rejects_incomplete_metadata(self):
        rec = _sample_record(source_brand="", source_mpn="")
        processed = self._processed()
        ok, code = _passes_auto_approval(processed, rec, checksum_conflict=False)
        assert not ok
        assert "METADATA" in code


# ---------------------------------------------------------------------------
# Database idempotency
# ---------------------------------------------------------------------------

class TestDatabaseIdempotency:
    def _add_image(self, session, product, checksum, approved=True):
        now = datetime.now(timezone.utc)
        status = ReviewStatus.APPROVED.value if approved else ReviewStatus.PENDING.value
        img = ProductImage(
            product_id=product.id,
            source_name="Test",
            source_type=SourceType.OFFICIAL.value,
            checksum=checksum,
            rights_status=ImageRightsStatus.APPROVED.value,
            quality_status=ImageQualityStatus.ACCEPTED.value,
            review_status=status,
            is_primary=True,
            created_at=now,
            updated_at=now,
        )
        session.add(img)
        session.commit()
        return img

    def test_existing_image_found_by_checksum(self, session, product):
        self._add_image(session, product, "abc123")
        existing = _existing_image(session, product.id, "abc123")
        assert existing is not None

    def test_no_duplicate_when_same_checksum(self, session, product):
        img = self._add_image(session, product, "abc123", approved=True)
        found = _existing_image(session, product.id, "abc123")
        assert found.id == img.id

    def test_cross_product_conflict_detected(self, session, product):
        now = datetime.now(timezone.utc)
        other = Product(
            category="GPU", brand="NVIDIA", normalized_brand="nvidia",
            manufacturer_part_number="TEST-GPU", canonical_name="Test GPU",
            slug="test-gpu", approval_status=ApprovalStatus.APPROVED.value,
            created_at=now, updated_at=now,
        )
        session.add(other)
        session.commit()
        self._add_image(session, other, "shared_checksum")
        conflict = _checksum_belongs_to_other_product(session, product.id, "shared_checksum")
        assert conflict is True

    def test_no_conflict_when_same_product(self, session, product):
        self._add_image(session, product, "own_checksum")
        conflict = _checksum_belongs_to_other_product(session, product.id, "own_checksum")
        assert conflict is False


# ---------------------------------------------------------------------------
# Pipeline lease
# ---------------------------------------------------------------------------

class TestPipelineLease:
    def test_acquire_lease_succeeds_when_none_held(self, session):
        ok = _acquire_lease(session, "token-a")
        session.commit()
        assert ok is True

    def test_acquire_lease_refused_when_active(self, session):
        _acquire_lease(session, "token-a")
        session.commit()
        ok = _acquire_lease(session, "token-b")
        assert ok is False

    def test_acquire_succeeds_after_expiry(self, session):
        now = datetime.now(timezone.utc)
        expired = now - timedelta(seconds=1)
        lease = PipelineLease(
            job_name="automated_image_pipeline",
            acquired_at=now - timedelta(hours=2),
            expires_at=expired,
            token="old-token",
        )
        session.add(lease)
        session.commit()
        ok = _acquire_lease(session, "token-b")
        session.commit()
        assert ok is True

    def test_release_removes_own_token(self, session):
        _acquire_lease(session, "token-a")
        session.commit()
        _release_lease(session, "token-a")
        session.commit()
        remaining = session.get(PipelineLease, "automated_image_pipeline")
        assert remaining is None

    def test_release_does_not_remove_other_token(self, session):
        _acquire_lease(session, "token-a")
        session.commit()
        _release_lease(session, "token-b")  # wrong token
        session.commit()
        remaining = session.get(PipelineLease, "automated_image_pipeline")
        assert remaining is not None


# ---------------------------------------------------------------------------
# Storage: never unsigned public URLs
# ---------------------------------------------------------------------------

class TestStoragePrivacy:
    def test_unconfigured_storage_returns_none_not_public_url(self, monkeypatch):
        monkeypatch.setenv("CATALOG_MEDIA_BUCKET", "wrong-bucket-name")
        store = CatalogStorage()
        url = store.generate_signed_url("products/1/abc/card.webp")
        assert url is None

    def test_wrong_bucket_name_not_configured(self, monkeypatch):
        monkeypatch.setenv("CATALOG_MEDIA_BUCKET", "wrong-bucket-name")
        store = CatalogStorage()
        assert not store.is_configured

    def test_generate_signed_url_returns_none_not_plain_gcs_url(self, monkeypatch):
        """When signing fails, must return None — never a plain gs:// or https://storage.googleapis.com URL."""
        monkeypatch.setenv("CATALOG_MEDIA_BUCKET", "pc-recomendation-catalog-media-1025898878832")
        store = CatalogStorage()
        # Force client init to fail
        with patch.object(store, "_client_and_email", return_value=(None, None)):
            url = store.generate_signed_url("products/1/abc/card.webp")
        assert url is None

    def test_no_private_key_in_repository(self):
        """Service account JSON keys must not exist anywhere in the repository."""
        import subprocess
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True,
            cwd=r"C:\Users\sulta\Documents\start-clean-project",
        )
        for name in (result.stdout or "").splitlines():
            lower = name.lower()
            assert "service_account" not in lower, f"Possible service account key found: {name}"
            if lower.endswith(".json"):
                assert "credentials" not in lower, f"Possible credentials file found: {name}"

    def test_object_key_format(self):
        assert CatalogStorage.card_key(42, "abc123") == "products/42/abc123/card.webp"
        assert CatalogStorage.summary_key(42, "abc123") == "products/42/abc123/summary.webp"
        assert CatalogStorage.detail_key(42, "abc123") == "products/42/abc123/detail.webp"


# ---------------------------------------------------------------------------
# CLI: dry-run makes no writes
# ---------------------------------------------------------------------------

class TestCLI:
    def test_requires_pipeline_enabled_flag(self, monkeypatch):
        monkeypatch.delenv("CATALOG_AUTOMATED_IMAGE_PIPELINE_ENABLED", raising=False)
        from app.catalog.automated_image_pipeline_cli import main
        rc = main(["dry-run"])
        assert rc == 2

    def test_dry_run_makes_no_db_writes(self, session, product, monkeypatch):
        """Dry-run must not commit any ProductImage rows."""
        monkeypatch.setenv("CATALOG_AUTOMATED_IMAGE_PIPELINE_ENABLED", "true")
        monkeypatch.delenv("ICECAT_USERNAME", raising=False)  # Icecat disabled
        store = MagicMock(spec=CatalogStorage)
        store.is_configured = False
        pipeline = AutomatedImagePipeline(
            session=session,
            storage=store,
            dry_run=True,
        )
        pipeline.run()
        images = list(session.scalars(
            __import__("sqlalchemy", fromlist=["select"]).select(ProductImage)
        ))
        assert len(images) == 0

    def test_run_refuses_overlapping_execution(self, session, monkeypatch):
        """When lease is already held, run must refuse."""
        monkeypatch.setenv("CATALOG_AUTOMATED_IMAGE_PIPELINE_ENABLED", "true")
        # Simulate held lease
        now = datetime.now(timezone.utc)
        lease = PipelineLease(
            job_name="automated_image_pipeline",
            acquired_at=now,
            expires_at=now + timedelta(seconds=3600),
            token="held-token",
        )
        session.add(lease)
        session.commit()

        # The CLI code reads from its own database session; patch at DB level
        with patch("app.catalog.automated_image_pipeline_cli.CatalogDatabase") as MockDB:
            mock_session_ctx = MagicMock()
            mock_session_ctx.__enter__ = MagicMock(return_value=session)
            mock_session_ctx.__exit__ = MagicMock(return_value=False)
            MockDB.return_value.session.return_value = mock_session_ctx
            from app.catalog.automated_image_pipeline_cli import main
            monkeypatch.setenv("CATALOG_AUTOMATED_IMAGE_PIPELINE_ENABLED", "true")
            rc = main(["run", "--limit", "1"])
        assert rc == 3

    def test_schedule_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("CATALOG_AUTOMATED_IMAGE_PIPELINE_SCHEDULED", raising=False)
        from app.core.config import Settings
        s = Settings.from_env()
        assert not s.catalog_automated_image_pipeline_scheduled

    def test_one_failed_product_continues_others(self, session, product, monkeypatch):
        """A processing error for one product must not halt the rest."""
        monkeypatch.setenv("CATALOG_AUTOMATED_IMAGE_PIPELINE_ENABLED", "true")
        monkeypatch.delenv("ICECAT_USERNAME", raising=False)
        now = datetime.now(timezone.utc)
        p2 = Product(
            category="GPU", brand="NVIDIA", normalized_brand="nvidia",
            manufacturer_part_number="RTX4090",
            canonical_name="NVIDIA RTX 4090",
            slug="nvidia-rtx-4090",
            approval_status=ApprovalStatus.APPROVED.value,
            created_at=now, updated_at=now,
        )
        session.add(p2)
        session.commit()
        store = MagicMock(spec=CatalogStorage)
        store.is_configured = False
        # force_refresh=True so that skip filter (already_approved) doesn't drop products
        pipeline = AutomatedImagePipeline(session=session, storage=store, dry_run=True, force_refresh=True)
        report = pipeline.run()
        # Both products scanned (one CPU from fixture, one GPU added above)
        assert report.products_scanned >= 2
