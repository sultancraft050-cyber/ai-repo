from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.graph.pricing_repository import (
    Neo4jPricingRepository,
    _load_canonical_dataset_file,
    _resolve_import_dataset_path,
)
from app.models.catalog import CanonicalImportCommitRequest, CanonicalImportStageRequest


class FakeRecord(dict):
    def data(self) -> dict[str, Any]:
        return dict(self)


class FakeDriver:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute_query(self, query: str, **_: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        if "MATCH (record:StagedCanonicalRecord {canonical_key:" in query:
            return [FakeRecord(count=0)], None, None
        if "MATCH (p:Product {canonical_key:" in query:
            return [], None, None
        if "RETURN size(records) AS staged_count" in query:
            return [
                FakeRecord(
                    staged_count=3,
                    valid_count=2,
                    invalid_count=1,
                    duplicate_candidate_count=1,
                    conflict_candidate_count=0,
                    categories=["CPU"],
                    source_type="canonical_specs",
                )
            ], None, None
        if "DETACH DELETE record" in query:
            return [FakeRecord(deleted_count=3)], None, None
        if "MATCH (s:RegionalPriceSnapshot)" in query:
            return [FakeRecord(count=0)], None, None
        if "RETURN count(" in query or "RETURN count(p)" in query or "RETURN count(e)" in query:
            return [FakeRecord(count=0)], None, None
        return [], None, None


def _stage_request(**overrides: Any) -> CanonicalImportStageRequest:
    return CanonicalImportStageRequest(
        source_name=overrides.get("source_name", "BuildCores/OpenDB"),
        source_type=overrides.get("source_type", "canonical_specs"),
        dataset_path=overrides.get("dataset_path", "samples/cpu_sample.json"),
        category=overrides.get("category", "CPU"),
        batch_limit=overrides.get("batch_limit", 100),
        license_note=overrides.get("license_note", "Sample fixture for controlled import tests."),
        dry_run=overrides.get("dry_run", True),
    )


def test_stage_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        _resolve_import_dataset_path("../secrets.csv")


def test_stage_rejects_unsupported_file_type() -> None:
    with pytest.raises(ValueError):
        _resolve_import_dataset_path("samples/not-supported.xlsx")


def test_stage_rejects_unsupported_source() -> None:
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        repository.stage_canonical_import(_stage_request(source_name="Unknown Source"))


def test_stage_requires_license_note() -> None:
    with pytest.raises(ValueError):
        _stage_request(license_note="")


def test_stage_valid_cpu_json_fixture() -> None:
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    response = repository.stage_canonical_import(_stage_request())

    assert response.total_records_seen == 2
    assert response.staged_records == 2
    assert response.rejected_records == 0
    assert response.categories == ["CPU"]
    assert "commit" in response.recommended_next_action.lower()


def test_stage_valid_gpu_csv_fixture() -> None:
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    response = repository.stage_canonical_import(
        _stage_request(dataset_path="samples/gpu_sample.csv", category="GPU")
    )

    assert response.total_records_seen == 2
    assert response.staged_records == 2
    assert response.categories == ["GPU"]


def test_stage_rejects_invalid_category_specs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.graph.pricing_repository as pricing_repository

    import_root = tmp_path / "imports"
    sample = import_root / "bad_cpu.json"
    import_root.mkdir()
    sample.write_text('[{"name":"Mystery CPU","brand":"AMD"}]', encoding="utf-8")
    monkeypatch.setattr(pricing_repository, "ALLOWED_CANONICAL_IMPORT_DIR", import_root)
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    response = repository.stage_canonical_import(_stage_request(dataset_path="bad_cpu.json"))

    assert response.staged_records == 0
    assert response.rejected_records == 1
    assert "missing required compatibility specs" in {item.reason for item in response.top_rejection_reasons}


def test_staged_summary_and_clear_work() -> None:
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    summary = repository.staged_canonical_import_summary(source_name="BuildCores/OpenDB", category="CPU")
    cleared = repository.clear_staged_canonical_import(source_name="BuildCores/OpenDB", category="CPU")

    assert summary.staged_count == 3
    assert summary.valid_count == 2
    assert summary.readiness_for_commit == "ready_for_commit"
    assert cleared.deleted_count == 3
    assert cleared.status == "cleared"


def test_commit_staged_query_consumes_only_valid_records() -> None:
    driver = FakeDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    repository.commit_canonical_import(
        request=CanonicalImportCommitRequest(
            source_name="BuildCores/OpenDB",
            source_type="canonical_specs",
            category="CPU",
            batch_limit=100,
            commit=True,
        )
    )

    staged_queries = [query for query in driver.queries if "MATCH (record:StagedCanonicalRecord)" in query]
    assert any('record.validation_status = "valid"' in query for query in staged_queries)
    assert not any("SET s:" in query or "SET snapshot" in query for query in driver.queries)


def test_csv_loader_reads_local_sample() -> None:
    path = _resolve_import_dataset_path("samples/gpu_sample.csv")

    rows = _load_canonical_dataset_file(path, 10)

    assert rows[0]["name"] == "NVIDIA GeForce RTX 4070 Super"
