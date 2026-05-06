from __future__ import annotations

from app.models.alignment import (
    AlignmentAuditEvent,
    AlignmentHealthIndex,
    AlignmentInspectionReport,
    AlignmentRollbackEvent,
    AlignmentViolation,
    CognitiveConstitution,
    ObjectivePriority,
    ObjectiveTradeoff,
    RecommendationEthicsAssessment,
    SystemIdentity,
)
from app.models.evolution import EvolutionOrchestrationReport


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return round(max(lower, min(upper, value)), 4)


def default_identity() -> SystemIdentity:
    objectives = [
        ObjectivePriority(
            name="correctness",
            rank=1,
            weight=1.0,
            description="Return compatible, evidence-backed, technically correct recommendations.",
        ),
        ObjectivePriority(
            name="safety_stability",
            rank=2,
            weight=0.94,
            description="Preserve thermal, power, mechanical, and long-term configuration stability.",
        ),
        ObjectivePriority(
            name="evidence_quality",
            rank=3,
            weight=0.88,
            description="Prefer validated, fresh, attributable evidence over inferred or popular claims.",
        ),
        ObjectivePriority(
            name="transparency",
            rank=4,
            weight=0.76,
            description="Expose uncertainty, assumptions, tradeoffs, contradictions, and confidence limits.",
        ),
        ObjectivePriority(
            name="optimization_quality",
            rank=5,
            weight=0.64,
            description="Optimize value, efficiency, longevity, and user intent inside safe constraints.",
        ),
        ObjectivePriority(
            name="performance_maximization",
            rank=6,
            weight=0.48,
            description="Maximize performance only after correctness, safety, evidence, and transparency are satisfied.",
        ),
    ]
    constitution = CognitiveConstitution(
        non_overridable_constraints=[
            "never optimize for performance while ignoring safety",
            "never hide uncertainty",
            "never overfit toward benchmark scores",
            "never maximize confidence without evidence",
            "never prioritize popularity over correctness",
        ],
        protected_governance_rules=[
            "confidence ceilings cannot be bypassed by recommendation ranking",
            "self-generated conclusions cannot recursively validate themselves",
            "policy rollback must remain available when instability is detected",
            "canonical compatibility constraints cannot be weakened by optimization pressure",
        ],
        safety_principles=[
            "insufficient PSU, thermal, clearance, bandwidth, or socket evidence blocks confident recommendations",
            "contradictory telemetry must reduce certainty",
            "missing data must be shown as uncertainty, not converted into confidence",
        ],
    )
    return SystemIdentity(
        purpose="produce transparent, compatible, evidence-governed PC hardware recommendations",
        core_reasoning_principles=[
            "compatibility constraints outrank performance",
            "evidence quality outranks popularity and benchmark hype",
            "uncertainty is surfaced rather than hidden",
            "optimization is multi-objective and bounded by safety",
            "human oversight remains available for policy and rollback decisions",
        ],
        optimization_priorities=objectives,
        trust_boundaries=[
            "self-generated reasoning is capped and cannot become primary evidence",
            "stale telemetry decays unless validated",
            "candidate policies require audit before promotion",
            "experimental reasoning strategies stay sandboxed until proven stable",
        ],
        recommendation_ethics=[
            "do not imply certainty where evidence is weak",
            "do not recommend unstable configurations for short-term benchmark gains",
            "do not let popularity override validated correctness",
            "explain tradeoffs and risks in user-visible language",
        ],
        uncertainty_handling=[
            "represent low evidence as low confidence and high uncertainty",
            "carry contradictions into recommendation explanations",
            "lower confidence when telemetry coverage is narrow",
        ],
        optimizes_for=[
            "valid compatibility",
            "thermal and power stability",
            "evidence-backed performance",
            "user intent within budget",
            "future-proofing when it does not violate correctness",
        ],
        avoids=[
            "unsafe PSU margins",
            "hidden bottlenecks",
            "benchmark-only recommendations",
            "recursive confidence inflation",
            "unapproved policy drift",
        ],
        acceptable_tradeoffs=[
            "slightly lower FPS for materially better stability",
            "higher cost when it prevents unsafe power or thermal margins",
            "lower confidence when evidence is stale or contradictory",
            "delayed optimization when fresh validation is required",
        ],
        constitution=constitution,
    )


class CognitiveAlignmentEngine:
    def inspect(
        self,
        product_id: str,
        evolution: EvolutionOrchestrationReport,
        identity: SystemIdentity | None = None,
    ) -> AlignmentInspectionReport:
        identity = identity or default_identity()
        violations = self.violations(evolution, identity)
        tradeoffs = self.tradeoffs(evolution, identity)
        ethics = self.ethics(evolution, violations)
        health = self.health(evolution, identity, violations, ethics)
        status = self.status(health, violations, ethics)
        rollback = self.rollback_events(evolution, violations, status)
        audit = self.audit_events(identity, violations, ethics, rollback)
        return AlignmentInspectionReport(
            product_id=product_id,
            status=status,
            identity=identity,
            health=health,
            tradeoffs=tradeoffs,
            violations=violations,
            ethics=ethics,
            rollback=rollback,
            audit_trail=audit,
            alignment_summary=self.summary(health, violations, ethics, evolution),
        )

    def violations(
        self,
        evolution: EvolutionOrchestrationReport,
        identity: SystemIdentity,
    ) -> list[AlignmentViolation]:
        policy = evolution.active_policy
        metrics = evolution.metrics
        health = evolution.health_index
        violations: list[AlignmentViolation] = []
        if policy.recommendation_aggressiveness > 0.74 and health.evidence_freshness < policy.evidence_freshness_min:
            violations.append(
                AlignmentViolation(
                    kind="safety_ignored",
                    severity="critical",
                    confidence_score=0.82,
                    explanation="Recommendation aggressiveness is high while evidence freshness is below policy.",
                    affected_objectives=["safety_stability", "evidence_quality", "performance_maximization"],
                    mitigation=["lower recommendation aggressiveness", "require fresh validation before performance ranking"],
                )
            )
        if policy.confidence_ceiling_max > 0.92 and health.evidence_freshness < 0.58:
            violations.append(
                AlignmentViolation(
                    kind="confidence_without_evidence",
                    severity="critical",
                    confidence_score=0.78,
                    explanation="Confidence ceiling is permissive relative to available evidence freshness.",
                    affected_objectives=["correctness", "evidence_quality", "transparency"],
                    mitigation=["restore conservative confidence ceiling", "preserve uncertainty display"],
                )
            )
        if metrics.policy_drift > policy.policy_drift_limit:
            violations.append(
                AlignmentViolation(
                    kind="policy_incoherence",
                    severity="warning",
                    confidence_score=_clip(0.5 + metrics.policy_drift),
                    explanation="Active policy has drifted beyond its own allowed policy drift envelope.",
                    affected_objectives=["correctness", "safety_stability", "transparency"],
                    mitigation=["require policy review", "prepare alignment rollback"],
                )
            )
        if metrics.confidence_volatility > 0.34 or metrics.adaptation_pressure > policy.adaptation_rate_limit * 1.8:
            violations.append(
                AlignmentViolation(
                    kind="objective_drift",
                    severity="warning",
                    confidence_score=_clip(0.52 + metrics.adaptation_pressure * 0.4),
                    explanation="Adaptation pressure or confidence volatility suggests emerging objective drift.",
                    affected_objectives=["correctness", "safety_stability", "optimization_quality"],
                    mitigation=["slow adaptation", "hold candidate model promotion"],
                )
            )
        if health.anomaly_pressure > policy.anomaly_escalation_threshold and policy.recommendation_aggressiveness > 0.62:
            violations.append(
                AlignmentViolation(
                    kind="benchmark_overfit",
                    severity="warning",
                    confidence_score=_clip(0.55 + health.anomaly_pressure * 0.3),
                    explanation="Anomaly pressure is high while optimization remains aggressive.",
                    affected_objectives=["evidence_quality", "transparency", "performance_maximization"],
                    mitigation=["reduce benchmark weighting", "prioritize stability evidence"],
                )
            )
        if any(event.status in {"recommended", "requires_approval"} for event in evolution.rollback_events) and not policy.requires_human_approval:
            violations.append(
                AlignmentViolation(
                    kind="governance_fragmentation",
                    severity="critical",
                    confidence_score=0.86,
                    explanation="Rollback is needed but policy does not require human approval.",
                    affected_objectives=["transparency", "correctness", "safety_stability"],
                    mitigation=["restore human approval requirement", "freeze policy promotion"],
                )
            )
        return violations[:8]

    def tradeoffs(self, evolution: EvolutionOrchestrationReport, identity: SystemIdentity) -> list[ObjectiveTradeoff]:
        policy = evolution.active_policy
        return [
            ObjectiveTradeoff(
                primary_objective="safety_stability",
                competing_objective="performance_maximization",
                acceptable=policy.recommendation_aggressiveness <= 0.68,
                confidence_score=_clip(1 - policy.recommendation_aggressiveness),
                resolution="performance may increase only inside governed confidence, thermal, power, and evidence constraints",
            ),
            ObjectiveTradeoff(
                primary_objective="evidence_quality",
                competing_objective="optimization_quality",
                acceptable=evolution.health_index.evidence_freshness >= policy.evidence_freshness_min,
                confidence_score=evolution.health_index.evidence_freshness,
                resolution="optimization is throttled until fresh evidence reaches policy threshold",
            ),
            ObjectiveTradeoff(
                primary_objective="transparency",
                competing_objective="performance_maximization",
                acceptable=not any(decision.status == "block" for decision in evolution.enforcement),
                confidence_score=_clip(1 - evolution.metrics.policy_drift),
                resolution="blocked policy rules must remain visible before performance claims are promoted",
            ),
        ]

    def ethics(
        self,
        evolution: EvolutionOrchestrationReport,
        violations: list[AlignmentViolation],
    ) -> RecommendationEthicsAssessment:
        misleading = _clip(
            evolution.metrics.confidence_volatility * 0.35
            + evolution.metrics.policy_drift * 0.25
            + (1 - evolution.health_index.evidence_freshness) * 0.24
            + len([item for item in violations if item.kind == "uncertainty_hidden"]) * 0.16
        )
        unsafe = _clip(
            evolution.metrics.contradiction_propagation * 0.34
            + evolution.metrics.anomaly_growth * 0.22
            + max(0.0, evolution.active_policy.recommendation_aggressiveness - 0.55) * 0.44
        )
        unstable = _clip(evolution.metrics.adaptation_pressure * 0.46 + evolution.metrics.graph_mutation_velocity * 0.28 + evolution.metrics.intervention_rate * 0.26)
        biased = _clip(
            max(0.0, evolution.active_policy.recommendation_aggressiveness - evolution.active_policy.contradiction_tolerance) * 0.52
            + evolution.metrics.policy_drift * 0.28
            + evolution.metrics.anomaly_growth * 0.2
        )
        notes = []
        if misleading > 0.45:
            notes.append("confidence claims require stronger uncertainty disclosure")
        if unsafe > 0.45:
            notes.append("safety/stability must outrank performance optimization")
        if unstable > 0.45:
            notes.append("adaptation should be throttled until behavior stabilizes")
        if biased > 0.45:
            notes.append("optimization path may be biased toward aggressive performance")
        return RecommendationEthicsAssessment(
            misleading_confidence_risk=misleading,
            unsafe_recommendation_risk=unsafe,
            unstable_configuration_risk=unstable,
            biased_optimization_risk=biased,
            ethics_passed=max(misleading, unsafe, unstable, biased) < 0.62 and not any(v.severity == "critical" for v in violations),
            notes=notes,
        )

    def health(
        self,
        evolution: EvolutionOrchestrationReport,
        identity: SystemIdentity,
        violations: list[AlignmentViolation],
        ethics: RecommendationEthicsAssessment,
    ) -> AlignmentHealthIndex:
        critical_penalty = sum(violation.severity == "critical" for violation in violations) * 0.12
        warning_penalty = sum(violation.severity == "warning" for violation in violations) * 0.05
        identity_stability = _clip(1 - evolution.metrics.policy_drift - critical_penalty * 0.35)
        objective_coherence = _clip(
            1
            - evolution.metrics.adaptation_pressure * 0.35
            - warning_penalty
            - critical_penalty
        )
        optimization_consistency = _clip(
            1
            - max(0.0, evolution.active_policy.recommendation_aggressiveness - 0.55) * 0.55
            - evolution.metrics.anomaly_growth * 0.22
            - evolution.metrics.contradiction_propagation * 0.23
        )
        governance_alignment = _clip(evolution.health_index.policy_alignment * 0.55 + evolution.health_index.graph_health * 0.45)
        confidence_integrity = _clip(
            1
            - evolution.metrics.confidence_volatility * 0.38
            - (1 - evolution.health_index.evidence_freshness) * 0.28
            - evolution.metrics.contradiction_propagation * 0.24
            - critical_penalty * 0.1
        )
        transparency_score = _clip(
            1
            - ethics.misleading_confidence_risk * 0.42
            - evolution.metrics.policy_drift * 0.18
            - warning_penalty * 0.2
        )
        safety_priority_score = _clip(
            1
            - ethics.unsafe_recommendation_risk * 0.5
            - max(0.0, evolution.active_policy.recommendation_aggressiveness - 0.6) * 0.28
            - critical_penalty * 0.22
        )
        overall = _clip(
            identity_stability * 0.16
            + objective_coherence * 0.15
            + optimization_consistency * 0.13
            + governance_alignment * 0.15
            + confidence_integrity * 0.16
            + transparency_score * 0.12
            + safety_priority_score * 0.13
        )
        return AlignmentHealthIndex(
            identity_stability=identity_stability,
            objective_coherence=objective_coherence,
            optimization_consistency=optimization_consistency,
            governance_alignment=governance_alignment,
            confidence_integrity=confidence_integrity,
            transparency_score=transparency_score,
            safety_priority_score=safety_priority_score,
            overall_alignment=overall,
        )

    def status(
        self,
        health: AlignmentHealthIndex,
        violations: list[AlignmentViolation],
        ethics: RecommendationEthicsAssessment,
    ):
        if any(violation.severity == "critical" for violation in violations) and health.overall_alignment < 0.52:
            return "violated"
        if any(violation.severity == "critical" for violation in violations) or not ethics.ethics_passed:
            return "misaligned"
        if violations or health.overall_alignment < 0.76:
            return "watch"
        return "aligned"

    def rollback_events(
        self,
        evolution: EvolutionOrchestrationReport,
        violations: list[AlignmentViolation],
        status: str,
    ) -> list[AlignmentRollbackEvent]:
        if status in {"misaligned", "violated"}:
            return [
                AlignmentRollbackEvent(
                    status="requires_approval",
                    trigger="alignment violation detected",
                    target_policy_id=evolution.active_policy.supersedes_policy_id,
                    reason="active policy or objective behavior conflicts with protected system identity",
                )
            ]
        return [
            AlignmentRollbackEvent(
                status="not_required",
                trigger="alignment checks passed",
                target_policy_id=None,
                reason="current objective hierarchy remains coherent",
            )
        ]

    def audit_events(
        self,
        identity: SystemIdentity,
        violations: list[AlignmentViolation],
        ethics: RecommendationEthicsAssessment,
        rollback: list[AlignmentRollbackEvent],
    ) -> list[AlignmentAuditEvent]:
        events = [
            AlignmentAuditEvent(
                event_type="identity_evaluated",
                severity="info",
                message=f"identity {identity.version} evaluated against protected constitution",
            ),
            AlignmentAuditEvent(
                event_type="objective_audited",
                severity="info",
                message=f"{len(identity.optimization_priorities)} objective priorities checked",
            ),
            AlignmentAuditEvent(
                event_type="ethics_checked",
                severity="info" if ethics.ethics_passed else "warning",
                message="recommendation ethics assessment completed",
            ),
            AlignmentAuditEvent(
                event_type="constitution_enforced",
                severity="info",
                message=f"{len(identity.constitution.non_overridable_constraints)} immutable constraints enforced",
            ),
        ]
        if violations:
            events.append(
                AlignmentAuditEvent(
                    event_type="violation_detected",
                    severity="critical" if any(item.severity == "critical" for item in violations) else "warning",
                    message=f"{len(violations)} alignment violation signal(s) detected",
                )
            )
        if any(item.status != "not_required" for item in rollback):
            events.append(
                AlignmentAuditEvent(
                    event_type="rollback_supported",
                    severity="critical",
                    message="alignment rollback path prepared for human oversight",
                )
            )
        return events

    def summary(
        self,
        health: AlignmentHealthIndex,
        violations: list[AlignmentViolation],
        ethics: RecommendationEthicsAssessment,
        evolution: EvolutionOrchestrationReport,
    ) -> list[str]:
        lines = [
            f"Alignment health {health.overall_alignment:.0%}; identity stability {health.identity_stability:.0%}.",
            f"Objective coherence {health.objective_coherence:.0%}, confidence integrity {health.confidence_integrity:.0%}, safety priority {health.safety_priority_score:.0%}.",
        ]
        if violations:
            lines.append(f"{len(violations)} alignment constraint signal(s) require review.")
        if not ethics.ethics_passed:
            lines.append("Recommendation ethics guardrails require lower certainty or safer tradeoffs.")
        if evolution.status in {"unstable", "quarantined"}:
            lines.append("Evolution state is unstable and must not promote reasoning behavior.")
        return lines[:5]
