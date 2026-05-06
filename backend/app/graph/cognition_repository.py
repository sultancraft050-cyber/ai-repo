from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.models.cognition import (
    ConfidenceState,
    ContradictionSignal,
    HardwareCognitionReport,
    LearningJob,
    OutcomeObservation,
    PredictionRecord,
    PredictionValidation,
)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _clean_properties(values: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool, datetime)):
            clean[key] = value
        elif isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
            clean[key] = value
        else:
            clean[key] = json.dumps(value, sort_keys=True, default=_json_default)
    return clean


def _prediction(data: dict[str, Any]) -> PredictionRecord:
    return PredictionRecord.model_validate_json(data["payload_json"])


def _validation(data: dict[str, Any]) -> PredictionValidation:
    return PredictionValidation.model_validate_json(data["payload_json"])


def _confidence(data: dict[str, Any]) -> ConfidenceState:
    return ConfidenceState.model_validate_json(data["payload_json"])


def _contradiction(data: dict[str, Any]) -> ContradictionSignal:
    return ContradictionSignal.model_validate_json(data["payload_json"])


class Neo4jCognitionRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT cognition_report_id IF NOT EXISTS "
            "FOR (n:HardwareCognition) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_prediction_id IF NOT EXISTS "
            "FOR (n:Prediction) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_outcome_id IF NOT EXISTS "
            "FOR (n:OutcomeObservation) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_validation_id IF NOT EXISTS "
            "FOR (n:PredictionValidation) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_confidence_id IF NOT EXISTS "
            "FOR (n:ConfidenceState) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_evidence_id IF NOT EXISTS "
            "FOR (n:CognitionEvidence) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_hypothesis_id IF NOT EXISTS "
            "FOR (n:Hypothesis) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_contradiction_id IF NOT EXISTS "
            "FOR (n:Contradiction) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT cognition_learning_job_id IF NOT EXISTS "
            "FOR (n:LearningJob) REQUIRE n.id IS UNIQUE",
            "CREATE INDEX prediction_product_kind IF NOT EXISTS "
            "FOR (n:Prediction) ON (n.product_id, n.kind)",
            "CREATE INDEX validation_product_created IF NOT EXISTS "
            "FOR (n:PredictionValidation) ON (n.product_id, n.created_at)",
            "CREATE INDEX confidence_key IF NOT EXISTS FOR (n:ConfidenceState) ON (n.scope, n.key)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def upsert_report(self, report: HardwareCognitionReport) -> None:
        report_id = f"cognition:{report.product_id}"
        payload_json = report.model_dump_json()
        props = _clean_properties(
            {
                "id": report_id,
                "product_id": report.product_id,
                "generated_at": report.generated_at,
                "confidence_score": report.confidence.confidence_score,
                "evidence_strength": report.confidence.evidence_strength,
                "uncertainty_score": report.confidence.uncertainty_score,
                "sample_size": report.confidence.sample_size,
                "contradiction_count": report.confidence.contradiction_count,
                "reliability_score": report.reliability.reliability_score,
                "payload_json": payload_json,
            }
        )
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MERGE (report:HardwareCognition {id: $report.id})
            SET report += $report
            MERGE (p)-[:HAS_COGNITION]->(report)
            SET p.cognition_confidence_score = $report.confidence_score,
                p.cognition_uncertainty_score = $report.uncertainty_score,
                p.cognition_reliability_score = $report.reliability_score,
                p.cognition_updated_at = datetime()
            """,
            product_id=report.product_id,
            report=props,
            database_=settings.neo4j_database,
        )
        self.upsert_predictions(report.active_predictions)
        self.upsert_confidence_states([report.reliability])
        self.upsert_contradictions(report.contradictions)

    def latest_report(self, product_id: str) -> HardwareCognitionReport | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_COGNITION]->(report:HardwareCognition)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN report.payload_json AS payload_json
            ORDER BY report.generated_at DESC
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return HardwareCognitionReport.model_validate_json(records[0]["payload_json"]) if records else None

    def upsert_predictions(self, predictions: list[PredictionRecord]) -> None:
        rows = [
            _clean_properties(
                {
                    "id": prediction.id,
                    "product_id": prediction.product_id,
                    "reasoning_report_id": prediction.reasoning_report_id,
                    "kind": prediction.kind,
                    "workload": prediction.workload,
                    "resolution": prediction.resolution,
                    "predicted_value": prediction.predicted_value,
                    "predicted_unit": prediction.predicted_unit,
                    "predicted_limiter": prediction.predicted_limiter,
                    "horizon": prediction.horizon,
                    "confidence_score": prediction.confidence.confidence_score,
                    "evidence_strength": prediction.confidence.evidence_strength,
                    "sample_size": prediction.confidence.sample_size,
                    "contradiction_count": prediction.confidence.contradiction_count,
                    "created_at": prediction.created_at,
                    "expires_at": prediction.expires_at,
                    "evidence_sources": prediction.evidence_sources,
                    "payload_json": prediction.model_dump_json(),
                }
            )
            for prediction in predictions
        ]
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = row.product_id OR p.canonical_key = row.product_id)
            MERGE (prediction:Prediction {id: row.id})
            SET prediction += row
            MERGE (p)-[:HAS_PREDICTION]->(prediction)
            WITH prediction, row
            MERGE (confidence:ConfidenceState {id: "confidence:prediction:" + row.id})
            SET confidence.scope = "inference_path",
                confidence.key = row.kind,
                confidence.reliability_score = row.confidence_score,
                confidence.calibration_error = 0.35,
                confidence.validation_count = 0,
                confidence.contradiction_rate = CASE row.sample_size WHEN 0 THEN 0 ELSE toFloat(row.contradiction_count) / row.sample_size END,
                confidence.last_updated = datetime(),
                confidence.payload_json = row.payload_json
            MERGE (prediction)-[:HAS_CONFIDENCE]->(confidence)
            WITH prediction, row
            UNWIND coalesce(row.evidence_sources, []) AS source
            MERGE (evidence:CognitionEvidence {id: "evidence:" + source})
            SET evidence.source = source,
                evidence.updated_at = datetime()
            MERGE (prediction)-[:SUPPORTED_BY]->(evidence)
            """,
            rows=rows,
            database_=settings.neo4j_database,
        )

    def predictions_for_product(self, product_id: str, limit: int = 50) -> list[PredictionRecord]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_PREDICTION]->(prediction:Prediction)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN prediction.payload_json AS payload_json
            ORDER BY prediction.created_at DESC
            LIMIT $limit
            """,
            product_id=product_id,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [_prediction(record.data()) for record in records]

    def upsert_outcome(self, outcome: OutcomeObservation) -> None:
        props = _clean_properties(
            {
                "id": outcome.id,
                "product_id": outcome.product_id,
                "prediction_id": outcome.prediction_id,
                "telemetry_snapshot_id": outcome.telemetry_snapshot_id,
                "workload": outcome.workload,
                "resolution": outcome.resolution,
                "observed_fps": outcome.observed_fps,
                "observed_one_percent_low_fps": outcome.observed_one_percent_low_fps,
                "observed_limiter": outcome.observed_limiter,
                "observed_average_temp_c": outcome.observed_average_temp_c,
                "observed_peak_power_w": outcome.observed_peak_power_w,
                "observed_instability_score": outcome.observed_instability_score,
                "observed_at": outcome.observed_at,
                "evidence_source": outcome.evidence.source,
                "payload_json": outcome.model_dump_json(),
            }
        )
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MERGE (outcome:OutcomeObservation {id: $outcome.id})
            SET outcome += $outcome
            MERGE (p)-[:HAS_OUTCOME]->(outcome)
            WITH outcome
            OPTIONAL MATCH (prediction:Prediction {id: $prediction_id})
            FOREACH (_ IN CASE WHEN prediction IS NULL THEN [] ELSE [1] END |
              MERGE (prediction)-[:VALIDATED_BY]->(outcome)
            )
            """,
            product_id=outcome.product_id,
            outcome=props,
            prediction_id=outcome.prediction_id,
            database_=settings.neo4j_database,
        )

    def upsert_validations(self, validations: list[PredictionValidation]) -> None:
        rows = [
            _clean_properties(
                {
                    "id": validation.id,
                    "prediction_id": validation.prediction_id,
                    "outcome_id": validation.outcome_id,
                    "product_id": validation.product_id,
                    "kind": validation.kind,
                    "status": validation.status,
                    "absolute_error": validation.absolute_error,
                    "relative_error": validation.relative_error,
                    "confidence_error": validation.confidence_error,
                    "calibrated_confidence": validation.calibrated_confidence,
                    "correctness_score": validation.correctness_score,
                    "severity": validation.severity,
                    "explanation": validation.explanation,
                    "created_at": validation.created_at,
                    "payload_json": validation.model_dump_json(),
                }
            )
            for validation in validations
        ]
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MERGE (validation:PredictionValidation {id: row.id})
            SET validation += row
            WITH validation, row
            OPTIONAL MATCH (prediction:Prediction {id: row.prediction_id})
            OPTIONAL MATCH (outcome:OutcomeObservation {id: row.outcome_id})
            FOREACH (_ IN CASE WHEN prediction IS NULL THEN [] ELSE [1] END |
              MERGE (prediction)-[:VALIDATED_BY]->(validation)
            )
            FOREACH (_ IN CASE WHEN outcome IS NULL THEN [] ELSE [1] END |
              MERGE (validation)-[:VALIDATED_BY]->(outcome)
            )
            FOREACH (_ IN CASE WHEN row.status = "contradicted" AND prediction IS NOT NULL THEN [1] ELSE [] END |
              MERGE (prediction)-[:CONTRADICTED_BY]->(validation)
            )
            """,
            rows=rows,
            database_=settings.neo4j_database,
        )

    def validations_for_product(self, product_id: str, limit: int = 50) -> list[PredictionValidation]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (validation:PredictionValidation {product_id: $product_id})
            RETURN validation.payload_json AS payload_json
            ORDER BY validation.created_at DESC
            LIMIT $limit
            """,
            product_id=product_id,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [_validation(record.data()) for record in records]

    def upsert_confidence_states(self, states: list[ConfidenceState]) -> None:
        rows = [
            _clean_properties(
                {
                    "id": state.id,
                    "scope": state.scope,
                    "key": state.key,
                    "reliability_score": state.reliability_score,
                    "calibration_error": state.calibration_error,
                    "validation_count": state.validation_count,
                    "contradiction_rate": state.contradiction_rate,
                    "last_updated": state.last_updated,
                    "downgrade_reasons": state.downgrade_reasons,
                    "payload_json": state.model_dump_json(),
                }
            )
            for state in states
        ]
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MERGE (state:ConfidenceState {id: row.id})
            SET state += row
            """,
            rows=rows,
            database_=settings.neo4j_database,
        )

    def confidence_states(self, product_id: str) -> list[ConfidenceState]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (state:ConfidenceState)
            WHERE state.id IN ["confidence:product:" + $product_id]
               OR (state.scope = "workload" AND state.validation_count > 0)
               OR (state.scope = "inference_path" AND state.validation_count > 0)
            RETURN state.payload_json AS payload_json
            ORDER BY state.last_updated DESC
            LIMIT 30
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        rows = [record.data() for record in records]
        return [_confidence(row) for row in rows if row.get("payload_json")]

    def upsert_contradictions(self, contradictions: list[ContradictionSignal]) -> None:
        rows = [
            _clean_properties(
                {
                    "id": contradiction.id,
                    "product_id": contradiction.product_id,
                    "kind": contradiction.kind,
                    "severity": contradiction.severity,
                    "confidence_score": contradiction.confidence_score,
                    "explanation": contradiction.explanation,
                    "evidence_sources": contradiction.evidence_sources,
                    "affected_workloads": contradiction.affected_workloads,
                    "detected_at": contradiction.detected_at,
                    "payload_json": contradiction.model_dump_json(),
                }
            )
            for contradiction in contradictions
        ]
        self.driver.execute_query(
            """
            UNWIND $rows AS row
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = row.product_id OR p.canonical_key = row.product_id)
            MERGE (contradiction:Contradiction {id: row.id})
            SET contradiction += row
            MERGE (p)-[:HAS_CONTRADICTION]->(contradiction)
            WITH contradiction, row
            UNWIND coalesce(row.evidence_sources, []) AS source
            MERGE (evidence:CognitionEvidence {id: "evidence:" + source})
            SET evidence.source = source,
                evidence.updated_at = datetime()
            MERGE (contradiction)-[:SUPPORTED_BY]->(evidence)
            """,
            rows=rows,
            database_=settings.neo4j_database,
        )

    def contradictions_for_product(self, product_id: str, limit: int = 50) -> list[ContradictionSignal]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_CONTRADICTION]->(contradiction:Contradiction)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN contradiction.payload_json AS payload_json
            ORDER BY contradiction.detected_at DESC
            LIMIT $limit
            """,
            product_id=product_id,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [_contradiction(record.data()) for record in records]

    def create_job(self, job: LearningJob) -> None:
        self.driver.execute_query(
            """
            MERGE (job:LearningJob {id: $id})
            SET job.kind = $kind,
                job.status = $status,
                job.payload_json = $payload_json,
                job.created_at = $created_at,
                job.updated_at = $updated_at,
                job.attempts = $attempts,
                job.max_attempts = $max_attempts,
                job.trace_id = $trace_id,
                job.risk_level = $risk_level,
                job.approval_required = $approval_required
            """,
            id=job.id,
            kind=job.kind,
            status=job.status,
            payload_json=json.dumps(job.payload, sort_keys=True),
            created_at=job.created_at,
            updated_at=job.updated_at,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            trace_id=job.trace_id,
            risk_level=job.risk_level,
            approval_required=job.approval_required,
            database_=settings.neo4j_database,
        )

    def update_job(self, job: LearningJob) -> None:
        self.driver.execute_query(
            """
            MATCH (job:LearningJob {id: $id})
            SET job.status = $status,
                job.updated_at = $updated_at,
                job.error = $error,
                job.attempts = $attempts,
                job.trace_id = $trace_id,
                job.risk_level = $risk_level,
                job.approval_required = $approval_required
            """,
            id=job.id,
            status=job.status,
            updated_at=job.updated_at,
            error=job.error,
            attempts=job.attempts,
            trace_id=job.trace_id,
            risk_level=job.risk_level,
            approval_required=job.approval_required,
            database_=settings.neo4j_database,
        )
