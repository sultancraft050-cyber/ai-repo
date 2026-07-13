# Local Catalog Review and Import Operations Interface

## Purpose

This is a manually started, loopback-only utility for reviewing synthetic catalog fixtures before a future approved import. It is not part of the production FastAPI application.

## Local-only architecture

`python -m app.catalog.ops_server` creates a separate FastAPI application, binds only to `127.0.0.1`, and uses checked-in Alembic migrations against an explicitly local SQLite database. It rejects missing, PostgreSQL, Neo4j, and other non-SQLite URLs. It does not fetch images, call external APIs, scrape sites, or render remote images.

## Feature flags and startup

All catalog flags remain false by default:

```sh
CATALOG_OPS_ENABLED=true \
CATALOG_IMPORT_ENABLED=true \
CATALOG_IMAGE_REVIEW_ENABLED=true \
CATALOG_WRITES_ENABLED=true \
CATALOG_DATABASE_URL=sqlite:////tmp/catalog-ops.sqlite3 \
python -m app.catalog.ops_server
```

The server refuses a non-loopback host. `CATALOG_OPS_PORT` may change the local port. No production flag is changed by this command.

Create a fresh temporary database explicitly with `rm /tmp/catalog-ops.sqlite3` followed by the startup command, or set `CATALOG_OPS_RESET=true` for a deliberate local reset. Existing databases are never erased automatically.

## Synthetic fixtures and pages

Only files under `backend/tests/fixtures/` are accepted. Existing product CSV/JSON and image-metadata review fixtures are supported; arbitrary uploads and real catalog records are not. The dashboard and bounded pages cover batches, staged records, pending image metadata, exact-checksum duplicate groups, products, stores, and offers.

## Review workflow

Dry-run imports normalize fields, validate identities, record safe errors, and stage an append-only batch. Invalid, blocked, ambiguous, malformed-URL, invalid-price, unsupported-category, and unresolved-dependency rows cannot be approved. Valid review-required rows can be approved or rejected; pending rows remain pending.

Batch commit is available only when import and local-write flags are enabled, the database is SQLite, the batch is `READY`, and no invalid, blocked, ambiguous, or pending-review records remain. It uses the existing idempotent commit pipeline, so a repeated commit does not duplicate catalog rows. The UI shows eligibility and a blocked-action explanation before commit.

## Image metadata review

The image queue shows metadata only: dimensions, format, bounded size, rights, quality, provenance, checksum duplicate state, and evaluator reason codes. No `<img>` element is emitted and no source URL is requested. Decisions use the existing image-review service and create append-only audit rows. Primary approval is rejected when eligibility fails or another approved primary is active; rights are not silently approved.

## Duplicate handling and catalog inspection

Exact checksum groups are listed with a shortened identifier, product IDs, same/cross-product classification, and metadata-conflict state. Nothing is deleted automatically. Product, store, and offer pages use deterministic bounded ordering and expose only normalized local catalog fields, including cheapest SAR offer where available.

## Testing, reset, and rollback

Tests cover startup guards, SQLite migration initialization, fixture-path restrictions, dry-run batches, safe review actions, commit eligibility/idempotence, image metadata decisions and audit history, duplicate groups, catalog inspection, accessible labels/tables/forms, and the absence of external requests. Migration upgrade/downgrade is exercised against temporary SQLite. To roll back, stop the local process and remove only the explicitly created temporary SQLite file; production databases, Neo4j, Secret Manager, Cloud Run, and Vercel are untouched.

No SQLite files, imported records, credentials, request headers, or raw production data belong in Git.
