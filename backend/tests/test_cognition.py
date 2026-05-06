from __future__ import annotations

from datetime import UTC, datetime

from app.models.cognition import EvidenceQuality, OutcomeObservation
from app.services.cognition import HardwareCognitionEngine
from app.services.telemetry_analysis import TelemetryAnalysisEngine
from app.services.telemetry_reasoning import TelemetryReasoningEngine
from tests.test_telemetry import _driver_snapshot, _snapshot


def _built_snapshots():
    analysis = TelemetryAnalysisEngine()
    return [
        analysis.build_snapshot(_driver_snapshot("556.12", 94, 7.8, 1)),
        analysis.build_snapshot(_driver_snapshot("556.12", 61, 11.5, 2)),
        analysis.build_snapshot(_driver_snapshot("555.85", 136, 3.1, 3)),
    ]


def test_cognition_confidence_exposes_contradictions() -> None:
    snapshots = _built_snapshots()
    engine = HardwareCognitionEngine()
    summary = TelemetryAnalysisEngine().summarize("gpu:test", snapshots)
    reasoning = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    contradictions = engine.detect_contradictions("gpu:test", snapshots)
    confidence = engine.confidence_vector(summary, snapshots, contradictions, reasoning)

    assert contradictions
    assert confidence.contradiction_count == len(contradictions)
    assert confidence.uncertainty_score > 0
    assert confidence.conflicting_evidence


def test_cognition_generates_auditable_predictions() -> None:
    analysis = TelemetryAnalysisEngine()
    snapshots = [analysis.build_snapshot(_snapshot())]
    summary = analysis.summarize("gpu:test", snapshots)
    reasoning = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    predictions = HardwareCognitionEngine().generate_predictions("gpu:test", summary, reasoning, snapshots)

    assert any(prediction.kind == "fps" for prediction in predictions)
    assert any(prediction.kind == "bottleneck" for prediction in predictions)
    assert all(prediction.confidence.sample_size == 1 for prediction in predictions)
    assert all(prediction.evidence_sources for prediction in predictions)


def test_outcome_validation_reduces_overconfident_wrong_prediction() -> None:
    analysis = TelemetryAnalysisEngine()
    snapshots = [analysis.build_snapshot(_snapshot())]
    summary = analysis.summarize("gpu:test", snapshots)
    reasoning = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    engine = HardwareCognitionEngine()
    prediction = next(
        item for item in engine.generate_predictions("gpu:test", summary, reasoning, snapshots) if item.kind == "fps"
    )
    outcome = OutcomeObservation(
        product_id="gpu:test",
        prediction_id=prediction.id,
        workload=prediction.workload,
        resolution=prediction.resolution,
        observed_fps=48,
        evidence=EvidenceQuality(
            source="user telemetry validation",
            methodology="post-build gameplay capture",
            timestamp=datetime(2026, 5, 6, tzinfo=UTC),
            trust_score=0.82,
            freshness_score=0.97,
            repeatability_score=0.72,
            evidence_rank="validated_telemetry",
        ),
    )

    response = engine.validate_outcome(outcome, [prediction])

    assert response.validations[0].status == "contradicted"
    assert response.validations[0].relative_error is not None
    assert response.validations[0].confidence_error is not None
    assert response.updated_confidence
    assert response.contradictions
