from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.models.evolution import CognitivePolicy, EvolutionOrchestrationReport, RollbackEvent


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


class Neo4jEvolutionRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT cognitive_policy_id IF NOT EXISTS "
            "FOR (n:CognitivePolicy) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT evolution_report_id IF NOT EXISTS "
            "FOR (n:EvolutionOrchestration) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT policy_enforcement_id IF NOT EXISTS "
            "FOR (n:PolicyEnforcement) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT sandbox_evaluation_id IF NOT EXISTS "
            "FOR (n:SandboxEvaluation) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT promotion_decision_id IF NOT EXISTS "
            "FOR (n:PromotionDecision) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT rollback_event_id IF NOT EXISTS "
            "FOR (n:RollbackEvent) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT memory_decision_id IF NOT EXISTS "
            "FOR (n:MemoryDecision) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT evolution_audit_id IF NOT EXISTS "
            "FOR (n:EvolutionAuditEvent) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX active_policy_scope IF NOT EXISTS "
            "FOR (n:CognitivePolicy) ON (n.scope, n.status)",
            "CREATE INDEX evolution_product_status IF NOT EXISTS "
            "FOR (n:EvolutionOrchestration) ON (n.product_id, n.status)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def upsert_policy(self, policy: CognitivePolicy) -> None:
        props = _clean_properties(
            {
                "id": policy.id,
                "version": policy.version,
                "status": policy.status,
                "scope": policy.scope,
                "confidence_ceiling_max": policy.confidence_ceiling_max,
                "evidence_freshness_min": policy.evidence_freshness_min,
                "contradiction_tolerance": policy.contradiction_tolerance,
                "anomaly_escalation_threshold": policy.anomaly_escalation_threshold,
                "adaptation_rate_limit": policy.adaptation_rate_limit,
                "recommendation_aggressiveness": policy.recommendation_aggressiveness,
                "self_generated_trust_cap": policy.self_generated_trust_cap,
                "telemetry_trust_growth_rate": policy.telemetry_trust_growth_rate,
                "policy_drift_limit": policy.policy_drift_limit,
                "requires_human_approval": policy.requires_human_approval,
                "created_by": policy.created_by,
                "change_reason": policy.change_reason,
                "supersedes_policy_id": policy.supersedes_policy_id,
                "created_at": policy.created_at,
                "payload_json": policy.model_dump_json(),
            }
        )
        self.driver.execute_query(
            """
            MERGE (policy:CognitivePolicy {id: $policy.id})
            SET policy += $policy
            WITH policy
            OPTIONAL MATCH (previous:CognitivePolicy {id: $supersedes_policy_id})
            FOREACH (_ IN CASE WHEN previous IS NULL THEN [] ELSE [1] END |
              MERGE (policy)-[:SUPERSEDES]->(previous)
            )
            """,
            policy=props,
            supersedes_policy_id=policy.supersedes_policy_id,
            database_=settings.neo4j_database,
        )

    def active_policy(self, scope: str = "global") -> CognitivePolicy | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (policy:CognitivePolicy {scope: $scope, status: "active"})
            RETURN policy.payload_json AS payload_json
            ORDER BY policy.created_at DESC
            LIMIT 1
            """,
            scope=scope,
            database_=settings.neo4j_database,
        )
        return CognitivePolicy.model_validate_json(records[0]["payload_json"]) if records else None

    def upsert_report(self, report: EvolutionOrchestrationReport) -> None:
        self.upsert_policy(report.active_policy)
        report_id = f"evolution:{report.product_id}"
        props = _clean_properties(
            {
                "id": report_id,
                "product_id": report.product_id,
                "generated_at": report.generated_at,
                "status": report.status,
                "policy_id": report.active_policy.id,
                "health_index": report.health_index.index,
                "evolution_velocity": report.metrics.evolution_velocity,
                "policy_drift": report.metrics.policy_drift,
                "adaptation_pressure": report.metrics.adaptation_pressure,
                "confidence_volatility": report.metrics.confidence_volatility,
                "payload_json": report.model_dump_json(),
            }
        )
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MATCH (policy:CognitivePolicy {id: $policy_id})
            MERGE (report:EvolutionOrchestration {id: $report.id})
            SET report += $report
            MERGE (p)-[:HAS_EVOLUTION_ORCHESTRATION]->(report)
            MERGE (report)-[:ENFORCES_POLICY]->(policy)
            SET p.cognitive_health_index = $report.health_index,
                p.evolution_velocity = $report.evolution_velocity,
                p.cognitive_policy_id = $policy_id,
                p.evolution_orchestration_status = $report.status,
                p.evolution_orchestration_updated_at = datetime()
            """,
            product_id=report.product_id,
            policy_id=report.active_policy.id,
            report=props,
            database_=settings.neo4j_database,
        )
        self._upsert_children(report, report_id)

    def latest_report(self, product_id: str) -> EvolutionOrchestrationReport | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_EVOLUTION_ORCHESTRATION]->(report:EvolutionOrchestration)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN report.payload_json AS payload_json
            ORDER BY report.generated_at DESC
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return EvolutionOrchestrationReport.model_validate_json(records[0]["payload_json"]) if records else None

    def record_rollback(self, event: RollbackEvent) -> None:
        props = _clean_properties(
            {
                "id": event.id,
                "status": event.status,
                "from_policy_id": event.from_policy_id,
                "to_policy_id": event.to_policy_id,
                "trigger": event.trigger,
                "reason": event.reason,
                "created_at": event.created_at,
                "payload_json": event.model_dump_json(),
            }
        )
        self.driver.execute_query(
            """
            MERGE (event:RollbackEvent {id: $event.id})
            SET event += $event
            WITH event
            OPTIONAL MATCH (from_policy:CognitivePolicy {id: $from_policy_id})
            OPTIONAL MATCH (to_policy:CognitivePolicy {id: $to_policy_id})
            FOREACH (_ IN CASE WHEN from_policy IS NULL THEN [] ELSE [1] END |
              MERGE (event)-[:ROLLS_BACK_FROM]->(from_policy)
            )
            FOREACH (_ IN CASE WHEN to_policy IS NULL THEN [] ELSE [1] END |
              MERGE (event)-[:ROLLS_BACK_TO]->(to_policy)
            )
            """,
            event=props,
            from_policy_id=event.from_policy_id,
            to_policy_id=event.to_policy_id,
            database_=settings.neo4j_database,
        )

    def _upsert_children(self, report: EvolutionOrchestrationReport, report_id: str) -> None:
        child_sets = [
            ("PolicyEnforcement", "HAS_POLICY_ENFORCEMENT", [item.model_dump(mode="json") for item in report.enforcement]),
            ("SandboxEvaluation", "HAS_SANDBOX_EVALUATION", [item.model_dump(mode="json") for item in report.sandbox_evaluations]),
            ("PromotionDecision", "HAS_PROMOTION_DECISION", [item.model_dump(mode="json") for item in report.promotion_decisions]),
            ("RollbackEvent", "HAS_ROLLBACK_EVENT", [item.model_dump(mode="json") for item in report.rollback_events]),
            ("MemoryDecision", "HAS_MEMORY_DECISION", [item.model_dump(mode="json") for item in report.memory_decisions]),
            ("EvolutionAuditEvent", "HAS_EVOLUTION_AUDIT", [item.model_dump(mode="json") for item in report.audit_trail]),
        ]
        for label, relationship, raw_rows in child_sets:
            rows = [
                _clean_properties(
                    {
                        **row,
                        "payload_json": json.dumps(row, sort_keys=True, default=_json_default),
                    }
                )
                for row in raw_rows
            ]
            if not rows:
                continue
            query = f"""
            UNWIND $rows AS row
            MATCH (report:EvolutionOrchestration {{id: $report_id}})
            MERGE (child:{label} {{id: row.id}})
            SET child += row
            MERGE (report)-[:{relationship}]->(child)
            """
            self.driver.execute_query(query, rows=rows, report_id=report_id, database_=settings.neo4j_database)
