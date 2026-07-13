"""Deterministic, local-only mapping for authorized synthetic catalog feeds."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.import_pipeline import ALLOWED_FIELDS, CatalogImportPipeline, ImportLimits, stage_result
from app.catalog.models import ImageRightsStatus, ImportBatch, ImportEntityType, ImportSource, SourceType

TRUE = {"1", "true", "yes"}
FIXTURE_ROOT = (Path(__file__).resolve().parents[2] / "tests" / "fixtures").resolve()
TEMPLATE_ROOT = (Path(__file__).resolve().parent / "feed_templates").resolve()
AUTHORIZATION_STATUSES = {"AUTHORIZED", "PENDING_AUTHORIZATION", "REVOKED", "EXPIRED", "SYNTHETIC_ONLY"}
RUNNABLE_AUTHORIZATIONS = {"AUTHORIZED", "SYNTHETIC_ONLY"}
SOURCE_TYPES = {"MANUFACTURER_FEED", "AUTHORIZED_DISTRIBUTOR_FEED", "AUTHORIZED_RETAILER_FEED", "PARTNER_CSV", "PARTNER_JSON", "MANUAL_AUTHORIZED_FILE", "SYNTHETIC_FIXTURE"}
INPUT_FORMATS = {"CSV", "JSON_ARRAY", "JSON_RECORDS"}
UNKNOWN_POLICIES = {"REJECT", "IGNORE_WITH_WARNING", "RECORD_FIELD_NAMES_ONLY"}
COUNTRIES = {"SA", "AE", "US"}
CURRENCIES = {"SAR", "AED", "USD"}
CREDENTIAL_FIELDS = {"password", "token", "secret", "authorization", "cookie", "api_key", "private_key"}
SAFE_TRANSFORMS = {"trim", "collapse_whitespace", "uppercase", "lowercase", "normalize_brand", "normalize_mpn", "normalize_gtin", "normalize_country_code", "normalize_currency", "normalize_boolean", "parse_decimal", "parse_integer", "parse_iso_datetime", "parse_local_datetime_with_timezone", "normalize_url", "normalize_stock_status", "normalize_category", "concatenate_fields", "map_controlled_value"}
PROTECTED_TARGETS = {"approval_status"}
REQUIRED_TEMPLATE_FIELDS = {"template_id", "template_version", "template_name", "source_name", "source_type", "authorization_status", "country", "default_currency", "default_timezone", "input_format", "entity_type", "field_mappings", "required_source_fields", "optional_source_fields", "controlled_defaults", "transforms", "identity_mapping", "provenance_mapping", "validation_rules", "stale_data_rules", "unknown_field_policy", "created_at", "updated_at"}


ERROR_TEXT = {
    "TEMPLATE_DISABLED": "Feed mapping is disabled.",
    "TEMPLATE_INVALID": "The mapping template is invalid.",
    "TEMPLATE_NOT_AUTHORIZED": "The template is not authorized for local use.",
    "TEMPLATE_VERSION_CONFLICT": "This template version has different content.",
    "UNSUPPORTED_SOURCE_TYPE": "The template source type is unsupported.",
    "UNSUPPORTED_ENTITY_TYPE": "The target entity type is unsupported.",
    "UNSUPPORTED_TRANSFORM": "The template requests an unsupported transform.",
    "SOURCE_FIELD_MISSING": "A required source field is missing.",
    "TARGET_FIELD_INVALID": "A target field is invalid.",
    "REQUIRED_MAPPING_MISSING": "A required mapping or identity is missing.",
    "UNKNOWN_SOURCE_FIELD": "The source record contains an unknown field.",
    "CREDENTIAL_FIELD_DETECTED": "A credential-like field name was detected.",
    "CONTROLLED_VALUE_UNKNOWN": "A controlled value is not mapped.",
    "COUNTRY_INVALID": "The country code is invalid.",
    "CURRENCY_INVALID": "The currency code is invalid.",
    "TIMEZONE_INVALID": "The timezone is invalid.",
    "DATETIME_INVALID": "The datetime value is invalid.",
    "PRICE_INVALID": "The numeric value is invalid.",
    "PRODUCT_IDENTITY_INCOMPLETE": "Product identity is incomplete.",
    "STORE_IDENTITY_INCOMPLETE": "Store identity is incomplete.",
    "OFFER_IDENTITY_INCOMPLETE": "Offer identity is incomplete.",
    "IMAGE_RIGHTS_REVIEW_REQUIRED": "Image rights require review.",
    "PRIMARY_IMAGE_REVIEW_REQUIRED": "Primary-image selection requires review.",
    "RECORD_LIMIT_EXCEEDED": "The feed exceeds configured limits.",
}


class MappingError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"{code}: {ERROR_TEXT.get(code, 'Mapping failed safely.')}")


@dataclass(frozen=True)
class MappingTemplate:
    data: dict[str, Any]
    checksum: str

    @property
    def template_id(self) -> str: return self.data["template_id"]
    @property
    def version(self) -> str: return str(self.data["template_version"])
    @property
    def entity_type(self) -> str: return self.data["entity_type"]


@dataclass(frozen=True)
class MappingResult:
    row_number: int
    entity_type: str
    mapped_payload: dict[str, Any]
    template_id: str
    template_version: str
    template_checksum: str
    validation_status: str
    proposed_action: str
    warnings: tuple[str, ...]
    error_codes: tuple[str, ...]
    provenance: dict[str, Any]

    def safe_dict(self) -> dict[str, Any]:
        return {"source_row_number": self.row_number, "entity_type": self.entity_type, "mapped_payload": self.mapped_payload, "template_id": self.template_id, "template_version": self.template_version, "template_checksum": self.template_checksum, "validation_status": self.validation_status, "proposed_action": self.proposed_action, "warnings": list(self.warnings), "stable_error_codes": list(self.error_codes), "provenance_summary": self.provenance}


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in TRUE


def template_checksum(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _credential_like(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).casefold()).strip("_")
    return any(part in CREDENTIAL_FIELDS for part in normalized.split("_")) or normalized in CREDENTIAL_FIELDS


def _validate_timezone(value: str) -> None:
    try: ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error: raise MappingError("TIMEZONE_INVALID") from error


def _transform(value: Any, name: str, options: dict[str, Any], record: dict[str, Any], template: MappingTemplate) -> Any:
    if name not in SAFE_TRANSFORMS: raise MappingError("UNSUPPORTED_TRANSFORM")
    text = str(value if value is not None else "")
    if name == "trim": return text.strip()
    if name == "collapse_whitespace": return re.sub(r"\s+", " ", text.strip())
    if name == "uppercase": return text.upper()
    if name == "lowercase": return text.lower()
    if name == "normalize_brand": return re.sub(r"\s+", " ", text.strip()).casefold()
    if name == "normalize_mpn": return re.sub(r"[^A-Z0-9]", "", text.upper())
    if name == "normalize_gtin": return re.sub(r"\D", "", text)
    if name == "normalize_country_code":
        result = text.strip().upper()
        if result not in COUNTRIES: raise MappingError("COUNTRY_INVALID")
        return result
    if name == "normalize_currency":
        result = text.strip().upper()
        if result not in CURRENCIES: raise MappingError("CURRENCY_INVALID")
        return result
    if name == "normalize_boolean":
        lowered = text.strip().casefold()
        if lowered in {"1", "true", "yes"}: return "true"
        if lowered in {"0", "false", "no"}: return "false"
        raise MappingError("TEMPLATE_INVALID")
    if name == "parse_decimal":
        try:
            result = Decimal(text.strip())
            if result < 0: raise InvalidOperation
            return format(result, "f")
        except InvalidOperation as error: raise MappingError("PRICE_INVALID") from error
    if name == "parse_integer":
        try: return str(int(text.strip()))
        except ValueError as error: raise MappingError("TEMPLATE_INVALID") from error
    if name in {"parse_iso_datetime", "parse_local_datetime_with_timezone"}:
        try:
            candidate = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
            if candidate.tzinfo is None:
                if name == "parse_iso_datetime": raise ValueError
                candidate = candidate.replace(tzinfo=ZoneInfo(template.data["default_timezone"]))
            return candidate.isoformat()
        except (ValueError, ZoneInfoNotFoundError) as error: raise MappingError("DATETIME_INVALID") from error
    if name == "normalize_url":
        parsed = urlsplit(text.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password: raise MappingError("TARGET_FIELD_INVALID")
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
    if name == "normalize_stock_status":
        mapping = {"available": "IN_STOCK", "sold_out": "OUT_OF_STOCK", "preorder": "PREORDER", "backorder": "BACKORDER", "unknown": "UNKNOWN"}
        result = mapping.get(text.strip().casefold())
        if not result: raise MappingError("CONTROLLED_VALUE_UNKNOWN")
        return result
    if name == "normalize_category":
        mapping = {"processor": "CPU", "graphics card": "GPU", "mainboard": "MOTHERBOARD", "memory": "RAM", "solid state drive": "STORAGE", "power supply": "PSU", "chassis": "CASE", "cpu cooler": "COOLER"}
        result = mapping.get(text.strip().casefold(), text.strip().upper())
        if result not in {item.value for item in ImportEntityType} and result not in {"CPU", "GPU", "MOTHERBOARD", "RAM", "STORAGE", "PSU", "CASE", "COOLER"}: raise MappingError("CONTROLLED_VALUE_UNKNOWN")
        return result
    if name == "concatenate_fields":
        fields = options.get("fields", [])
        separator = str(options.get("separator", " "))
        if not isinstance(fields, list) or len(fields) > 8 or len(separator) > 8: raise MappingError("TEMPLATE_INVALID")
        return separator.join(str(record.get(field, "")).strip() for field in fields)[:1000]
    if name == "map_controlled_value":
        mapping = options.get("mapping", {})
        if not isinstance(mapping, dict) or len(mapping) > 100: raise MappingError("TEMPLATE_INVALID")
        key = text.strip()
        if key not in mapping: raise MappingError("CONTROLLED_VALUE_UNKNOWN")
        return mapping[key]
    return value


class FeedMappingService:
    def __init__(self, limits: ImportLimits | None = None) -> None:
        self.limits = limits or ImportLimits()
        self._versions: dict[tuple[str, str], str] = {}

    def load_template(self, path: Path) -> MappingTemplate:
        if not _enabled("CATALOG_FEED_MAPPING_ENABLED"): raise MappingError("TEMPLATE_DISABLED")
        candidate = path.expanduser().resolve()
        if FIXTURE_ROOT not in candidate.parents and TEMPLATE_ROOT not in candidate.parents: raise MappingError("TEMPLATE_INVALID")
        try: data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error: raise MappingError("TEMPLATE_INVALID") from error
        return self.validate_template(data)

    def validate_template(self, data: dict[str, Any]) -> MappingTemplate:
        if not _enabled("CATALOG_FEED_MAPPING_ENABLED"): raise MappingError("TEMPLATE_DISABLED")
        if not isinstance(data, dict) or REQUIRED_TEMPLATE_FIELDS - set(data): raise MappingError("TEMPLATE_INVALID")
        if data["entity_type"] not in {item.value for item in ImportEntityType}: raise MappingError("UNSUPPORTED_ENTITY_TYPE")
        if data["source_type"] not in SOURCE_TYPES: raise MappingError("UNSUPPORTED_SOURCE_TYPE")
        if data["authorization_status"] not in AUTHORIZATION_STATUSES or data["authorization_status"] not in RUNNABLE_AUTHORIZATIONS: raise MappingError("TEMPLATE_NOT_AUTHORIZED")
        if data["input_format"] not in INPUT_FORMATS or data["unknown_field_policy"] not in UNKNOWN_POLICIES: raise MappingError("TEMPLATE_INVALID")
        if data["country"] not in COUNTRIES: raise MappingError("COUNTRY_INVALID")
        if data["default_currency"] not in CURRENCIES: raise MappingError("CURRENCY_INVALID")
        _validate_timezone(data["default_timezone"])
        mappings = data["field_mappings"]
        if not isinstance(mappings, list) or not mappings: raise MappingError("REQUIRED_MAPPING_MISSING")
        targets: set[str] = set()
        allowed_targets = ALLOWED_FIELDS[ImportEntityType(data["entity_type"])]
        sources: set[str] = set()
        for item in mappings:
            if not isinstance(item, dict) or not {"source_field", "target_field", "required", "allowed_transforms", "default_behavior", "missing_value_behavior"} <= set(item): raise MappingError("TEMPLATE_INVALID")
            source, target = item["source_field"], item["target_field"]
            if _credential_like(source) or _credential_like(target): raise MappingError("CREDENTIAL_FIELD_DETECTED")
            if target not in allowed_targets or target in PROTECTED_TARGETS: raise MappingError("TARGET_FIELD_INVALID")
            if target in targets: raise MappingError("TEMPLATE_INVALID")
            targets.add(target); sources.add(source)
            for transform in item["allowed_transforms"]:
                name = transform if isinstance(transform, str) else transform.get("name")
                if name not in SAFE_TRANSFORMS: raise MappingError("UNSUPPORTED_TRANSFORM")
        if not set(data["required_source_fields"]) <= sources: raise MappingError("REQUIRED_MAPPING_MISSING")
        defaults = data["controlled_defaults"]
        if any(_credential_like(key) for key in defaults): raise MappingError("CREDENTIAL_FIELD_DETECTED")
        if str(defaults.get("approval_status", "")).casefold() == "approved": raise MappingError("TEMPLATE_INVALID")
        if str(defaults.get("review_status", "")).casefold() == "approved": raise MappingError("TEMPLATE_INVALID")
        if str(defaults.get("is_primary", "")).casefold() in TRUE: raise MappingError("PRIMARY_IMAGE_REVIEW_REQUIRED")
        identity = data["identity_mapping"]
        if not isinstance(identity, dict) or not identity.get("strategies"): raise MappingError("REQUIRED_MAPPING_MISSING")
        checksum = template_checksum(data)
        key = (str(data["template_id"]), str(data["template_version"]))
        if key in self._versions and self._versions[key] != checksum: raise MappingError("TEMPLATE_VERSION_CONFLICT")
        self._versions[key] = checksum
        return MappingTemplate(data=data, checksum=checksum)

    def map_record(self, template: MappingTemplate, record: dict[str, Any], row_number: int = 1) -> MappingResult:
        if not _enabled("CATALOG_FEED_MAPPING_ENABLED") or not _enabled("CATALOG_IMPORT_ENABLED"): raise MappingError("TEMPLATE_DISABLED")
        if not isinstance(record, dict) or any(isinstance(value, (dict, list)) for value in record.values()): raise MappingError("TEMPLATE_INVALID")
        if any(_credential_like(key) for key in record): raise MappingError("CREDENTIAL_FIELD_DETECTED")
        known = set(template.data["required_source_fields"]) | set(template.data["optional_source_fields"])
        unknown = sorted(set(record) - known)
        warnings: list[str] = []
        if unknown and template.data["unknown_field_policy"] == "REJECT": raise MappingError("UNKNOWN_SOURCE_FIELD")
        if unknown: warnings.append("UNKNOWN_FIELDS:" + ",".join(unknown))
        payload: dict[str, Any] = {}
        used: list[str] = []
        for mapping in template.data["field_mappings"]:
            source, target = mapping["source_field"], mapping["target_field"]
            value = record.get(source)
            if value in (None, ""):
                if mapping["required"]: raise MappingError("SOURCE_FIELD_MISSING")
                if mapping["default_behavior"] == "USE_CONTROLLED_DEFAULT": value = template.data["controlled_defaults"].get(target)
                else: continue
            used.append(source)
            for transform in mapping["allowed_transforms"]:
                options = transform if isinstance(transform, dict) else {}
                name = transform if isinstance(transform, str) else transform["name"]
                value = _transform(value, name, options, record, template)
            payload[target] = value
        for key, value in template.data["controlled_defaults"].items():
            if key in ALLOWED_FIELDS[ImportEntityType(template.entity_type)] and key not in payload: payload[key] = value
        errors: list[str] = []
        identity = template.data["identity_mapping"]["strategies"]
        if template.entity_type == "PRODUCT" and not (payload.get("gtin") or payload.get("brand") and payload.get("manufacturer_part_number") or payload.get("product_id")): errors.append("PRODUCT_IDENTITY_INCOMPLETE")
        if template.entity_type == "STORE" and not (payload.get("store_id") or payload.get("slug") or payload.get("name") and payload.get("country")): errors.append("STORE_IDENTITY_INCOMPLETE")
        if template.entity_type == "STORE_OFFER" and not (payload.get("store_sku") and (payload.get("product_id") or payload.get("gtin") or payload.get("brand") and payload.get("manufacturer_part_number")) and (payload.get("store_id") or payload.get("store_slug") or payload.get("store_name"))): errors.append("OFFER_IDENTITY_INCOMPLETE")
        if template.entity_type == "PRODUCT_IMAGE_METADATA":
            payload["review_status"] = "PENDING"
            payload["is_primary"] = "false"
            if str(payload.get("rights_status", "")).upper() != "APPROVED": errors.append("IMAGE_RIGHTS_REVIEW_REQUIRED")
        status = "REVIEW_REQUIRED" if errors else "VALID"
        provenance = {"template_id": template.template_id, "template_version": template.version, "template_checksum": template.checksum, "safe_source_reference": template.data["source_name"], "source_row_number": row_number, "source_field_names_used": sorted(set(used)), "mapped_at": datetime.now(timezone.utc).isoformat(), "authorization_status": template.data["authorization_status"], "source_type": template.data["source_type"]}
        return MappingResult(row_number, template.entity_type, payload, template.template_id, template.version, template.checksum, status, "REVIEW" if errors else "STAGE", tuple(warnings), tuple(errors), provenance)

    def map_file(self, template: MappingTemplate, content: bytes) -> list[MappingResult]:
        if len(content) > self.limits.max_file_size: raise MappingError("RECORD_LIMIT_EXCEEDED")
        try: text = content.decode("utf-8")
        except UnicodeDecodeError as error: raise MappingError("TEMPLATE_INVALID") from error
        try:
            if template.data["input_format"] == "CSV": rows = list(csv.DictReader(io.StringIO(text), strict=True))
            else:
                parsed = json.loads(text)
                rows = parsed.get("records") if template.data["input_format"] == "JSON_RECORDS" and isinstance(parsed, dict) else parsed
        except (csv.Error, json.JSONDecodeError) as error: raise MappingError("TEMPLATE_INVALID") from error
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows): raise MappingError("TEMPLATE_INVALID")
        if len(rows) > self.limits.max_rows: raise MappingError("RECORD_LIMIT_EXCEEDED")
        results: list[MappingResult] = []
        seen: set[str] = set()
        for index, row in enumerate(rows, 1):
            result = self.map_record(template, row, index)
            fingerprint = hashlib.sha256(json.dumps(result.mapped_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if fingerprint in seen:
                result = replace(result, validation_status="DUPLICATE", proposed_action="SKIP", warnings=(*result.warnings, "DUPLICATE_SOURCE_ROW"))
            seen.add(fingerprint)
            results.append(result)
        return results

    def stage(self, session: Session, template: MappingTemplate, results: list[MappingResult]) -> ImportBatch:
        valid = [result.mapped_payload for result in results]
        content = json.dumps(valid).encode("utf-8")
        dry_run = CatalogImportPipeline(session, self.limits).dry_run(content, file_format="json", entity_type=template.entity_type)
        source_name = f"mapping:{template.template_id}:{template.version}:{template.checksum}"
        source = session.scalar(select(ImportSource).where(ImportSource.name == source_name))
        if not source:
            now = datetime.now(timezone.utc)
            source = ImportSource(name=source_name[:200], source_type=SourceType.JSON.value, rights_status=ImageRightsStatus.REVIEW.value, active=True, created_at=now, updated_at=now)
            session.add(source); session.flush()
        return stage_result(session, source, dry_run)

    @staticmethod
    def compare_versions(first: MappingTemplate, second: MappingTemplate) -> dict[str, Any]:
        if first.template_id != second.template_id: raise MappingError("TEMPLATE_INVALID")
        keys = sorted(set(first.data) | set(second.data))
        changed = [key for key in keys if first.data.get(key) != second.data.get(key)]
        return {"template_id": first.template_id, "from_version": first.version, "to_version": second.version, "changed_fields": changed, "mapping_changed": "field_mappings" in changed, "from_checksum": first.checksum, "to_checksum": second.checksum}

    def list_templates(self, root: Path) -> list[MappingTemplate]:
        templates = []
        for path in sorted(root.glob("*.json")):
            try: templates.append(self.load_template(path))
            except MappingError: continue
        return sorted(templates, key=lambda item: (item.template_id, item.version))
