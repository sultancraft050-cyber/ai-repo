from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.graph.driver import Neo4jSessionManager  # noqa: E402
from app.graph.pricing_repository import Neo4jPricingRepository  # noqa: E402
from app.models.catalog import ConfirmedSpecEnrichmentRequest  # noqa: E402


DEFAULT_FIXTURE = BACKEND_ROOT / "data" / "canonical_specs" / "phase2_gpu_exact_card_specs.json"


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"source_name", "license_note", "gpu_exact_card_records"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"fixture missing required keys: {', '.join(missing)}")
    return payload


def _request(*, fixture: dict[str, Any], dry_run: bool) -> ConfirmedSpecEnrichmentRequest:
    return ConfirmedSpecEnrichmentRequest(
        category="GPU",
        source_name=str(fixture["source_name"]),
        license_note=str(fixture["license_note"]),
        records=list(fixture["gpu_exact_card_records"]),
        dry_run=dry_run,
    )


def _summary(response: Any) -> dict[str, Any]:
    statuses = Counter(str(item.status) for item in response.items)
    return {
        "fixture_records": response.total_records,
        "matched_staged_records": response.matched_staged_records,
        "would_enrich": statuses.get("would_enrich", 0),
        "enriched": response.enriched_records,
        "skipped": response.skipped_records,
        "conflicts": response.conflict_count,
        "evidence_created": response.evidence_created,
        "statuses": dict(statuses),
        "items": [item.model_dump() for item in response.items],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled Phase 2 exact-card GPU spec enrichment.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--execute", action="store_true", help="Execute enrichment only after dry-run has no conflicts.")
    args = parser.parse_args()

    fixture = _load_fixture(args.fixture)
    manager = Neo4jSessionManager(settings)
    repository = Neo4jPricingRepository(manager.driver)
    try:
        dry = repository.enrich_staged_specs(_request(fixture=fixture, dry_run=True))
        safe_to_execute = dry.conflict_count == 0 and dry.matched_staged_records > 0
        report: dict[str, Any] = {
            "dry_run": _summary(dry),
            "safe_to_execute": safe_to_execute,
            "executed": False,
            "execute": None,
            "deferred_exact_card_targets": fixture.get("deferred_exact_card_targets", []),
            "notes": [
                "GPU family-ready remains separate from exact-ready.",
                "No URL ingestion is performed.",
                "No canonical commit is performed.",
                "PriceSnapshot and RegionalPriceSnapshot are not written by this script.",
            ],
        }
        if args.execute and safe_to_execute:
            execute = repository.enrich_staged_specs(_request(fixture=fixture, dry_run=False))
            report["executed"] = True
            report["execute"] = _summary(execute)
        elif args.execute:
            report["execute"] = {"skipped_reason": "dry-run reported conflicts or no exact staged matches"}
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        manager.close()


if __name__ == "__main__":
    main()
