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
    AutonomyJob,
    AutonomyQueue,
    AutonomySummary,
    CognitionOpsSummary,
    DailyFounderReport,
    DataOpsSummary,
    FounderAlert,
    GraphHealth,
    JobMonitorItem,
    OpsRunbook,
    RecommendedAction,
    SourceHealthSummary,
    SourceHealth,
    SystemHealthSummary,
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
        graph = self._safe_graph_health(neo4j_connected)
        workers = self._safe_worker_health(app_state)
        sources = self._safe_source_health()
        jobs = self._safe_recent_jobs(30) if neo4j_connected else []
        failed_jobs = [job for job in jobs if job.status in {"failed", "retrying", "requires_approval"}]
        approvals = self._safe_pending_approvals() if neo4j_connected else []
        stale_sources = [source for source in sources if source.status in {"degraded", "paused", "quota_limited", "not_configured"}]
        alerts = self.alerts(graph, workers, sources, failed_jobs, approvals)
        system_health = "healthy"
        if any(alert.severity == "critical" for alert in alerts) or not neo4j_connected:
            system_health = "critical"
        elif alerts:
            system_health = "watch"
        if failed_jobs:
            system_health = "degraded" if system_health == "healthy" else system_health
        successful_refreshes = self._safe_successful_refresh_count() if neo4j_connected else 0
        new_products = self._safe_new_products_24h() if neo4j_connected else 0
        recent_audit = self._safe_recent_audit_events(12) if neo4j_connected else []
        data_summary = DataOpsSummary(
            new_products_discovered=new_products,
            price_snapshots_updated=successful_refreshes,
            stale_prices_detected=graph.stale_product_count,
            telemetry_gaps_detected=1 if not any(source.configured for source in sources) else 0,
            enrichment_jobs_completed=len([job for job in jobs if "enrichment" in job.job_type and job.status == "succeeded"]),
        )
        cognition_summary = CognitionOpsSummary(
            governance_risks=len([alert for alert in alerts if "governance" in alert.reason.lower()]),
            alignment_warnings=len([alert for alert in alerts if "alignment" in alert.reason.lower()]),
            anomaly_spikes=len([alert for alert in alerts if "anomaly" in alert.reason.lower()]),
        )
        source_summary = self.source_summary(sources)
        autonomy_summary = AutonomySummary(
            completed_jobs=len([job for job in jobs if job.status == "succeeded"]),
            failed_jobs=len([job for job in jobs if job.status == "failed"]),
            retries=sum(job.attempts for job in jobs if job.status == "retrying"),
            pending_approvals=len(approvals),
            interventions_proposed=len(approvals),
            high_risk_alerts=len([alert for alert in alerts if alert.severity in {"warning", "critical"}]),
        )
        system_summary = self.system_summary(system_health, graph, workers, sources)
        handled = self.handled_automatically(jobs, successful_refreshes, new_products)
        report = DailyFounderReport(
            system_health=system_health,  # type: ignore[arg-type]
            neo4j_health=graph,
            workers=workers,
            failed_jobs=failed_jobs[:12],
            successful_refreshes=successful_refreshes,
            new_products_discovered=new_products,
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
            recent_audit_events=recent_audit,
            system_summary=system_summary,
            autonomy_summary=autonomy_summary,
            data_summary=data_summary,
            cognition_summary=cognition_summary,
            source_summary=source_summary,
            handled_automatically=handled,
            needs_attention=alerts[:8],
        )
        if neo4j_connected:
            try:
                self.repository.upsert_daily_report(report)
            except Exception:
                pass
        return report

    def _safe_graph_health(self, neo4j_connected: bool) -> GraphHealth:
        try:
            return self.graph_health(neo4j_connected)
        except Exception:
            return GraphHealth(
                status="degraded",
                neo4j_connected=neo4j_connected,
                message="Operational graph counts are unavailable; report is partial.",
            )

    def _safe_worker_health(self, app_state: Any) -> list[WorkerHealth]:
        try:
            return self.worker_health(app_state)
        except Exception:
            return [
                WorkerHealth(
                    name="worker status",
                    enabled=False,
                    running=False,
                    queue_depth=0,
                    status="degraded",
                    message="Worker health subsystem did not respond; report is partial.",
                )
            ]

    def _safe_source_health(self) -> list[SourceHealth]:
        try:
            return self.source_health()
        except Exception:
            return [
                SourceHealth(
                    source="external sources",
                    configured=False,
                    status="unknown",
                    quota_status="unknown",
                    reliability_score=0,
                    freshness_score=0,
                    message="Source health subsystem did not respond; report is partial.",
                )
            ]

    def _safe_recent_jobs(self, limit: int) -> list[JobMonitorItem]:
        try:
            return self.repository.recent_jobs(limit)
        except Exception:
            return []

    def _safe_pending_approvals(self) -> list[ApprovalItem]:
        try:
            return self.repository.pending_approvals()
        except Exception:
            return []

    def _safe_recent_audit_events(self, limit: int) -> list[AuditEvent]:
        try:
            return self.repository.recent_audit_events(limit)
        except Exception:
            return []

    def _safe_successful_refresh_count(self) -> int:
        try:
            return self.repository.successful_refresh_count()
        except Exception:
            return 0

    def _safe_new_products_24h(self) -> int:
        try:
            return self.repository.new_products_24h()
        except Exception:
            return 0

    def system_summary(
        self,
        system_health: str,
        graph: GraphHealth,
        workers: list[WorkerHealth],
        sources: list[SourceHealth],
    ) -> SystemHealthSummary:
        worker_status = "healthy"
        if any(worker.status == "degraded" for worker in workers):
            worker_status = "degraded"
        elif any(worker.enabled and not worker.running for worker in workers):
            worker_status = "watch"
        if not any(source.configured for source in sources):
            external_source_status = "not_configured"
        elif any(source.status in {"degraded", "paused", "quota_limited"} for source in sources):
            external_source_status = "degraded"
        else:
            external_source_status = "watch"
        severity = "critical" if system_health == "critical" else "warning" if system_health == "degraded" else "watch" if system_health == "watch" else "info"
        return SystemHealthSummary(
            backend_status=system_health,  # type: ignore[arg-type]
            neo4j_status=graph.status,
            worker_status=worker_status,  # type: ignore[arg-type]
            frontend_configured=bool(settings.frontend_url),
            external_source_status=external_source_status,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
        )

    def source_summary(self, sources: list[SourceHealth]) -> SourceHealthSummary:
        return SourceHealthSummary(
            configured_sources=len([source for source in sources if source.configured]),
            missing_api_keys=[source.source for source in sources if not source.configured],
            degraded_sources=[source.source for source in sources if source.status in {"degraded", "paused", "quota_limited"}],
            quota_warnings=[source.source for source in sources if source.quota_status in {"near_limit", "limited"}],
            last_successful_sync_by_source={source.source: source.last_successful_request for source in sources},
        )

    def handled_automatically(
        self,
        jobs: list[JobMonitorItem],
        successful_refreshes: int,
        new_products: int,
    ) -> list[str]:
        handled = []
        if successful_refreshes:
            handled.append(f"Updated {successful_refreshes} pricing refresh job(s) in the last 24 hours.")
        if new_products:
            handled.append(f"Discovered {new_products} new product node(s) in the last 24 hours.")
        retrying = len([job for job in jobs if job.status == "retrying"])
        if retrying:
            handled.append(f"Retry policy is handling {retrying} bounded retry job(s).")
        if not handled:
            handled.append("No completed automation has been recorded yet for this daily window.")
        return handled[:6]

    def autonomy_queue(self) -> AutonomyQueue:
        try:
            jobs = self.repository.autonomy_jobs(75)
        except Exception:
            jobs = []
        scheduled = self.scheduled_jobs()
        all_jobs = jobs + scheduled
        return AutonomyQueue(
            running_now=[job for job in jobs if job.status == "running"],
            waiting_approval=[job for job in jobs if job.status == "requires_approval" or job.approval_required],
            failed_needs_attention=[job for job in jobs if job.status in {"failed", "retrying", "blocked"}],
            recently_completed=[job for job in jobs if job.status in {"succeeded", "cancelled"}][:12],
            scheduled_next=scheduled,
            all_jobs=all_jobs,
        )

    def scheduled_jobs(self) -> list[AutonomyJob]:
        now = datetime.now(UTC)
        definitions = [
            ("scheduled:health-check", "health_check", "Health Check", "Check backend, Neo4j, workers, and sources.", "System Monitor"),
            ("scheduled:price-refresh", "price_refresh", "Top Product Price Refresh", "Refresh top product price snapshots using configured sources.", "Pricing Agent"),
            ("scheduled:telemetry-freshness", "telemetry_freshness", "Telemetry Freshness Scan", "Find stale telemetry coverage without fabricating missing data.", "Telemetry Agent"),
            ("scheduled:daily-brief", "daily_report", "Founder Daily Brief", "Generate the daily operational report.", "Operations Agent"),
        ]
        return [
            AutonomyJob(
                job_id=job_id,
                job_type=job_type,
                title=title,
                description=description,
                status="queued",
                risk_level="level_0",
                approval_required=False,
                agent_name=agent,
                attempts=0,
                max_attempts=1,
                created_at=now,
                trace_id=f"scheduled-{job_type}",
                summary="Scheduled safe automation; no founder approval required.",
                cancellable=False,
            )
            for job_id, job_type, title, description, agent in definitions
        ]

    def cancel_job(self, job_id: str, actor: AuthPrincipal, trace_id: str) -> AutonomyJob | None:
        job = self.repository.cancel_autonomy_job(job_id)
        self.repository.create_audit_event(
            AuditEvent(
                actor=actor.actor,
                role=actor.role,
                action="ops.autonomy_queue.cancel",
                endpoint=f"/ops/autonomy-queue/{job_id}/cancel",
                method="POST",
                target=job_id,
                result="succeeded" if job and job.status == "cancelled" else "blocked",
                status_code=200 if job else 404,
                trace_id=trace_id,
                approval_required=False,
                risk_level=job.risk_level if job else "level_1",
            )
        )
        return job

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
    ) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        if approvals:
            actions.append(
                RecommendedAction(
                    reason="High-risk action waiting",
                    severity="warning",
                    suggested_action="Review pending approval items before high-impact graph or policy mutations proceed.",
                    approval_required=True,
                    approval_id=approvals[0].id,
                )
            )
        if failed_jobs:
            actions.append(
                RecommendedAction(
                    reason="Failed autonomous job",
                    severity="warning",
                    suggested_action="Inspect failed jobs; retry only idempotent level 0 or level 1 jobs.",
                )
            )
        if any(alert.reason == "Neo4j unavailable" for alert in alerts):
            actions.append(
                RecommendedAction(
                    reason="Neo4j unavailable",
                    severity="critical",
                    suggested_action="Restore Neo4j connectivity before running ingestion or governance refreshes.",
                )
            )
        actions.append(
            RecommendedAction(
                reason="Safe automation can continue",
                severity="info",
                suggested_action="Let level 0 and level 1 automation continue; stale safe data is preferred over untrusted fresh data.",
            )
        )
        return actions[:6]

    def create_approval_from_autonomy(self, report: AutonomousCognitionReport) -> list[ApprovalItem]:
        approvals: list[ApprovalItem] = []
        for intervention in report.interventions:
            if not intervention.requires_human_approval:
                continue
            existing_key = f"{intervention.kind}:{intervention.target}:{report.product_id}"
            approval_id = f"approval:{existing_key}"
            try:
                if self.repository.unresolved_approval_exists(approval_id):
                    existing = self.repository.approval_by_id(approval_id)
                    if existing:
                        approvals.append(existing)
                        continue
            except Exception:
                pass
            approval = ApprovalItem(
                id=approval_id,
                action_type=intervention.kind,
                title=intervention.kind.replace("_", " ").title(),
                description=intervention.reason,
                affected_entities=[entity for entity in [report.product_id, intervention.target] if entity],
                risk_level="level_2",
                reasoning=intervention.reason,
                evidence={
                    "agent_kind": intervention.agent_kind,
                    "severity": intervention.severity,
                    "alignment_checked": intervention.alignment_checked,
                    "autonomy_report_id": report.id,
                },
                requested_by_agent=intervention.agent_kind,
                risk_explanation="High-impact autonomous intervention requires explicit founder approval.",
                expected_impact="If approved, a bounded execution job can apply the intervention with audit metadata.",
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
        if approved and approval.risk_level == "level_3":
            audit = self.repository.create_audit_event(
                AuditEvent(
                    actor=actor.actor,
                    role=actor.role,
                    action="approval.blocked_level_3",
                    endpoint=f"/approvals/{approval.id}",
                    method="POST",
                    target=approval.id,
                    result="blocked",
                    status_code=403,
                    trace_id=trace_id,
                    approval_required=True,
                    approval_status=approval.status,
                    risk_level=approval.risk_level,
                )
            )
            return ApprovalDecisionResponse(approval=approval, audit_event=audit)
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

    def defer_approval(
        self,
        approval: ApprovalItem,
        *,
        actor: AuthPrincipal,
        note: str | None,
        trace_id: str,
    ) -> ApprovalDecisionResponse:
        return self._set_approval_status(
            approval,
            actor=actor,
            status="deferred",
            note=note,
            trace_id=trace_id,
            action="approval.defer",
        )

    def mark_approval_reviewed(
        self,
        approval: ApprovalItem,
        *,
        actor: AuthPrincipal,
        note: str | None,
        trace_id: str,
    ) -> ApprovalDecisionResponse:
        return self._set_approval_status(
            approval,
            actor=actor,
            status="reviewed",
            note=note,
            trace_id=trace_id,
            action="approval.mark_reviewed",
        )

    def _set_approval_status(
        self,
        approval: ApprovalItem,
        *,
        actor: AuthPrincipal,
        status: str,
        note: str | None,
        trace_id: str,
        action: str,
    ) -> ApprovalDecisionResponse:
        updated = approval.model_copy(
            update={
                "status": status,
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
                action=action,
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
