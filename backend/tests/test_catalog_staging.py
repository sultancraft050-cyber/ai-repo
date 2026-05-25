from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.graph.pricing_repository import (
    Neo4jPricingRepository,
    _load_canonical_dataset_file,
    _normalize_canonical_stage_record,
    _resolve_import_dataset_path,
    _stage_preselection_sort_key,
)
from app.models.catalog import CanonicalImportCommitRequest, CanonicalImportStageRequest
from app.services.catalog_expansion import annotate_expansion_target, match_expansion_target
from app.services.import_adapters.pc_part_dataset_adapter import adapt_pc_part_dataset_record


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


class ConfirmedSpecCommitDriver(FakeDriver):
    def execute_query(self, query: str, **kwargs: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        self.calls.append({"query": query, **kwargs})
        if "MATCH (record:StagedCanonicalRecord)" in query and 'record.validation_status = "valid"' in query:
            return [
                FakeRecord(
                    record={
                        "source_name": "pc-part-dataset",
                        "source_type": "community_repository",
                        "category": "GPU",
                        "validation_status": "valid",
                        "import_status": "pending",
                        "compatibility_ready": True,
                        "required_specs_present": True,
                        "license_note": "pc-part-dataset controlled fixture.",
                        "identity_confidence": 0.95,
                        "canonical_key": "GPU|AMD|POWERCOLOR_RX7800XT_16G_P",
                        "name": "PowerColor RX7800XT 16G-P",
                        "brand": "AMD",
                        "model": "PowerColor RX7800XT 16G-P",
                        "specs": {
                            "vram_gb": 16,
                            "tdp_w": 263,
                            "length_mm": 260,
                            "slots": 2.5,
                            "power_connectors": "2x 8-pin",
                            "pcie_generation": "PCIe 4.0",
                        },
                        "confirmed_spec_source_name": "founder_confirmed_gpu_specs",
                        "confirmed_spec_license_note": "manual confirmed GPU compatibility evidence",
                        "confirmed_spec_note": "confirmed GPU spec evidence",
                    }
                )
            ], None, None
        if "MATCH (p:Product {canonical_key:" in query and "RETURN p.id AS id" in query:
            return [], None, None
        if "MERGE (p:Product:CanonicalProduct" in query:
            return [FakeRecord(id="canonical:gpu", created=True)], None, None
        if "MATCH (p:Product {canonical_key:" in query and "MERGE (source:CanonicalSource" in query:
            return [FakeRecord(evidence_id="evidence:confirmed-gpu")], None, None
        return super().execute_query(query, **kwargs)


class GPUFamilyReadyCommitDriver(FakeDriver):
    def execute_query(self, query: str, **kwargs: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        self.calls.append({"query": query, **kwargs})
        if "MATCH (record:StagedCanonicalRecord)" in query and 'record.validation_status = "valid"' in query:
            return [
                FakeRecord(
                    record={
                        "source_name": "pc-part-dataset",
                        "source_type": "community_repository",
                        "category": "GPU",
                        "validation_status": "valid",
                        "import_status": "pending",
                        "compatibility_ready": False,
                        "compatibility_ready_exact": False,
                        "compatibility_ready_family": True,
                        "readiness_state": "compatibility_ready_family",
                        "required_specs_present": True,
                        "license_note": "pc-part-dataset controlled fixture.",
                        "identity_confidence": 0.95,
                        "canonical_key": "GPU|AMD|RADEON_RX_7800_XT|POWERCOLOR_RX7800XT_16G_P",
                        "name": "PowerColor RX7800XT 16G-P",
                        "brand": "AMD",
                        "model": "PowerColor RX7800XT 16G-P",
                        "specs": {
                            "chip_family": "Radeon RX 7800 XT",
                            "vram_gb": 16,
                            "pcie_generation": "PCIe 4.0",
                            "reference_tdp_w": 263,
                        },
                        "confirmed_spec_source_name": "founder_confirmed_gpu_family_specs",
                        "confirmed_spec_license_note": "manual confirmed GPU family compatibility evidence",
                        "confirmed_spec_note": "confirmed GPU family spec evidence",
                    }
                )
            ], None, None
        if "MATCH (p:Product {canonical_key:" in query and "RETURN p.id AS id" in query:
            return [], None, None
        if "MERGE (p:Product:CanonicalProduct" in query:
            return [FakeRecord(id="canonical:gpu-family", created=True)], None, None
        if "MATCH (p:Product {canonical_key:" in query and "MERGE (source:CanonicalSource" in query:
            return [FakeRecord(evidence_id="evidence:confirmed-gpu-family")], None, None
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
    assert "missing_required_specs" in {item.reason for item in response.top_rejection_reasons}


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


def test_commit_attaches_confirmed_gpu_spec_evidence_after_product_import() -> None:
    driver = ConfirmedSpecCommitDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.commit_canonical_import(
        request=CanonicalImportCommitRequest(
            source_name="pc-part-dataset",
            source_type="community_repository",
            category="GPU",
            batch_limit=25,
            commit=True,
        )
    )

    confirmed_calls = [
        call
        for call in driver.calls
        if call.get("source_name") == "founder_confirmed_gpu_specs"
        and call.get("field") == "confirmed_gpu_card_specs"
    ]
    assert response.imported_count == 1
    assert confirmed_calls
    assert not any("SET snapshot" in query or "CREATE (snapshot" in query for query in driver.queries)


def test_commit_allows_family_ready_gpu_without_exact_card_readiness() -> None:
    driver = GPUFamilyReadyCommitDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.commit_canonical_import(
        request=CanonicalImportCommitRequest(
            source_name="pc-part-dataset",
            source_type="community_repository",
            category="GPU",
            batch_limit=25,
            commit=True,
        )
    )

    product_upsert = next(call for call in driver.calls if "MERGE (p:Product:CanonicalProduct" in call["query"])
    family_evidence_calls = [
        call
        for call in driver.calls
        if call.get("source_name") == "founder_confirmed_gpu_family_specs"
        and call.get("field") == "confirmed_gpu_family_specs"
    ]
    assert response.imported_count == 1
    assert product_upsert["properties"]["compatibility_ready"] is False
    assert product_upsert["properties"]["compatibility_ready_exact"] is False
    assert product_upsert["properties"]["compatibility_ready_family"] is True
    assert product_upsert["properties"]["readiness_state"] == "compatibility_ready_family"
    assert family_evidence_calls
    assert any("MERGE (family:GPUFamily" in query for query in driver.queries)
    assert not any("SET snapshot" in query or "CREATE (snapshot" in query for query in driver.queries)


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
    assert response.product_states == [
        "compatibility_ready_exact",
        "compatibility_ready_family",
        "metadata_only",
        "conflict_requires_review",
    ]
    assert response.categories[0].category == "GPU"
    assert response.categories[0].safe_stage_batch_size == 50
    assert response.categories[0].families[0].family_name == "RTX 5060"
    assert response.categories[0].families[0].priority_tier == "current_gen_priority"
    assert any(family.family_name == "RTX 4070 Super" for family in response.categories[0].families)
    assert next(family for family in response.categories[0].families if family.family_name == "RTX 4070 Super").priority_tier == "value_fallback"


def test_phase2_manifest_prefers_specific_target_family() -> None:
    match = match_expansion_target(
        {"name": "NVIDIA GeForce RTX 4070 Super", "brand": "NVIDIA", "model": "GeForce RTX 4070 Super"},
        "GPU",
    )

    assert match is not None
    assert match.family_name == "RTX 4070 Super"
    assert match.priority_tier == "value_fallback"


def test_phase2_manifest_prioritizes_current_generation_targets() -> None:
    gpu_match = match_expansion_target(
        {"name": "NVIDIA GeForce RTX 5070 Ti", "brand": "NVIDIA", "model": "GeForce RTX 5070 Ti"},
        "GPU",
    )
    cpu_match = match_expansion_target(
        {"name": "Intel Core Ultra 7 265K", "brand": "Intel", "model": "Core Ultra 7 265K"},
        "CPU",
    )
    legacy_match = match_expansion_target(
        {"name": "AMD Radeon RX 6600", "brand": "AMD", "model": "Radeon RX 6600"},
        "GPU",
    )

    assert gpu_match is not None
    assert gpu_match.priority_tier == "current_gen_priority"
    assert cpu_match is not None
    assert cpu_match.priority_tier == "current_gen_priority"
    assert legacy_match is not None
    assert legacy_match.priority_tier == "legacy_deprioritized"
    assert gpu_match.priority < legacy_match.priority


def test_stage_can_filter_to_current_generation_priority_tier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.graph.pricing_repository as pricing_repository

    import_root = tmp_path / "imports"
    dataset = import_root / "datasets" / "pc-part-dataset" / "video-card.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(
        json.dumps(
            [
                {"name": "RTX 5070 AIB Card", "chipset": "GeForce RTX 5070", "memory": 12},
                {"name": "RTX 4070 Super AIB Card", "chipset": "GeForce RTX 4070 SUPER", "memory": 12},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pricing_repository, "ALLOWED_CANONICAL_IMPORT_DIR", import_root)
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    response = repository.stage_canonical_import(
        CanonicalImportStageRequest(
            source_name="pc-part-dataset",
            source_type="community_repository",
            dataset_path="data/imports/datasets/pc-part-dataset/video-card.json",
            category="GPU",
            adapter="pc_part_dataset",
            batch_limit=2,
            target_priority_tier="current_gen_priority",
            license_note="pc-part-dataset local fixture for priority tier filtering tests",
            dry_run=True,
        )
    )

    assert response.staged_records == 0
    assert response.deferred_records == 1
    assert response.rejected_records == 1
    assert any(item.reason == "outside_manifest" for item in response.top_rejection_reasons)


def test_phase2_manifest_prioritizes_modern_core_parts_after_cpu_gpu() -> None:
    examples = [
        (
            "RAM",
            {"name": "G.Skill Trident Z5 Neo 32GB DDR5 6000 EXPO Kit"},
            "current_gen_priority",
        ),
        (
            "Storage",
            {"name": "Samsung 990 Pro 2TB NVMe PCIe 4.0 M.2 SSD"},
            "current_gen_priority",
        ),
        (
            "PSU",
            {"name": "MSI MAG A850GL PCIE5 850W Gold Fully Modular ATX 3.0 PSU"},
            "current_gen_priority",
        ),
        (
            "Motherboard",
            {"name": "MSI MAG B650 Tomahawk WiFi AM5 DDR5 ATX Motherboard"},
            "current_gen_priority",
        ),
        (
            "Case",
            {"name": "Corsair 4000D Airflow ATX Mid Tower Case"},
            "current_gen_priority",
        ),
        (
            "Cooler",
            {"name": "Arctic Liquid Freezer III 360mm AIO CPU Cooler AM5 LGA1851"},
            "current_gen_priority",
        ),
    ]

    for category, record, tier in examples:
        match = match_expansion_target(record, category)
        assert match is not None, category
        assert match.priority_tier == tier


def test_motherboard_target_matching_prioritizes_am5_ddr5_wifi_fixture_boards() -> None:
    fixture_rows = [
        "Asus TUF GAMING B650-PLUS WIFI",
        "Asus PRIME B650-PLUS WIFI",
        "MSI MAG B650 TOMAHAWK WIFI",
        "Gigabyte B650 AORUS ELITE AX",
        "ASRock B650M Pro RS WiFi",
    ]

    for name in fixture_rows:
        record = {
            "name": name,
            "raw_name": name,
            "brand": name.split()[0],
            "category": "Motherboard",
            "specs": {"socket": "AM5", "form_factor": "ATX"},
        }
        match = match_expansion_target(record, "Motherboard")
        assert match is not None, name
        assert match.priority_tier == "current_gen_priority"


def test_motherboard_preselection_prefers_fixture_targets_over_ddr4_legacy() -> None:
    raw_rows = [
        {"name": "Gigabyte B660 AORUS Master DDR4", "socket": "LGA1700", "form_factor": "ATX"},
        {"name": "Gigabyte B660 DS3H DDR4", "socket": "LGA1700", "form_factor": "ATX"},
        {"name": "MSI B760 GAMING PLUS WIFI DDR4", "socket": "LGA1700", "form_factor": "ATX"},
        {"name": "Asus TUF GAMING B650-PLUS WIFI", "socket": "AM5", "form_factor": "ATX"},
        {"name": "Asus PRIME B650-PLUS WIFI", "socket": "AM5", "form_factor": "ATX"},
        {"name": "MSI MAG B650 TOMAHAWK WIFI", "socket": "AM5", "form_factor": "ATX"},
        {"name": "Gigabyte B650 AORUS ELITE AX", "socket": "AM5", "form_factor": "ATX"},
        {"name": "ASRock B650M Pro RS WiFi", "socket": "AM5", "form_factor": "Micro ATX"},
    ]
    records = []
    for raw in raw_rows:
        adapted = adapt_pc_part_dataset_record(raw, "Motherboard")
        record = _normalize_canonical_stage_record(adapted, "Motherboard", "pc-part-dataset fixture")
        annotate_expansion_target(record, "Motherboard")
        records.append(record)

    selected = sorted(records, key=_stage_preselection_sort_key)[:5]
    selected_names = [str(record["name"]) for record in selected]

    assert selected_names == [
        "Asus TUF GAMING B650-PLUS WIFI",
        "Asus PRIME B650-PLUS WIFI",
        "MSI MAG B650 TOMAHAWK WIFI",
        "Gigabyte B650 AORUS ELITE AX",
        "ASRock B650M Pro RS WiFi",
    ]
    assert all("DDR4" not in name for name in selected_names)


def test_phase2_low_risk_categories_can_scale_to_fifty_item_batches() -> None:
    for category in ("RAM", "Storage", "PSU"):
        request = CanonicalImportCommitRequest(
            source_name="BuildCores/OpenDB",
            source_type="canonical_specs",
            category=category,
            batch_limit=50,
            commit=True,
        )
        assert request.batch_limit == 50

    with pytest.raises(ValueError, match="Motherboard canonical imports are capped at batch_limit=20"):
        CanonicalImportCommitRequest(
            source_name="BuildCores/OpenDB",
            source_type="canonical_specs",
            category="Motherboard",
            batch_limit=21,
            commit=True,
        )


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
    assert "outside_manifest" in {item.reason for item in response.top_rejection_reasons}


def test_pc_part_dataset_preselects_manifest_targets_before_batch_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.graph.pricing_repository as pricing_repository

    import_root = tmp_path / "imports"
    dataset = import_root / "datasets" / "pc-part-dataset" / "internal-hard-drive.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(
        json.dumps(
            [
                {"name": "Seagate Barracuda Compute 2TB", "capacity": "2 TB", "interface": "SATA 6.0 Gb/s", "form_factor": "3.5\""},
                {"name": "Old Laptop Hard Drive", "capacity": "500 GB", "interface": "SATA 3.0 Gb/s", "form_factor": "2.5\""},
                {"name": "Samsung 990 Pro 2TB", "capacity": "2 TB", "interface": "M.2 PCIe 4.0 X4", "form_factor": "M.2-2280"},
                {"name": "Western Digital WD_Black SN850X 2TB", "capacity": "2 TB", "interface": "M.2 PCIe 4.0 X4", "form_factor": "M.2-2280"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pricing_repository, "ALLOWED_CANONICAL_IMPORT_DIR", import_root)
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    response = repository.stage_canonical_import(
        CanonicalImportStageRequest(
            source_name="pc-part-dataset",
            source_type="community_repository",
            dataset_path="data/imports/datasets/pc-part-dataset/internal-hard-drive.json",
            category="Storage",
            adapter="pc_part_dataset",
            batch_limit=2,
            license_note="pc-part-dataset local fixture for preselection tests",
            dry_run=True,
        )
    )

    assert response.total_records_seen == 4
    assert response.staged_records == 2
    assert response.rejected_records == 0
    assert response.accepted_current_gen_count == 2
    assert not response.top_rejection_reasons


def test_target_family_with_missing_specs_is_deferred_not_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.graph.pricing_repository as pricing_repository

    import_root = tmp_path / "imports"
    dataset = import_root / "datasets" / "pc-part-dataset" / "internal-hard-drive.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(
        json.dumps([{"name": "Samsung 990 Pro 2TB", "capacity": "2 TB", "form_factor": "M.2-2280"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(pricing_repository, "ALLOWED_CANONICAL_IMPORT_DIR", import_root)
    repository = Neo4jPricingRepository(FakeDriver())  # type: ignore[arg-type]

    response = repository.stage_canonical_import(
        CanonicalImportStageRequest(
            source_name="pc-part-dataset",
            source_type="community_repository",
            dataset_path="data/imports/datasets/pc-part-dataset/internal-hard-drive.json",
            category="Storage",
            adapter="pc_part_dataset",
            batch_limit=1,
            license_note="pc-part-dataset local fixture for deferred state tests",
            dry_run=True,
        )
    )

    assert response.staged_records == 0
    assert response.deferred_records == 1
    assert response.rejected_records == 0
    assert any(item.reason == "missing_required_specs" for item in response.top_warning_reasons)
