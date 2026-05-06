from __future__ import annotations

from datetime import UTC, datetime

from app.services.cognition import HardwareCognitionEngine
from app.services.governance import ReasoningGovernanceEngine
from app.services.telemetry_analysis import TelemetryAnalysisEngine
from app.services.telemetry_reasoning import TelemetryReasoningEngine
from tests.test_cognition import _built_snapshots
from tests.test_telemetry import _snapshot


def test_governance_detects_contradiction_and_stability_pressure() -> None:
    snapshots = _built_snapshots()
    analysis = TelemetryAnalysisEngine()
    summary = analysis.summarize("gpu:test", snapshots)
    reasoning = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    cognition_engine = HardwareCognitionEngine()
    cognition = cognition_engine.cognition_report("gpu:test", snapshots, reasoning=reasoning)
    report = ReasoningGovernanceEngine().govern(
        product_id="gpu:test",
        cognition=cognition,
        snapshots=snapshots,
        predictions=cognition.active_predictions,
        validations=[],
        contradictions=cognition.contradictions,
        reasoning=reasoning,
    )

    assert report.metrics.overall_health <= 1
    assert report.metrics.contradiction_density > 0
    assert report.stability.governed_confidence <= report.stability.confidence_ceiling
    assert report.consensus
    assert report.governance_summary


def test_governance_decays_old_unvalidated_evidence() -> None:
    old = _snapshot().model_copy(update={"timestamp": datetime(2025, 1, 1, tzinfo=UTC), "freshness_score": 0.18})
    snapshot = TelemetryAnalysisEngine().build_snapshot(old)
    summary = TelemetryAnalysisEngine().summarize("gpu:test", [snapshot])
    reasoning = TelemetryReasoningEngine().reason("gpu:test", [snapshot], summary)
    cognition = HardwareCognitionEngine().cognition_report("gpu:test", [snapshot], reasoning=reasoning)

    report = ReasoningGovernanceEngine().govern(
        product_id="gpu:test",
        cognition=cognition,
        snapshots=[snapshot],
        predictions=cognition.active_predictions,
        validations=[],
        contradictions=[],
        reasoning=reasoning,
    )

    assert report.evidence_decay
    assert report.evidence_decay[0].status in {"decayed", "stale", "quarantined"}
    assert report.metrics.evidence_decay_pressure > 0.3
    assert any(action.kind in {"evidence_decay", "revalidation_job"} for action in report.stabilization_actions)


def test_governance_blocks_recursive_confidence_inflation() -> None:
    snapshots = [TelemetryAnalysisEngine().build_snapshot(_snapshot())]
    summary = TelemetryAnalysisEngine().summarize("gpu:test", snapshots)
    reasoning = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    cognition_engine = HardwareCognitionEngine()
    cognition = cognition_engine.cognition_report("gpu:test", snapshots, reasoning=reasoning)
    predictions = [
        prediction.model_copy(
            update={
                "evidence_sources": ["self-generated reasoning path"],
                "confidence": prediction.confidence.model_copy(update={"confidence_score": 0.91}),
            }
        )
        for prediction in cognition.active_predictions
    ]
    report = ReasoningGovernanceEngine().govern(
        product_id="gpu:test",
        cognition=cognition.model_copy(
            update={"confidence": cognition.confidence.model_copy(update={"confidence_score": 0.91})}
        ),
        snapshots=snapshots,
        predictions=predictions,
        validations=[],
        contradictions=[],
        reasoning=reasoning,
    )

    assert report.metrics.recursive_feedback_risk >= 0.5
    assert report.stability.governed_confidence < report.stability.original_confidence
    assert any(action.kind == "confidence_damping" for action in report.stabilization_actions)
