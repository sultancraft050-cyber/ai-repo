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
from app.models.source_url import ProductUrlIngestRequest, ProductUrlPreviewRequest  # noqa: E402
from app.services.product_url_sources import ProductUrlIngestionService  # noqa: E402
from app.services.region_config import normalize_region  # noqa: E402
from app.services.saudi_build_generator import SaudiLocalBuildService  # noqa: E402


DEFAULT_URL_BATCH = BACKEND_ROOT / "data" / "pricing_batches" / "core500_url_batch.example.json"
DEFAULT_GPU_EXACT_FIXTURE = BACKEND_ROOT / "data" / "canonical_specs" / "phase2_gpu_exact_card_specs.json"
PRIORITY_CATEGORIES = ("GPU", "Storage", "RAM", "PSU")
COUNT_QUERIES = {
    "CanonicalProduct": "MATCH (p:Product:CanonicalProduct) RETURN count(p) AS count",
    "CanonicalEvidence": "MATCH (e:CanonicalEvidence) RETURN count(e) AS count",
    "PriceSnapshot": "MATCH (s:PriceSnapshot) RETURN count(s) AS count",
    "RegionalPriceSnapshot": "MATCH (s:RegionalPriceSnapshot) RETURN count(s) AS count",
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _load_gpu_exact_records(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    required = {"source_name", "license_note", "gpu_exact_card_records"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"GPU exact fixture missing required key(s): {', '.join(missing)}")
    return payload


def _gpu_exact_request(*, fixture: dict[str, Any], dry_run: bool) -> ConfirmedSpecEnrichmentRequest:
    return ConfirmedSpecEnrichmentRequest(
        category="GPU",
        source_name=str(fixture["source_name"]),
        license_note=str(fixture["license_note"]),
        records=list(fixture["gpu_exact_card_records"]),
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
        "sample_items": [item.model_dump(mode="json") for item in response.items[:10]],
    }


def _counts(repository: Neo4jPricingRepository) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label, query in COUNT_QUERIES.items():
        records, _, _ = repository.driver.execute_query(query, database_=settings.neo4j_database)
        counts[label] = int(records[0]["count"] or 0) if records else 0
    return counts


def _selected_batches(payload: dict[str, Any], categories: list[str]) -> list[dict[str, Any]]:
    selected = set(categories or PRIORITY_CATEGORIES)
    batches = payload.get("batches") or []
    if not isinstance(batches, list):
        raise ValueError("url batch payload must contain a batches list")
    result = []
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        category = str(batch.get("category") or "").strip()
        if category in selected:
            result.append(batch)
    return sorted(result, key=lambda item: PRIORITY_CATEGORIES.index(str(item.get("category"))) if str(item.get("category")) in PRIORITY_CATEGORIES else 99)


def _url_entries(batch: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    entries = batch.get("urls") or []
    if not isinstance(entries, list):
        raise ValueError(f"{batch.get('category')} batch urls must be a list")
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, str):
            normalized.append({"url": entry, "approved": False})
        elif isinstance(entry, dict) and entry.get("url"):
            normalized.append(entry)
    return normalized[:limit] if limit else normalized


def _preview_and_maybe_ingest_urls(
    *,
    service: ProductUrlIngestionService,
    region: str,
    batches: list[dict[str, Any]],
    execute_pricing: bool,
    limit_per_category: int | None,
) -> dict[str, Any]:
    report: dict[str, Any] = {"categories": {}, "accepted_preview_count": 0, "rejected_preview_count": 0, "ingested_count": 0}
    for batch in batches:
        category = str(batch.get("category"))
        items: list[dict[str, Any]] = []
        for entry in _url_entries(batch, limit_per_category):
            preview = service.preview(ProductUrlPreviewRequest(url=str(entry["url"]), region=region, category=category))
            accepted = bool(preview.accepted and preview.currency == "SAR" and preview.region == region)
            item: dict[str, Any] = {
                "url": preview.normalized_url,
                "category": category,
                "accepted": accepted,
                "source_name": preview.source_name,
                "price": preview.price,
                "currency": preview.currency,
                "product_type": preview.product_type,
                "canonical_key": preview.canonical_key,
                "rejected_reasons": preview.rejected_reasons,
                "approved_for_ingest": bool(entry.get("approved")),
                "ingest_status": "not_requested",
            }
            if accepted:
                report["accepted_preview_count"] += 1
            else:
                report["rejected_preview_count"] += 1
            if execute_pricing and accepted and bool(entry.get("approved")):
                ingest = service.ingest(
                    ProductUrlIngestRequest(url=str(entry["url"]), region=region, category=category, approved=True),
                    actor="core500_pricing_runner",
                    role="admin",
                    trace_id="trace-core500-pricing-expansion",
                )
                item["ingest_status"] = ingest.status
                item["price_snapshot_id"] = ingest.price_snapshot_id
                if ingest.status == "ingested":
                    report["ingested_count"] += 1
            elif execute_pricing and not bool(entry.get("approved")):
                item["ingest_status"] = "skipped_unapproved_url"
            items.append(item)
        report["categories"][category] = {
            "url_count": len(items),
            "accepted_preview_count": sum(1 for item in items if item["accepted"]),
            "rejected_preview_count": sum(1 for item in items if not item["accepted"]),
            "items": items,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Core 500 exact-URL pricing expansion with safety gates.")
    parser.add_argument("--url-batch", type=Path, default=DEFAULT_URL_BATCH)
    parser.add_argument("--gpu-exact-fixture", type=Path, default=DEFAULT_GPU_EXACT_FIXTURE)
    parser.add_argument("--category", action="append", choices=PRIORITY_CATEGORIES, help="Category to process; repeatable.")
    parser.add_argument("--limit-per-category", type=int, default=None)
    parser.add_argument("--skip-gpu-exact", action="store_true")
    parser.add_argument("--execute-gpu-exact", action="store_true", help="Execute exact GPU enrichment after a clean dry-run.")
    parser.add_argument("--execute-pricing", action="store_true", help="Ingest accepted and approved exact URLs after preview.")
    args = parser.parse_args()

    payload = _load_json(args.url_batch)
    region = normalize_region(str(payload.get("region") or "SA"))
    batches = _selected_batches(payload, list(args.category or PRIORITY_CATEGORIES))

    manager = Neo4jSessionManager(settings)
    repository = Neo4jPricingRepository(manager.driver)
    url_service = ProductUrlIngestionService(repository)
    try:
        before_counts = _counts(repository)
        gpu_exact: dict[str, Any] | None = None
        if not args.skip_gpu_exact and any(str(batch.get("category")) == "GPU" for batch in batches):
            fixture = _load_gpu_exact_records(args.gpu_exact_fixture)
            dry = repository.enrich_staged_specs(_gpu_exact_request(fixture=fixture, dry_run=True))
            safe_to_execute = dry.conflict_count == 0 and dry.matched_staged_records > 0
            gpu_exact = {
                "dry_run": _summarize_enrichment(dry),
                "safe_to_execute": safe_to_execute,
                "executed": False,
                "execute": None,
            }
            if args.execute_gpu_exact and safe_to_execute:
                executed = repository.enrich_staged_specs(_gpu_exact_request(fixture=fixture, dry_run=False))
                gpu_exact["executed"] = True
                gpu_exact["execute"] = _summarize_enrichment(executed)
            elif args.execute_gpu_exact:
                gpu_exact["execute"] = {"skipped_reason": "dry-run reported conflicts or no exact staged matches"}

        pricing = _preview_and_maybe_ingest_urls(
            service=url_service,
            region=region,
            batches=batches,
            execute_pricing=args.execute_pricing,
            limit_per_category=args.limit_per_category,
        )
        after_counts = _counts(repository)
        integrity = repository.hybrid_graph_integrity(region=region)
        build_service = SaudiLocalBuildService(repository)
        report = {
            "region": region,
            "categories": [str(batch.get("category")) for batch in batches],
            "mode": {
                "gpu_exact_execution": bool(args.execute_gpu_exact),
                "pricing_execution": bool(args.execute_pricing),
            },
            "counts": {"before": before_counts, "after": after_counts},
            "gpu_exact_enrichment": gpu_exact,
            "pricing": pricing,
            "hybrid_integrity": integrity.model_dump(mode="json"),
            "catalog_completeness": build_service.catalog_completeness(region=region).model_dump(mode="json"),
            "build_data_completeness": build_service.data_completeness(region=region).model_dump(mode="json"),
            "notes": [
                "URL preview is always run before ingest.",
                "Pricing ingest requires --execute-pricing and per-URL approved=true.",
                "GPU exact enrichment requires --execute-gpu-exact and a clean dry-run.",
                "No broad scraping is performed by this runner.",
            ],
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        manager.close()


if __name__ == "__main__":
    main()
