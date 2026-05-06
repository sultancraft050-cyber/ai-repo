from __future__ import annotations

from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.governance import GovernanceRefreshRequest, GovernanceRefreshResponse, ReasoningGovernanceReport
from app.services.cognition_service import HardwareCognitionService
from app.services.governance import ReasoningGovernanceEngine
from app.services.telemetry_analysis import TelemetryAnalysisEngine
from app.services.telemetry_reasoning import TelemetryReasoningEngine


class ReasoningGovernanceService:
    def __init__(
        self,
        governance_repository: Neo4jGovernanceRepository,
        cognition_repository: Neo4jCognitionRepository,
        telemetry_repository: Neo4jTelemetryRepository,
    ) -> None:
        self.governance_repository = governance_repository
        self.cognition_repository = cognition_repository
        self.telemetry_repository = telemetry_repository
        self.engine = ReasoningGovernanceEngine()

    def report(self, product_id: str, *, refresh: bool = False, persist: bool = True) -> ReasoningGovernanceReport:
        if not refresh:
            existing = self.governance_repository.latest_report(product_id)
            if existing:
                return existing
        cognition_service = HardwareCognitionService(self.cognition_repository, self.telemetry_repository)
        cognition = cognition_service.report(product_id, refresh=refresh, persist=persist)
        snapshots = self.telemetry_repository.snapshots_for_product(product_id, limit=500)
        summary = TelemetryAnalysisEngine().summarize(product_id, snapshots)
        reasoning = self.telemetry_repository.latest_reasoning(product_id)
        if not reasoning:
            reasoning = TelemetryReasoningEngine().reason(product_id, snapshots, summary)
        predictions = self.cognition_repository.predictions_for_product(product_id, limit=100)
        validations = self.cognition_repository.validations_for_product(product_id, limit=100)
        contradictions = self.cognition_repository.contradictions_for_product(product_id, limit=100)
        report = self.engine.govern(
            product_id=product_id,
            cognition=cognition,
            snapshots=snapshots,
            predictions=predictions or cognition.active_predictions,
            validations=validations or cognition.recent_validations,
            contradictions=contradictions or cognition.contradictions,
            reasoning=reasoning,
        )
        if persist:
            self.governance_repository.upsert_report(report)
        return report

    def refresh(self, request: GovernanceRefreshRequest) -> GovernanceRefreshResponse:
        reports: list[ReasoningGovernanceReport] = []
        for product_id in request.product_ids:
            reports.append(self.report(product_id, refresh=True, persist=request.persist))
        return GovernanceRefreshResponse(
            status="completed",
            message=f"governance refreshed for {len(reports)} product(s)",
            refreshed_count=len(reports),
            reports=reports,
        )
