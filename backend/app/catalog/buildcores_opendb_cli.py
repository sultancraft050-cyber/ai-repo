from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.database import CatalogDatabase
from app.catalog.models import (
    ImportSource, SourceType, ImageRightsStatus, ImportBatch, ImportRecord,
    ImportValidationStatus, ImportReviewStatus, ImportProposedAction, ImportBatchStatus
)
from app.catalog.import_pipeline import CatalogImportPipeline, stage_result, commit_batch
from app.catalog.buildcores_opendb_adapter import (
    validate_checkout, get_git_revision, parse_opendb_record,
    CATEGORY_LIMITS, CATEGORY_FOLDERS, CategoryStats, has_reliable_identity
)

def verify_db_url():
    url = os.getenv("CATALOG_DATABASE_URL", "")
    if not url:
        raise ValueError("CATALOG_DATABASE_URL is not set.")
    if not url.startswith("sqlite:///"):
        raise ValueError("Only local SQLite database URLs are supported.")
    # Simple check for production DB names
    if "production" in url.lower() or "prod" in url.lower() or "rds" in url.lower() or "@" in url:
        raise ValueError("Production databases are not allowed.")
    return url

def get_session():
    verify_db_url()
    db = CatalogDatabase()
    return db.session()

def cmd_inspect(args):
    source_path = Path(args.source)
    if not validate_checkout(source_path):
        print("ERROR: Invalid BuildCores OpenDB source directory.")
        sys.exit(1)
    
    rev = get_git_revision(source_path)
    print(f"BuildCores OpenDB source directory is valid.")
    print(f"Git Revision: {rev}")
    print(f"Discovered component JSON files:")
    for cat, folder in CATEGORY_FOLDERS.items():
        if cat.upper() not in args.categories:
            continue
        folder_path = source_path / "open-db" / folder
        files = list(folder_path.glob("*.json"))
        print(f"  - {cat}: {len(files)} files discovered")

def run_dry_run_mapping(source_path: Path, categories: list[str], max_total: int) -> tuple[list[dict], list[dict], dict[str, CategoryStats], str]:
    rev = get_git_revision(source_path)
    all_products = []
    all_specs = []
    stats_dict = {}
    
    total_staged = 0
    for cat in categories:
        folder = CATEGORY_FOLDERS.get(cat.upper())
        if not folder:
            continue
        stats = CategoryStats(cat)
        stats_dict[cat] = stats
        
        folder_path = source_path / "open-db" / folder
        files = sorted(list(folder_path.glob("*.json"))) # sorted to be deterministic
        stats.files_discovered = len(files)
        
        limit = min(CATEGORY_LIMITS.get(cat.upper(), 0), max_total - total_staged)
        for filepath in files[:limit]:
            if total_staged >= max_total:
                break
            
            # Verify file is not path traversal or outside open-db/
            if "open-db" not in filepath.parts:
                print(f"ERROR: File {filepath} is outside open-db/ directory.")
                sys.exit(1)
                
            p_payload, specs = parse_opendb_record(filepath, cat, stats)
            if p_payload:
                all_products.append(p_payload)
                all_specs.extend(specs)
                
                # Check validation status
                if has_reliable_identity(p_payload):
                    stats.valid_count += 1
                else:
                    stats.review_required_count += 1
                total_staged += 1
                
    return all_products, all_specs, stats_dict, rev

def cmd_preview(args):
    source_path = Path(args.source)
    if not validate_checkout(source_path):
        print("ERROR: Invalid BuildCores OpenDB source directory.")
        sys.exit(1)
        
    products, specs, stats, rev = run_dry_run_mapping(source_path, args.categories, args.max_total)
    
    print(f"--- BuildCores OpenDB Preview (Dry-Run) ---")
    print(f"Source Git Revision: {rev}")
    print(f"Total Products Parsed: {len(products)}")
    print(f"Total Specifications Mapped: {len(specs)}")
    
    for cat, stat in stats.items():
        print(f"\nCategory: {cat}")
        print(f"  Source files discovered: {stat.files_discovered}")
        print(f"  Records parsed: {stat.records_parsed}")
        print(f"  Valid records: {stat.valid_count}")
        print(f"  Review-required records: {stat.review_required_count}")
        print(f"  Rejected records: {stat.rejected_count}")
        print(f"  Duplicate records: {stat.duplicate_count}")
        print(f"  Missing MPN count: {stat.missing_mpn_count}")
        print(f"  Missing GTIN count: {stat.missing_gtin_count}")
        print(f"  Missing compatibility-field counts: {stat.missing_compatibility_fields}")
        print(f"  Specification keys discovered: {sorted(list(stat.spec_keys_discovered))}")
        print(f"  Unmapped source fields: {dict(stat.unmapped_fields)}")
        print(f"  Controlled-value conflicts: {stat.controlled_value_conflicts}")

def cmd_stage(args):
    if not os.getenv("CATALOG_IMPORT_ENABLED", "").lower() in {"1", "true", "yes"}:
        print("ERROR: CATALOG_IMPORT_ENABLED is not enabled.")
        sys.exit(1)
        
    source_path = Path(args.source)
    if not validate_checkout(source_path):
        print("ERROR: Invalid BuildCores OpenDB source directory.")
        sys.exit(1)
        
    products, specs, stats, rev = run_dry_run_mapping(source_path, args.categories, args.max_total)
    
    session_ctx = get_session()
    with session_ctx as session:
        # Create ImportSource
        now = datetime.now(timezone.utc)
        source_name = f"BuildCores OpenDB (Git: {rev[:8]})"
        source = session.scalar(select(ImportSource).where(ImportSource.name == source_name))
        if not source:
            source = ImportSource(
                name=source_name,
                source_type=SourceType.JSON.value,
                rights_status=ImageRightsStatus.APPROVED.value,
                active=True,
                created_at=now,
                updated_at=now
            )
            session.add(source)
            session.flush()
            
        # Stage Products
        p_json = json.dumps({"records": products})
        pipeline = CatalogImportPipeline(session)
        p_dry = pipeline.dry_run(p_json.encode("utf-8"), file_format="json", entity_type="PRODUCT")
        p_batch = stage_result(session, source, p_dry)
        
        # Stage Specifications
        s_json = json.dumps({"records": specs})
        s_dry = pipeline.dry_run(s_json.encode("utf-8"), file_format="json", entity_type="PRODUCT_SPECIFICATION")
        s_batch = stage_result(session, source, s_dry)
        
        print(f"Staged batches:")
        print(f"  Product Batch ID: {p_batch.id} (Status: {p_batch.status})")
        print(f"  Specification Batch ID: {s_batch.id} (Status: {s_batch.status})")
        session.commit()

def cmd_report(args):
    session_ctx = get_session()
    with session_ctx as session:
        batches = session.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())).all()
        print("--- Staged Batch Reports ---")
        for b in batches:
            print(f"Batch ID: {b.id}")
            print(f"  Source ID: {b.source_id}")
            print(f"  Entity Type: {b.entity_type}")
            print(f"  Status: {b.status}")
            print(f"  Received Count: {b.received_count}")
            print(f"  Accepted Count: {b.accepted_count}")
            print(f"  Staged Count: {b.staged_count}")
            print(f"  Committed Count: {b.committed_count}")
            print(f"  Created At: {b.created_at}")

def cmd_commit_local(args):
    if not os.getenv("CATALOG_IMPORT_ENABLED", "").lower() in {"1", "true", "yes"}:
        print("ERROR: CATALOG_IMPORT_ENABLED is not enabled.")
        sys.exit(1)
    if not os.getenv("CATALOG_WRITES_ENABLED", "").lower() in {"1", "true", "yes"}:
        print("ERROR: CATALOG_WRITES_ENABLED is not enabled.")
        sys.exit(1)
        
    source_path = Path(args.source)
    if not validate_checkout(source_path):
        print("ERROR: Invalid BuildCores OpenDB source directory.")
        sys.exit(1)
        
    products, specs, stats, rev = run_dry_run_mapping(source_path, args.categories, args.max_total)
    
    session_ctx = get_session()
    with session_ctx as session:
        # Create ImportSource
        now = datetime.now(timezone.utc)
        source_name = f"BuildCores OpenDB (Git: {rev[:8]})"
        source = session.scalar(select(ImportSource).where(ImportSource.name == source_name))
        if not source:
            source = ImportSource(
                name=source_name,
                source_type=SourceType.JSON.value,
                rights_status=ImageRightsStatus.APPROVED.value,
                active=True,
                created_at=now,
                updated_at=now
            )
            session.add(source)
            session.flush()
            
        # Stage Products first
        p_json = json.dumps({"records": products})
        pipeline = CatalogImportPipeline(session)
        p_dry = pipeline.dry_run(p_json.encode("utf-8"), file_format="json", entity_type="PRODUCT")
        p_batch = stage_result(session, source, p_dry)
        
        # In order to commit the batch, we must approve the records.
        # We only approve products that have a reliable identity.
        # Products without reliable identity are kept as PENDING (which will block their commit, raising validation error).
        records = session.scalars(select(ImportRecord).where(ImportRecord.batch_id == p_batch.id)).all()
        approved_count = 0
        for r in records:
            payload = json.loads(r.normalized_payload)
            if has_reliable_identity(payload) and r.validation_status == ImportValidationStatus.VALID.value:
                r.review_status = ImportReviewStatus.APPROVED.value
                approved_count += 1
                
        p_batch.status = ImportBatchStatus.READY.value
        session.commit()
        
        # Commit products batch (returns number of committed items)
        committed_products = commit_batch(session, p_batch)
        print(f"Committed {committed_products} products to local SQLite database.")
        
        # Stage Specifications (now that products exist, the specifications will resolve their matched product IDs)
        s_json = json.dumps({"records": specs})
        s_dry = pipeline.dry_run(s_json.encode("utf-8"), file_format="json", entity_type="PRODUCT_SPECIFICATION")
        s_batch = stage_result(session, source, s_dry)
        
        # Approve specifications that belong to valid resolved products
        s_records = session.scalars(select(ImportRecord).where(ImportRecord.batch_id == s_batch.id)).all()
        for r in s_records:
            if r.matched_product_id and r.validation_status == ImportValidationStatus.VALID.value:
                r.review_status = ImportReviewStatus.APPROVED.value
                
        s_batch.status = ImportBatchStatus.READY.value
        session.commit()
        
        # Commit specifications batch
        committed_specs = commit_batch(session, s_batch)
        print(f"Committed {committed_specs} product specifications to local SQLite database.")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BuildCores OpenDB Catalog Bootstrap CLI")
    parser.add_argument("command", choices=["inspect", "preview", "stage", "report", "commit-local"])
    parser.add_argument("--source", required=True, help="Path to the BuildCores OpenDB directory")
    parser.add_argument("--categories", default="CPU,GPU,MOTHERBOARD,RAM,STORAGE,PSU,CASE,COOLER", help="Comma-separated categories to process")
    parser.add_argument("--max-total", type=int, default=300, help="Maximum number of products to process (capped at 300)")
    
    args = parser.parse_args(argv)
    
    # Cap max-total at 300 strictly
    if args.max_total > 300:
        args.max_total = 300
        
    categories = [c.strip().upper() for c in args.categories.split(",")]
    # Filter only supported categories
    supported = {"CPU", "GPU", "MOTHERBOARD", "RAM", "STORAGE", "PSU", "CASE", "COOLER"}
    args.categories = [c for c in categories if c in supported]
    
    # Check if paths are outside source checkout
    if "../" in args.source or "..\\" in args.source:
        print("ERROR: Path traversal is not allowed in --source path.")
        sys.exit(1)
        
    cmds = {
        "inspect": cmd_inspect,
        "preview": cmd_preview,
        "stage": cmd_stage,
        "report": cmd_report,
        "commit-local": cmd_commit_local
    }
    
    cmds[args.command](args)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
