"""BuildCores OpenDB — Cloud SQL bounded import CLI.

Supports:
    dry-run  — scan, validate, select records; no DB writes
    import   — execute real bounded import into Cloud SQL staging

Safety gates:
    - Requires CATALOG_BUILDCORES_IMPORT_ENABLED=true
    - Refuses if DB host is not 127.0.0.1 (proxy-only)
    - Refuses if DB name is not exactly 'catalog'
    - Never prints password / DB URL
    - Never writes prices, images, offers, Neo4j
    - Idempotent: skips existing brand+MPN pairs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.models import (
    ApprovalStatus,
    ImportBatch,
    ImportBatchStatus,
    ImportEntityType,
    ImportError as ImportErrorRow,
    ImportProposedAction,
    ImportRecord,
    ImportReviewStatus,
    ImportSource,
    ImportValidationStatus,
    LifecycleStatus,
    Product,
    ProductSpecification,
    SourceType,
    ImageRightsStatus,
)
from app.catalog.buildcores_opendb_adapter import (
    CATEGORY_FOLDERS,
    CategoryStats,
    get_git_revision,
    has_reliable_identity,
    parse_opendb_record,
    validate_checkout,
)

# Per-category bounded import limits (total <= 300)
IMPORT_CATEGORY_LIMITS: dict[str, int] = {
    "CPU": 40,
    "GPU": 40,
    "MOTHERBOARD": 40,
    "RAM": 40,
    "STORAGE": 40,
    "PSU": 30,
    "CASE": 30,
    "COOLER": 20,
}
IMPORT_TOTAL_LIMIT = 300

# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_password() -> str:
    """Load DB password from environment without printing it."""
    pw = os.environ.get("CATALOG_DB_PASSWORD", "")
    if not pw:
        raise RuntimeError(
            "CATALOG_DB_PASSWORD is not set. "
            "Populate it from Secret Manager before running."
        )
    return pw


def _build_proxy_url(password: str) -> str:
    """Build psycopg2 URL targeting the local Cloud SQL Auth Proxy."""
    import urllib.parse
    user = os.environ.get("CATALOG_DB_USER", "sultansotb")
    dbname = os.environ.get("CATALOG_DB_NAME", "catalog")
    host = os.environ.get("CATALOG_DB_HOST", "127.0.0.1")
    port = int(os.environ.get("CATALOG_DB_PORT", "5433"))
    return (
        f"postgresql+psycopg2://{user}:{urllib.parse.quote_plus(password)}"
        f"@{host}:{port}/{dbname}"
    )


def _verify_connection_safety(url: str) -> None:
    """Refuse if host is not 127.0.0.1 or db name is not 'catalog'."""
    # Parse without printing URL
    host = os.environ.get("CATALOG_DB_HOST", "127.0.0.1")
    dbname = os.environ.get("CATALOG_DB_NAME", "catalog")
    port = int(os.environ.get("CATALOG_DB_PORT", "5433"))

    if host != "127.0.0.1":
        raise RuntimeError(
            f"Safety gate: host must be 127.0.0.1 (Cloud SQL proxy). Got: {host}"
        )
    if dbname != "catalog":
        raise RuntimeError(
            f"Safety gate: database name must be 'catalog'. Got: {dbname}"
        )
    if port not in (5432, 5433):
        raise RuntimeError(
            f"Safety gate: port must be 5432 or 5433 (proxy). Got: {port}"
        )


def _check_alembic_revision(session: Session) -> str:
    """Return the current Alembic head revision from alembic_version table."""
    try:
        row = session.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
        ).fetchone()
        return row[0] if row else "unknown"
    except Exception as exc:
        raise RuntimeError(f"Cannot read Alembic version: {exc}") from exc


def _make_engine(url: str):
    return create_engine(
        url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=20.0,
        pool_pre_ping=True,
    )


# ---------------------------------------------------------------------------
# Slug normalization
# ---------------------------------------------------------------------------

def _normalize_brand(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", brand.lower()).strip()


def _make_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base[:319]


def _make_checksum(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:64]


# ---------------------------------------------------------------------------
# Scan & select
# ---------------------------------------------------------------------------

def scan_source(
    source_path: Path,
    total_limit: int = IMPORT_TOTAL_LIMIT,
) -> tuple[list[dict], list[dict], dict[str, CategoryStats], str]:
    """Scan OpenDB source, apply per-category limits, return selected products+specs."""
    rev = get_git_revision(source_path)
    all_products: list[dict] = []
    all_specs: list[dict] = []
    stats_dict: dict[str, CategoryStats] = {}
    total_staged = 0

    for cat, limit in IMPORT_CATEGORY_LIMITS.items():
        folder_name = CATEGORY_FOLDERS.get(cat)
        if not folder_name:
            continue
        folder_path = source_path / "open-db" / folder_name
        if not folder_path.exists():
            continue

        stats = CategoryStats(cat)
        stats_dict[cat] = stats

        # Deterministic sort by filename
        files = sorted(folder_path.glob("*.json"))
        stats.files_discovered = len(files)

        per_cat_limit = min(limit, total_limit - total_staged)
        if per_cat_limit <= 0:
            break

        for filepath in files:
            if total_staged >= total_limit:
                break
            if len([p for p in all_products if p.get("category") == cat]) >= per_cat_limit:
                break

            # Safety: file must be inside open-db/
            try:
                filepath.relative_to(source_path / "open-db")
            except ValueError:
                print(f"SAFETY: skipping file outside open-db/: {filepath}")
                continue

            p_payload, specs = parse_opendb_record(filepath, cat, stats)
            if p_payload is None:
                continue

            # Reject if no stable identity (brand+mpn required)
            mpn = p_payload.get("manufacturer_part_number", "")
            brand = p_payload.get("brand", "")
            canonical_name = p_payload.get("canonical_name", "")
            # Reject records with no real brand (Unknown fallback) or no real canonical name
            if brand in ("", "Unknown") or canonical_name in ("", "Unknown"):
                stats.review_required_count += 1
                continue
            if not mpn or mpn.strip().lower() == brand.strip().lower():
                stats.review_required_count += 1
                continue

            # Attach provenance
            rel_path = str(filepath.relative_to(source_path))
            p_payload["_opendb_source_commit"] = rev
            p_payload["_opendb_rel_path"] = rel_path
            p_payload["normalized_brand"] = _normalize_brand(brand)
            if not p_payload.get("slug"):
                p_payload["slug"] = _make_slug(p_payload.get("canonical_name", "unknown"))

            # Safety: no prices, offers, images
            for bad_key in (
                "price", "regular_price", "sale_price", "currency",
                "store_sku", "product_url", "source_url", "storage_key",
                "image", "image_url",
            ):
                p_payload.pop(bad_key, None)

            all_products.append(p_payload)
            for sp in specs:
                sp["_opendb_source_commit"] = rev
            all_specs.extend(specs)

            stats.valid_count += 1
            total_staged += 1

    return all_products, all_specs, stats_dict, rev


# ---------------------------------------------------------------------------
# Dry-run command
# ---------------------------------------------------------------------------

def cmd_dry_run(args) -> int:
    source_path = Path(args.source)
    if not validate_checkout(source_path):
        print("ERROR: Invalid BuildCores OpenDB source directory.")
        return 1

    total_limit = min(args.limit, IMPORT_TOTAL_LIMIT)
    products, specs, stats_dict, rev = scan_source(source_path, total_limit)

    # Duplicate identity check (within selected set)
    seen_brand_mpn: set[tuple[str, str]] = set()
    duplicates = 0
    for p in products:
        key = (_normalize_brand(p.get("brand", "")), p.get("manufacturer_part_number", "").lower())
        if key in seen_brand_mpn:
            duplicates += 1
        seen_brand_mpn.add(key)

    # Safety assertions
    has_price = any(
        "price" in p or "currency" in p or "store_sku" in p or "image" in p
        for p in products
    )
    has_price_in_specs = any(
        "price" in sp or "currency" in sp
        for sp in specs
    )

    print("=" * 60)
    print("BuildCores OpenDB DRY-RUN Report")
    print("=" * 60)
    print(f"OpenDB source commit : {rev}")
    print(f"Categories scanned   : {', '.join(stats_dict.keys())}")
    total_files = sum(s.files_discovered for s in stats_dict.values())
    total_parsed = sum(s.records_parsed for s in stats_dict.values())
    print(f"Files discovered     : {total_files}")
    print(f"Records parsed       : {total_parsed}")
    print(f"Records selected     : {len(products)}")
    print(f"Specifications mapped: {len(specs)}")
    print(f"Duplicate identities : {duplicates}")
    print(f"Price/offer/image data included: {'YES — ABORT' if (has_price or has_price_in_specs) else 'NO'}")
    print()
    for cat, stat in stats_dict.items():
        selected = len([p for p in products if p.get("category") == cat])
        print(f"  {cat}: {stat.files_discovered} files, {stat.records_parsed} parsed, "
              f"{selected} selected, {stat.review_required_count} review-required, "
              f"{stat.rejected_count} rejected")

    # Stop conditions
    if has_price or has_price_in_specs:
        print("ABORT: Price or retailer data found in payload. This must never happen.")
        return 1
    if len(products) == 0:
        print("ABORT: No records selected.")
        return 1
    if len(products) > IMPORT_TOTAL_LIMIT:
        print(f"ABORT: Selected {len(products)} > {IMPORT_TOTAL_LIMIT} limit.")
        return 1
    if duplicates > 0:
        print(f"ABORT: {duplicates} duplicate identities in selected set.")
        return 1

    print()
    print("DRY-RUN PASSED — safe to proceed with real import.")
    return 0


# ---------------------------------------------------------------------------
# Import command
# ---------------------------------------------------------------------------

def cmd_import(args) -> int:
    # Safety gate 1: explicit flag
    enabled = os.environ.get("CATALOG_BUILDCORES_IMPORT_ENABLED", "").lower()
    if enabled not in {"1", "true", "yes"}:
        print(
            "ERROR: CATALOG_BUILDCORES_IMPORT_ENABLED is not set to true.\n"
            "Set it explicitly before running a real import."
        )
        return 1

    source_path = Path(args.source)
    if not validate_checkout(source_path):
        print("ERROR: Invalid BuildCores OpenDB source directory.")
        return 1

    total_limit = min(args.limit, IMPORT_TOTAL_LIMIT)

    # Run dry-run first
    products, specs, stats_dict, rev = scan_source(source_path, total_limit)

    has_price = any(
        "price" in p or "currency" in p or "store_sku" in p or "image" in p
        for p in products
    )
    if has_price:
        print("ABORT: Price or retailer data detected in payload.")
        return 1
    if not products:
        print("ABORT: No records selected after scanning.")
        return 1

    # Safety gate 2: connection safety
    password = _get_password()
    url = _build_proxy_url(password)
    _verify_connection_safety(url)

    engine = _make_engine(url)

    with sessionmaker(engine)() as session:
        # Safety gate 3: verify Alembic revision
        revision = _check_alembic_revision(session)
        if "0003" not in revision:
            print(
                f"ERROR: Expected Alembic revision 0003_product_image_reviews, "
                f"got: {revision}"
            )
            return 1
        print(f"Alembic revision verified: {revision}")

        # Safety gate 4: verify source commit is recorded
        if not rev or rev == "unknown":
            print("ERROR: Could not determine OpenDB source commit.")
            return 1

        now = datetime.now(timezone.utc)
        source_name = f"BuildCores OpenDB (commit: {rev})"

        # --- Create or retrieve ImportSource ---
        import_source = session.scalar(
            select(ImportSource).where(ImportSource.name == source_name)
        )
        if not import_source:
            import_source = ImportSource(
                name=source_name,
                source_type=SourceType.JSON,
                rights_status=ImageRightsStatus.APPROVED,
                active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(import_source)
            session.flush()
        print(f"ImportSource ID: {import_source.id} — {source_name}")

        # --- Create ImportBatch ---
        batch = ImportBatch(
            source_id=import_source.id,
            entity_type=ImportEntityType.PRODUCT.value,
            status=ImportBatchStatus.PARSING,
            received_count=len(products),
            accepted_count=0,
            rejected_count=0,
            duplicate_count=0,
            ambiguous_count=0,
            staged_count=0,
            committed_count=0,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(batch)
        session.flush()
        print(f"ImportBatch ID: {batch.id}")

        # --- Stage ImportRecords ---
        accepted_products: list[dict] = []
        accepted_specs: list[dict] = []
        errors = 0
        skipped_existing = 0
        claimed_slugs: set[str] = set()  # track slugs assigned in this batch (not yet in DB)

        for row_num, p in enumerate(products, start=1):
            brand = p.get("brand", "")
            mpn = p.get("manufacturer_part_number", "")
            norm_brand = _normalize_brand(brand)
            category = p.get("category", "")
            canonical_name = p.get("canonical_name", "")

            # Check for existing product (idempotency)
            existing = session.scalar(
                select(Product).where(
                    Product.normalized_brand == norm_brand,
                    Product.manufacturer_part_number == mpn,
                )
            )
            if existing:
                skipped_existing += 1
                batch.duplicate_count += 1
                # Record as ImportRecord with DUPLICATE status
                checksum = _make_checksum({"brand": brand, "mpn": mpn})
                rec = ImportRecord(
                    batch_id=batch.id,
                    row_number=row_num,
                    entity_type=ImportEntityType.PRODUCT.value,
                    record_checksum=checksum,
                    normalized_payload=json.dumps({
                        "brand": brand,
                        "manufacturer_part_number": mpn,
                        "canonical_name": canonical_name,
                    }),
                    validation_status=ImportValidationStatus.DUPLICATE.value,
                    review_status=ImportReviewStatus.NOT_REQUIRED.value,
                    proposed_action=ImportProposedAction.SKIP.value,
                    matched_product_id=existing.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(rec)
                continue

            # Build slug — ensure uniqueness against DB AND within current batch
            slug = _make_slug(canonical_name)
            slug_candidate = slug
            slug_suffix = 0
            while True:
                in_batch = slug_candidate in claimed_slugs
                slug_clash = in_batch or bool(session.scalar(
                    select(Product).where(Product.slug == slug_candidate)
                ))
                if not slug_clash:
                    break
                slug_suffix += 1
                slug_candidate = f"{slug}-{slug_suffix}"
            slug = slug_candidate
            claimed_slugs.add(slug)

            # Validate category enum
            from app.catalog.models import ProductCategory
            try:
                cat_enum = ProductCategory(category)
            except ValueError:
                errors += 1
                batch.rejected_count += 1
                err = ImportErrorRow(
                    batch_id=batch.id,
                    row_number=row_num,
                    error_code="INVALID_CATEGORY",
                    safe_message=f"Unknown category: {category!r}",
                    created_at=now,
                )
                session.add(err)
                continue

            # Create ImportRecord (staged)
            safe_payload = {
                "brand": brand,
                "manufacturer_part_number": mpn,
                "canonical_name": canonical_name,
                "category": category,
                "slug": slug,
                "opendb_source_commit": p.get("_opendb_source_commit", rev),
                "opendb_rel_path": p.get("_opendb_rel_path", ""),
            }
            checksum = _make_checksum(safe_payload)
            rec = ImportRecord(
                batch_id=batch.id,
                row_number=row_num,
                entity_type=ImportEntityType.PRODUCT.value,
                record_checksum=checksum,
                normalized_payload=json.dumps(safe_payload),
                validation_status=ImportValidationStatus.VALID.value,
                review_status=ImportReviewStatus.NOT_REQUIRED.value,
                proposed_action=ImportProposedAction.CREATE.value,
                created_at=now,
                updated_at=now,
            )
            session.add(rec)
            batch.staged_count += 1

            accepted_products.append({
                **p,
                "slug": slug,
                "normalized_brand": norm_brand,
            })
            # Collect specs associated with this product
            p_specs = [
                sp for sp in specs
                if sp.get("brand") == brand
                and sp.get("manufacturer_part_number") == mpn
            ]
            accepted_specs.extend(p_specs)

        batch.status = ImportBatchStatus.STAGED
        session.flush()

        # --- Commit Product rows ---
        batch.status = ImportBatchStatus.COMMITTING
        session.flush()

        inserted_products = 0
        inserted_specs = 0

        for p in accepted_products:
            brand = p["brand"]
            mpn = p["manufacturer_part_number"]
            norm_brand = _normalize_brand(brand)

            # Final idempotency check before insert
            already = session.scalar(
                select(Product).where(
                    Product.normalized_brand == norm_brand,
                    Product.manufacturer_part_number == mpn,
                )
            )
            if already:
                continue

            from app.catalog.models import ProductCategory as PC
            product = Product(
                category=PC(p["category"]),
                brand=brand,
                normalized_brand=norm_brand,
                manufacturer_part_number=mpn,
                gtin=p.get("gtin"),
                exact_model=p.get("exact_model"),
                variant=p.get("variant"),
                canonical_name=p["canonical_name"],
                slug=p["slug"],
                lifecycle_status=LifecycleStatus.ACTIVE,
                approval_status=ApprovalStatus.PENDING,
                created_at=now,
                updated_at=now,
            )
            session.add(product)
            session.flush()
            inserted_products += 1

            # Insert specifications
            p_specs = [
                sp for sp in accepted_specs
                if sp.get("brand") == brand
                and sp.get("manufacturer_part_number") == mpn
            ]
            for sp in p_specs:
                # Skip if spec key already exists for this product
                existing_spec = session.scalar(
                    select(ProductSpecification).where(
                        ProductSpecification.product_id == product.id,
                        ProductSpecification.specification_key == sp["specification_key"],
                    )
                )
                if existing_spec:
                    continue
                spec_row = ProductSpecification(
                    product_id=product.id,
                    specification_key=sp["specification_key"],
                    normalized_value=str(sp["normalized_value"]),
                    display_value=str(sp["display_value"]),
                    unit=sp.get("unit"),
                    source_id=import_source.id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(spec_row)
                inserted_specs += 1

        # Update batch final status
        batch.accepted_count = inserted_products
        batch.committed_count = inserted_products
        batch.completed_at = datetime.now(timezone.utc)
        batch.status = ImportBatchStatus.COMPLETED
        batch.updated_at = datetime.now(timezone.utc)
        session.commit()

        # Capture IDs as plain ints before the session context manager exits
        _source_id: int = import_source.id
        _batch_id: int = batch.id

    print()
    print("=" * 60)
    print("BuildCores OpenDB IMPORT Complete")
    print("=" * 60)
    print(f"OpenDB source commit : {rev}")
    print(f"ImportSource ID      : {_source_id}")
    print(f"ImportBatch ID       : {_batch_id}")
    print(f"Products inserted    : {inserted_products}")
    print(f"Specs inserted       : {inserted_specs}")
    print(f"Skipped (existing)   : {skipped_existing}")
    print(f"Errors               : {errors}")
    print()
    print("Safety verification:")
    print("  Prices imported: NO")
    print("  Offers imported: NO")
    print("  Images imported: NO")
    print("  Neo4j modified:  NO")
    print("  Cloud Storage:   NOT ACCESSED")
    return 0


# ---------------------------------------------------------------------------
# Idempotency dry-run (re-scan, check no new inserts would occur)
# ---------------------------------------------------------------------------

def cmd_idempotency(args) -> int:
    """Verify that re-running the import produces zero new inserts."""
    enabled = os.environ.get("CATALOG_BUILDCORES_IMPORT_ENABLED", "").lower()
    if enabled not in {"1", "true", "yes"}:
        print("ERROR: CATALOG_BUILDCORES_IMPORT_ENABLED is not set to true.")
        return 1

    source_path = Path(args.source)
    if not validate_checkout(source_path):
        print("ERROR: Invalid BuildCores OpenDB source directory.")
        return 1

    total_limit = min(args.limit, IMPORT_TOTAL_LIMIT)
    products, _, stats_dict, rev = scan_source(source_path, total_limit)

    password = _get_password()
    url = _build_proxy_url(password)
    _verify_connection_safety(url)
    engine = _make_engine(url)

    would_insert = 0
    would_skip = 0

    with sessionmaker(engine)() as session:
        for p in products:
            norm_brand = _normalize_brand(p.get("brand", ""))
            mpn = p.get("manufacturer_part_number", "")
            existing = session.scalar(
                select(Product).where(
                    Product.normalized_brand == norm_brand,
                    Product.manufacturer_part_number == mpn,
                )
            )
            if existing:
                would_skip += 1
            else:
                would_insert += 1

    print("=" * 60)
    print("Idempotency Check Report")
    print("=" * 60)
    print(f"Records scanned  : {len(products)}")
    print(f"Would insert     : {would_insert}  (must be 0 after first import)")
    print(f"Would skip       : {would_skip}")
    if would_insert == 0:
        print("IDEMPOTENCY: PASSED — zero new inserts.")
        return 0
    else:
        print(f"IDEMPOTENCY: FAILED — {would_insert} records would be inserted again.")
        return 1


# ---------------------------------------------------------------------------
# Verify command (read-only post-import checks)
# ---------------------------------------------------------------------------

def cmd_verify(args) -> int:
    password = _get_password()
    url = _build_proxy_url(password)
    _verify_connection_safety(url)
    engine = _make_engine(url)

    with sessionmaker(engine)() as session:
        from sqlalchemy import func
        from app.catalog.models import StoreOffer, PriceHistory, ProductImage

        # Product counts by category
        from sqlalchemy import case
        rows = session.execute(
            select(Product.category, func.count(Product.id))
            .group_by(Product.category)
        ).all()
        total_products = sum(c for _, c in rows)
        print("=" * 60)
        print("Post-Import Verification Report")
        print("=" * 60)
        print(f"Total products in catalog: {total_products}")
        print("  By category:")
        for cat, cnt in sorted(rows, key=lambda x: x[0]):
            print(f"    {cat}: {cnt}")

        # Spec counts
        spec_count = session.scalar(select(func.count(ProductSpecification.id)))
        print(f"Total specifications    : {spec_count}")

        # Safety: no offers, prices, images
        offer_count = session.scalar(select(func.count(StoreOffer.id)))
        price_count = session.scalar(select(func.count(PriceHistory.id)))
        image_count = session.scalar(select(func.count(ProductImage.id)))
        print(f"Store offers            : {offer_count}")
        print(f"Price history rows      : {price_count}")
        print(f"Product image rows      : {image_count}")

        # Duplicate GTIN check
        from sqlalchemy import distinct
        gtin_dupes = session.execute(
            select(Product.gtin, func.count(Product.id))
            .where(Product.gtin.is_not(None))
            .group_by(Product.gtin)
            .having(func.count(Product.id) > 1)
        ).all()
        print(f"Duplicate GTINs         : {len(gtin_dupes)}")

        # Duplicate brand+MPN check
        brand_mpn_dupes = session.execute(
            select(Product.normalized_brand, Product.manufacturer_part_number, func.count(Product.id))
            .group_by(Product.normalized_brand, Product.manufacturer_part_number)
            .having(func.count(Product.id) > 1)
        ).all()
        print(f"Duplicate brand+MPN     : {len(brand_mpn_dupes)}")

        # Sample read checks
        cpu_sample = session.scalars(
            select(Product).where(Product.category == "CPU").limit(3)
        ).all()
        print(f"CPU sample reads        : {len(cpu_sample)} records retrieved")

        gpu_sample = session.scalars(
            select(Product).where(Product.category == "GPU").limit(3)
        ).all()
        print(f"GPU sample reads        : {len(gpu_sample)} records retrieved")

        # Pagination check
        page1 = session.scalars(select(Product).order_by(Product.id).limit(10)).all()
        page2 = session.scalars(select(Product).order_by(Product.id).offset(10).limit(10)).all()
        print(f"Pagination check        : page1={len(page1)}, page2={len(page2)}")

        # Provenance check
        products_without_source = session.scalars(
            select(Product).where(
                ~select(ProductSpecification.product_id)
                .where(ProductSpecification.source_id.is_not(None))
                .where(ProductSpecification.product_id == Product.id)
                .correlate(Product)
                .exists()
            )
        ).all()
        # This is expected when products have 0 specs — just report
        print(f"Products without any spec+source_id: {len(products_without_source)}")

        print()
        issues = []
        if offer_count and offer_count > 0:
            issues.append(f"Unexpected store offers: {offer_count}")
        if price_count and price_count > 0:
            issues.append(f"Unexpected price history: {price_count}")
        if image_count and image_count > 0:
            issues.append(f"Unexpected product images: {image_count}")
        if gtin_dupes:
            issues.append(f"Duplicate GTINs: {gtin_dupes}")
        if brand_mpn_dupes:
            issues.append(f"Duplicate brand+MPN: {brand_mpn_dupes}")

        if issues:
            print("VERIFICATION FAILED:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        print("VERIFICATION PASSED.")
        return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BuildCores OpenDB Cloud SQL import CLI"
    )
    sub = parser.add_subparsers(dest="command")

    def _add_source(p):
        p.add_argument("--source", required=True, help="Path to buildcores-open-db checkout")
        p.add_argument("--limit", type=int, default=300, help="Max products (hard-capped at 300)")

    dr = sub.add_parser("dry-run", help="Scan and validate without writing to DB")
    _add_source(dr)

    imp = sub.add_parser("import", help="Execute real import into Cloud SQL")
    _add_source(imp)

    idem = sub.add_parser("idempotency", help="Verify no duplicate inserts would occur")
    _add_source(idem)

    ver = sub.add_parser("verify", help="Read-only post-import verification")
    ver.add_argument("--source", required=False, default="", help="Unused (kept for consistency)")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "dry-run":
        return cmd_dry_run(args)
    elif args.command == "import":
        return cmd_import(args)
    elif args.command == "idempotency":
        return cmd_idempotency(args)
    elif args.command == "verify":
        return cmd_verify(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
