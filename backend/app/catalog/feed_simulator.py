"""Deterministic, synthetic-only catalog feed adapter simulator.

The simulator is deliberately a file generator.  It has no transport, URL
fetching, connector, database, or production integration.  Generated feeds are
passed to :mod:`feed_mapping` for the existing validation rules.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from app.catalog.feed_mapping import FeedMappingService, MappingError
from app.catalog.import_pipeline import ImportLimits

TRUE = {"1", "true", "yes"}
SIMULATOR_ROOT = Path("/tmp/catalog-feed-simulator").resolve()
FIXTURE_ROOT = (Path(__file__).resolve().parents[2] / "tests" / "fixtures").resolve()
DEFINITION_ROOT = (FIXTURE_ROOT / "catalog_feed_simulator").resolve()
TEMPLATE_ROOT = (FIXTURE_ROOT / "catalog_feed_mappings").resolve()
SUPPORTED_ENTITIES = {"PRODUCT", "PRODUCT_SPECIFICATION", "PRODUCT_IMAGE_METADATA", "STORE", "STORE_OFFER", "PRICE_OBSERVATION"}
FORMATS = {"csv", "json-array", "json-records"}
DEFAULT_LIMITS = {"max_records": 100, "max_file_size": 1_048_576, "max_mutations": 12, "max_field_length": 1_000, "max_runs": 20, "max_preview_rows": 10}


class SimulatorError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(f"{code}: {message or 'Simulation failed safely.'}")


class Mutation(str, Enum):
    SET_FIELD = "set_field"
    REMOVE_FIELD = "remove_field"
    DUPLICATE_RECORD = "duplicate_record"
    REORDER_RECORDS = "reorder_records"
    INCREMENT_DECIMAL = "increment_decimal"
    DECREMENT_DECIMAL = "decrement_decimal"
    CHANGE_STOCK_STATUS = "change_stock_status"
    SHIFT_TIMESTAMP = "shift_timestamp"
    REPLACE_CONTROLLED_VALUE = "replace_controlled_value"
    ADD_UNKNOWN_FIELD = "add_unknown_field"
    INTRODUCE_IDENTITY_CONFLICT = "introduce_identity_conflict"
    TRUNCATE_FEED = "truncate_feed"


@dataclass(frozen=True)
class Adapter:
    adapter_id: str
    adapter_version: str
    adapter_name: str
    source_type: str
    authorization_status: str
    supported_entity_types: tuple[str, ...]
    supported_formats: tuple[str, ...]
    template_id: str
    template_version: str
    default_country: str
    default_currency: str
    default_timezone: str
    scenario_id: str
    deterministic_seed: int
    maximum_records: int
    created_at: str


@dataclass(frozen=True)
class SimulationRun:
    run_id: str
    directory: Path
    manifest: dict[str, Any]
    records: tuple[dict[str, Any], ...]


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in TRUE


def _safe_id(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum() or char in "-_")


def _limits() -> dict[str, int]:
    values = dict(DEFAULT_LIMITS)
    for key in values:
        env = "CATALOG_FEED_SIMULATOR_" + key.upper()
        raw = os.getenv(env)
        if raw:
            try: values[key] = int(raw)
            except ValueError: raise SimulatorError("SCENARIO_INVALID")
        if values[key] <= 0: raise SimulatorError("SCENARIO_INVALID")
    return values


def require_enabled(*, staging: bool = False) -> None:
    if not _enabled("CATALOG_FEED_SIMULATOR_ENABLED"):
        raise SimulatorError("SIMULATOR_DISABLED", "The feed simulator is disabled.")
    if not _enabled("CATALOG_FEED_MAPPING_ENABLED"):
        raise SimulatorError("MAPPING_DISABLED", "Feed mapping must be enabled for simulation.")
    if staging and not _enabled("CATALOG_IMPORT_ENABLED"):
        raise SimulatorError("STAGING_DISABLED", "Import staging must be enabled explicitly.")


def _load_json(path: Path) -> dict[str, Any]:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error: raise SimulatorError("SCENARIO_INVALID") from error


def list_adapters() -> list[dict[str, Any]]:
    return [_load_json(path) for path in sorted(DEFINITION_ROOT.glob("adapters/*.json"))]


def list_scenarios() -> list[dict[str, Any]]:
    return [_load_json(path) for path in sorted(DEFINITION_ROOT.glob("scenarios/*.json"))]


def load_adapter(adapter_id: str) -> Adapter:
    candidate = next((item for item in list_adapters() if item.get("adapter_id") == adapter_id), None)
    if not candidate: raise SimulatorError("ADAPTER_NOT_FOUND")
    required = {"adapter_id", "adapter_version", "adapter_name", "source_type", "authorization_status", "supported_entity_types", "supported_formats", "template_id", "template_version", "default_country", "default_currency", "default_timezone", "scenario_id", "deterministic_seed", "maximum_records", "created_at"}
    if not required <= set(candidate) or candidate["source_type"] != "SYNTHETIC_FIXTURE" or candidate["authorization_status"] != "SYNTHETIC_ONLY": raise SimulatorError("ADAPTER_INVALID")
    if candidate["maximum_records"] <= 0 or candidate["maximum_records"] > _limits()["max_records"] or not candidate["deterministic_seed"] >= 0: raise SimulatorError("ADAPTER_INVALID")
    if set(candidate["supported_entity_types"]) - SUPPORTED_ENTITIES or set(candidate["supported_formats"]) - {"CSV", "JSON_ARRAY", "JSON_RECORDS"}: raise SimulatorError("ADAPTER_INVALID")
    return Adapter(**{key: tuple(value) if key in {"supported_entity_types", "supported_formats"} else value for key, value in candidate.items()})


def load_scenario(scenario_id: str) -> dict[str, Any]:
    candidate = next((item for item in list_scenarios() if item.get("scenario_id") == scenario_id), None)
    if not candidate: raise SimulatorError("SCENARIO_NOT_FOUND")
    if candidate.get("source_type") != "SYNTHETIC_FIXTURE" or candidate.get("authorization_status") != "SYNTHETIC_ONLY": raise SimulatorError("SCENARIO_INVALID")
    return candidate


def validate_adapter(adapter_id: str) -> dict[str, Any]:
    require_enabled()
    adapter = load_adapter(adapter_id)
    if adapter.scenario_id not in {item["scenario_id"] for item in list_scenarios()}: raise SimulatorError("SCENARIO_NOT_FOUND")
    return {"adapter_id": adapter.adapter_id, "adapter_version": adapter.adapter_version, "source_type": adapter.source_type, "authorization_status": adapter.authorization_status, "supported_entity_types": list(adapter.supported_entity_types), "supported_formats": list(adapter.supported_formats), "template_id": adapter.template_id, "template_version": adapter.template_version}


def _anchor(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None: raise ValueError
        return result
    except ValueError as error: raise SimulatorError("SCENARIO_INVALID") from error


def _default_entity(scenario_id: str) -> str:
    return {"new-store-offer": "STORE_OFFER", "price-and-stock-update": "STORE_OFFER", "image-metadata-review": "PRODUCT_IMAGE_METADATA", "stale-and-out-of-order": "PRICE_OBSERVATION", "duplicate-feed-replay": "PRODUCT", "identity-conflict": "PRODUCT", "invalid-pricing": "STORE_OFFER", "malformed-record-set": "PRODUCT", "partial-feed-interruption": "PRODUCT"}.get(scenario_id, "PRODUCT")


def _base_records(scenario_id: str, entity: str, anchor: datetime) -> list[dict[str, Any]]:
    stamp = anchor.isoformat()
    products = [
        {"brand": "Synthetic Labs", "mpn": "TEST-CPU-A", "name": "Test CPU Model A", "category": "Processor", "gtin": "00000000000001"},
        {"brand": "Synthetic Labs", "mpn": "TEST-CPU-B", "name": "Test CPU Model B", "category": "Processor", "gtin": "00000000000002"},
        {"brand": "Synthetic Labs", "mpn": "TEST-GPU-A", "name": "Test GPU Model A", "category": "Graphics Card", "gtin": "00000000000003"},
        {"brand": "Synthetic Labs", "mpn": "TEST-GPU-B", "name": "Test GPU Model B", "category": "Graphics Card", "gtin": "00000000000004"},
        {"brand": "Synthetic Labs", "mpn": "TEST-MAINBOARD-A", "name": "Test Mainboard Model A", "category": "Mainboard", "gtin": "00000000000005"},
        {"brand": "Synthetic Labs", "mpn": "TEST-MEMORY-A", "name": "Test Memory Kit A", "category": "Memory", "gtin": "00000000000006"},
    ]
    if entity == "PRODUCT":
        if scenario_id == "incremental-product-update":
            products[0] = {**products[0], "name": "Test CPU Model A Corrected"}
            products.append({"brand": "Synthetic Labs", "mpn": "TEST-CPU-A", "name": "Test CPU Model A Corrected", "category": "Processor", "gtin": "00000000000001"})
        if scenario_id == "identity-conflict": products[0] = {**products[0], "gtin": "00000000000002"}
        if scenario_id == "duplicate-feed-replay": products.append(dict(products[0]))
        if scenario_id == "partial-feed-interruption": return products[:2]
        if scenario_id == "malformed-record-set": products[0].pop("mpn")
        return products
    if entity == "STORE": return [{"name": "Synthetic Riyadh Components", "slug": "synthetic-riyadh-components", "country": "SA", "website": "https://fixture.invalid/store-a"}, {"name": "Fixture Electronics KSA", "slug": "fixture-electronics-ksa", "country": "SA", "website": "https://fixture.invalid/store-b"}]
    if entity == "STORE_OFFER":
        price = "899.00" if scenario_id == "price-and-stock-update" else "999.00"
        offers = [{"product_id": "1", "store_id": "1", "sku": "SYNTH-SKU-001", "url": "https://fixture.invalid/product-1", "price": price, "currency": "SAR", "stock": "available", "observed_at": stamp}, {"product_id": "2", "store_id": "2", "sku": "SYNTH-SKU-002", "url": "https://fixture.invalid/product-2", "price": "1499.00", "currency": "SAR", "stock": "sold_out" if scenario_id == "price-and-stock-update" else "available", "observed_at": stamp}]
        if scenario_id == "invalid-pricing": offers = [{**offers[0], "price": "-1.00"}, {**offers[1], "currency": "XXX"}]
        return offers
    if entity == "PRODUCT_SPECIFICATION": return [{"product_id": "1", "key": "socket", "value": "synthetic-socket"}, {"product_id": "2", "key": "memory_type", "value": "synthetic-memory"}]
    if entity == "PRODUCT_IMAGE_METADATA": return [{"product_id": "1", "url": "https://fixture.invalid/images/cpu-a.webp", "source": "Synthetic Fixture", "rights": "APPROVED"}, {"product_id": "2", "url": "https://fixture.invalid/images/cpu-b.webp", "source": "Synthetic Fixture", "rights": "PENDING"}]
    if entity == "PRICE_OBSERVATION": return [{"offer_id": "1", "price": "899.00", "currency": "SAR", "availability": "available", "observed_at": stamp}, {"offer_id": "1", "price": "899.00", "currency": "SAR", "availability": "available", "observed_at": (anchor - timedelta(days=1)).isoformat()}]
    raise SimulatorError("SCENARIO_INVALID")


def apply_mutations(records: list[dict[str, Any]], mutations: list[dict[str, Any]] | None, *, seed: int) -> list[dict[str, Any]]:
    limits = _limits()
    if len(mutations or []) > limits["max_mutations"]: raise SimulatorError("MUTATION_LIMIT_EXCEEDED")
    output = [dict(item) for item in records]
    for item in mutations or []:
        try: operator = Mutation(item["operator"])
        except (KeyError, ValueError) as error: raise SimulatorError("SCENARIO_INVALID") from error
        index = int(item.get("index", 0))
        if operator == Mutation.DUPLICATE_RECORD: output.insert(min(index, len(output)), dict(output[index % len(output)]))
        elif operator == Mutation.REORDER_RECORDS: output.reverse()
        elif operator == Mutation.REMOVE_FIELD: output[index % len(output)].pop(str(item.get("field", "")), None)
        elif operator == Mutation.SET_FIELD: output[index % len(output)][str(item.get("field", ""))] = str(item.get("value", ""))[:limits["max_field_length"]]
        elif operator in {Mutation.INCREMENT_DECIMAL, Mutation.DECREMENT_DECIMAL}:
            field = str(item.get("field", "price")); value = float(output[index % len(output)].get(field, "0")); delta = float(item.get("amount", "1")); output[index % len(output)][field] = f"{max(0, value + (delta if operator == Mutation.INCREMENT_DECIMAL else -delta)):.2f}"
        elif operator == Mutation.CHANGE_STOCK_STATUS: output[index % len(output)]["stock"] = str(item.get("value", "sold_out"))
        elif operator == Mutation.SHIFT_TIMESTAMP:
            field = str(item.get("field", "observed_at")); current = datetime.fromisoformat(output[index % len(output)][field]); output[index % len(output)][field] = (current + timedelta(minutes=int(item.get("minutes", 1)))).isoformat()
        elif operator == Mutation.REPLACE_CONTROLLED_VALUE: output[index % len(output)][str(item.get("field", "currency"))] = str(item.get("value", "SAR"))
        elif operator == Mutation.ADD_UNKNOWN_FIELD: output[index % len(output)]["synthetic_unknown"] = "fixture-only"
        elif operator == Mutation.INTRODUCE_IDENTITY_CONFLICT: output[index % len(output)].update({"gtin": "00000000000002", "brand": "Synthetic Conflict", "mpn": "CONFLICT-MPN"})
        elif operator == Mutation.TRUNCATE_FEED: output = output[:max(1, int(item.get("count", 1)))]
    return output


def _template_for(adapter: Adapter, entity: str) -> Path:
    names = {"PRODUCT": "synthetic_product_v1.json", "PRODUCT_SPECIFICATION": "synthetic_specification_v1.json", "PRODUCT_IMAGE_METADATA": "synthetic_image_v1.json", "STORE": "synthetic_store_v1.json", "STORE_OFFER": "synthetic_offer_v1.json", "PRICE_OBSERVATION": "synthetic_price_observation_v1.json"}
    path = TEMPLATE_ROOT / names[entity]
    if entity not in adapter.supported_entity_types or not path.is_file(): raise SimulatorError("TEMPLATE_NOT_FOUND")
    return path


def _serialize(records: list[dict[str, Any]], output_format: str) -> bytes:
    if output_format == "csv":
        fields = sorted({key for record in records for key in record})
        stream = __import__("io").StringIO(); writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n"); writer.writeheader(); writer.writerows(records); return stream.getvalue().encode("utf-8")
    if output_format == "json-array": return json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if output_format == "json-records": return json.dumps({"records": records}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    raise SimulatorError("UNSUPPORTED_OUTPUT_FORMAT")


def _approved_output_dir(output_dir: str | Path | None, run_id: str) -> Path:
    root = SIMULATOR_ROOT
    root.mkdir(parents=True, exist_ok=True)
    candidate = (Path(output_dir).expanduser().resolve() if output_dir else root)
    if root not in candidate.parents and candidate != root: raise SimulatorError("LOCAL_PATH_REQUIRED")
    if candidate == root: candidate = root / run_id
    elif candidate.name != run_id: raise SimulatorError("LOCAL_PATH_REQUIRED")
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def generate(*, adapter_id: str, scenario_id: str, output_format: str = "csv", seed: int | None = None, timestamp_anchor: str, record_count: int | None = None, entity_type: str | None = None, output_dir: str | Path | None = None, mutations: list[dict[str, Any]] | None = None) -> SimulationRun:
    require_enabled()
    if output_format not in FORMATS: raise SimulatorError("UNSUPPORTED_OUTPUT_FORMAT")
    adapter = load_adapter(adapter_id); scenario = load_scenario(scenario_id)
    entity = entity_type or _default_entity(scenario_id)
    if entity not in SUPPORTED_ENTITIES: raise SimulatorError("SCENARIO_INVALID")
    anchor = _anchor(timestamp_anchor); count = record_count or len(_base_records(scenario_id, entity, anchor)); limit = min(_limits()["max_records"], adapter.maximum_records)
    if count <= 0 or count > limit: raise SimulatorError("RECORD_LIMIT_EXCEEDED")
    actual_seed = adapter.deterministic_seed if seed is None else int(seed)
    records = _base_records(scenario_id, entity, anchor)[:count]
    if len(records) > 1:
        offset = actual_seed % len(records)
        records = records[offset:] + records[:offset]
    records = apply_mutations(records, mutations, seed=actual_seed)
    if len(records) > limit: raise SimulatorError("RECORD_LIMIT_EXCEEDED")
    template_path = _template_for(adapter, entity)
    service = FeedMappingService(ImportLimits(max_rows=limit))
    template = service.load_template(template_path)
    content = _serialize(records, output_format)
    if len(content) > _limits()["max_file_size"]: raise SimulatorError("FILE_SIZE_LIMIT_EXCEEDED")
    run_id = hashlib.sha256(f"{adapter_id}:{adapter.adapter_version}:{scenario_id}:{actual_seed}:{timestamp_anchor}:{entity}:{output_format}:{json.dumps(mutations or [], sort_keys=True)}".encode()).hexdigest()[:20]
    directory = _approved_output_dir(output_dir, run_id); filename = f"{_safe_id(scenario_id)}-{entity.lower()}.{('csv' if output_format == 'csv' else 'json')}"; feed_path = directory / filename; feed_path.write_bytes(content)
    # Existing templates intentionally declare their native input format.  The
    # simulator supports all three safe output encodings while validating the
    # same records through that template (without changing the template).
    native_format = {"CSV": "csv", "JSON_ARRAY": "json-array", "JSON_RECORDS": "json-records"}[template.data["input_format"]]
    mapping_error: str | None = None
    try: results = service.map_file(template, _serialize(records, native_format))
    except MappingError as error: results = []; mapping_error = error.code
    checksum = hashlib.sha256(content).hexdigest(); manifest = {"run_id": run_id, "adapter_id": adapter.adapter_id, "adapter_version": adapter.adapter_version, "scenario_id": scenario_id, "deterministic_seed": actual_seed, "timestamp_anchor": timestamp_anchor, "entity_type": entity, "output_format": output_format, "record_count": len(records), "generated_file_name": filename, "template_id": template.template_id, "template_version": template.version, "template_checksum": template.checksum, "generated_file_checksum": checksum, "expected_valid_count": sum(item.validation_status == "VALID" for item in results), "expected_invalid_count": len(records) if mapping_error else sum(item.validation_status == "REVIEW_REQUIRED" for item in results), "expected_duplicate_count": sum(item.validation_status == "DUPLICATE" for item in results), "expected_review_count": len(records) if mapping_error else sum(item.proposed_action == "REVIEW" for item in results), "mapping_error_code": mapping_error, "created_at": timestamp_anchor}
    (directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return SimulationRun(run_id, directory, manifest, tuple(records))


def preview(run: SimulationRun) -> dict[str, Any]:
    require_enabled()
    path = run.directory / run.manifest["generated_file_name"]; service = FeedMappingService(); template = service.load_template(_template_for(load_adapter(run.manifest["adapter_id"]), run.manifest["entity_type"]))
    content = path.read_bytes()
    try:
        results = service.map_file(template, content)
    except MappingError as error:
        # Preview the generated representation through the declared template
        # format, while keeping the requested output file unchanged.
        records = list(run.records)
        native_format = {"CSV": "csv", "JSON_ARRAY": "json-array", "JSON_RECORDS": "json-records"}[template.data["input_format"]]
        try: results = service.map_file(template, _serialize(records, native_format))
        except MappingError: return {"run_id": run.run_id, "record_count": len(records), "validation_counts": {"REJECTED": len(records)}, "stable_error_code": error.code, "preview_records": []}
    return {"run_id": run.run_id, "record_count": len(results), "validation_counts": {status: sum(item.validation_status == status for item in results) for status in sorted({item.validation_status for item in results})}, "preview_records": [{"source_row_number": item.row_number, "entity_type": item.entity_type, "validation_status": item.validation_status, "proposed_action": item.proposed_action, "stable_error_codes": list(item.error_codes), "source_field_names_used": item.provenance.get("source_field_names_used", [])} for item in results[:_limits()["max_preview_rows"]]]}


def stage_run(run: SimulationRun, database_url: str) -> dict[str, Any]:
    """Stage a run into an explicitly local ephemeral SQLite database."""
    require_enabled(staging=True)
    if not database_url.startswith("sqlite:///") or database_url.startswith("sqlite+"):
        raise SimulatorError("SQLITE_REQUIRED")
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from app.catalog.models import Base, ImportSource

    adapter = load_adapter(run.manifest["adapter_id"])
    template = FeedMappingService().load_template(_template_for(adapter, run.manifest["entity_type"]))
    native_format = {"CSV": "csv", "JSON_ARRAY": "json-array", "JSON_RECORDS": "json-records"}[template.data["input_format"]]
    results = FeedMappingService(ImportLimits(max_rows=_limits()["max_records"])).map_file(template, _serialize(list(run.records), native_format))
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        batch = FeedMappingService().stage(session, template, results)
        source = session.scalar(select(ImportSource).where(ImportSource.id == batch.source_id))
        if source is not None:
            provenance_name = f"simulator:{run.run_id}:{adapter.adapter_id}:{run.manifest['scenario_id']}:{run.manifest['deterministic_seed']}:{template.version}:{template.checksum}"[:200]
            existing = session.scalar(select(ImportSource).where(ImportSource.name == provenance_name))
            if existing is None or existing.id == source.id:
                source.name = provenance_name
                session.commit()
        return {"run_id": run.run_id, "batch_id": batch.id, "status": batch.status, "received_count": batch.received_count, "staged_count": batch.staged_count, "committed_count": batch.committed_count, "automatic_commit": False}


def read_manifest(run_id: str) -> dict[str, Any]:
    if not _safe_id(run_id) == run_id: raise SimulatorError("RUN_NOT_FOUND")
    path = SIMULATOR_ROOT / run_id / "manifest.json"
    if not path.is_file(): raise SimulatorError("RUN_NOT_FOUND")
    data = _load_json(path)
    if data.get("run_id") != run_id: raise SimulatorError("RUN_MANIFEST_INVALID")
    return data


def load_run(run_id: str) -> SimulationRun:
    manifest = read_manifest(run_id); directory = SIMULATOR_ROOT / run_id; path = directory / manifest["generated_file_name"]
    if not path.is_file(): raise SimulatorError("GENERATED_FILE_INVALID")
    try:
        if manifest["output_format"] == "csv": records = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        else:
            parsed = json.loads(path.read_text(encoding="utf-8")); records = parsed.get("records") if isinstance(parsed, dict) else parsed
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as error: raise SimulatorError("GENERATED_FILE_INVALID") from error
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records): raise SimulatorError("GENERATED_FILE_INVALID")
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.get("generated_file_checksum"): raise SimulatorError("RUN_MANIFEST_INVALID")
    return SimulationRun(run_id, directory, manifest, tuple(records))


def list_runs() -> list[dict[str, Any]]:
    if not SIMULATOR_ROOT.is_dir(): return []
    runs: list[dict[str, Any]] = []
    for directory in sorted(SIMULATOR_ROOT.iterdir()):
        if directory.is_dir():
            try: runs.append(read_manifest(directory.name))
            except SimulatorError: continue
    return runs[-_limits()["max_runs"]:]


def clean_run(run_id: str) -> None:
    if not _safe_id(run_id) == run_id: raise SimulatorError("RUN_NOT_FOUND")
    path = SIMULATOR_ROOT / run_id
    if not path.is_dir(): raise SimulatorError("RUN_NOT_FOUND")
    shutil.rmtree(path)


def compare_runs(first: str, second: str) -> dict[str, Any]:
    left, right = read_manifest(first), read_manifest(second)
    return {"first_run_id": first, "second_run_id": second, "same_checksum": left.get("generated_file_checksum") == right.get("generated_file_checksum"), "same_inputs": all(left.get(key) == right.get(key) for key in ("adapter_id", "adapter_version", "scenario_id", "deterministic_seed", "timestamp_anchor", "entity_type", "output_format"))}
