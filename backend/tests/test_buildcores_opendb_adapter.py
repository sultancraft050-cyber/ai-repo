from __future__ import annotations

import json
import os
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.catalog.models import (
    Base, ImportSource, ImportBatch, ImportRecord, Product, ProductSpecification, ProductImage
)
from app.catalog.buildcores_opendb_adapter import (
    validate_checkout, get_git_revision, parse_opendb_record, CATEGORY_LIMITS
)
from app.catalog.buildcores_opendb_cli import run_dry_run_mapping, main

@pytest.fixture()
def mock_opendb_checkout(tmp_path):
    # Create the directory structure for mock OpenDB
    (tmp_path / "LICENSE.txt").write_text("Mock ODC-By-1.0 License")
    (tmp_path / "README.md").write_text("Mock BuildCores OpenDB README")
    
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()
    
    open_db_dir = tmp_path / "open-db"
    open_db_dir.mkdir()
    
    categories = {
        "CPU": "CPU",
        "GPU": "GPU",
        "Motherboard": "Motherboard",
        "RAM": "RAM",
        "Storage": "Storage",
        "PSU": "PSU",
        "Case": "PCCase",
        "Cooler": "CPUCooler"
    }
    
    for cat_name, folder in categories.items():
        (schemas_dir / f"{folder}.schema.json").write_text(json.dumps({"properties": {}}))
        (open_db_dir / folder).mkdir()
        
    return tmp_path

@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value

def test_validate_checkout_checks_structure(mock_opendb_checkout, tmp_path):
    assert validate_checkout(mock_opendb_checkout) is True
    
    # Missing LICENSE.txt
    (mock_opendb_checkout / "LICENSE.txt").unlink()
    assert validate_checkout(mock_opendb_checkout) is False

def test_get_git_revision_returns_string(mock_opendb_checkout):
    rev = get_git_revision(mock_opendb_checkout)
    assert isinstance(rev, str)

def test_cpu_mapping(mock_opendb_checkout):
    cpu_data = {
        "opendb_id": "mock-cpu-uuid",
        "socket": "AM5",
        "cores": {"total": 8, "threads": 16},
        "clocks": {"performance": {"base": 4.2, "boost": 5.0}},
        "specifications": {
            "tdp": 120,
            "integratedGraphics": {"model": "Radeon Graphics"},
            "memory": {"types": ["DDR5"]}
        },
        "metadata": {
            "name": "AMD Ryzen 7 7800X3D",
            "manufacturer": "AMD",
            "part_numbers": ["100-100000910WOF"]
        }
    }
    cpu_file = mock_opendb_checkout / "open-db" / "CPU" / "cpu.json"
    cpu_file.write_text(json.dumps(cpu_data))
    
    from app.catalog.buildcores_opendb_adapter import CategoryStats
    stats = CategoryStats("CPU")
    p_payload, specs = parse_opendb_record(cpu_file, "CPU", stats)
    
    assert p_payload["brand"] == "AMD"
    assert p_payload["manufacturer_part_number"] == "100-100000910WOF"
    assert p_payload["category"] == "CPU"
    assert p_payload["canonical_name"] == "AMD Ryzen 7 7800X3D"
    
    # check specifications mapped
    spec_map = {s["specification_key"]: s for s in specs}
    assert spec_map["socket"]["normalized_value"] == "AM5"
    assert spec_map["core_count"]["normalized_value"] == "8"
    assert spec_map["thread_count"]["normalized_value"] == "16"
    assert spec_map["base_clock"]["normalized_value"] == "4.2"
    assert spec_map["boost_clock"]["normalized_value"] == "5.0"
    assert spec_map["tdp"]["normalized_value"] == "120"
    assert spec_map["integrated_graphics"]["normalized_value"] == "Radeon Graphics"
    assert spec_map["supported_memory_generation"]["normalized_value"] == "DDR5"

def test_gpu_mapping(mock_opendb_checkout):
    gpu_data = {
        "opendb_id": "mock-gpu-uuid",
        "chipset": "Radeon RX 7800 XT",
        "memory": 16,
        "length": 267,
        "total_slot_width": 2.5,
        "tdp": 263,
        "power_connectors": {"pcie_8_pin": 2, "pcie_6_pin": 0},
        "metadata": {
            "name": "AMD Radeon RX 7800 XT",
            "manufacturer": "AMD",
            "part_numbers": ["RX-7800XT-16G"]
        }
    }
    gpu_file = mock_opendb_checkout / "open-db" / "GPU" / "gpu.json"
    gpu_file.write_text(json.dumps(gpu_data))
    
    from app.catalog.buildcores_opendb_adapter import CategoryStats
    stats = CategoryStats("GPU")
    p_payload, specs = parse_opendb_record(gpu_file, "GPU", stats)
    
    assert p_payload["brand"] == "AMD"
    assert p_payload["manufacturer_part_number"] == "RX-7800XT-16G"
    
    spec_map = {s["specification_key"]: s for s in specs}
    assert spec_map["chipset"]["normalized_value"] == "Radeon RX 7800 XT"
    assert spec_map["vram"]["normalized_value"] == "16"
    assert spec_map["length"]["normalized_value"] == "267"
    assert spec_map["slot_width"]["normalized_value"] == "2.5"
    assert spec_map["power_consumption"]["normalized_value"] == "263"
    assert spec_map["power_connectors"]["normalized_value"] == "2x 8 Pin"

def test_limits_capped_correctly(mock_opendb_checkout):
    # Write 5 mock CPUs (limit CPU is 40 normally, but we test max-total 3 override)
    for i in range(5):
        cpu_data = {
            "opendb_id": f"cpu-{i}",
            "metadata": {
                "name": f"CPU {i}",
                "manufacturer": "Intel",
                "part_numbers": [f"INT-CPU-{i}"]
            }
        }
        (mock_opendb_checkout / "open-db" / "CPU" / f"cpu_{i}.json").write_text(json.dumps(cpu_data))
        
    products, specs, stats, rev = run_dry_run_mapping(mock_opendb_checkout, ["CPU"], max_total=3)
    assert len(products) == 3
    assert len(stats["CPU"].spec_keys_discovered) == 0 # no compatibility specs inside mock

def test_path_traversal_rejection(mock_opendb_checkout):
    with pytest.raises(SystemExit):
        main(["inspect", "--source", "../outside", "--categories", "CPU"])

def test_stage_and_commit(mock_opendb_checkout, session, monkeypatch):
    monkeypatch.setenv("CATALOG_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("CATALOG_IMPORT_ENABLED", "true")
    monkeypatch.setenv("CATALOG_WRITES_ENABLED", "true")
    
    # Mock get_session in buildcores_opendb_cli to return our memory session fixture
    monkeypatch.setattr("app.catalog.buildcores_opendb_cli.get_session", lambda: session)
    
    # Write mock CPU
    cpu_data = {
        "opendb_id": "cpu-test",
        "socket": "AM5",
        "cores": {"total": 8},
        "metadata": {
            "name": "AMD Ryzen 7 7800X3D",
            "manufacturer": "AMD",
            "part_numbers": ["100-100000910WOF"]
        }
    }
    (mock_opendb_checkout / "open-db" / "CPU" / "cpu.json").write_text(json.dumps(cpu_data))
    
    # Run commit-local command
    main(["commit-local", "--source", str(mock_opendb_checkout), "--categories", "CPU", "--max-total", "10"])
    
    # Verify records got committed to database
    db_products = session.scalars(select(Product)).all()
    assert len(db_products) == 1
    assert db_products[0].canonical_name == "AMD Ryzen 7 7800X3D"
    
    db_specs = session.scalars(select(ProductSpecification)).all()
    assert len(db_specs) == 2
    assert {s.specification_key for s in db_specs} == {"socket", "core_count"}
