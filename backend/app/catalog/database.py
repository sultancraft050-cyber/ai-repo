from __future__ import annotations

import os
from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class CatalogDatabase:
    """Lazy database factory; absent URLs never affect the existing app."""

    def __init__(self) -> None:
        self.url = os.getenv("CATALOG_DATABASE_URL")
        self._engine = None
        self._session_factory = None

    @property
    def enabled(self) -> bool:
        return os.getenv("CATALOG_V2_ENABLED", "false").lower() in {"1", "true", "yes"}

    @property
    def writes_enabled(self) -> bool:
        return os.getenv("CATALOG_WRITES_ENABLED", "false").lower() in {"1", "true", "yes"}

    @contextmanager
    def session(self) -> Iterator[Session]:
        if not self.url:
            raise RuntimeError("Relational catalog is unavailable: CATALOG_DATABASE_URL is not configured.")
        if self._session_factory is None:
            connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
            self._engine = create_engine(self.url, pool_pre_ping=True, connect_args=connect_args)
            self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
        with self._session_factory() as session:
            yield session


catalog_database = CatalogDatabase()
