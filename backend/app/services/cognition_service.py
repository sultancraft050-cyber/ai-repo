from __future__ import annotations

from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.cognition import (
    HardwareCognitionReport,
    OutcomeValidationRequest,
    OutcomeValidationResponse,
    PredictionRecord,
)
from app.services.cognition import HardwareCognitionEngine
from app.services.telemetry_analysis import TelemetryAnalysisEngine
from app.services.telemetry_reasoning import TelemetryReasoningEngine


class HardwareCognitionService:
    def __init__(
        self,
        cognition_repository: Neo4jCognitionRepository,
        telemetry_repository: Neo4jTelemetryRepository,
    ) -> None:
        self.cognition_repository = cognition_repository
        self.telemetry_repository = telemetry_repository
        self.engine = HardwareCognitionEngine()

    def report(self, product_id: str, *, refresh: bool = False, persist: bool = True) -> HardwareCognitionReport:
        if not refresh:
            existing = self.cognition_repository.latest_report(product_id)
            if existing:
                return existing
        snapshots = self.telemetry_repository.snapshots_for_product(product_id, limit=500)
        summary = TelemetryAnalysisEngine().summarize(product_id, snapshots)
        reasoning = self.telemetry_repository.latest_reasoning(product_id)
        if not reasoning or refresh:
            reasoning = TelemetryReasoningEngine().reason(product_id, snapshots, summary)
            if persist and snapshots:
                self.telemetry_repository.upsert_reasoning(reasoning)
        predictions = self.cognition_repository.predictions_for_product(product_id, limit=50)
        validations = self.cognition_repository.validations_for_product(product_id, limit=50)
        states = self.cognition_repository.confidence_states(product_id)
        report = self.engine.cognition_report(
            product_id,
            snapshots,
            reasoning,
            stored_predictions=predictions or None,
            stored_validations=validations,
            stored_confidence=states[0] if states else None,
        )
        if persist:
            self.cognition_repository.upsert_report(report)
        return report

    def generate_predictions(self, product_id: str, *, persist: bool = True) -> list[PredictionRecord]:
        snapshots = self.telemetry_repository.snapshots_for_product(product_id, limit=500)
        summary = TelemetryAnalysisEngine().summarize(product_id, snapshots)
        reasoning = self.telemetry_repository.latest_reasoning(product_id) or TelemetryReasoningEngine().reason(
            product_id,
            snapshots,
            summary,
        )
        predictions = self.engine.generate_predictions(product_id, summary, reasoning, snapshots)
        if persist:
            self.cognition_repository.upsert_predictions(predictions)
        return predictions

    def validate_outcome(self, request: OutcomeValidationRequest) -> OutcomeValidationResponse:
        if request.persist:
            self.cognition_repository.upsert_outcome(request.outcome)
        predictions = self._target_predictions(request)
        states = self.cognition_repository.confidence_states(request.outcome.product_id)
        response = self.engine.validate_outcome(request.outcome, predictions, states)
        if request.persist:
            self.cognition_repository.upsert_validations(response.validations)
            self.cognition_repository.upsert_confidence_states(response.updated_confidence)
            self.cognition_repository.upsert_contradictions(response.contradictions)
            self.report(request.outcome.product_id, refresh=True, persist=True)
        return response

    def _target_predictions(self, request: OutcomeValidationRequest) -> list[PredictionRecord]:
        predictions = self.cognition_repository.predictions_for_product(request.outcome.product_id, limit=100)
        if request.prediction_ids:
            wanted = set(request.prediction_ids)
            predictions = [prediction for prediction in predictions if prediction.id in wanted]
        elif request.outcome.prediction_id:
            predictions = [prediction for prediction in predictions if prediction.id == request.outcome.prediction_id]
        return predictions
