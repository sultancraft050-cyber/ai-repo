from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.models.ops import ApprovalItem, AuditEvent, JobMonitorItem


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


def _to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if hasattr(value, "to_native"):
        return value.to_native()
    return None


class Neo4jOpsRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT audit_event_id IF NOT EXISTS FOR (n:AuditEvent) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT approval_item_id IF NOT EXISTS FOR (n:ApprovalItem) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX audit_event_trace IF NOT EXISTS FOR (n:AuditEvent) ON (n.trace_id)",
            "CREATE INDEX audit_event_endpoint IF NOT EXISTS FOR (n:AuditEvent) ON (n.endpoint, n.timestamp)",
            "CREATE INDEX approval_status IF NOT EXISTS FOR (n:ApprovalItem) ON (n.status, n.risk_level)",
            "CREATE INDEX approval_action_type IF NOT EXISTS FOR (n:ApprovalItem) ON (n.action_type)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def create_audit_event(self, event: AuditEvent) -> AuditEvent:
        props = _clean_properties({**event.model_dump(mode="json"), "payload_json": event.model_dump_json()})
        self.driver.execute_query(
            """
            MERGE (event:AuditEvent {id: $event.id})
            SET event += $event
            """,
            event=props,
            database_=settings.neo4j_database,
        )
        return event

    def recent_audit_events(self, limit: int = 25) -> list[AuditEvent]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (event:AuditEvent)
            RETURN event.payload_json AS payload_json
            ORDER BY event.timestamp DESC
            LIMIT $limit
            """,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [AuditEvent.model_validate_json(record["payload_json"]) for record in records]

    def idempotency_seen(self, endpoint: str, key: str) -> bool:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (event:AuditEvent {endpoint: $endpoint, idempotency_key: $key})
            WHERE event.result = "succeeded"
            RETURN event.id AS id
            LIMIT 1
            """,
            endpoint=endpoint,
            key=key,
            database_=settings.neo4j_database,
        )
        return bool(records)

    def upsert_approval(self, approval: ApprovalItem) -> ApprovalItem:
        props = _clean_properties({**approval.model_dump(mode="json"), "payload_json": approval.model_dump_json()})
        self.driver.execute_query(
            """
            MERGE (approval:ApprovalItem {id: $approval.id})
            SET approval += $approval
            WITH approval
            UNWIND $affected_entities AS entity_id
            OPTIONAL MATCH (entity)
            WHERE entity.id = entity_id OR entity.canonical_key = entity_id
            FOREACH (_ IN CASE WHEN entity IS NULL THEN [] ELSE [1] END |
              MERGE (approval)-[:AFFECTS_ENTITY]->(entity)
            )
            """,
            approval=props,
            affected_entities=approval.affected_entities,
            database_=settings.neo4j_database,
        )
        return approval

    def pending_approvals(self, limit: int = 50) -> list[ApprovalItem]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (approval:ApprovalItem {status: "pending"})
            RETURN approval.payload_json AS payload_json
            ORDER BY approval.created_at DESC
            LIMIT $limit
            """,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [ApprovalItem.model_validate_json(record["payload_json"]) for record in records]

    def approval_by_id(self, approval_id: str) -> ApprovalItem | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (approval:ApprovalItem {id: $approval_id})
            RETURN approval.payload_json AS payload_json
            LIMIT 1
            """,
            approval_id=approval_id,
            database_=settings.neo4j_database,
        )
        return ApprovalItem.model_validate_json(records[0]["payload_json"]) if records else None

    def update_approval(self, approval: ApprovalItem) -> ApprovalItem:
        props = _clean_properties({**approval.model_dump(mode="json"), "payload_json": approval.model_dump_json()})
        self.driver.execute_query(
            """
            MATCH (approval:ApprovalItem {id: $approval.id})
            SET approval += $approval
            """,
            approval=props,
            database_=settings.neo4j_database,
        )
        return approval

    def graph_counts(self) -> dict[str, int]:
        records, _, _ = self.driver.execute_query(
            """
            OPTIONAL MATCH (p)
            WHERE p:Product OR p:Component
            WITH count(p) AS product_count,
                 count(CASE WHEN coalesce(p.stale, false) THEN 1 END) AS stale_product_count
            OPTIONAL MATCH (approval:ApprovalItem {status: "pending"})
            WITH product_count, stale_product_count, count(approval) AS pending_approval_count
            OPTIONAL MATCH (audit:AuditEvent)
            WHERE audit.timestamp > datetime() - duration({days: 1})
            RETURN product_count, stale_product_count, pending_approval_count, count(audit) AS recent_audit_count
            """,
            database_=settings.neo4j_database,
        )
        if not records:
            return {
                "product_count": 0,
                "stale_product_count": 0,
                "pending_approval_count": 0,
                "recent_audit_count": 0,
            }
        return {key: int(records[0][key] or 0) for key in records[0].keys()}

    def recent_jobs(self, limit: int = 30) -> list[JobMonitorItem]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (job)
            WHERE job:PricingJob OR job:LearningJob
            RETURN job.id AS job_id,
                   coalesce(job.kind, head(labels(job))) AS job_type,
                   job.status AS status,
                   coalesce(job.attempts, 0) AS attempts,
                   job.created_at AS started_at,
                   job.updated_at AS finished_at,
                   coalesce(job.trace_id, job.id) AS trace_id,
                   coalesce(job.risk_level, "level_0") AS risk_level,
                   coalesce(job.approval_required, false) AS approval_required,
                   job.error AS error
            ORDER BY coalesce(job.updated_at, job.created_at, datetime({epochMillis: 0})) DESC
            LIMIT $limit
            """,
            limit=limit,
            database_=settings.neo4j_database,
        )
        items: list[JobMonitorItem] = []
        for record in records:
            status = str(record["status"] or "queued")
            normalized = {
                "completed": "succeeded",
                "stale": "failed",
            }.get(status, status)
            if normalized not in {"queued", "running", "succeeded", "failed", "retrying", "cancelled", "requires_approval"}:
                normalized = "failed"
            items.append(
                JobMonitorItem(
                    job_id=str(record["job_id"]),
                    job_type=str(record["job_type"]),
                    status=normalized,  # type: ignore[arg-type]
                    attempts=int(record["attempts"] or 0),
                    started_at=_to_datetime(record["started_at"]),
                    finished_at=_to_datetime(record["finished_at"]),
                    trace_id=str(record["trace_id"]),
                    risk_level=record["risk_level"] or "level_0",
                    approval_required=bool(record["approval_required"]),
                    error=record["error"],
                )
            )
        return items

    def successful_refresh_count(self) -> int:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (job:PricingJob)
            WHERE job.status IN ["completed", "succeeded"]
              AND job.updated_at > datetime() - duration({days: 1})
            RETURN count(job) AS count
            """,
            database_=settings.neo4j_database,
        )
        return int(records[0]["count"] or 0) if records else 0

    def new_products_24h(self) -> int:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p:Product)
            WHERE p.created_at > datetime() - duration({days: 1})
            RETURN count(p) AS count
            """,
            database_=settings.neo4j_database,
        )
        return int(records[0]["count"] or 0) if records else 0
