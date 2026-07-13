from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import (
    ApprovalStatus,
    ImageRightsStatus,
    ImportBatch,
    ImportBatchStatus,
    ImportEntityType,
    ImportError,
    ImportProposedAction,
    ImportRecord,
    ImportReviewStatus,
    ImportSource,
    ImportValidationStatus,
    PriceHistory,
    Product,
    ProductCategory,
    ProductImage,
    ProductSpecification,
    ReviewStatus,
    Store,
    StoreOffer,
)
from app.catalog.image_review import evaluate_metadata_payload

TRUE_VALUES = {"1", "true", "yes"}
CONTROLLED_CURRENCIES = {"SAR"}
CONTROLLED_AVAILABILITY = {"IN_STOCK", "OUT_OF_STOCK", "UNKNOWN"}

ALLOWED_FIELDS: dict[ImportEntityType, set[str]] = {
    ImportEntityType.PRODUCT: {
        "product_id", "brand", "manufacturer_part_number", "gtin", "exact_model", "model",
        "variant", "canonical_name", "category", "slug", "lifecycle_status", "approval_status",
    },
    ImportEntityType.PRODUCT_SPECIFICATION: {
        "product_id", "brand", "manufacturer_part_number", "gtin", "specification_key",
        "normalized_value", "display_value", "unit", "source_id", "confidence", "verified_at",
    },
    ImportEntityType.PRODUCT_IMAGE_METADATA: {
        "product_id", "brand", "manufacturer_part_number", "gtin", "source_url", "source_name",
        "source_type", "width", "height", "format", "file_size", "checksum", "rights_status",
        "quality_status", "review_status", "is_primary", "verified_at",
    },
    ImportEntityType.STORE: {"store_id", "name", "slug", "country", "website", "status"},
    ImportEntityType.STORE_OFFER: {
        "product_id", "brand", "manufacturer_part_number", "gtin", "store_id", "store_slug",
        "store_name", "country", "store_sku", "product_url", "currency", "regular_price",
        "sale_price", "stock_status", "warranty", "shipping_cost", "observed_at", "expires_at",
    },
    ImportEntityType.PRICE_OBSERVATION: {
        "offer_id", "price", "currency", "availability", "observed_at",
    },
}


@dataclass(frozen=True)
class ImportLimits:
    max_file_size: int = field(default_factory=lambda: int(os.getenv("CATALOG_IMPORT_MAX_FILE_SIZE", "1048576")))
    max_rows: int = field(default_factory=lambda: int(os.getenv("CATALOG_IMPORT_MAX_ROWS", "1000")))
    max_field_length: int = field(default_factory=lambda: int(os.getenv("CATALOG_IMPORT_MAX_FIELD_LENGTH", "1000")))
    max_specifications: int = field(default_factory=lambda: int(os.getenv("CATALOG_IMPORT_MAX_SPECIFICATIONS", "100")))
    max_offers: int = field(default_factory=lambda: int(os.getenv("CATALOG_IMPORT_MAX_OFFERS", "100")))
    max_errors: int = field(default_factory=lambda: int(os.getenv("CATALOG_IMPORT_MAX_ERRORS", "100")))


@dataclass
class StagedRow:
    row_number: int
    entity_type: ImportEntityType
    normalized_payload: dict[str, Any]
    checksum: str
    validation_status: ImportValidationStatus
    review_status: ImportReviewStatus
    proposed_action: ImportProposedAction
    matched_product_id: int | None = None
    matched_store_id: int | None = None
    matched_offer_id: int | None = None
    error_code: str | None = None
    safe_message: str | None = None


@dataclass
class DryRunResult:
    entity_type: ImportEntityType
    rows: list[StagedRow] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        return {
            "received": len(self.rows),
            "valid": sum(row.validation_status == ImportValidationStatus.VALID for row in self.rows),
            "invalid": sum(row.validation_status == ImportValidationStatus.INVALID for row in self.rows),
            "duplicate": sum(row.validation_status == ImportValidationStatus.DUPLICATE for row in self.rows),
            "ambiguous": sum(row.validation_status == ImportValidationStatus.AMBIGUOUS for row in self.rows),
            "blocked": sum(row.validation_status == ImportValidationStatus.BLOCKED for row in self.rows),
        }


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in TRUE_VALUES


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _brand_key(value: Any) -> str:
    return _compact(value).casefold()


def _identity_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _compact(value).upper())


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _compact(value).lower()).strip("-")


def _checksum(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_timestamp(value: str) -> str:
    candidate = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.username


class CatalogImportPipeline:
    """Bounded, explicit staging pipeline; it never writes canonical rows itself."""

    def __init__(self, session: Session | None = None, limits: ImportLimits | None = None) -> None:
        self.session = session
        self.limits = limits or ImportLimits()

    def dry_run(self, content: bytes, *, file_format: str, entity_type: str) -> DryRunResult:
        if not _enabled("CATALOG_IMPORT_ENABLED"):
            raise RuntimeError("Catalog import is disabled.")
        try:
            declared_type = ImportEntityType(entity_type.upper())
        except ValueError as error:
            raise ValueError("UNSUPPORTED_ENTITY_TYPE") from error
        records = self._parse(content, file_format.lower())
        result = DryRunResult(entity_type=declared_type)
        seen_checksums: set[str] = set()
        identity_rows: dict[tuple[str, ...], StagedRow] = {}
        per_parent_count: dict[str, int] = {}
        for row_number, record in enumerate(records, start=1):
            normalized = self._normalize(record, declared_type)
            staged = self._validate_and_match(row_number, declared_type, normalized)
            if staged.checksum in seen_checksums:
                self._mark_duplicate(staged)
                staged.checksum = hashlib.sha256(f"{staged.checksum}:{row_number}".encode()).hexdigest()
            else:
                seen_checksums.add(staged.checksum)
                identities = self._batch_identities(declared_type, normalized)
                priors = {id(identity_rows[key]): identity_rows[key] for key in identities if key in identity_rows}
                for prior in priors.values():
                    if prior.checksum != staged.checksum:
                        self._mark_ambiguous(prior, "CONFLICTING_DUPLICATE", "Conflicting rows share a catalog identity.")
                        self._mark_ambiguous(staged, "CONFLICTING_DUPLICATE", "Conflicting rows share a catalog identity.")
                for identity in identities:
                    identity_rows.setdefault(identity, staged)
            parent_key = self._parent_key(declared_type, normalized)
            if parent_key:
                per_parent_count[parent_key] = per_parent_count.get(parent_key, 0) + 1
                maximum = self.limits.max_specifications if declared_type == ImportEntityType.PRODUCT_SPECIFICATION else self.limits.max_offers
                if per_parent_count[parent_key] > maximum:
                    self._mark_invalid(staged, "DEPENDENT_ROW_LIMIT_EXCEEDED", "Per-product import limit exceeded.")
            result.rows.append(staged)
        return result

    def _parse(self, content: bytes, file_format: str) -> list[dict[str, Any]]:
        if len(content) > self.limits.max_file_size:
            raise ValueError("FILE_SIZE_EXCEEDED")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("UNSUPPORTED_ENCODING") from error
        if file_format == "csv":
            try:
                reader = csv.DictReader(io.StringIO(text), strict=True)
                if not reader.fieldnames:
                    raise ValueError("MALFORMED_FILE")
                rows = [dict(row) for row in reader]
            except csv.Error as error:
                raise ValueError("MALFORMED_FILE") from error
        elif file_format == "json":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as error:
                raise ValueError("MALFORMED_FILE") from error
            rows = parsed.get("records") if isinstance(parsed, dict) and set(parsed) == {"records"} else parsed
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise ValueError("UNEXPECTED_PAYLOAD")
        else:
            raise ValueError("UNSUPPORTED_FORMAT")
        if len(rows) > self.limits.max_rows:
            raise ValueError("ROW_LIMIT_EXCEEDED")
        for row in rows:
            if any(isinstance(value, (dict, list)) for value in row.values()):
                raise ValueError("UNEXPECTED_PAYLOAD")
            if any(len(str(value or "")) > self.limits.max_field_length for value in row.values()):
                raise ValueError("FIELD_LENGTH_EXCEEDED")
        return rows

    def _normalize(self, record: dict[str, Any], entity_type: ImportEntityType) -> dict[str, Any]:
        normalized = {str(key).strip().lower(): _compact(value) for key, value in record.items() if value is not None and _compact(value) != ""}
        unexpected = set(normalized) - ALLOWED_FIELDS[entity_type]
        if unexpected:
            normalized["_unexpected_field"] = sorted(unexpected)[0]
            for key in unexpected:
                normalized.pop(key, None)
        for key in ("category", "currency", "country", "availability", "stock_status", "rights_status", "quality_status", "review_status", "format", "source_type"):
            if key in normalized:
                normalized[key] = normalized[key].upper()
        if "brand" in normalized:
            normalized["normalized_brand"] = _brand_key(normalized["brand"])
        if "manufacturer_part_number" in normalized:
            normalized["normalized_mpn"] = _identity_key(normalized["manufacturer_part_number"])
        if "gtin" in normalized:
            normalized["gtin"] = re.sub(r"\D", "", normalized["gtin"])
        if "specification_key" in normalized:
            normalized["specification_key"] = re.sub(r"[^a-z0-9]+", "_", normalized["specification_key"].casefold()).strip("_")
        if "unit" in normalized:
            normalized["unit"] = normalized["unit"].casefold()
        if entity_type == ImportEntityType.PRODUCT and "slug" not in normalized and normalized.get("canonical_name"):
            normalized["slug"] = _slug(normalized["canonical_name"])
        if entity_type == ImportEntityType.STORE and "slug" not in normalized and normalized.get("name"):
            normalized["slug"] = _slug(normalized["name"])
        return normalized

    def _validate_and_match(self, row: int, entity: ImportEntityType, payload: dict[str, Any]) -> StagedRow:
        staged = StagedRow(row, entity, payload, _checksum(payload), ImportValidationStatus.VALID, ImportReviewStatus.NOT_REQUIRED, ImportProposedAction.CREATE)
        if payload.get("_unexpected_field"):
            return self._mark_invalid(staged, "UNEXPECTED_FIELD", "Input contains a field outside the catalog import schema.")
        required = {
            ImportEntityType.PRODUCT: ("brand", "manufacturer_part_number", "canonical_name", "category"),
            ImportEntityType.PRODUCT_SPECIFICATION: ("specification_key", "normalized_value"),
            ImportEntityType.PRODUCT_IMAGE_METADATA: ("source_url", "source_name", "rights_status"),
            ImportEntityType.STORE: ("name", "country"),
            ImportEntityType.STORE_OFFER: ("store_sku", "product_url", "currency", "observed_at"),
            ImportEntityType.PRICE_OBSERVATION: ("offer_id", "price", "currency", "availability", "observed_at"),
        }[entity]
        missing = [key for key in required if not payload.get(key)]
        if missing:
            return self._mark_invalid(staged, "REQUIRED_FIELD_MISSING", f"Required catalog field is missing: {missing[0]}.")
        if payload.get("gtin") and (not payload["gtin"].isdigit() or len(payload["gtin"]) not in {8, 12, 13, 14}):
            return self._mark_invalid(staged, "INVALID_GTIN", "GTIN must contain 8, 12, 13, or 14 digits.")
        if entity == ImportEntityType.PRODUCT and payload["category"] not in {item.value for item in ProductCategory}:
            return self._mark_invalid(staged, "INVALID_CATEGORY", "Product category is not supported.")
        for key in ("currency",):
            if payload.get(key) and payload[key] not in CONTROLLED_CURRENCIES:
                return self._mark_invalid(staged, "INVALID_CURRENCY", "Currency is not supported for this catalog.")
        if payload.get("availability") and payload["availability"] not in CONTROLLED_AVAILABILITY:
            return self._mark_invalid(staged, "INVALID_AVAILABILITY", "Availability is not supported.")
        for key in ("observed_at", "expires_at", "verified_at"):
            if payload.get(key):
                try:
                    payload[key] = _parse_timestamp(payload[key])
                except ValueError:
                    return self._mark_invalid(staged, "INVALID_TIMESTAMP", "Timestamp must be valid ISO 8601.")
        for key in ("source_url", "product_url", "website"):
            if payload.get(key) and not _valid_url(payload[key]):
                return self._mark_invalid(staged, "INVALID_URL", "Catalog URL must use HTTP or HTTPS without embedded credentials.")
        for key in ("regular_price", "sale_price", "shipping_cost", "price"):
            if payload.get(key):
                try:
                    if Decimal(payload[key]) < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    return self._mark_invalid(staged, "INVALID_PRICE", "Price must be a non-negative decimal.")
        if payload.get("sale_price") and payload.get("regular_price") and Decimal(payload["sale_price"]) > Decimal(payload["regular_price"]):
            return self._mark_invalid(staged, "INVALID_PRICE", "Sale price cannot exceed regular price.")
        if payload.get("confidence"):
            try:
                confidence = Decimal(payload["confidence"])
                if confidence < 0 or confidence > 1:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                return self._mark_invalid(staged, "INVALID_CONFIDENCE", "Confidence must be between zero and one.")
        return {
            ImportEntityType.PRODUCT: self._match_product,
            ImportEntityType.PRODUCT_SPECIFICATION: self._match_specification,
            ImportEntityType.PRODUCT_IMAGE_METADATA: self._match_image,
            ImportEntityType.STORE: self._match_store,
            ImportEntityType.STORE_OFFER: self._match_offer,
            ImportEntityType.PRICE_OBSERVATION: self._match_observation,
        }[entity](staged)

    def _product_matches(self, payload: dict[str, Any]) -> tuple[Product | None, bool]:
        if not self.session:
            return None, False
        candidates: list[Product] = []
        gtin_match = self.session.scalar(select(Product).where(Product.gtin == payload["gtin"])) if payload.get("gtin") else None
        brand_mpn_match = None
        if payload.get("normalized_brand") and payload.get("normalized_mpn"):
            all_products = self.session.scalars(select(Product)).all()
            mpn_matches = [item for item in all_products if _identity_key(item.manufacturer_part_number) == payload["normalized_mpn"]]
            if any(item.normalized_brand != payload["normalized_brand"] for item in mpn_matches):
                return None, True
            brand_mpn_match = next((item for item in mpn_matches if item.normalized_brand == payload["normalized_brand"]), None)
        id_match = None
        missing_id = False
        if payload.get("product_id"):
            try:
                id_match = self.session.get(Product, int(payload["product_id"]))
            except ValueError:
                return None, True
            missing_id = id_match is None
        candidates = [item for item in (gtin_match, brand_mpn_match, id_match) if item]
        if len({item.id for item in candidates}) > 1 or (missing_id and candidates):
            return None, True
        return (candidates[0] if candidates else None), False

    def _store_matches(self, payload: dict[str, Any]) -> tuple[Store | None, bool]:
        if not self.session:
            return None, False
        candidates: list[Store] = []
        missing_id = False
        if payload.get("store_id"):
            try:
                match = self.session.get(Store, int(payload["store_id"]))
            except ValueError:
                return None, True
            missing_id = match is None
            if match:
                candidates.append(match)
        slug = payload.get("store_slug") or payload.get("slug")
        if slug:
            match = self.session.scalar(select(Store).where(Store.slug == _slug(slug)))
            if match:
                candidates.append(match)
        name = payload.get("store_name") or payload.get("name")
        if name and payload.get("country"):
            matches = self.session.scalars(select(Store).where(Store.country == payload["country"])).all()
            match = next((item for item in matches if _brand_key(item.name) == _brand_key(name)), None)
            if match:
                candidates.append(match)
        return (None, True) if len({item.id for item in candidates}) > 1 or (missing_id and candidates) else ((candidates[0] if candidates else None), False)

    def _match_product(self, staged: StagedRow) -> StagedRow:
        match, conflict = self._product_matches(staged.normalized_payload)
        if conflict:
            return self._mark_ambiguous(staged, "PRODUCT_IDENTITY_AMBIGUOUS", "Product identifiers resolve to different catalog products.")
        if self.session and staged.normalized_payload.get("slug"):
            slug_match = self.session.scalar(select(Product).where(Product.slug == staged.normalized_payload["slug"]))
            if slug_match and (not match or slug_match.id != match.id):
                return self._mark_ambiguous(staged, "PRODUCT_IDENTITY_AMBIGUOUS", "Product slug conflicts with another catalog product.")
        if staged.normalized_payload.get("product_id") and not match:
            return self._mark_invalid(staged, "PRODUCT_NOT_FOUND", "Explicit product ID does not exist.")
        if match:
            staged.matched_product_id = match.id
            staged.proposed_action = ImportProposedAction.UPDATE
            staged.review_status = ImportReviewStatus.PENDING
        else:
            staged.review_status = ImportReviewStatus.PENDING
        return staged

    def _match_store(self, staged: StagedRow) -> StagedRow:
        match, conflict = self._store_matches(staged.normalized_payload)
        if conflict:
            return self._mark_ambiguous(staged, "STORE_IDENTITY_AMBIGUOUS", "Store identifiers resolve to different stores.")
        if staged.normalized_payload.get("store_id") and not match:
            return self._mark_invalid(staged, "STORE_NOT_FOUND", "Explicit store ID does not exist.")
        if match:
            staged.matched_store_id = match.id
            staged.proposed_action = ImportProposedAction.UPDATE
        else:
            staged.review_status = ImportReviewStatus.PENDING
        return staged

    def _resolve_product(self, staged: StagedRow) -> Product | None:
        product, conflict = self._product_matches(staged.normalized_payload)
        if conflict:
            self._mark_ambiguous(staged, "PRODUCT_IDENTITY_AMBIGUOUS", "Product identifiers resolve to different catalog products.")
            return None
        if not product:
            self._mark_blocked(staged, "PRODUCT_NOT_FOUND", "Product identity did not resolve to an existing catalog product.")
            return None
        staged.matched_product_id = product.id
        return product

    def _match_specification(self, staged: StagedRow) -> StagedRow:
        product = self._resolve_product(staged)
        if not product or not self.session:
            return staged
        existing = self.session.scalar(select(ProductSpecification).where(ProductSpecification.product_id == product.id, ProductSpecification.specification_key == staged.normalized_payload["specification_key"]))
        if existing:
            if existing.normalized_value == staged.normalized_payload["normalized_value"]:
                self._mark_duplicate(staged)
            else:
                self._mark_ambiguous(staged, "SPECIFICATION_CONFLICT", "Existing specification has a different value.")
        return staged

    def _match_image(self, staged: StagedRow) -> StagedRow:
        product = self._resolve_product(staged)
        if not product or not self.session:
            return staged
        payload = staged.normalized_payload
        if _enabled("CATALOG_IMAGE_REVIEW_ENABLED"):
            evaluation = evaluate_metadata_payload(payload, product.category, session=self.session, product_id=product.id)
            if evaluation.classification == "REJECTED":
                return self._mark_invalid(staged, evaluation.reason_codes[0], "Image metadata failed review.")
            if evaluation.classification == "REVIEW_REQUIRED":
                staged.review_status = ImportReviewStatus.PENDING
                staged.proposed_action = ImportProposedAction.REVIEW
                staged.error_code = evaluation.reason_codes[0]
                staged.safe_message = "Image metadata requires review."
        if payload.get("checksum") and self.session.scalar(select(ProductImage).where(ProductImage.checksum == payload["checksum"])):
            return self._mark_duplicate(staged)
        if payload.get("is_primary", "").lower() in TRUE_VALUES:
            primary = self.session.scalar(select(ProductImage).where(ProductImage.product_id == product.id, ProductImage.is_primary.is_(True), ProductImage.review_status == ReviewStatus.APPROVED.value))
            if primary:
                return self._mark_ambiguous(staged, "PRIMARY_IMAGE_CONFLICT", "An approved primary image already exists.")
        if payload["rights_status"] != "APPROVED" and not staged.error_code:
            staged.review_status = ImportReviewStatus.PENDING
            staged.proposed_action = ImportProposedAction.REVIEW
            staged.error_code = "RIGHTS_REVIEW_REQUIRED"
            staged.safe_message = "Image rights require review."
        return staged

    def _match_offer(self, staged: StagedRow) -> StagedRow:
        product = self._resolve_product(staged)
        store, conflict = self._store_matches(staged.normalized_payload)
        if conflict:
            return self._mark_ambiguous(staged, "STORE_IDENTITY_AMBIGUOUS", "Store identifiers resolve to different stores.")
        if not store:
            return self._mark_blocked(staged, "STORE_NOT_FOUND", "Store identity did not resolve to an existing catalog store.")
        staged.matched_store_id = store.id
        if not product or not self.session:
            return staged
        existing = self.session.scalar(select(StoreOffer).where(StoreOffer.store_id == store.id, StoreOffer.store_sku == staged.normalized_payload["store_sku"]))
        if not existing:
            return staged
        if existing.product_id != product.id:
            return self._mark_ambiguous(staged, "OFFER_IDENTITY_AMBIGUOUS", "Store SKU is already assigned to another product.")
        staged.matched_offer_id = existing.id
        payload = staged.normalized_payload
        unchanged = (
            existing.product_url == payload["product_url"]
            and existing.currency == payload["currency"]
            and str(existing.regular_price or "") == payload.get("regular_price", "")
            and str(existing.sale_price or "") == payload.get("sale_price", "")
            and str(existing.stock_status).upper() == payload.get("stock_status", "UNKNOWN")
            and existing.observed_at.replace(tzinfo=timezone.utc) == datetime.fromisoformat(payload["observed_at"])
        )
        staged.proposed_action = ImportProposedAction.SKIP if unchanged else ImportProposedAction.UPDATE
        if unchanged:
            staged.validation_status = ImportValidationStatus.DUPLICATE
        return staged

    def _match_observation(self, staged: StagedRow) -> StagedRow:
        if not self.session:
            return self._mark_blocked(staged, "OFFER_NOT_FOUND", "Offer identity cannot be resolved without a catalog database.")
        try:
            offer = self.session.get(StoreOffer, int(staged.normalized_payload["offer_id"]))
        except ValueError:
            offer = None
        if not offer:
            return self._mark_blocked(staged, "OFFER_NOT_FOUND", "Offer identity did not resolve to an existing store offer.")
        staged.matched_offer_id = offer.id
        payload = staged.normalized_payload
        observed_at = datetime.fromisoformat(payload["observed_at"])
        observations = self.session.scalars(select(PriceHistory).where(PriceHistory.offer_id == offer.id)).all()
        duplicate = next((
            item for item in observations
            if item.price == Decimal(payload["price"])
            and item.currency == payload["currency"]
            and str(item.availability).upper() == payload["availability"]
            and item.observed_at.replace(tzinfo=timezone.utc) == observed_at
        ), None)
        return self._mark_duplicate(staged) if duplicate else staged

    @staticmethod
    def _batch_identities(entity: ImportEntityType, payload: dict[str, Any]) -> list[tuple[str, ...]]:
        if entity == ImportEntityType.PRODUCT:
            identities = []
            if payload.get("gtin"):
                identities.append((entity.value, "gtin", payload["gtin"]))
            if payload.get("normalized_brand") and payload.get("normalized_mpn"):
                identities.append((entity.value, "brand_mpn", payload["normalized_brand"], payload["normalized_mpn"]))
            if payload.get("slug"):
                identities.append((entity.value, "slug", payload["slug"]))
            return identities
        if entity == ImportEntityType.STORE:
            return [(entity.value, payload.get("slug", ""))]
        if entity == ImportEntityType.STORE_OFFER:
            return [(entity.value, payload.get("store_id") or payload.get("store_slug", ""), payload.get("store_sku", ""))]
        if entity == ImportEntityType.PRODUCT_SPECIFICATION:
            return [(entity.value, payload.get("product_id") or payload.get("gtin", ""), payload.get("specification_key", ""))]
        if entity == ImportEntityType.PRODUCT_IMAGE_METADATA and payload.get("checksum"):
            return [(entity.value, payload["checksum"])]
        if entity == ImportEntityType.PRICE_OBSERVATION:
            return [(entity.value, payload.get("offer_id", ""), payload.get("observed_at", ""))]
        return []

    @staticmethod
    def _parent_key(entity: ImportEntityType, payload: dict[str, Any]) -> str | None:
        if entity == ImportEntityType.PRODUCT_SPECIFICATION:
            return payload.get("product_id") or payload.get("gtin") or f'{payload.get("normalized_brand", "")}:{payload.get("normalized_mpn", "")}'
        if entity == ImportEntityType.STORE_OFFER:
            return payload.get("product_id") or payload.get("gtin") or f'{payload.get("normalized_brand", "")}:{payload.get("normalized_mpn", "")}'
        return None

    @staticmethod
    def _mark_invalid(staged: StagedRow, code: str, message: str) -> StagedRow:
        staged.validation_status = ImportValidationStatus.INVALID
        staged.review_status = ImportReviewStatus.PENDING
        staged.proposed_action = ImportProposedAction.REJECT
        staged.error_code, staged.safe_message = code, message
        return staged

    @staticmethod
    def _mark_blocked(staged: StagedRow, code: str, message: str) -> StagedRow:
        staged.validation_status = ImportValidationStatus.BLOCKED
        staged.review_status = ImportReviewStatus.PENDING
        staged.proposed_action = ImportProposedAction.REVIEW
        staged.error_code, staged.safe_message = code, message
        return staged

    @staticmethod
    def _mark_ambiguous(staged: StagedRow, code: str, message: str) -> StagedRow:
        staged.validation_status = ImportValidationStatus.AMBIGUOUS
        staged.review_status = ImportReviewStatus.PENDING
        staged.proposed_action = ImportProposedAction.REVIEW
        staged.error_code, staged.safe_message = code, message
        return staged

    @staticmethod
    def _mark_duplicate(staged: StagedRow) -> StagedRow:
        staged.validation_status = ImportValidationStatus.DUPLICATE
        staged.review_status = ImportReviewStatus.NOT_REQUIRED
        staged.proposed_action = ImportProposedAction.SKIP
        staged.error_code = "DUPLICATE_RECORD"
        staged.safe_message = "Record is already represented in this batch or catalog."
        return staged


def stage_result(session: Session, source: ImportSource, result: DryRunResult) -> ImportBatch:
    """Persist normalized staging rows and safe summaries, never canonical data."""
    if not _enabled("CATALOG_IMPORT_ENABLED"):
        raise RuntimeError("Catalog import is disabled.")
    now = datetime.now(timezone.utc)
    summary = result.summary
    pending = any(row.review_status == ImportReviewStatus.PENDING for row in result.rows)
    blocked = summary["invalid"] or summary["ambiguous"] or summary["blocked"]
    status = ImportBatchStatus.REVIEW_REQUIRED.value if pending or blocked else ImportBatchStatus.READY.value
    batch = ImportBatch(
        source_id=source.id, entity_type=result.entity_type.value, status=status, received_count=summary["received"],
        accepted_count=summary["valid"], rejected_count=summary["invalid"] + summary["blocked"],
        duplicate_count=summary["duplicate"], ambiguous_count=summary["ambiguous"],
        staged_count=len(result.rows), committed_count=0, started_at=now, created_at=now, updated_at=now,
    )
    session.add(batch)
    session.flush()
    error_count = 0
    for row in result.rows:
        session.add(ImportRecord(
            batch_id=batch.id, row_number=row.row_number, entity_type=row.entity_type.value,
            record_checksum=row.checksum, normalized_payload=json.dumps(row.normalized_payload, sort_keys=True),
            validation_status=row.validation_status.value, review_status=row.review_status.value,
            proposed_action=row.proposed_action.value, matched_product_id=row.matched_product_id,
            matched_store_id=row.matched_store_id, matched_offer_id=row.matched_offer_id,
            safe_error_code=row.error_code, safe_error_message=row.safe_message, created_at=now, updated_at=now,
        ))
        if row.error_code and error_count < CatalogImportPipeline().limits.max_errors:
            session.add(ImportError(batch_id=batch.id, row_number=row.row_number, error_code=row.error_code, safe_message=row.safe_message or "Import row requires review.", created_at=now))
            error_count += 1
    session.commit()
    return batch


def assert_commit_allowed(batch: ImportBatch, rows: list[ImportRecord]) -> None:
    if not _enabled("CATALOG_IMPORT_ENABLED") or not _enabled("CATALOG_WRITES_ENABLED"):
        raise RuntimeError("Catalog import commit is disabled.")
    if batch.status != ImportBatchStatus.READY.value:
        raise RuntimeError("Catalog import batch is not ready.")
    blocked = {ImportValidationStatus.INVALID.value, ImportValidationStatus.AMBIGUOUS.value, ImportValidationStatus.BLOCKED.value}
    approved = {ImportReviewStatus.APPROVED.value, ImportReviewStatus.NOT_REQUIRED.value}
    if any(row.validation_status in blocked or row.review_status not in approved for row in rows):
        raise RuntimeError("Catalog import batch contains unapproved or invalid rows.")


def commit_batch(session: Session, batch: ImportBatch) -> int:
    """Atomically apply an approved local batch; no caller is exposed through HTTP."""
    if session.bind is None or session.bind.dialect.name != "sqlite":
        raise RuntimeError("Catalog import commit is limited to a local SQLite database in this iteration.")
    if batch.status in {ImportBatchStatus.COMPLETED.value, ImportBatchStatus.COMPLETED_WITH_ERRORS.value}:
        return 0
    rows = session.scalars(select(ImportRecord).where(ImportRecord.batch_id == batch.id).order_by(ImportRecord.row_number)).all()
    assert_commit_allowed(batch, rows)
    batch.status = ImportBatchStatus.COMMITTING.value
    committed = 0
    try:
        for row in rows:
            if row.proposed_action == ImportProposedAction.SKIP.value:
                continue
            payload = json.loads(row.normalized_payload)
            committed += _commit_row(session, row, payload)
        batch.committed_count = committed
        batch.status = ImportBatchStatus.COMPLETED_WITH_ERRORS.value if batch.rejected_count else ImportBatchStatus.COMPLETED.value
        batch.completed_at = datetime.now(timezone.utc)
        batch.updated_at = batch.completed_at
        session.commit()
        return committed
    except Exception:
        session.rollback()
        failed = session.get(ImportBatch, batch.id)
        if failed:
            failed.status = ImportBatchStatus.FAILED.value
            failed.updated_at = datetime.now(timezone.utc)
            session.commit()
        raise


def _commit_row(session: Session, row: ImportRecord, payload: dict[str, Any]) -> int:
    now = datetime.now(timezone.utc)
    entity = ImportEntityType(row.entity_type)
    if entity == ImportEntityType.PRODUCT:
        target = session.get(Product, row.matched_product_id) if row.matched_product_id else None
        if not target:
            target = Product(created_at=now, updated_at=now)
            session.add(target)
        for key in ("brand", "normalized_brand", "manufacturer_part_number", "gtin", "exact_model", "variant", "canonical_name", "slug", "category", "lifecycle_status"):
            if key in payload:
                setattr(target, key, payload[key])
        target.approval_status = payload.get("approval_status", ApprovalStatus.PENDING.value).lower()
    elif entity == ImportEntityType.STORE:
        target = session.get(Store, row.matched_store_id) if row.matched_store_id else None
        if not target:
            target = Store(created_at=now, updated_at=now)
            session.add(target)
        for key in ("name", "slug", "country", "website", "status"):
            if key in payload:
                setattr(target, key, payload[key])
    elif entity == ImportEntityType.PRODUCT_SPECIFICATION:
        session.add(ProductSpecification(product_id=row.matched_product_id, specification_key=payload["specification_key"], normalized_value=payload["normalized_value"], display_value=payload.get("display_value", payload["normalized_value"]), unit=payload.get("unit"), source_id=int(payload["source_id"]) if payload.get("source_id") else None, confidence=Decimal(payload["confidence"]) if payload.get("confidence") else None, verified_at=datetime.fromisoformat(payload["verified_at"]) if payload.get("verified_at") else None, created_at=now, updated_at=now))
    elif entity == ImportEntityType.PRODUCT_IMAGE_METADATA:
        session.add(ProductImage(product_id=row.matched_product_id, source_url=payload["source_url"], source_name=payload["source_name"], source_type=payload.get("source_type", "manual").lower(), width=int(payload["width"]) if payload.get("width") else None, height=int(payload["height"]) if payload.get("height") else None, format=payload.get("format", "").lower() or None, file_size=int(payload["file_size"]) if payload.get("file_size") else None, checksum=payload.get("checksum"), rights_status=payload["rights_status"].lower(), quality_status=payload.get("quality_status", "unknown").lower(), review_status=payload.get("review_status", ReviewStatus.PENDING.value).lower(), is_primary=payload.get("is_primary", "").lower() in TRUE_VALUES, verified_at=datetime.fromisoformat(payload["verified_at"]) if payload.get("verified_at") else None, created_at=now, updated_at=now))
    elif entity == ImportEntityType.STORE_OFFER:
        target = session.get(StoreOffer, row.matched_offer_id) if row.matched_offer_id else None
        observed = datetime.fromisoformat(payload["observed_at"])
        if target:
            current_price = payload.get("sale_price") or payload.get("regular_price")
            if current_price:
                session.add(PriceHistory(offer_id=target.id, price=Decimal(current_price), currency=payload["currency"], availability=payload.get("stock_status", "UNKNOWN").lower(), observed_at=observed, created_at=now))
            if target.observed_at.replace(tzinfo=timezone.utc) > observed:
                return 1
        else:
            target = StoreOffer(product_id=row.matched_product_id, store_id=row.matched_store_id, store_sku=payload["store_sku"], created_at=now, updated_at=now)
            session.add(target)
        for key in ("product_url", "currency", "warranty"):
            if key in payload:
                setattr(target, key, payload[key])
        for key in ("regular_price", "sale_price", "shipping_cost"):
            if key in payload:
                setattr(target, key, Decimal(payload[key]))
        target.stock_status = payload.get("stock_status", "UNKNOWN").lower()
        target.observed_at = observed
        target.expires_at = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
    elif entity == ImportEntityType.PRICE_OBSERVATION:
        session.add(PriceHistory(offer_id=row.matched_offer_id, price=Decimal(payload["price"]), currency=payload["currency"], availability=payload["availability"].lower(), observed_at=datetime.fromisoformat(payload["observed_at"]), created_at=now))
    return 1


def read_file_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        content = handle.read(limit + 1)
    if len(content) > limit:
        raise ValueError("FILE_SIZE_EXCEEDED")
    return content
