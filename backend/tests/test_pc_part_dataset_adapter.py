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


def test_gpu_requires_confirmed_power_length_and_pcie_for_compatibility_ready() -> None:
    record = adapt_pc_part_dataset_record(
        {"name": "MSI GeForce RTX 4070 Super", "chipset": "GeForce RTX 4070 SUPER", "memory": 12, "length": 261},
        "GPU",
    )

    assert record["compatibility_ready"] is False
    assert "tdp_w" in record["missing_compatibility_fields"]
    assert "pcie_generation" in record["missing_compatibility_fields"]


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
    assert any(item.reason == "outside curated phase2 target manifest" for item in response.top_rejection_reasons)
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
