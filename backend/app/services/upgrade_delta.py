from __future__ import annotations

from app.models.domain import ComponentNode


class UpgradeDeltaEngine:
    def compare(self, current: ComponentNode, candidate: ComponentNode) -> dict[str, float | str]:
        current_perf = self._performance_proxy(current)
        candidate_perf = self._performance_proxy(candidate)
        current_price = float(current.price_usd or 0.0)
        candidate_price = float(candidate.price_usd or 0.0)
        delta_perf = candidate_perf - current_perf
        delta_cost = candidate_price - current_price
        return {
            "current_component_id": current.id,
            "candidate_component_id": candidate.id,
            "performance_delta": round(delta_perf, 4),
            "cost_delta_usd": round(delta_cost, 2),
            "performance_per_dollar_delta": round(delta_perf / max(delta_cost, 1.0), 4),
        }

    def _performance_proxy(self, component: ComponentNode) -> float:
        numeric_values = []
        for group_name in ("specs", "bandwidth"):
            for value in getattr(component, group_name).values():
                if isinstance(value, (int, float)):
                    numeric_values.append(float(value))
        return sum(numeric_values) / max(len(numeric_values), 1)

