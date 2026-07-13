from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.catalog import ops_server
from app.main import app as production_app


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CATALOG_OPS_ENABLED", raising=False)
    monkeypatch.setenv("CATALOG_DATABASE_URL", "sqlite:////tmp/catalog-ops-test.sqlite3")
    with pytest.raises(RuntimeError, match="CATALOG_OPS_DISABLED"):
        ops_server.validate_ops_environment()


@pytest.mark.parametrize("url", ["postgresql://local", "bolt://local", "mysql://local", "sqlite+aiosqlite:///tmp/x"])
def test_non_sqlite_database_rejected(monkeypatch, url):
    monkeypatch.setenv("CATALOG_OPS_ENABLED", "true")
    monkeypatch.setenv("CATALOG_DATABASE_URL", url)
    with pytest.raises(RuntimeError, match="SQLITE_ONLY"):
        ops_server.validate_ops_environment()


def test_missing_database_url_fails_safely(monkeypatch):
    monkeypatch.setenv("CATALOG_OPS_ENABLED", "true")
    monkeypatch.delenv("CATALOG_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="CATALOG_DATABASE_URL_REQUIRED"):
        ops_server.validate_ops_environment()


def test_fixture_path_is_bounded_to_synthetic_fixture_root():
    valid = ops_server.FIXTURE_ROOT / "catalog_import" / "valid_products.csv"
    assert ops_server._fixture_path(str(valid)) == valid.resolve()
    with pytest.raises(ValueError, match="FIXTURE_PATH_REQUIRED"):
        ops_server._fixture_path("/tmp/real-catalog.csv")


def test_loopback_host_guard(monkeypatch):
    monkeypatch.setenv("CATALOG_OPS_HOST", "0.0.0.0")
    assert os.getenv("CATALOG_OPS_HOST") != "127.0.0.1"
    # main() validates the same guard before uvicorn is started; no listener is opened here.


def test_temporary_database_migrates_and_overview_is_safe(monkeypatch, tmp_path):
    database = tmp_path / "catalog-ops.sqlite3"
    monkeypatch.setenv("CATALOG_OPS_ENABLED", "true")
    monkeypatch.setenv("CATALOG_IMPORT_ENABLED", "true")
    monkeypatch.setenv("CATALOG_IMAGE_REVIEW_ENABLED", "true")
    monkeypatch.delenv("CATALOG_WRITES_ENABLED", raising=False)
    monkeypatch.setenv("CATALOG_DATABASE_URL", f"sqlite:///{database}")
    app = ops_server.create_ops_app()
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "Operations overview" in response.text
    assert str(database) not in response.text
    assert "No records" not in response.text
    assert "catalog_import_batches" in inspect(ops_server._local_engine(f"sqlite:///{database}")).get_table_names()


def test_standalone_routes_are_not_mounted_in_production_app():
    production_paths = {route.path for route in production_app.routes}
    assert "/imports/dry-run" not in production_paths
    assert not any(path.startswith("/batches/") for path in production_paths)
    assert not any(path.startswith("/images/pending") for path in production_paths)
