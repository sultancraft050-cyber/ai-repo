# BuildCores OpenDB Import Runbook

This runbook documents how to safely run the bounded BuildCores OpenDB catalog
import into the Cloud SQL staging database.

## Overview

This process imports structured open hardware product metadata from the
**BuildCores OpenDB** repository into the `catalog` PostgreSQL database on
Cloud SQL staging.

**This process must never:**
- Deploy or modify Cloud Run
- Change traffic routing
- Enable the Catalog V2 feature flag in production
- Import prices, retailer offers, images, or 3D assets
- Modify Neo4j
- Access Cloud Storage
- Call external APIs
- Expose secrets

---

## Prerequisites

1. Cloud SQL Auth Proxy running on `127.0.0.1:5433`
2. `catalog-db-password-staging` secret accessible
3. `CATALOG_BUILDCORES_IMPORT_ENABLED=true` explicitly set
4. BuildCores OpenDB cloned at a path outside the main repository
5. Starting commit verified against CI prerequisite
6. Pre-import Cloud SQL backup created and confirmed `SUCCESSFUL`

---

## Phase 1 — Preflight

```bash
cd /path/to/start-clean-project
git status --short
git branch --show-current
git pull --ff-only origin master
git log -5 --oneline
```

Confirm:
- Branch is `master`
- Working tree is clean
- Prior CI passed

---

## Phase 2 — Obtain Source

```bash
# If not already cloned:
git clone https://github.com/buildcores/buildcores-open-db.git \
    /path/to/buildcores-open-db

# Otherwise update:
cd /path/to/buildcores-open-db
git fetch origin
git pull --ff-only origin main
git log -1
```

Record the source commit SHA.

---

## Phase 3 — Create Pre-Import Backup

```bash
gcloud sql backups create \
  --instance=catalog-postgres-staging \
  --description=pre-buildcores-bounded-import-YYYYMMDD \
  --project=pc-recomendation-project

# Wait until SUCCESSFUL:
gcloud sql backups list \
  --instance=catalog-postgres-staging \
  --project=pc-recomendation-project \
  --limit=5
```

Record the backup ID.

---

## Phase 4 — Start Cloud SQL Auth Proxy

```bash
./cloud-sql-proxy \
  --port=5433 \
  pc-recomendation-project:me-central1:catalog-postgres-staging &
```

If ADC is not configured, use:
```bash
./cloud-sql-proxy \
  --port=5433 \
  --gcloud-auth \
  pc-recomendation-project:me-central1:catalog-postgres-staging &
```

---

## Phase 5 — Load Password from Secret Manager

```bash
export CATALOG_DB_PASSWORD=$(gcloud secrets versions access latest \
  --secret=catalog-db-password-staging \
  --project=pc-recomendation-project)
```

**Never print `$CATALOG_DB_PASSWORD`.**

---

## Phase 6 — Run Dry-Run

```bash
cd backend
source .venv/bin/activate

python -m app.catalog.buildcores_import_cli dry-run \
  --source /path/to/buildcores-open-db \
  --limit 300
```

**Stop unless the dry-run reports PASSED.**

Dry-run checks:
- Schema validation
- Category selection counts (≤ 300 total)
- Zero duplicate identities
- Zero price/retailer/image data

---

## Phase 7 — Execute Import

```bash
export CATALOG_BUILDCORES_IMPORT_ENABLED=true
export CATALOG_DB_HOST=127.0.0.1
export CATALOG_DB_PORT=5433
export CATALOG_DB_NAME=catalog
export CATALOG_DB_USER=sultansotb

python -m app.catalog.buildcores_import_cli import \
  --source /path/to/buildcores-open-db \
  --limit 300
```

The import will:
1. Verify `CATALOG_BUILDCORES_IMPORT_ENABLED=true`
2. Verify Alembic revision is `0003_product_image_reviews`
3. Verify host=127.0.0.1, dbname=catalog
4. Create one `ImportSource`
5. Create one `ImportBatch`
6. Stage `ImportRecord` rows
7. Commit `Product` rows (with idempotency check)
8. Commit `ProductSpecification` rows
9. Mark batch `COMPLETED`

---

## Phase 8 — Verify Import

```bash
python -m app.catalog.buildcores_import_cli verify
```

Checks:
- Product counts by category
- Specification counts
- Zero store offers
- Zero price history rows
- Zero product image rows
- Zero duplicate GTIN
- Zero duplicate brand+MPN

---

## Phase 9 — Idempotency Test

```bash
python -m app.catalog.buildcores_import_cli idempotency \
  --source /path/to/buildcores-open-db \
  --limit 300
```

Expected: `IDEMPOTENCY: PASSED — zero new inserts.`

---

## Rollback Procedure

If a rollback is needed:

```bash
# List backups
gcloud sql backups list \
  --instance=catalog-postgres-staging \
  --project=pc-recomendation-project

# Restore from backup ID
gcloud sql backups restore <BACKUP_ID> \
  --restore-instance=catalog-postgres-staging \
  --project=pc-recomendation-project
```

Rollback does **not** affect:
- Neo4j
- Cloud Run
- Cloud Storage
- Other Cloud SQL tables not modified by this import

---

## Safety Assertions

| Check | Expected |
|---|---|
| Cloud Run deployed | NO |
| Traffic changed | NO |
| Neo4j modified | NO |
| Prices imported | NO |
| Images imported | NO |
| Offers imported | NO |
| Cloud Storage written | NO |
| Secrets printed | NO |
| Force-push used | NO |

---

## Contacts

- Cloud SQL instance: `catalog-postgres-staging`
- Project: `pc-recomendation-project`
- Region: `me-central1`
- Connection name: `pc-recomendation-project:me-central1:catalog-postgres-staging`
- Password secret: `catalog-db-password-staging`
