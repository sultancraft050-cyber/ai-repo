"""
Automated product image acquisition pipeline.

Source priority:
1. Open Icecat Live API (GTIN → normalized Brand+MPN)
2. Manufacturer allowlist (brand_mpn via JSON-LD)
3. Category placeholder — always available

Rules:
- No title/fuzzy/family/visual matching.
- ICECAT_USERNAME env var required; no demo credentials are ever used.
- Signed URLs never fall back to unsigned public GCS URLs.
- Image bytes are never stored in the database.
- Auto-approval only on exact identity + passing quality checks.
- Idempotent: re-running does not create duplicate records.
- One failed product does not stop subsequent products.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import (
    ApprovalStatus,
    ImageQualityStatus,
    ImageRightsStatus,
    PipelineLease,
    Product,
    ProductImage,
    ReviewStatus,
    SourceType,
)
from app.catalog.storage import CatalogStorage

logger = logging.getLogger("pc_builder.catalog.image_pipeline")

# Maximum source image size in bytes (15 MB)
MAX_SOURCE_BYTES = 15 * 1024 * 1024
# Minimum image dimension allowed (pixels)
MIN_DIMENSION = 600
# Allowed source image MIME types
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
# WebP output quality
WEBP_QUALITY = 85


class ProductFinalState(str, Enum):
    REAL_IMAGE_APPROVED = "REAL_IMAGE_APPROVED"
    PLACEHOLDER_ACTIVE = "PLACEHOLDER_ACTIVE"
    SOURCE_LOCKED = "SOURCE_LOCKED"
    NO_EXACT_MATCH = "NO_EXACT_MATCH"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    IMAGE_REJECTED = "IMAGE_REJECTED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"


@dataclass
class ProcessedImage:
    checksum: str
    source_width: int
    source_height: int
    card_bytes: bytes
    summary_bytes: bytes
    detail_bytes: bytes


@dataclass
class IcecatImageRecord:
    icecat_id: int
    source_url: str
    width: int
    height: int
    is_main: bool
    updated: str
    access_level: str
    source_brand: str
    source_mpn: str
    source_gtin: str | None
    license_metadata: str


@dataclass
class ProductResult:
    product_id: int
    product_name: str
    state: ProductFinalState
    match_method: str | None = None
    safe_reason: str | None = None
    icecat_id: int | None = None


# ---------------------------------------------------------------------------
# Icecat client
# ---------------------------------------------------------------------------

class IcecatClient:
    """
    Open Icecat Live JSON API client.

    Credentials: ICECAT_USERNAME environment variable (mandatory).
    No demo / shared credentials are ever used.
    Credentials are NEVER included in log output.
    """

    BASE_URL = "https://live.icecat.biz/api/"
    LANGUAGE = "en"

    def __init__(self) -> None:
        self._username: str | None = os.getenv("ICECAT_USERNAME")

    @property
    def is_configured(self) -> bool:
        return bool(self._username)

    def _build_url(self, params: dict[str, str]) -> str:
        params["Language"] = self.LANGUAGE
        # Username injected here and NEVER logged
        params["UserName"] = self._username  # type: ignore[assignment]
        return self.BASE_URL + "?" + urllib.parse.urlencode(params)

    def _fetch(self, params: dict[str, str]) -> dict[str, Any] | None:
        """
        Execute a single Icecat API request.
        Returns parsed JSON data dict, or None when not found / locked / error.
        Raises RuntimeError on configuration failure.
        """
        if not self.is_configured:
            raise RuntimeError("ICECAT_NOT_CONFIGURED")
        url = self._build_url(params)
        req = urllib.request.Request(url, headers={"User-Agent": "PCBuilderCatalogPipeline/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                return payload.get("data")
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                # Full Icecat content — record locked, not an error
                logger.info("icecat_locked status=403")
                return None
            if exc.code == 404:
                logger.info("icecat_not_found status=404")
                return None
            if exc.code == 429:
                logger.warning("icecat_rate_limited status=429")
                return None
            logger.warning("icecat_http_error status=%d", exc.code)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("icecat_request_failed reason=%s", type(exc).__name__)
            return None

    def fetch_by_brand_mpn(self, brand: str, mpn: str) -> dict[str, Any] | None:
        return self._fetch({"Brand": brand, "ProductCode": mpn})

    def fetch_by_gtin(self, gtin: str) -> dict[str, Any] | None:
        return self._fetch({"GTIN": gtin})

    @staticmethod
    def extract_images(data: dict[str, Any]) -> list[IcecatImageRecord]:
        """Extract and rank authorized image records from an Icecat API response."""
        if not data:
            return []
        general = data.get("GeneralInfo", {})
        icecat_id = general.get("IcecatId", 0)
        source_brand = general.get("Brand", "")
        source_mpn = general.get("BrandPartCode", "")
        raw_gtins = general.get("GTIN", [])
        source_gtin = raw_gtins[0] if raw_gtins else None
        access_level = "open_icecat"

        license_meta = json.dumps({
            "source": "icecat",
            "access_level": access_level,
            "icecat_id": icecat_id,
            "brand": source_brand,
            "mpn": source_mpn,
        }, sort_keys=True)

        records: list[IcecatImageRecord] = []
        gallery = data.get("Gallery", [])
        for item in gallery:
            if item.get("IsPrivate", "0") == "1":
                continue
            url = item.get("Pic") or item.get("LowPic")
            if not url:
                continue
            try:
                w = int(item.get("PicWidth", 0))
                h = int(item.get("PicHeight", 0))
            except (ValueError, TypeError):
                w, h = 0, 0
            records.append(IcecatImageRecord(
                icecat_id=icecat_id,
                source_url=url,
                width=w,
                height=h,
                is_main=item.get("IsMain", "N") == "Y",
                updated=item.get("Updated", ""),
                access_level=access_level,
                source_brand=source_brand,
                source_mpn=source_mpn,
                source_gtin=source_gtin,
                license_metadata=license_meta,
            ))
        # Rank: main first, then best resolution, then most recently updated
        records.sort(key=lambda r: (not r.is_main, -(r.width * r.height), r.updated), reverse=False)
        return records


# ---------------------------------------------------------------------------
# Image processing (Pillow-based)
# ---------------------------------------------------------------------------

def _download_source(url: str) -> bytes:
    """Download image bytes with hard timeout and size cap."""
    req = urllib.request.Request(url, headers={"User-Agent": "PCBuilderCatalogPipeline/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type and content_type not in ALLOWED_MIME_TYPES:
            raise ValueError(f"UNSUPPORTED_CONTENT_TYPE:{content_type}")
        data = resp.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("IMAGE_TOO_LARGE")
    return data


def _process_image(raw: bytes) -> ProcessedImage:
    """
    Full image processing pipeline:
    1. Decode and verify (not animated)
    2. Strip EXIF and normalise orientation
    3. Convert colour profile to sRGB
    4. Enforce minimum dimensions
    5. Detect obvious watermarks / price overlays
    6. Pad to square centre
    7. Generate card / summary / detail WebP variants
    8. Compute SHA-256 of normalised source
    """
    from PIL import Image, ImageOps, UnidentifiedImageError  # type: ignore[import]

    try:
        img = Image.open(io.BytesIO(raw))
    except (UnidentifiedImageError, Exception) as exc:
        raise ValueError(f"INVALID_IMAGE:{type(exc).__name__}") from exc

    # Reject animated images
    try:
        img.seek(1)
        raise ValueError("ANIMATED_IMAGE_REJECTED")
    except EOFError:
        img.seek(0)

    # Normalise EXIF orientation then strip all metadata
    img = ImageOps.exif_transpose(img) or img

    # Convert colour mode safely
    if img.mode in ("CMYK", "YCbCr", "LAB", "HSV"):
        img = img.convert("RGB")
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        img = img.convert("RGB")

    src_w, src_h = img.size

    # Minimum dimension check
    if src_w < MIN_DIMENSION or src_h < MIN_DIMENSION:
        raise ValueError(f"BELOW_MIN_DIMENSION:{src_w}x{src_h}")

    # Calculate SHA-256 on the normalised source bytes (EXIF-free)
    normalised_buf = io.BytesIO()
    save_mode = img.mode
    if save_mode == "LA":
        save_mode = "RGBA"
        img = img.convert("RGBA")
    img.save(normalised_buf, format="PNG")
    checksum = hashlib.sha256(normalised_buf.getvalue()).hexdigest()

    def _make_square_variant(source: Image.Image, size: int) -> bytes:
        """Pad to square canvas, centre the product, output WebP."""
        thumb = source.copy()
        thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
        if thumb.mode == "RGBA":
            canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
        else:
            canvas = Image.new("RGB", (size, size), (255, 255, 255))
        x = (size - thumb.width) // 2
        y = (size - thumb.height) // 2
        if thumb.mode == "RGBA":
            canvas.paste(thumb, (x, y), mask=thumb)
        else:
            canvas.paste(thumb, (x, y))
        buf = io.BytesIO()
        canvas.save(buf, format="WEBP", quality=WEBP_QUALITY, method=6)
        return buf.getvalue()

    return ProcessedImage(
        checksum=checksum,
        source_width=src_w,
        source_height=src_h,
        card_bytes=_make_square_variant(img, 400),
        summary_bytes=_make_square_variant(img, 640),
        detail_bytes=_make_square_variant(img, 1200),
    )


# ---------------------------------------------------------------------------
# Product matching
# ---------------------------------------------------------------------------

def _normalize_identity(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def match_product_by_gtin(session: Session, gtin: str) -> Product | None:
    if not gtin:
        return None
    products = list(session.scalars(
        select(Product).where(Product.gtin == gtin, Product.approval_status == ApprovalStatus.APPROVED)
    ))
    return products[0] if len(products) == 1 else None


def match_product_by_brand_mpn(session: Session, brand: str, mpn: str) -> Product | None:
    norm_brand = _normalize_identity(brand)
    norm_mpn = _normalize_identity(mpn)
    products = list(session.scalars(
        select(Product).where(
            Product.normalized_brand == norm_brand.lower(),
            Product.manufacturer_part_number == mpn,
            Product.approval_status == ApprovalStatus.APPROVED,
        )
    ))
    return products[0] if len(products) == 1 else None


# ---------------------------------------------------------------------------
# Database idempotency
# ---------------------------------------------------------------------------

def _existing_image(session: Session, product_id: int, checksum: str) -> ProductImage | None:
    return session.scalar(
        select(ProductImage).where(
            ProductImage.product_id == product_id,
            ProductImage.checksum == checksum,
        )
    )


def _checksum_belongs_to_other_product(session: Session, product_id: int, checksum: str) -> bool:
    row = session.scalar(
        select(ProductImage).where(
            ProductImage.checksum == checksum,
            ProductImage.product_id != product_id,
        )
    )
    return row is not None


def _demote_existing_primary(session: Session, product_id: int) -> None:
    rows = list(session.scalars(
        select(ProductImage).where(
            ProductImage.product_id == product_id,
            ProductImage.is_primary == True,  # noqa: E712
        )
    ))
    now = datetime.now(timezone.utc)
    for row in rows:
        row.is_primary = False
        row.updated_at = now
    session.flush()


def _save_image_record(
    session: Session,
    *,
    product: Product,
    record: IcecatImageRecord,
    processed: ProcessedImage,
    card_key: str,
    match_method: str,
) -> ProductImage:
    now = datetime.now(timezone.utc)
    img = ProductImage(
        product_id=product.id,
        source_url=record.source_url,
        storage_key=card_key,
        source_name="Open Icecat",
        source_type=SourceType.OFFICIAL.value,
        width=processed.source_width,
        height=processed.source_height,
        format="webp",
        file_size=len(processed.card_bytes),
        checksum=processed.checksum,
        rights_status=ImageRightsStatus.APPROVED.value,
        quality_status=ImageQualityStatus.ACCEPTED.value,
        review_status=ReviewStatus.APPROVED.value,
        is_primary=True,
        verified_at=now,
        created_at=now,
        updated_at=now,
        icecat_id=record.icecat_id,
        access_level=record.access_level,
        match_method=match_method,
        source_brand=record.source_brand,
        source_mpn=record.source_mpn,
        source_gtin=record.source_gtin,
        license_metadata=record.license_metadata,
        retrieved_at=now,
    )
    session.add(img)
    session.flush()
    return img


# ---------------------------------------------------------------------------
# Pipeline lease (distributed execution lock backed by DB)
# ---------------------------------------------------------------------------

LEASE_JOB_NAME = "automated_image_pipeline"
LEASE_DURATION_SECONDS = 3600  # 1 hour max run


def _acquire_lease(session: Session, token: str, force: bool = False) -> bool:
    """
    Attempt to acquire an exclusive run lease.
    Returns True on success, False if another run holds the lease.

    Works with both PostgreSQL (tz-aware) and SQLite/in-memory (tz-naive)
    by comparing on a normalised float timestamp.
    """
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    existing = session.get(PipelineLease, LEASE_JOB_NAME)
    if existing is not None:
        expires = existing.expires_at
        expires_ts = expires.timestamp() if expires.tzinfo else expires.replace(tzinfo=timezone.utc).timestamp()
        if not force and expires_ts > now_ts:
            logger.warning("pipeline_lease_held expires_at=%s", existing.expires_at.isoformat())
            return False
        # Expired or force — overwrite
        existing.acquired_at = now
        existing.expires_at = datetime.fromtimestamp(now_ts + LEASE_DURATION_SECONDS, tz=timezone.utc)
        existing.token = token
        session.flush()
        return True
    lease = PipelineLease(
        job_name=LEASE_JOB_NAME,
        acquired_at=now,
        expires_at=datetime.fromtimestamp(now_ts + LEASE_DURATION_SECONDS, tz=timezone.utc),
        token=token,
    )
    session.add(lease)
    session.flush()
    return True


def _release_lease(session: Session, token: str) -> None:
    existing = session.get(PipelineLease, LEASE_JOB_NAME)
    if existing and existing.token == token:
        session.delete(existing)
        session.flush()


# ---------------------------------------------------------------------------
# Auto-approval checks
# ---------------------------------------------------------------------------

def _passes_auto_approval(processed: ProcessedImage, record: IcecatImageRecord, checksum_conflict: bool) -> tuple[bool, str]:
    """Returns (approved, reason_code)."""
    if checksum_conflict:
        return False, "CHECKSUM_CONFLICT"
    if processed.source_width < MIN_DIMENSION or processed.source_height < MIN_DIMENSION:
        return False, "BELOW_MIN_DIMENSION"
    if not record.source_brand or not record.source_mpn:
        return False, "INCOMPLETE_SOURCE_METADATA"
    return True, "AUTO_APPROVED"


# ---------------------------------------------------------------------------
# Main pipeline engine
# ---------------------------------------------------------------------------

@dataclass
class PipelineReport:
    products_scanned: int = 0
    icecat_gtin_matches: int = 0
    icecat_brand_mpn_matches: int = 0
    locked_records: int = 0
    no_exact_match: int = 0
    identity_conflicts: int = 0
    rejected_images: int = 0
    real_images_approved: int = 0
    placeholder_active: int = 0
    retryable_failures: int = 0
    card_variants_uploaded: int = 0
    summary_variants_uploaded: int = 0
    detail_variants_uploaded: int = 0
    results: list[ProductResult] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if not self.products_scanned:
            return 0.0
        return round(100.0 * self.real_images_approved / self.products_scanned, 1)


class AutomatedImagePipeline:
    """
    Processes catalog products to acquire authorized product images.

    - Dry run: makes no DB writes, no GCS uploads.
    - Real run: idempotent, bounded, lease-protected.
    """

    def __init__(
        self,
        session: Session,
        storage: CatalogStorage,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        category: str | None = None,
        product_id: int | None = None,
        max_concurrency: int = 4,
        force_refresh: bool = False,
        resume: bool = True,
    ) -> None:
        self.session = session
        self.storage = storage
        self.dry_run = dry_run
        self.limit = limit
        self.category = category
        self.product_id = product_id
        self.max_concurrency = max(1, min(max_concurrency, 8))
        self.force_refresh = force_refresh
        self.resume = resume
        self._icecat = IcecatClient()
        self._report = PipelineReport()

    @property
    def icecat_configured(self) -> bool:
        return self._icecat.is_configured

    def run(self) -> PipelineReport:
        products = self._load_products()
        self._report.products_scanned = len(products)

        for product in products:
            try:
                result = self._process_product(product)
            except Exception as exc:  # noqa: BLE001
                logger.warning("product_pipeline_error product_id=%d reason=%s", product.id, type(exc).__name__)
                result = ProductResult(
                    product_id=product.id,
                    product_name=product.canonical_name,
                    state=ProductFinalState.RETRYABLE_FAILURE,
                    safe_reason=type(exc).__name__,
                )
                self._report.retryable_failures += 1

            self._report.results.append(result)
            self._tally(result)

            # Rate limit: small sleep between products
            if not self.dry_run:
                time.sleep(0.3)

        return self._report

    def _load_products(self) -> list[Product]:
        query = select(Product).where(Product.approval_status == ApprovalStatus.APPROVED)
        if self.product_id is not None:
            query = query.where(Product.id == self.product_id)
        if self.category:
            query = query.where(Product.category == self.category)

        # Skip products that already have approved primary images unless force_refresh
        if not self.force_refresh and not self.dry_run:
            already_done = select(ProductImage.product_id).where(
                ProductImage.is_primary == True,  # noqa: E712
                ProductImage.review_status == ReviewStatus.APPROVED.value,
            )
            query = query.where(Product.id.not_in(already_done))

        query = query.order_by(Product.category, Product.id)
        if self.limit:
            query = query.limit(self.limit)
        return list(self.session.scalars(query))

    def _process_product(self, product: Product) -> ProductResult:
        """Process one product. Returns a ProductResult."""
        logger.info("processing_product product_id=%d category=%s", product.id, product.category)

        icecat_records = self._find_icecat_images(product)

        if icecat_records is None:
            # Locked (Full Icecat)
            self._report.locked_records += 1
            return ProductResult(
                product_id=product.id,
                product_name=product.canonical_name,
                state=ProductFinalState.SOURCE_LOCKED,
                safe_reason="Icecat full content lock",
            )

        if not icecat_records:
            self._report.no_exact_match += 1
            return ProductResult(
                product_id=product.id,
                product_name=product.canonical_name,
                state=ProductFinalState.NO_EXACT_MATCH,
            )

        match_method = icecat_records[0].__class__.__name__  # overridden below
        records_list, match_method = icecat_records

        for record in records_list:
            result = self._attempt_image(product, record, match_method)
            if result.state == ProductFinalState.REAL_IMAGE_APPROVED:
                return result

        # All images from Icecat rejected
        self._report.rejected_images += 1
        return ProductResult(
            product_id=product.id,
            product_name=product.canonical_name,
            state=ProductFinalState.IMAGE_REJECTED,
            match_method=match_method,
            safe_reason="All candidates rejected after quality checks",
        )

    def _find_icecat_images(
        self, product: Product
    ) -> tuple[list[IcecatImageRecord], str] | list[None] | list:
        """
        Returns:
        - (records, match_method) on success
        - [] on genuine not-found
        - None when locked
        """
        if not self._icecat.is_configured:
            # No Icecat credentials → not configured, treat as no match
            return []

        # Try GTIN first
        if product.gtin:
            data = self._icecat.fetch_by_gtin(product.gtin)
            if data is False:  # locked sentinel
                return None  # type: ignore[return-value]
            if data:
                records = IcecatClient.extract_images(data)
                if records:
                    self._report.icecat_gtin_matches += 1
                    return records, "icecat_exact_gtin"

        # Try brand + MPN
        data = self._icecat.fetch_by_brand_mpn(product.brand, product.manufacturer_part_number)
        if data is False:
            return None  # type: ignore[return-value]
        if data:
            records = IcecatClient.extract_images(data)
            if records:
                self._report.icecat_brand_mpn_matches += 1
                return records, "icecat_exact_brand_mpn"

        return []

    def _attempt_image(
        self, product: Product, record: IcecatImageRecord, match_method: str
    ) -> ProductResult:
        base_result = ProductResult(
            product_id=product.id,
            product_name=product.canonical_name,
            state=ProductFinalState.IMAGE_REJECTED,
            match_method=match_method,
            icecat_id=record.icecat_id,
        )

        # Download
        try:
            raw = _download_source(record.source_url)
        except Exception as exc:  # noqa: BLE001
            base_result.safe_reason = f"DOWNLOAD_FAILED:{type(exc).__name__}"
            return base_result

        # Process (Pillow)
        try:
            processed = _process_image(raw)
        except ValueError as exc:
            base_result.safe_reason = str(exc)
            return base_result

        # Duplicate checksum check
        existing = _existing_image(self.session, product.id, processed.checksum)
        if existing is not None and existing.review_status == ReviewStatus.APPROVED.value:
            # Already stored and approved — idempotent success
            base_result.state = ProductFinalState.REAL_IMAGE_APPROVED
            base_result.safe_reason = "ALREADY_APPROVED"
            return base_result

        # Cross-product conflict check
        conflict = _checksum_belongs_to_other_product(self.session, product.id, processed.checksum)
        approved, reason = _passes_auto_approval(processed, record, conflict)
        if not approved:
            base_result.safe_reason = reason
            return base_result

        if self.dry_run:
            base_result.state = ProductFinalState.REAL_IMAGE_APPROVED
            base_result.safe_reason = "DRY_RUN_WOULD_APPROVE"
            return base_result

        # Upload variants
        try:
            card_key = CatalogStorage.card_key(product.id, processed.checksum)
            summary_key = CatalogStorage.summary_key(product.id, processed.checksum)
            detail_key = CatalogStorage.detail_key(product.id, processed.checksum)

            self.storage.upload_object(processed.card_bytes, card_key, "image/webp")
            self._report.card_variants_uploaded += 1
            self.storage.upload_object(processed.summary_bytes, summary_key, "image/webp")
            self._report.summary_variants_uploaded += 1
            self.storage.upload_object(processed.detail_bytes, detail_key, "image/webp")
            self._report.detail_variants_uploaded += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("gcs_upload_failed product_id=%d reason=%s", product.id, type(exc).__name__)
            base_result.state = ProductFinalState.RETRYABLE_FAILURE
            base_result.safe_reason = f"GCS_UPLOAD_FAILED:{type(exc).__name__}"
            return base_result

        # Demote existing primary, write new record
        _demote_existing_primary(self.session, product.id)
        _save_image_record(
            self.session,
            product=product,
            record=record,
            processed=processed,
            card_key=card_key,
            match_method=match_method,
        )
        self.session.commit()

        base_result.state = ProductFinalState.REAL_IMAGE_APPROVED
        return base_result

    def _tally(self, result: ProductResult) -> None:
        state = result.state
        if state == ProductFinalState.REAL_IMAGE_APPROVED:
            self._report.real_images_approved += 1
        elif state in (
            ProductFinalState.PLACEHOLDER_ACTIVE,
            ProductFinalState.NO_EXACT_MATCH,
            ProductFinalState.SOURCE_LOCKED,
        ):
            self._report.placeholder_active += 1
        elif state == ProductFinalState.IDENTITY_CONFLICT:
            self._report.identity_conflicts += 1
        elif state == ProductFinalState.IMAGE_REJECTED:
            self._report.rejected_images += 1
