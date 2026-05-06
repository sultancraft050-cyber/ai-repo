from __future__ import annotations

from datetime import UTC, datetime

from app.models.telemetry import (
    DriverVersionInfo,
    TelemetryIngestRequest,
    TelemetryMetrics,
    TelemetrySnapshotIn,
    TelemetrySourceTier,
    WorkloadProfile,
)
from app.services.telemetry_analysis import TelemetryAnalysisEngine, TelemetryIngestionService
from app.services.telemetry_reasoning import TelemetryReasoningEngine


def _snapshot() -> TelemetrySnapshotIn:
    return TelemetrySnapshotIn(
        product_ids=["gpu:test"],
        benchmark_name="Validated Gaming Bench",
        kind="gaming",
        resolution="1440p",
        workload=WorkloadProfile(
            name="ARK Survival Ascended",
            category="gaming",
            engine="Unreal Engine 5",
            api_dependencies=["DirectX 12"],
            cpu_sensitivity=0.78,
            gpu_sensitivity=0.86,
            vram_sensitivity=0.9,
            cache_sensitivity=0.74,
            driver_sensitivity=0.62,
        ),
        metrics=TelemetryMetrics(
            average_fps=92,
            one_percent_low_fps=54,
            point_one_percent_low_fps=34,
            average_frame_time_ms=10.9,
            p95_frame_time_ms=22.4,
            p99_frame_time_ms=38.0,
            frame_time_variance_ms=7.2,
            average_power_w=232,
            peak_power_w=355,
            average_temp_c=81,
            hotspot_temp_c=96,
            vram_used_gb=13.4,
            gpu_utilization_percent=96,
            cpu_utilization_percent=72,
        ),
        source="Validated public benchmark fixture",
        source_type="validated_public_dataset",
        source_tier=TelemetrySourceTier.BENCHMARK_DATABASE,
        trust_score=0.86,
        freshness_score=0.92,
    )


def _driver_snapshot(version: str, fps: float, instability: float, day: int) -> TelemetrySnapshotIn:
    snapshot = _snapshot().model_copy(
        update={
            "timestamp": datetime(2026, 5, day, tzinfo=UTC),
            "driver_version": DriverVersionInfo(vendor="NVIDIA", version=version),
            "metrics": _snapshot().metrics.model_copy(
                update={
                    "average_fps": fps,
                    "one_percent_low_fps": fps * 0.64,
                    "frame_time_variance_ms": instability,
                }
            ),
        }
    )
    return snapshot


class _Repository:
    def __init__(self) -> None:
        self.snapshots = []

    def missing_product_ids(self, product_ids: list[str]) -> list[str]:
        return [item for item in product_ids if item != "gpu:test"]

    def upsert_snapshot(self, snapshot) -> None:
        self.snapshots.append(snapshot)


def test_telemetry_analysis_detects_real_world_bottlenecks() -> None:
    result = TelemetryAnalysisEngine().build_snapshot(_snapshot())
    assert result.primary_limiter in {"gpu", "vram"}
    assert result.frame_time_instability_score > 35
    assert result.thermal_throttling_risk in {"medium", "high"}
    assert any(reason.kind in {"gpu", "vram"} for reason in result.limit_reasons)


def test_telemetry_ingestion_rejects_unknown_products() -> None:
    snapshot = _snapshot().model_copy(update={"product_ids": ["missing:gpu"]})
    repository = _Repository()
    response = TelemetryIngestionService(repository).ingest(
        TelemetryIngestRequest(snapshots=[snapshot], persist=True)
    )
    assert response.accepted_count == 0
    assert response.rejected_count == 1
    assert not repository.snapshots
    assert "unknown product" in response.rejected[0].reasons[0]


def test_telemetry_summary_preserves_resolution_and_driver_evidence() -> None:
    engine = TelemetryAnalysisEngine()
    snapshot = engine.build_snapshot(_snapshot())
    summary = engine.summarize("gpu:test", [snapshot])
    assert summary.sample_count == 1
    assert summary.covered_resolutions == ["1440p"]
    assert summary.average_fps == 92
    assert summary.primary_limiter == snapshot.primary_limiter


def test_reasoning_engine_detects_anomalies_and_predictions() -> None:
    engine = TelemetryAnalysisEngine()
    snapshots = [engine.build_snapshot(_snapshot())]
    summary = engine.summarize("gpu:test", snapshots)
    report = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    assert report.sample_size == 1
    assert report.confidence_score > 0
    assert any(item.kind in {"frame_pacing", "fps_drop", "vram_pressure"} for item in report.anomalies)
    assert report.bottleneck_explanations
    assert report.predictions


def test_reasoning_engine_detects_driver_regression() -> None:
    engine = TelemetryAnalysisEngine()
    previous = engine.build_snapshot(_driver_snapshot("555.85", 118, 2.5, 1))
    current = engine.build_snapshot(_driver_snapshot("556.12", 96, 8.5, 2))
    snapshots = [previous, current]
    summary = engine.summarize("gpu:test", snapshots)
    report = TelemetryReasoningEngine().reason("gpu:test", snapshots, summary)
    assert report.driver_regressions
    assert report.driver_regressions[0].driver_from == "555.85"
    assert report.driver_regressions[0].driver_to == "556.12"
    assert any(pattern.kind == "problematic_driver" for pattern in report.patterns)
