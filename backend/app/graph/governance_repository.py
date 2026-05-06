from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.models.governance import ReasoningGovernanceReport


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _clean_properties(values: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool, datetime)):
            clean[key] = value
        elif isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
            clean[key] = value
        else:
            clean[key] = json.dumps(value, sort_keys=True, default=_json_default)
    return clean


class Neo4jGovernanceRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT reasoning_governance_id IF NOT EXISTS "
            "FOR (n:ReasoningGovernance) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT governance_signal_id IF NOT EXISTS "
            "FOR (n:GovernanceSignal) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT governance_action_id IF NOT EXISTS "
            "FOR (n:StabilizationAction) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT evidence_decay_id IF NOT EXISTS "
            "FOR (n:EvidenceDecay) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX governance_product_status IF NOT EXISTS "
            "FOR (n:ReasoningGovernance) ON (n.product_id, n.status)",
            "CREATE INDEX governance_generated_at IF NOT EXISTS "
            "FOR (n:ReasoningGovernance) ON (n.generated_at)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def upsert_report(self, report: ReasoningGovernanceReport) -> None:
        report_props = _clean_properties(
            {
                "id": f"governance:{report.product_id}",
                "product_id": report.product_id,
                "generated_at": report.generated_at,
                "status": report.status,
                "overall_health": report.metrics.overall_health,
                "reasoning_quality": report.metrics.reasoning_quality,
                "confidence_drift": report.metrics.confidence_drift,
                "contradiction_density": report.metrics.contradiction_density,
                "recursive_feedback_risk": report.metrics.recursive_feedback_risk,
                "governed_confidence": report.stability.governed_confidence,
                "original_confidence": report.stability.original_confidence,
                "revalidation_required": report.stability.revalidation_required,
                "payload_json": report.model_dump_json(),
            }
        )
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MERGE (report:ReasoningGovernance {id: $report.id})
            SET report += $report
            MERGE (p)-[:HAS_REASONING_GOVERNANCE]->(report)
            SET p.reasoning_health_score = $report.overall_health,
                p.governed_confidence_score = $report.governed_confidence,
                p.reasoning_governance_status = $report.status,
                p.reasoning_governance_updated_at = datetime()
            """,
            product_id=report.product_id,
            report=report_props,
            database_=settings.neo4j_database,
        )
        self._upsert_evidence_decay(report)
        self._upsert_signals(report)
        self._upsert_actions(report)

    def latest_report(self, product_id: str) -> ReasoningGovernanceReport | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_REASONING_GOVERNANCE]->(report:ReasoningGovernance)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN report.payload_json AS payload_json
            ORDER BY report.generated_at DESC
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return ReasoningGovernanceReport.model_validate_json(records[0]["payload_json"]) if records else None

    def _upsert_evidence_decay(self, report: ReasoningGovernanceReport) -> None:
        rows = [
            _clean_properties(
                {
                    "id": record.id,
                    "product_id": report.product_id,
                    "source": record.source,
                    "age_days": record.age_days,
                    "original_weight": record.original_weight,
                    "decayed_weight": record.decayed_weight,
                    "validation_support": record.validation_support,
                    "statistical_stability": record.statistical_stability,
                    "status": record.status,
                    "reason": record.reason,
                    "payload_json": record.model_dump_json(),
                }
            )
            for record in report.evidence_decay
        ]
        if not rows:
            return
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (report:ReasoningGovernance {id: $report_id})
            MERGE (decay:EvidenceDecay {id: row.id})
            SET decay += row
            MERGE (report)-[:APPLIES_EVIDENCE_DECAY]->(decay)
            WITH decay, row
            MERGE (evidence:CognitionEvidence {id: "evidence:" + row.source})
            SET evidence.source = row.source,
                evidence.governance_status = row.status,
                evidence.decayed_weight = row.decayed_weight,
                evidence.updated_at = datetime()
            MERGE (decay)-[:GOVERNS_EVIDENCE]->(evidence)
            """,
            rows=rows,
            report_id=f"governance:{report.product_id}",
            database_=settings.neo4j_database,
        )

    def _upsert_signals(self, report: ReasoningGovernanceReport) -> None:
        rows = [
            _clean_properties(
                {
                    "id": signal.id,
                    "product_id": report.product_id,
                    "kind": signal.kind,
                    "severity": signal.severity,
                    "confidence_score": signal.confidence_score,
                    "affected_nodes": signal.affected_nodes,
                    "explanation": signal.explanation,
                    "mitigation": signal.mitigation,
                    "detected_at": signal.detected_at,
                    "payload_json": signal.model_dump_json(),
                }
            )
            for signal in report.graph_hygiene
        ]
        if not rows:
            return
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (report:ReasoningGovernance {id: $report_id})
            MERGE (signal:GovernanceSignal {id: row.id})
            SET signal += row
            MERGE (report)-[:RAISES_GOVERNANCE_SIGNAL]->(signal)
            WITH signal, row
            UNWIND coalesce(row.affected_nodes, []) AS affected
            MERGE (node:GovernanceTarget {id: affected})
            MERGE (signal)-[:AFFECTS]->(node)
            """,
            rows=rows,
            report_id=f"governance:{report.product_id}",
            database_=settings.neo4j_database,
        )

    def _upsert_actions(self, report: ReasoningGovernanceReport) -> None:
        rows = [
            _clean_properties(
                {
                    "id": action.id,
                    "product_id": report.product_id,
                    "kind": action.kind,
                    "severity": action.severity,
                    "status": action.status,
                    "target": action.target,
                    "reason": action.reason,
                    "created_at": action.created_at,
                    "payload_json": action.model_dump_json(),
                }
            )
            for action in report.stabilization_actions
        ]
        if not rows:
            return
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (report:ReasoningGovernance {id: $report_id})
            MERGE (action:StabilizationAction {id: row.id})
            SET action += row
            MERGE (report)-[:RECOMMENDS_STABILIZATION]->(action)
            """,
            rows=rows,
            report_id=f"governance:{report.product_id}",
            database_=settings.neo4j_database,
        )
