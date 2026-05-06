from __future__ import annotations

from statistics import mean, pstdev
from typing import Iterable

from app.models.evolution import (
    CognitiveHealthIndex,
    CognitivePolicy,
    EvolutionAuditEvent,
    EvolutionMetrics,
    EvolutionOrchestrationReport,
    LongTermMemoryDecision,
    ModelPromotionDecision,
    PolicyEnforcementDecision,
    RollbackEvent,
    SandboxEvaluation,
)
from app.models.governance import ReasoningGovernanceReport


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return round(max(lower, min(upper, value)), 4)


def _avg(values: Iterable[float | None], default: float = 0.0) -> float:
    clean = [float(value) for value in values if value is not None]
    return round(mean(clean), 4) if clean else default


def _spread(values: Iterable[float | None]) -> float:
    clean = [float(value) for value in values if value is not None]
    if len(clean) < 2:
        return 0.0
    return _clip(pstdev(clean) / max(mean(clean), 1.0))


def default_policy() -> CognitivePolicy:
    return CognitivePolicy(id="cognitive-policy-default", version="1.0.0")


class EvolutionOrchestrator:
    def orchestrate(
        self,
        product_id: str,
        governance: ReasoningGovernanceReport,
        policy: CognitivePolicy | None = None,
        previous_report: EvolutionOrchestrationReport | None = None,
    ) -> EvolutionOrchestrationReport:
        active_policy = policy or default_policy()
        metrics = self.metrics(governance, active_policy, previous_report)
        health = self.health_index(governance, metrics)
        enforcement = self.enforcement_decisions(governance, active_policy, metrics)
        sandbox = self.sandbox_evaluations(governance, active_policy)
        promotions = self.promotion_decisions(sandbox, governance, active_policy)
        rollbacks = self.rollback_events(governance, active_policy, previous_report, metrics, enforcement)
        memory = self.memory_decisions(governance)
        status = self.status(governance, health, enforcement, rollbacks)
        audit = self.audit_events(enforcement, sandbox, promotions, rollbacks, memory)
        return EvolutionOrchestrationReport(
            product_id=product_id,
            status=status,
            active_policy=active_policy,
            health_index=health,
            metrics=metrics,
            enforcement=enforcement,
            sandbox_evaluations=sandbox,
            promotion_decisions=promotions,
            rollback_events=rollbacks,
            memory_decisions=memory,
            audit_trail=audit,
            orchestration_summary=self.summary(health, metrics, enforcement, rollbacks),
        )

    def metrics(
        self,
        governance: ReasoningGovernanceReport,
        policy: CognitivePolicy,
        previous_report: EvolutionOrchestrationReport | None,
    ) -> EvolutionMetrics:
        confidence_delta = 0.0
        policy_status_delta = 0.0
        if previous_report:
            confidence_delta = abs(
                governance.stability.governed_confidence
                - previous_report.health_index.reasoning_stability
            )
            policy_status_delta = 0.1 if previous_report.active_policy.id != policy.id else 0.0
        graph_mutation_velocity = _clip(
            (
                len(governance.graph_hygiene)
                + len(governance.stabilization_actions)
                + len(governance.evidence_decay) * 0.35
            )
            / 16
        )
        anomaly_growth = governance.metrics.anomaly_density
        contradiction_propagation = governance.metrics.contradiction_density
        confidence_volatility = _clip(
            governance.metrics.confidence_drift * 0.55 + governance.metrics.confidence_oscillation * 0.45
        )
        policy_drift = self.policy_drift(policy)
        evolution_velocity = _clip(
            confidence_delta * 0.35
            + graph_mutation_velocity * 0.25
            + anomaly_growth * 0.13
            + contradiction_propagation * 0.17
            + policy_status_delta
        )
        adaptation_pressure = _clip(
            evolution_velocity * 0.28
            + confidence_volatility * 0.22
            + contradiction_propagation * 0.18
            + governance.metrics.recursive_feedback_risk * 0.16
            + governance.metrics.evidence_decay_pressure * 0.16
        )
        intervention_rate = _clip(len(governance.stabilization_actions) / 10)
        return EvolutionMetrics(
            evolution_velocity=evolution_velocity,
            graph_mutation_velocity=graph_mutation_velocity,
            anomaly_growth=anomaly_growth,
            contradiction_propagation=contradiction_propagation,
            policy_drift=policy_drift,
            adaptation_pressure=adaptation_pressure,
            confidence_volatility=confidence_volatility,
            intervention_rate=intervention_rate,
        )

    def policy_drift(self, policy: CognitivePolicy) -> float:
        baseline = default_policy()
        differences = [
            abs(policy.confidence_ceiling_max - baseline.confidence_ceiling_max),
            abs(policy.evidence_freshness_min - baseline.evidence_freshness_min),
            abs(policy.contradiction_tolerance - baseline.contradiction_tolerance),
            abs(policy.anomaly_escalation_threshold - baseline.anomaly_escalation_threshold),
            abs(policy.adaptation_rate_limit - baseline.adaptation_rate_limit),
            abs(policy.recommendation_aggressiveness - baseline.recommendation_aggressiveness),
            abs(policy.self_generated_trust_cap - baseline.self_generated_trust_cap),
            abs(policy.telemetry_trust_growth_rate - baseline.telemetry_trust_growth_rate),
        ]
        return _clip(_avg(differences, 0))

    def health_index(self, governance: ReasoningGovernanceReport, metrics: EvolutionMetrics) -> CognitiveHealthIndex:
        reasoning_stability = _clip(1 - metrics.confidence_volatility)
        graph_health = governance.metrics.graph_integrity
        evidence_freshness = governance.metrics.telemetry_freshness
        contradiction_resilience = _clip(1 - metrics.contradiction_propagation)
        anomaly_pressure = metrics.anomaly_growth
        adaptation_volatility = _clip(1 - metrics.adaptation_pressure)
        policy_alignment = _clip(1 - metrics.policy_drift)
        index = _clip(
            reasoning_stability * 0.18
            + graph_health * 0.17
            + evidence_freshness * 0.13
            + contradiction_resilience * 0.16
            + (1 - anomaly_pressure) * 0.12
            + adaptation_volatility * 0.14
            + policy_alignment * 0.1
        )
        return CognitiveHealthIndex(
            reasoning_stability=reasoning_stability,
            graph_health=graph_health,
            evidence_freshness=evidence_freshness,
            contradiction_resilience=contradiction_resilience,
            anomaly_pressure=anomaly_pressure,
            adaptation_volatility=adaptation_volatility,
            policy_alignment=policy_alignment,
            index=index,
        )

    def enforcement_decisions(
        self,
        governance: ReasoningGovernanceReport,
        policy: CognitivePolicy,
        metrics: EvolutionMetrics,
    ) -> list[PolicyEnforcementDecision]:
        decisions = [
            self._decision(
                "confidence_ceiling",
                governance.stability.governed_confidence,
                policy.confidence_ceiling_max,
                over_limit_blocks=True,
                action="cap governed confidence before recommendation ranking",
            ),
            self._decision(
                "evidence_freshness",
                governance.metrics.telemetry_freshness,
                policy.evidence_freshness_min,
                over_limit_blocks=False,
                action="require fresh evidence before confidence growth",
            ),
            self._decision(
                "contradiction_tolerance",
                governance.metrics.contradiction_density,
                policy.contradiction_tolerance,
                over_limit_blocks=True,
                action="throttle adaptation and downgrade recommendations",
            ),
            self._decision(
                "anomaly_escalation",
                governance.metrics.anomaly_density,
                policy.anomaly_escalation_threshold,
                over_limit_blocks=True,
                action="escalate anomaly review before model promotion",
            ),
            self._decision(
                "adaptation_rate",
                metrics.adaptation_pressure,
                policy.adaptation_rate_limit,
                over_limit_blocks=True,
                action="smooth transition and delay policy promotion",
            ),
            self._decision(
                "self_generated_trust",
                governance.metrics.recursive_feedback_risk,
                policy.self_generated_trust_cap,
                over_limit_blocks=True,
                action="block recursive self-validation from increasing confidence",
            ),
            self._decision(
                "policy_drift",
                metrics.policy_drift,
                policy.policy_drift_limit,
                over_limit_blocks=True,
                action="require human approval before policy divergence",
            ),
        ]
        return decisions

    def _decision(
        self,
        rule,
        observed: float,
        threshold: float,
        *,
        over_limit_blocks: bool,
        action: str,
    ) -> PolicyEnforcementDecision:
        if over_limit_blocks:
            exceeded = observed > threshold
            margin = observed - threshold
        else:
            exceeded = observed < threshold
            margin = threshold - observed
        if not exceeded:
            status = "allow"
            severity = "info"
        elif margin >= 0.18:
            status = "block"
            severity = "critical"
        else:
            status = "throttle"
            severity = "warning"
        if rule in {"anomaly_escalation", "policy_drift"} and exceeded:
            status = "escalate"
        return PolicyEnforcementDecision(
            rule=rule,
            status=status,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            observed_value=_clip(observed),
            threshold=_clip(threshold),
            action=action,
        )

    def sandbox_evaluations(
        self,
        governance: ReasoningGovernanceReport,
        policy: CognitivePolicy,
    ) -> list[SandboxEvaluation]:
        evaluations: list[SandboxEvaluation] = []
        for score in governance.consensus:
            stability = _clip(
                score.confidence_score * 0.28
                + governance.metrics.graph_integrity * 0.22
                + (1 - governance.metrics.confidence_drift) * 0.2
                + (1 - governance.metrics.recursive_feedback_risk) * 0.15
                + (1 - score.disagreement_score) * 0.15
            )
            accuracy = _clip(
                governance.stability.governed_confidence * 0.45
                + governance.metrics.reasoning_quality * 0.35
                + (1 - governance.metrics.calibration_risk) * 0.2
            )
            contradiction_impact = _clip(governance.metrics.contradiction_density + score.disagreement_score * 0.35)
            consistency = _clip(
                governance.metrics.telemetry_freshness * 0.3
                + (1 - governance.metrics.evidence_decay_pressure) * 0.3
                + governance.metrics.graph_integrity * 0.4
            )
            ready = (
                stability >= 0.74
                and accuracy >= 0.62
                and contradiction_impact <= policy.contradiction_tolerance
                and consistency >= policy.evidence_freshness_min
            )
            evaluations.append(
                SandboxEvaluation(
                    model_id=f"strategy:{score.strategy}",
                    policy_id=policy.id,
                    stability_score=stability,
                    prediction_accuracy_score=accuracy,
                    contradiction_impact=contradiction_impact,
                    telemetry_consistency=consistency,
                    promotion_ready=ready,
                    rationale=(
                        "strategy remains isolated until stability, prediction accuracy, telemetry consistency, "
                        "and contradiction impact pass policy thresholds"
                    ),
                )
            )
        return evaluations

    def promotion_decisions(
        self,
        evaluations: list[SandboxEvaluation],
        governance: ReasoningGovernanceReport,
        policy: CognitivePolicy,
    ) -> list[ModelPromotionDecision]:
        decisions: list[ModelPromotionDecision] = []
        for evaluation in evaluations:
            if evaluation.contradiction_impact > policy.contradiction_tolerance * 1.7:
                status = "quarantine"
                reason = "sandbox strategy increases contradiction impact beyond quarantine threshold"
            elif not evaluation.promotion_ready:
                status = "hold"
                reason = "sandbox strategy has not proven stable enough for promotion"
            elif policy.requires_human_approval:
                status = "hold"
                reason = "promotion is ready but requires human governance approval"
            else:
                status = "promote"
                reason = "sandbox strategy satisfies policy and approval constraints"
            decisions.append(
                ModelPromotionDecision(
                    model_id=evaluation.model_id,
                    status=status,  # type: ignore[arg-type]
                    stability_delta=_clip(evaluation.stability_score - governance.metrics.overall_health, -1, 1),
                    contradiction_delta=_clip(evaluation.contradiction_impact - governance.metrics.contradiction_density, -1, 1),
                    prediction_accuracy=evaluation.prediction_accuracy_score,
                    reason=reason,
                    requires_approval=policy.requires_human_approval,
                )
            )
        return decisions

    def rollback_events(
        self,
        governance: ReasoningGovernanceReport,
        policy: CognitivePolicy,
        previous_report: EvolutionOrchestrationReport | None,
        metrics: EvolutionMetrics,
        enforcement: list[PolicyEnforcementDecision],
    ) -> list[RollbackEvent]:
        severe_enforcement = any(decision.status in {"block", "escalate"} for decision in enforcement)
        unstable = governance.status in {"unstable", "quarantined"} or metrics.adaptation_pressure >= policy.adaptation_rate_limit * 2
        if not severe_enforcement and not unstable:
            return [
                RollbackEvent(
                    status="not_required",
                    from_policy_id=policy.id,
                    to_policy_id=previous_report.active_policy.id if previous_report else None,
                    trigger="stability checks passed",
                    reason="current evolution remains inside governed policy envelope",
                )
            ]
        return [
            RollbackEvent(
                status="requires_approval" if policy.requires_human_approval else "recommended",
                from_policy_id=policy.id,
                to_policy_id=previous_report.active_policy.id if previous_report else policy.supersedes_policy_id,
                trigger="cognitive instability detected",
                reason="policy rollback is recommended before further graph mutation or model promotion",
            )
        ]

    def memory_decisions(self, governance: ReasoningGovernanceReport) -> list[LongTermMemoryDecision]:
        decisions: list[LongTermMemoryDecision] = []
        for record in governance.evidence_decay[:10]:
            if record.status == "quarantined":
                status = "archive"
            elif record.status in {"decayed", "stale"}:
                status = "decay"
            elif record.validation_support > 2 and record.statistical_stability >= 0.78:
                status = "strengthen"
            else:
                status = "retain"
            decisions.append(
                LongTermMemoryDecision(
                    target=record.source,
                    status=status,  # type: ignore[arg-type]
                    support_score=record.decayed_weight,
                    reason=record.reason,
                )
            )
        if not decisions:
            decisions.append(
                LongTermMemoryDecision(
                    target=governance.product_id,
                    status="retain",
                    support_score=governance.metrics.overall_health,
                    reason="no old cognition memory requires decay or archival yet",
                )
            )
        return decisions

    def status(
        self,
        governance: ReasoningGovernanceReport,
        health: CognitiveHealthIndex,
        enforcement: list[PolicyEnforcementDecision],
        rollbacks: list[RollbackEvent],
    ):
        if any(event.status in {"recommended", "requires_approval"} for event in rollbacks):
            return "unstable"
        if any(decision.status == "block" for decision in enforcement):
            return "unstable"
        if any(decision.status == "escalate" for decision in enforcement):
            return "degraded"
        if governance.status in {"degraded", "watch"} or health.index < 0.68:
            return "watch"
        return "healthy"

    def audit_events(
        self,
        enforcement: list[PolicyEnforcementDecision],
        sandbox: list[SandboxEvaluation],
        promotions: list[ModelPromotionDecision],
        rollbacks: list[RollbackEvent],
        memory: list[LongTermMemoryDecision],
    ) -> list[EvolutionAuditEvent]:
        events: list[EvolutionAuditEvent] = [
            EvolutionAuditEvent(
                event_type="policy_evaluated",
                severity="info",
                message=f"{len(enforcement)} policy rule(s) evaluated",
            )
        ]
        if any(decision.status in {"throttle", "block"} for decision in enforcement):
            events.append(
                EvolutionAuditEvent(
                    event_type="adaptation_throttled",
                    severity="warning",
                    message="policy enforcement throttled or blocked adaptation",
                )
            )
        events.append(
            EvolutionAuditEvent(
                event_type="sandbox_evaluated",
                severity="info",
                message=f"{len(sandbox)} isolated strategy evaluation(s) completed",
            )
        )
        if promotions:
            events.append(
                EvolutionAuditEvent(
                    event_type="promotion_reviewed",
                    severity="info",
                    message=f"{len(promotions)} promotion decision(s) recorded",
                )
            )
        if any(event.status in {"recommended", "requires_approval"} for event in rollbacks):
            events.append(
                EvolutionAuditEvent(
                    event_type="rollback_recommended",
                    severity="critical",
                    message="rollback path is available and awaits governance approval",
                )
            )
        if memory:
            events.append(
                EvolutionAuditEvent(
                    event_type="memory_governed",
                    severity="info",
                    message=f"{len(memory)} long-term memory decision(s) emitted",
                )
            )
        return events

    def summary(
        self,
        health: CognitiveHealthIndex,
        metrics: EvolutionMetrics,
        enforcement: list[PolicyEnforcementDecision],
        rollbacks: list[RollbackEvent],
    ) -> list[str]:
        lines = [
            f"Cognitive health index {health.index:.0%}; evolution velocity {metrics.evolution_velocity:.0%}.",
            f"Adaptation pressure {metrics.adaptation_pressure:.0%}, confidence volatility {metrics.confidence_volatility:.0%}, policy drift {metrics.policy_drift:.0%}.",
        ]
        blocked = [decision for decision in enforcement if decision.status in {"block", "escalate"}]
        if blocked:
            lines.append(f"{len(blocked)} policy rule(s) block or escalate evolution.")
        if any(event.status in {"recommended", "requires_approval"} for event in rollbacks):
            lines.append("Rollback path is prepared for governance approval.")
        return lines[:5]
