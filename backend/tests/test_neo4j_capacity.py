from __future__ import annotations

from typing import Any

import pytest

from app.graph.ops_repository import Neo4jOpsRepository
from app.models.ops import (
    Neo4jPruneExecuteRequest,
    Neo4jPrunePreviewRequest,
    RegionalPriceSnapshotLabelExecuteRequest,
)


class FakeRecord(dict):
    def data(self) -> dict[str, Any]:
        return dict(self)


class CapacityFakeDriver:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.deleted_batches = [2, 0]
        self.regional_label_candidates = 3

    def execute_query(self, query: str, **kwargs: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        compact = " ".join(query.split())
        if "RETURN count(snapshot) AS price_snapshot_count" in query:
            return [
                FakeRecord(
                    price_snapshot_count=36,
                    price_checksum=100.0,
                    item_price_sar_checksum=200.0,
                    final_landed_price_sar_checksum=300.0,
                )
            ], None, None
        if "RETURN count(snapshot) AS would_label_count" in query:
            return [
                FakeRecord(
                    would_label_count=self.regional_label_candidates,
                    sample_snapshot_ids=["price:1", "price:2"],
                    regions=["SA"],
                    currencies=["SAR"],
                )
            ], None, None
        if "SET snapshot:RegionalPriceSnapshot" in query:
            labeled = self.regional_label_candidates
            self.regional_label_candidates = 0
            return [FakeRecord(labeled_count=labeled)], None, None
        if "RETURN count(snapshot) AS remaining_unlabeled_count" in query:
            return [FakeRecord(remaining_unlabeled_count=self.regional_label_candidates)], None, None
        if compact == "MATCH (n) RETURN count(n) AS count":
            return [FakeRecord(count=200000)], None, None
        if compact == "MATCH ()-[r]->() RETURN count(r) AS count":
            return [FakeRecord(count=350000)], None, None
        if "UNWIND labels(n) AS name" in query and "RETURN name, count(*) AS count" in query:
            return [
                FakeRecord(name="Product", count=90000),
                FakeRecord(name="AnalyticsEvent", count=50000),
                FakeRecord(name="StagedCanonicalRecord", count=1200),
            ], None, None
        if "RETURN type(r) AS name" in query:
            return [FakeRecord(name="HAS_PRICE", count=70000)], None, None
        if "RETURN size(nodes) AS node_count" in query:
            return [
                FakeRecord(
                    node_count=1200,
                    relationship_count=1400,
                    sample_node_ids=["staged:1", "staged:2"],
                )
            ], None, None
        if "WITH name, n" in query and "RETURN name, count(DISTINCT n) AS count" in query:
            return [FakeRecord(name="StagedCanonicalRecord", count=1200)], None, None
        if "any(label IN labels(n) WHERE label IN $requested_labels)" in query:
            return [FakeRecord(count=3)], None, None
        if "FOREACH (node IN nodes | DETACH DELETE node)" in query:
            return [FakeRecord(deleted=self.deleted_batches.pop(0))], None, None
        if "MATCH (n:FieldEvidence)" in query:
            return [FakeRecord(count=4, sample_node_ids=["evidence:1"])], None, None
        if "MATCH (n:PriceSnapshot)" in query:
            return [FakeRecord(count=1, sample_node_ids=["snapshot:1"])], None, None
        if "MATCH (n:ProductURL)" in query:
            return [FakeRecord(count=2, sample_node_ids=["url:1"])], None, None
        if "MATCH (n:StagedCanonicalRecord)" in query:
            return [FakeRecord(count=8, sample_node_ids=["staged:old"])], None, None
        return [], None, None


def test_capacity_report_counts_labels_and_detects_hard_blocker() -> None:
    repository = Neo4jOpsRepository(CapacityFakeDriver())  # type: ignore[arg-type]

    report = repository.neo4j_capacity_report()

    assert report.total_node_count == 200000
    assert report.over_limit
    assert report.hard_blocker
    assert report.largest_labels[0].name == "Product"
    assert "Product" in report.production_critical_labels
    assert "StagedCanonicalRecord" in report.estimated_safe_to_prune_labels


def test_prune_preview_does_not_delete_and_excludes_protected_labels() -> None:
    driver = CapacityFakeDriver()
    repository = Neo4jOpsRepository(driver)  # type: ignore[arg-type]

    preview = repository.neo4j_prune_preview(
        Neo4jPrunePreviewRequest(
            include_labels=["Product", "StagedCanonicalRecord"],
            retention_days=7,
            dry_run=True,
        )
    )

    assert preview.would_delete_node_count == 1200
    assert preview.approval_required
    assert preview.protected_nodes_skipped == 3
    assert any("Protected label skipped: Product" in warning for warning in preview.safety_warnings)
    assert not any("DETACH DELETE" in query for query in driver.queries)


def test_prune_execute_requires_approval_and_uses_signed_preview_scope() -> None:
    driver = CapacityFakeDriver()
    repository = Neo4jOpsRepository(driver)  # type: ignore[arg-type]
    preview = repository.neo4j_prune_preview(
        Neo4jPrunePreviewRequest(include_labels=["StagedCanonicalRecord"], retention_days=7)
    )

    response = repository.neo4j_prune_execute(
        Neo4jPruneExecuteRequest(preview_id=preview.preview_id, approved=True)
    )

    assert response.deleted_node_count == 2
    assert response.status == "completed"
    assert any("FOREACH (node IN nodes | DETACH DELETE node)" in query for query in driver.queries)


def test_prune_execute_rejects_unapproved_request() -> None:
    repository = Neo4jOpsRepository(CapacityFakeDriver())  # type: ignore[arg-type]
    preview = repository.neo4j_prune_preview(
        Neo4jPrunePreviewRequest(include_labels=["StagedCanonicalRecord"], retention_days=7)
    )

    with pytest.raises(ValueError):
        repository.neo4j_prune_execute(Neo4jPruneExecuteRequest(preview_id=preview.preview_id, approved=False))


def test_orphan_detection_reports_without_deleting() -> None:
    driver = CapacityFakeDriver()
    repository = Neo4jOpsRepository(driver)  # type: ignore[arg-type]

    response = repository.neo4j_orphans()

    assert {finding.kind for finding in response.findings} >= {"orphan_field_evidence", "orphan_price_snapshot"}
    assert not any("DETACH DELETE" in query for query in driver.queries)


def test_regional_price_snapshot_label_preview_does_not_mutate_prices() -> None:
    driver = CapacityFakeDriver()
    repository = Neo4jOpsRepository(driver)  # type: ignore[arg-type]

    preview = repository.regional_price_snapshot_label_preview()

    assert preview.dry_run
    assert preview.would_label_count == 3
    assert preview.price_snapshot_count == 36
    assert preview.price_checksum == 100.0
    assert preview.safe_to_execute
    assert not any("SET snapshot:RegionalPriceSnapshot" in query for query in driver.queries)


def test_regional_price_snapshot_label_execute_requires_approval() -> None:
    repository = Neo4jOpsRepository(CapacityFakeDriver())  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        repository.regional_price_snapshot_label_execute(RegionalPriceSnapshotLabelExecuteRequest(approved=False))


def test_regional_price_snapshot_label_execute_only_adds_label_and_preserves_checksums() -> None:
    driver = CapacityFakeDriver()
    repository = Neo4jOpsRepository(driver)  # type: ignore[arg-type]
    preview = repository.regional_price_snapshot_label_preview()

    response = repository.regional_price_snapshot_label_execute(
        RegionalPriceSnapshotLabelExecuteRequest(approved=True, preview_count=preview.would_label_count)
    )

    assert response.labeled_count == 3
    assert response.remaining_unlabeled_count == 0
    assert response.price_snapshot_count_before == response.price_snapshot_count_after
    assert response.price_checksum_before == response.price_checksum_after
    assert response.item_price_sar_checksum_before == response.item_price_sar_checksum_after
    assert response.final_landed_price_sar_checksum_before == response.final_landed_price_sar_checksum_after
    assert response.price_values_unchanged
    assert any("SET snapshot:RegionalPriceSnapshot" in query for query in driver.queries)
