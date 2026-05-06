from __future__ import annotations

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.core.config import Settings


class Neo4jSessionManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.driver: Driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=2.0,
        )
        self.unavailable_reason: str | None = None

    def verify(self) -> bool:
        try:
            self.driver.verify_connectivity()
            self.unavailable_reason = None
            return True
        except (Neo4jError, ServiceUnavailable, OSError) as exc:
            self.unavailable_reason = str(exc)
            return False

    def close(self) -> None:
        self.driver.close()
