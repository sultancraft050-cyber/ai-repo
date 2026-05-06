from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import mean, pstdev
from typing import Iterable

from app.models.cognition import (
    ConfidenceState,
    ConfidenceVector,
    ContradictionSignal,
    EvidenceQuality,
    HardwareCognitionReport,
    MetaReasoningReport,
    OutcomeObservation,
    OutcomeValidationResponse,
    PredictionRecord,
    PredictionValidation,
)
from app.models.telemetry import (
    BottleneckKind,
    TelemetryBottleneckBreakdown,
    TelemetryReasoningReport,
    TelemetrySnapshotView,
    TelemetrySummary,
)
from app.services.telemetry_analysis import TelemetryAnalysisEngine
from app.services.telemetry_reasoning import TelemetryReasoningEngine


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return round(max(lower, min(upper, value)), 4)


def _avg(values: Iterable[float | None], default: float = 0.0) -> float:
    clean = [float(value) for value in values if value is not None]
    return round(mean(clean), 4) if clean else default


def _spread(values: Iterable[float | None]) -> float:
    clean = [float(value) for value in values if value is not None]
    if len(clean) < 2:
        return 0.0
    baseline = max(mean(clean), 1.0)
    return round(pstdev(clean) / baseline, 4)


def _evidence_rank_score(rank: str) -> float:
    return {
        "validated_telemetry": 1.0,
        "repeated_benchmark_consistency": 0.86,
        "official_specification": 0.72,
        "historical_trend": 0.58,
        "inferred_estimation": 0.38,
    }.get(rank, 0.38)


class HardwareCognitionEngine:
    def cognition_report(
        self,
        product_id: str,
        snapshots: list[TelemetrySnapshotView],
        reasoning: TelemetryReasoningReport | None = None,
        stored_predictions: list[PredictionRecord] | None = None,
        stored_validations: list[PredictionValidation] | None = None,
        stored_confidence: ConfidenceState | None = None,
    ) -> HardwareCognitionReport:
        summary = TelemetryAnalysisEngine().summarize(product_id, snapshots)
        reasoning = reasoning or TelemetryReasoningEngine().reason(product_id, snapshots, summary)
        contradictions = self.detect_contradictions(product_id, snapshots)
        confidence = self.confidence_vector(summary, snapshots, contradictions, reasoning)
        reliability = stored_confidence or self.initial_confidence_state(product_id, confidence, [])
        predictions = stored_predictions or self.generate_predictions(product_id, summary, reasoning, snapshots)
        validations = stored_validations or []
        meta = self.meta_reasoning(product_id, summary, snapshots, contradictions, confidence, reasoning)
        return HardwareCognitionReport(
            product_id=product_id,
            generated_at=datetime.now(UTC),
            confidence=confidence,
            reliability=reliability,
            meta_reasoning=meta,
            active_predictions=predictions,
            recent_validations=validations[:10],
            contradictions=contradictions,
            bottleneck_memory=summary.bottleneck,
            learning_summary=self.learning_summary(summary, confidence, contradictions, validations),
            audit_events=self.audit_events(reasoning, confidence, contradictions, validations),
        )

    def generate_predictions(
        self,
        product_id: str,
        summary: TelemetrySummary,
        reasoning: TelemetryReasoningReport,
        snapshots: list[TelemetrySnapshotView],
    ) -> list[PredictionRecord]:
        confidence = self.confidence_vector(
            summary,
            snapshots,
            self.detect_contradictions(product_id, snapshots),
            reasoning,
        )
        evidence = self.evidence_quality(snapshots)
        predictions: list[PredictionRecord] = []
        if summary.average_fps is not None:
            predictions.append(
                PredictionRecord(
                    product_id=product_id,
                    reasoning_report_id=reasoning.id,
                    kind="fps",
                    workload=summary.covered_workloads[0] if summary.covered_workloads else None,
                    resolution=summary.covered_resolutions[-1] if summary.covered_resolutions else None,
                    predicted_value=summary.average_fps,
                    predicted_unit="fps",
                    confidence=confidence,
                    evidence=evidence,
                    evidence_sources=reasoning.evidence_sources,
                    expires_at=datetime.now(UTC) + timedelta(days=45),
                )
            )
        if summary.primary_limiter != "none":
            predictions.append(
                PredictionRecord(
                    product_id=product_id,
                    reasoning_report_id=reasoning.id,
                    kind="bottleneck",
                    workload=summary.covered_workloads[0] if summary.covered_workloads else None,
                    resolution=summary.covered_resolutions[-1] if summary.covered_resolutions else None,
                    predicted_limiter=summary.primary_limiter,
                    confidence=confidence,
                    evidence=evidence,
                    evidence_sources=reasoning.evidence_sources,
                    expires_at=datetime.now(UTC) + timedelta(days=60),
                )
            )
        if summary.average_temp_c is not None or summary.thermal_throttling_risk != "unknown":
            predictions.append(
                PredictionRecord(
                    product_id=product_id,
                    reasoning_report_id=reasoning.id,
                    kind="thermal",
                    workload=summary.covered_workloads[0] if summary.covered_workloads else None,
                    resolution=summary.covered_resolutions[-1] if summary.covered_resolutions else None,
                    predicted_value=summary.hotspot_temp_c or summary.average_temp_c,
                    predicted_unit="celsius",
                    predicted_limiter="thermal" if summary.thermal_throttling_risk in {"medium", "high"} else None,
                    confidence=confidence,
                    evidence=evidence,
                    evidence_sources=reasoning.evidence_sources,
                    expires_at=datetime.now(UTC) + timedelta(days=45),
                )
            )
        if summary.peak_power_w is not None:
            predictions.append(
                PredictionRecord(
                    product_id=product_id,
                    reasoning_report_id=reasoning.id,
                    kind="power",
                    workload=summary.covered_workloads[0] if summary.covered_workloads else None,
                    resolution=summary.covered_resolutions[-1] if summary.covered_resolutions else None,
                    predicted_value=summary.peak_power_w,
                    predicted_unit="watts",
                    confidence=confidence,
                    evidence=evidence,
                    evidence_sources=reasoning.evidence_sources,
                    expires_at=datetime.now(UTC) + timedelta(days=45),
                )
            )
        for insight in reasoning.predictions[:2]:
            predictions.append(
                PredictionRecord(
                    product_id=product_id,
                    reasoning_report_id=reasoning.id,
                    kind="upgrade_limit",
                    workload=summary.covered_workloads[0] if summary.covered_workloads else None,
                    resolution=summary.covered_resolutions[-1] if summary.covered_resolutions else None,
                    predicted_value=insight.risk_score,
                    predicted_unit="risk_score",
                    predicted_limiter=insight.predicted_limitation,
                    horizon=insight.horizon,
                    confidence=confidence.model_copy(
                        update={"confidence_score": min(confidence.confidence_score, insight.confidence_score)}
                    ),
                    evidence=evidence,
                    evidence_sources=insight.evidence_sources or reasoning.evidence_sources,
                    expires_at=datetime.now(UTC) + timedelta(days=120),
                )
            )
        return predictions[:8]

    def validate_outcome(
        self,
        outcome: OutcomeObservation,
        predictions: list[PredictionRecord],
        existing_states: list[ConfidenceState] | None = None,
    ) -> OutcomeValidationResponse:
        validations = [self.validate_prediction(prediction, outcome) for prediction in predictions]
        states = self.update_confidence_states(predictions, validations, existing_states or [])
        contradictions = self.contradictions_from_validation(outcome, validations)
        return OutcomeValidationResponse(
            outcome_id=outcome.id,
            validations=validations,
            updated_confidence=states,
            contradictions=contradictions,
            message=f"validated {len(validations)} prediction(s) against outcome {outcome.id}",
        )

    def validate_prediction(self, prediction: PredictionRecord, outcome: OutcomeObservation) -> PredictionValidation:
        observed = self._observed_value(prediction, outcome)
        status = "insufficient_evidence"
        absolute_error = None
        relative_error = None
        correctness = 0.35
        explanation = "Outcome does not include the required observed field for this prediction."
        if prediction.kind == "bottleneck" or prediction.predicted_limiter:
            observed_limiter = outcome.observed_limiter
            if observed_limiter:
                correct = observed_limiter == prediction.predicted_limiter
                correctness = 1.0 if correct else 0.0
                status = "validated" if correct else "contradicted"
                explanation = (
                    f"Predicted limiter {prediction.predicted_limiter}; observed limiter {observed_limiter}."
                )
        elif observed is not None and prediction.predicted_value is not None:
            absolute_error = abs(prediction.predicted_value - observed)
            relative_error = absolute_error / max(abs(observed), 1)
            correctness = _clip(1 - relative_error)
            if relative_error <= 0.08:
                status = "validated"
            elif relative_error <= 0.18:
                status = "partially_validated"
            else:
                status = "contradicted"
            explanation = (
                f"Predicted {prediction.predicted_value:.2f} {prediction.predicted_unit or ''}; "
                f"observed {observed:.2f}; relative error {relative_error:.2%}."
            )
        confidence_error = abs(prediction.confidence.confidence_score - correctness)
        calibrated = _clip(prediction.confidence.confidence_score * 0.78 + correctness * 0.22)
        severity = "critical" if status == "contradicted" and prediction.confidence.confidence_score >= 0.72 else (
            "warning" if status == "contradicted" else "info"
        )
        return PredictionValidation(
            prediction_id=prediction.id,
            outcome_id=outcome.id,
            product_id=prediction.product_id,
            kind=prediction.kind,
            status=status,
            absolute_error=round(absolute_error, 4) if absolute_error is not None else None,
            relative_error=round(relative_error, 4) if relative_error is not None else None,
            confidence_error=round(confidence_error, 4),
            calibrated_confidence=calibrated,
            correctness_score=correctness,
            severity=severity,
            explanation=explanation,
        )

    def update_confidence_states(
        self,
        predictions: list[PredictionRecord],
        validations: list[PredictionValidation],
        existing_states: list[ConfidenceState],
    ) -> list[ConfidenceState]:
        state_by_key = {state.key: state for state in existing_states}
        state_by_key.update({f"{state.scope}:{state.key}": state for state in existing_states})
        updated: list[ConfidenceState] = []
        groups: dict[str, list[PredictionValidation]] = {}
        for prediction, validation in zip(predictions, validations, strict=False):
            keys = [
                f"product:{prediction.product_id}",
                f"inference_path:{prediction.kind}",
            ]
            if prediction.workload:
                keys.append(f"workload:{prediction.workload}")
            for key in keys:
                groups.setdefault(key, []).append(validation)
        for key, items in groups.items():
            existing = state_by_key.get(key)
            reliability = _avg((item.correctness_score for item in items), 0.5)
            calibration = _avg((item.confidence_error for item in items), 0.35)
            contradictions = sum(item.status == "contradicted" for item in items)
            prior_count = existing.validation_count if existing else 0
            prior_reliability = existing.reliability_score if existing else 0.58
            total_count = prior_count + len(items)
            adjusted = _clip(prior_reliability * 0.82 + reliability * 0.18)
            downgrade_reasons = list(existing.downgrade_reasons if existing else [])
            if contradictions:
                adjusted = _clip(adjusted - min(0.16, contradictions * 0.04))
                downgrade_reasons.append("contradicted predictions reduced confidence")
            if calibration > 0.28:
                adjusted = _clip(adjusted - 0.05)
                downgrade_reasons.append("overconfidence calibration error detected")
            scope, _, suffix = key.partition(":")
            updated.append(
                ConfidenceState(
                    id=f"confidence:{key}",
                    scope=scope,  # type: ignore[arg-type]
                    key=suffix or key,
                    reliability_score=adjusted,
                    calibration_error=_clip((existing.calibration_error if existing else 0.35) * 0.75 + calibration * 0.25),
                    validation_count=total_count,
                    contradiction_rate=_clip(((existing.contradiction_rate if existing else 0) * prior_count + contradictions) / max(total_count, 1)),
                    last_updated=datetime.now(UTC),
                    downgrade_reasons=dedupe(downgrade_reasons)[-6:],
                )
            )
        return updated

    def confidence_vector(
        self,
        summary: TelemetrySummary,
        snapshots: list[TelemetrySnapshotView],
        contradictions: list[ContradictionSignal],
        reasoning: TelemetryReasoningReport,
    ) -> ConfidenceVector:
        sample_factor = min(1.0, summary.sample_count / 10)
        source_quality = _avg((snapshot.trust_score for snapshot in snapshots), 0.42)
        freshness = _avg((snapshot.freshness_score for snapshot in snapshots), 0.4)
        repeatability = 1 - min(0.72, _spread(snapshot.metrics.average_fps for snapshot in snapshots) * 1.6)
        workload_consistency = self.workload_consistency(snapshots)
        telemetry_stability = 1 - min(0.85, (summary.frame_time_instability_score or 45) / 100)
        contradiction_penalty = min(0.38, len(contradictions) * 0.08)
        evidence_strength = _clip(
            source_quality * 0.25
            + freshness * 0.12
            + repeatability * 0.2
            + sample_factor * 0.22
            + workload_consistency * 0.12
            + reasoning.confidence_score * 0.09
            - contradiction_penalty
        )
        confidence_score = _clip(evidence_strength * 0.72 + telemetry_stability * 0.18 + source_quality * 0.1)
        uncertainty = _clip(1 - confidence_score + contradiction_penalty * 0.45)
        assumptions = []
        if summary.sample_count < 3:
            assumptions.append("small telemetry sample size")
        if not summary.covered_resolutions:
            assumptions.append("resolution coverage is missing")
        if summary.thermal_throttling_risk == "unknown":
            assumptions.append("thermal outcome coverage is incomplete")
        return ConfidenceVector(
            confidence_score=confidence_score,
            evidence_strength=evidence_strength,
            sample_size=summary.sample_count,
            workload_consistency=workload_consistency,
            telemetry_stability=_clip(telemetry_stability),
            contradiction_count=len(contradictions),
            uncertainty_score=uncertainty,
            assumptions=assumptions,
            conflicting_evidence=[item.explanation for item in contradictions[:4]],
        )

    def detect_contradictions(
        self,
        product_id: str,
        snapshots: list[TelemetrySnapshotView],
    ) -> list[ContradictionSignal]:
        contradictions: list[ContradictionSignal] = []
        fps_spread = _spread(snapshot.metrics.average_fps for snapshot in snapshots)
        if fps_spread >= 0.24 and len(snapshots) >= 3:
            contradictions.append(
                ContradictionSignal(
                    product_id=product_id,
                    kind="fps_spread",
                    severity="critical" if fps_spread >= 0.45 else "warning",
                    confidence_score=_clip(0.45 + fps_spread),
                    explanation=f"Accepted FPS telemetry has {fps_spread:.1%} normalized spread.",
                    evidence_sources=dedupe(snapshot.source for snapshot in snapshots),
                    affected_workloads=dedupe(snapshot.workload.name for snapshot in snapshots),
                )
            )
        thermal_values = [snapshot.metrics.hotspot_temp_c for snapshot in snapshots if snapshot.metrics.hotspot_temp_c is not None]
        if len(thermal_values) >= 3 and max(thermal_values) - min(thermal_values) >= 18:
            contradictions.append(
                ContradictionSignal(
                    product_id=product_id,
                    kind="thermal_conflict",
                    severity="warning",
                    confidence_score=0.68,
                    explanation="Thermal telemetry conflicts across accepted samples; cooling conditions may differ.",
                    evidence_sources=dedupe(snapshot.source for snapshot in snapshots),
                    affected_workloads=dedupe(snapshot.workload.name for snapshot in snapshots),
                )
            )
        for snapshot in snapshots:
            if snapshot.metrics.average_fps and snapshot.metrics.average_power_w:
                efficiency = snapshot.metrics.average_fps / max(snapshot.metrics.average_power_w, 1)
                if efficiency > 3.2 and snapshot.trust_score < 0.78:
                    contradictions.append(
                        ContradictionSignal(
                            product_id=product_id,
                            kind="power_efficiency",
                            severity="warning",
                            confidence_score=0.58,
                            explanation="A low-trust sample reports unusually high FPS per watt.",
                            evidence_sources=[snapshot.source],
                            affected_workloads=[snapshot.workload.name],
                        )
                    )
        driver_counts = Counter(
            snapshot.driver_version.version
            for snapshot in snapshots
            if snapshot.driver_version and snapshot.frame_time_instability_score >= 42
        )
        if len(driver_counts) >= 2:
            contradictions.append(
                ContradictionSignal(
                    product_id=product_id,
                    kind="driver_instability",
                    severity="warning",
                    confidence_score=0.62,
                    explanation="Instability appears across multiple driver versions; driver causality is uncertain.",
                    evidence_sources=dedupe(snapshot.source for snapshot in snapshots),
                    affected_workloads=dedupe(snapshot.workload.name for snapshot in snapshots),
                )
            )
        return contradictions[:8]

    def contradictions_from_validation(
        self,
        outcome: OutcomeObservation,
        validations: list[PredictionValidation],
    ) -> list[ContradictionSignal]:
        return [
            ContradictionSignal(
                product_id=outcome.product_id,
                kind="source_disagreement",
                severity=validation.severity,
                confidence_score=min(0.92, 0.5 + (validation.confidence_error or 0)),
                explanation=validation.explanation,
                evidence_sources=[outcome.evidence.source],
                affected_workloads=[outcome.workload] if outcome.workload else [],
            )
            for validation in validations
            if validation.status == "contradicted"
        ][:6]

    def meta_reasoning(
        self,
        product_id: str,
        summary: TelemetrySummary,
        snapshots: list[TelemetrySnapshotView],
        contradictions: list[ContradictionSignal],
        confidence: ConfidenceVector,
        reasoning: TelemetryReasoningReport,
    ) -> MetaReasoningReport:
        gaps = []
        if not any(snapshot.metrics.one_percent_low_fps is not None for snapshot in snapshots):
            gaps.append("1% low telemetry missing")
        if not any(snapshot.metrics.hotspot_temp_c is not None for snapshot in snapshots):
            gaps.append("hotspot thermal telemetry missing")
        if not any(snapshot.driver_version for snapshot in snapshots):
            gaps.append("driver version coverage missing")
        if not summary.covered_resolutions or len(summary.covered_resolutions) < 2:
            gaps.append("limited resolution coverage")
        weak = []
        if confidence.evidence_strength < 0.55:
            weak.append("evidence strength below production recommendation threshold")
        if summary.sample_count < 3:
            weak.append("insufficient repeated telemetry")
        if contradictions:
            weak.append("contradictory telemetry detected")
        corrections = []
        if confidence.contradiction_count:
            corrections.append("confidence reduced due to contradiction density")
        if confidence.telemetry_stability < 0.52:
            corrections.append("reasoning downgraded due to unstable telemetry")
        if reasoning.driver_regressions:
            corrections.append("driver-sensitive predictions require revalidation after updates")
        return MetaReasoningReport(
            product_id=product_id,
            uncertainty_score=confidence.uncertainty_score,
            evidence_strength=confidence.evidence_strength,
            weak_evidence=weak,
            assumptions=confidence.assumptions,
            telemetry_gaps=gaps,
            contradiction_density=_clip(len(contradictions) / max(summary.sample_count, 1)),
            self_corrections=corrections,
        )

    def evidence_quality(self, snapshots: list[TelemetrySnapshotView]) -> list[EvidenceQuality]:
        evidence: list[EvidenceQuality] = []
        for snapshot in snapshots[:12]:
            repeated = len([item for item in snapshots if item.source == snapshot.source])
            evidence.append(
                EvidenceQuality(
                    source=snapshot.source,
                    methodology=snapshot.benchmark_name,
                    benchmark_conditions={
                        "resolution": snapshot.resolution,
                        "settings_preset": snapshot.settings_preset,
                        "workload": snapshot.workload.name,
                    },
                    hardware_configuration={
                        "product_ids": snapshot.product_ids,
                        "driver": snapshot.driver_version.model_dump(mode="json") if snapshot.driver_version else None,
                    },
                    timestamp=snapshot.timestamp,
                    trust_score=snapshot.trust_score,
                    freshness_score=snapshot.freshness_score,
                    repeatability_score=min(1.0, 0.45 + repeated * 0.12),
                    evidence_rank="validated_telemetry" if snapshot.trust_score >= 0.78 else "historical_trend",
                )
            )
        return evidence

    def initial_confidence_state(
        self,
        product_id: str,
        confidence: ConfidenceVector,
        validations: list[PredictionValidation],
    ) -> ConfidenceState:
        return ConfidenceState(
            id=f"confidence:product:{product_id}",
            scope="product",
            key=product_id,
            reliability_score=confidence.confidence_score,
            calibration_error=_avg((validation.confidence_error for validation in validations), 0.35),
            validation_count=len(validations),
            contradiction_rate=confidence.contradiction_count / max(confidence.sample_size, 1),
            downgrade_reasons=confidence.conflicting_evidence[:5],
        )

    def learning_summary(
        self,
        summary: TelemetrySummary,
        confidence: ConfidenceVector,
        contradictions: list[ContradictionSignal],
        validations: list[PredictionValidation],
    ) -> list[str]:
        lines = [
            f"Confidence {confidence.confidence_score:.0%} from {confidence.sample_size} sample(s); uncertainty {confidence.uncertainty_score:.0%}.",
            f"Evidence strength {confidence.evidence_strength:.0%}, workload consistency {confidence.workload_consistency:.0%}, telemetry stability {confidence.telemetry_stability:.0%}.",
        ]
        if contradictions:
            lines.append(f"{len(contradictions)} contradiction signal(s) reduce certainty.")
        if validations:
            accuracy = _avg((validation.correctness_score for validation in validations), 0)
            lines.append(f"Recent validation correctness averages {accuracy:.0%}.")
        if summary.primary_limiter != "none":
            lines.append(f"Current probabilistic limiter memory favors {summary.primary_limiter.upper()}.")
        return lines[:5]

    def audit_events(
        self,
        reasoning: TelemetryReasoningReport,
        confidence: ConfidenceVector,
        contradictions: list[ContradictionSignal],
        validations: list[PredictionValidation],
    ) -> list[str]:
        events = [
            f"reasoning_report={reasoning.id}",
            f"confidence_score={confidence.confidence_score:.4f}",
            f"evidence_strength={confidence.evidence_strength:.4f}",
            f"contradictions={len(contradictions)}",
            f"validations={len(validations)}",
        ]
        return events

    def workload_consistency(self, snapshots: list[TelemetrySnapshotView]) -> float:
        if not snapshots:
            return 0.0
        workloads = Counter(snapshot.workload.name for snapshot in snapshots)
        dominant = workloads.most_common(1)[0][1] / len(snapshots)
        resolution_diversity = len({snapshot.resolution for snapshot in snapshots})
        return _clip(dominant * 0.7 + min(1.0, resolution_diversity / 3) * 0.3)

    def _observed_value(self, prediction: PredictionRecord, outcome: OutcomeObservation) -> float | None:
        if prediction.kind == "fps":
            return outcome.observed_fps
        if prediction.kind == "thermal":
            return outcome.observed_average_temp_c
        if prediction.kind == "power":
            return outcome.observed_peak_power_w
        if prediction.kind == "stability":
            return outcome.observed_instability_score
        if prediction.kind == "upgrade_limit":
            return None
        return None


def dedupe(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
