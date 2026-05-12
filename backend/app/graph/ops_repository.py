from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.models.launch import AnalyticsEventView, FeedbackSubmissionView
from app.models.ops import ApprovalItem, AuditEvent, AutonomyJob, DailyFounderReport, JobMonitorItem


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
            "CREATE CONSTRAINT approval_request_id IF NOT EXISTS FOR (n:ApprovalRequest) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT autonomy_job_id IF NOT EXISTS FOR (n:AutonomyJob) REQUIRE n.job_id IS UNIQUE",
            "CREATE CONSTRAINT founder_daily_report_id IF NOT EXISTS FOR (n:FounderDailyReport) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT operational_signal_id IF NOT EXISTS FOR (n:OperationalSignal) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT analytics_event_id IF NOT EXISTS FOR (n:AnalyticsEvent) REQUIRE n.event_id IS UNIQUE",
            "CREATE CONSTRAINT feedback_submission_id IF NOT EXISTS FOR (n:FeedbackSubmission) REQUIRE n.feedback_id IS UNIQUE",
            "CREATE INDEX audit_event_trace IF NOT EXISTS FOR (n:AuditEvent) ON (n.trace_id)",
            "CREATE INDEX audit_event_endpoint IF NOT EXISTS FOR (n:AuditEvent) ON (n.endpoint, n.timestamp)",
            "CREATE INDEX analytics_event_region IF NOT EXISTS FOR (n:AnalyticsEvent) ON (n.region, n.timestamp)",
            "CREATE INDEX feedback_submission_status IF NOT EXISTS FOR (n:FeedbackSubmission) ON (n.status, n.created_at)",
            "CREATE INDEX approval_status IF NOT EXISTS FOR (n:ApprovalItem) ON (n.status, n.risk_level)",
            "CREATE INDEX approval_action_type IF NOT EXISTS FOR (n:ApprovalItem) ON (n.action_type)",
            "CREATE INDEX autonomy_job_status IF NOT EXISTS FOR (n:AutonomyJob) ON (n.status, n.risk_level)",
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

    def create_analytics_event(self, event: AnalyticsEventView) -> AnalyticsEventView:
        props = _clean_properties({**event.model_dump(mode="json"), "payload_json": event.model_dump_json()})
        self.driver.execute_query(
            """
            MERGE (event:AnalyticsEvent {event_id: $event.event_id})
            SET event += $event
            """,
            event=props,
            database_=settings.neo4j_database,
        )
        return event

    def create_feedback_submission(self, feedback: FeedbackSubmissionView) -> FeedbackSubmissionView:
        props = _clean_properties({**feedback.model_dump(mode="json"), "payload_json": feedback.model_dump_json()})
        self.driver.execute_query(
            """
            MERGE (feedback:FeedbackSubmission {feedback_id: $feedback.feedback_id})
            SET feedback += $feedback
            """,
            feedback=props,
            database_=settings.neo4j_database,
        )
        return feedback

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
            MERGE (approval:ApprovalItem:ApprovalRequest {id: $approval.id})
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

    def unresolved_approval_exists(self, approval_id: str) -> bool:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (approval:ApprovalItem {id: $approval_id})
            WHERE approval.status IN ["pending", "deferred"]
            RETURN approval.id AS id
            LIMIT 1
            """,
            approval_id=approval_id,
            database_=settings.neo4j_database,
        )
        return bool(records)

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

    def autonomy_jobs(self, limit: int = 75) -> list[AutonomyJob]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (job)
            WHERE job:PricingJob OR job:LearningJob OR job:AgentTask OR job:AutonomyJob
            RETURN coalesce(job.job_id, job.id) AS job_id,
                   coalesce(job.kind, job.job_type, head(labels(job))) AS job_type,
                   coalesce(job.title, job.kind, job.job_type, head(labels(job))) AS title,
                   coalesce(job.description, job.reason, job.summary, "Autonomous operation") AS description,
                   job.status AS status,
                   coalesce(job.risk_level, "level_0") AS risk_level,
                   coalesce(job.approval_required, job.requires_human_approval, false) AS approval_required,
                   coalesce(job.agent_name, job.agent_kind, "System") AS agent_name,
                   coalesce(job.product_id, job.target_entity_id, job.target) AS target_entity_id,
                   coalesce(job.target_entity_type, CASE WHEN job.product_id IS NULL THEN null ELSE "Product" END) AS target_entity_type,
                   coalesce(job.attempts, 0) AS attempts,
                   coalesce(job.max_attempts, 3) AS max_attempts,
                   coalesce(job.created_at, job.started_at) AS created_at,
                   job.started_at AS started_at,
                   coalesce(job.finished_at, job.completed_at, job.updated_at) AS finished_at,
                   coalesce(job.trace_id, job.id) AS trace_id,
                   coalesce(job.last_error, job.error) AS last_error,
                   job.next_retry_at AS next_retry_at,
                   coalesce(job.summary, job.reason, job.message, "No job summary recorded yet.") AS summary
            ORDER BY coalesce(job.updated_at, job.finished_at, job.created_at, datetime({epochMillis: 0})) DESC
            LIMIT $limit
            """,
            limit=limit,
            database_=settings.neo4j_database,
        )
        jobs: list[AutonomyJob] = []
        for record in records:
            status = str(record["status"] or "queued")
            normalized = {
                "completed": "succeeded",
                "stale": "failed",
            }.get(status, status)
            if normalized not in {
                "queued",
                "running",
                "succeeded",
                "failed",
                "retrying",
                "cancelled",
                "requires_approval",
                "blocked",
                "deferred",
            }:
                normalized = "failed"
            risk_level = str(record["risk_level"] or "level_0")
            if risk_level == "level_3":
                normalized = "blocked"
            jobs.append(
                AutonomyJob(
                    job_id=str(record["job_id"]),
                    job_type=str(record["job_type"]),
                    title=str(record["title"]).replace("_", " ").title(),
                    description=str(record["description"]),
                    status=normalized,  # type: ignore[arg-type]
                    risk_level=risk_level,  # type: ignore[arg-type]
                    approval_required=bool(record["approval_required"]) or risk_level == "level_2",
                    agent_name=record["agent_name"],
                    target_entity_id=record["target_entity_id"],
                    target_entity_type=record["target_entity_type"],
                    attempts=int(record["attempts"] or 0),
                    max_attempts=int(record["max_attempts"] or 3),
                    created_at=_to_datetime(record["created_at"]),
                    started_at=_to_datetime(record["started_at"]),
                    finished_at=_to_datetime(record["finished_at"]),
                    trace_id=str(record["trace_id"]),
                    last_error=record["last_error"],
                    next_retry_at=_to_datetime(record["next_retry_at"]),
                    summary=str(record["summary"]),
                    cancellable=normalized in {"queued", "retrying", "deferred"} and risk_level != "level_3",
                )
            )
        return jobs

    def upsert_autonomy_job(self, job: AutonomyJob) -> AutonomyJob:
        props = _clean_properties({**job.model_dump(mode="json"), "payload_json": job.model_dump_json()})
        self.driver.execute_query(
            """
            MERGE (job:AutonomyJob {job_id: $job.job_id})
            SET job += $job
            """,
            job=props,
            database_=settings.neo4j_database,
        )
        return job

    def cancel_autonomy_job(self, job_id: str) -> AutonomyJob | None:
        existing = [job for job in self.autonomy_jobs(200) if job.job_id == job_id]
        if not existing:
            return None
        job = existing[0]
        if not job.cancellable:
            return job
        updated = job.model_copy(update={"status": "cancelled", "finished_at": datetime.now(UTC), "summary": "Cancelled by founder."})
        return self.upsert_autonomy_job(updated)

    def upsert_daily_report(self, report: DailyFounderReport) -> DailyFounderReport:
        props = _clean_properties({**report.model_dump(mode="json"), "payload_json": report.model_dump_json()})
        signals = [
            {
                "id": alert.id,
                "severity": alert.severity,
                "reason": alert.reason,
                "payload_json": alert.model_dump_json(),
            }
            for alert in report.alerts
        ]
        self.driver.execute_query(
            """
            MERGE (report:FounderDailyReport {id: $report.id})
            SET report += $report
            WITH report
            UNWIND $signals AS signal
            MERGE (ops_signal:OperationalSignal {id: signal.id})
            SET ops_signal += signal
            MERGE (report)-[:SUMMARIZES]->(ops_signal)
            """,
            report=props,
            signals=signals,
            database_=settings.neo4j_database,
        )
        return report

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

    def source_activity(self) -> dict[str, dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (snapshot:PriceSnapshot)
            WITH snapshot.source AS source_name, max(snapshot.timestamp) AS last_success
            RETURN source_name, last_success
            """,
            database_=settings.neo4j_database,
        )
        activity: dict[str, dict[str, Any]] = {}
        for record in records:
            source_name = str(record["source_name"] or "")
            if source_name:
                activity[source_name] = {"last_success": _to_datetime(record["last_success"])}
        failed_records, _, _ = self.driver.execute_query(
            """
            MATCH (job:PricingJob)
            WHERE job.status = "failed" AND job.error IS NOT NULL
            RETURN job.error AS error, job.updated_at AS last_failure
            ORDER BY job.updated_at DESC
            LIMIT 20
            """,
            database_=settings.neo4j_database,
        )
        for record in failed_records:
            error = str(record["error"] or "pricing source failed")
            source_key = "unknown"
            for candidate in ("SerpAPI", "eBay", "BestBuy", "Amazon"):
                if candidate.lower() in error.lower():
                    source_key = candidate
                    break
            current = activity.setdefault(source_key, {})
            current.setdefault("last_failure", _to_datetime(record["last_failure"]))
            current.setdefault("last_error_sanitized", _sanitize_error(error))
        return activity

    def saudi_market_quality_summary(self) -> dict[str, Any]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p:Product)-[:HAS_PRICE]->(snapshot:PriceSnapshot {region: "SA"})
            WHERE coalesce(snapshot.accepted, true) = true
            OPTIONAL MATCH (snapshot)-[:FROM_VENDOR]->(vendor:Vendor)
            WITH collect({
              product_id: p.id,
              vendor: vendor.name,
              flags: coalesce(snapshot.flags, []),
              vendor_region_type: coalesce(snapshot.vendor_region_type, ""),
              risk: coalesce(snapshot.marketplace_risk_score, 0.5),
              accepted: coalesce(snapshot.accepted, true),
              imported: coalesce(snapshot.is_imported, false) OR coalesce(snapshot.local_stock_status, "") = "imported_stock",
              item_price_sar: snapshot.item_price_sar,
              vat_status: snapshot.vat_status,
              shipping_status: snapshot.shipping_status
            }) AS rows
            UNWIND rows AS row
            WITH rows, row.product_id AS product_id, collect(row) AS productRows
            WITH rows, collect({
              has_safe: any(item IN productRows WHERE item.accepted
                AND item.vendor_region_type IN ["local_saudi_vendor", "local", "gcc_vendor"]
                AND item.risk < 0.65
                AND item.item_price_sar IS NOT NULL
                AND NOT ("unusually_low_price" IN item.flags OR "unusually_high_price" IN item.flags)),
              has_risky: any(item IN productRows WHERE item.imported OR item.risk >= 0.65
                OR "price_requires_review" IN item.flags OR item.item_price_sar IS NULL)
            }) AS productQuality
            WITH rows, productQuality,
                 [row IN rows WHERE row.vendor_region_type IN ["local_saudi_vendor", "local", "gcc_vendor"]] AS localRows,
                 [row IN rows WHERE row.imported] AS importedRows,
                 [row IN rows WHERE "unusually_low_price" IN row.flags OR "unusually_high_price" IN row.flags
                   OR "suspicious_price_below_gpu_family_market_range" IN row.flags
                   OR "suspicious_price_above_gpu_family_market_range" IN row.flags
                   OR "suspicious_price_below_cpu_model_market_range" IN row.flags
                   OR "suspicious_price_above_cpu_model_market_range" IN row.flags] AS suspiciousRows,
                 [row IN rows WHERE row.vat_status = "vat_unknown" AND row.vendor IS NOT NULL | row.vendor] AS vatVendorRows,
                 [row IN rows WHERE row.shipping_status = "unknown_shipping" AND row.vendor IS NOT NULL | row.vendor] AS shippingVendorRows
            RETURN size(rows) AS listings,
                   size(localRows) AS local_count,
                   size(importedRows) AS imported_count,
                   size(suspiciousRows) AS suspicious_count,
                   size([item IN productQuality WHERE item.has_safe]) AS recommended_products,
                   size([item IN productQuality WHERE item.has_risky AND NOT item.has_safe]) AS risky_only_products,
                   size([item IN productQuality WHERE NOT item.has_safe]) AS products_needing_review,
                   [name IN vatVendorRows | name][0..8] AS unknown_vat_vendors,
                   [name IN shippingVendorRows | name][0..8] AS unknown_shipping_vendors
            """,
            database_=settings.neo4j_database,
        )
        if not records:
            return {}
        data = records[0].data()
        return {
            "saudi_listings_ingested": int(data.get("listings") or 0),
            "saudi_listings_with_recommended_option": int(data.get("recommended_products") or 0),
            "saudi_risky_only_products": int(data.get("risky_only_products") or 0),
            "saudi_local_listing_count": int(data.get("local_count") or 0),
            "saudi_imported_listing_count": int(data.get("imported_count") or 0),
            "saudi_suspicious_price_count": int(data.get("suspicious_count") or 0),
            "saudi_products_needing_review": int(data.get("products_needing_review") or 0),
            "saudi_unknown_vat_vendors": [str(item) for item in data.get("unknown_vat_vendors") or []],
            "saudi_unknown_shipping_vendors": [str(item) for item in data.get("unknown_shipping_vendors") or []],
        }

    def saudi_build_readiness_summary(self) -> dict[str, Any]:
        required = ["CPU", "GPU", "Motherboard", "RAM", "Storage", "PSU", "Case", "Cooler"]
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p:Product)-[:HAS_PRICE]->(snapshot:PriceSnapshot {region: "SA"})
            WHERE coalesce(snapshot.accepted, true) = true
              AND snapshot.availability IN ["in_stock", "preorder", "backorder"]
            WITH coalesce(p.category, head([label IN labels(p) WHERE label <> "Product" AND label <> "Component"])) AS category,
                 p,
                 snapshot
            WHERE category IN $required
            WITH category,
                 count(DISTINCT p) AS priced_count,
                 count(DISTINCT CASE
                   WHEN snapshot.item_price_sar IS NOT NULL
                    AND coalesce(snapshot.marketplace_risk_score, 0.5) < 0.65
                    AND coalesce(snapshot.vendor_region_type, "") IN ["local_saudi_vendor", "local", "gcc_vendor"]
                   THEN p END) AS trusted_count,
                 count(DISTINCT CASE
                   WHEN coalesce(snapshot.marketplace_risk_score, 0.5) >= 0.65
                    OR "price_requires_review" IN coalesce(snapshot.flags, [])
                    OR coalesce(snapshot.is_imported, false)
                   THEN p END) AS risky_count
            RETURN collect({
              category: category,
              priced_count: priced_count,
              trusted_count: trusted_count,
              risky_count: risky_count
            }) AS rows
            """,
            required=required,
            database_=settings.neo4j_database,
        )
        rows = records[0]["rows"] if records else []
        by_category = {str(row["category"]): row for row in rows}
        ready = [category for category in required if int(by_category.get(category, {}).get("trusted_count") or 0) > 0]
        missing = [category for category in required if category not in ready]
        jobs = [
            {
                "category": category,
                "query": _build_discovery_query(category),
                "region": "SA",
                "city": "Riyadh",
                "limit": 5,
                "dry_run": True,
                "reason": f"{category} lacks enough trusted Saudi market data for build generation.",
            }
            for category in missing
        ]
        return {
            "saudi_build_readiness_score": round(len(ready) / len(required), 2),
            "saudi_build_ready_categories": ready,
            "saudi_build_missing_categories": missing,
            "common_missing_build_components": missing,
            "recommended_build_discovery_jobs": jobs[:12],
        }


def _sanitize_error(error: str) -> str:
    sanitized = error
    for marker in ("api_key=", "apiKey=", "Authorization=", "Bearer "):
        if marker in sanitized:
            prefix = sanitized.split(marker, 1)[0]
            sanitized = f"{prefix}{marker}REDACTED"
    return sanitized[:240]


def _build_discovery_query(category: str) -> str:
    return {
        "CPU": "Ryzen 7 7800X3D processor",
        "GPU": "RTX 4070 Super graphics card",
        "Motherboard": "B650 AM5 DDR5 ATX motherboard",
        "RAM": "32GB DDR5 6000 RAM kit",
        "Storage": "1TB NVMe PCIe 4 SSD",
        "PSU": "750W Gold PSU",
        "Case": "ATX airflow PC case",
        "Cooler": "AM5 CPU air cooler",
    }.get(category, f"{category} PC component")
