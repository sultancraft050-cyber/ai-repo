from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.catalog.feed_simulator import (
    Mutation, SimulatorError, apply_mutations, generate, list_adapters, list_scenarios,
    preview, require_enabled, validate_adapter,
)
from app.core.config import Settings


ANCHOR = "2026-07-13T09:00:00+03:00"


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("CATALOG_FEED_SIMULATOR_ENABLED", "true")
    monkeypatch.setenv("CATALOG_FEED_MAPPING_ENABLED", "true")
    monkeypatch.setenv("CATALOG_IMPORT_ENABLED", "true")


def test_simulator_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CATALOG_FEED_SIMULATOR_ENABLED", raising=False)
    with pytest.raises(SimulatorError, match="SIMULATOR_DISABLED"):
        require_enabled()
    assert Settings.from_env().catalog_feed_simulator_enabled is False


def test_adapter_and_scenarios_are_repository_definitions_only():
    assert any(item["adapter_id"] == "synthetic-sa-retailer-v1" for item in list_adapters())
    assert len(list_scenarios()) == 12
    assert validate_adapter("synthetic-sa-retailer-v1")["authorization_status"] == "SYNTHETIC_ONLY"
    with pytest.raises(SimulatorError, match="ADAPTER_INVALID"):
        validate_adapter("invalid-revoked")


def test_generation_is_deterministic_and_bounded(tmp_path):
    first = generate(adapter_id="synthetic-sa-retailer-v1", scenario_id="initial-catalog-load", output_format="csv", seed=7, timestamp_anchor=ANCHOR, output_dir="/tmp/catalog-feed-simulator")
    second = generate(adapter_id="synthetic-sa-retailer-v1", scenario_id="initial-catalog-load", output_format="csv", seed=7, timestamp_anchor=ANCHOR, output_dir="/tmp/catalog-feed-simulator")
    assert first.run_id == second.run_id
    assert first.manifest["generated_file_checksum"] == second.manifest["generated_file_checksum"]
    assert first.manifest["record_count"] == 6
    assert "fixture.invalid" not in json.dumps(first.manifest)
    assert Path("/tmp/catalog-feed-simulator").resolve() in first.directory.parents
    different = generate(adapter_id="synthetic-sa-retailer-v1", scenario_id="initial-catalog-load", output_format="csv", seed=8, timestamp_anchor=ANCHOR)
    assert different.manifest["generated_file_checksum"] != first.manifest["generated_file_checksum"]


@pytest.mark.parametrize("output_format", ["csv", "json-array", "json-records"])
def test_formats_and_mapping_preview(output_format):
    run = generate(adapter_id="synthetic-sa-retailer-v1", scenario_id="image-metadata-review", entity_type="PRODUCT_IMAGE_METADATA", output_format=output_format, seed=8, timestamp_anchor=ANCHOR)
    result = preview(run)
    assert result["record_count"] == 2
    assert (run.directory / run.manifest["generated_file_name"]).read_bytes().decode("utf-8")


def test_mutations_are_strict_and_input_is_not_modified():
    original = [{"price": "10.00", "stock": "available"}]
    changed = apply_mutations(original, [{"operator": Mutation.INCREMENT_DECIMAL.value, "field": "price", "amount": 2}], seed=1)
    assert original[0]["price"] == "10.00" and changed[0]["price"] == "12.00"
    with pytest.raises(SimulatorError, match="SCENARIO_INVALID"):
        apply_mutations(original, [{"operator": "eval"}], seed=1)


def test_limits_and_local_path_restriction(monkeypatch):
    with pytest.raises(SimulatorError, match="LOCAL_PATH_REQUIRED"):
        generate(adapter_id="synthetic-sa-retailer-v1", scenario_id="initial-catalog-load", timestamp_anchor=ANCHOR, output_dir="/tmp/not-approved")
    monkeypatch.setenv("CATALOG_FEED_SIMULATOR_MAX_MUTATIONS", "1")
    with pytest.raises(SimulatorError, match="MUTATION_LIMIT_EXCEEDED"):
        apply_mutations([{"price": "1"}], [{"operator": "set_field", "field": "a", "value": "x"}, {"operator": "set_field", "field": "b", "value": "y"}], seed=1)


def test_no_network_or_execution_symbols():
    text = Path(__file__).parents[1].joinpath("app/catalog/feed_simulator.py").read_text()
    assert "requests" not in text and "httpx" not in text and "urlopen" not in text and "subprocess" not in text
    assert "eval(" not in text and "exec(" not in text
