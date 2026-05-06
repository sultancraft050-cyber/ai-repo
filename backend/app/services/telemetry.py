from __future__ import annotations

from app.models.api import CompatibilityResponse, PerformanceResponse


class SimulationTelemetry:
    def snapshot(
        self,
        compatibility: CompatibilityResponse,
        performance: PerformanceResponse | None,
    ) -> dict[str, float | int | str]:
        failed = sum(check.status == "fail" for check in compatibility.checks)
        warnings = sum(check.status in {"warning", "unknown"} for check in compatibility.checks)
        return {
            "valid": int(compatibility.valid),
            "state": compatibility.state,
            "failed_constraints": failed,
            "warning_constraints": warnings,
            "expected_fps": performance.expected_fps if performance else 0.0,
            "frame_time_variance_ms": performance.frame_time_variance_ms if performance else 0.0,
        }

