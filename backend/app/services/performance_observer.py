from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from statistics import mean
from threading import Lock
from time import monotonic
from typing import Any


@dataclass
class TimedEvent:
    name: str
    latency_ms: float
    endpoint: str | None = None
    timestamp: float = field(default_factory=monotonic)


class PerformanceObserver:
    def __init__(self, *, max_events: int = 500) -> None:
        self._lock = Lock()
        self._queries: deque[TimedEvent] = deque(maxlen=max_events)
        self._endpoints: deque[TimedEvent] = deque(maxlen=max_events)
        self._cache_hits = 0
        self._cache_misses = 0

    def record_query(self, name: str, latency_ms: float) -> None:
        with self._lock:
            self._queries.append(TimedEvent(name=name, latency_ms=latency_ms))

    def record_endpoint(self, endpoint: str, latency_ms: float) -> None:
        with self._lock:
            self._endpoints.append(TimedEvent(name=endpoint, endpoint=endpoint, latency_ms=latency_ms))

    def record_cache(self, *, hit: bool) -> None:
        with self._lock:
            if hit:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

    def query_performance(self) -> dict[str, Any]:
        with self._lock:
            queries = list(self._queries)
        duplicate_counts = Counter(event.name for event in queries)
        average_latency = round(mean([event.latency_ms for event in queries]), 2) if queries else 0.0
        return {
            "slowest_queries": [
                {"name": event.name, "latency_ms": round(event.latency_ms, 2)}
                for event in sorted(queries, key=lambda item: item.latency_ms, reverse=True)[:10]
            ],
            "average_query_latency_ms": average_latency,
            "duplicate_query_hotspots": [
                {"name": name, "count": count}
                for name, count in duplicate_counts.most_common(10)
                if count > 1
            ],
            "graph_scan_warnings": (
                []
                if queries
                else ["No query telemetry has been recorded in this process yet."]
            ),
        }

    def performance_summary(self) -> dict[str, Any]:
        with self._lock:
            endpoints = list(self._endpoints)
            queries = list(self._queries)
            hits = self._cache_hits
            misses = self._cache_misses
        build_events = [event for event in endpoints if event.endpoint == "/build/generate-local"]
        cache_total = hits + misses
        return {
            "average_build_generation_latency_ms": (
                round(mean([event.latency_ms for event in build_events]), 2) if build_events else 0.0
            ),
            "slowest_categories": [],
            "average_graph_query_latency_ms": (
                round(mean([event.latency_ms for event in queries]), 2) if queries else 0.0
            ),
            "cache_hit_rates": {
                "overall": round(hits / cache_total, 3) if cache_total else 0.0,
                "hits": hits,
                "misses": misses,
            },
            "refresh_success_failure": {
                "success": 0,
                "failure": 0,
            },
            "frontend_payload_sizes": {},
            "top_expensive_endpoints": [
                {"endpoint": event.endpoint or event.name, "latency_ms": round(event.latency_ms, 2)}
                for event in sorted(endpoints, key=lambda item: item.latency_ms, reverse=True)[:10]
            ],
        }


performance_observer = PerformanceObserver()
