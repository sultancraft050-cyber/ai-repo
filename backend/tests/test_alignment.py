from __future__ import annotations

from app.models.evolution import CognitivePolicy
from app.services.alignment import CognitiveAlignmentEngine, default_identity
from app.services.evolution import EvolutionOrchestrator, default_policy
from tests.test_evolution import _governance_report


def test_alignment_identity_preserves_objective_hierarchy() -> None:
    identity = default_identity()
    ranks = [objective.name for objective in sorted(identity.optimization_priorities, key=lambda item: item.rank)]

    assert ranks[:3] == ["correctness", "safety_stability", "evidence_quality"]
    assert ranks[-1] == "performance_maximization"
    assert identity.constitution.immutable
    assert any("never hide uncertainty" in item for item in identity.constitution.non_overridable_constraints)


def test_alignment_reports_high_health_for_default_policy() -> None:
    governance = _governance_report()
    evolution = EvolutionOrchestrator().orchestrate("gpu:test", governance, default_policy())
    report = CognitiveAlignmentEngine().inspect("gpu:test", evolution)

    assert report.health.overall_alignment > 0.5
    assert report.ethics.ethics_passed in {True, False}
    assert report.tradeoffs
    assert report.audit_trail


def test_alignment_detects_aggressive_policy_without_evidence() -> None:
    governance = _governance_report()
    policy = CognitivePolicy(
        id="policy:alignment-aggressive",
        version="2.0.0",
        confidence_ceiling_max=0.98,
        evidence_freshness_min=0.88,
        contradiction_tolerance=0.04,
        adaptation_rate_limit=0.03,
        recommendation_aggressiveness=0.95,
        self_generated_trust_cap=0.92,
        change_reason="test unsafe aggressive optimization",
    )
    evolution = EvolutionOrchestrator().orchestrate("gpu:test", governance, policy)
    report = CognitiveAlignmentEngine().inspect("gpu:test", evolution)

    assert report.violations
    assert any(
        violation.kind
        in {"safety_ignored", "confidence_without_evidence", "policy_incoherence", "objective_drift", "benchmark_overfit"}
        for violation in report.violations
    )
    assert report.rollback[0].status in {"requires_approval", "not_required"}
    assert report.health.overall_alignment <= 1


def test_alignment_ethics_flags_biased_optimization_path() -> None:
    governance = _governance_report()
    policy = default_policy().model_copy(update={"recommendation_aggressiveness": 0.9, "contradiction_tolerance": 0.05})
    evolution = EvolutionOrchestrator().orchestrate("gpu:test", governance, policy)
    report = CognitiveAlignmentEngine().inspect("gpu:test", evolution)

    assert report.ethics.biased_optimization_risk > 0.2
    assert report.alignment_summary
