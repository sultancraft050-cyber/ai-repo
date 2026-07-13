from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalog.models import (
    ImageQualityStatus,
    ImageReviewDecision,
    ImageRightsStatus,
    Product,
    ProductImage,
    ProductImageReview,
    ReviewStatus,
)

TRUE_VALUES = {"1", "true", "yes"}
SUPPORTED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP", "AVIF"}
SOURCE_TYPES = {"MANUFACTURER", "AUTHORIZED_DISTRIBUTOR", "AUTHORIZED_RETAILER", "PARTNER_FEED", "MANUAL_UPLOAD", "SYNTHETIC_FIXTURE", "UNKNOWN"}
REASON_TEXT = {
    "URL_INVALID": "The image URL is invalid or unsupported.",
    "HOST_NOT_APPROVED": "The image host is not approved by local policy.",
    "RIGHTS_PENDING": "Image rights require review.",
    "RIGHTS_REJECTED": "Image rights are rejected.",
    "RIGHTS_EXPIRED": "Image rights have expired.",
    "DIMENSIONS_MISSING": "Image dimensions were not supplied.",
    "DIMENSIONS_TOO_SMALL": "Image dimensions are below the configured minimum.",
    "DIMENSIONS_TOO_LARGE": "Image dimensions exceed the configured maximum.",
    "ASPECT_RATIO_REVIEW": "Aspect ratio requires human review for this category.",
    "FORMAT_UNSUPPORTED": "Image format is unsupported or missing.",
    "FILE_SIZE_EXCEEDED": "Image file size exceeds the configured maximum.",
    "FILE_SIZE_MISSING": "Image file size was not supplied.",
    "CHECKSUM_MISSING": "Image checksum is required for approval.",
    "DUPLICATE_SAME_PRODUCT": "Checksum already exists for this product.",
    "DUPLICATE_CROSS_PRODUCT": "Checksum is shared by different products.",
    "DUPLICATE_URL": "Source URL is already used by another image.",
    "METADATA_CONFLICT": "Metadata conflicts for the same checksum.",
    "CATEGORY_UNKNOWN": "Product category is unknown.",
    "PRIMARY_CONFLICT": "Another approved primary image is active.",
    "VERIFICATION_STALE": "Metadata verification is stale.",
    "SOURCE_UNKNOWN": "Source provenance is unknown.",
    "MAX_IMAGES_PER_PRODUCT": "Product exceeds the configured image count limit.",
    "ACCEPTABLE_METADATA": "Metadata satisfies the configured review checks.",
}


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in TRUE_VALUES


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def _bounded_float(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be numeric") from error
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


@dataclass(frozen=True)
class ImageReviewConfig:
    minimum_width: int = field(default_factory=lambda: _bounded_int("CATALOG_IMAGE_MIN_WIDTH", 320, 1, 20000))
    minimum_height: int = field(default_factory=lambda: _bounded_int("CATALOG_IMAGE_MIN_HEIGHT", 240, 1, 20000))
    maximum_width: int = field(default_factory=lambda: _bounded_int("CATALOG_IMAGE_MAX_WIDTH", 4096, 1, 30000))
    maximum_height: int = field(default_factory=lambda: _bounded_int("CATALOG_IMAGE_MAX_HEIGHT", 4096, 1, 30000))
    maximum_file_size: int = field(default_factory=lambda: _bounded_int("CATALOG_IMAGE_MAX_FILE_SIZE", 5_000_000, 1, 100_000_000))
    minimum_aspect_ratio: float = field(default_factory=lambda: _bounded_float("CATALOG_IMAGE_MIN_ASPECT_RATIO", 0.5, 0.05, 20.0))
    maximum_aspect_ratio: float = field(default_factory=lambda: _bounded_float("CATALOG_IMAGE_MAX_ASPECT_RATIO", 4.0, 0.05, 20.0))
    freshness_days: int = field(default_factory=lambda: _bounded_int("CATALOG_IMAGE_VERIFICATION_DAYS", 180, 1, 3650))
    maximum_images_per_product: int = field(default_factory=lambda: _bounded_int("CATALOG_IMAGE_MAX_PER_PRODUCT", 12, 1, 100))
    allowed_hosts: frozenset[str] = field(default_factory=lambda: frozenset(host.strip().lower() for host in os.getenv("CATALOG_IMAGE_ALLOWED_HOSTS", "").split(",") if host.strip()))

    def __post_init__(self) -> None:
        if self.minimum_width > self.maximum_width or self.minimum_height > self.maximum_height:
            raise ValueError("image dimension minimums cannot exceed maximums")
        if self.minimum_aspect_ratio > self.maximum_aspect_ratio:
            raise ValueError("image aspect-ratio minimum cannot exceed maximum")


@dataclass(frozen=True)
class ImageEvaluation:
    image_id: int | None
    product_id: int | None
    classification: str
    results: dict[str, str]
    reason_codes: tuple[str, ...]
    recommended_action: str
    primary_eligible: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "product_id": self.product_id,
            "overall_classification": self.classification,
            **self.results,
            "reason_codes": list(self.reason_codes),
            "recommended_review_action": self.recommended_action,
            "primary_eligibility": self.primary_eligible,
        }


def _safe_text(value: str, limit: int) -> str:
    value = str(value or "").strip()
    if not value or len(value) > limit or any(ord(char) < 32 for char in value):
        raise ValueError("review text is empty, too long, or contains control characters")
    return value


def _url_result(url: str | None, storage_key: str | None, config: ImageReviewConfig) -> tuple[str, str]:
    candidate = (url or "").strip()
    if storage_key and storage_key.startswith("/") and not candidate:
        return "PASS", "LOCAL_REFERENCE"
    if not candidate or len(candidate) > 2048 or any(ord(char) < 32 for char in candidate):
        return "FAIL", "URL_INVALID"
    if candidate.startswith("/"):
        return "PASS", "LOCAL_REFERENCE"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        return "FAIL", "URL_INVALID"
    if parsed.scheme == "http" and not _enabled("CATALOG_IMAGE_ALLOW_HTTP"):
        return "FAIL", "URL_INVALID"
    host = parsed.hostname.lower()
    if host not in config.allowed_hosts:
        return "FAIL", "HOST_NOT_APPROVED"
    return "PASS", "APPROVED_HOST"


def _evaluate_values(payload: dict[str, Any], category: str | None, *, image_id: int | None, product_id: int | None, session: Session | None, config: ImageReviewConfig) -> ImageEvaluation:
    reasons: list[str] = []
    results: dict[str, str] = {}
    url_status, url_reason = _url_result(payload.get("source_url"), payload.get("storage_key"), config)
    results["url_result"], results["host_policy_result"] = url_status, url_reason if url_reason != "LOCAL_REFERENCE" else "LOCAL_REFERENCE"
    if url_status == "FAIL":
        reasons.append(url_reason)
    rights = str(payload.get("rights_status", "unknown")).upper()
    results["rights_result"] = "PASS" if rights == "APPROVED" else "REVIEW"
    if rights != "APPROVED":
        reasons.append({"PENDING": "RIGHTS_PENDING", "REVIEW": "RIGHTS_PENDING", "REJECTED": "RIGHTS_REJECTED", "EXPIRED": "RIGHTS_EXPIRED"}.get(rights, "RIGHTS_PENDING"))
    width, height = payload.get("width"), payload.get("height")
    width_value = height_value = 0
    if not width or not height:
        results["dimension_result"] = "REVIEW"
        reasons.append("DIMENSIONS_MISSING")
    else:
        try:
            width_value, height_value = int(width), int(height)
        except (TypeError, ValueError):
            results["dimension_result"] = "REVIEW"
            reasons.append("DIMENSIONS_MISSING")
        if width_value and height_value and (width_value < config.minimum_width or height_value < config.minimum_height):
            results["dimension_result"] = "FAIL"
            reasons.append("DIMENSIONS_TOO_SMALL")
        elif width_value and height_value and (width_value > config.maximum_width or height_value > config.maximum_height):
            results["dimension_result"] = "FAIL"
            reasons.append("DIMENSIONS_TOO_LARGE")
        elif width_value and height_value:
            results["dimension_result"] = "PASS"
    ratio = (float(width_value) / float(height_value)) if width_value and height_value else None
    category_key = str(category or "UNKNOWN").upper()
    if ratio is None or category_key == "UNKNOWN":
        results["aspect_ratio_result"] = "REVIEW"
        if "DIMENSIONS_MISSING" not in reasons:
            reasons.append("CATEGORY_UNKNOWN")
    elif category_key == "CASE":
        results["aspect_ratio_result"] = "PASS"
    elif category_key == "GPU" and ratio <= 8.0:
        results["aspect_ratio_result"] = "PASS"
    elif config.minimum_aspect_ratio <= ratio <= config.maximum_aspect_ratio:
        results["aspect_ratio_result"] = "PASS"
    else:
        results["aspect_ratio_result"] = "REVIEW"
        reasons.append("ASPECT_RATIO_REVIEW")
    image_format = str(payload.get("format", "")).upper()
    results["format_result"] = "PASS" if image_format in SUPPORTED_FORMATS else "REVIEW"
    if image_format not in SUPPORTED_FORMATS:
        reasons.append("FORMAT_UNSUPPORTED")
    file_size = payload.get("file_size")
    try:
        file_size_value = int(file_size) if file_size is not None else 0
    except (TypeError, ValueError):
        file_size_value = config.maximum_file_size + 1
    results["file_size_result"] = "PASS" if file_size_value and file_size_value <= config.maximum_file_size else "FAIL" if file_size else "REVIEW"
    if not file_size:
        reasons.append("FILE_SIZE_MISSING")
    elif file_size_value > config.maximum_file_size:
        reasons.append("FILE_SIZE_EXCEEDED")
    checksum = str(payload.get("checksum") or "").strip()
    results["checksum_result"] = "PASS" if checksum else "REVIEW"
    if not checksum:
        reasons.append("CHECKSUM_MISSING")
    if session and checksum:
        matches = session.scalars(select(ProductImage).where(ProductImage.checksum == checksum, ProductImage.id != image_id)).all()
        if matches:
            same_product = product_id is not None and all(item.product_id == product_id for item in matches)
            reasons.append("DUPLICATE_SAME_PRODUCT" if same_product else "DUPLICATE_CROSS_PRODUCT")
            results["duplicate_result"] = "SAME_PRODUCT" if same_product else "CROSS_PRODUCT"
            if any((item.width, item.height, str(item.format or "").upper()) != (width_value, height_value, str(payload.get("format") or "").upper()) for item in matches):
                reasons.append("METADATA_CONFLICT")
        else:
            results["duplicate_result"] = "NONE"
    else:
        results["duplicate_result"] = "UNKNOWN"
    if session and payload.get("source_url"):
        url_matches = session.scalars(select(ProductImage).where(ProductImage.source_url == payload["source_url"], ProductImage.id != image_id)).first()
        if url_matches:
            reasons.append("DUPLICATE_URL")
    source_type = str(payload.get("source_type", "UNKNOWN")).upper()
    if source_type not in SOURCE_TYPES or source_type == "UNKNOWN":
        reasons.append("SOURCE_UNKNOWN")
    verified = payload.get("verified_at")
    if not verified:
        reasons.append("VERIFICATION_STALE")
    else:
        try:
            timestamp = datetime.fromisoformat(str(verified).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timestamp < datetime.now(timezone.utc) - timedelta(days=config.freshness_days):
                reasons.append("VERIFICATION_STALE")
        except ValueError:
            reasons.append("VERIFICATION_STALE")
    duplicate_reasons = {"DUPLICATE_CROSS_PRODUCT", "METADATA_CONFLICT"}
    hard_failures = {"URL_INVALID", "DIMENSIONS_TOO_SMALL", "DIMENSIONS_TOO_LARGE", "FILE_SIZE_EXCEEDED", "RIGHTS_REJECTED", "RIGHTS_EXPIRED"}
    if any(reason in hard_failures for reason in reasons):
        classification, action = "REJECTED", "REJECT"
    elif reasons:
        classification, action = "REVIEW_REQUIRED", "REQUEST_CHANGES"
    else:
        classification, action = "ACCEPTABLE", "APPROVE"
    primary_eligible = classification == "ACCEPTABLE" and rights == "APPROVED" and bool(checksum) and url_status == "PASS"
    if payload.get("is_primary") and session and product_id and session.scalar(select(ProductImage).where(ProductImage.product_id == product_id, ProductImage.is_primary.is_(True), ProductImage.review_status == ReviewStatus.APPROVED.value, ProductImage.id != image_id)):
        primary_eligible = False
        reasons.append("PRIMARY_CONFLICT")
        results["primary_conflict_result"] = "CONFLICT"
    else:
        results["primary_conflict_result"] = "NONE"
    if "PRIMARY_CONFLICT" in reasons and classification == "ACCEPTABLE":
        classification, action = "REVIEW_REQUIRED", "APPROVE_PRIMARY"
    results["category_suitability_result"] = "PASS" if "CATEGORY_UNKNOWN" not in reasons and "ASPECT_RATIO_REVIEW" not in reasons else "REVIEW"
    results["recommended_quality"] = "acceptable" if classification == "ACCEPTABLE" else "pending" if classification == "REVIEW_REQUIRED" else "rejected"
    return ImageEvaluation(image_id, product_id, classification, results, tuple(dict.fromkeys(reasons)) or ("ACCEPTABLE_METADATA",), action, primary_eligible)


def evaluate_metadata_payload(payload: dict[str, Any], category: str | None, *, session: Session | None = None, product_id: int | None = None) -> ImageEvaluation:
    return _evaluate_values(payload, category, image_id=None, product_id=product_id, session=session, config=ImageReviewConfig())


class ImageReviewService:
    def __init__(self, session: Session, config: ImageReviewConfig | None = None) -> None:
        self.session = session
        self.config = config or ImageReviewConfig()

    def _require_enabled(self) -> None:
        if not _enabled("CATALOG_IMAGE_REVIEW_ENABLED"):
            raise RuntimeError("Catalog image review is disabled.")

    def _require_writes(self) -> None:
        self._require_enabled()
        if not _enabled("CATALOG_WRITES_ENABLED"):
            raise RuntimeError("Catalog image review writes are disabled.")

    def evaluate_image(self, image_id: int) -> ImageEvaluation:
        self._require_enabled()
        image = self.session.get(ProductImage, image_id)
        if image is None:
            raise ValueError("IMAGE_NOT_FOUND")
        return _evaluate_values({key: getattr(image, key) for key in ("source_url", "storage_key", "source_type", "width", "height", "format", "file_size", "checksum", "rights_status", "verified_at", "is_primary")}, image.product.category if image.product else None, image_id=image.id, product_id=image.product_id, session=self.session, config=self.config)

    def evaluate_product(self, product_id: int) -> list[ImageEvaluation]:
        self._require_enabled()
        images = self.session.scalars(select(ProductImage).where(ProductImage.product_id == product_id).order_by(ProductImage.id)).all()
        evaluations = [self.evaluate_image(image.id) for image in images]
        if len(images) <= self.config.maximum_images_per_product:
            return evaluations
        return [ImageEvaluation(item.image_id, item.product_id, "REVIEW_REQUIRED", item.results, tuple(dict.fromkeys((*item.reason_codes, "MAX_IMAGES_PER_PRODUCT"))), "REQUEST_CHANGES", False) for item in evaluations]

    def list_pending(self) -> list[ProductImage]:
        self._require_enabled()
        return list(self.session.scalars(select(ProductImage).where((ProductImage.review_status != ReviewStatus.APPROVED.value) | (ProductImage.rights_status != ImageRightsStatus.APPROVED.value) | (ProductImage.quality_status != ImageQualityStatus.ACCEPTABLE.value)).order_by(ProductImage.id)))

    def list_duplicate_groups(self) -> list[dict[str, Any]]:
        self._require_enabled()
        groups = self.session.execute(select(ProductImage.checksum, func.count(ProductImage.id)).where(ProductImage.checksum.is_not(None)).group_by(ProductImage.checksum).having(func.count(ProductImage.id) > 1)).all()
        return [{"checksum": checksum, "count": count} for checksum, count in groups]

    def review_history(self, image_id: int) -> list[ProductImageReview]:
        self._require_enabled()
        return list(self.session.scalars(select(ProductImageReview).where(ProductImageReview.image_id == image_id).order_by(ProductImageReview.created_at, ProductImageReview.id)))

    def record_decision(self, image_id: int, decision: str, *, reason_code: str, safe_reason: str, reviewer_identifier: str) -> ProductImageReview:
        self._require_writes()
        image = self.session.get(ProductImage, image_id)
        if image is None:
            raise ValueError("IMAGE_NOT_FOUND")
        decision = decision.upper()
        if decision not in {item.value for item in ImageReviewDecision}:
            raise ValueError("INVALID_REVIEW_DECISION")
        reason_code = _safe_text(reason_code.upper(), 80)
        safe_reason = _safe_text(safe_reason, 500)
        reviewer_identifier = _safe_text(reviewer_identifier, 120)
        if "@" in reviewer_identifier:
            raise ValueError("reviewer identifier must not be an email address")
        previous = (str(image.rights_status), str(image.quality_status), str(image.review_status))
        if decision == ImageReviewDecision.APPROVE.value:
            if str(image.rights_status).lower() != ImageRightsStatus.APPROVED.value:
                raise ValueError("RIGHTS_NOT_APPROVED")
            evaluation = self.evaluate_image(image_id)
            if evaluation.classification != "ACCEPTABLE":
                raise ValueError("IMAGE_NOT_ELIGIBLE")
            image.rights_status, image.quality_status, image.review_status = "approved", "acceptable", "approved"
        elif decision in {ImageReviewDecision.REJECT.value, ImageReviewDecision.MARK_DUPLICATE.value}:
            image.rights_status, image.quality_status, image.review_status = "rejected", "rejected", "rejected"
            image.is_primary = False
        elif decision == ImageReviewDecision.REQUEST_CHANGES.value:
            image.review_status = "pending"
        elif decision == ImageReviewDecision.EXPIRE_RIGHTS.value:
            image.rights_status, image.review_status, image.is_primary = "expired", "rejected", False
        elif decision == ImageReviewDecision.REMOVE_PRIMARY.value:
            image.is_primary = False
        elif decision == ImageReviewDecision.APPROVE_PRIMARY.value:
            evaluation = self.evaluate_image(image_id)
            if not evaluation.primary_eligible:
                raise ValueError("PRIMARY_NOT_ELIGIBLE")
            old = self.session.scalar(select(ProductImage).where(ProductImage.product_id == image.product_id, ProductImage.is_primary.is_(True), ProductImage.review_status == ReviewStatus.APPROVED.value, ProductImage.id != image.id))
            if old:
                old.is_primary = False
                self._audit(old, ImageReviewDecision.REMOVE_PRIMARY.value, "PRIMARY_REPLACED", "Primary replaced by an explicit review decision.", reviewer_identifier, (str(old.rights_status), str(old.quality_status), str(old.review_status)), (str(old.rights_status), str(old.quality_status), str(old.review_status)), False)
            image.rights_status, image.quality_status, image.review_status, image.is_primary = "approved", "acceptable", "approved", True
        image.updated_at = datetime.now(timezone.utc)
        audit = self._audit(image, decision, reason_code, safe_reason, reviewer_identifier, previous, (str(image.rights_status), str(image.quality_status), str(image.review_status)), decision == ImageReviewDecision.APPROVE_PRIMARY.value)
        self.session.commit()
        return audit

    def _audit(self, image: ProductImage, decision: str, reason_code: str, safe_reason: str, reviewer: str, previous: tuple[str, str, str], new: tuple[str, str, str], proposed_primary: bool) -> ProductImageReview:
        audit = ProductImageReview(image_id=image.id, decision=decision, reason_code=reason_code, safe_reason=safe_reason, reviewer_identifier=reviewer, previous_rights_status=previous[0], new_rights_status=new[0], previous_quality_status=previous[1], new_quality_status=new[1], previous_review_status=previous[2], new_review_status=new[2], proposed_primary=proposed_primary, created_at=datetime.now(timezone.utc))
        self.session.add(audit)
        self.session.flush()
        return audit
