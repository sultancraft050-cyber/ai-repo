from __future__ import annotations

from threading import Event, Thread

from neo4j import Driver

from app.graph.alignment_repository import Neo4jAlignmentRepository
from app.graph.autonomy_repository import Neo4jAutonomyRepository
from app.graph.cognition_repository import Neo4jCognitionRepository
from app.graph.evolution_repository import Neo4jEvolutionRepository
from app.graph.governance_repository import Neo4jGovernanceRepository
from app.graph.telemetry_repository import Neo4jTelemetryRepository
from app.models.autonomy import AutonomyRunRequest
from app.services.autonomy_service import AutonomousCognitionService


class AutonomousAgentWorker:
    def __init__(self, driver: Driver, *, interval_seconds: int = 900, max_products: int = 6) -> None:
        self.driver = driver
        self.interval_seconds = interval_seconds
        self.max_products = max_products
        self.stop_event = Event()
        self.thread = Thread(target=self._run, name="autonomous-cognition-agent-worker", daemon=True)

    def start(self) -> None:
        if not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            try:
                self._cycle()
            except Exception:
                continue

    def _cycle(self) -> None:
        repository = Neo4jAutonomyRepository(self.driver)
        service = AutonomousCognitionService(
            repository,
            Neo4jAlignmentRepository(self.driver),
            Neo4jEvolutionRepository(self.driver),
            Neo4jGovernanceRepository(self.driver),
            Neo4jCognitionRepository(self.driver),
            Neo4jTelemetryRepository(self.driver),
        )
        product_ids = repository.candidate_product_ids(self.max_products)
        if not product_ids:
            return
        service.run(AutonomyRunRequest(product_ids=product_ids, persist=True, refresh=True))
