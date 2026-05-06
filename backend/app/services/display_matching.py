from __future__ import annotations

from app.models.api import PerformanceResponse
from app.models.domain import BuildPreferences


class DisplayMatchingEngine:
    def match(self, performance: PerformanceResponse, preferences: BuildPreferences, refresh_hz: int) -> dict[str, str | float]:
        utilization = performance.expected_fps / max(refresh_hz, 1)
        if utilization >= 0.92:
            status = "matched"
            guidance = "Configuration is well matched to the requested display target."
        elif utilization >= 0.65:
            status = "acceptable"
            guidance = "Display target is reachable in lighter workloads; tune quality settings for heavy scenes."
        else:
            status = "undermatched"
            guidance = "GPU or CPU upgrade is recommended for the requested resolution and refresh target."
        return {
            "status": status,
            "resolution": preferences.resolution,
            "refresh_hz": float(refresh_hz),
            "estimated_utilization": round(utilization, 3),
            "guidance": guidance,
        }

