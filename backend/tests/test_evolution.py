from __future__ import annotations

from app.models.evolution import CognitivePolicy
from app.services.cognition import HardwareCognitionEngine
from app.services.evolution import EvolutionOrchestrator, default_policy
from app.services.governance import ReasoningGovernanceEngine
from app.services.telemetry_analysis import TelemetryAnalysisEngine
from app.services.telemetry_reasoning import TelemetryReasoningEngine
from tests.test_cognition import _built_snapshots
from tests.test_telemetry import _snapshot


def _governance_report():
    snapshots = _built_snapshots()
    summary = TelemetryAnalysisEngine().summarize("gpu:test", snapshots)
    reasoning = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    cognition = HardwareCognitionEngine().cognition_report("gpu:test", snapshots, reasoning=reasoning)
    return ReasoningGovernanceEngine().govern(
        product_id="gpu:test",
        cognition=cognition,
        snapshots=snapshots,
        predictions=cognition.active_predictions,
        validations=[],
        contradictions=cognition.contradictions,
        reasoning=reasoning,
    )


def test_evolution_enforces_policy_thresholds() -> None:
    governance = _governance_report()
    policy = default_policy().model_copy(
        update={
            "contradiction_tolerance": 0.03,
            "adaptation_rate_limit": 0.04,
            "requires_human_approval": True,
        }
    )
    report = EvolutionOrchestrator().orchestrate("gpu:test", governance, policy)

    assert report.health_index.index <= 1
    assert any(decision.status in {"throttle", "block", "escalate"} for decision in report.enforcement)
    assert report.rollback_events
    assert report.orchestration_summary


def test_evolution_sandboxes_reasoning_strategies_before_promotion() -> None:
    governance = _governance_report()
    report = EvolutionOrchestrator().orchestrate("gpu:test", governance, default_policy())

    assert report.sandbox_evaluations
    assert report.promotion_decisions
    assert all(evaluation.isolated for evaluation in report.sandbox_evaluations)
    assert all(decision.requires_approval for decision in report.promotion_decisions)


def test_evolution_detects_policy_drift() -> None:
    governance = _governance_report()
    policy = CognitivePolicy(
        id="policy:aggressive-test",
        version="9.9.0",
        confidence_ceiling_max=0.98,
        contradiction_tolerance=0.55,
        adaptation_rate_limit=0.7,
        recommendation_aggressiveness=0.95,
        self_generated_trust_cap=0.92,
        change_reason="test aggressive policy drift",
    )
    report = EvolutionOrchestrator().orchestrate("gpu:test", governance, policy)

    assert report.metrics.policy_drift > 0.1
    assert any(decision.rule == "policy_drift" for decision in report.enforcement)


def test_evolution_limits_no_telemetry_confidence() -> None:
    snapshots = [TelemetryAnalysisEngine().build_snapshot(_snapshot())]
    summary = TelemetryAnalysisEngine().summarize("gpu:test", snapshots)
    reasoning = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    cognition = HardwareCognitionEngine().cognition_report("gpu:test", snapshots, reasoning=reasoning)
    governance = ReasoningGovernanceEngine().govern(
        product_id="gpu:test",
        cognition=cognition,
        snapshots=[],
        predictions=cognition.active_predictions,
        validations=[],
        contradictions=[],
        reasoning=reasoning,
    )
    report = EvolutionOrchestrator().orchestrate("gpu:test", governance, default_policy())

    assert report.metrics.adaptation_pressure >= 0
    assert any(decision.rule == "evidence_freshness" for decision in report.enforcement)
