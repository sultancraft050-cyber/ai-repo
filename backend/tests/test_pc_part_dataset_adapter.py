from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.catalog import (
    CanonicalImportStageRequest,
    ConfirmedCpuSpecEnrichmentRequest,
    ConfirmedSpecEnrichmentRequest,
    MarketEvidenceLinkRequest,
)
from app.services.import_adapters.pc_part_dataset_adapter import adapt_pc_part_dataset_record
from app.services.catalog_expansion import annotate_expansion_target
from scripts.prepare_datasets import prepare_pc_part_dataset


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
        if "RETURN count(" in query or "RETURN count(p)" in query or "RETURN count(e)" in query:
            return [FakeRecord(count=0)], None, None
        return [], None, None


class EnrichmentDriver(FakeDriver):
    def execute_query(self, query: str, **parameters: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        if "RETURN properties(record) AS record" in query:
            return [
                FakeRecord(
                    record={
                        "canonical_key": parameters["canonical_key"],
                        "category": "CPU",
                        "specs": json.dumps({"socket": "AM5", "cores": 8, "tdp_w": 120}),
                        "compatibility_ready": False,
                    }
                )
            ], None, None
        if "RETURN count(record) AS count" in query:
            return [FakeRecord(count=1)], None, None
        if "CREATE (e:CanonicalEvidence)" in query:
            return [FakeRecord(evidence_id="evidence:test")], None, None
        return [], None, None


class MotherboardEnrichmentDriver(FakeDriver):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def execute_query(self, query: str, **parameters: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        self.calls.append({"query": query, **parameters})
        if "RETURN properties(record) AS record" in query:
            return [
                FakeRecord(
                    record={
                        "canonical_key": parameters["canonical_key"],
                        "category": "Motherboard",
                        "specs": json.dumps({"socket": "AM5", "form_factor": "ATX"}),
                        "compatibility_ready": False,
                        "missing_compatibility_fields": ["chipset", "memory_type", "m2_slots", "pcie_x16_slots"],
                    }
                )
            ], None, None
        if "RETURN count(record) AS count" in query:
            return [FakeRecord(count=1)], None, None
        if "CREATE (e:CanonicalEvidence)" in query:
            return [FakeRecord(evidence_id="evidence:motherboard")], None, None
        return [], None, None


class GPUFamilyEnrichmentDriver(FakeDriver):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def execute_query(self, query: str, **parameters: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        self.calls.append({"query": query, **parameters})
        if "RETURN properties(record) AS record" in query:
            return [
                FakeRecord(
                    record={
                        "canonical_key": parameters["canonical_key"],
                        "category": "GPU",
                        "specs": json.dumps({"chip_family": "Radeon RX 7800 XT", "vram_gb": 16}),
                        "compatibility_ready": False,
                        "compatibility_ready_exact": False,
                        "compatibility_ready_family": False,
                    }
                )
            ], None, None
        if "RETURN count(record) AS count" in query:
            return [FakeRecord(count=1)], None, None
        return [], None, None


class CurrentGenGPUFamilyEnrichmentDriver(FakeDriver):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def execute_query(self, query: str, **parameters: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        self.calls.append({"query": query, **parameters})
        if "record.target_family_key = $target_family_key" in query:
            return [
                FakeRecord(
                    record={
                        "canonical_key": "GPU|GIGABYTE|GEFORCE_RTX_5070|GIGABYTE_RTX_5070_EAGLE_OC",
                        "category": "GPU",
                        "target_family_key": "GPU|RTX_5070",
                        "target_family_name": "RTX 5070",
                        "specs": json.dumps({"chip_family": "RTX 5070", "vram_gb": 12}),
                        "compatibility_ready": False,
                        "compatibility_ready_exact": False,
                        "compatibility_ready_family": False,
                    }
                ),
                FakeRecord(
                    record={
                        "canonical_key": "GPU|MSI|GEFORCE_RTX_5070|MSI_RTX_5070_SHADOW_3X",
                        "category": "GPU",
                        "target_family_key": "GPU|RTX_5070",
                        "target_family_name": "RTX 5070",
                        "specs": json.dumps({"chip_family": "RTX 5070", "vram_gb": 12}),
                        "compatibility_ready": False,
                        "compatibility_ready_exact": False,
                        "compatibility_ready_family": False,
                    }
                ),
            ], None, None
        if "RETURN count(record) AS count" in query:
            return [FakeRecord(count=1)], None, None
        return [], None, None


class CurrentGenGPUFamilySpecOnlyEnrichmentDriver(FakeDriver):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []

    def execute_query(self, query: str, **parameters: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        self.calls.append({"query": query, **parameters})
        if "record.specs" in query and parameters.get("family_text") == "RTX 5090":
            return [
                FakeRecord(
                    record={
                        "canonical_key": "GPU|ASUS|ASUS_ROG_ASTRAL_OC",
                        "category": "GPU",
                        "target_family_key": None,
                        "target_family_name": None,
                        "raw_name": "Asus ROG Astral OC",
                        "specs": json.dumps({"chip_family": "RTX 5090", "vram_gb": 32}),
                        "compatibility_ready": False,
                        "compatibility_ready_exact": False,
                        "compatibility_ready_family": False,
                    }
                )
            ], None, None
        if "RETURN count(record) AS count" in query:
            return [FakeRecord(count=1)], None, None
        return [], None, None


class HybridReviewDriver(FakeDriver):
    def execute_query(self, query: str, **parameters: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        if "MATCH (record:StagedCanonicalRecord)" in query and "price_snapshot_count" in query:
            return [
                FakeRecord(
                    record={
                        "staged_id": "staged:cpu",
                        "raw_name": "AMD Ryzen 7 7800X3D",
                        "name": "AMD Ryzen 7 7800X3D",
                        "canonical_key": "CPU|AMD|RYZEN_7_7800X3D",
                        "category": "CPU",
                        "validation_status": "valid",
                        "compatibility_ready": False,
                        "missing_compatibility_fields": ["socket"],
                        "inferred_fields": [{"field": "socket", "inferred_value": "AM5"}],
                    },
                    market_product_id=None,
                    price_snapshot_count=0,
                    cheapest=None,
                )
            ], None, None
        return super().execute_query(query, **parameters)


class GPUHybridReviewDriver(FakeDriver):
    def execute_query(self, query: str, **parameters: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        if "MATCH (record:StagedCanonicalRecord)" in query and "price_snapshot_count" in query:
            return [
                FakeRecord(
                    record={
                        "staged_id": "staged:gpu",
                        "raw_name": "PowerColor RX7800XT 16G-P",
                        "name": "PowerColor RX7800XT 16G-P",
                        "canonical_key": "GPU|AMD|RADEON_RX_7800_XT|POWERCOLOR_RX7800XT_16G_P",
                        "category": "GPU",
                        "validation_status": "valid",
                        "compatibility_ready": False,
                        "compatibility_ready_exact": False,
                        "compatibility_ready_family": True,
                        "readiness_state": "compatibility_ready_family",
                        "specs": json.dumps(
                            {
                                "chip_family": "Radeon RX 7800 XT",
                                "vram_gb": 16,
                                "pcie_generation": "PCIe 4.0",
                                "reference_tdp_w": 263,
                            }
                        ),
                    },
                    market_product_id=None,
                    price_snapshot_count=0,
                    cheapest=None,
                )
            ], None, None
        return super().execute_query(query, **parameters)


class MarketLinkDriver(FakeDriver):
    def execute_query(self, query: str, **parameters: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        if "MATCH (p:Product)" in query and "price_snapshot_count" in query:
            return [
                FakeRecord(
                    product_id="prod:cpu",
                    product_name="AMD Ryzen 7 7800X3D",
                    canonical_key="CPU|AMD|RYZEN_7_7800X3D",
                    confidence=0.95,
                    price_snapshot_count=1,
                    cheapest_price_sar=1499,
                    cheapest_vendor="Computer Palace",
                )
            ], None, None
        return [], None, None


def test_prepare_datasets_copies_approved_files_and_creates_target(tmp_path: Path) -> None:
    source = tmp_path / "pc-part-dataset" / "data" / "json"
    target = tmp_path / "backend" / "data" / "imports" / "datasets" / "pc-part-dataset"
    source.mkdir(parents=True)
    (source / "cpu.json").write_text("[]", encoding="utf-8")
    (source / "unknown.json").write_text("[]", encoding="utf-8")

    copied = prepare_pc_part_dataset(source, target, ["cpu.json"])

    assert copied == 1
    assert (target / "cpu.json").is_file()
    assert not (target / "unknown.json").exists()


def test_prepare_datasets_rejects_unknown_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported pc-part-dataset"):
        prepare_pc_part_dataset(tmp_path, tmp_path / "target", ["unknown.json"])


def test_flat_cpu_record_infers_socket_as_inferred_evidence_not_confirmed_compatibility() -> None:
    record = adapt_pc_part_dataset_record(
        {"name": "AMD Ryzen 7 7800X3D", "core_count": 8, "thread_count": 16, "tdp": 120},
        "CPU",
    )

    assert record["specs"]["socket"] == "AM5"
    assert record["compatibility_ready"] is False
    assert record["compatibility_completeness_score"] == 0.0
    assert record["inferred_fields"][0]["field"] == "socket"
    assert record["inferred_fields"][0]["confidence"] == 0.8
    assert any("critical compatibility field is inferred" in warning for warning in record["warning_reasons"])


def test_cpu_missing_socket_stages_as_metadata_not_ready() -> None:
    record = adapt_pc_part_dataset_record({"name": "Mystery Processor", "core_count": 6}, "CPU")

    assert record["compatibility_ready"] is False
    assert "socket" in record["missing_compatibility_fields"]


def test_ram_speed_modules_parse_capacity_and_ddr_type() -> None:
    record = adapt_pc_part_dataset_record(
        {"name": "Example 32GB DDR5 Kit", "speed": [6000], "modules": ["2 x 16"]},
        "RAM",
    )

    assert record["specs"]["memory_type"] == "DDR5"
    assert record["specs"]["capacity_gb"] == 32
    assert record["specs"]["kit_config"] == "2x16GB"


def test_ram_pc_part_dataset_speed_and_modules_lists_parse_structured_values() -> None:
    record = adapt_pc_part_dataset_record(
        {"name": "Corsair Vengeance RGB 32 GB", "speed": [5, 6000], "modules": [2, 16], "cas_latency": 36},
        "RAM",
    )

    assert record["specs"]["memory_type"] == "DDR5"
    assert record["specs"]["speed_mhz"] == 6000
    assert record["specs"]["capacity_gb"] == 32
    assert record["specs"]["kit_config"] == "2x16GB"
    assert record["compatibility_ready"] is True
    assert not record["inferred_fields"]


def test_ram_rejects_unrealistic_structured_speed_and_module_ranges() -> None:
    record = adapt_pc_part_dataset_record(
        {"name": "Unrealistic Memory Kit", "speed": [3, 1600], "modules": [3, 12]},
        "RAM",
    )

    assert "memory_type" not in record["specs"]
    assert "speed_mhz" not in record["specs"]
    assert "capacity_gb" not in record["specs"]
    assert "kit_config" not in record["specs"]
    assert record["compatibility_ready"] is False


def test_ram_target_matching_uses_parsed_specs_not_name_labels() -> None:
    record = adapt_pc_part_dataset_record(
        {"name": "Corsair Vengeance RGB 32 GB", "speed": [5, 6000], "modules": [2, 16], "cas_latency": 36},
        "RAM",
    )

    match = annotate_expansion_target(record, "RAM")

    assert match is not None
    assert match.family_name == "DDR5 2x16GB 6000"
    assert match.priority_tier == "current_gen_priority"
    assert record["compatibility_ready"] is True
    assert record["missing_compatibility_fields"] == []


def test_ram_target_matching_does_not_match_64gb_kit_to_32gb_target() -> None:
    record = adapt_pc_part_dataset_record(
        {"name": "G.Skill Trident Z5 RGB 64 GB", "speed": [5, 6400], "modules": [2, 32]},
        "RAM",
    )

    match = annotate_expansion_target(record, "RAM")

    assert match is None


def test_gpu_requires_confirmed_power_length_and_pcie_for_compatibility_ready() -> None:
    record = adapt_pc_part_dataset_record(
        {"name": "MSI GeForce RTX 4070 Super", "chipset": "GeForce RTX 4070 SUPER", "memory": 12, "length": 261},
        "GPU",
    )

    assert record["compatibility_ready"] is False
    assert "tdp_w" in record["missing_compatibility_fields"]
    assert "pcie_generation" in record["missing_compatibility_fields"]
    assert "slots" in record["missing_compatibility_fields"]
    assert "power_connectors" in record["missing_compatibility_fields"]


def test_case_missing_clearance_warns_without_fake_defaults() -> None:
    record = adapt_pc_part_dataset_record({"name": "Airflow ATX Case", "motherboard_form_factor": ["ATX"]}, "Case")

    assert "max_gpu_length_mm" not in record["specs"]
    assert "max_cpu_cooler_height_mm" not in record["specs"]
    assert any("clearance_unknown" in warning for warning in record["warning_reasons"])


def test_cooler_missing_dimensions_warns_and_is_not_ready_without_socket_support() -> None:
    record = adapt_pc_part_dataset_record({"name": "Quiet Air Cooler"}, "Cooler")

    assert record["compatibility_ready"] is False
    assert "socket_support" in record["missing_compatibility_fields"]
    assert any("dimensions unknown" in warning for warning in record["warning_reasons"])


def test_pc_part_dataset_stage_accepts_flat_json_without_price_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.graph.pricing_repository as pricing_repository

    import_root = tmp_path / "imports"
    dataset = import_root / "datasets" / "pc-part-dataset" / "cpu.json"
    dataset.parent.mkdir(parents=True)
    dataset.write_text(
        json.dumps(
            [
                {"name": "AMD Ryzen 7 7800X3D", "core_count": 8, "thread_count": 16, "tdp": 120},
                {"name": "Mystery Processor", "core_count": 4},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pricing_repository, "ALLOWED_CANONICAL_IMPORT_DIR", import_root)
    driver = FakeDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.stage_canonical_import(
        CanonicalImportStageRequest(
            source_name="pc-part-dataset",
            source_type="community_repository",
            dataset_path="data/imports/datasets/pc-part-dataset/cpu.json",
            category="CPU",
            adapter="pc_part_dataset",
            batch_limit=25,
            license_note="pc-part-dataset local fixture for controlled adapter tests",
            dry_run=False,
        )
    )

    assert response.staged_records == 1
    assert response.rejected_records == 1
    assert response.true_rejected_count == 1
    assert any(item.reason == "metadata-only record is not compatibility-ready" for item in response.top_warning_reasons)
    assert not any("PriceSnapshot" in query or "RegionalPriceSnapshot" in query for query in driver.queries)


def test_unsupported_adapter_is_rejected_by_request_model() -> None:
    with pytest.raises(ValueError):
        CanonicalImportStageRequest.model_validate(
            {
                "source_name": "pc-part-dataset",
                "source_type": "community_repository",
                "dataset_path": "data/imports/datasets/pc-part-dataset/cpu.json",
                "category": "CPU",
                "adapter": "unsupported",
                "batch_limit": 50,
                "license_note": "pc-part-dataset local fixture for controlled adapter tests",
                "dry_run": True,
            }
        )


def test_confirmed_cpu_enrichment_dry_run_does_not_write() -> None:
    driver = EnrichmentDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.enrich_staged_cpu_specs(
        ConfirmedCpuSpecEnrichmentRequest(
            source_name="founder_confirmed_specs",
            license_note="manual confirmed CPU compatibility evidence",
            records=[
                {
                    "canonical_key": "CPU|AMD|RYZEN_7_7800X3D",
                    "socket": "AM5",
                    "cores": 8,
                    "threads": 16,
                    "tdp_w": 120,
                    "evidence_note": "confirmed CPU spec evidence",
                }
            ],
            dry_run=True,
        )
    )

    assert response.enriched_records == 0
    assert response.items[0].status == "would_enrich"
    assert not any("SET record.specs" in query for query in driver.queries)
    assert not any("CanonicalEvidence" in query for query in driver.queries)


def test_confirmed_cpu_enrichment_updates_staged_record_without_price_mutation() -> None:
    driver = EnrichmentDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.enrich_staged_cpu_specs(
        ConfirmedCpuSpecEnrichmentRequest(
            source_name="founder_confirmed_specs",
            license_note="manual confirmed CPU compatibility evidence",
            records=[
                {
                    "canonical_key": "CPU|AMD|RYZEN_7_7800X3D",
                    "socket": "AM5",
                    "cores": 8,
                    "threads": 16,
                    "tdp_w": 120,
                    "evidence_note": "confirmed CPU spec evidence",
                }
            ],
            dry_run=False,
        )
    )

    assert response.enriched_records == 1
    assert response.evidence_created == 1
    assert response.items[0].confirmed_fields == ["socket", "cores", "threads", "tdp_w"]
    assert any("SET record.specs" in query for query in driver.queries)
    assert any("CREATE (e:CanonicalEvidence)" in query for query in driver.queries)
    assert not any("PriceSnapshot" in query or "RegionalPriceSnapshot" in query for query in driver.queries)


def test_hybrid_review_classifies_metadata_only_without_market_mutation() -> None:
    driver = HybridReviewDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.hybrid_import_review(source_name="pc-part-dataset", category="CPU", region="SA")

    assert response.total_staged == 1
    assert response.items[0].classification == "metadata_only_needs_enrichment"
    assert response.items[0].commit_eligible is False
    assert response.top_missing_compatibility_fields[0].reason == "socket"
    assert not any("SET snapshot" in query or "CREATE (snapshot" in query for query in driver.queries)


def test_hybrid_review_reports_gpu_family_ready_separately_from_exact_ready() -> None:
    driver = GPUHybridReviewDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.hybrid_import_review(source_name="pc-part-dataset", category="GPU", region="SA")

    assert response.family_ready_count == 1
    assert response.exact_ready_count == 0
    assert response.commit_eligible_count == 1
    assert response.card_dimension_missing_count == 1
    assert response.items[0].readiness_state == "compatibility_ready_family"
    assert response.items[0].compatibility_ready is True
    assert response.items[0].compatibility_ready_exact is False
    assert response.items[0].compatibility_ready_family is True
    assert "length_mm" in response.items[0].missing_exact_card_fields


def test_general_confirmed_spec_enrichment_dry_run_writes_nothing() -> None:
    driver = EnrichmentDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.enrich_staged_specs(
        ConfirmedSpecEnrichmentRequest(
            category="CPU",
            source_name="founder_confirmed_specs",
            license_note="manual confirmed CPU compatibility evidence",
            records=[
                {
                    "canonical_key": "CPU|AMD|RYZEN_7_7800X3D",
                    "specs": {"socket": "AM5", "cores": 8, "threads": 16, "tdp_w": 120},
                    "evidence_note": "confirmed CPU spec evidence",
                }
            ],
            dry_run=True,
        )
    )

    assert response.items[0].status == "would_enrich"
    assert response.enriched_records == 0
    assert not any("SET record.specs" in query for query in driver.queries)
    assert not any("CREATE (e:CanonicalEvidence)" in query for query in driver.queries)


def test_motherboard_confirmed_enrichment_requires_chipset() -> None:
    driver = MotherboardEnrichmentDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.enrich_staged_specs(
        ConfirmedSpecEnrichmentRequest(
            category="Motherboard",
            source_name="founder_confirmed_phase2_motherboard_specs",
            license_note="source-attributed AM5 motherboard compatibility evidence",
            records=[
                {
                    "canonical_key": "Motherboard|ASUS|ASUS_TUF_GAMING_B650_PLUS_WIFI",
                    "specs": {
                        "socket": "AM5",
                        "memory_type": "DDR5",
                        "form_factor": "ATX",
                        "m2_slots": 3,
                        "pcie_x16_slots": 2,
                    },
                    "evidence_note": "confirmed motherboard spec evidence",
                }
            ],
            dry_run=True,
        )
    )

    assert response.items[0].status == "skipped"
    assert "chipset" in response.items[0].missing_required_fields
    assert response.enriched_records == 0
    assert not any("SET record.specs" in query for query in driver.queries)
    assert not any("PriceSnapshot" in query or "RegionalPriceSnapshot" in query for query in driver.queries)


def test_motherboard_confirmed_enrichment_marks_exact_ready_without_price_mutation() -> None:
    driver = MotherboardEnrichmentDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.enrich_staged_specs(
        ConfirmedSpecEnrichmentRequest(
            category="Motherboard",
            source_name="founder_confirmed_phase2_motherboard_specs",
            license_note="source-attributed AM5 motherboard compatibility evidence",
            records=[
                {
                    "canonical_key": "Motherboard|ASUS|ASUS_TUF_GAMING_B650_PLUS_WIFI",
                    "specs": {
                        "chipset": "B650",
                        "socket": "AM5",
                        "memory_type": "DDR5",
                        "form_factor": "ATX",
                        "m2_slots": 3,
                        "pcie_x16_slots": 2,
                        "wifi": True,
                        "bios_flashback": True,
                    },
                    "evidence_note": "confirmed motherboard spec evidence",
                }
            ],
            dry_run=False,
        )
    )

    update_call = next(call for call in driver.calls if "record.compatibility_ready" in call["query"])
    assert response.enriched_records == 1
    assert response.evidence_created == 1
    assert response.items[0].status == "enriched"
    assert update_call["compatibility_ready"] is True
    assert update_call["compatibility_ready_exact"] is True
    assert update_call["readiness_state"] == "compatibility_ready_exact"
    assert update_call["missing_compatibility_fields"] == []
    assert not any("PriceSnapshot" in query or "RegionalPriceSnapshot" in query for query in driver.queries)


def test_gpu_family_enrichment_does_not_create_exact_card_readiness() -> None:
    driver = GPUFamilyEnrichmentDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.enrich_staged_specs(
        ConfirmedSpecEnrichmentRequest(
            category="GPU",
            source_name="founder_confirmed_gpu_family_specs",
            license_note="manual confirmed GPU family compatibility evidence",
            records=[
                {
                    "canonical_key": "GPU|AMD|RADEON_RX_7800_XT|POWERCOLOR_RX7800XT_16G_P",
                    "specs": {
                        "chip_family": "Radeon RX 7800 XT",
                        "vram_gb": 16,
                        "pcie_generation": "PCIe 4.0",
                        "reference_tdp_w": 263,
                    },
                    "evidence_note": "confirmed GPU family spec evidence",
                }
            ],
            dry_run=False,
        )
    )

    update_call = next(call for call in driver.calls if "record.compatibility_ready_family" in call["query"])
    assert response.enriched_records == 1
    assert response.items[0].status == "enriched"
    assert update_call["compatibility_ready"] is False
    assert update_call["compatibility_ready_exact"] is False
    assert update_call["compatibility_ready_family"] is True
    assert update_call["readiness_state"] == "compatibility_ready_family"
    assert "length_mm" in update_call["missing_exact_card_fields"]
    assert not any("SET snapshot" in query or "CREATE (snapshot" in query for query in driver.queries)


def test_current_gen_gpu_family_enrichment_matches_multiple_staged_cards_without_exact_readiness() -> None:
    driver = CurrentGenGPUFamilyEnrichmentDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.enrich_staged_specs(
        ConfirmedSpecEnrichmentRequest(
            category="GPU",
            source_name="founder_confirmed_phase2_specs",
            license_note="source-attributed current-generation GPU family evidence",
            records=[
                {
                    "canonical_key": "GPU|FAMILY|RTX_5070",
                    "specs": {
                        "chip_family": "RTX 5070",
                        "vram_gb": 12,
                        "pcie_generation": "PCIe 5.0",
                        "reference_tdp_w": 250,
                    },
                    "evidence_note": "confirmed RTX 5070 family evidence",
                }
            ],
            dry_run=False,
        )
    )

    update_calls = [call for call in driver.calls if "record.compatibility_ready_family" in call["query"]]
    assert response.matched_staged_records == 2
    assert response.enriched_records == 2
    assert {item.status for item in response.items} == {"enriched"}
    assert len(update_calls) == 2
    assert all(call["compatibility_ready"] is False for call in update_calls)
    assert all(call["compatibility_ready_exact"] is False for call in update_calls)
    assert all(call["compatibility_ready_family"] is True for call in update_calls)
    assert all("slots" in call["missing_exact_card_fields"] for call in update_calls)
    assert not any("PriceSnapshot" in query or "RegionalPriceSnapshot" in query for query in driver.queries)


def test_current_gen_gpu_family_enrichment_matches_chip_family_inside_staged_specs() -> None:
    driver = CurrentGenGPUFamilySpecOnlyEnrichmentDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.enrich_staged_specs(
        ConfirmedSpecEnrichmentRequest(
            category="GPU",
            source_name="founder_confirmed_phase2_specs",
            license_note="source-attributed current-generation GPU family evidence",
            records=[
                {
                    "canonical_key": "GPU|FAMILY|RTX_5090",
                    "specs": {
                        "chip_family": "RTX 5090",
                        "vram_gb": 32,
                        "pcie_generation": "PCIe 5.0",
                        "reference_tdp_w": 575,
                    },
                    "evidence_note": "confirmed RTX 5090 family evidence",
                }
            ],
            dry_run=True,
        )
    )

    assert response.matched_staged_records == 1
    assert response.items[0].canonical_key == "GPU|ASUS|ASUS_ROG_ASTRAL_OC"
    assert response.items[0].status == "would_enrich"
    family_query = next(call for call in driver.calls if "record.specs" in call["query"])
    assert "record.raw_name" not in family_query["query"]
    assert "record.normalized_name" not in family_query["query"]
    assert '"chip_family": "GeForce RTX 5090"' in family_query["spec_family_values"]
    assert not any("PriceSnapshot" in query or "RegionalPriceSnapshot" in query for query in driver.queries)


def test_phase2_current_gen_fixture_keeps_ambiguous_gpu_variants_out_of_family_enrichment() -> None:
    fixture = json.loads(Path("backend/data/canonical_specs/phase2_current_gen_specs.json").read_text())
    gpu_keys = {record["canonical_key"] for record in fixture["gpu_family_records"]}
    ambiguous_targets = {record["target_family"] for record in fixture["gpu_family_records_requiring_variant_split"]}
    cpu_keys = {record["canonical_key"] for record in fixture["cpu_records"]}

    assert "GPU|FAMILY|RTX_5070" in gpu_keys
    assert "GPU|FAMILY|RTX_5060_TI" not in gpu_keys
    assert "GPU|FAMILY|RX_9060_XT" not in gpu_keys
    assert ambiguous_targets == {"RTX 5060 Ti", "RX 9060 XT"}
    assert "CPU|AMD|RYZEN_7_9800X3D" in cpu_keys
    assert "CPU|INTEL|CORE_ULTRA_9_285K" in cpu_keys


def test_phase2_motherboard_fixture_has_required_confirmed_fields_only_for_narrow_am5_targets() -> None:
    fixture = json.loads(Path("backend/data/canonical_specs/phase2_motherboard_confirmed_specs.json").read_text())
    required = {"chipset", "socket", "memory_type", "form_factor", "m2_slots", "pcie_x16_slots"}
    records = fixture["motherboard_records"]

    assert 5 <= len(records) <= 10
    assert fixture["source_name"] == "founder_confirmed_phase2_motherboard_specs"
    for record in records:
        specs = record["specs"]
        assert record["canonical_key"].startswith("Motherboard|")
        assert required.issubset(specs)
        assert specs["socket"] == "AM5"
        assert specs["memory_type"] == "DDR5"
        assert specs["chipset"] in {"B650", "B650E", "X870", "X870E"}
        assert record["source_urls"]
        assert "price" not in specs


def test_market_evidence_link_dry_run_preserves_prices() -> None:
    driver = MarketLinkDriver()
    repository = Neo4jPricingRepository(driver)  # type: ignore[arg-type]

    response = repository.link_market_evidence(
        MarketEvidenceLinkRequest(category="CPU", region="SA", dry_run=True, limit=10)
    )

    assert response.items[0].status == "would_link"
    assert response.linked_count == 0
    assert response.price_mutation_count == 0
    assert not any("SET snapshot" in query or "CREATE (snapshot" in query for query in driver.queries)
