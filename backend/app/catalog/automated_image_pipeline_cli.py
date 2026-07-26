"""
Automated image pipeline CLI.

Usage:
    python -m app.catalog.automated_image_pipeline_cli dry-run [options]
    python -m app.catalog.automated_image_pipeline_cli run [options]

Requires: CATALOG_AUTOMATED_IMAGE_PIPELINE_ENABLED=true

This command is designed to run as a finite Cloud Run Job — it starts,
processes a bounded catalog batch, prints aggregate results, and exits.
Overlapping executions are refused via a database-backed lease.

Credentials never printed to output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
import uuid

from app.catalog.automated_image_pipeline import (
    LEASE_JOB_NAME,
    AutomatedImagePipeline,
    PipelineReport,
    ProductFinalState,
    _acquire_lease,
    _release_lease,
)
from app.catalog.database import CatalogDatabase
from app.catalog.storage import CatalogStorage


def _enabled() -> bool:
    return os.getenv("CATALOG_AUTOMATED_IMAGE_PIPELINE_ENABLED", "false").lower() in {"1", "true", "yes"}


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Automated catalog product image acquisition pipeline."
    )
    p.add_argument("command", choices=("dry-run", "run"))
    p.add_argument("--limit", type=int, default=None, help="Max products to process")
    p.add_argument("--category", default=None, help="Filter to one category (CPU, GPU, ...)")
    p.add_argument("--product-id", type=int, default=None, help="Process a single product by ID")
    p.add_argument("--source", default="icecat", choices=("icecat",), help="Image source(s) to use")
    p.add_argument("--resume", action="store_true", default=True, help="Skip already-approved products (default)")
    p.add_argument("--max-concurrency", type=int, default=4, help="Max concurrent downloads (1-8)")
    p.add_argument("--force-refresh", action="store_true", default=False,
                   help="Re-process products that already have approved images")
    return p


def _print_report(report: PipelineReport, dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "RUN"
    print(f"\n=== Automated Image Pipeline Report ({mode}) ===")
    print(f"Products scanned:              {report.products_scanned}")
    print(f"Icecat exact GTIN matches:     {report.icecat_gtin_matches}")
    print(f"Icecat exact brand+MPN matches:{report.icecat_brand_mpn_matches}")
    print(f"Locked/inaccessible records:   {report.locked_records}")
    print(f"No exact match:                {report.no_exact_match}")
    print(f"Identity conflicts:            {report.identity_conflicts}")
    print(f"Rejected images:               {report.rejected_images}")
    print(f"Retryable failures:            {report.retryable_failures}")
    print(f"Real images approved:          {report.real_images_approved}")
    print(f"Placeholder active:            {report.placeholder_active}")
    if not dry_run:
        print(f"Card variants uploaded:        {report.card_variants_uploaded}")
        print(f"Summary variants uploaded:     {report.summary_variants_uploaded}")
        print(f"Detail variants uploaded:      {report.detail_variants_uploaded}")
    print(f"Coverage:                      {report.coverage_pct}%")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if not _enabled():
        print("ERROR: CATALOG_AUTOMATED_IMAGE_PIPELINE_ENABLED is not set to true.", file=sys.stderr)
        return 2

    icecat_username = os.getenv("ICECAT_USERNAME")
    icecat_configured = bool(icecat_username)
    print(f"Icecat credentials configured: {'YES' if icecat_configured else 'NO (Icecat will be skipped)'}")
    print("Shared/demo credentials used:  NO")

    database = CatalogDatabase()
    storage = CatalogStorage()

    dry_run = args.command == "dry-run"
    token = secrets.token_hex(16)

    with database.session() as session:
        if database.url and database.url.startswith("sqlite"):
            from app.catalog.models import Base
            Base.metadata.create_all(bind=session.get_bind())

        if not dry_run:
            acquired = _acquire_lease(session, token)
            session.commit()
            if not acquired:
                print("ERROR: Another pipeline run is active. Refusing to start (overlapping execution prevented).", file=sys.stderr)
                return 3

        try:
            pipeline = AutomatedImagePipeline(
                session=session,
                storage=storage,
                dry_run=dry_run,
                limit=args.limit,
                category=args.category,
                product_id=args.product_id,
                max_concurrency=args.max_concurrency,
                force_refresh=args.force_refresh,
                resume=args.resume,
            )
            report = pipeline.run()
        finally:
            if not dry_run:
                _release_lease(session, token)
                session.commit()

    _print_report(report, dry_run)

    # Exit nonzero if every product failed
    if report.products_scanned > 0 and report.real_images_approved == 0 and report.placeholder_active == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
