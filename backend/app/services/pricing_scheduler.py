from __future__ import annotations

from threading import Event, Thread

from neo4j import Driver

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import PricingJob
from app.services.hardware_taxonomy import GLOBAL_HARDWARE_CATEGORIES
from app.services.pricing_worker import PricingWorker


class PricingScheduler:
    def __init__(
        self,
        driver: Driver,
        worker: PricingWorker,
        *,
        top_interval_seconds: int = 3600,
        standard_interval_seconds: int = 21600,
    ) -> None:
        self.driver = driver
        self.worker = worker
        self.top_interval_seconds = max(60, top_interval_seconds)
        self.standard_interval_seconds = max(300, standard_interval_seconds)
        self.stop_event = Event()
        self.thread = Thread(target=self._run, name="pricing-refresh-scheduler", daemon=True)

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def _run(self) -> None:
        top_elapsed = 0
        standard_elapsed = 0
        while not self.stop_event.wait(60):
            top_elapsed += 60
            standard_elapsed += 60
            if top_elapsed >= self.top_interval_seconds:
                self._queue_due_refresh(top_only=True)
                top_elapsed = 0
            if standard_elapsed >= self.standard_interval_seconds:
                self._queue_due_refresh(top_only=False)
                self._queue_discovery_sweep()
                standard_elapsed = 0

    def _queue_due_refresh(self, *, top_only: bool) -> None:
        repository = Neo4jPricingRepository(self.driver)
        product_ids = repository.products_due_for_refresh(limit=40 if top_only else 120, top_only=top_only)
        if not product_ids:
            return
        self.worker.enqueue(
            PricingJob(
                kind="refresh",
                payload={
                    "product_ids": product_ids,
                    "region": "US",
                    "providers": [],
                    "scheduler": "top_products" if top_only else "standard_products",
                },
            )
        )

    def _queue_discovery_sweep(self) -> None:
        self.worker.enqueue(
            PricingJob(
                kind="discover",
                payload={
                    "categories": GLOBAL_HARDWARE_CATEGORIES,
                    "region": "US",
                    "providers": [],
                    "limit_per_query": 6,
                    "max_queries": 32,
                    "scheduler": "market_discovery_sweep",
                },
            )
        )
        self.worker.enqueue(
            PricingJob(
                kind="enrich",
                payload={
                    "product_ids": [],
                    "category": None,
                    "limit": 120,
                    "persist": True,
                    "scheduler": "hardware_intelligence_enrichment",
                },
            )
        )
