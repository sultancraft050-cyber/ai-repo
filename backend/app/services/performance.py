from __future__ import annotations

import numpy as np

from app.models.api import BottleneckBreakdown, PerformanceResponse
from app.models.domain import BuildPreferences, ComponentNode


RESOLUTION_PIXELS = {
    "1080p": 1920 * 1080,
    "1440p": 2560 * 1440,
    "4K": 3840 * 2160,
}

PURPOSE_WEIGHTS = {
    "gaming": np.array([0.42, 0.13, 0.45], dtype=float),
    "simulation": np.array([0.35, 0.45, 0.20], dtype=float),
    "workstation": np.array([0.28, 0.32, 0.40], dtype=float),
}

BASELINE = np.array(
    [
        [3000.0, 55000.0, 95.0],
        [42000.0, 55.0, 760.0],
    ],
    dtype=float,
)


class PerformanceEngine:
    def calculate(
        self,
        *,
        cpu: ComponentNode,
        gpu: ComponentNode,
        ram: ComponentNode | None,
        preferences: BuildPreferences,
        display_refresh_hz: int,
    ) -> PerformanceResponse:
        feature_matrix = self._feature_matrix(cpu, gpu, ram)
        normalized = np.divide(feature_matrix, BASELINE, out=np.zeros_like(feature_matrix), where=BASELINE != 0)

        workload = PURPOSE_WEIGHTS[preferences.purpose]
        cpu_capacity = float(np.dot(normalized[0], workload))
        gpu_capacity = float(np.dot(normalized[1], workload))

        resolution_factor = RESOLUTION_PIXELS[preferences.resolution] / RESOLUTION_PIXELS["1080p"]
        balanced_capacity = min(cpu_capacity, gpu_capacity)
        expected_fps = float(np.clip((62.0 + balanced_capacity * 138.0) / resolution_factor, 18.0, 420.0))

        display_limit_percent = max(0.0, (expected_fps - display_refresh_hz) / max(expected_fps, 1.0) * 100.0)
        expected_fps = min(expected_fps, float(display_refresh_hz))

        imbalance = abs(cpu_capacity - gpu_capacity) / max(cpu_capacity, gpu_capacity, 0.001)
        memory_capacity = float(normalized[0, 2])
        memory_penalty = max(0.0, (1.0 - memory_capacity) * 18.0)
        frame_time_ms = 1000.0 / max(expected_fps, 1.0)
        variance_ms = float(np.clip(frame_time_ms * (0.06 + imbalance * 0.22) + memory_penalty * 0.12, 0.2, 28.0))
        one_percent_low = max(1.0, expected_fps * (1.0 - min(0.45, variance_ms / max(frame_time_ms, 1.0) * 0.55)))

        cpu_bottleneck = max(0.0, (gpu_capacity - cpu_capacity) / max(gpu_capacity, 0.001) * 100.0)
        gpu_bottleneck = max(0.0, (cpu_capacity - gpu_capacity) / max(cpu_capacity, 0.001) * 100.0)
        confidence = self._confidence(cpu, gpu, ram)

        reasoning = [
            f"{preferences.purpose} workload weights CPU single/multi throughput and GPU throughput with a deterministic NumPy matrix.",
            f"{preferences.resolution} applies a {resolution_factor:.2f}x pixel workload multiplier.",
            "Bottleneck percentages compare normalized CPU and GPU capacity after memory bandwidth normalization.",
        ]
        if display_limit_percent > 0:
            reasoning.append("Display refresh rate caps the rendered FPS estimate.")

        return PerformanceResponse(
            expected_fps=round(expected_fps, 1),
            one_percent_low_fps=round(one_percent_low, 1),
            frame_time_ms=round(frame_time_ms, 2),
            frame_time_variance_ms=round(variance_ms, 2),
            bottleneck=BottleneckBreakdown(
                cpu_percent=round(cpu_bottleneck, 1),
                gpu_percent=round(gpu_bottleneck, 1),
                memory_percent=round(memory_penalty, 1),
                display_percent=round(display_limit_percent, 1),
            ),
            confidence=confidence,
            model_inputs={
                "cpu_capacity": round(cpu_capacity, 4),
                "gpu_capacity": round(gpu_capacity, 4),
                "memory_capacity": round(memory_capacity, 4),
                "resolution_factor": round(resolution_factor, 4),
            },
            reasoning=reasoning,
        )

    def _feature_matrix(
        self,
        cpu: ComponentNode,
        gpu: ComponentNode,
        ram: ComponentNode | None,
    ) -> np.ndarray:
        memory_bandwidth = (
            ram.number("bandwidth", "memory_gbps") if ram else None
        ) or cpu.number("bandwidth", "memory_gbps", 55.0)
        return np.array(
            [
                [
                    cpu.number("specs", "single_thread_score", 0.0) or 0.0,
                    cpu.number("specs", "multi_thread_score", 0.0) or 0.0,
                    memory_bandwidth or 0.0,
                ],
                [
                    gpu.number("specs", "raster_score", 0.0) or 0.0,
                    gpu.number("specs", "vram_gb", 0.0) or 0.0,
                    gpu.number("specs", "compute_score", 0.0) or 0.0,
                ],
            ],
            dtype=float,
        )

    def _confidence(
        self,
        cpu: ComponentNode,
        gpu: ComponentNode,
        ram: ComponentNode | None,
    ) -> str:
        required = [
            cpu.number("specs", "single_thread_score"),
            cpu.number("specs", "multi_thread_score"),
            gpu.number("specs", "raster_score"),
            gpu.number("specs", "compute_score"),
        ]
        if ram:
            required.append(ram.number("bandwidth", "memory_gbps"))
        known = sum(value is not None and value > 0 for value in required)
        if known == len(required):
            return "high"
        if known >= max(2, len(required) - 2):
            return "medium"
        return "low"

