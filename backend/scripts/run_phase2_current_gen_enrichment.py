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
from app.services.catalog_expansion import match_expansion_target  # noqa: E402
from app.services.import_adapters.pc_part_dataset_adapter import load_pc_part_dataset_records  # noqa: E402


DEFAULT_FIXTURE = BACKEND_ROOT / "data" / "canonical_specs" / "phase2_current_gen_specs.json"
DEFAULT_DATASET_DIR = BACKEND_ROOT / "data" / "imports" / "datasets" / "pc-part-dataset"


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"source_name", "license_note", "gpu_family_records", "cpu_records"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"fixture missing required keys: {', '.join(missing)}")
    return payload


def _request(*, fixture: dict[str, Any], category: str, records: list[dict[str, Any]], dry_run: bool) -> ConfirmedSpecEnrichmentRequest:
    return ConfirmedSpecEnrichmentRequest(
        category=category,
        source_name=str(fixture["source_name"]),
        license_note=str(fixture["license_note"]),
        records=records,
        dry_run=dry_run,
    )


def _summarize_enrichment(response: Any) -> dict[str, Any]:
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
        "sample_items": [item.model_dump() for item in response.items[:10]],
    }


def _scan_current_gen_candidates(dataset_dir: Path) -> dict[str, Any]:
    scan_specs = {
        "GPU": dataset_dir / "video-card.json",
        "CPU": dataset_dir / "cpu.json",
    }
    result: dict[str, Any] = {}
    for category, path in scan_specs.items():
        records = load_pc_part_dataset_records(path, category, 100000)
        tiers: Counter[str] = Counter()
        current_gen_families: Counter[str] = Counter()
        missing: Counter[str] = Counter()
        family_ready_count = 0
        exact_ready_count = 0
        compatibility_ready_count = 0
        for record in records:
            match = match_expansion_target(record, category)
            if not match:
                tiers["outside_manifest"] += 1
                continue
            tiers[match.priority_tier] += 1
            if match.priority_tier != "current_gen_priority":
                continue
            current_gen_families[match.family_name] += 1
            for field in record.get("missing_compatibility_fields") or []:
                missing[str(field)] += 1
            if bool(record.get("compatibility_ready")):
                compatibility_ready_count += 1
            if bool(record.get("compatibility_ready_exact")):
                exact_ready_count += 1
            if bool(record.get("compatibility_ready_family")):
                family_ready_count += 1
        result[category] = {
            "total_records": len(records),
            "current_gen_candidates": tiers.get("current_gen_priority", 0),
            "value_fallback_candidates": tiers.get("value_fallback", 0),
            "legacy_deprioritized_candidates": tiers.get("legacy_deprioritized", 0),
            "outside_manifest": tiers.get("outside_manifest", 0),
            "compatibility_ready_current_gen": compatibility_ready_count,
            "exact_ready_current_gen": exact_ready_count,
            "family_ready_current_gen": family_ready_count,
            "top_missing_current_gen_fields": missing.most_common(8),
            "current_gen_families": sorted(current_gen_families.items()),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled Phase 2 current-gen CPU/GPU spec enrichment.")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--execute", action="store_true", help="Execute enrichment only after dry-run has no conflicts.")
    parser.add_argument("--scan-only", action="store_true", help="Scan current-gen candidates without connecting to Neo4j.")
    args = parser.parse_args()

    fixture = _load_fixture(args.fixture)
    if args.scan_only:
        print(
            json.dumps(
                {
                    "current_gen_staging_scan": _scan_current_gen_candidates(args.dataset_dir),
                    "fixture": {
                        "gpu_family_records": len(fixture["gpu_family_records"]),
                        "cpu_records": len(fixture["cpu_records"]),
                        "ambiguous_gpu_variants_requiring_split": fixture.get(
                            "gpu_family_records_requiring_variant_split", []
                        ),
                    },
                    "notes": [
                        "Scan-only mode does not connect to Neo4j.",
                        "No URL ingestion is performed.",
                        "No canonical commit is performed.",
                        "No PriceSnapshot or RegionalPriceSnapshot writes are possible in scan-only mode.",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    manager = Neo4jSessionManager(settings)
    repository = Neo4jPricingRepository(manager.driver)
    try:
        gpu_dry = repository.enrich_staged_specs(
            _request(fixture=fixture, category="GPU", records=list(fixture["gpu_family_records"]), dry_run=True)
        )
        cpu_dry = repository.enrich_staged_specs(
            _request(fixture=fixture, category="CPU", records=list(fixture["cpu_records"]), dry_run=True)
        )
        safe_to_execute = gpu_dry.conflict_count == 0 and cpu_dry.conflict_count == 0
        report: dict[str, Any] = {
            "dry_run": {
                "GPU": _summarize_enrichment(gpu_dry),
                "CPU": _summarize_enrichment(cpu_dry),
            },
            "safe_to_execute": safe_to_execute,
            "executed": False,
            "execute": None,
            "current_gen_staging_scan_after": None,
            "notes": [
                "No URL ingestion is performed.",
                "No canonical commit is performed.",
                "PriceSnapshot and RegionalPriceSnapshot are not written by this script.",
            ],
            "ambiguous_gpu_variants_requiring_split": fixture.get("gpu_family_records_requiring_variant_split", []),
        }
        if args.execute and safe_to_execute:
            gpu_execute = repository.enrich_staged_specs(
                _request(fixture=fixture, category="GPU", records=list(fixture["gpu_family_records"]), dry_run=False)
            )
            cpu_execute = repository.enrich_staged_specs(
                _request(fixture=fixture, category="CPU", records=list(fixture["cpu_records"]), dry_run=False)
            )
            report["executed"] = True
            report["execute"] = {
                "GPU": _summarize_enrichment(gpu_execute),
                "CPU": _summarize_enrichment(cpu_execute),
            }
            report["current_gen_staging_scan_after"] = _scan_current_gen_candidates(args.dataset_dir)
        elif args.execute:
            report["execute"] = {"skipped_reason": "dry-run reported conflicts"}
        else:
            report["current_gen_staging_scan_after"] = _scan_current_gen_candidates(args.dataset_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        manager.close()


if __name__ == "__main__":
    main()
