from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread
from time import sleep

from neo4j import Driver

from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.cognition import LearningJob, OutcomeValidationRequest
from app.services.cognition_service import HardwareCognitionService


class CognitionWorker:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver
        self.queue: Queue[LearningJob] = Queue()
        self.stop_event = Event()
        self.thread = Thread(target=self._run, name="hardware-cognition-worker", daemon=True)

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def enqueue(self, job: LearningJob) -> None:
        repository = Neo4jCognitionRepository(self.driver)
        repository.create_job(job)
        self.queue.put(job)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.queue.get(timeout=0.5)
            except Empty:
                continue
            repository = Neo4jCognitionRepository(self.driver)
            service = HardwareCognitionService(repository, Neo4jTelemetryRepository(self.driver))
            job.attempts += 1
            job.status = "running"
            repository.update_job(job)
            try:
                self._execute(service, job)
                job.status = "completed"
            except Exception as error:  # noqa: BLE001 - learning jobs must not crash the API process.
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

    def _execute(self, service: HardwareCognitionService, job: LearningJob) -> None:
        payload = job.payload
        if job.kind in {"generate_predictions", "refresh_cognition"}:
            for product_id in payload.get("product_ids") or []:
                service.report(product_id, refresh=True, persist=payload.get("persist", True))
            return
        if job.kind == "validate_outcome":
            service.validate_outcome(OutcomeValidationRequest(**payload))
