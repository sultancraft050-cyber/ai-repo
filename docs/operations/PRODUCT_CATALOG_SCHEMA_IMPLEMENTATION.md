# Relational Product Catalog Foundation

**Status:** disabled by default; local foundation only

## Responsibilities

Neo4j remains the existing compatibility/readiness graph and is unchanged. Catalog V2 owns canonical products, specifications, approved image metadata, stores, offers, append-only price history, import provenance, batches, and safe import errors. Original/derived image bytes remain a future object-storage concern; this schema stores metadata only.

## Entities and relationships

The initial migration creates `catalog_products`, `catalog_product_specifications`, `catalog_product_images`, `catalog_stores`, `catalog_store_offers`, `catalog_price_history`, `catalog_import_sources`, `catalog_import_batches`, and `catalog_import_errors`. Products have specifications/images/offers; stores have offers; offers have append-only price history; import sources own batches and safe error summaries.

Categories are controlled: CPU, GPU, MOTHERBOARD, RAM, STORAGE, PSU, CASE, COOLER. Product identity is not title-only: normalized brand plus manufacturer part number is constrained, GTIN is nullable/unique when present, and slug is unique.

## Constraints and indexes

- Unique product slug, nullable unique GTIN, normalized-brand/MPN identity, and unique store slug.
- Unique store SKU per store; non-negative prices; sale price cannot exceed regular price.
- One approved primary image per product through a partial unique index; checksum index supports duplicate detection.
- Category and approval indexes; product/store offer, observed-time, price-history offer/time, and import source/status indexes.
- Foreign keys preserve product/specification/image/offer/history and import batch/error ownership.

## Feature flags and disabled production behavior

- `CATALOG_V2_ENABLED=false` by default.
- `CATALOG_WRITES_ENABLED=false` by default; no write route is exposed.
- `CATALOG_DATABASE_URL` is optional. If absent, existing application startup continues normally and Catalog V2 returns a clear unavailable response when enabled.
- The catalog module is lazy: it does not open a connection at application startup.
- Existing product/search/build/readiness/price behavior is unchanged.

## Migration and local test setup

From `backend`, use the repository environment with `alembic upgrade head` and `alembic downgrade base`. The default migration URL is temporary SQLite (`sqlite:///./catalog-local.sqlite3`); PostgreSQL-compatible URLs can be supplied through `CATALOG_DATABASE_URL`. Local database files are ignored and must not be committed.

The migration creates all catalog tables and downgrade drops only those catalog tables. It does not target Neo4j or rename/remove existing application tables. Tests use an in-memory SQLite database and synthetic fixture records only.

## Read-only API routes

When both the feature flag and URL are available:

- `GET /catalog/products` — bounded deterministic pagination, category filter, and bounded search
- `GET /catalog/products/{product_id}` — approved product detail, specifications, approved images, current offers, and cheapest available SAR offer
- `GET /catalog/products/{product_id}/offers` — currently valid offers
- `GET /catalog/products/{product_id}/images` — approved images only
- `GET /catalog/stores` — active stores with bounded pagination

No write endpoint is exposed. Responses preserve store identity, observed timestamps, stock status, and price freshness instead of flattening vendors.

## Synthetic fixtures

Tests create fixture-marked records: two CPUs, two GPUs, one motherboard, one RAM kit, two stores, multiple offers, one approved image metadata row, one pending image row, and multiple price-history entries. No production products, offers, images, or credentials are included, and startup never seeds these fixtures.

## Future import and image steps

The next task is a staged CSV/JSON Product and Store-Offer Import Pipeline. It must validate provenance, identity, rights, review status, and append-only price history before any write is enabled. A later image-storage step may upload reviewed image bytes to approved object storage; this iteration downloads nothing and creates no bucket.

## Rollback and safety

Rollback is `alembic downgrade base` in a local catalog database or reverting the catalog-only application commit. Production flags remain disabled. No Cloud SQL, storage bucket, Secret Manager version, Vercel setting, Cloud Run deployment, Neo4j mutation, real import, or external image download occurred.
