from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.graph.ops_repository import Neo4jOpsRepository
from app.models.autonomy import AutonomousCognitionReport
from app.models.ops import (
    ApprovalDecisionResponse,
    ApprovalItem,
    AuditEvent,
    AuthPrincipal,
    DailyFounderReport,
    FounderAlert,
    GraphHealth,
    JobMonitorItem,
    OpsRunbook,
    SourceHealth,
    WorkerHealth,
)


class OpsService:
    def __init__(self, repository: Neo4jOpsRepository) -> None:
        self.repository = repository

    def source_health(self) -> list[SourceHealth]:
        sources = [
            ("SerpAPI", bool(settings.serpapi_key), "aggregator pricing discovery"),
            ("eBay Browse", bool(settings.ebay_browse_token), "retailer marketplace pricing"),
            ("BestBuy", bool(settings.bestbuy_api_key), "official retailer pricing"),
            (
                "Amazon PAAPI",
                bool(
                    settings.amazon_paapi_access_key
                    and settings.amazon_paapi_secret_key
                    and settings.amazon_paapi_partner_tag
                ),
                "Amazon product advertising pricing",
            ),
        ]
        result: list[SourceHealth] = []
        for name, configured, purpose in sources:
            status = "unknown" if configured else "not_configured"
            result.append(
                SourceHealth(
                    source=name,
                    configured=configured,
                    status=status,  # type: ignore[arg-type]
                    quota_status="unknown" if configured else "not_configured",
                    reliability_score=0.72 if configured else 0.0,
                    freshness_score=0.65 if configured else 0.0,
                    message=f"{purpose}; {'configured' if configured else 'API key not configured, source is skipped safely'}",
                )
            )
        return result

    def worker_health(self, app_state: Any) -> list[WorkerHealth]:
        workers = [
            ("pricing_worker", "Pricing ingestion worker"),
            ("pricing_scheduler", "Pricing scheduler"),
            ("cognition_worker", "Cognition worker"),
            ("autonomous_agent_worker", "Autonomous agent worker"),
        ]
        result: list[WorkerHealth] = []
        for attr, label in workers:
            worker = getattr(app_state, attr, None)
            enabled = worker is not None
            thread = getattr(worker, "thread", None)
            running = bool(thread and thread.is_alive())
            queue = getattr(worker, "queue", None)
            queue_depth = queue.qsize() if queue is not None else 0
            status = "healthy" if running else "stopped"
            if not enabled:
                status = "idle"
            result.append(
                WorkerHealth(
                    name=label,
                    enabled=enabled,
                    running=running,
                    queue_depth=queue_depth,
                    last_heartbeat=datetime.now(UTC) if running else None,
                    status=status,  # type: ignore[arg-type]
                    message="running" if running else "not running; queued jobs will use fallback paths where available",
                )
            )
        return result

    def graph_health(self, neo4j_connected: bool) -> GraphHealth:
        if not neo4j_connected:
            return GraphHealth(
                status="unavailable",
                neo4j_connected=False,
                message="Neo4j is unavailable; UI should preserve cached/degraded states.",
            )
        counts = self.repository.graph_counts()
        status = "healthy"
        if counts["pending_approval_count"] > 0 or counts["stale_product_count"] > max(3, counts["product_count"] * 0.2):
            status = "watch"
        return GraphHealth(
            status=status,  # type: ignore[arg-type]
            neo4j_connected=True,
            message="Neo4j is connected and operational graph counts are available.",
            **counts,
        )

    def daily_report(self, *, neo4j_connected: bool, app_state: Any) -> DailyFounderReport:
        graph = self.graph_health(neo4j_connected)
        workers = self.worker_health(app_state)
        sources = self.source_health()
        jobs = self.repository.recent_jobs(30) if neo4j_connected else []
        failed_jobs = [job for job in jobs if job.status in {"failed", "retrying", "requires_approval"}]
        approvals = self.repository.pending_approvals() if neo4j_connected else []
        stale_sources = [source for source in sources if source.status in {"degraded", "paused", "quota_limited", "not_configured"}]
        alerts = self.alerts(graph, workers, sources, failed_jobs, approvals)
        system_health = "healthy"
        if any(alert.severity == "critical" for alert in alerts) or not neo4j_connected:
            system_health = "critical"
        elif alerts:
            system_health = "watch"
        if failed_jobs:
            system_health = "degraded" if system_health == "healthy" else system_health
        return DailyFounderReport(
            system_health=system_health,  # type: ignore[arg-type]
            neo4j_health=graph,
            workers=workers,
            failed_jobs=failed_jobs[:12],
            successful_refreshes=self.repository.successful_refresh_count() if neo4j_connected else 0,
            new_products_discovered=self.repository.new_products_24h() if neo4j_connected else 0,
            stale_sources=stale_sources,
            source_health=sources,
            pricing_anomalies=[],
            telemetry_gaps=["Telemetry coverage is reduced when no external benchmark source is configured"]
            if not any(source.configured for source in sources)
            else [],
            cognition_risks=[
                "Pending approvals may block high-impact autonomous actions"
            ]
            if approvals
            else [],
            approval_items_waiting=approvals[:12],
            alerts=alerts,
            recommended_next_actions=self.recommended_actions(alerts, approvals, failed_jobs),
            recent_audit_events=self.repository.recent_audit_events(12) if neo4j_connected else [],
        )

    def alerts(
        self,
        graph: GraphHealth,
        workers: list[WorkerHealth],
        sources: list[SourceHealth],
        failed_jobs: list[JobMonitorItem],
        approvals: list[ApprovalItem],
    ) -> list[FounderAlert]:
        alerts: list[FounderAlert] = []
        if not graph.neo4j_connected:
            alerts.append(
                FounderAlert(
                    severity="critical",
                    reason="Neo4j unavailable",
                    evidence={"status": graph.status},
                    suggested_action="Check database credentials, network access, and Aura instance state.",
                )
            )
        for approval in approvals[:5]:
            alerts.append(
                FounderAlert(
                    severity="warning" if approval.risk_level == "level_2" else "critical",
                    reason=f"Approval required: {approval.action_type}",
                    evidence={"affected_entities": approval.affected_entities, "risk_level": approval.risk_level},
                    suggested_action="Approve, reject, defer, or mark reviewed in the approval center.",
                    approval_id=approval.id,
                )
            )
        stopped = [worker for worker in workers if worker.enabled and not worker.running]
        if stopped:
            alerts.append(
                FounderAlert(
                    severity="warning",
                    reason="Worker stopped",
                    evidence={"workers": [worker.name for worker in stopped]},
                    suggested_action="Restart the backend process or inspect worker logs.",
                )
            )
        repeated_failures = [job for job in failed_jobs if job.status == "failed"]
        if repeated_failures:
            alerts.append(
                FounderAlert(
                    severity="warning",
                    reason="Failed jobs need review",
                    evidence={"job_ids": [job.job_id for job in repeated_failures[:5]]},
                    suggested_action="Review failed jobs; safe retries are bounded by retry policy.",
                )
            )
        missing_sources = [source.source for source in sources if not source.configured]
        if missing_sources:
            alerts.append(
                FounderAlert(
                    severity="info",
                    reason="Optional sources are not configured",
                    evidence={"sources": missing_sources},
                    suggested_action="Add API keys only for sources you plan to use; system continues with configured sources.",
                )
            )
        return alerts[:12]

    def recommended_actions(
        self,
        alerts: list[FounderAlert],
        approvals: list[ApprovalItem],
        failed_jobs: list[JobMonitorItem],
    ) -> list[str]:
        actions = []
        if approvals:
            actions.append("Review pending approval items before high-impact graph or policy mutations proceed.")
        if failed_jobs:
            actions.append("Inspect failed jobs; retry only idempotent level 0 or level 1 jobs.")
        if any(alert.reason == "Neo4j unavailable" for alert in alerts):
            actions.append("Restore Neo4j connectivity before running ingestion or governance refreshes.")
        actions.append("Let level 0 and level 1 automation continue; stale safe data is preferred over untrusted fresh data.")
        return actions[:6]

    def create_approval_from_autonomy(self, report: AutonomousCognitionReport) -> list[ApprovalItem]:
        approvals: list[ApprovalItem] = []
        for intervention in report.interventions:
            if not intervention.requires_human_approval:
                continue
            existing_key = f"{intervention.kind}:{intervention.target}:{report.product_id}"
            approval = ApprovalItem(
                id=f"approval:{existing_key}",
                action_type=intervention.kind,
                affected_entities=[entity for entity in [report.product_id, intervention.target] if entity],
                risk_level="level_2",
                reasoning=intervention.reason,
                evidence={
                    "agent_kind": intervention.agent_kind,
                    "severity": intervention.severity,
                    "alignment_checked": intervention.alignment_checked,
                    "autonomy_report_id": report.id,
                },
                rollback_plan="Do not execute mutation until approved; if executed, restore previous policy/evidence state from audit trail.",
                recommended_decision="defer",
                trace_id=report.id,
            )
            approvals.append(self.repository.upsert_approval(approval))
        return approvals

    def decide_approval(
        self,
        approval: ApprovalItem,
        *,
        actor: AuthPrincipal,
        approved: bool,
        note: str | None,
        trace_id: str,
    ) -> ApprovalDecisionResponse:
        updated = approval.model_copy(
            update={
                "status": "approved" if approved else "rejected",
                "decided_at": datetime.now(UTC),
                "decided_by": actor.actor,
                "decision_note": note,
            }
        )
        updated = self.repository.update_approval(updated)
        audit = self.repository.create_audit_event(
            AuditEvent(
                actor=actor.actor,
                role=actor.role,
                action="approval.approve" if approved else "approval.reject",
                endpoint=f"/approvals/{approval.id}",
                method="POST",
                target=approval.id,
                result=updated.status,
                status_code=200,
                trace_id=trace_id,
                approval_required=True,
                approval_status=updated.status,
                risk_level=approval.risk_level,
            )
        )
        return ApprovalDecisionResponse(approval=updated, audit_event=audit)

    def runbook(self) -> OpsRunbook:
        return OpsRunbook(
            autonomy_levels={
                "level_0": ["price refresh", "health checks", "stale marking", "safe retry", "read-only reports"],
                "level_1": ["minor confidence adjustment", "metadata enrichment", "source reliability scoring"],
                "level_2": ["evidence quarantine", "policy rollback", "large graph mutation", "mass confidence downgrade"],
                "level_3": ["delete database", "wipe graph data", "change secrets", "disable governance or alignment"],
            },
            schedules={
                "every_15_minutes": ["health check", "worker status check", "failed job scan"],
                "hourly": ["top product price refresh", "source availability check", "stale data detection"],
                "every_6_hours": ["broader discovery", "pricing sync", "telemetry freshness scan"],
                "daily": ["governance refresh", "alignment refresh", "graph hygiene scan", "founder report"],
                "weekly": ["deep graph audit", "duplicate review", "policy drift report"],
            },
            safe_defaults=[
                "Prefer stale but safe data over fresh untrusted data.",
                "Prefer lower confidence over false certainty.",
                "Prefer manual approval over irreversible autonomous mutation.",
            ],
        )
