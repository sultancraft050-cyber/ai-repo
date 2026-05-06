from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.models.alignment import AlignmentInspectionReport, SystemIdentity


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


class Neo4jAlignmentRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT system_identity_id IF NOT EXISTS "
            "FOR (n:SystemIdentity) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognitive_constitution_id IF NOT EXISTS "
            "FOR (n:CognitiveConstitution) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT alignment_report_id IF NOT EXISTS "
            "FOR (n:AlignmentReport) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT alignment_violation_id IF NOT EXISTS "
            "FOR (n:AlignmentViolation) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT objective_tradeoff_id IF NOT EXISTS "
            "FOR (n:ObjectiveTradeoff) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT ethics_assessment_id IF NOT EXISTS "
            "FOR (n:EthicsAssessment) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT alignment_audit_id IF NOT EXISTS "
            "FOR (n:AlignmentAuditEvent) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT alignment_rollback_id IF NOT EXISTS "
            "FOR (n:AlignmentRollbackEvent) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX alignment_product_status IF NOT EXISTS "
            "FOR (n:AlignmentReport) ON (n.product_id, n.status)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def upsert_identity(self, identity: SystemIdentity) -> None:
        identity_props = _clean_properties(
            {
                "id": identity.id,
                "version": identity.version,
                "purpose": identity.purpose,
                "created_at": identity.created_at,
                "payload_json": identity.model_dump_json(),
            }
        )
        constitution = identity.constitution
        constitution_props = _clean_properties(
            {
                "id": constitution.id,
                "version": constitution.version,
                "immutable": constitution.immutable,
                "non_overridable_constraints": constitution.non_overridable_constraints,
                "protected_governance_rules": constitution.protected_governance_rules,
                "safety_principles": constitution.safety_principles,
                "created_at": constitution.created_at,
                "payload_json": constitution.model_dump_json(),
            }
        )
        objectives = [
            _clean_properties(
                {
                    "id": f"objective:{objective.rank}:{objective.name}",
                    "name": objective.name,
                    "rank": objective.rank,
                    "weight": objective.weight,
                    "description": objective.description,
                    "protected": objective.protected,
                    "payload_json": objective.model_dump_json(),
                }
            )
            for objective in identity.optimization_priorities
        ]
        self.driver.execute_query(
            """
            MERGE (identity:SystemIdentity {id: $identity.id})
            SET identity += $identity
            MERGE (constitution:CognitiveConstitution {id: $constitution.id})
            SET constitution += $constitution
            MERGE (identity)-[:PROTECTED_BY]->(constitution)
            WITH identity
            UNWIND $objectives AS row
            MERGE (objective:ObjectivePriority {id: row.id})
            SET objective += row
            MERGE (identity)-[:HAS_OBJECTIVE]->(objective)
            """,
            identity=identity_props,
            constitution=constitution_props,
            objectives=objectives,
            database_=settings.neo4j_database,
        )

    def latest_identity(self) -> SystemIdentity | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (identity:SystemIdentity)
            RETURN identity.payload_json AS payload_json
            ORDER BY identity.created_at DESC
            LIMIT 1
            """,
            database_=settings.neo4j_database,
        )
        return SystemIdentity.model_validate_json(records[0]["payload_json"]) if records else None

    def upsert_report(self, report: AlignmentInspectionReport) -> None:
        self.upsert_identity(report.identity)
        report_id = f"alignment:{report.product_id}"
        props = _clean_properties(
            {
                "id": report_id,
                "product_id": report.product_id,
                "generated_at": report.generated_at,
                "status": report.status,
                "identity_id": report.identity.id,
                "overall_alignment": report.health.overall_alignment,
                "identity_stability": report.health.identity_stability,
                "objective_coherence": report.health.objective_coherence,
                "confidence_integrity": report.health.confidence_integrity,
                "safety_priority_score": report.health.safety_priority_score,
                "violation_count": len(report.violations),
                "ethics_passed": report.ethics.ethics_passed,
                "payload_json": report.model_dump_json(),
            }
        )
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MATCH (identity:SystemIdentity {id: $identity_id})
            MERGE (report:AlignmentReport {id: $report.id})
            SET report += $report
            MERGE (p)-[:HAS_ALIGNMENT_REPORT]->(report)
            MERGE (report)-[:ASSERTS_IDENTITY]->(identity)
            SET p.alignment_status = $report.status,
                p.alignment_health_score = $report.overall_alignment,
                p.alignment_updated_at = datetime()
            """,
            product_id=report.product_id,
            identity_id=report.identity.id,
            report=props,
            database_=settings.neo4j_database,
        )
        self._upsert_children(report, report_id)

    def latest_report(self, product_id: str) -> AlignmentInspectionReport | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_ALIGNMENT_REPORT]->(report:AlignmentReport)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN report.payload_json AS payload_json
            ORDER BY report.generated_at DESC
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return AlignmentInspectionReport.model_validate_json(records[0]["payload_json"]) if records else None

    def _upsert_children(self, report: AlignmentInspectionReport, report_id: str) -> None:
        ethics_row = _clean_properties(
            {
                "id": f"ethics:{report.product_id}",
                "product_id": report.product_id,
                "misleading_confidence_risk": report.ethics.misleading_confidence_risk,
                "unsafe_recommendation_risk": report.ethics.unsafe_recommendation_risk,
                "unstable_configuration_risk": report.ethics.unstable_configuration_risk,
                "biased_optimization_risk": report.ethics.biased_optimization_risk,
                "ethics_passed": report.ethics.ethics_passed,
                "payload_json": report.ethics.model_dump_json(),
            }
        )
        child_sets = [
            ("ObjectiveTradeoff", "HAS_OBJECTIVE_TRADEOFF", [item.model_dump(mode="json") for item in report.tradeoffs]),
            ("AlignmentViolation", "HAS_ALIGNMENT_VIOLATION", [item.model_dump(mode="json") for item in report.violations]),
            ("AlignmentRollbackEvent", "HAS_ALIGNMENT_ROLLBACK", [item.model_dump(mode="json") for item in report.rollback]),
            ("AlignmentAuditEvent", "HAS_ALIGNMENT_AUDIT", [item.model_dump(mode="json") for item in report.audit_trail]),
        ]
        self.driver.execute_query(
            """
            MATCH (report:AlignmentReport {id: $report_id})
            MERGE (ethics:EthicsAssessment {id: $ethics.id})
            SET ethics += $ethics
            MERGE (report)-[:HAS_ETHICS_ASSESSMENT]->(ethics)
            """,
            report_id=report_id,
            ethics=ethics_row,
            database_=settings.neo4j_database,
        )
        for label, relationship, raw_rows in child_sets:
            rows = [
                _clean_properties(
                    {
                        **row,
                        "product_id": report.product_id,
                        "payload_json": json.dumps(row, sort_keys=True, default=_json_default),
                    }
                )
                for row in raw_rows
            ]
            if not rows:
                continue
            query = f"""
            UNWIND $rows AS row
            MATCH (report:AlignmentReport {{id: $report_id}})
            MERGE (child:{label} {{id: row.id}})
            SET child += row
            MERGE (report)-[:{relationship}]->(child)
            """
            self.driver.execute_query(query, rows=rows, report_id=report_id, database_=settings.neo4j_database)
