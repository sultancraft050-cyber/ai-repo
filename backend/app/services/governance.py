from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from math import exp
from statistics import mean, pstdev
from typing import Iterable

from app.models.cognition import (
    ContradictionSignal,
    HardwareCognitionReport,
    PredictionRecord,
    PredictionValidation,
)
from app.models.governance import (
    ConsensusStrategyScore,
    EvidenceDecayRecord,
    GraphHygieneSignal,
    ReasoningAuditTrail,
    ReasoningGovernanceReport,
    ReasoningHealthMetrics,
    StabilizationAction,
    StabilityControl,
)
from app.models.telemetry import TelemetryReasoningReport, TelemetrySnapshotView


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


class ReasoningGovernanceEngine:
    def govern(
        self,
        product_id: str,
        cognition: HardwareCognitionReport,
        snapshots: list[TelemetrySnapshotView],
        predictions: list[PredictionRecord],
        validations: list[PredictionValidation],
        contradictions: list[ContradictionSignal],
        reasoning: TelemetryReasoningReport | None = None,
    ) -> ReasoningGovernanceReport:
        evidence_decay = self.evidence_decay_records(snapshots, validations)
        confidence_drift = self.confidence_drift(cognition, predictions, validations)
        confidence_oscillation = self.confidence_oscillation(predictions, validations)
        contradiction_density = self.contradiction_density(cognition, predictions, validations, contradictions)
        telemetry_freshness = _avg((snapshot.freshness_score for snapshot in snapshots), 0.35)
        decay_pressure = self.decay_pressure(evidence_decay)
        recursive_risk = self.recursive_feedback_risk(cognition, predictions, validations, contradictions)
        anomaly_density = self.anomaly_density(reasoning, snapshots)
        coverage_gap = _clip(len(cognition.meta_reasoning.telemetry_gaps) / 6)
        calibration_risk = _clip(
            _avg((validation.confidence_error for validation in validations), cognition.reliability.calibration_error)
        )

        preliminary_signals = self.graph_hygiene_signals(
            product_id=product_id,
            evidence_decay=evidence_decay,
            confidence_drift=confidence_drift,
            confidence_oscillation=confidence_oscillation,
            contradiction_density=contradiction_density,
            recursive_risk=recursive_risk,
            decay_pressure=decay_pressure,
            consensus_disagreement=0,
        )
        graph_integrity = self.graph_integrity(preliminary_signals)
        reasoning_quality = _clip(
            cognition.confidence.evidence_strength * 0.28
            + cognition.reliability.reliability_score * 0.22
            + (1 - calibration_risk) * 0.16
            + (1 - contradiction_density) * 0.14
            + telemetry_freshness * 0.1
            + graph_integrity * 0.1
        )
        consensus = self.consensus_scores(
            cognition,
            telemetry_freshness,
            decay_pressure,
            calibration_risk,
            contradiction_density,
            recursive_risk,
        )
        consensus_disagreement = _spread(score.confidence_score for score in consensus)
        signals = self.graph_hygiene_signals(
            product_id=product_id,
            evidence_decay=evidence_decay,
            confidence_drift=confidence_drift,
            confidence_oscillation=confidence_oscillation,
            contradiction_density=contradiction_density,
            recursive_risk=recursive_risk,
            decay_pressure=decay_pressure,
            consensus_disagreement=consensus_disagreement,
        )
        graph_integrity = self.graph_integrity(signals)
        overall_health = _clip(
            reasoning_quality * 0.24
            + (1 - confidence_drift) * 0.11
            + (1 - confidence_oscillation) * 0.08
            + (1 - calibration_risk) * 0.12
            + (1 - contradiction_density) * 0.13
            + telemetry_freshness * 0.1
            + (1 - decay_pressure) * 0.08
            + graph_integrity * 0.09
            + (1 - recursive_risk) * 0.05
        )
        metrics = ReasoningHealthMetrics(
            reasoning_quality=reasoning_quality,
            confidence_drift=confidence_drift,
            confidence_oscillation=confidence_oscillation,
            calibration_risk=calibration_risk,
            contradiction_density=contradiction_density,
            telemetry_freshness=telemetry_freshness,
            evidence_decay_pressure=decay_pressure,
            graph_integrity=graph_integrity,
            recursive_feedback_risk=recursive_risk,
            anomaly_density=anomaly_density,
            coverage_gap_score=coverage_gap,
            overall_health=overall_health,
        )
        stability = self.stability_control(cognition, metrics, consensus, snapshots)
        status = self.status(metrics, signals, stability)
        actions = self.stabilization_actions(product_id, status, stability, evidence_decay, signals, metrics)
        return ReasoningGovernanceReport(
            product_id=product_id,
            status=status,
            metrics=metrics,
            stability=stability,
            evidence_decay=evidence_decay[:12],
            graph_hygiene=signals[:10],
            consensus=consensus,
            stabilization_actions=actions,
            audit_trail=self.audit_trail(cognition, predictions, validations, contradictions, reasoning),
            governance_summary=self.governance_summary(metrics, stability, signals, actions),
        )

    def evidence_decay_records(
        self,
        snapshots: list[TelemetrySnapshotView],
        validations: list[PredictionValidation],
    ) -> list[EvidenceDecayRecord]:
        now = datetime.now(UTC)
        fps_by_source: dict[str, list[float]] = defaultdict(list)
        source_counts = Counter(snapshot.source for snapshot in snapshots)
        validation_support = Counter(
            validation.product_id for validation in validations if validation.status in {"validated", "partially_validated"}
        )
        for snapshot in snapshots:
            if snapshot.metrics.average_fps is not None:
                fps_by_source[snapshot.source].append(snapshot.metrics.average_fps)

        records: list[EvidenceDecayRecord] = []
        for snapshot in snapshots:
            age_days = max((now - snapshot.timestamp).total_seconds() / 86400, 0)
            repeated = source_counts[snapshot.source]
            support = validation_support[snapshot.product_ids[0]] if snapshot.product_ids else 0
            stability = _clip(1 - _spread(fps_by_source[snapshot.source]))
            half_life = 45.0
            if support:
                half_life += min(90.0, support * 18.0)
            if repeated >= 3 and stability >= 0.76:
                half_life += 45.0
            original_weight = _clip(snapshot.trust_score * 0.58 + snapshot.freshness_score * 0.28 + stability * 0.14)
            decayed_weight = _clip(original_weight * exp(-age_days / max(half_life, 1)) + min(0.18, support * 0.03))
            if snapshot.trust_score < 0.4 and decayed_weight < 0.32:
                status = "quarantined"
                reason = "low-trust telemetry cannot safely influence governed reasoning"
            elif age_days > 90 and support == 0:
                status = "stale"
                reason = "old telemetry has no validation support"
            elif decayed_weight < original_weight * 0.68:
                status = "decayed"
                reason = "age and weak validation support reduced influence"
            else:
                status = "active"
                reason = "telemetry remains recent or statistically supported"
            records.append(
                EvidenceDecayRecord(
                    source=snapshot.source,
                    age_days=round(age_days, 2),
                    original_weight=original_weight,
                    decayed_weight=decayed_weight,
                    validation_support=support,
                    statistical_stability=stability,
                    status=status,
                    reason=reason,
                )
            )
        return sorted(records, key=lambda item: (item.status != "quarantined", item.decayed_weight))

    def confidence_drift(
        self,
        cognition: HardwareCognitionReport,
        predictions: list[PredictionRecord],
        validations: list[PredictionValidation],
    ) -> float:
        values = [cognition.confidence.confidence_score, cognition.reliability.reliability_score]
        values.extend(prediction.confidence.confidence_score for prediction in predictions[:20])
        values.extend(validation.calibrated_confidence for validation in validations[:20])
        return _spread(values)

    def confidence_oscillation(
        self,
        predictions: list[PredictionRecord],
        validations: list[PredictionValidation],
    ) -> float:
        ordered = sorted(
            [(prediction.created_at, prediction.confidence.confidence_score) for prediction in predictions]
            + [(validation.created_at, validation.calibrated_confidence) for validation in validations],
            key=lambda item: item[0],
        )
        if len(ordered) < 4:
            return 0.0
        deltas = [ordered[index][1] - ordered[index - 1][1] for index in range(1, len(ordered))]
        sign_changes = sum(
            1
            for index in range(1, len(deltas))
            if abs(deltas[index]) >= 0.04 and abs(deltas[index - 1]) >= 0.04 and deltas[index] * deltas[index - 1] < 0
        )
        return _clip(sign_changes / max(len(deltas) - 1, 1))

    def contradiction_density(
        self,
        cognition: HardwareCognitionReport,
        predictions: list[PredictionRecord],
        validations: list[PredictionValidation],
        contradictions: list[ContradictionSignal],
    ) -> float:
        contradicted_validations = sum(validation.status == "contradicted" for validation in validations)
        contradiction_count = len(contradictions) + cognition.confidence.contradiction_count + contradicted_validations
        denominator = max(
            cognition.confidence.sample_size + len(predictions[:20]) + len(validations[:20]),
            1,
        )
        return _clip(contradiction_count / denominator)

    def recursive_feedback_risk(
        self,
        cognition: HardwareCognitionReport,
        predictions: list[PredictionRecord],
        validations: list[PredictionValidation],
        contradictions: list[ContradictionSignal],
    ) -> float:
        evidence_sources = [source for prediction in predictions for source in prediction.evidence_sources]
        source_total = len(evidence_sources)
        concentration = 0.0
        if source_total:
            concentration = Counter(evidence_sources).most_common(1)[0][1] / source_total
        elif predictions:
            concentration = 0.65
        no_validation = 1.0 if predictions and not validations else 0.0
        high_confidence_without_support = max(0.0, cognition.confidence.confidence_score - 0.66) / 0.34
        contradiction_pressure = min(1.0, len(contradictions) / 4)
        return _clip(
            concentration * 0.32
            + no_validation * 0.24
            + high_confidence_without_support * 0.25
            + contradiction_pressure * 0.19
        )

    def anomaly_density(self, reasoning: TelemetryReasoningReport | None, snapshots: list[TelemetrySnapshotView]) -> float:
        if not reasoning:
            return 0.0
        return _clip((len(reasoning.anomalies) + len(reasoning.patterns) * 0.7) / max(len(snapshots), 1))

    def decay_pressure(self, records: list[EvidenceDecayRecord]) -> float:
        if not records:
            return 0.62
        losses = [
            1 - record.decayed_weight / max(record.original_weight, 0.01)
            for record in records
        ]
        quarantine_pressure = sum(record.status == "quarantined" for record in records) / len(records)
        return _clip(_avg(losses, 0.5) * 0.75 + quarantine_pressure * 0.25)

    def consensus_scores(
        self,
        cognition: HardwareCognitionReport,
        freshness: float,
        decay_pressure: float,
        calibration_risk: float,
        contradiction_density: float,
        recursive_risk: float,
    ) -> list[ConsensusStrategyScore]:
        raw_scores = {
            "telemetry_weighted": _clip(cognition.confidence.confidence_score * (0.72 + freshness * 0.28)),
            "validation_calibrated": _clip(cognition.reliability.reliability_score * (1 - calibration_risk * 0.85)),
            "decay_adjusted": _clip(cognition.confidence.evidence_strength * (1 - decay_pressure * 0.72)),
            "contradiction_adverse": _clip(
                cognition.confidence.confidence_score
                * (1 - contradiction_density * 0.78)
                * (1 - recursive_risk * 0.34)
            ),
        }
        disagreement = _spread(raw_scores.values())
        rationales = {
            "telemetry_weighted": "weights accepted telemetry by freshness before allowing confidence growth",
            "validation_calibrated": "uses outcome validation and calibration error as the primary guard",
            "decay_adjusted": "reduces evidence influence as telemetry ages or loses support",
            "contradiction_adverse": "penalizes confidence when contradictions and feedback-loop risk rise",
        }
        return [
            ConsensusStrategyScore(
                strategy=strategy,  # type: ignore[arg-type]
                confidence_score=score,
                evidence_weight=_clip(score * (1 - disagreement * 0.35)),
                disagreement_score=disagreement,
                rationale=rationales[strategy],
            )
            for strategy, score in raw_scores.items()
        ]

    def graph_hygiene_signals(
        self,
        *,
        product_id: str,
        evidence_decay: list[EvidenceDecayRecord],
        confidence_drift: float,
        confidence_oscillation: float,
        contradiction_density: float,
        recursive_risk: float,
        decay_pressure: float,
        consensus_disagreement: float,
    ) -> list[GraphHygieneSignal]:
        signals: list[GraphHygieneSignal] = []
        quarantined = [record for record in evidence_decay if record.status == "quarantined"]
        stale = [record for record in evidence_decay if record.status in {"stale", "decayed"}]
        if quarantined:
            signals.append(
                GraphHygieneSignal(
                    kind="polluted_node",
                    severity="critical",
                    confidence_score=min(0.96, 0.62 + len(quarantined) * 0.08),
                    affected_nodes=[record.source for record in quarantined[:6]],
                    explanation="Low-trust decayed evidence is isolated from governed confidence.",
                    mitigation=["quarantine evidence source", "request fresh validation telemetry"],
                )
            )
        if decay_pressure >= 0.48 or len(stale) >= 3:
            signals.append(
                GraphHygieneSignal(
                    kind="stale_telemetry_dominance",
                    severity="warning" if decay_pressure < 0.7 else "critical",
                    confidence_score=_clip(0.48 + decay_pressure * 0.45),
                    affected_nodes=[record.source for record in stale[:6]],
                    explanation="Aging telemetry is exerting too much influence on reasoning.",
                    mitigation=["apply evidence decay", "lower recommendation certainty"],
                )
            )
        if recursive_risk >= 0.52:
            signals.append(
                GraphHygieneSignal(
                    kind="circular_evidence",
                    severity="critical" if recursive_risk >= 0.72 else "warning",
                    confidence_score=_clip(recursive_risk),
                    affected_nodes=[product_id],
                    explanation="Reasoning may be reinforcing predictions without independent validation.",
                    mitigation=["block confidence inflation", "require external outcome validation"],
                )
            )
        if confidence_drift >= 0.18 or confidence_oscillation >= 0.3:
            signals.append(
                GraphHygieneSignal(
                    kind="unstable_telemetry_cluster",
                    severity="warning",
                    confidence_score=_clip(0.5 + confidence_drift + confidence_oscillation * 0.4),
                    affected_nodes=[product_id],
                    explanation="Confidence evolution shows drift or oscillation above stability threshold.",
                    mitigation=["dampen confidence shifts", "trigger revalidation job"],
                )
            )
        if contradiction_density >= 0.24:
            signals.append(
                GraphHygieneSignal(
                    kind="corrupted_inference_chain",
                    severity="critical" if contradiction_density >= 0.44 else "warning",
                    confidence_score=_clip(0.52 + contradiction_density),
                    affected_nodes=[product_id],
                    explanation="Contradiction density suggests the inference path may be polluted.",
                    mitigation=["downgrade recommendation certainty", "review conflicting evidence"],
                )
            )
        if consensus_disagreement >= 0.2:
            signals.append(
                GraphHygieneSignal(
                    kind="low_trust_reasoning_path",
                    severity="warning",
                    confidence_score=_clip(0.48 + consensus_disagreement),
                    affected_nodes=[product_id],
                    explanation="Independent reasoning strategies disagree materially.",
                    mitigation=["surface disagreement", "use lowest-confidence strategy for ranking"],
                )
            )
        return signals

    def graph_integrity(self, signals: list[GraphHygieneSignal]) -> float:
        if not signals:
            return 1.0
        penalty = sum(0.22 if signal.severity == "critical" else 0.11 for signal in signals)
        return _clip(1 - penalty)

    def stability_control(
        self,
        cognition: HardwareCognitionReport,
        metrics: ReasoningHealthMetrics,
        consensus: list[ConsensusStrategyScore],
        snapshots: list[TelemetrySnapshotView],
    ) -> StabilityControl:
        original = cognition.confidence.confidence_score
        consensus_mean = _avg((score.confidence_score for score in consensus), original)
        sample_factor = min(1.0, len(snapshots) / 10)
        ceiling = _clip(
            0.62
            + sample_factor * 0.22
            + metrics.telemetry_freshness * 0.12
            - metrics.confidence_drift * 0.16
            - metrics.contradiction_density * 0.2
            - metrics.evidence_decay_pressure * 0.14
            - metrics.recursive_feedback_risk * 0.22,
            0.22,
            0.94,
        )
        dampening = _clip(
            0.18
            + metrics.confidence_drift * 0.28
            + metrics.confidence_oscillation * 0.22
            + metrics.contradiction_density * 0.2
            + metrics.recursive_feedback_risk * 0.16,
            0.12,
            0.78,
        )
        governed = _clip(original * (1 - dampening) + consensus_mean * dampening)
        governed = min(governed, ceiling)
        if not snapshots:
            governed = min(governed, 0.55)
        downgrade_reasons = []
        if governed < original:
            downgrade_reasons.append("governed confidence ceiling reduced unsupported certainty")
        if metrics.evidence_decay_pressure >= 0.45:
            downgrade_reasons.append("evidence decay pressure limits confidence growth")
        if metrics.recursive_feedback_risk >= 0.5:
            downgrade_reasons.append("recursive reasoning protection is active")
        if metrics.contradiction_density >= 0.2:
            downgrade_reasons.append("contradiction density requires recommendation downgrade")
        return StabilityControl(
            original_confidence=original,
            governed_confidence=_clip(governed),
            confidence_ceiling=ceiling,
            dampening_factor=dampening,
            decay_rate=_clip(metrics.evidence_decay_pressure * 0.45 + (1 - metrics.telemetry_freshness) * 0.25),
            quarantine_threshold=0.32,
            revalidation_required=(
                metrics.overall_health < 0.62
                or metrics.recursive_feedback_risk >= 0.52
                or metrics.contradiction_density >= 0.24
                or metrics.evidence_decay_pressure >= 0.55
            ),
            downgrade_reasons=downgrade_reasons,
        )

    def status(
        self,
        metrics: ReasoningHealthMetrics,
        signals: list[GraphHygieneSignal],
        stability: StabilityControl,
    ):
        critical = any(signal.severity == "critical" for signal in signals)
        if critical and metrics.overall_health < 0.42:
            return "quarantined"
        if critical or metrics.recursive_feedback_risk >= 0.72 or metrics.overall_health < 0.5:
            return "unstable"
        if metrics.overall_health < 0.64 or stability.revalidation_required:
            return "degraded"
        if signals or metrics.overall_health < 0.78:
            return "watch"
        return "healthy"

    def stabilization_actions(
        self,
        product_id: str,
        status: str,
        stability: StabilityControl,
        evidence_decay: list[EvidenceDecayRecord],
        signals: list[GraphHygieneSignal],
        metrics: ReasoningHealthMetrics,
    ) -> list[StabilizationAction]:
        actions: list[StabilizationAction] = []
        if stability.governed_confidence < stability.original_confidence - 0.03:
            actions.append(
                StabilizationAction(
                    kind="confidence_damping",
                    severity="warning",
                    target=product_id,
                    reason="confidence dampening prevents runaway certainty",
                )
            )
            actions.append(
                StabilizationAction(
                    kind="recommendation_downgrade",
                    severity="warning" if status != "unstable" else "critical",
                    target=product_id,
                    reason="recommendation certainty is lowered until governed confidence recovers",
                )
            )
        for record in evidence_decay:
            if record.status in {"decayed", "stale"}:
                actions.append(
                    StabilizationAction(
                        kind="evidence_decay",
                        severity="warning",
                        target=record.source,
                        reason=record.reason,
                    )
                )
            if record.status == "quarantined":
                actions.append(
                    StabilizationAction(
                        kind="evidence_quarantine",
                        severity="critical",
                        target=record.source,
                        reason=record.reason,
                    )
                )
        if stability.revalidation_required:
            actions.append(
                StabilizationAction(
                    kind="revalidation_job",
                    severity="critical" if status in {"unstable", "quarantined"} else "warning",
                    target=product_id,
                    reason="fresh independent telemetry is required before confidence can increase",
                )
            )
        if signals or metrics.graph_integrity < 0.82:
            actions.append(
                StabilizationAction(
                    kind="graph_hygiene_review",
                    severity="critical" if any(signal.severity == "critical" for signal in signals) else "warning",
                    target=product_id,
                    reason="graph hygiene signals require audit before promotion",
                )
            )
        return actions[:12]

    def audit_trail(
        self,
        cognition: HardwareCognitionReport,
        predictions: list[PredictionRecord],
        validations: list[PredictionValidation],
        contradictions: list[ContradictionSignal],
        reasoning: TelemetryReasoningReport | None,
    ) -> ReasoningAuditTrail:
        evidence_sources = sorted(
            set(
                source
                for prediction in predictions
                for source in prediction.evidence_sources
            )
            | set(source for contradiction in contradictions for source in contradiction.evidence_sources)
            | set(reasoning.evidence_sources if reasoning else [])
        )
        reasoning_paths = sorted(
            set(
                path
                for path in [prediction.reasoning_report_id for prediction in predictions]
                if path
            )
        )
        confidence_evolution = [
            f"current={cognition.confidence.confidence_score:.4f}",
            f"reliability={cognition.reliability.reliability_score:.4f}",
            f"calibration_error={cognition.reliability.calibration_error:.4f}",
        ]
        confidence_evolution.extend(
            f"{validation.kind}:{validation.status}:{validation.calibrated_confidence:.4f}"
            for validation in validations[:8]
        )
        return ReasoningAuditTrail(
            evidence_sources=evidence_sources[:20],
            reasoning_paths=reasoning_paths[:12],
            confidence_evolution=confidence_evolution[:16],
            anomaly_history=[item.title for item in reasoning.anomalies[:8]] if reasoning else [],
            contradiction_history=[item.explanation for item in contradictions[:8]],
        )

    def governance_summary(
        self,
        metrics: ReasoningHealthMetrics,
        stability: StabilityControl,
        signals: list[GraphHygieneSignal],
        actions: list[StabilizationAction],
    ) -> list[str]:
        lines = [
            f"Reasoning health {metrics.overall_health:.0%}; governed confidence {stability.governed_confidence:.0%}.",
            f"Confidence drift {metrics.confidence_drift:.0%}, contradiction density {metrics.contradiction_density:.0%}, recursive risk {metrics.recursive_feedback_risk:.0%}.",
        ]
        if stability.downgrade_reasons:
            lines.append(stability.downgrade_reasons[0])
        if signals:
            lines.append(f"{len(signals)} graph hygiene signal(s) require monitoring.")
        if actions:
            lines.append(f"{len(actions)} stabilization action(s) recommended.")
        return lines[:5]
