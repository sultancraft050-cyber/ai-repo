from __future__ import annotations

from app.graph.alignment_repository import Neo4jAlignmentRepository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.alignment import AlignmentInspectionReport, AlignmentRefreshRequest, AlignmentRefreshResponse, SystemIdentity
from app.services.alignment import CognitiveAlignmentEngine, default_identity
from app.services.evolution_service import EvolutionOrchestrationService


class CognitiveAlignmentService:
    def __init__(
        self,
        alignment_repository: Neo4jAlignmentRepository,
        evolution_repository: Neo4jEvolutionRepository,
        governance_repository: Neo4jGovernanceRepository,
        cognition_repository: Neo4jCognitionRepository,
        telemetry_repository: Neo4jTelemetryRepository,
    ) -> None:
        self.alignment_repository = alignment_repository
        self.evolution_repository = evolution_repository
        self.governance_repository = governance_repository
        self.cognition_repository = cognition_repository
        self.telemetry_repository = telemetry_repository
        self.engine = CognitiveAlignmentEngine()

    def identity(self) -> SystemIdentity:
        identity = self.alignment_repository.latest_identity()
        if identity:
            return identity
        identity = default_identity()
        self.alignment_repository.upsert_identity(identity)
        return identity

    def report(self, product_id: str, *, refresh: bool = False, persist: bool = True) -> AlignmentInspectionReport:
        if not refresh:
            existing = self.alignment_repository.latest_report(product_id)
            if existing:
                return existing
        evolution = EvolutionOrchestrationService(
            self.evolution_repository,
            self.governance_repository,
            self.cognition_repository,
            self.telemetry_repository,
        ).report(product_id, refresh=refresh, persist=persist)
        identity = self.identity()
        report = self.engine.inspect(product_id, evolution, identity)
        if persist:
            self.alignment_repository.upsert_report(report)
        return report

    def refresh(self, request: AlignmentRefreshRequest) -> AlignmentRefreshResponse:
        reports = [self.report(product_id, refresh=True, persist=request.persist) for product_id in request.product_ids]
        return AlignmentRefreshResponse(
            status="completed",
            message=f"alignment refreshed for {len(reports)} product(s)",
            refreshed_count=len(reports),
            reports=reports,
        )
