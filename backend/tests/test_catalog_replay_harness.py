from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.catalog.replay_harness import HarnessError, compare, list_scenarios, replay, run, show_manifest


ANCHOR = "2026-07-13T09:00:00+03:00"


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("REPLAY_FAILURE_HARNESS_ENABLED", "true")
    monkeypatch.setenv("CATALOG_FEED_SIMULATOR_ENABLED", "true")
    monkeypatch.setenv("CATALOG_FEED_MAPPING_ENABLED", "true")
    monkeypatch.setenv("CATALOG_IMPORT_ENABLED", "true")


def test_harness_disabled_and_local_sqlite_guards(monkeypatch, tmp_path):
    monkeypatch.setenv("REPLAY_FAILURE_HARNESS_ENABLED", "false")
    with pytest.raises(HarnessError, match="HARNESS_DISABLED"):
        run(scenario_id="exact-replay", database_url=f"sqlite:///{tmp_path / 'x.sqlite3'}", seed=1, timestamp_anchor=ANCHOR)
    monkeypatch.setenv("REPLAY_FAILURE_HARNESS_ENABLED", "true")
    with pytest.raises(HarnessError, match="SQLITE_REQUIRED"):
        run(scenario_id="exact-replay", database_url="postgresql://local", seed=1, timestamp_anchor=ANCHOR)


def test_scenarios_and_deterministic_replay(tmp_path):
    assert len(list_scenarios()) == 12
    database = f"sqlite:///{tmp_path / 'replay.sqlite3'}"
    first = run(scenario_id="exact-replay", database_url=database, seed=7, timestamp_anchor=ANCHOR)
    second = run(scenario_id="exact-replay", database_url=database, seed=7, timestamp_anchor=ANCHOR, replay_number=2)
    assert first.manifest["generated_checksum"] == second.manifest["generated_checksum"]
    assert first.manifest["final_status"] == "PASS_CLEAN_RUN_EQUIVALENT"
    assert compare(first.run_id, second.run_id)["same_generated_checksum"] is True


@pytest.mark.parametrize("point", ["BEFORE_GENERATION", "DURING_MAPPING", "DURING_STAGING", "DURING_COMMIT", "BEFORE_PRIMARY_IMAGE_CHANGE"])
def test_controlled_failure_points_are_safe(tmp_path, point):
    database = f"sqlite:///{tmp_path / (point + '.sqlite3')}"
    result = run(scenario_id="interrupted-staging", database_url=database, seed=1, timestamp_anchor=ANCHOR, failure_point=point, failure_mode="CONTROLLED_EXCEPTION")
    assert result.manifest["actual_result"] in {"BLOCKED", "EXPECTED_FAILURE"}
    assert result.manifest["safe_error"]
    assert "generated_checksum" in show_manifest(result.run_id)


def test_invalid_controls_and_evidence_contains_no_raw_records(tmp_path):
    database = f"sqlite:///{tmp_path / 'invalid.sqlite3'}"
    with pytest.raises(HarnessError, match="FAILURE_POINT_INVALID"):
        run(scenario_id="exact-replay", database_url=database, seed=1, timestamp_anchor=ANCHOR, failure_point="eval")
    result = run(scenario_id="malformed-retry", database_url=database, seed=2, timestamp_anchor=ANCHOR, failure_point="DURING_STAGING", failure_mode="TRUNCATED_INPUT")
    evidence = json.dumps({path.name: path.read_text() for path in result.directory.iterdir()})
    assert "Test CPU Model" not in evidence and "password" not in evidence.lower()


def test_replay_count_is_bounded(tmp_path):
    with pytest.raises(HarnessError, match="RETRY_LIMIT_REACHED"):
        replay(scenario_id="exact-replay", database_url=f"sqlite:///{tmp_path / 'x.sqlite3'}", seed=1, timestamp_anchor=ANCHOR, replay_count=4)


def test_no_network_or_arbitrary_execution_symbols():
    text = Path(__file__).parents[1].joinpath("app/catalog/replay_harness.py").read_text()
    assert "requests" not in text and "httpx" not in text and "urlopen" not in text and "subprocess" not in text
    assert "eval(" not in text and "exec(" not in text and "__import__" not in text
