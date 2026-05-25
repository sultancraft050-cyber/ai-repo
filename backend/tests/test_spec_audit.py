from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.catalog import SpecAuditRunRequest


class FakeRecord(dict):
    def data(self) -> dict[str, Any]:
        return dict(self)


class SpecAuditDriver:
    def __init__(self, products: list[dict[str, Any]]) -> None:
        self.products = products
        self.queries: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.run_payload: str | None = None
        self.item_payloads: list[str] = []

    def execute_query(self, query: str, **kwargs: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        self.calls.append({"query": query, **kwargs})
        if "MATCH (s:PriceSnapshot)" in query:
            return [FakeRecord(count=11)], None, None
        if "MATCH (s:RegionalPriceSnapshot)" in query:
            return [FakeRecord(count=7)], None, None
        if "MATCH (p:Product:CanonicalProduct)" in query:
            return [
                FakeRecord(
                    product=row["product"],
                    category=row["category"],
                    evidence=row.get("evidence", []),
                )
                for row in self.products
            ], None, None
        if "MERGE (run:SpecAuditRun" in query:
            self.run_payload = str(kwargs["payload_json"])
            return [], None, None
        if "MERGE (item:SpecAuditItem" in query:
            self.item_payloads.append(str(kwargs["payload_json"]))
            return [], None, None
        if "MATCH (run:SpecAuditRun {audit_id:" in query and self.run_payload:
            return [FakeRecord(payload_json=self.run_payload)], None, None
        if "MATCH (run:SpecAuditRun)" in query:
            return [
                FakeRecord(audit_id="spec-audit:test", payload_json=payload)
                for payload in self.item_payloads
            ], None, None
        return [], None, None


def _request(category: str = "CPU") -> SpecAuditRunRequest:
    return SpecAuditRunRequest(
        region="SA",
        categories=[category],
        mode="preview",
        limit=50,
        source_policy="trusted_mixed",
    )


def _apply_request(category: str = "CPU") -> SpecAuditRunRequest:
    return SpecAuditRunRequest(
        region="SA",
        categories=[category],
        mode="apply_safe",
        limit=50,
        source_policy="trusted_mixed",
    )


def _evidence(field: str, value: Any, *, trust_score: float = 0.95) -> dict[str, Any]:
    return {
        "source_name": "trusted_fixture",
        "evidence_type": "canonical_spec",
        "field": field,
        "value_json": json.dumps(value),
        "trust_score": trust_score,
        "approval_state": "approved",
    }


def test_spec_audit_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        SpecAuditRunRequest(
            region="SA",
            categories=["CPU"],
            mode="delete_all",  # type: ignore[arg-type]
            limit=50,
            source_policy="trusted_mixed",
        )


def test_spec_audit_preview_writes_only_report_nodes_and_preserves_price_counts() -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "CPU",
                "product": {
                    "id": "cpu-1",
                    "canonical_key": "CPU|TEST|VERIFIED",
                    "name": "Verified CPU",
                    "category": "CPU",
                    "spec_socket": "AM5",
                    "spec_cores": 8,
                    "spec_threads": 16,
                    "spec_tdp_w": 120,
                },
                "evidence": [
                    _evidence("socket", "AM5"),
                    _evidence("cores", 8),
                    _evidence("threads", 16),
                    _evidence("tdp_w", 120),
                ],
            }
        ]
    )

    response = Neo4jPricingRepository(driver).run_spec_audit(_request())

    assert response.verified_count == 1
    assert response.price_snapshot_count.before == response.price_snapshot_count.after == 11
    assert response.regional_price_snapshot_count.before == response.regional_price_snapshot_count.after == 7
    write_queries = [query for query in driver.queries if "SET " in query or "CREATE " in query or "MERGE " in query]
    assert any("SpecAuditRun" in query for query in write_queries)
    assert any("SpecAuditItem" in query for query in write_queries)
    item_calls = [call for call in driver.calls if "MERGE (item:SpecAuditItem" in call["query"]]
    assert item_calls
    assert all(str(call["item_id"]).startswith("spec-audit-item:") for call in item_calls)
    assert all(len(str(call["item_id"])) <= 48 for call in item_calls)
    assert not any("CanonicalEvidence" in query and "SpecAudit" not in query for query in write_queries)
    assert not any("MERGE (p:Product:CanonicalProduct" in query for query in write_queries)
    assert not any("SET p += $properties" in query for query in write_queries)


def test_spec_audit_inferred_fields_do_not_count_as_confirmed() -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "CPU",
                "product": {
                    "id": "cpu-2",
                    "canonical_key": "CPU|TEST|INFERRED",
                    "name": "Inferred CPU",
                    "category": "CPU",
                    "spec_socket": "AM5",
                    "spec_cores": 8,
                    "spec_threads": 16,
                    "spec_tdp_w": 120,
                    "inferred_fields": [{"field": "socket"}],
                },
                "evidence": [
                    _evidence("socket", "AM5"),
                    _evidence("cores", 8),
                    _evidence("threads", 16),
                    _evidence("tdp_w", 120),
                ],
            }
        ]
    )

    response = Neo4jPricingRepository(driver).run_spec_audit(_request())

    assert response.product_actions[0].status == "missing_trusted_evidence"
    assert "socket" in response.product_actions[0].missing_fields
    assert "socket" in response.product_actions[0].inferred_fields


def test_spec_audit_gpu_family_evidence_does_not_satisfy_exact_card_fields() -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "GPU",
                "product": {
                    "id": "gpu-1",
                    "canonical_key": "GPU|TEST|RTX_5070|AIB_CARD",
                    "name": "AIB RTX 5070",
                    "category": "GPU",
                    "spec_chip_family": "RTX 5070",
                    "spec_vram_gb": 12,
                    "spec_pcie_generation": "PCIe 5.0",
                    "spec_reference_tdp_w": 250,
                },
                "evidence": [
                    _evidence(
                        "confirmed_gpu_family_specs",
                        {
                            "canonical_key": "GPU|FAMILY|RTX_5070",
                            "category": "GPU",
                            "specs": {
                                "chip_family": "RTX 5070",
                                "vram_gb": 12,
                                "pcie_generation": "PCIe 5.0",
                                "reference_tdp_w": 250,
                            },
                        },
                    )
                ],
            }
        ]
    )

    response = Neo4jPricingRepository(driver).run_spec_audit(_request("GPU"))

    assert response.product_actions[0].status == "missing_trusted_evidence"
    assert {"board_power_w", "length_mm", "slots", "power_connectors"}.issubset(
        set(response.product_actions[0].missing_fields)
    )


def test_spec_audit_reports_conflicting_trusted_evidence_without_overwrite() -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "CPU",
                "product": {
                    "id": "cpu-3",
                    "canonical_key": "CPU|TEST|CONFLICT",
                    "name": "Conflict CPU",
                    "category": "CPU",
                    "spec_socket": "AM5",
                    "spec_cores": 8,
                    "spec_threads": 16,
                    "spec_tdp_w": 120,
                },
                "evidence": [
                    _evidence("socket", "AM5"),
                    _evidence("cores", 6),
                    _evidence("threads", 16),
                    _evidence("tdp_w", 120),
                ],
            }
        ]
    )

    response = Neo4jPricingRepository(driver).run_spec_audit(_request())

    assert response.conflict_count == 1
    assert response.product_actions[0].status == "spec_conflict_requires_review"
    assert response.product_actions[0].conflicting_fields == ["cores"]
    assert not any("SET p." in query for query in driver.queries)
    assert not any("spec_audit_conflict" in str(call) for call in driver.calls)


def test_spec_audit_apply_safe_updates_missing_confirmed_fields_and_creates_evidence() -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "CPU",
                "product": {
                    "id": "cpu-apply",
                    "canonical_key": "CPU|TEST|SAFE_FIX",
                    "name": "Safe Fix CPU",
                    "category": "CPU",
                    "spec_cores": 8,
                    "spec_threads": 16,
                    "spec_tdp_w": 120,
                },
                "evidence": [
                    _evidence("socket", "AM5"),
                    _evidence("cores", 8),
                    _evidence("threads", 16),
                    _evidence("tdp_w", 120),
                ],
            }
        ]
    )

    response = Neo4jPricingRepository(driver).run_spec_audit(_apply_request())

    assert response.safe_fixes_applied_count == 1
    assert response.safe_fixes_available_count == 0
    assert response.verified_count == 1
    assert response.product_actions[0].safe_fix_applied_fields == ["socket"]
    assert response.price_snapshot_count.before == response.price_snapshot_count.after == 11
    assert response.regional_price_snapshot_count.before == response.regional_price_snapshot_count.after == 7
    product_update = next(call for call in driver.calls if "SET p += $properties" in call["query"])
    assert product_update["properties"]["spec_socket"] == "AM5"
    assert product_update["properties"]["compatibility_ready"] is True
    evidence_calls = [call for call in driver.calls if call.get("field") == "socket"]
    assert evidence_calls
    assert evidence_calls[-1]["approval_state"] == "approved"
    assert not any("SET snapshot" in query or "CREATE (snapshot" in query for query in driver.queries)


def test_spec_audit_apply_safe_creates_founder_review_for_conflicts_without_overwrite() -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "CPU",
                "product": {
                    "id": "cpu-conflict",
                    "canonical_key": "CPU|TEST|CONFLICT",
                    "name": "Conflict CPU",
                    "category": "CPU",
                    "spec_socket": "AM5",
                    "spec_cores": 8,
                    "spec_threads": 16,
                    "spec_tdp_w": 120,
                },
                "evidence": [
                    _evidence("socket", "AM5"),
                    _evidence("cores", 6),
                    _evidence("threads", 16),
                    _evidence("tdp_w", 120),
                ],
            }
        ]
    )

    response = Neo4jPricingRepository(driver).run_spec_audit(_apply_request())

    assert response.conflict_count == 1
    assert response.conflict_reviews_created_count == 1
    assert response.safe_fixes_applied_count == 0
    assert response.product_actions[0].status == "spec_conflict_requires_review"
    assert not any("SET p += $properties" in query for query in driver.queries)
    review_calls = [call for call in driver.calls if call.get("field") == "spec_audit_conflict"]
    assert review_calls
    assert review_calls[-1]["approval_state"] == "pending_review"
    assert not any("SET snapshot" in query or "CREATE (snapshot" in query for query in driver.queries)


def test_spec_audit_conflicting_trusted_sources_are_not_safe_fixes() -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "CPU",
                "product": {
                    "id": "cpu-source-conflict",
                    "canonical_key": "CPU|TEST|SOURCE_CONFLICT",
                    "name": "Source Conflict CPU",
                    "category": "CPU",
                    "spec_cores": 8,
                    "spec_threads": 16,
                    "spec_tdp_w": 120,
                },
                "evidence": [
                    _evidence("socket", "AM5"),
                    _evidence("socket", "AM4"),
                    _evidence("cores", 8),
                    _evidence("threads", 16),
                    _evidence("tdp_w", 120),
                ],
            }
        ]
    )

    response = Neo4jPricingRepository(driver).run_spec_audit(_apply_request())

    assert response.conflict_count == 1
    assert response.safe_fixes_applied_count == 0
    assert response.product_actions[0].conflicting_fields == ["socket"]
    assert not any("SET p += $properties" in query for query in driver.queries)


def test_spec_audit_reports_missing_trusted_evidence_for_unbacked_specs() -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "RAM",
                "product": {
                    "id": "ram-1",
                    "canonical_key": "RAM|TEST|UNBACKED",
                    "name": "Unbacked DDR5 Kit",
                    "category": "RAM",
                    "spec_memory_type": "DDR5",
                    "spec_capacity_gb": 32,
                    "spec_speed_mhz": 6000,
                    "spec_kit_config": "2x16GB",
                },
                "evidence": [],
            }
        ]
    )

    response = Neo4jPricingRepository(driver).run_spec_audit(_request("RAM"))

    assert response.missing_evidence_count == 1
    assert response.product_actions[0].status == "missing_trusted_evidence"
    assert set(response.product_actions[0].missing_fields) == {
        "memory_type",
        "capacity_gb",
        "speed_mhz",
        "kit_config",
    }


def test_spec_audit_preview_isolates_unparseable_product_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = SpecAuditDriver(
        [
            {
                "category": "PSU",
                "product": {
                    "id": "psu-1",
                    "canonical_key": "PSU|TEST|ODD",
                    "name": "Odd PSU",
                    "category": "PSU",
                },
                "evidence": [],
            }
        ]
    )

    def raise_for_product(*args: Any, **kwargs: Any) -> None:
        raise TypeError("unexpected live row shape")

    monkeypatch.setattr(Neo4jPricingRepository, "_spec_audit_action", raise_for_product)

    response = Neo4jPricingRepository(driver).run_spec_audit(_request("PSU"))

    assert response.audited_product_count == 1
    assert response.missing_evidence_count == 1
    assert response.product_actions[0].status == "missing_trusted_evidence"
    assert set(response.product_actions[0].missing_fields) == {"wattage_w", "efficiency_rating", "modularity"}
