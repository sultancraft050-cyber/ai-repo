from __future__ import annotations

from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.evolution import (
    CognitivePolicy,
    EvolutionOrchestrationReport,
    EvolutionRefreshRequest,
    EvolutionRefreshResponse,
    PolicyCreateRequest,
    PolicyRollbackRequest,
    RollbackEvent,
)
from app.services.evolution import EvolutionOrchestrator, default_policy
from app.services.governance_service import ReasoningGovernanceService


class EvolutionOrchestrationService:
    def __init__(
        self,
        evolution_repository: Neo4jEvolutionRepository,
        governance_repository: Neo4jGovernanceRepository,
        cognition_repository: Neo4jCognitionRepository,
        telemetry_repository: Neo4jTelemetryRepository,
    ) -> None:
        self.evolution_repository = evolution_repository
        self.governance_repository = governance_repository
        self.cognition_repository = cognition_repository
        self.telemetry_repository = telemetry_repository
        self.orchestrator = EvolutionOrchestrator()

    def active_policy(self, scope: str = "global") -> CognitivePolicy:
        policy = self.evolution_repository.active_policy(scope)
        if policy:
            return policy
        policy = default_policy()
        self.evolution_repository.upsert_policy(policy)
        return policy

    def create_policy(self, request: PolicyCreateRequest) -> CognitivePolicy:
        policy = request.policy.model_copy(update={"status": "active" if request.activate else "candidate"})
        self.evolution_repository.upsert_policy(policy)
        return policy

    def report(self, product_id: str, *, refresh: bool = False, persist: bool = True) -> EvolutionOrchestrationReport:
        if not refresh:
            existing = self.evolution_repository.latest_report(product_id)
            if existing:
                return existing
        governance = ReasoningGovernanceService(
            self.governance_repository,
            self.cognition_repository,
            self.telemetry_repository,
        ).report(product_id, refresh=refresh, persist=persist)
        policy = self.active_policy("global")
        previous = self.evolution_repository.latest_report(product_id)
        report = self.orchestrator.orchestrate(product_id, governance, policy, previous)
        if persist:
            self.evolution_repository.upsert_report(report)
        return report

    def refresh(self, request: EvolutionRefreshRequest) -> EvolutionRefreshResponse:
        reports = [self.report(product_id, refresh=True, persist=request.persist) for product_id in request.product_ids]
        return EvolutionRefreshResponse(
            status="completed",
            message=f"evolution orchestration refreshed for {len(reports)} product(s)",
            refreshed_count=len(reports),
            reports=reports,
        )

    def rollback(self, request: PolicyRollbackRequest) -> RollbackEvent:
        current_policy = self.active_policy("global")
        event = RollbackEvent(
            status="requires_approval",
            from_policy_id=current_policy.id,
            to_policy_id=request.target_policy_id,
            trigger="human oversight rollback request",
            reason=request.approval_note or "rollback requested through governance oversight",
        )
        if request.persist:
            self.evolution_repository.record_rollback(event)
        return event
