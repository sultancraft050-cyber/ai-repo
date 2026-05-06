from __future__ import annotations

from statistics import mean
from typing import Iterable

from app.models.alignment import AlignmentInspectionReport
from app.models.autonomy import (
    AgentDefinition,
    AgentSignal,
    AgentTask,
    AutonomousCognitionReport,
    AutonomousHealthIndex,
    AutonomousIntervention,
    CognitionEvent,
    HumanOversightAction,
    InvestigationRecord,
)
from app.models.evolution import EvolutionOrchestrationReport


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return round(max(lower, min(upper, value)), 4)


def _avg(values: Iterable[float | None], default: float = 0.0) -> float:
    clean = [float(value) for value in values if value is not None]
    return round(mean(clean), 4) if clean else default


def default_agents() -> list[AgentDefinition]:
    constitution = [
        "cognitive-constitution-v1",
        "alignment constraints",
        "cognitive-policy-default",
        "human oversight gates",
    ]
    return [
        AgentDefinition(
            id="agent:telemetry",
            kind="telemetry",
            name="Telemetry Agent",
            priority_weight=0.82,
            cadence_seconds=900,
            governed_by=constitution,
            responsibilities=[
                "monitor telemetry freshness",
                "trigger telemetry refresh",
                "detect missing telemetry coverage",
            ],
            allowed_actions=["monitor_telemetry", "refresh_telemetry", "request_revalidation"],
            forbidden_actions=["overwrite canonical specs", "raise confidence without fresh evidence"],
        ),
        AgentDefinition(
            id="agent:benchmark-validation",
            kind="benchmark_validation",
            name="Benchmark Validation Agent",
            priority_weight=0.76,
            cadence_seconds=1800,
            governed_by=constitution,
            responsibilities=[
                "validate benchmark consistency",
                "escalate benchmark contradictions",
                "request independent revalidation",
            ],
            allowed_actions=["validate_benchmark", "request_revalidation"],
            forbidden_actions=["blindly trust a single benchmark source"],
        ),
        AgentDefinition(
            id="agent:anomaly-investigation",
            kind="anomaly_investigation",
            name="Anomaly Investigation Agent",
            priority_weight=0.9,
            cadence_seconds=600,
            governed_by=constitution,
            responsibilities=[
                "investigate recurring anomalies",
                "correlate instability patterns",
                "isolate problematic hardware combinations",
            ],
            allowed_actions=["investigate_anomaly", "request_revalidation"],
            forbidden_actions=["suppress anomaly evidence"],
        ),
        AgentDefinition(
            id="agent:confidence-audit",
            kind="confidence_audit",
            name="Confidence Audit Agent",
            priority_weight=0.86,
            cadence_seconds=900,
            governed_by=constitution,
            responsibilities=[
                "detect confidence inflation",
                "validate evidence sufficiency",
                "lower unstable confidence",
            ],
            allowed_actions=["audit_confidence", "request_revalidation"],
            forbidden_actions=["increase confidence from self-generated conclusions"],
        ),
        AgentDefinition(
            id="agent:governance-stability",
            kind="governance_stability",
            name="Governance Stability Agent",
            priority_weight=0.88,
            cadence_seconds=900,
            governed_by=constitution,
            responsibilities=[
                "monitor graph hygiene",
                "quarantine polluted evidence through governed approval",
                "stabilize recursive reasoning risks",
            ],
            allowed_actions=["stabilize_governance", "request_revalidation"],
            forbidden_actions=["mutate policy without oversight"],
        ),
        AgentDefinition(
            id="agent:evolution-monitoring",
            kind="evolution_monitoring",
            name="Evolution Monitoring Agent",
            priority_weight=0.8,
            cadence_seconds=1200,
            governed_by=constitution,
            responsibilities=[
                "monitor cognitive evolution velocity",
                "detect policy drift",
                "prepare rollback paths",
            ],
            allowed_actions=["monitor_evolution", "request_revalidation"],
            forbidden_actions=["promote sandboxed models without approval"],
        ),
        AgentDefinition(
            id="agent:alignment-integrity",
            kind="alignment_integrity",
            name="Alignment Integrity Agent",
            priority_weight=0.96,
            cadence_seconds=600,
            governed_by=constitution,
            responsibilities=[
                "detect objective drift",
                "monitor optimization bias",
                "enforce cognitive constitution",
            ],
            allowed_actions=["enforce_alignment", "request_revalidation"],
            forbidden_actions=["override non-overridable alignment constraints"],
        ),
        AgentDefinition(
            id="agent:recommendation-verification",
            kind="recommendation_verification",
            name="Recommendation Verification Agent",
            priority_weight=0.78,
            cadence_seconds=900,
            governed_by=constitution,
            responsibilities=[
                "verify recommendation safety",
                "downgrade risky recommendations",
                "surface uncertainty before ranking",
            ],
            allowed_actions=["verify_recommendation", "request_revalidation"],
            forbidden_actions=["prioritize popularity over correctness"],
        ),
    ]


class AutonomousCognitionEngine:
    def orchestrate(
        self,
        product_id: str,
        alignment: AlignmentInspectionReport,
        evolution: EvolutionOrchestrationReport,
        agents: list[AgentDefinition] | None = None,
        external_events: list[CognitionEvent] | None = None,
    ) -> AutonomousCognitionReport:
        active_agents = agents or default_agents()
        events = self.events(product_id, alignment, evolution)
        if external_events:
            events.extend(external_events)
        events = sorted(events, key=lambda event: event.priority_score, reverse=True)[:24]
        tasks = self.tasks(events, alignment, evolution)
        signals = self.signals(tasks, events)
        investigations = self.investigations(events, alignment, evolution)
        interventions = self.interventions(events, tasks, alignment, evolution)
        oversight = self.oversight(interventions, investigations, alignment, evolution)
        health = self.health(active_agents, events, tasks, interventions, alignment, evolution)
        status = self.status(health, events, interventions, alignment)
        return AutonomousCognitionReport(
            product_id=product_id,
            status=status,
            agents=self.agent_statuses(active_agents, tasks, events),
            events=events,
            tasks=tasks,
            signals=signals,
            investigations=investigations,
            interventions=interventions,
            oversight=oversight,
            health=health,
            autonomy_summary=self.summary(health, events, tasks, interventions),
        )

    def events(
        self,
        product_id: str,
        alignment: AlignmentInspectionReport,
        evolution: EvolutionOrchestrationReport,
    ) -> list[CognitionEvent]:
        policy = evolution.active_policy
        events = [
            CognitionEvent(
                kind="scheduled_tick",
                severity="info",
                product_id=product_id,
                source="autonomous-agent-scheduler",
                message="Autonomous cognition cycle evaluated product state.",
                payload={"policy_id": policy.id, "identity_id": alignment.identity.id},
                priority_score=0.18,
            )
        ]
        if evolution.health_index.evidence_freshness < policy.evidence_freshness_min:
            events.append(
                self._event(
                    "stale_evidence",
                    product_id,
                    "Telemetry freshness is below the active policy floor.",
                    "telemetry-agent",
                    evolution.health_index.evidence_freshness,
                    policy.evidence_freshness_min,
                    lower_is_bad=True,
                )
            )
        if evolution.metrics.contradiction_propagation > policy.contradiction_tolerance:
            events.append(
                self._event(
                    "benchmark_contradiction",
                    product_id,
                    "Contradiction propagation exceeded policy tolerance.",
                    "benchmark-validation-agent",
                    evolution.metrics.contradiction_propagation,
                    policy.contradiction_tolerance,
                )
            )
        if evolution.metrics.anomaly_growth > policy.anomaly_escalation_threshold:
            events.append(
                self._event(
                    "anomaly_spike",
                    product_id,
                    "Anomaly pressure exceeded the escalation threshold.",
                    "anomaly-investigation-agent",
                    evolution.metrics.anomaly_growth,
                    policy.anomaly_escalation_threshold,
                )
            )
        if evolution.metrics.policy_drift > policy.policy_drift_limit:
            events.append(
                self._event(
                    "policy_drift",
                    product_id,
                    "Cognitive policy drift exceeded the approved limit.",
                    "evolution-monitoring-agent",
                    evolution.metrics.policy_drift,
                    policy.policy_drift_limit,
                )
            )
        if evolution.metrics.confidence_volatility > 0.18 or alignment.health.confidence_integrity < 0.72:
            observed = max(evolution.metrics.confidence_volatility, 1 - alignment.health.confidence_integrity)
            events.append(
                self._event(
                    "confidence_inflation",
                    product_id,
                    "Confidence stability is weak enough to trigger audit.",
                    "confidence-audit-agent",
                    observed,
                    0.18,
                )
            )
        if alignment.status != "aligned" or alignment.violations:
            max_confidence = max((violation.confidence_score for violation in alignment.violations), default=1 - alignment.health.overall_alignment)
            events.append(
                CognitionEvent(
                    kind="alignment_drift",
                    severity="critical" if alignment.status in {"misaligned", "violated"} else "warning",
                    product_id=product_id,
                    source="alignment-integrity-agent",
                    message="Alignment inspection emitted violations or non-aligned status.",
                    payload={
                        "alignment_status": alignment.status,
                        "violation_count": len(alignment.violations),
                    },
                    priority_score=_clip(0.72 + max_confidence * 0.25),
                )
            )
        if not alignment.ethics.ethics_passed or alignment.ethics.unsafe_recommendation_risk >= 0.34:
            events.append(
                CognitionEvent(
                    kind="recommendation_risk",
                    severity="critical" if alignment.ethics.unsafe_recommendation_risk >= 0.52 else "warning",
                    product_id=product_id,
                    source="recommendation-verification-agent",
                    message="Recommendation ethics assessment requires autonomous verification.",
                    payload=alignment.ethics.model_dump(mode="json"),
                    priority_score=_clip(0.64 + alignment.ethics.unsafe_recommendation_risk * 0.3),
                )
            )
        if evolution.metrics.graph_mutation_velocity >= 0.42 or alignment.health.governance_alignment < 0.68:
            events.append(
                CognitionEvent(
                    kind="graph_pollution",
                    severity="warning",
                    product_id=product_id,
                    source="governance-stability-agent",
                    message="Graph mutation velocity or governance alignment requires hygiene review.",
                    payload={
                        "graph_mutation_velocity": evolution.metrics.graph_mutation_velocity,
                        "governance_alignment": alignment.health.governance_alignment,
                    },
                    priority_score=_clip(0.45 + evolution.metrics.graph_mutation_velocity * 0.3),
                )
            )
        return events

    def _event(
        self,
        kind,
        product_id: str,
        message: str,
        source: str,
        observed: float,
        threshold: float,
        *,
        lower_is_bad: bool = False,
    ) -> CognitionEvent:
        margin = threshold - observed if lower_is_bad else observed - threshold
        severity = "critical" if margin >= 0.18 else "warning"
        priority_floor = {
            "benchmark_contradiction": 0.78,
            "stale_evidence": 0.58,
            "anomaly_spike": 0.72,
            "policy_drift": 0.68,
        }.get(kind, 0.55)
        return CognitionEvent(
            kind=kind,
            severity=severity,
            product_id=product_id,
            source=source,
            message=message,
            payload={"observed": round(observed, 4), "threshold": round(threshold, 4)},
            priority_score=_clip(priority_floor + max(margin, 0) * 0.7),
        )

    def tasks(
        self,
        events: list[CognitionEvent],
        alignment: AlignmentInspectionReport,
        evolution: EvolutionOrchestrationReport,
    ) -> list[AgentTask]:
        mapping = {
            "scheduled_tick": ("telemetry", "monitor_telemetry", "monitor telemetry and coverage state"),
            "new_telemetry": ("telemetry", "monitor_telemetry", "process new telemetry through governed reasoning"),
            "stale_evidence": ("telemetry", "refresh_telemetry", "refresh stale or missing telemetry evidence"),
            "benchmark_contradiction": ("benchmark_validation", "validate_benchmark", "validate contradictory benchmark evidence"),
            "driver_regression": ("benchmark_validation", "validate_benchmark", "revalidate driver-sensitive workload behavior"),
            "anomaly_spike": ("anomaly_investigation", "investigate_anomaly", "open recurring anomaly investigation"),
            "confidence_inflation": ("confidence_audit", "audit_confidence", "audit confidence inflation and evidence sufficiency"),
            "policy_drift": ("evolution_monitoring", "monitor_evolution", "monitor policy drift and prepare rollback path"),
            "alignment_drift": ("alignment_integrity", "enforce_alignment", "enforce cognitive constitution and objective hierarchy"),
            "recommendation_risk": ("recommendation_verification", "verify_recommendation", "verify recommendation safety before ranking"),
            "graph_pollution": ("governance_stability", "stabilize_governance", "review graph hygiene and polluted evidence risk"),
        }
        tasks: list[AgentTask] = []
        for event in events:
            agent_kind, task_kind, reason = mapping[event.kind]
            requires_approval = event.kind in {"policy_drift", "graph_pollution"} and event.severity == "critical"
            status = "requires_approval" if requires_approval else "queued"
            if event.kind == "scheduled_tick" and alignment.status == "aligned" and evolution.status == "healthy":
                status = "completed"
            tasks.append(
                AgentTask(
                    agent_kind=agent_kind,  # type: ignore[arg-type]
                    kind=task_kind,  # type: ignore[arg-type]
                    status=status,  # type: ignore[arg-type]
                    product_id=event.product_id,
                    priority_score=event.priority_score,
                    triggered_by_event_id=event.id,
                    reason=reason,
                    expected_actions=self.expected_actions(event.kind),
                    requires_human_approval=requires_approval,
                )
            )
        return sorted(tasks, key=lambda item: item.priority_score, reverse=True)[:24]

    def expected_actions(self, event_kind: str) -> list[str]:
        actions = {
            "stale_evidence": ["queue telemetry refresh", "preserve last valid snapshot", "mark freshness constraint"],
            "benchmark_contradiction": ["compare evidence methods", "request independent revalidation", "downgrade confidence"],
            "anomaly_spike": ["cluster recurring anomaly patterns", "correlate workload and hardware family"],
            "confidence_inflation": ["apply confidence ceiling", "block self-generated trust growth"],
            "policy_drift": ["escalate to human governance", "prepare rollback candidate"],
            "alignment_drift": ["apply constitution guardrail", "block unsafe recommendation path"],
            "recommendation_risk": ["downgrade recommendation certainty", "surface ethics risk"],
            "graph_pollution": ["review graph hygiene", "quarantine through approval gate"],
        }
        return actions.get(event_kind, ["record cognition event", "maintain audit trail"])

    def signals(self, tasks: list[AgentTask], events: list[CognitionEvent]) -> list[AgentSignal]:
        event_by_id = {event.id: event for event in events}
        signals: list[AgentSignal] = []
        routes = {
            "anomaly_investigation": ("confidence_audit", "reasoning_notification"),
            "benchmark_validation": ("governance_stability", "governance_signal"),
            "alignment_integrity": ("recommendation_verification", "governance_signal"),
            "telemetry": ("benchmark_validation", "event_queue"),
            "evolution_monitoring": ("alignment_integrity", "graph_event"),
            "governance_stability": ("alignment_integrity", "graph_event"),
        }
        for task in tasks:
            route = routes.get(task.agent_kind)
            if not route:
                continue
            to_agent, channel = route
            event = event_by_id.get(task.triggered_by_event_id or "")
            signals.append(
                AgentSignal(
                    from_agent=task.agent_kind,
                    to_agent=to_agent,  # type: ignore[arg-type]
                    channel=channel,  # type: ignore[arg-type]
                    event_id=task.triggered_by_event_id,
                    message=f"{task.kind.replace('_', ' ')} requires downstream review.",
                    priority_score=event.priority_score if event else task.priority_score,
                )
            )
        return signals[:18]

    def investigations(
        self,
        events: list[CognitionEvent],
        alignment: AlignmentInspectionReport,
        evolution: EvolutionOrchestrationReport,
    ) -> list[InvestigationRecord]:
        investigations: list[InvestigationRecord] = []
        for event in events:
            if event.kind not in {"anomaly_spike", "benchmark_contradiction", "driver_regression", "graph_pollution", "alignment_drift"}:
                continue
            findings = [
                f"priority={event.priority_score:.2f}",
                f"severity={event.severity}",
                f"alignment={alignment.status}",
                f"evolution={evolution.status}",
            ]
            evidence = [
                "alignment-report",
                "evolution-orchestration",
                "reasoning-governance",
            ]
            if alignment.violations:
                findings.append(f"{len(alignment.violations)} alignment violation(s) active")
            investigations.append(
                InvestigationRecord(
                    product_id=event.product_id,
                    agent_kind=self.agent_for_event(event.kind),
                    status="escalated" if event.severity == "critical" else "open",
                    hypothesis=self.hypothesis(event.kind),
                    evidence_sources=evidence,
                    correlated_signals=[event.id],
                    findings=findings,
                    recommended_resolution=self.expected_actions(event.kind),
                    confidence_score=_clip(event.priority_score * 0.85 + alignment.health.overall_alignment * 0.15),
                )
            )
        return investigations[:12]

    def interventions(
        self,
        events: list[CognitionEvent],
        tasks: list[AgentTask],
        alignment: AlignmentInspectionReport,
        evolution: EvolutionOrchestrationReport,
    ) -> list[AutonomousIntervention]:
        interventions: list[AutonomousIntervention] = []
        product_id = alignment.product_id
        for event in events:
            if event.kind == "confidence_inflation":
                interventions.append(
                    AutonomousIntervention(
                        kind="confidence_reduction",
                        status="applied",
                        agent_kind="confidence_audit",
                        target=product_id,
                        severity=event.severity,
                        reason="Governed confidence ceiling applied before recommendation ranking.",
                        confidence_delta=-_clip(1 - alignment.health.confidence_integrity, 0, 0.35),
                    )
                )
            if event.kind == "stale_evidence":
                interventions.append(
                    AutonomousIntervention(
                        kind="telemetry_refresh",
                        status="queued",
                        agent_kind="telemetry",
                        target=product_id,
                        severity=event.severity,
                        reason="Telemetry refresh queued while preserving the last valid snapshot.",
                    )
                )
            if event.kind in {"benchmark_contradiction", "driver_regression"}:
                interventions.append(
                    AutonomousIntervention(
                        kind="revalidation_request",
                        status="queued",
                        agent_kind="benchmark_validation",
                        target=product_id,
                        severity=event.severity,
                        reason="Independent benchmark revalidation requested before confidence can increase.",
                    )
                )
            if event.kind == "anomaly_spike":
                interventions.append(
                    AutonomousIntervention(
                        kind="revalidation_request",
                        status="queued",
                        agent_kind="anomaly_investigation",
                        target=product_id,
                        severity=event.severity,
                        reason="Anomaly investigation opened for workload and hardware-family correlation.",
                    )
                )
            if event.kind == "recommendation_risk":
                interventions.append(
                    AutonomousIntervention(
                        kind="recommendation_downgrade",
                        status="applied",
                        agent_kind="recommendation_verification",
                        target=product_id,
                        severity=event.severity,
                        reason="Recommendation certainty downgraded until ethics risks fall below threshold.",
                        confidence_delta=-_clip(
                            max(
                                alignment.ethics.misleading_confidence_risk,
                                alignment.ethics.unsafe_recommendation_risk,
                                alignment.ethics.biased_optimization_risk,
                            )
                            * 0.32
                        ),
                    )
                )
            if event.kind == "alignment_drift":
                interventions.append(
                    AutonomousIntervention(
                        kind="constitution_guardrail",
                        status="applied" if event.severity != "critical" else "blocked",
                        agent_kind="alignment_integrity",
                        target=product_id,
                        severity=event.severity,
                        reason="Cognitive constitution prevents unsafe optimization paths from overriding alignment.",
                    )
                )
            if event.kind == "graph_pollution":
                interventions.append(
                    AutonomousIntervention(
                        kind="evidence_quarantine",
                        status="requires_approval",
                        agent_kind="governance_stability",
                        target=product_id,
                        severity=event.severity,
                        reason="Evidence quarantine requires human governance approval before graph mutation.",
                        requires_human_approval=True,
                    )
                )
            if event.kind == "policy_drift":
                interventions.append(
                    AutonomousIntervention(
                        kind="policy_escalation",
                        status="requires_approval",
                        agent_kind="evolution_monitoring",
                        target=evolution.active_policy.id,
                        severity=event.severity,
                        reason="Policy drift escalation prepared for human oversight.",
                        requires_human_approval=True,
                    )
                )
                if any(rollback.status in {"recommended", "requires_approval"} for rollback in evolution.rollback_events):
                    interventions.append(
                        AutonomousIntervention(
                            kind="evolution_rollback",
                            status="requires_approval",
                            agent_kind="evolution_monitoring",
                            target=evolution.active_policy.id,
                            severity="critical",
                            reason="Rollback path is available but cannot be applied without approval.",
                            requires_human_approval=True,
                        )
                    )
        if not interventions and all(task.status == "completed" for task in tasks):
            interventions.append(
                AutonomousIntervention(
                    kind="recommendation_downgrade",
                    status="recommended",
                    agent_kind="recommendation_verification",
                    target=product_id,
                    severity="info",
                    reason="No autonomous corrective action is required; recommendation guard remains available.",
                )
            )
        return interventions[:16]

    def oversight(
        self,
        interventions: list[AutonomousIntervention],
        investigations: list[InvestigationRecord],
        alignment: AlignmentInspectionReport,
        evolution: EvolutionOrchestrationReport,
    ) -> list[HumanOversightAction]:
        actions = [
            HumanOversightAction(
                action_type="inspect_agent_action",
                target=alignment.product_id,
                reason="Inspect autonomous agent queue, signals, and interventions.",
            ),
            HumanOversightAction(
                action_type="review_investigation",
                status="required" if any(item.status == "escalated" for item in investigations) else "available",
                target=alignment.product_id,
                reason="Review escalated investigations before graph quarantine or rollback.",
            ),
        ]
        if any(item.requires_human_approval for item in interventions):
            actions.append(
                HumanOversightAction(
                    action_type="approve_policy_escalation",
                    status="required",
                    target=evolution.active_policy.id,
                    reason="One or more autonomous interventions require governance approval.",
                )
            )
        if any(item.kind == "evolution_rollback" for item in interventions):
            actions.append(
                HumanOversightAction(
                    action_type="approve_rollback",
                    status="required",
                    target=evolution.active_policy.id,
                    reason="Autonomous rollback preparation cannot execute without human approval.",
                )
            )
        return actions[:8]

    def health(
        self,
        agents: list[AgentDefinition],
        events: list[CognitionEvent],
        tasks: list[AgentTask],
        interventions: list[AutonomousIntervention],
        alignment: AlignmentInspectionReport,
        evolution: EvolutionOrchestrationReport,
    ) -> AutonomousHealthIndex:
        active_agents = sum(agent.status == "active" for agent in agents)
        agent_availability = _clip(active_agents / max(len(agents), 1))
        unresolved = sum(task.status in {"queued", "running", "requires_approval"} for task in tasks)
        queue_pressure = _clip(unresolved / max(len(tasks), 1))
        critical_events = sum(event.severity == "critical" for event in events)
        contradiction_events = sum(event.kind in {"benchmark_contradiction", "driver_regression"} for event in events)
        applied = sum(intervention.status == "applied" for intervention in interventions)
        blocked = sum(intervention.status in {"blocked", "requires_approval"} for intervention in interventions)
        safety = _clip(alignment.health.safety_priority_score - critical_events * 0.06)
        contradiction_resolution = _clip(1 - evolution.metrics.contradiction_propagation - contradiction_events * 0.08)
        telemetry = evolution.health_index.evidence_freshness
        governance = _clip(alignment.health.governance_alignment * (1 - evolution.metrics.policy_drift * 0.35))
        intervention_effectiveness = _clip(0.72 + applied * 0.05 - blocked * 0.08 - queue_pressure * 0.14)
        overall = _clip(
            safety * 0.25
            + contradiction_resolution * 0.18
            + telemetry * 0.14
            + governance * 0.18
            + intervention_effectiveness * 0.14
            + agent_availability * 0.07
            + (1 - queue_pressure) * 0.04
        )
        return AutonomousHealthIndex(
            agent_availability=agent_availability,
            queue_pressure=queue_pressure,
            safety_stability_score=safety,
            contradiction_resolution_score=contradiction_resolution,
            telemetry_freshness_score=telemetry,
            governance_compliance_score=governance,
            intervention_effectiveness=intervention_effectiveness,
            overall_autonomy_health=overall,
        )

    def status(
        self,
        health: AutonomousHealthIndex,
        events: list[CognitionEvent],
        interventions: list[AutonomousIntervention],
        alignment: AlignmentInspectionReport,
    ):
        if alignment.status == "violated" or any(item.status == "blocked" for item in interventions):
            return "blocked"
        if any(event.severity == "critical" for event in events) or health.overall_autonomy_health < 0.52:
            return "degraded"
        if health.queue_pressure > 0.45 or health.overall_autonomy_health < 0.74:
            return "watch"
        return "active"

    def agent_statuses(
        self,
        agents: list[AgentDefinition],
        tasks: list[AgentTask],
        events: list[CognitionEvent],
    ) -> list[AgentDefinition]:
        busy = {task.agent_kind for task in tasks if task.status in {"queued", "running", "requires_approval"}}
        critical = {self.agent_for_event(event.kind) for event in events if event.severity == "critical"}
        statuses: list[AgentDefinition] = []
        for agent in agents:
            if agent.kind in critical:
                status = "degraded"
            elif agent.kind in busy:
                status = "investigating"
            else:
                status = "active"
            statuses.append(agent.model_copy(update={"status": status}))
        return statuses

    def agent_for_event(self, kind: str):
        return {
            "scheduled_tick": "telemetry",
            "new_telemetry": "telemetry",
            "stale_evidence": "telemetry",
            "benchmark_contradiction": "benchmark_validation",
            "driver_regression": "benchmark_validation",
            "anomaly_spike": "anomaly_investigation",
            "confidence_inflation": "confidence_audit",
            "policy_drift": "evolution_monitoring",
            "alignment_drift": "alignment_integrity",
            "recommendation_risk": "recommendation_verification",
            "graph_pollution": "governance_stability",
        }.get(kind, "governance_stability")

    def hypothesis(self, kind: str) -> str:
        return {
            "anomaly_spike": "Recurring workload instability may indicate thermal, driver, memory, or bandwidth pressure.",
            "benchmark_contradiction": "Telemetry and benchmark sources disagree enough to weaken recommendation confidence.",
            "driver_regression": "Driver-sensitive workloads may have regressed under the current software stack.",
            "graph_pollution": "Low-trust or unstable evidence may be influencing the graph.",
            "alignment_drift": "Recommendation optimization may be drifting away from protected objective hierarchy.",
        }.get(kind, "Autonomous cognition event requires governed investigation.")

    def summary(
        self,
        health: AutonomousHealthIndex,
        events: list[CognitionEvent],
        tasks: list[AgentTask],
        interventions: list[AutonomousIntervention],
    ) -> list[str]:
        lines = [
            f"Autonomous health {health.overall_autonomy_health:.0%}; queue pressure {health.queue_pressure:.0%}.",
            f"{len(events)} cognition event(s), {len(tasks)} agent task(s), {len(interventions)} intervention(s) evaluated.",
        ]
        critical = [event for event in events if event.severity == "critical"]
        if critical:
            lines.append(f"{len(critical)} critical event(s) require governed review.")
        applied = [item for item in interventions if item.status == "applied"]
        if applied:
            lines.append(f"{len(applied)} reversible intervention(s) applied inside alignment constraints.")
        approvals = [item for item in interventions if item.requires_human_approval]
        if approvals:
            lines.append(f"{len(approvals)} intervention(s) require human approval before graph mutation.")
        return lines[:5]
