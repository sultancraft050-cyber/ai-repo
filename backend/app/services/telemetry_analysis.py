from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
import json
from statistics import mean
from typing import Iterable

from app.models.telemetry import (
    BottleneckKind,
    TelemetryBottleneckBreakdown,
    TelemetryIngestRejected,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    TelemetryLimitReason,
    TelemetryMetrics,
    TelemetrySnapshotIn,
    TelemetrySnapshotView,
    TelemetrySummary,
    ThermalRisk,
    WorkloadProfile,
)


def _clip(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return round(max(lower, min(upper, value)), 1)


def _avg(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(mean(clean), 2) if clean else None


def _max(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(max(clean), 2) if clean else None


def _source_confidence(sample_count: int, trust_score: float) -> str:
    if sample_count >= 8 and trust_score >= 0.82:
        return "high"
    if sample_count >= 3 and trust_score >= 0.65:
        return "medium"
    return "low"


class TelemetryAnalysisEngine:
    def build_snapshot(self, snapshot: TelemetrySnapshotIn) -> TelemetrySnapshotView:
        flags = self._quality_flags(snapshot)
        bottleneck, reasons = self._bottleneck(snapshot.metrics, snapshot.workload, snapshot.resolution)
        primary = self._primary_limiter(bottleneck)
        instability = self._frame_time_instability(snapshot.metrics)
        thermal_risk = self._thermal_risk(snapshot.metrics, bottleneck.thermal_percent)
        snapshot_id = self._snapshot_id(snapshot)
        return TelemetrySnapshotView(
            **snapshot.model_dump(),
            id=snapshot_id,
            bottleneck=bottleneck,
            primary_limiter=primary,
            frame_time_instability_score=instability,
            thermal_throttling_risk=thermal_risk,
            limit_reasons=reasons,
            flags=flags,
            accepted=True,
        )

    def validate(self, snapshot: TelemetrySnapshotIn) -> list[str]:
        metrics = snapshot.metrics
        reasons: list[str] = []
        if snapshot.trust_score < 0.55:
            reasons.append("telemetry source trust score is below ingestion threshold")
        if snapshot.source_type == "manual_validation" and snapshot.trust_score < 0.72:
            reasons.append("manual validation requires trust_score >= 0.72")
        if metrics.average_fps is not None and metrics.one_percent_low_fps is not None:
            if metrics.one_percent_low_fps > metrics.average_fps * 1.03:
                reasons.append("1% low FPS cannot exceed average FPS")
        if metrics.point_one_percent_low_fps is not None and metrics.one_percent_low_fps is not None:
            if metrics.point_one_percent_low_fps > metrics.one_percent_low_fps * 1.05:
                reasons.append("0.1% low FPS cannot materially exceed 1% low FPS")
        if metrics.p95_frame_time_ms is not None and metrics.average_frame_time_ms is not None:
            if metrics.p95_frame_time_ms < metrics.average_frame_time_ms:
                reasons.append("p95 frame time cannot be lower than average frame time")
        if metrics.p99_frame_time_ms is not None and metrics.p95_frame_time_ms is not None:
            if metrics.p99_frame_time_ms < metrics.p95_frame_time_ms:
                reasons.append("p99 frame time cannot be lower than p95 frame time")
        if metrics.peak_power_w is not None and metrics.average_power_w is not None:
            if metrics.peak_power_w < metrics.average_power_w:
                reasons.append("peak power cannot be lower than average power")
        if metrics.hotspot_temp_c is not None and metrics.average_temp_c is not None:
            if metrics.hotspot_temp_c + 3 < metrics.average_temp_c:
                reasons.append("hotspot temperature cannot be materially lower than average temperature")
        if snapshot.resolution == "4K" and metrics.vram_used_gb is not None and metrics.vram_used_gb < 1:
            reasons.append("4K workload reports implausibly low VRAM use")
        return reasons

    def summarize(self, product_id: str, snapshots: list[TelemetrySnapshotView]) -> TelemetrySummary:
        if not snapshots:
            return TelemetrySummary(
                product_id=product_id,
                sample_count=0,
                confidence="low",
                bottleneck=TelemetryBottleneckBreakdown(),
                primary_limiter="none",
                thermal_throttling_risk="unknown",
                notes=["No validated telemetry snapshots are available for this product yet."],
            )
        bottleneck = TelemetryBottleneckBreakdown(
            cpu_percent=_avg(snapshot.bottleneck.cpu_percent for snapshot in snapshots) or 0,
            gpu_percent=_avg(snapshot.bottleneck.gpu_percent for snapshot in snapshots) or 0,
            vram_percent=_avg(snapshot.bottleneck.vram_percent for snapshot in snapshots) or 0,
            thermal_percent=_avg(snapshot.bottleneck.thermal_percent for snapshot in snapshots) or 0,
            driver_percent=_avg(snapshot.bottleneck.driver_percent for snapshot in snapshots) or 0,
            memory_percent=_avg(snapshot.bottleneck.memory_percent for snapshot in snapshots) or 0,
            bandwidth_percent=_avg(snapshot.bottleneck.bandwidth_percent for snapshot in snapshots) or 0,
            storage_percent=_avg(snapshot.bottleneck.storage_percent for snapshot in snapshots) or 0,
        )
        primary = self._primary_limiter(bottleneck)
        trust = _avg(snapshot.trust_score for snapshot in snapshots) or 0
        thermal_counter = Counter(snapshot.thermal_throttling_risk for snapshot in snapshots)
        thermal_risk = self._summary_thermal_risk(thermal_counter, bottleneck.thermal_percent)
        notes = self._summary_notes(snapshots, bottleneck, thermal_risk)
        drivers = sorted(
            {
                f"{snapshot.driver_version.vendor} {snapshot.driver_version.version}"
                for snapshot in snapshots
                if snapshot.driver_version
            }
        )
        latest = max(snapshot.timestamp for snapshot in snapshots)
        return TelemetrySummary(
            product_id=product_id,
            sample_count=len(snapshots),
            confidence=_source_confidence(len(snapshots), trust),
            average_fps=_avg(snapshot.metrics.average_fps for snapshot in snapshots),
            one_percent_low_fps=_avg(snapshot.metrics.one_percent_low_fps for snapshot in snapshots),
            average_frame_time_ms=_avg(
                snapshot.metrics.average_frame_time_ms or self._fps_to_frame_time(snapshot.metrics.average_fps)
                for snapshot in snapshots
            ),
            frame_time_instability_score=_avg(
                snapshot.frame_time_instability_score for snapshot in snapshots
            ),
            average_power_w=_avg(snapshot.metrics.average_power_w for snapshot in snapshots),
            peak_power_w=_max(snapshot.metrics.peak_power_w for snapshot in snapshots),
            average_temp_c=_avg(snapshot.metrics.average_temp_c for snapshot in snapshots),
            hotspot_temp_c=_max(snapshot.metrics.hotspot_temp_c for snapshot in snapshots),
            bottleneck=bottleneck,
            primary_limiter=primary,
            thermal_throttling_risk=thermal_risk,
            covered_resolutions=sorted({snapshot.resolution for snapshot in snapshots}),
            covered_workloads=sorted({snapshot.workload.name for snapshot in snapshots}),
            latest_driver_versions=drivers[-4:],
            notes=notes,
            updated_at=latest,
        )

    def _snapshot_id(self, snapshot: TelemetrySnapshotIn) -> str:
        payload = {
            "products": snapshot.product_ids,
            "benchmark": snapshot.benchmark_name,
            "kind": snapshot.kind,
            "resolution": snapshot.resolution,
            "workload": snapshot.workload.name,
            "timestamp": snapshot.timestamp.isoformat(),
            "source": snapshot.source,
        }
        digest = sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
        return f"telemetry-{digest}"

    def _quality_flags(self, snapshot: TelemetrySnapshotIn) -> list[str]:
        flags: list[str] = []
        metrics = snapshot.metrics
        if snapshot.freshness_score < 0.45:
            flags.append("stale_source")
        if snapshot.trust_score < 0.72:
            flags.append("limited_trust")
        low_ratio = self._low_fps_ratio(metrics)
        if low_ratio is not None and low_ratio < 0.62:
            flags.append("poor_one_percent_lows")
        if metrics.hotspot_temp_c is not None and metrics.hotspot_temp_c >= 100:
            flags.append("hotspot_temperature_risk")
        if metrics.peak_power_w and metrics.average_power_w and metrics.peak_power_w > metrics.average_power_w * 1.75:
            flags.append("large_power_spike")
        return flags

    def _bottleneck(
        self,
        metrics: TelemetryMetrics,
        workload: WorkloadProfile,
        resolution: str,
    ) -> tuple[TelemetryBottleneckBreakdown, list[TelemetryLimitReason]]:
        low_ratio = self._low_fps_ratio(metrics)
        instability = self._frame_time_instability(metrics)
        high_resolution = 1.0 if resolution in {"4K", "ultrawide"} else 0.6 if resolution == "1440p" else 0.35

        cpu = 0.0
        if metrics.cpu_utilization_percent is not None and metrics.cpu_utilization_percent >= 88:
            cpu += 34
        if metrics.gpu_utilization_percent is not None and metrics.gpu_utilization_percent < 88 and low_ratio is not None:
            cpu += (1 - low_ratio) * 42 * workload.cpu_sensitivity
        if low_ratio is not None and low_ratio < 0.74:
            cpu += (0.74 - low_ratio) * 95 * max(workload.cpu_sensitivity, workload.cache_sensitivity)

        gpu = 0.0
        if metrics.gpu_utilization_percent is not None and metrics.gpu_utilization_percent >= 92:
            gpu += 44
        if metrics.average_fps is not None and metrics.average_fps < 75:
            gpu += (75 - metrics.average_fps) * 0.38 * workload.gpu_sensitivity * (0.8 + high_resolution)
        if metrics.average_frame_time_ms is not None and metrics.average_frame_time_ms > 18:
            gpu += (metrics.average_frame_time_ms - 18) * 1.4 * workload.gpu_sensitivity

        vram = 0.0
        if metrics.vram_used_gb is not None:
            if metrics.vram_used_gb >= 11:
                vram += min(45, (metrics.vram_used_gb - 10) * 6.2)
            if metrics.vram_used_gb >= 15:
                vram += 24
        vram += workload.vram_sensitivity * high_resolution * max(0, instability - 38) * 0.42

        thermal = 0.0
        if metrics.average_temp_c is not None and metrics.average_temp_c >= 82:
            thermal += (metrics.average_temp_c - 78) * 2.8
        if metrics.hotspot_temp_c is not None and metrics.hotspot_temp_c >= 94:
            thermal += (metrics.hotspot_temp_c - 90) * 2.4
        if metrics.peak_power_w is not None and metrics.average_power_w is not None:
            thermal += max(0, metrics.peak_power_w - metrics.average_power_w * 1.45) * 0.06

        driver = 0.0
        if instability >= 42:
            driver += (instability - 35) * workload.driver_sensitivity * 0.58
        if metrics.point_one_percent_low_fps and metrics.average_fps:
            deep_low_ratio = metrics.point_one_percent_low_fps / metrics.average_fps
            if deep_low_ratio < 0.45:
                driver += (0.45 - deep_low_ratio) * 80 * workload.driver_sensitivity

        memory = 0.0
        if metrics.system_memory_used_gb is not None and metrics.system_memory_used_gb >= 24:
            memory += min(55, (metrics.system_memory_used_gb - 20) * 1.5)
        if workload.cache_sensitivity >= 0.75 and instability >= 50:
            memory += (instability - 42) * 0.32

        bandwidth = 0.0
        if high_resolution >= 0.6 and metrics.gpu_utilization_percent is not None:
            if metrics.gpu_utilization_percent < 86 and instability >= 34 and workload.vram_sensitivity >= 0.68:
                bandwidth += (86 - metrics.gpu_utilization_percent) * 0.72 + (instability - 28) * 0.28
        if workload.category in {"ai", "cad", "simulation"} and metrics.system_memory_used_gb is not None:
            if metrics.system_memory_used_gb >= 20:
                bandwidth += min(38, (metrics.system_memory_used_gb - 18) * 1.2)
        if workload.vram_sensitivity >= 0.82 and high_resolution >= 0.6 and vram >= 18:
            bandwidth += vram * 0.22

        storage = 0.0
        if workload.category in {"compile", "simulation"} and metrics.compile_time_seconds:
            storage += min(35, metrics.compile_time_seconds / 90)

        bottleneck = TelemetryBottleneckBreakdown(
            cpu_percent=_clip(cpu),
            gpu_percent=_clip(gpu),
            vram_percent=_clip(vram),
            thermal_percent=_clip(thermal),
            driver_percent=_clip(driver),
            memory_percent=_clip(memory),
            bandwidth_percent=_clip(bandwidth),
            storage_percent=_clip(storage),
        )
        reasons = self._limit_reasons(bottleneck, workload)
        return bottleneck, reasons

    def _limit_reasons(
        self,
        bottleneck: TelemetryBottleneckBreakdown,
        workload: WorkloadProfile,
    ) -> list[TelemetryLimitReason]:
        reason_map: dict[str, str] = {
            "cpu": f"{workload.name} shows CPU/cache-sensitive frame pacing behavior.",
            "gpu": f"{workload.name} is constrained by GPU render throughput.",
            "vram": f"{workload.name} is sensitive to VRAM pressure at the tested resolution.",
            "thermal": "Thermal readings indicate sustained boost or throttling risk.",
            "driver": "Frame pacing pattern is driver/version sensitive.",
            "memory": "System memory or cache pressure is visible in the telemetry.",
            "bandwidth": "Memory, bus, or data-movement pressure is visible in the workload telemetry.",
            "storage": "Storage-sensitive workload metrics indicate I/O contribution.",
        }
        values = {
            "cpu": bottleneck.cpu_percent,
            "gpu": bottleneck.gpu_percent,
            "vram": bottleneck.vram_percent,
            "thermal": bottleneck.thermal_percent,
            "driver": bottleneck.driver_percent,
            "memory": bottleneck.memory_percent,
            "bandwidth": bottleneck.bandwidth_percent,
            "storage": bottleneck.storage_percent,
        }
        return [
            TelemetryLimitReason(kind=kind, percent=percent, reason=reason_map[kind])
            for kind, percent in sorted(values.items(), key=lambda item: item[1], reverse=True)
            if percent >= 18
        ][:4]

    def _primary_limiter(self, bottleneck: TelemetryBottleneckBreakdown) -> BottleneckKind:
        values = {
            "cpu": bottleneck.cpu_percent,
            "gpu": bottleneck.gpu_percent,
            "vram": bottleneck.vram_percent,
            "thermal": bottleneck.thermal_percent,
            "driver": bottleneck.driver_percent,
            "memory": bottleneck.memory_percent,
            "bandwidth": bottleneck.bandwidth_percent,
            "storage": bottleneck.storage_percent,
        }
        kind, percent = max(values.items(), key=lambda item: item[1])
        return kind if percent >= 18 else "none"  # type: ignore[return-value]

    def _frame_time_instability(self, metrics: TelemetryMetrics) -> float:
        average_frame = metrics.average_frame_time_ms or self._fps_to_frame_time(metrics.average_fps)
        variance = metrics.frame_time_variance_ms
        if variance is None and metrics.p95_frame_time_ms and average_frame:
            variance = max(0.0, metrics.p95_frame_time_ms - average_frame)
        low_ratio = self._low_fps_ratio(metrics)
        low_signal = 0.0 if low_ratio is None else max(0.0, (0.92 - low_ratio) * 118)
        variance_signal = 0.0 if variance is None else min(100.0, variance * 8.5)
        p99_signal = 0.0
        if metrics.p99_frame_time_ms and average_frame:
            p99_signal = max(0.0, metrics.p99_frame_time_ms - average_frame * 1.6) * 1.4
        return _clip(low_signal * 0.48 + variance_signal * 0.38 + p99_signal * 0.14)

    def _low_fps_ratio(self, metrics: TelemetryMetrics) -> float | None:
        if metrics.average_fps and metrics.one_percent_low_fps is not None and metrics.average_fps > 0:
            return metrics.one_percent_low_fps / metrics.average_fps
        return None

    def _fps_to_frame_time(self, fps: float | None) -> float | None:
        return 1000 / fps if fps and fps > 0 else None

    def _thermal_risk(self, metrics: TelemetryMetrics, thermal_percent: float) -> ThermalRisk:
        if thermal_percent >= 65:
            return "high"
        if metrics.hotspot_temp_c is not None and metrics.hotspot_temp_c >= 102:
            return "high"
        if thermal_percent >= 35:
            return "medium"
        if metrics.hotspot_temp_c is not None and metrics.hotspot_temp_c >= 94:
            return "medium"
        if metrics.average_temp_c is not None and metrics.average_temp_c >= 84:
            return "medium"
        if metrics.average_temp_c is None and metrics.hotspot_temp_c is None:
            return "unknown"
        return "low"

    def _summary_thermal_risk(self, counter: Counter[str], thermal_percent: float) -> ThermalRisk:
        total = sum(counter.values())
        if total == 0:
            return "unknown"
        if counter["high"] / total >= 0.22 or thermal_percent >= 55:
            return "high"
        if (counter["high"] + counter["medium"]) / total >= 0.28 or thermal_percent >= 30:
            return "medium"
        return "low"

    def _summary_notes(
        self,
        snapshots: list[TelemetrySnapshotView],
        bottleneck: TelemetryBottleneckBreakdown,
        thermal_risk: ThermalRisk,
    ) -> list[str]:
        notes = [
            f"Validated telemetry covers {len({snapshot.resolution for snapshot in snapshots})} resolution bucket(s)."
        ]
        primary = self._primary_limiter(bottleneck)
        if primary != "none":
            notes.append(f"Observed bottleneck trend is {primary.upper()} at {getattr(bottleneck, primary + '_percent'):.1f}%.")
        fps = _avg(snapshot.metrics.average_fps for snapshot in snapshots)
        lows = _avg(snapshot.metrics.one_percent_low_fps for snapshot in snapshots)
        if fps and lows:
            notes.append(f"Average FPS is {fps:.1f} with {lows:.1f} FPS 1% lows across accepted samples.")
        if thermal_risk in {"medium", "high"}:
            notes.append(f"Thermal throttling risk is {thermal_risk}; recommendations should preserve cooling headroom.")
        return notes[:4]


class TelemetryIngestionService:
    def __init__(self, repository) -> None:
        self.repository = repository
        self.engine = TelemetryAnalysisEngine()

    def ingest(self, request: TelemetryIngestRequest) -> TelemetryIngestResponse:
        accepted: list[TelemetrySnapshotView] = []
        rejected: list[TelemetryIngestRejected] = []
        for index, snapshot in enumerate(request.snapshots):
            reasons = self.engine.validate(snapshot)
            if request.persist and not request.validate_only and hasattr(self.repository, "missing_product_ids"):
                missing = self.repository.missing_product_ids(snapshot.product_ids)
                if missing:
                    reasons.append(f"unknown product id(s): {', '.join(missing)}")
            if reasons:
                rejected.append(TelemetryIngestRejected(index=index, reasons=reasons))
                continue
            view = self.engine.build_snapshot(snapshot)
            accepted.append(view)
            if request.persist and not request.validate_only:
                self.repository.upsert_snapshot(view)
        return TelemetryIngestResponse(
            accepted_count=len(accepted),
            rejected_count=len(rejected),
            snapshots=accepted,
            rejected=rejected,
        )
