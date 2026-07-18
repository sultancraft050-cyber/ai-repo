from __future__ import annotations

import os
import urllib.parse
from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker


def build_db_url() -> str | None:
    """Safely constructs the database URL supporting PostgreSQL TCP and Unix sockets."""
    url = os.getenv("CATALOG_DATABASE_URL")
    if url:
        return url

    user = os.getenv("CATALOG_DB_USER")
    dbname = os.getenv("CATALOG_DB_NAME")
    password = os.getenv("CATALOG_DB_PASSWORD")
    connection_name = os.getenv("CATALOG_CLOUD_SQL_CONNECTION_NAME")

    if user and dbname:
        pw_str = ""
        if password:
            pw_str = f":{urllib.parse.quote_plus(password)}"

        if connection_name:
            socket_dir = f"/cloudsql/{connection_name}"
            return f"postgresql+psycopg2://{user}{pw_str}@/{dbname}?host={socket_dir}"
        else:
            return f"postgresql+psycopg2://{user}{pw_str}@localhost/{dbname}"

    return None


def redact_url(url: str | None) -> str:
    """Redacts the password from a TCP or Unix socket database connection URL."""
    if not url:
        return "Not Configured"
    try:
        if "@" in url:
            prefix, suffix = url.rsplit("@", 1)
            if "://" in prefix:
                proto, creds = prefix.split("://", 1)
                if ":" in creds:
                    user, _ = creds.split(":", 1)
                    return f"{proto}://{user}:***@{suffix}"
                return f"{proto}://{creds}:***@{suffix}"
    except Exception:
        pass
    return url


class CatalogDatabase:
    """Lazy database factory; absent URLs never affect the existing app."""

    def __init__(self) -> None:
        self.url = build_db_url()
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
        url = build_db_url()
        if not url:
            raise RuntimeError("Relational catalog is unavailable: database configuration is missing.")

        self.url = url

        if self._engine is None or str(self._engine.url) != url:
            self._engine = None
            self._session_factory = None

        if self._session_factory is None:
            if url.startswith("postgresql"):
                self._engine = create_engine(
                    url,
                    pool_size=5,
                    max_overflow=10,
                    pool_timeout=30.0,
                    pool_recycle=1800,
                    pool_pre_ping=True
                )
            else:
                connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
                self._engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
            self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

        with self._session_factory() as session:
            yield session

    def check_health(self) -> str:
        """Reports safe catalog status: disabled, not configured, connected, unavailable."""
        if not self.enabled:
            return "disabled"
        url = build_db_url()
        if not url:
            return "not configured"
        try:
            with self.session() as session:
                session.execute(select(1))
            return "connected"
        except Exception:
            return "unavailable"


catalog_database = CatalogDatabase()
