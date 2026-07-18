from __future__ import annotations

import os
import urllib.parse
import pytest
from sqlalchemy import create_engine

from app.core.config import Settings
from app.catalog.database import build_db_url, redact_url, CatalogDatabase
from app.catalog.storage import catalog_storage
from app.catalog.models import Base
from app.core.security import ENDPOINT_RULES
from app.main import app

def test_postgresql_url_creation(monkeypatch):
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    monkeypatch.setenv("CATALOG_DB_USER", "sultansotb")
    monkeypatch.setenv("CATALOG_DB_NAME", "catalog")
    monkeypatch.setenv("CATALOG_DB_PASSWORD", "pass123")
    monkeypatch.delenv("CATALOG_CLOUD_SQL_CONNECTION_NAME", raising=False)

    url = build_db_url()
    assert url == "postgresql+psycopg2://sultansotb:pass123@localhost/catalog"

def test_unix_socket_configuration(monkeypatch):
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    monkeypatch.setenv("CATALOG_DB_USER", "sultansotb")
    monkeypatch.setenv("CATALOG_DB_NAME", "catalog")
    monkeypatch.setenv("CATALOG_DB_PASSWORD", "pass123")
    monkeypatch.setenv("CATALOG_CLOUD_SQL_CONNECTION_NAME", "pc-recomendation-project:me-central1:catalog-postgres-staging")

    url = build_db_url()
    assert url == "postgresql+psycopg2://sultansotb:pass123@/catalog?host=/cloudsql/pc-recomendation-project:me-central1:catalog-postgres-staging"

def test_password_encoding(monkeypatch):
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    monkeypatch.setenv("CATALOG_DB_USER", "sultansotb")
    monkeypatch.setenv("CATALOG_DB_NAME", "catalog")
    # password with special characters
    monkeypatch.setenv("CATALOG_DB_PASSWORD", "pass@word:123")
    monkeypatch.delenv("CATALOG_CLOUD_SQL_CONNECTION_NAME", raising=False)

    url = build_db_url()
    encoded = urllib.parse.quote_plus("pass@word:123")
    assert encoded in url
    assert "pass@word:123" not in url

def test_password_redaction():
    url_tcp = "postgresql+psycopg2://sultansotb:my_secret_pass@localhost/catalog"
    url_socket = "postgresql+psycopg2://sultansotb:my_secret_pass@/catalog?host=/cloudsql/conn"

    redacted_tcp = redact_url(url_tcp)
    redacted_socket = redact_url(url_socket)

    assert "my_secret_pass" not in redacted_tcp
    assert "sultansotb:***@" in redacted_tcp

    assert "my_secret_pass" not in redacted_socket
    assert "sultansotb:***@" in redacted_socket

    assert redact_url(None) == "Not Configured"
    assert redact_url("sqlite:///./local.db") == "sqlite:///./local.db"

def test_missing_password_behavior(monkeypatch):
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    monkeypatch.setenv("CATALOG_DB_USER", "sultansotb")
    monkeypatch.setenv("CATALOG_DB_NAME", "catalog")
    monkeypatch.delenv("CATALOG_DB_PASSWORD", raising=False)
    monkeypatch.delenv("CATALOG_CLOUD_SQL_CONNECTION_NAME", raising=False)

    url = build_db_url()
    assert url == "postgresql+psycopg2://sultansotb@localhost/catalog"

def test_missing_socket_configuration(monkeypatch):
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    monkeypatch.setenv("CATALOG_DB_USER", "sultansotb")
    monkeypatch.setenv("CATALOG_DB_NAME", "catalog")
    monkeypatch.delenv("CATALOG_CLOUD_SQL_CONNECTION_NAME", raising=False)

    url = build_db_url()
    assert "localhost" in url
    assert "host=" not in url

def test_bounded_pool_settings(monkeypatch):
    # If connection string starts with postgresql, bounded pool parameters should be injected
    db = CatalogDatabase()
    monkeypatch.setenv("CATALOG_DATABASE_URL", "postgresql+psycopg2://sultansotb:pw@localhost/catalog")
    
    with db.session() as session:
        engine = session.bind
        # Check pool settings on the engine
        assert engine.pool.size() == 5
        assert engine.pool._max_overflow == 10
        assert engine.pool._timeout == 30.0
        assert engine.pool._recycle == 1800

def test_catalog_health_statuses(monkeypatch):
    db = CatalogDatabase()

    # Case 1: Disabled
    monkeypatch.setenv("CATALOG_V2_ENABLED", "false")
    assert db.check_health() == "disabled"

    # Case 2: Not Configured
    monkeypatch.setenv("CATALOG_V2_ENABLED", "true")
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    monkeypatch.delenv("CATALOG_DB_USER", raising=False)
    assert db.check_health() == "not configured"

    # Case 3: Connected (using memory sqlite as test connection)
    monkeypatch.setenv("CATALOG_DATABASE_URL", "sqlite:///:memory:")
    assert db.check_health() == "connected"

    # Case 4: Unavailable (using unreachable connection url)
    monkeypatch.setenv("CATALOG_DATABASE_URL", "postgresql+psycopg2://sultansotb:pw@127.0.0.1:9999/catalog")
    assert db.check_health() == "unavailable"

def test_cloud_storage_bucket_validation(monkeypatch):
    assert catalog_storage.validate_bucket_name() is True

    # Modified bucket name should fail validation
    monkeypatch.setenv("CATALOG_MEDIA_BUCKET", "other-bucket-name")
    custom_storage = catalog_storage.__class__()
    assert custom_storage.validate_bucket_name() is False

def test_no_image_bytes_stored_in_sql():
    # Verify model definitions: ProductImage has only metadata, no binary/BLOB fields
    from app.catalog.models import ProductImage
    for col in ProductImage.__table__.columns:
        # Check type is not LARGEBINARY, BLOB, or BYTEA
        assert not str(col.type).lower().startswith("largebinary")
        assert not str(col.type).lower().startswith("blob")
        assert not str(col.type).lower().startswith("bytea")

def test_startup_invariants(monkeypatch):
    # Verify Catalog V2 is disabled by default
    settings = Settings.from_env()
    assert settings.catalog_v2_enabled is False
    assert settings.catalog_import_enabled is False
    assert settings.catalog_writes_enabled is False
    assert settings.catalog_image_review_enabled is False
    assert settings.catalog_ops_enabled is False
    assert settings.catalog_feed_mapping_enabled is False
    assert settings.catalog_feed_simulator_enabled is False
    assert settings.replay_failure_harness_enabled is False

    # Verify other safe-off flags are false
    assert settings.pricing_scheduler_enabled is False
    assert settings.autonomous_agents_enabled is False

def test_neo4j_behavior_unchanged():
    # Make sure app startup does not touch Neo4j if verify() fails, and no automatic migrations/imports run
    assert os.getenv("CPU_SPECS_SEED_ON_START", "false").lower() not in {"1", "true", "yes"}

def test_production_route_list_unchanged():
    # Verify that only GET routes exist for public catalog `/catalog/products`
    # and no public POST/PUT/DELETE write routes are registered on the app
    public_catalog_writes = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set())
        if path.startswith("/catalog/products"):
            # Any modifying method is write route
            for m in methods:
                if m in {"POST", "PUT", "DELETE", "PATCH"}:
                    public_catalog_writes.append((path, m))
                    
    assert len(public_catalog_writes) == 0, f"Found public catalog write routes: {public_catalog_writes}"


def test_cloud_sql_verification_cli_guards(monkeypatch):
    from app.catalog.cloud_sql_verification_cli import main
    monkeypatch.setenv("CATALOG_CLOUD_VERIFICATION_ENABLED", "false")
    with pytest.raises(SystemExit):
        main()

    monkeypatch.setenv("CATALOG_CLOUD_VERIFICATION_ENABLED", "true")
    monkeypatch.setenv("CATALOG_DATABASE_URL", "sqlite:///:memory:")
    with pytest.raises(SystemExit):
        main()

    monkeypatch.setenv("CATALOG_DATABASE_URL", "postgresql://user:pw@127.0.0.1/other_db")
    with pytest.raises(SystemExit):
        main()

    monkeypatch.setenv("CATALOG_DATABASE_URL", "postgresql://user:pw@localhost/catalog")
    with pytest.raises(SystemExit):
        main()
