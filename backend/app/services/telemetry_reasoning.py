from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from statistics import mean
from typing import Iterable

from app.models.telemetry import (
    DriverRegressionFinding,
    TelemetryAnomaly,
    TelemetryBottleneckBreakdown,
    TelemetryEvidencePoint,
    TelemetryLimitReason,
    TelemetryPatternFinding,
    TelemetryReasoningReport,
    TelemetrySeverity,
    TelemetrySnapshotView,
    TelemetrySummary,
    PredictiveTelemetryInsight,
)
from app.services.telemetry_analysis import TelemetryAnalysisEngine


def _avg(values: Iterable[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(mean(clean), 2) if clean else None


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return round(max(lower, min(upper, value)), 3)


def _percent(value: float | None) -> float | None:
    return round(value * 100, 2) if value is not None else None


def _id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{prefix}-{sha256(raw.encode('utf-8')).hexdigest()[:18]}"


def _severity(score: float, critical: float, warning: float) -> TelemetrySeverity:
    if score >= critical:
        return "critical"
    if score >= warning:
        return "warning"
    return "info"


class TelemetryReasoningEngine:
    def reason(
        self,
        product_id: str,
        snapshots: list[TelemetrySnapshotView],
        summary: TelemetrySummary | None = None,
    ) -> TelemetryReasoningReport:
        summary = summary or TelemetryAnalysisEngine().summarize(product_id, snapshots)
        evidence_sources = self._evidence_sources(snapshots)
        sample_size = len(snapshots)
        anomalies = self._anomalies(product_id, snapshots, summary)
        regressions = self._driver_regressions(product_id, snapshots)
        patterns = self._patterns(product_id, snapshots, summary, anomalies, regressions)
        predictions = self._predictions(product_id, summary, anomalies, patterns)
        bottleneck_explanations = self._bottleneck_explanations(summary, snapshots)
        workload_reasoning = self._workload_reasoning(summary, snapshots)
        confidence = self._confidence(sample_size, snapshots, anomalies, regressions)
        recommended_for = self._recommended_for(summary, anomalies)
        warnings = self._warnings(anomalies, regressions, patterns, predictions)
        summary_lines = self._summary_lines(summary, anomalies, regressions, patterns, predictions)
        return TelemetryReasoningReport(
            id=_id("telemetry-reasoning", product_id, summary.updated_at.isoformat(), sample_size),
            product_id=product_id,
            generated_at=datetime.now(UTC),
            confidence_score=confidence,
            sample_size=sample_size,
            evidence_sources=evidence_sources,
            ai_explanation=self._ai_explanation(
                product_id,
                summary,
                anomalies,
                patterns,
                bottleneck_explanations,
                workload_reasoning,
            ),
            summary=summary_lines,
            workload_reasoning=workload_reasoning,
            bottleneck_explanations=bottleneck_explanations,
            anomalies=anomalies,
            driver_regressions=regressions,
            patterns=patterns,
            predictions=predictions,
            recommended_for=recommended_for,
            warnings=warnings,
        )

    def _anomalies(
        self,
        product_id: str,
        snapshots: list[TelemetrySnapshotView],
        summary: TelemetrySummary,
    ) -> list[TelemetryAnomaly]:
        anomalies: list[TelemetryAnomaly] = []
        if summary.sample_count == 0:
            return anomalies
        pacing = summary.frame_time_instability_score or 0
        if pacing >= 42:
            causes = ["1% low collapse", "long-tail frame-time spikes"]
            if summary.bottleneck.cpu_percent >= 26:
                causes.append("CPU frame delivery instability")
            if summary.bottleneck.driver_percent >= 18:
                causes.append("driver-sensitive frame pacing")
            anomalies.append(
                self._anomaly(
                    product_id,
                    "frame_pacing",
                    _severity(pacing, 62, 42),
                    "Abnormal frame pacing detected",
                    "Frame pacing variance exceeds the stability threshold for the accepted telemetry set.",
                    _clip(0.48 + pacing / 160 + summary.sample_count / 80),
                    summary.sample_count,
                    [
                        self._evidence("frame_time_instability_score", pacing, 42, snapshots),
                        self._evidence("one_percent_low_fps", summary.one_percent_low_fps or "missing", "stable 1% low", snapshots),
                    ],
                    summary.covered_workloads,
                    summary.covered_resolutions,
                    causes,
                    [
                        "Check driver version against known stable releases.",
                        "Pair with stronger CPU/cache subsystem for simulation-heavy titles.",
                    ],
                )
            )
        if summary.average_fps and summary.one_percent_low_fps:
            low_ratio = summary.one_percent_low_fps / summary.average_fps
            if low_ratio < 0.68:
                anomalies.append(
                    self._anomaly(
                        product_id,
                        "fps_drop",
                        _severity(1 - low_ratio, 0.46, 0.32),
                        "Unexpected FPS low collapse",
                        "Average FPS is materially higher than 1% lows, indicating visible stutter risk.",
                        _clip(0.44 + (0.68 - low_ratio) + summary.sample_count / 90),
                        summary.sample_count,
                        [
                            self._evidence("average_fps", summary.average_fps, "baseline", snapshots),
                            self._evidence("one_percent_low_ratio", round(low_ratio, 3), 0.68, snapshots),
                        ],
                        summary.covered_workloads,
                        summary.covered_resolutions,
                        ["CPU saturation", "cache pressure", "driver scheduling", "background memory pressure"],
                        ["Prefer hardware with stronger 1% low telemetry in the target workload."],
                    )
                )
        if summary.thermal_throttling_risk in {"medium", "high"}:
            risk_score = 72 if summary.thermal_throttling_risk == "high" else 48
            anomalies.append(
                self._anomaly(
                    product_id,
                    "thermal_throttling",
                    "critical" if summary.thermal_throttling_risk == "high" else "warning",
                    "Likely thermal throttling risk",
                    "Thermal telemetry indicates sustained boost instability or cooling headroom loss.",
                    _clip(0.46 + risk_score / 120 + summary.sample_count / 100),
                    summary.sample_count,
                    [
                        self._evidence("average_temp_c", summary.average_temp_c or "missing", 84, snapshots),
                        self._evidence("hotspot_temp_c", summary.hotspot_temp_c or "missing", 94, snapshots),
                    ],
                    summary.covered_workloads,
                    summary.covered_resolutions,
                    ["insufficient cooling", "case airflow bottleneck", "power transient heat load"],
                    [
                        "Increase cooler capacity or case airflow.",
                        "Preserve PSU headroom to reduce transient instability.",
                    ],
                )
            )
        if summary.bottleneck.vram_percent >= 22:
            anomalies.append(
                self._anomaly(
                    product_id,
                    "vram_pressure",
                    _severity(summary.bottleneck.vram_percent, 55, 22),
                    "VRAM pressure detected",
                    "VRAM-sensitive workloads show memory pressure at the tested resolution.",
                    _clip(0.42 + summary.bottleneck.vram_percent / 135 + summary.sample_count / 100),
                    summary.sample_count,
                    [self._evidence("vram_bottleneck_percent", summary.bottleneck.vram_percent, 22, snapshots)],
                    summary.covered_workloads,
                    summary.covered_resolutions,
                    ["high-resolution textures", "ray tracing memory pressure", "engine streaming pressure"],
                    ["Prefer larger VRAM capacity for 4K, ultrawide, AI, and heavy texture workloads."],
                )
            )
        if summary.bottleneck.cpu_percent >= 28:
            anomalies.append(
                self._anomaly(
                    product_id,
                    "cpu_saturation",
                    _severity(summary.bottleneck.cpu_percent, 58, 28),
                    "CPU saturation pattern detected",
                    "Telemetry suggests the GPU can wait on CPU frame delivery in the tested workload.",
                    _clip(0.42 + summary.bottleneck.cpu_percent / 150 + summary.sample_count / 110),
                    summary.sample_count,
                    [self._evidence("cpu_bottleneck_percent", summary.bottleneck.cpu_percent, 28, snapshots)],
                    summary.covered_workloads,
                    summary.covered_resolutions,
                    ["simulation workload", "cache-sensitive engine", "main-thread saturation"],
                    ["Use a CPU with stronger single-thread and cache behavior for this workload."],
                )
            )
        if summary.bottleneck.bandwidth_percent >= 20:
            anomalies.append(
                self._anomaly(
                    product_id,
                    "workload_bottleneck",
                    _severity(summary.bottleneck.bandwidth_percent, 52, 20),
                    "Bandwidth pressure detected",
                    "Telemetry indicates data-movement pressure from memory, bus, or workload asset streaming.",
                    _clip(0.42 + summary.bottleneck.bandwidth_percent / 145 + summary.sample_count / 100),
                    summary.sample_count,
                    [self._evidence("bandwidth_bottleneck_percent", summary.bottleneck.bandwidth_percent, 20, snapshots)],
                    summary.covered_workloads,
                    summary.covered_resolutions,
                    ["PCIe or memory bandwidth pressure", "engine asset streaming", "AI/CAD data movement"],
                    ["Prefer higher memory bandwidth, larger VRAM, or stronger platform I/O for this workload."],
                )
            )
        if summary.peak_power_w and summary.average_power_w and summary.peak_power_w > summary.average_power_w * 1.55:
            ratio = summary.peak_power_w / summary.average_power_w
            anomalies.append(
                self._anomaly(
                    product_id,
                    "power_spike",
                    _severity(ratio, 1.95, 1.55),
                    "Power spike behavior detected",
                    "Peak draw is materially above average draw, raising PSU transient stability risk.",
                    _clip(0.4 + (ratio - 1.2) / 1.8 + summary.sample_count / 120),
                    summary.sample_count,
                    [
                        self._evidence("average_power_w", summary.average_power_w, "average", snapshots),
                        self._evidence("peak_power_w", summary.peak_power_w, "1.55x average", snapshots),
                    ],
                    summary.covered_workloads,
                    summary.covered_resolutions,
                    ["transient load spikes", "PSU headroom limits", "thermal load bursts"],
                    ["Select a PSU with transient headroom and high-quality voltage regulation."],
                )
            )
        outlier = self._outlier_anomaly(product_id, snapshots)
        if outlier:
            anomalies.append(outlier)
        return anomalies

    def _driver_regressions(
        self,
        product_id: str,
        snapshots: list[TelemetrySnapshotView],
    ) -> list[DriverRegressionFinding]:
        grouped: dict[tuple[str, str], list[TelemetrySnapshotView]] = defaultdict(list)
        for snapshot in snapshots:
            if snapshot.driver_version:
                grouped[(snapshot.workload.name, snapshot.resolution)].append(snapshot)
        regressions: list[DriverRegressionFinding] = []
        for (workload, resolution), items in grouped.items():
            ordered = sorted(items, key=lambda snapshot: snapshot.timestamp)
            if len({item.driver_version.version for item in ordered if item.driver_version}) < 2:
                continue
            previous = ordered[-2]
            current = ordered[-1]
            if not previous.driver_version or not current.driver_version:
                continue
            previous_fps = previous.metrics.average_fps
            current_fps = current.metrics.average_fps
            fps_delta = None
            if previous_fps and current_fps:
                fps_delta = (current_fps - previous_fps) / previous_fps * 100
            instability_delta = current.frame_time_instability_score - previous.frame_time_instability_score
            thermal_delta = None
            if previous.metrics.hotspot_temp_c is not None and current.metrics.hotspot_temp_c is not None:
                thermal_delta = current.metrics.hotspot_temp_c - previous.metrics.hotspot_temp_c
            if (
                (fps_delta is not None and fps_delta <= -7)
                or instability_delta >= 12
                or (thermal_delta is not None and thermal_delta >= 8)
            ):
                severity = "critical" if (fps_delta is not None and fps_delta <= -14) or instability_delta >= 25 else "warning"
                explanation = (
                    f"Driver {current.driver_version.version} regressed against "
                    f"{previous.driver_version.version} for {workload} at {resolution}."
                )
                regressions.append(
                    DriverRegressionFinding(
                        id=_id("driver-regression", product_id, workload, resolution, previous.driver_version.version, current.driver_version.version),
                        driver_from=previous.driver_version.version,
                        driver_to=current.driver_version.version,
                        workload=workload,
                        resolution=resolution,
                        fps_delta_percent=round(fps_delta, 2) if fps_delta is not None else None,
                        instability_delta=round(instability_delta, 2),
                        thermal_delta_c=round(thermal_delta, 2) if thermal_delta is not None else None,
                        severity=severity,
                        confidence_score=_clip(0.56 + min(len(ordered), 10) * 0.035),
                        explanation=explanation,
                        evidence_sources=sorted({previous.source, current.source}),
                    )
                )
        return regressions[:8]

    def _patterns(
        self,
        product_id: str,
        snapshots: list[TelemetrySnapshotView],
        summary: TelemetrySummary,
        anomalies: list[TelemetryAnomaly],
        regressions: list[DriverRegressionFinding],
    ) -> list[TelemetryPatternFinding]:
        patterns: list[TelemetryPatternFinding] = []
        if len([item for item in anomalies if item.kind in {"frame_pacing", "fps_drop"}]) >= 2:
            patterns.append(
                self._pattern(
                    product_id,
                    "recurring_instability",
                    "warning",
                    "Recurring instability pattern",
                    "Multiple accepted signals point to repeatable stutter or FPS-low behavior.",
                    _clip(0.5 + summary.sample_count / 90),
                    summary.sample_count,
                    snapshots,
                    ["Use telemetry from the exact target game before recommending this part."],
                )
            )
        if regressions:
            patterns.append(
                self._pattern(
                    product_id,
                    "problematic_driver",
                    "warning",
                    "Driver-sensitive performance pattern",
                    "Recent driver-to-driver telemetry shows FPS, thermal, or pacing regression risk.",
                    _clip(0.56 + len(regressions) * 0.06),
                    summary.sample_count,
                    snapshots,
                    ["Prefer the stable driver branch shown in benchmark history."],
                )
            )
        bios_versions = Counter(
            snapshot.driver_version.bios_version
            for snapshot in snapshots
            if snapshot.driver_version and snapshot.driver_version.bios_version
        )
        if bios_versions and summary.thermal_throttling_risk in {"medium", "high"}:
            bios, count = bios_versions.most_common(1)[0]
            if count >= 2:
                patterns.append(
                    self._pattern(
                        product_id,
                        "problematic_bios",
                        "warning",
                        "BIOS-linked thermal pattern",
                        f"Thermal risk repeatedly appears with BIOS {bios}.",
                        _clip(0.48 + count / 20),
                        count,
                        snapshots,
                        ["Check board BIOS notes before selecting this platform."],
                    )
                )
        memory_pressure = sum(
            1
            for snapshot in snapshots
            if snapshot.metrics.system_memory_used_gb is not None and snapshot.metrics.system_memory_used_gb >= 28
        )
        if memory_pressure >= 2:
            patterns.append(
                self._pattern(
                    product_id,
                    "unstable_memory_configuration",
                    "warning",
                    "Memory pressure pattern",
                    "Telemetry repeatedly shows high system memory pressure during workload execution.",
                    _clip(0.48 + memory_pressure / 16),
                    memory_pressure,
                    snapshots,
                    ["Increase memory capacity or use validated stable memory profiles."],
                )
            )
        if summary.thermal_throttling_risk in {"medium", "high"}:
            patterns.append(
                self._pattern(
                    product_id,
                    "insufficient_cooling",
                    "critical" if summary.thermal_throttling_risk == "high" else "warning",
                    "Cooling headroom limitation",
                    "Sustained telemetry indicates cooling or airflow constraints under load.",
                    _clip(0.5 + (summary.bottleneck.thermal_percent / 140)),
                    summary.sample_count,
                    snapshots,
                    ["Use stronger cooling and case airflow for sustained workloads."],
                )
            )
        if summary.peak_power_w and summary.average_power_w and summary.peak_power_w > summary.average_power_w * 1.55:
            patterns.append(
                self._pattern(
                    product_id,
                    "psu_instability_risk",
                    "warning",
                    "PSU transient risk pattern",
                    "Power telemetry shows enough transient spread to affect PSU selection.",
                    _clip(0.48 + (summary.peak_power_w / max(summary.average_power_w, 1) - 1.3) / 1.4),
                    summary.sample_count,
                    snapshots,
                    ["Avoid tight PSU sizing and prefer high transient response quality."],
                )
            )
        return patterns[:8]

    def _predictions(
        self,
        product_id: str,
        summary: TelemetrySummary,
        anomalies: list[TelemetryAnomaly],
        patterns: list[TelemetryPatternFinding],
    ) -> list[PredictiveTelemetryInsight]:
        if summary.sample_count == 0:
            return []
        predictions: list[PredictiveTelemetryInsight] = []
        if summary.bottleneck.vram_percent >= 18 or any("4K" == item for item in summary.covered_resolutions):
            predictions.append(
                PredictiveTelemetryInsight(
                    id=_id("prediction", product_id, "vram", summary.updated_at.isoformat()),
                    horizon="next-generation high-resolution workloads",
                    predicted_limitation="vram",
                    risk_score=min(100, round(summary.bottleneck.vram_percent * 1.35 + 18, 1)),
                    confidence_score=_clip(0.45 + summary.sample_count / 90),
                    explanation="Texture, ray tracing, and AI workloads are likely to increase VRAM pressure.",
                    evidence_sources=summary.covered_workloads,
                    mitigation=["Prioritize higher VRAM capacity for 4K, ultrawide, and AI-heavy builds."],
                )
            )
        if summary.bottleneck.cpu_percent >= 20:
            predictions.append(
                PredictiveTelemetryInsight(
                    id=_id("prediction", product_id, "cpu", summary.updated_at.isoformat()),
                    horizon="simulation-heavy and cache-sensitive upcoming workloads",
                    predicted_limitation="cpu",
                    risk_score=min(100, round(summary.bottleneck.cpu_percent * 1.45 + 12, 1)),
                    confidence_score=_clip(0.44 + summary.sample_count / 95),
                    explanation="Observed 1% low behavior suggests future CPU/cache-sensitive workloads may bottleneck earlier.",
                    evidence_sources=summary.covered_workloads,
                    mitigation=["Select stronger single-thread/cache platforms when this workload matters."],
                )
            )
        if summary.bottleneck.bandwidth_percent >= 18:
            predictions.append(
                PredictiveTelemetryInsight(
                    id=_id("prediction", product_id, "bandwidth", summary.updated_at.isoformat()),
                    horizon="asset-heavy game engines, AI, and workstation datasets",
                    predicted_limitation="bandwidth",
                    risk_score=min(100, round(summary.bottleneck.bandwidth_percent * 1.35 + 16, 1)),
                    confidence_score=_clip(0.44 + summary.sample_count / 95),
                    explanation="Observed data-movement pressure can become a platform bandwidth limit in larger workloads.",
                    evidence_sources=summary.covered_workloads,
                    mitigation=["Prioritize PCIe, memory bandwidth, VRAM capacity, and storage throughput together."],
                )
            )
        if any(item.kind == "insufficient_cooling" for item in patterns):
            predictions.append(
                PredictiveTelemetryInsight(
                    id=_id("prediction", product_id, "thermal", summary.updated_at.isoformat()),
                    horizon="sustained workstation or long gaming sessions",
                    predicted_limitation="thermal",
                    risk_score=78 if summary.thermal_throttling_risk == "high" else 56,
                    confidence_score=_clip(0.5 + summary.sample_count / 100),
                    explanation="Thermal readings predict boost instability under sustained load unless cooling improves.",
                    evidence_sources=summary.covered_workloads,
                    mitigation=["Increase cooler capacity, airflow, and PSU headroom."],
                )
            )
        if any(item.kind == "driver_regression" for item in anomalies) or any(item.kind == "problematic_driver" for item in patterns):
            predictions.append(
                PredictiveTelemetryInsight(
                    id=_id("prediction", product_id, "driver", summary.updated_at.isoformat()),
                    horizon="future driver updates",
                    predicted_limitation="driver",
                    risk_score=54,
                    confidence_score=_clip(0.48 + summary.sample_count / 110),
                    explanation="Driver-sensitive telemetry means future updates can shift performance or frame pacing.",
                    evidence_sources=summary.latest_driver_versions,
                    mitigation=["Track stable driver branches and retest after major driver releases."],
                )
            )
        return predictions[:5]

    def _bottleneck_explanations(
        self,
        summary: TelemetrySummary,
        snapshots: list[TelemetrySnapshotView],
    ) -> list[TelemetryLimitReason]:
        if summary.sample_count == 0:
            return []
        workload = ", ".join(summary.covered_workloads[:2]) or "accepted workloads"
        values = {
            "cpu": (summary.bottleneck.cpu_percent, f"{workload} shows CPU/cache-sensitive frame delivery limits."),
            "gpu": (summary.bottleneck.gpu_percent, f"{workload} is constrained by GPU render throughput."),
            "vram": (summary.bottleneck.vram_percent, f"{workload} shows VRAM pressure at tested resolution(s)."),
            "thermal": (summary.bottleneck.thermal_percent, "Thermal telemetry indicates sustained boost headroom risk."),
            "driver": (summary.bottleneck.driver_percent, "Frame pacing changes suggest driver/version sensitivity."),
            "memory": (summary.bottleneck.memory_percent, "Memory pressure contributes to workload instability."),
            "bandwidth": (summary.bottleneck.bandwidth_percent, "Platform or GPU bandwidth pressure contributes to workload limits."),
            "storage": (summary.bottleneck.storage_percent, "I/O-sensitive telemetry contributes to workload limits."),
        }
        reasons = [
            TelemetryLimitReason(kind=kind, percent=round(percent, 1), reason=reason)
            for kind, (percent, reason) in sorted(values.items(), key=lambda item: item[1][0], reverse=True)
            if percent >= 14
        ]
        if not reasons and snapshots:
            reasons.append(
                TelemetryLimitReason(
                    kind=summary.primary_limiter,
                    percent=getattr(summary.bottleneck, f"{summary.primary_limiter}_percent", 0) if summary.primary_limiter != "none" else 0,
                    reason="No dominant bottleneck is currently visible in the accepted telemetry.",
                )
            )
        return reasons[:5]

    def _workload_reasoning(
        self,
        summary: TelemetrySummary,
        snapshots: list[TelemetrySnapshotView],
    ) -> list[str]:
        if summary.sample_count == 0:
            return []
        lines: list[str] = []
        strongest_cpu = max((snapshot.workload.cpu_sensitivity for snapshot in snapshots), default=0)
        strongest_cache = max((snapshot.workload.cache_sensitivity for snapshot in snapshots), default=0)
        strongest_vram = max((snapshot.workload.vram_sensitivity for snapshot in snapshots), default=0)
        ai_seen = any(snapshot.workload.category == "ai" for snapshot in snapshots)
        simulation_seen = any(snapshot.workload.category == "simulation" for snapshot in snapshots)
        ray_seen = any(
            "ray" in " ".join(snapshot.workload.api_dependencies + [snapshot.settings_preset or ""]).lower()
            or "rt" in (snapshot.settings_preset or "").lower()
            for snapshot in snapshots
        )
        if strongest_cache >= 0.72 and summary.bottleneck.cpu_percent >= 18:
            lines.append("Cache-sensitive workload behavior can amplify CPU frame delivery instability.")
        if strongest_cpu >= 0.76 and summary.frame_time_instability_score and summary.frame_time_instability_score >= 36:
            lines.append("CPU-heavy workload telemetry shows frame pacing risk when the main thread is saturated.")
        if strongest_vram >= 0.78 and summary.bottleneck.vram_percent >= 18:
            lines.append("VRAM-heavy workload telemetry indicates texture, asset streaming, or model-memory pressure.")
        if simulation_seen:
            lines.append("Simulation-heavy engines are treated as CPU/cache sensitive and can expose low-FPS collapse before averages fall.")
        if ray_seen or any("4K" == resolution for resolution in summary.covered_resolutions):
            lines.append("Ray tracing or high-resolution pressure increases GPU, VRAM, and bandwidth risk.")
        if ai_seen:
            lines.append("AI acceleration workloads are evaluated for tensor throughput, VRAM capacity, and data movement pressure.")
        if summary.bottleneck.bandwidth_percent >= 18:
            lines.append("Bandwidth pressure suggests PCIe, memory, storage, or GPU memory bandwidth may contribute to the observed limit.")
        return lines[:6]

    def _outlier_anomaly(
        self,
        product_id: str,
        snapshots: list[TelemetrySnapshotView],
    ) -> TelemetryAnomaly | None:
        fps_values = [snapshot.metrics.average_fps for snapshot in snapshots if snapshot.metrics.average_fps is not None]
        if len(fps_values) < 4:
            return None
        baseline = mean(fps_values)
        if baseline <= 0:
            return None
        lowest = min(fps_values)
        highest = max(fps_values)
        spread = (highest - lowest) / baseline
        if spread < 0.38:
            return None
        related = [snapshot for snapshot in snapshots if snapshot.metrics.average_fps in {lowest, highest}]
        return self._anomaly(
            product_id,
            "benchmark_outlier",
            _severity(spread, 0.7, 0.38),
            "Suspicious benchmark outlier detected",
            "Accepted samples show unusually wide FPS spread for the same product family.",
            _clip(0.42 + spread / 1.4 + len(fps_values) / 90),
            len(fps_values),
            [
                self._evidence("lowest_average_fps", lowest, "peer spread", related),
                self._evidence("highest_average_fps", highest, "peer spread", related),
            ],
            sorted({snapshot.workload.name for snapshot in related}),
            sorted({snapshot.resolution for snapshot in related}),
            ["test configuration mismatch", "driver difference", "thermal throttling", "source anomaly"],
            ["Require another source before treating this result as canonical."],
        )

    def _confidence(
        self,
        sample_size: int,
        snapshots: list[TelemetrySnapshotView],
        anomalies: list[TelemetryAnomaly],
        regressions: list[DriverRegressionFinding],
    ) -> float:
        if sample_size == 0:
            return 0.22
        trust = _avg(snapshot.trust_score for snapshot in snapshots) or 0.5
        freshness = _avg(snapshot.freshness_score for snapshot in snapshots) or 0.5
        source_diversity = min(1.0, len({snapshot.source for snapshot in snapshots}) / 4)
        driver_evidence = 0.08 if regressions else 0.0
        anomaly_penalty = min(0.18, len([item for item in anomalies if item.severity == "critical"]) * 0.06)
        return _clip(
            trust * 0.42
            + freshness * 0.18
            + min(1.0, sample_size / 10) * 0.22
            + source_diversity * 0.12
            + driver_evidence
            - anomaly_penalty
        )

    def _recommended_for(
        self,
        summary: TelemetrySummary,
        anomalies: list[TelemetryAnomaly],
    ) -> list[str]:
        if summary.sample_count == 0:
            return []
        critical = {item.kind for item in anomalies if item.severity == "critical"}
        recommended: list[str] = []
        if "frame_pacing" not in critical and summary.frame_time_instability_score is not None and summary.frame_time_instability_score < 34:
            recommended.append("latency-sensitive gaming")
        if summary.thermal_throttling_risk == "low":
            recommended.append("sustained workstation load")
        if summary.bottleneck.vram_percent < 22 and any(resolution in {"4K", "ultrawide"} for resolution in summary.covered_resolutions):
            recommended.append("high-resolution gaming")
        if summary.bottleneck.cpu_percent < 24:
            recommended.append("GPU-bound visual workloads")
        return recommended[:4]

    def _summary_lines(
        self,
        summary: TelemetrySummary,
        anomalies: list[TelemetryAnomaly],
        regressions: list[DriverRegressionFinding],
        patterns: list[TelemetryPatternFinding],
        predictions: list[PredictiveTelemetryInsight],
    ) -> list[str]:
        if summary.sample_count == 0:
            return ["No validated telemetry is available, so behavior reasoning is intentionally conservative."]
        lines = [
            f"Reasoning uses {summary.sample_count} telemetry sample(s) across {len(summary.covered_resolutions)} resolution bucket(s).",
        ]
        if summary.primary_limiter != "none":
            percent = getattr(summary.bottleneck, f"{summary.primary_limiter}_percent")
            lines.append(f"Primary observed limiter is {summary.primary_limiter.upper()} at {percent:.1f}%.")
        if anomalies:
            lines.append(f"{len(anomalies)} anomaly signal(s) detected; highest severity is {self._max_severity(anomalies)}.")
        if regressions:
            lines.append(f"{len(regressions)} driver regression signal(s) found across comparable snapshots.")
        if patterns:
            lines.append(f"Recurring pattern detected: {patterns[0].title}.")
        if predictions:
            lines.append(f"Predictive risk: {predictions[0].predicted_limitation.upper()} may limit {predictions[0].horizon}.")
        return lines[:6]

    def _warnings(
        self,
        anomalies: list[TelemetryAnomaly],
        regressions: list[DriverRegressionFinding],
        patterns: list[TelemetryPatternFinding],
        predictions: list[PredictiveTelemetryInsight],
    ) -> list[str]:
        warnings = [item.title for item in anomalies if item.severity in {"warning", "critical"}]
        warnings.extend(item.explanation for item in regressions if item.severity in {"warning", "critical"})
        warnings.extend(item.title for item in patterns if item.severity in {"warning", "critical"})
        warnings.extend(
            f"{item.predicted_limitation.upper()} risk under {item.horizon}"
            for item in predictions
            if item.risk_score >= 60
        )
        return warnings[:8]

    def _ai_explanation(
        self,
        product_id: str,
        summary: TelemetrySummary,
        anomalies: list[TelemetryAnomaly],
        patterns: list[TelemetryPatternFinding],
        bottlenecks: list[TelemetryLimitReason],
        workload_reasoning: list[str],
    ) -> str:
        if summary.sample_count == 0:
            return f"{product_id} has no validated telemetry yet, so the system cannot claim a real-world bottleneck."
        subject = product_id.split(":")[-1].replace("-", " ")
        opener = f"{subject} is limited because:"
        bullets: list[str] = []
        for anomaly in anomalies:
            bullets.append(anomaly.title)
            if len(bullets) >= 2:
                break
        for bottleneck in bottlenecks:
            bullets.append(bottleneck.reason)
            if len(bullets) >= 4:
                break
        for line in workload_reasoning:
            bullets.append(line)
            if len(bullets) >= 5:
                break
        for pattern in patterns:
            bullets.append(pattern.explanation)
            if len(bullets) >= 5:
                break
        if not bullets:
            bullets.append("No dominant anomaly is currently visible in the accepted telemetry.")
        return "\n".join([opener, *[f"- {line}" for line in bullets[:5]]])

    def _max_severity(self, anomalies: list[TelemetryAnomaly]) -> str:
        order = {"critical": 3, "warning": 2, "info": 1}
        return max((item.severity for item in anomalies), key=lambda severity: order[severity])

    def _evidence_sources(self, snapshots: list[TelemetrySnapshotView]) -> list[str]:
        values = sorted({snapshot.source for snapshot in snapshots if snapshot.source})
        return values[:12]

    def _evidence(
        self,
        metric: str,
        value: float | str,
        threshold: float | str | None,
        snapshots: list[TelemetrySnapshotView],
    ) -> TelemetryEvidencePoint:
        snapshot = snapshots[0] if snapshots else None
        return TelemetryEvidencePoint(
            metric=metric,
            value=round(value, 3) if isinstance(value, float) else value,
            threshold=threshold,
            source=snapshot.source if snapshot else "computed",
            snapshot_id=snapshot.id if snapshot else None,
            timestamp=snapshot.timestamp if snapshot else None,
        )

    def _anomaly(
        self,
        product_id: str,
        kind: str,
        severity: TelemetrySeverity,
        title: str,
        explanation: str,
        confidence_score: float,
        sample_size: int,
        evidence: list[TelemetryEvidencePoint],
        workloads: list[str],
        resolutions: list[str],
        causes: list[str],
        actions: list[str],
    ) -> TelemetryAnomaly:
        return TelemetryAnomaly(
            id=_id("anomaly", product_id, kind, title, sample_size, ",".join(resolutions)),
            kind=kind,  # type: ignore[arg-type]
            severity=severity,
            title=title,
            explanation=explanation,
            confidence_score=confidence_score,
            sample_size=sample_size,
            evidence=evidence,
            affected_workloads=workloads[:6],
            affected_resolutions=resolutions[:6],
            likely_causes=causes[:5],
            recommended_actions=actions[:5],
        )

    def _pattern(
        self,
        product_id: str,
        kind: str,
        severity: TelemetrySeverity,
        title: str,
        explanation: str,
        confidence_score: float,
        sample_size: int,
        snapshots: list[TelemetrySnapshotView],
        actions: list[str],
    ) -> TelemetryPatternFinding:
        return TelemetryPatternFinding(
            id=_id("pattern", product_id, kind, title, sample_size),
            kind=kind,  # type: ignore[arg-type]
            severity=severity,
            title=title,
            explanation=explanation,
            confidence_score=confidence_score,
            sample_size=sample_size,
            evidence_sources=self._evidence_sources(snapshots),
            recommended_actions=actions[:5],
        )
