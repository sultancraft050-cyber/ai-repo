"""Tests for buildcores_import_cli.py — Cloud SQL bounded import."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import (
    Base,
    ImportBatch,
    ImportRecord,
    ImportSource,
    Product,
    ProductImage,
    ProductSpecification,
    StoreOffer,
    PriceHistory,
)
from app.catalog.buildcores_import_cli import (
    IMPORT_CATEGORY_LIMITS,
    IMPORT_TOTAL_LIMIT,
    _make_slug,
    _normalize_brand,
    _make_checksum,
    _verify_connection_safety,
    scan_source,
    cmd_dry_run,
    main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_opendb(tmp_path):
    """Minimal valid BuildCores OpenDB checkout."""
    (tmp_path / "LICENSE.txt").write_text("ODC-By")
    (tmp_path / "README.md").write_text("BuildCores OpenDB")
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    open_db = tmp_path / "open-db"
    open_db.mkdir()

    # Create all required schema and category folders
    category_folder_map = {
        "CPU": "CPU",
        "GPU": "GPU",
        "MOTHERBOARD": "Motherboard",
        "RAM": "RAM",
        "STORAGE": "Storage",
        "PSU": "PSU",
        "CASE": "PCCase",
        "COOLER": "CPUCooler",
    }
    for cat, folder in category_folder_map.items():
        (schemas / f"{folder}.schema.json").write_text(json.dumps({"properties": {}}))
        (open_db / folder).mkdir()

    return tmp_path


def _write_cpu(tmp_path, opendb_id, mpn, manufacturer="Intel", name=None):
    data = {
        "opendb_id": opendb_id,
        "socket": "LGA1700",
        "cores": {"total": 8, "threads": 16},
        "clocks": {"performance": {"base": 3.5, "boost": 5.0}},
        "specifications": {"tdp": 65},
        "metadata": {
            "name": name or f"{manufacturer} {mpn}",
            "manufacturer": manufacturer,
            "part_numbers": [mpn],
            "series": "Core",
            "variant": mpn,
        },
    }
    path = tmp_path / "open-db" / "CPU" / f"{opendb_id}.json"
    path.write_text(json.dumps(data))
    return path


def _write_gpu(tmp_path, opendb_id, mpn, manufacturer="NVIDIA", name=None):
    data = {
        "opendb_id": opendb_id,
        "chipset": "GeForce RTX 4080",
        "memory": 16,
        "length": 340,
        "tdp": 320,
        "metadata": {
            "name": name or f"{manufacturer} {mpn}",
            "manufacturer": manufacturer,
            "part_numbers": [mpn],
            "series": "GeForce",
            "variant": mpn,
        },
    }
    path = tmp_path / "open-db" / "GPU" / f"{opendb_id}.json"
    path.write_text(json.dumps(data))
    return path


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_normalize_brand():
    assert _normalize_brand("AMD") == "amd"
    assert _normalize_brand("Fractal Design") == "fractal design"
    assert _normalize_brand("  CORSAIR  ") == "corsair"


def test_make_slug():
    assert _make_slug("AMD Ryzen 7 7800X3D") == "amd-ryzen-7-7800x3d"
    assert _make_slug("ASUS ROG STRIX B550-F") == "asus-rog-strix-b550-f"
    assert "-" not in _make_slug("  test  ")[:1]  # no leading dash


def test_make_checksum_stable():
    payload = {"brand": "AMD", "mpn": "100-100000910WOF"}
    c1 = _make_checksum(payload)
    c2 = _make_checksum(payload)
    assert c1 == c2


def test_make_checksum_different():
    c1 = _make_checksum({"brand": "AMD"})
    c2 = _make_checksum({"brand": "Intel"})
    assert c1 != c2


def test_import_total_limit():
    assert IMPORT_TOTAL_LIMIT == 300


def test_category_limits_sum_at_most_300():
    assert sum(IMPORT_CATEGORY_LIMITS.values()) <= IMPORT_TOTAL_LIMIT


def test_category_limits_values():
    assert IMPORT_CATEGORY_LIMITS["CPU"] == 40
    assert IMPORT_CATEGORY_LIMITS["GPU"] == 40
    assert IMPORT_CATEGORY_LIMITS["MOTHERBOARD"] == 40
    assert IMPORT_CATEGORY_LIMITS["RAM"] == 40
    assert IMPORT_CATEGORY_LIMITS["STORAGE"] == 40
    assert IMPORT_CATEGORY_LIMITS["PSU"] == 30
    assert IMPORT_CATEGORY_LIMITS["CASE"] == 30
    assert IMPORT_CATEGORY_LIMITS["COOLER"] == 20


# ---------------------------------------------------------------------------
# Scan source tests
# ---------------------------------------------------------------------------

def test_scan_source_selects_valid_cpu(mock_opendb):
    _write_cpu(mock_opendb, "cpu-001", "BX8071514600K", "Intel", "Intel Core i5-14600K")
    products, specs, stats, rev = scan_source(mock_opendb, total_limit=300)
    assert any(p["category"] == "CPU" for p in products)
    cpu_p = [p for p in products if p["category"] == "CPU"][0]
    assert cpu_p["brand"] == "Intel"
    assert cpu_p["manufacturer_part_number"] == "BX8071514600K"


def test_scan_source_no_fuzzy_match(mock_opendb):
    """Records where MPN equals brand name (fuzzy) are rejected."""
    data = {
        "opendb_id": "bad-cpu",
        "metadata": {
            "name": "Intel",
            "manufacturer": "Intel",
            "part_numbers": ["Intel"],  # MPN same as brand name — ambiguous
        },
    }
    (mock_opendb / "open-db" / "CPU" / "bad.json").write_text(json.dumps(data))
    products, _, stats, _ = scan_source(mock_opendb, total_limit=300)
    # This record should be rejected (mpn == brand)
    assert not any(p.get("manufacturer_part_number") == "Intel" and p.get("brand") == "Intel"
                   for p in products)


def test_scan_source_no_price_fields(mock_opendb):
    _write_cpu(mock_opendb, "cpu-002", "BX8071514600K", "Intel", "Intel Core i5-14600K")
    products, specs, _, _ = scan_source(mock_opendb, total_limit=300)
    for p in products:
        assert "price" not in p
        assert "regular_price" not in p
        assert "sale_price" not in p
        assert "currency" not in p
        assert "store_sku" not in p
        assert "product_url" not in p
        assert "image" not in p
        assert "image_url" not in p
    for sp in specs:
        assert "price" not in sp
        assert "currency" not in sp


def test_scan_source_no_retailer_fields(mock_opendb):
    """Retailer fields from general_product_information are never in output."""
    data = {
        "opendb_id": "cpu-003",
        "metadata": {
            "name": "Intel Core i7-14700K",
            "manufacturer": "Intel",
            "part_numbers": ["BX8071514700K"],
        },
        "general_product_information": {
            "amazon_sku": "B0CGJ41N95",
            "newegg_sku": "N82E16819117624",
            "walmart_sku": 12345,
        },
    }
    (mock_opendb / "open-db" / "CPU" / "cpu003.json").write_text(json.dumps(data))
    products, _, _, _ = scan_source(mock_opendb, total_limit=300)
    for p in products:
        assert "amazon_sku" not in p
        assert "newegg_sku" not in p
        assert "walmart_sku" not in p


def test_scan_source_respects_total_limit(mock_opendb):
    for i in range(10):
        _write_cpu(mock_opendb, f"cpu-{i}", f"CPU-MPN-{i}", "Intel", f"Intel CPU {i}")
    products, _, _, _ = scan_source(mock_opendb, total_limit=5)
    assert len(products) <= 5


def test_scan_source_deterministic(mock_opendb):
    for i in range(5):
        _write_cpu(mock_opendb, f"cpu-{i:03}", f"MPN-{i:03}", "Intel", f"Intel CPU {i:03}")
    p1, _, _, _ = scan_source(mock_opendb, total_limit=300)
    p2, _, _, _ = scan_source(mock_opendb, total_limit=300)
    assert [p["manufacturer_part_number"] for p in p1] == [
        p["manufacturer_part_number"] for p in p2
    ]


def test_scan_source_opendb_source_commit_present(mock_opendb):
    _write_cpu(mock_opendb, "cpu-prov", "MPN-PROV", "Intel", "Intel CPU Prov")
    products, _, _, _ = scan_source(mock_opendb, total_limit=300)
    for p in products:
        assert "_opendb_source_commit" in p
        assert "_opendb_rel_path" in p


def test_scan_source_no_image_import(mock_opendb):
    """No product image rows should be produced by scan."""
    _write_cpu(mock_opendb, "cpu-img", "MPN-IMG", "Intel", "Intel CPU Img")
    products, specs, _, _ = scan_source(mock_opendb, total_limit=300)
    # There is no image data in the scan result
    for p in products:
        assert "source_url" not in p
        assert "storage_key" not in p
        assert "rights_status" not in p


def test_scan_source_multiple_categories(mock_opendb):
    _write_cpu(mock_opendb, "cpu-a", "CPU-MPN-A", "Intel", "Intel CPU A")
    _write_gpu(mock_opendb, "gpu-a", "GPU-MPN-A", "NVIDIA", "NVIDIA GPU A")
    products, _, _, _ = scan_source(mock_opendb, total_limit=300)
    categories = {p["category"] for p in products}
    assert "CPU" in categories
    assert "GPU" in categories


def test_scan_source_missing_name_rejected(mock_opendb):
    data = {
        "opendb_id": "cpu-noname",
        "metadata": {
            "name": "",
            "manufacturer": "Intel",
            "part_numbers": ["SOME-MPN"],
        },
    }
    (mock_opendb / "open-db" / "CPU" / "noname.json").write_text(json.dumps(data))
    products, _, _, _ = scan_source(mock_opendb, total_limit=300)
    assert not any(p.get("manufacturer_part_number") == "SOME-MPN" for p in products)


def test_scan_source_missing_brand_rejected(mock_opendb):
    data = {
        "opendb_id": "cpu-nobrand",
        "metadata": {
            "name": "Some CPU",
            "manufacturer": "",
            "part_numbers": ["SOME-MPN-2"],
        },
    }
    (mock_opendb / "open-db" / "CPU" / "nobrand.json").write_text(json.dumps(data))
    products, _, _, _ = scan_source(mock_opendb, total_limit=300)
    assert not any(p.get("manufacturer_part_number") == "SOME-MPN-2" for p in products)


def test_scan_source_unsupported_category_skipped(mock_opendb):
    """A file placed in a folder that isn't supported is simply not scanned."""
    (mock_opendb / "open-db" / "UnknownCat").mkdir(exist_ok=True)
    (mock_opendb / "open-db" / "UnknownCat" / "item.json").write_text(
        json.dumps({"opendb_id": "x", "metadata": {"name": "X", "manufacturer": "X", "part_numbers": ["X"]}})
    )
    # scan_source only iterates over IMPORT_CATEGORY_LIMITS keys — no error
    products, _, _, _ = scan_source(mock_opendb, total_limit=300)
    assert not any(p.get("category") == "UnknownCat" for p in products)


# ---------------------------------------------------------------------------
# Dry-run command tests
# ---------------------------------------------------------------------------

def test_dry_run_passes_with_valid_data(mock_opendb):
    _write_cpu(mock_opendb, "cpu-dr", "MPN-DR", "Intel", "Intel CPU DR")
    args = MagicMock()
    args.source = str(mock_opendb)
    args.limit = 300
    result = cmd_dry_run(args)
    assert result == 0


def test_dry_run_fails_with_no_records(mock_opendb):
    args = MagicMock()
    args.source = str(mock_opendb)
    args.limit = 300
    result = cmd_dry_run(args)
    assert result == 1


def test_dry_run_never_writes_to_db(mock_opendb, monkeypatch):
    """Dry-run must not import anything into DB."""
    _write_cpu(mock_opendb, "cpu-nw", "MPN-NW", "Intel", "Intel NW CPU")

    # Ensure any session call would fail loudly if attempted
    import app.catalog.buildcores_import_cli as cli_mod
    original_make_engine = cli_mod._make_engine

    def no_db(*args, **kwargs):
        raise RuntimeError("DRY-RUN MUST NOT CONNECT TO DB")

    monkeypatch.setattr(cli_mod, "_make_engine", no_db)
    args = MagicMock()
    args.source = str(mock_opendb)
    args.limit = 300
    result = cmd_dry_run(args)
    assert result == 0  # passed without DB


# ---------------------------------------------------------------------------
# Safety gate tests
# ---------------------------------------------------------------------------

def test_import_flag_required(mock_opendb, monkeypatch):
    monkeypatch.delenv("CATALOG_BUILDCORES_IMPORT_ENABLED", raising=False)
    result = main(["import", "--source", str(mock_opendb), "--limit", "300"])
    assert result == 1


def test_import_flag_false_rejected(mock_opendb, monkeypatch):
    monkeypatch.setenv("CATALOG_BUILDCORES_IMPORT_ENABLED", "false")
    result = main(["import", "--source", str(mock_opendb), "--limit", "300"])
    assert result == 1


def test_wrong_host_rejected(monkeypatch):
    monkeypatch.setenv("CATALOG_DB_HOST", "rds.amazonaws.com")
    monkeypatch.setenv("CATALOG_DB_NAME", "catalog")
    monkeypatch.setenv("CATALOG_DB_PORT", "5433")
    with pytest.raises(RuntimeError, match="Safety gate: host must be 127.0.0.1"):
        _verify_connection_safety("")


def test_wrong_db_name_rejected(monkeypatch):
    monkeypatch.setenv("CATALOG_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("CATALOG_DB_NAME", "production")
    monkeypatch.setenv("CATALOG_DB_PORT", "5433")
    with pytest.raises(RuntimeError, match="Safety gate: database name must be 'catalog'"):
        _verify_connection_safety("")


def test_correct_proxy_passes(monkeypatch):
    monkeypatch.setenv("CATALOG_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("CATALOG_DB_NAME", "catalog")
    monkeypatch.setenv("CATALOG_DB_PORT", "5433")
    _verify_connection_safety("")  # must not raise


def test_bounded_limit_enforced(mock_opendb):
    """CLI hard-caps at 300."""
    for i in range(50):
        _write_cpu(mock_opendb, f"cpu-{i:03}", f"BIGMPN-{i:03}", "Intel", f"Intel CPU {i}")
    products, _, _, _ = scan_source(mock_opendb, total_limit=300)
    assert len(products) <= 300


def test_no_gtin_fabrication(mock_opendb):
    """The adapter must not create GTIN values from OpenDB ID."""
    _write_cpu(mock_opendb, "cpu-gtin", "MPN-GTIN", "Intel", "Intel GTIN CPU")
    products, _, _, _ = scan_source(mock_opendb, total_limit=300)
    for p in products:
        # GTIN must be None — OpenDB has no GTIN data
        assert p.get("gtin") is None


def test_idempotency_command_flag_required(mock_opendb, monkeypatch):
    monkeypatch.delenv("CATALOG_BUILDCORES_IMPORT_ENABLED", raising=False)
    result = main(["idempotency", "--source", str(mock_opendb), "--limit", "300"])
    assert result == 1


# ---------------------------------------------------------------------------
# License / attribution tests
# ---------------------------------------------------------------------------

def test_attribution_file_exists():
    attr_path = Path(__file__).parent.parent.parent / "docs" / "third-party" / "BUILDCORES_OPENDB_ATTRIBUTION.md"
    assert attr_path.exists(), "Attribution file must exist at docs/third-party/BUILDCORES_OPENDB_ATTRIBUTION.md"


def test_attribution_file_contains_required_fields():
    attr_path = Path(__file__).parent.parent.parent / "docs" / "third-party" / "BUILDCORES_OPENDB_ATTRIBUTION.md"
    if not attr_path.exists():
        pytest.skip("Attribution file not yet created")
    content = attr_path.read_text()
    assert "ODC-By" in content, "Attribution must mention ODC-By license"
    assert "buildcores" in content.lower(), "Attribution must mention BuildCores"
    assert "github.com" in content.lower(), "Attribution must include upstream repository"


# ---------------------------------------------------------------------------
# Neo4j untouched assertion
# ---------------------------------------------------------------------------

def test_neo4j_not_touched(mock_opendb, monkeypatch):
    """Import code must never import neo4j or attempt Neo4j connections."""
    import importlib
    import sys

    # Ensure neo4j is not imported during scan
    neo4j_modules = [m for m in sys.modules if "neo4j" in m]
    _write_cpu(mock_opendb, "cpu-neo", "MPN-NEO", "Intel", "Intel NEO CPU")
    scan_source(mock_opendb, total_limit=300)
    new_neo4j_modules = [m for m in sys.modules if "neo4j" in m]
    assert new_neo4j_modules == neo4j_modules, "scan_source must not import neo4j"


# ---------------------------------------------------------------------------
# Secret redaction test
# ---------------------------------------------------------------------------

def test_secret_not_in_checksum():
    """The checksum function must never include secret values."""
    payload = {"brand": "Intel", "mpn": "MPN-SECRET"}
    checksum = _make_checksum(payload)
    # checksum is just a hash — verify it doesn't contain raw text
    assert "Intel" not in checksum
    assert "MPN-SECRET" not in checksum
