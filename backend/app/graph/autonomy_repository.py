from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.models.autonomy import AgentDefinition, AutonomousCognitionReport, CognitionEvent


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


class Neo4jAutonomyRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT autonomous_agent_id IF NOT EXISTS "
            "FOR (n:AutonomousAgent) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_event_id IF NOT EXISTS "
            "FOR (n:CognitionEvent) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT agent_task_id IF NOT EXISTS "
            "FOR (n:AgentTask) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT agent_signal_id IF NOT EXISTS "
            "FOR (n:AgentSignal) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT investigation_record_id IF NOT EXISTS "
            "FOR (n:InvestigationRecord) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT autonomous_intervention_id IF NOT EXISTS "
            "FOR (n:AutonomousIntervention) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT human_oversight_action_id IF NOT EXISTS "
            "FOR (n:HumanOversightAction) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT autonomy_report_id IF NOT EXISTS "
            "FOR (n:AutonomousCognitionReport) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX autonomous_agent_status IF NOT EXISTS "
            "FOR (n:AutonomousAgent) ON (n.kind, n.status)",
            "CREATE INDEX cognition_event_product IF NOT EXISTS "
            "FOR (n:CognitionEvent) ON (n.product_id, n.kind, n.handled)",
            "CREATE INDEX agent_task_status IF NOT EXISTS "
            "FOR (n:AgentTask) ON (n.status, n.priority_score)",
            "CREATE INDEX autonomy_product_status IF NOT EXISTS "
            "FOR (n:AutonomousCognitionReport) ON (n.product_id, n.status)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def upsert_agents(self, agents: list[AgentDefinition]) -> None:
        rows = [
            _clean_properties(
                {
                    "id": agent.id,
                    "kind": agent.kind,
                    "name": agent.name,
                    "status": agent.status,
                    "priority_weight": agent.priority_weight,
                    "cadence_seconds": agent.cadence_seconds,
                    "governed_by": agent.governed_by,
                    "responsibilities": agent.responsibilities,
                    "allowed_actions": agent.allowed_actions,
                    "forbidden_actions": agent.forbidden_actions,
                    "last_heartbeat": agent.last_heartbeat,
                    "payload_json": agent.model_dump_json(),
                }
            )
            for agent in agents
        ]
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MERGE (agent:AutonomousAgent {id: row.id})
            SET agent += row
            """,
            rows=rows,
            database_=settings.neo4j_database,
        )

    def list_agents(self) -> list[AgentDefinition]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (agent:AutonomousAgent)
            RETURN agent.payload_json AS payload_json
            ORDER BY agent.priority_weight DESC, agent.name ASC
            """,
            database_=settings.neo4j_database,
        )
        return [AgentDefinition.model_validate_json(record["payload_json"]) for record in records]

    def candidate_product_ids(self, limit: int = 8) -> list[str]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)
            WHERE p:Product OR p:Component
            WITH p, coalesce(
              p.alignment_updated_at,
              p.evolution_orchestration_updated_at,
              p.cognition_updated_at,
              p.telemetry_updated_at,
              datetime({epochMillis: 0})
            ) AS updated
            RETURN coalesce(p.id, p.canonical_key) AS product_id
            ORDER BY updated ASC
            LIMIT $limit
            """,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [record["product_id"] for record in records if record["product_id"]]

    def upsert_event(self, event: CognitionEvent) -> None:
        props = _clean_properties(
            {
                "id": event.id,
                "kind": event.kind,
                "severity": event.severity,
                "product_id": event.product_id,
                "source": event.source,
                "message": event.message,
                "priority_score": event.priority_score,
                "handled": event.handled,
                "created_at": event.created_at,
                "payload_json": event.model_dump_json(),
            }
        )
        self.driver.execute_query(
            """
            MERGE (event:CognitionEvent {id: $event.id})
            SET event += $event
            WITH event
            OPTIONAL MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
              MERGE (p)-[:EMITS_COGNITION_EVENT]->(event)
            )
            """,
            event=props,
            product_id=event.product_id,
            database_=settings.neo4j_database,
        )

    def upsert_report(self, report: AutonomousCognitionReport) -> None:
        self.upsert_agents(report.agents)
        report_id = f"autonomy:{report.product_id or 'global'}"
        props = _clean_properties(
            {
                "id": report_id,
                "product_id": report.product_id,
                "generated_at": report.generated_at,
                "status": report.status,
                "overall_autonomy_health": report.health.overall_autonomy_health,
                "queue_pressure": report.health.queue_pressure,
                "safety_stability_score": report.health.safety_stability_score,
                "telemetry_freshness_score": report.health.telemetry_freshness_score,
                "governance_compliance_score": report.health.governance_compliance_score,
                "event_count": len(report.events),
                "task_count": len(report.tasks),
                "intervention_count": len(report.interventions),
                "investigation_count": len(report.investigations),
                "payload_json": report.model_dump_json(),
            }
        )
        self.driver.execute_query(
            """
            MERGE (report:AutonomousCognitionReport {id: $report.id})
            SET report += $report
            WITH report
            OPTIONAL MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
              MERGE (p)-[:HAS_AUTONOMY_REPORT]->(report)
              SET p.autonomy_status = $report.status,
                  p.autonomy_health_score = $report.overall_autonomy_health,
                  p.autonomy_queue_pressure = $report.queue_pressure,
                  p.autonomy_updated_at = datetime()
            )
            """,
            report=props,
            product_id=report.product_id,
            database_=settings.neo4j_database,
        )
        self._upsert_children(report, report_id)

    def latest_report(self, product_id: str) -> AutonomousCognitionReport | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_AUTONOMY_REPORT]->(report:AutonomousCognitionReport)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN report.payload_json AS payload_json
            ORDER BY report.generated_at DESC
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return AutonomousCognitionReport.model_validate_json(records[0]["payload_json"]) if records else None

    def _upsert_children(self, report: AutonomousCognitionReport, report_id: str) -> None:
        child_sets = [
            ("CognitionEvent", "HAS_COGNITION_EVENT", [item.model_dump(mode="json") for item in report.events]),
            ("AgentTask", "HAS_AGENT_TASK", [item.model_dump(mode="json") for item in report.tasks]),
            ("AgentSignal", "HAS_AGENT_SIGNAL", [item.model_dump(mode="json") for item in report.signals]),
            ("InvestigationRecord", "HAS_INVESTIGATION", [item.model_dump(mode="json") for item in report.investigations]),
            ("AutonomousIntervention", "HAS_AUTONOMOUS_INTERVENTION", [item.model_dump(mode="json") for item in report.interventions]),
            ("HumanOversightAction", "HAS_HUMAN_OVERSIGHT", [item.model_dump(mode="json") for item in report.oversight]),
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
            MATCH (report:AutonomousCognitionReport {{id: $report_id}})
            MERGE (child:{label} {{id: row.id}})
            SET child += row
            MERGE (report)-[:{relationship}]->(child)
            WITH child, row
            OPTIONAL MATCH (agent:AutonomousAgent {{kind: row.agent_kind}})
            FOREACH (_ IN CASE WHEN agent IS NULL THEN [] ELSE [1] END |
              MERGE (agent)-[:PERFORMED]->(child)
            )
            """
            self.driver.execute_query(query, rows=rows, report_id=report_id, database_=settings.neo4j_database)
