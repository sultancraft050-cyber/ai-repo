from __future__ import annotations

from typing import Any

import pytest

from app.graph.ops_repository import Neo4jOpsRepository
from app.models.ops import Neo4jPruneExecuteRequest, Neo4jPrunePreviewRequest


class FakeRecord(dict):
    def data(self) -> dict[str, Any]:
        return dict(self)


class CapacityFakeDriver:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.deleted_batches = [2, 0]

    def execute_query(self, query: str, **kwargs: Any) -> tuple[list[FakeRecord], None, None]:
        self.queries.append(query)
        compact = " ".join(query.split())
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
