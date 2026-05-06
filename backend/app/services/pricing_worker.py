from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread
from time import sleep
from typing import Any

from neo4j import Driver

from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.pricing import PricingJob
from app.models.intelligence import EnrichmentRequest
from app.services.hardware_enrichment import HardwareEnrichmentService
from app.services.pricing_ingestion import IngestionResult, PricingIngestionService, ProductDiscoveryService


class PricingWorker:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver
        self.queue: Queue[PricingJob] = Queue()
        self.stop_event = Event()
        self.thread = Thread(target=self._run, name="pricing-ingestion-worker", daemon=True)

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def enqueue(self, job: PricingJob) -> None:
        repository = Neo4jPricingRepository(self.driver)
        repository.create_job(job)
        self.queue.put(job)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.queue.get(timeout=0.5)
            except Empty:
                continue
            repository = Neo4jPricingRepository(self.driver)
            service = PricingIngestionService(repository)
            job.attempts += 1
            job.status = "running"
            repository.update_job(job)
            try:
                result = self._execute(service, job)
                job.status = "completed"
                result = result or IngestionResult()
                job.accepted_snapshots = result.accepted_snapshots
                job.rejected_snapshots = result.rejected_snapshots
            except Exception as error:  # noqa: BLE001 - jobs are isolated from the API process.
                job.error = str(error)
                if job.attempts < job.max_attempts:
                    job.status = "retrying"
                    repository.update_job(job)
                    sleep(min(2**job.attempts, 30))
                    self.queue.put(job)
                    self.queue.task_done()
                    continue
                job.status = "failed"
            finally:
                repository.update_job(job)
                self.queue.task_done()

    def _execute(self, service: PricingIngestionService, job: PricingJob):
        payload: dict[str, Any] = job.payload
        if job.kind == "refresh":
            product_ids = payload.get("product_ids") or []
            if product_ids:
                aggregate = None
                for product_id in product_ids:
                    result = service.refresh_product(
                        product_id=product_id,
                        region=payload.get("region", "US"),
                        providers=payload.get("providers") or [],
                    )
                    if aggregate is None:
                        aggregate = result
                    else:
                        aggregate.accepted_snapshots += result.accepted_snapshots
                        aggregate.rejected_snapshots += result.rejected_snapshots
                        aggregate.stale_products.extend(result.stale_products or [])
                        aggregate.source_errors.extend(result.source_errors or [])
                return aggregate or IngestionResult()
            return service.sync_query(
                query=payload.get("query") or "",
                category=payload.get("category") or "GPU",
                region=payload.get("region", "US"),
                providers=payload.get("providers") or [],
                limit=payload.get("limit", 8),
            )
        if job.kind == "discover":
            result, _ = ProductDiscoveryService(service).discover(
                categories=payload.get("categories") or [],
                query=payload.get("query"),
                region=payload.get("region", "US"),
                providers=payload.get("providers") or [],
                limit_per_query=payload.get("limit_per_query", 8),
                max_queries=payload.get("max_queries", 24),
            )
            return result
        if job.kind == "enrich":
            response = HardwareEnrichmentService(Neo4jPricingRepository(self.driver)).enrich(
                EnrichmentRequest(**payload)
            )
            return IngestionResult(
                accepted_snapshots=response.enriched_count,
                rejected_snapshots=response.skipped_count,
            )
        aggregate = None
        for query in payload.get("queries") or []:
            result = service.sync_query(
                query=query,
                category=payload.get("category") or "GPU",
                region=payload.get("region", "US"),
                providers=payload.get("providers") or [],
                limit=payload.get("limit_per_query", 8),
            )
            if aggregate is None:
                aggregate = result
            else:
                aggregate.accepted_snapshots += result.accepted_snapshots
                aggregate.rejected_snapshots += result.rejected_snapshots
                aggregate.stale_products.extend(result.stale_products or [])
                aggregate.source_errors.extend(result.source_errors or [])
        return aggregate or IngestionResult()
