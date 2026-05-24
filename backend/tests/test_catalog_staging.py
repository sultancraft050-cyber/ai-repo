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
from app.services.catalog_expansion import match_expansion_target


class FakeRecord(dict):
    def data(self) -> dict[str, Any]:
        return dict(self)


class FakeDriver:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.calls: list[dict[str, Any]] = []

    def execute_query(self, query: str, **_: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        self.calls.append({"query": query, **_})
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


class StageRunFailingDriver(FakeDriver):
    def execute_query(self, query: str, **kwargs: Any) -> tuple[list[FakeRecord], None, None]:
        if "MERGE (run:CanonicalStageRun" in query:
            raise RuntimeError("stage run write failed")
        return super().execute_query(query, **kwargs)


def _stage_request(**overrides: Any) -> CanonicalImportStageRequest:
    return CanonicalImportStageRequest(
        source_name=overrides.get("source_name", "BuildCores/OpenDB"),
        source_type=overrides.get("source_type", "canonical_specs"),
        dataset_path=overrides.get("dataset_path", "samples/cpu_sample.json"),
        category=overrides.get("category", "CPU"),
        batch_limit=overrides.get("batch_limit", 25),
        license_note=overrides.get("license_note", "Sample fixture for controlled import tests."),
        dry_run=overrides.get("dry_run", True),
    )


def test_stage_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        _resolve_import_dataset_path("../secrets.csv")


def test_stage_rejects_absolute_path() -> None:
    with pytest.raises(ValueError, match="absolute paths are not allowed"):
        _resolve_import_dataset_path(str((Path.cwd() / "secrets" / "cpu_sample.json").resolve()))


def test_stage_rejects_unsupported_file_type() -> None:
    with pytest.raises(ValueError):
        _resolve_import_dataset_path("samples/not-supported.xlsx")


def test_stage_missing_file_has_deployment_hint() -> None:
    with pytest.raises(ValueError, match="Railway images must include backend/data fixtures"):
        _resolve_import_dataset_path("samples/missing_cpu_sample.json")


def test_stage_resolves_documented_data_imports_path() -> None:
    path = _resolve_import_dataset_path("data/imports/samples/cpu_sample.json")

    assert path.name == "cpu_sample.json"
    assert path.exists()


def test_stage_rejects_unsupported_source() -> None:
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        repository.stage_canonical_import(_stage_request(source_name="Unknown Source"))


def test_stage_requires_license_note() -> None:
    with pytest.raises(ValueError):
        _stage_request(license_note="")


def test_stage_valid_cpu_json_fixture() -> None:
    driver = FakeDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.stage_canonical_import(_stage_request())

    assert response.total_records_seen == 2
    assert response.staged_records == 2
    assert response.rejected_records == 0
    assert response.categories == ["CPU"]
    assert "commit" in response.recommended_next_action.lower()
    assert not any("PriceSnapshot" in query or "RegionalPriceSnapshot" in query for query in driver.queries)


def test_stage_commit_path_uses_canonical_key_merge_without_price_mutation() -> None:
    driver = FakeDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.stage_canonical_import(_stage_request(dry_run=False))

    assert response.status == "completed"
    staged_writes = [
        call for call in driver.calls if "MERGE (record:StagedCanonicalRecord {canonical_key:" in call["query"]
    ]
    assert len(staged_writes) == 2
    assert all(call["canonical_key"] for call in staged_writes)
    assert all("staged_id" not in call["properties"] for call in staged_writes)
    assert not any("PriceSnapshot" in query or "RegionalPriceSnapshot" in query for query in driver.queries)


def test_stage_run_record_failure_does_not_block_staged_records() -> None:
    driver = StageRunFailingDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.stage_canonical_import(_stage_request(dry_run=False))

    assert response.status == "completed"
    assert response.staged_records == 2
    assert any("MERGE (record:StagedCanonicalRecord {canonical_key:" in query for query in driver.queries)


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
            batch_limit=25,
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


def test_phase2_batch_caps_are_enforced() -> None:
    with pytest.raises(ValueError, match="CPU canonical staging is capped at batch_limit=25"):
        _stage_request(batch_limit=26)
    with pytest.raises(ValueError, match="GPU canonical imports are capped at batch_limit=50"):
        CanonicalImportCommitRequest(
            source_name="BuildCores/OpenDB",
            source_type="canonical_specs",
            category="GPU",
            batch_limit=51,
            commit=True,
        )


def test_catalog_expansion_targets_returns_phase2_manifest_summary() -> None:
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    response = repository.catalog_expansion_targets(region="SA")

    assert response.phase == "phase2_saudi_core"
    assert response.product_states == ["compatibility_ready", "metadata_only", "conflict_requires_review"]
    assert response.categories[0].category == "GPU"
    assert response.categories[0].safe_stage_batch_size == 50
    assert any(family.family_name == "RTX 4070 Super" for family in response.categories[0].families)


def test_phase2_manifest_prefers_specific_target_family() -> None:
    match = match_expansion_target(
        {"name": "NVIDIA GeForce RTX 4070 Super", "brand": "NVIDIA", "model": "GeForce RTX 4070 Super"},
        "GPU",
    )

    assert match is not None
    assert match.family_name == "RTX 4070 Super"


def test_stage_rejects_records_outside_phase2_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.graph.pricing_repository as pricing_repository

    import_root = tmp_path / "imports"
    sample = import_root / "old_gpu.json"
    import_root.mkdir()
    sample.write_text(
        '[{"name":"NVIDIA GeForce GT 710","brand":"NVIDIA","model":"GeForce GT 710","vram_gb":2,"tdp_w":20,"length_mm":145,"pcie_generation":"PCIe 2.0"}]',
        encoding="utf-8",
    )
    monkeypatch.setattr(pricing_repository, "ALLOWED_CANONICAL_IMPORT_DIR", import_root)
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    response = repository.stage_canonical_import(_stage_request(dataset_path="old_gpu.json", category="GPU"))

    assert response.staged_records == 0
    assert response.rejected_records == 1
    assert "outside curated phase2 target manifest" in {item.reason for item in response.top_rejection_reasons}
