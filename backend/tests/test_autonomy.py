from __future__ import annotations

from app.models.alignment import AlignmentInspectionReport
from app.models.autonomy import CognitionEvent
from app.models.evolution import CognitivePolicy
from app.services.alignment import CognitiveAlignmentEngine
from app.services.autonomy import AutonomousCognitionEngine, default_agents
from app.services.evolution import EvolutionOrchestrator, default_policy
from tests.test_evolution import _governance_report


def _alignment_and_evolution(policy: CognitivePolicy | None = None) -> tuple[AlignmentInspectionReport, object]:
    governance = _governance_report()
    evolution = EvolutionOrchestrator().orchestrate("gpu:test", governance, policy or default_policy())
    alignment = CognitiveAlignmentEngine().inspect("gpu:test", evolution)
    return alignment, evolution


def test_autonomous_agents_are_governed_and_specialized() -> None:
    agents = default_agents()

    assert len(agents) == 8
    assert {agent.kind for agent in agents} >= {"telemetry", "alignment_integrity", "confidence_audit"}
    assert all(agent.governed_by for agent in agents)
    assert all(agent.forbidden_actions for agent in agents)


def test_autonomy_generates_event_queue_and_tasks() -> None:
    policy = default_policy().model_copy(
        update={
            "evidence_freshness_min": 0.95,
            "contradiction_tolerance": 0.02,
            "anomaly_escalation_threshold": 0.02,
        }
    )
    alignment, evolution = _alignment_and_evolution(policy)
    report = AutonomousCognitionEngine().orchestrate("gpu:test", alignment, evolution)

    assert report.events
    assert report.tasks
    assert report.health.overall_autonomy_health <= 1
    assert any(task.agent_kind in {"telemetry", "benchmark_validation", "anomaly_investigation"} for task in report.tasks)
    assert report.oversight


def test_autonomy_applies_reversible_guardrails_without_policy_override() -> None:
    policy = CognitivePolicy(
        id="policy:autonomy-aggressive",
        confidence_ceiling_max=0.98,
        evidence_freshness_min=0.9,
        contradiction_tolerance=0.03,
        adaptation_rate_limit=0.03,
        recommendation_aggressiveness=0.96,
        self_generated_trust_cap=0.94,
        change_reason="test unsafe autonomous path",
    )
    alignment, evolution = _alignment_and_evolution(policy)
    report = AutonomousCognitionEngine().orchestrate("gpu:test", alignment, evolution)

    assert any(item.kind in {"confidence_reduction", "recommendation_downgrade", "constitution_guardrail"} for item in report.interventions)
    assert all(
        item.status != "applied" or item.kind not in {"policy_escalation", "evolution_rollback", "evidence_quarantine"}
        for item in report.interventions
    )
    assert any(action.status == "required" for action in report.oversight)


def test_external_event_triggers_investigation_path() -> None:
    alignment, evolution = _alignment_and_evolution()
    event = CognitionEvent(
        kind="driver_regression",
        severity="critical",
        product_id="gpu:test",
        source="telemetry-feed",
        message="Driver version regression detected in workload telemetry.",
        payload={"driver_from": "551.86", "driver_to": "552.22"},
        priority_score=0.93,
    )
    report = AutonomousCognitionEngine().orchestrate("gpu:test", alignment, evolution, external_events=[event])

    assert any(task.kind == "validate_benchmark" for task in report.tasks)
    assert any(item.agent_kind == "benchmark_validation" for item in report.investigations)
    assert any(signal.channel in {"event_queue", "governance_signal"} for signal in report.signals)
