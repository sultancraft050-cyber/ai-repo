from __future__ import annotations

from app.graph.alignment_repository import Neo4jAlignmentRepository
from app.graph.autonomy_repository import Neo4jAutonomyRepository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.autonomy import (
    AgentDefinition,
    AutonomyRunRequest,
    AutonomyRunResponse,
    AutonomousCognitionReport,
    CognitionEvent,
    CognitionEventIngestRequest,
    CognitionEventIngestResponse,
)
from app.services.alignment_service import CognitiveAlignmentService
from app.services.autonomy import AutonomousCognitionEngine, default_agents
from app.services.evolution_service import EvolutionOrchestrationService


class AutonomousCognitionService:
    def __init__(
        self,
        autonomy_repository: Neo4jAutonomyRepository,
        alignment_repository: Neo4jAlignmentRepository,
        evolution_repository: Neo4jEvolutionRepository,
        governance_repository: Neo4jGovernanceRepository,
        cognition_repository: Neo4jCognitionRepository,
        telemetry_repository: Neo4jTelemetryRepository,
    ) -> None:
        self.autonomy_repository = autonomy_repository
        self.alignment_repository = alignment_repository
        self.evolution_repository = evolution_repository
        self.governance_repository = governance_repository
        self.cognition_repository = cognition_repository
        self.telemetry_repository = telemetry_repository
        self.engine = AutonomousCognitionEngine()

    def agents(self) -> list[AgentDefinition]:
        agents = self.autonomy_repository.list_agents()
        if agents:
            return agents
        agents = default_agents()
        self.autonomy_repository.upsert_agents(agents)
        return agents

    def candidate_product_ids(self, limit: int = 8) -> list[str]:
        return self.autonomy_repository.candidate_product_ids(limit)

    def report(
        self,
        product_id: str,
        *,
        refresh: bool = False,
        persist: bool = True,
        external_events: list[CognitionEvent] | None = None,
    ) -> AutonomousCognitionReport:
        if not refresh and not external_events:
            existing = self.autonomy_repository.latest_report(product_id)
            if existing:
                return existing
        evolution = EvolutionOrchestrationService(
            self.evolution_repository,
            self.governance_repository,
            self.cognition_repository,
            self.telemetry_repository,
        ).report(product_id, refresh=refresh, persist=persist)
        alignment = CognitiveAlignmentService(
            self.alignment_repository,
            self.evolution_repository,
            self.governance_repository,
            self.cognition_repository,
            self.telemetry_repository,
        ).report(product_id, refresh=refresh, persist=persist)
        report = self.engine.orchestrate(
            product_id=product_id,
            alignment=alignment,
            evolution=evolution,
            agents=self.agents(),
            external_events=external_events,
        )
        if persist:
            self.autonomy_repository.upsert_report(report)
        return report

    def run(self, request: AutonomyRunRequest) -> AutonomyRunResponse:
        product_ids = request.product_ids or self.candidate_product_ids()
        reports = [
            self.report(product_id, refresh=request.refresh, persist=request.persist)
            for product_id in product_ids
        ]
        return AutonomyRunResponse(
            status="completed",
            message=f"autonomous cognition evaluated {len(reports)} product(s)",
            evaluated_count=len(reports),
            reports=reports,
        )

    def ingest_event(self, request: CognitionEventIngestRequest) -> CognitionEventIngestResponse:
        if request.persist:
            self.autonomy_repository.upsert_event(request.event)
        if request.trigger_analysis and request.event.product_id:
            report = self.report(
                request.event.product_id,
                refresh=True,
                persist=request.persist,
                external_events=[request.event],
            )
            return CognitionEventIngestResponse(status="analyzed", event_id=request.event.id, report=report)
        return CognitionEventIngestResponse(status="recorded", event_id=request.event.id, report=None)
