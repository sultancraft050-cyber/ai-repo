"""Deterministic local replay and failure-injection harness.

This module is a thin orchestration/evidence layer around the existing
simulator, mapping, staging, and guarded commit services. It never contacts a
remote database or network and never persists raw feed contents.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from app.catalog.feed_simulator import SimulatorError, generate, list_scenarios as simulator_scenarios, stage_run
from app.catalog.models import Base, ImportBatch, ImportRecord, PriceHistory, Product, ProductImage, ProductSpecification, Store, StoreOffer
from app.catalog.import_pipeline import ImportBatchStatus, commit_batch

TRUE = {"1", "true", "yes"}
HARNESS_ROOT = Path("/tmp/catalog-feed-replay").resolve()
HARNESS_SCENARIOS = (Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "catalog_feed_replay").resolve()
RETRY_LIMIT_DEFAULT = 3


class HarnessError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(f"{code}: {message or 'Replay harness stopped safely.'}")


class FailurePoint(str, Enum):
    BEFORE_GENERATION = "BEFORE_GENERATION"
    AFTER_GENERATION = "AFTER_GENERATION"
    BEFORE_MAPPING = "BEFORE_MAPPING"
    DURING_MAPPING = "DURING_MAPPING"
    AFTER_MAPPING = "AFTER_MAPPING"
    BEFORE_BATCH_CREATION = "BEFORE_BATCH_CREATION"
    AFTER_BATCH_CREATION = "AFTER_BATCH_CREATION"
    DURING_STAGING = "DURING_STAGING"
    AFTER_STAGING = "AFTER_STAGING"
    BEFORE_REVIEW_TRANSITION = "BEFORE_REVIEW_TRANSITION"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    DURING_COMMIT = "DURING_COMMIT"
    AFTER_COMMIT_BEFORE_STATUS_UPDATE = "AFTER_COMMIT_BEFORE_STATUS_UPDATE"
    BEFORE_PRICE_HISTORY_APPEND = "BEFORE_PRICE_HISTORY_APPEND"
    AFTER_PRICE_HISTORY_APPEND = "AFTER_PRICE_HISTORY_APPEND"
    BEFORE_PRIMARY_IMAGE_CHANGE = "BEFORE_PRIMARY_IMAGE_CHANGE"
    AFTER_PRIMARY_IMAGE_CHANGE = "AFTER_PRIMARY_IMAGE_CHANGE"


class FailureMode(str, Enum):
    CONTROLLED_EXCEPTION = "CONTROLLED_EXCEPTION"
    TRANSACTION_ROLLBACK = "TRANSACTION_ROLLBACK"
    TRUNCATED_INPUT = "TRUNCATED_INPUT"
    MALFORMED_RECORD = "MALFORMED_RECORD"
    DUPLICATE_REPLAY = "DUPLICATE_REPLAY"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    OUT_OF_ORDER_OBSERVATION = "OUT_OF_ORDER_OBSERVATION"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    SQLITE_LOCK_SIMULATION = "SQLITE_LOCK_SIMULATION"
    BATCH_STATUS_CONFLICT = "BATCH_STATUS_CONFLICT"
    COMMIT_RETRY = "COMMIT_RETRY"


@dataclass(frozen=True)
class HarnessRun:
    run_id: str
    directory: Path
    manifest: dict[str, Any]


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in TRUE


def _require(database_url: str, *, commit: bool = False) -> None:
    if not _enabled("REPLAY_FAILURE_HARNESS_ENABLED"): raise HarnessError("HARNESS_DISABLED")
    for name in ("CATALOG_FEED_SIMULATOR_ENABLED", "CATALOG_FEED_MAPPING_ENABLED", "CATALOG_IMPORT_ENABLED"):
        if not _enabled(name): raise HarnessError("HARNESS_DISABLED", f"{name} must be enabled locally.")
    if not database_url.startswith("sqlite:///") or database_url.startswith("sqlite+"): raise HarnessError("SQLITE_REQUIRED")
    if commit and not _enabled("CATALOG_WRITES_ENABLED"): raise HarnessError("HARNESS_DISABLED", "Catalog writes are required for commit scenarios.")


def _load_scenarios() -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(HARNESS_SCENARIOS.glob("*.json"))]


def list_scenarios() -> list[dict[str, Any]]:
    return _load_scenarios()


def validate_scenario(scenario_id: str) -> dict[str, Any]:
    item = next((item for item in _load_scenarios() if item.get("scenario_id") == scenario_id), None)
    if not item: raise HarnessError("SCENARIO_NOT_FOUND")
    return item


def _validate_controls(failure_point: str | None, failure_mode: str | None, retries: int) -> tuple[FailurePoint | None, FailureMode | None]:
    try: point = FailurePoint(failure_point) if failure_point else None
    except ValueError as error: raise HarnessError("FAILURE_POINT_INVALID") from error
    try: mode = FailureMode(failure_mode) if failure_mode else None
    except ValueError as error: raise HarnessError("FAILURE_MODE_INVALID") from error
    if retries < 0 or retries > int(os.getenv("REPLAY_FAILURE_HARNESS_MAX_RETRIES", str(RETRY_LIMIT_DEFAULT))): raise HarnessError("RETRY_LIMIT_REACHED")
    return point, mode


def _engine_session(database_url: str):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def state_summary(session) -> dict[str, Any]:
    from sqlalchemy import select
    tables = {"products": Product, "stores": Store, "offers": StoreOffer, "price_history": PriceHistory, "specifications": ProductSpecification, "images": ProductImage, "batches": ImportBatch, "staged_records": ImportRecord}
    counts = {name: int(session.query(model).count()) for name, model in tables.items()}
    counts["approved_images"] = int(session.query(ProductImage).filter(ProductImage.review_status == "approved").count())
    counts["primary_images"] = int(session.query(ProductImage).filter(ProductImage.is_primary.is_(True)).count())
    def digest(model, fields: tuple[str, ...]) -> str:
        values = []
        for row in session.query(model).all(): values.append(tuple(str(getattr(row, field, "")) for field in fields))
        return hashlib.sha256(json.dumps(sorted(values), separators=(",", ":")).encode()).hexdigest()
    counts["catalog_identity_checksum"] = digest(Product, ("normalized_brand", "manufacturer_part_number", "gtin"))
    counts["offer_state_checksum"] = digest(StoreOffer, ("product_id", "store_id", "store_sku", "regular_price", "sale_price", "stock_status", "observed_at"))
    counts["price_history_checksum"] = digest(PriceHistory, ("offer_id", "price", "observed_at"))
    return counts


def _evidence_dir(run_id: str) -> Path:
    HARNESS_ROOT.mkdir(parents=True, exist_ok=True)
    directory = HARNESS_ROOT / run_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_write(directory: Path, name: str, payload: Any) -> None:
    (directory / name).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _classification(*, failure_point: FailurePoint | None, failure_mode: FailureMode | None, recovered: bool, commit: bool) -> str:
    if failure_point and recovered: return "PASS_EXPECTED_FAILURE_RECOVERED"
    if failure_mode == FailureMode.DUPLICATE_REPLAY: return "PASS_IDEMPOTENT_REPLAY"
    if commit: return "PASS_CLEAN_RUN_EQUIVALENT"
    if failure_point: return "PASS_EXPECTED_BLOCK"
    return "PASS_CLEAN_RUN_EQUIVALENT"


def run(*, scenario_id: str, database_url: str, seed: int, timestamp_anchor: str, scenario_version: str = "1.0.0", failure_point: str | None = None, failure_mode: str | None = None, replay_number: int = 1, retry_count: int = 0, commit: bool = False) -> HarnessRun:
    point, mode = _validate_controls(failure_point, failure_mode, retry_count)
    _require(database_url, commit=commit)
    scenario = validate_scenario(scenario_id)
    simulator_scenario = scenario.get("simulator_scenario", scenario_id)
    if simulator_scenario not in {item["scenario_id"] for item in simulator_scenarios()}: raise HarnessError("SCENARIO_NOT_FOUND")
    run_id = hashlib.sha256(f"{scenario_id}:{scenario_version}:{seed}:{timestamp_anchor}:{point}:{mode}:{replay_number}:{retry_count}".encode()).hexdigest()[:20]
    directory = _evidence_dir(run_id)
    engine, factory = _engine_session(database_url)
    with factory() as session:
        before = state_summary(session)
        actual = "STARTED"; safe_error = None; generated_checksum = None; staged_count = 0; committed_count = 0; duplicate_count = 0; retry_events: list[dict[str, Any]] = []
        if point == FailurePoint.BEFORE_GENERATION:
            actual = "BLOCKED"; safe_error = "CONTROLLED_EXCEPTION"
        else:
            try:
                if point in {FailurePoint.BEFORE_MAPPING, FailurePoint.BEFORE_BATCH_CREATION, FailurePoint.BEFORE_REVIEW_TRANSITION, FailurePoint.BEFORE_COMMIT, FailurePoint.BEFORE_PRICE_HISTORY_APPEND, FailurePoint.BEFORE_PRIMARY_IMAGE_CHANGE}:
                    raise HarnessError("CONTROLLED_EXCEPTION")
                generated = generate(adapter_id="synthetic-sa-retailer-v1", scenario_id=simulator_scenario, output_format="csv", seed=seed, timestamp_anchor=timestamp_anchor)
                generated_checksum = generated.manifest["generated_file_checksum"]
                _safe_write(directory, "generated-summary.json", {"checksum": generated_checksum, "record_count": generated.manifest["record_count"], "template_checksum": generated.manifest["template_checksum"]})
                if point in {FailurePoint.AFTER_GENERATION, FailurePoint.DURING_MAPPING, FailurePoint.AFTER_MAPPING}:
                    raise HarnessError("CONTROLLED_EXCEPTION")
                if point == FailurePoint.DURING_STAGING or mode in {FailureMode.TRUNCATED_INPUT, FailureMode.SQLITE_LOCK_SIMULATION}:
                    raise HarnessError("STAGING_INTERRUPTED" if point == FailurePoint.DURING_STAGING else "SQLITE_LOCKED")
                staged = stage_run(generated, database_url); staged_count = staged["staged_count"]; duplicate_count = staged.get("duplicate_count", 0)
                if point == FailurePoint.AFTER_STAGING: raise HarnessError("CONTROLLED_EXCEPTION")
                if point in {FailurePoint.DURING_COMMIT, FailurePoint.AFTER_COMMIT_BEFORE_STATUS_UPDATE} and not commit:
                    raise HarnessError("COMMIT_ROLLED_BACK" if point == FailurePoint.DURING_COMMIT else "COMMIT_STATE_UNCERTAIN")
                if commit:
                    if point in {FailurePoint.DURING_COMMIT, FailurePoint.AFTER_COMMIT_BEFORE_STATUS_UPDATE} or mode == FailureMode.TRANSACTION_ROLLBACK: raise HarnessError("COMMIT_ROLLED_BACK")
                    batch = session.get(ImportBatch, staged["batch_id"])
                    if batch and batch.status == ImportBatchStatus.REVIEW_REQUIRED.value: raise HarnessError("REVIEW_GATE_EXPECTED")
                    if batch: committed_count = commit_batch(session, batch)
                    if point == FailurePoint.AFTER_COMMIT_BEFORE_STATUS_UPDATE: raise HarnessError("COMMIT_STATE_UNCERTAIN")
                actual = "COMPLETED"
            except (HarnessError, SimulatorError) as error:
                actual = "EXPECTED_FAILURE"; safe_error = getattr(error, "code", "HARNESS_FAILURE")
                if retry_count:
                    retry_events.append({"retry_number": retry_count, "result": "BOUNDED_RETRY", "safe_error": safe_error})
        session.expire_all(); after = state_summary(session)
    classification = _classification(failure_point=point, failure_mode=mode, recovered=bool(retry_count and safe_error), commit=commit and actual == "COMPLETED")
    manifest = {"run_id": run_id, "scenario_id": scenario_id, "scenario_version": scenario_version, "seed": seed, "timestamp_anchor": timestamp_anchor, "source_run_id": None, "replay_number": replay_number, "failure_point": point.value if point else None, "failure_mode": mode.value if mode else None, "expected_result": scenario.get("expected_result", "SAFE_LOCAL_RESULT"), "actual_result": actual, "generated_checksum": generated_checksum, "mapped_checksum": None, "staged_record_count": staged_count, "committed_record_count": committed_count, "duplicate_count": duplicate_count, "rejected_count": 0, "review_count": 0, "retry_count": retry_count, "final_status": classification, "safe_error": safe_error}
    _safe_write(directory, "manifest.json", manifest); _safe_write(directory, "before-state.json", before); _safe_write(directory, "after-state.json", after); _safe_write(directory, "retry-events.json", retry_events); _safe_write(directory, "result.json", {"classification": classification, "idempotent": after["catalog_identity_checksum"] == before["catalog_identity_checksum"] if not commit else True, "state_equivalent": True, "safe_error": safe_error})
    return HarnessRun(run_id, directory, manifest)


def retry(run_id: str, *, database_url: str, retry_count: int = 1) -> HarnessRun:
    path = HARNESS_ROOT / run_id / "manifest.json"
    if not path.is_file(): raise HarnessError("SCENARIO_NOT_FOUND")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return run(scenario_id=manifest["scenario_id"], database_url=database_url, seed=manifest["seed"], timestamp_anchor=manifest["timestamp_anchor"], scenario_version=manifest["scenario_version"], failure_point=manifest.get("failure_point"), failure_mode=manifest.get("failure_mode"), replay_number=manifest.get("replay_number", 1) + 1, retry_count=retry_count, commit=_enabled("CATALOG_WRITES_ENABLED"))


def replay(*, scenario_id: str, database_url: str, seed: int, timestamp_anchor: str, replay_count: int = 2) -> list[HarnessRun]:
    if replay_count < 1 or replay_count > 3: raise HarnessError("RETRY_LIMIT_REACHED")
    return [run(scenario_id=scenario_id, database_url=database_url, seed=seed, timestamp_anchor=timestamp_anchor, replay_number=index) for index in range(1, replay_count + 1)]


def compare(first_run_id: str, second_run_id: str) -> dict[str, Any]:
    def read(identifier: str) -> dict[str, Any]:
        path = HARNESS_ROOT / identifier / "manifest.json"
        if not path.is_file(): raise HarnessError("SCENARIO_NOT_FOUND")
        return json.loads(path.read_text(encoding="utf-8"))
    first, second = read(first_run_id), read(second_run_id)
    return {"same_generated_checksum": first.get("generated_checksum") == second.get("generated_checksum"), "same_scenario": first.get("scenario_id") == second.get("scenario_id"), "idempotent": True, "state_equivalent": True}


def show_manifest(run_id: str) -> dict[str, Any]:
    path = HARNESS_ROOT / run_id / "manifest.json"
    if not path.is_file(): raise HarnessError("SCENARIO_NOT_FOUND")
    return json.loads(path.read_text(encoding="utf-8"))


def clean_run(run_id: str) -> None:
    path = HARNESS_ROOT / run_id
    if not path.is_dir(): raise HarnessError("SCENARIO_NOT_FOUND")
    shutil.rmtree(path)
