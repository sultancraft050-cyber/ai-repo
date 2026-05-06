from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
import re
from typing import Any

from neo4j import Driver

from app.core.config import settings
from app.models.telemetry import TelemetryReasoningReport, TelemetrySnapshotView


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


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _key(value: str, prefix: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    digest = sha256(value.lower().encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{normalized or digest}:{digest}"


def _snapshot_from_record(data: dict[str, Any]) -> TelemetrySnapshotView:
    return TelemetrySnapshotView.model_validate_json(data["payload_json"])


def _reasoning_from_record(data: dict[str, Any]) -> TelemetryReasoningReport:
    return TelemetryReasoningReport.model_validate_json(data["payload_json"])


class Neo4jTelemetryRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def apply_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT benchmark_id IF NOT EXISTS FOR (n:Benchmark) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT game_canonical_key IF NOT EXISTS FOR (n:Game) REQUIRE n.canonical_key IS UNIQUE",
            "CREATE CONSTRAINT workload_canonical_key IF NOT EXISTS "
            "FOR (n:Workload) REQUIRE n.canonical_key IS UNIQUE",
            "CREATE CONSTRAINT driver_version_id IF NOT EXISTS "
            "FOR (n:DriverVersion) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT telemetry_snapshot_id IF NOT EXISTS "
            "FOR (n:TelemetrySnapshot) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT bottleneck_factor_name IF NOT EXISTS "
            "FOR (n:BottleneckFactor) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT telemetry_reasoning_id IF NOT EXISTS "
            "FOR (n:TelemetryReasoning) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT telemetry_anomaly_id IF NOT EXISTS "
            "FOR (n:TelemetryAnomaly) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT driver_regression_id IF NOT EXISTS "
            "FOR (n:DriverRegression) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT telemetry_pattern_id IF NOT EXISTS "
            "FOR (n:TelemetryPattern) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT predictive_insight_id IF NOT EXISTS "
            "FOR (n:PredictiveInsight) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT recommendation_target_name IF NOT EXISTS "
            "FOR (n:RecommendationTarget) REQUIRE n.name IS UNIQUE",
            "CREATE INDEX telemetry_snapshot_timestamp IF NOT EXISTS "
            "FOR (n:TelemetrySnapshot) ON (n.timestamp)",
            "CREATE INDEX telemetry_snapshot_resolution IF NOT EXISTS "
            "FOR (n:TelemetrySnapshot) ON (n.resolution)",
            "CREATE INDEX telemetry_snapshot_kind IF NOT EXISTS "
            "FOR (n:TelemetrySnapshot) ON (n.kind)",
            "CREATE INDEX telemetry_snapshot_primary_limiter IF NOT EXISTS "
            "FOR (n:TelemetrySnapshot) ON (n.primary_limiter)",
            "CREATE INDEX telemetry_reasoning_generated_at IF NOT EXISTS "
            "FOR (n:TelemetryReasoning) ON (n.generated_at)",
            "CREATE INDEX telemetry_anomaly_kind IF NOT EXISTS "
            "FOR (n:TelemetryAnomaly) ON (n.kind)",
            "CREATE INDEX telemetry_anomaly_severity IF NOT EXISTS "
            "FOR (n:TelemetryAnomaly) ON (n.severity)",
        ]
        for statement in statements:
            self.driver.execute_query(statement, database_=settings.neo4j_database)

    def missing_product_ids(self, product_ids: list[str]) -> list[str]:
        records, _, _ = self.driver.execute_query(
            """
            UNWIND $product_ids AS product_id
            OPTIONAL MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = product_id OR p.canonical_key = product_id)
            WITH product_id, count(p) AS matches
            WHERE matches = 0
            RETURN product_id
            """,
            product_ids=product_ids,
            database_=settings.neo4j_database,
        )
        return [str(record["product_id"]) for record in records]

    def upsert_snapshot(self, snapshot: TelemetrySnapshotView) -> None:
        benchmark_id = _key(f"{snapshot.benchmark_name}|{snapshot.kind}", "benchmark")
        workload_key = _key(
            f"{snapshot.workload.category}|{snapshot.workload.name}|{snapshot.workload.engine or ''}",
            "workload",
        )
        benchmark = _clean_properties(
            {
                "id": benchmark_id,
                "name": snapshot.benchmark_name,
                "kind": snapshot.kind,
                "source": snapshot.source,
                "source_type": snapshot.source_type,
                "source_tier": int(snapshot.source_tier),
                "source_url": snapshot.source_url,
                "trust_score": snapshot.trust_score,
                "freshness_score": snapshot.freshness_score,
                "updated_at": datetime.now(UTC),
            }
        )
        workload = _clean_properties(
            {
                "canonical_key": workload_key,
                "name": snapshot.workload.name,
                "category": snapshot.workload.category,
                "engine": snapshot.workload.engine,
                "api_dependencies": snapshot.workload.api_dependencies,
                "cpu_sensitivity": snapshot.workload.cpu_sensitivity,
                "gpu_sensitivity": snapshot.workload.gpu_sensitivity,
                "vram_sensitivity": snapshot.workload.vram_sensitivity,
                "cache_sensitivity": snapshot.workload.cache_sensitivity,
                "driver_sensitivity": snapshot.workload.driver_sensitivity,
                "thermal_sensitivity": snapshot.workload.thermal_sensitivity,
                "updated_at": datetime.now(UTC),
            }
        )
        metrics = snapshot.metrics.model_dump()
        bottleneck = snapshot.bottleneck.model_dump()
        snapshot_props = _clean_properties(
            {
                "id": snapshot.id,
                "kind": snapshot.kind,
                "resolution": snapshot.resolution,
                "settings_preset": snapshot.settings_preset,
                "benchmark_name": snapshot.benchmark_name,
                "workload_name": snapshot.workload.name,
                "timestamp": snapshot.timestamp,
                "source": snapshot.source,
                "source_url": snapshot.source_url,
                "source_type": snapshot.source_type,
                "source_tier": int(snapshot.source_tier),
                "trust_score": snapshot.trust_score,
                "freshness_score": snapshot.freshness_score,
                "primary_limiter": snapshot.primary_limiter,
                "frame_time_instability_score": snapshot.frame_time_instability_score,
                "thermal_throttling_risk": snapshot.thermal_throttling_risk,
                "accepted": snapshot.accepted,
                "flags": snapshot.flags,
                "payload_json": snapshot.model_dump_json(),
                **{f"metric_{key}": value for key, value in metrics.items()},
                **{f"bottleneck_{key}": value for key, value in bottleneck.items()},
            }
        )
        self.driver.execute_query(
            """
            MERGE (snapshot:TelemetrySnapshot {id: $snapshot.id})
            SET snapshot += $snapshot
            MERGE (benchmark:Benchmark {id: $benchmark.id})
            SET benchmark += $benchmark
            MERGE (workload:Workload {canonical_key: $workload.canonical_key})
            SET workload += $workload
            MERGE (snapshot)-[:BENCHMARKED_WITH]->(benchmark)
            MERGE (snapshot)-[:BENCHMARKED_WITH]->(workload)
            """,
            snapshot=snapshot_props,
            benchmark=benchmark,
            workload=workload,
            database_=settings.neo4j_database,
        )
        if snapshot.kind == "gaming" or snapshot.workload.category == "gaming":
            self.driver.execute_query(
                """
                MATCH (snapshot:TelemetrySnapshot {id: $snapshot_id})
                MERGE (game:Game {canonical_key: $workload.canonical_key})
                SET game += $workload
                MERGE (snapshot)-[:BENCHMARKED_WITH]->(game)
                """,
                snapshot_id=snapshot.id,
                workload=workload,
                database_=settings.neo4j_database,
            )
        if snapshot.driver_version:
            driver_id = _key(
                "|".join(
                    [
                        snapshot.driver_version.vendor,
                        snapshot.driver_version.version,
                        snapshot.driver_version.bios_version or "",
                        snapshot.driver_version.firmware_revision or "",
                    ]
                ),
                "driver",
            )
            driver = _clean_properties(
                {
                    "id": driver_id,
                    "vendor": snapshot.driver_version.vendor,
                    "version": snapshot.driver_version.version,
                    "release_date": snapshot.driver_version.release_date,
                    "bios_version": snapshot.driver_version.bios_version,
                    "firmware_revision": snapshot.driver_version.firmware_revision,
                    "updated_at": datetime.now(UTC),
                }
            )
            self.driver.execute_query(
                """
                MATCH (snapshot:TelemetrySnapshot {id: $snapshot_id})
                MERGE (driver:DriverVersion {id: $driver.id})
                SET driver += $driver
                MERGE (snapshot)-[:BENCHMARKED_WITH]->(driver)
                MERGE (driver)-[:AFFECTS]->(snapshot)
                WITH driver
                UNWIND $product_ids AS product_id
                MATCH (p)
                WHERE (p:Product OR p:Component)
                  AND (p.id = product_id OR p.canonical_key = product_id)
                MERGE (driver)-[:AFFECTS]->(p)
                """,
                snapshot_id=snapshot.id,
                driver=driver,
                product_ids=snapshot.product_ids,
                database_=settings.neo4j_database,
            )
        self.driver.execute_query(
            """
            MATCH (snapshot:TelemetrySnapshot {id: $snapshot_id})
            UNWIND $product_ids AS product_id
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = product_id OR p.canonical_key = product_id)
            MERGE (p)-[:HAS_TELEMETRY]->(snapshot)
            MERGE (snapshot)-[:TESTED_ON]->(p)
            SET p.telemetry_sample_count = coalesce(p.telemetry_sample_count, 0) + 1,
                p.telemetry_updated_at = datetime()
            """,
            snapshot_id=snapshot.id,
            product_ids=snapshot.product_ids,
            database_=settings.neo4j_database,
        )
        self.driver.execute_query(
            """
            MATCH (snapshot:TelemetrySnapshot {id: $snapshot_id})
            UNWIND $limits AS limit
            MERGE (factor:BottleneckFactor {name: limit.kind})
            MERGE (snapshot)-[rel:LIMITED_BY]->(factor)
            SET rel.percent = limit.percent,
                rel.reason = limit.reason
            """,
            snapshot_id=snapshot.id,
            limits=[reason.model_dump() for reason in snapshot.limit_reasons],
            database_=settings.neo4j_database,
        )

    def snapshots_for_product(
        self,
        product_id: str,
        *,
        resolution: str | None = None,
        workload: str | None = None,
        limit: int = 200,
    ) -> list[TelemetrySnapshotView]:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)<-[:TESTED_ON]-(snapshot:TelemetrySnapshot)
            WHERE (p.id = $product_id OR p.canonical_key = $product_id)
              AND ($resolution IS NULL OR snapshot.resolution = $resolution)
              AND (
                $workload IS NULL
                OR toLower(snapshot.workload_name) CONTAINS toLower($workload)
                OR toLower(snapshot.kind) CONTAINS toLower($workload)
              )
            RETURN snapshot.payload_json AS payload_json
            ORDER BY snapshot.timestamp DESC
            LIMIT $limit
            """,
            product_id=product_id,
            resolution=resolution,
            workload=workload,
            limit=limit,
            database_=settings.neo4j_database,
        )
        return [
            _snapshot_from_record(data)
            for record in records
            for data in [record.data()]
            if data.get("payload_json")
        ]

    def latest_snapshots(self, product_id: str, limit: int = 20) -> list[TelemetrySnapshotView]:
        return self.snapshots_for_product(product_id, limit=limit)

    def upsert_reasoning(self, report: TelemetryReasoningReport) -> None:
        payload_json = report.model_dump_json()
        report_props = _clean_properties(
            {
                "id": report.id,
                "product_id": report.product_id,
                "generated_at": report.generated_at,
                "confidence_score": report.confidence_score,
                "sample_size": report.sample_size,
                "evidence_sources": report.evidence_sources,
                "summary": report.summary,
                "warnings": report.warnings,
                "payload_json": payload_json,
            }
        )
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MERGE (report:TelemetryReasoning {id: $report.id})
            SET report += $report
            MERGE (p)-[:HAS_TELEMETRY_REASONING]->(report)
            SET p.telemetry_reasoning_confidence = $confidence_score,
                p.telemetry_reasoning_generated_at = $generated_at,
                p.telemetry_warning_count = size($warnings)
            """,
            product_id=report.product_id,
            report=report_props,
            confidence_score=report.confidence_score,
            generated_at=report.generated_at,
            warnings=report.warnings,
            database_=settings.neo4j_database,
        )
        self._upsert_reasoning_bottlenecks(report)
        self._upsert_anomalies(report)
        self._upsert_regressions(report)
        self._upsert_patterns(report)
        self._upsert_predictions(report)
        self._upsert_recommendations(report)

    def latest_reasoning(self, product_id: str) -> TelemetryReasoningReport | None:
        records, _, _ = self.driver.execute_query(
            """
            MATCH (p)-[:HAS_TELEMETRY_REASONING]->(report:TelemetryReasoning)
            WHERE p.id = $product_id OR p.canonical_key = $product_id
            RETURN report.payload_json AS payload_json
            ORDER BY report.generated_at DESC
            LIMIT 1
            """,
            product_id=product_id,
            database_=settings.neo4j_database,
        )
        return _reasoning_from_record(records[0].data()) if records else None

    def _upsert_reasoning_bottlenecks(self, report: TelemetryReasoningReport) -> None:
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MATCH (report:TelemetryReasoning {id: $report_id})
            UNWIND $limits AS limit
            MERGE (factor:BottleneckFactor {name: limit.kind})
            MERGE (report)-[reportRel:LIMITED_BY]->(factor)
            SET reportRel.percent = limit.percent,
                reportRel.reason = limit.reason
            MERGE (p)-[productRel:LIMITED_BY]->(factor)
            SET productRel.percent = limit.percent,
                productRel.reason = limit.reason,
                productRel.updated_at = datetime()
            """,
            product_id=report.product_id,
            report_id=report.id,
            limits=[reason.model_dump() for reason in report.bottleneck_explanations],
            database_=settings.neo4j_database,
        )

    def _upsert_anomalies(self, report: TelemetryReasoningReport) -> None:
        anomalies = [
            _clean_properties(
                {
                    **anomaly.model_dump(),
                    "payload_json": anomaly.model_dump_json(),
                    "evidence_json": json.dumps(
                        [item.model_dump(mode="json") for item in anomaly.evidence],
                        sort_keys=True,
                        default=_json_default,
                    ),
                }
            )
            for anomaly in report.anomalies
        ]
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MATCH (report:TelemetryReasoning {id: $report_id})
            UNWIND $anomalies AS anomaly
            MERGE (node:TelemetryAnomaly {id: anomaly.id})
            SET node += anomaly
            MERGE (report)-[:HAS_ANOMALY]->(node)
            MERGE (p)-[:HAS_ANOMALY]->(node)
            WITH p, report, node, anomaly
            FOREACH (_ IN CASE WHEN anomaly.kind = "thermal_throttling" THEN [1] ELSE [] END |
              MERGE (p)-[:SHOWS_THROTTLING]->(node)
            )
            WITH p, anomaly
            FOREACH (_ IN CASE WHEN anomaly.kind IN ["cpu_saturation", "vram_pressure", "frame_pacing", "workload_bottleneck"] THEN [1] ELSE [] END |
              MERGE (factor:BottleneckFactor {name: anomaly.kind})
              MERGE (p)-[rel:LIMITED_BY]->(factor)
              SET rel.reason = anomaly.explanation,
                  rel.confidence_score = anomaly.confidence_score,
                  rel.updated_at = datetime()
            )
            """,
            product_id=report.product_id,
            report_id=report.id,
            anomalies=anomalies,
            database_=settings.neo4j_database,
        )

    def _upsert_regressions(self, report: TelemetryReasoningReport) -> None:
        regressions = [
            _clean_properties(
                {
                    **regression.model_dump(),
                    "payload_json": regression.model_dump_json(),
                }
            )
            for regression in report.driver_regressions
        ]
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MATCH (report:TelemetryReasoning {id: $report_id})
            UNWIND $regressions AS regression
            MERGE (node:DriverRegression {id: regression.id})
            SET node += regression
            MERGE (report)-[:REGRESSION_DETECTED]->(node)
            MERGE (p)-[:REGRESSION_DETECTED]->(node)
            """,
            product_id=report.product_id,
            report_id=report.id,
            regressions=regressions,
            database_=settings.neo4j_database,
        )

    def _upsert_patterns(self, report: TelemetryReasoningReport) -> None:
        patterns = [
            _clean_properties(
                {
                    **pattern.model_dump(),
                    "payload_json": pattern.model_dump_json(),
                }
            )
            for pattern in report.patterns
        ]
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MATCH (report:TelemetryReasoning {id: $report_id})
            UNWIND $patterns AS pattern
            MERGE (node:TelemetryPattern {id: pattern.id})
            SET node += pattern
            MERGE (report)-[:HAS_PATTERN]->(node)
            MERGE (p)-[:HAS_PATTERN]->(node)
            """,
            product_id=report.product_id,
            report_id=report.id,
            patterns=patterns,
            database_=settings.neo4j_database,
        )

    def _upsert_predictions(self, report: TelemetryReasoningReport) -> None:
        predictions = [
            _clean_properties(
                {
                    **prediction.model_dump(),
                    "payload_json": prediction.model_dump_json(),
                }
            )
            for prediction in report.predictions
        ]
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MATCH (report:TelemetryReasoning {id: $report_id})
            UNWIND $predictions AS prediction
            MERGE (node:PredictiveInsight {id: prediction.id})
            SET node += prediction
            MERGE (report)-[:PREDICTS]->(node)
            MERGE (p)-[:HAS_PREDICTION]->(node)
            """,
            product_id=report.product_id,
            report_id=report.id,
            predictions=predictions,
            database_=settings.neo4j_database,
        )

    def _upsert_recommendations(self, report: TelemetryReasoningReport) -> None:
        self.driver.execute_query(
            """
            MATCH (p)
            WHERE (p:Product OR p:Component)
              AND (p.id = $product_id OR p.canonical_key = $product_id)
            MATCH (report:TelemetryReasoning {id: $report_id})
            UNWIND $recommended_for AS target
            MERGE (node:RecommendationTarget {name: target})
            MERGE (report)-[:RECOMMENDED_FOR]->(node)
            MERGE (p)-[:RECOMMENDED_FOR]->(node)
            """,
            product_id=report.product_id,
            report_id=report.id,
            recommended_for=report.recommended_for,
            database_=settings.neo4j_database,
        )
