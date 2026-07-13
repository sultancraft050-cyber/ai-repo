# Product Catalog Import Pipeline

**Status:** local staging only; disabled by default

## Supported input

The internal pipeline accepts bounded UTF-8 CSV, a JSON array, or a JSON object whose only top-level field is `records`. Every batch declares exactly one entity type: `PRODUCT`, `PRODUCT_SPECIFICATION`, `PRODUCT_IMAGE_METADATA`, `STORE`, `STORE_OFFER`, or `PRICE_OBSERVATION`. It rejects malformed input, nested values, unsupported formats and encodings, unknown fields, and configured file, row, field, per-product specification, and per-product offer limits.

The conservative defaults are a 1 MiB file, 1,000 rows, 1,000 characters per field, 100 specifications per product, 100 offers per product, and 100 retained safe errors. Environment overrides use `CATALOG_IMPORT_MAX_FILE_SIZE`, `CATALOG_IMPORT_MAX_ROWS`, `CATALOG_IMPORT_MAX_FIELD_LENGTH`, `CATALOG_IMPORT_MAX_SPECIFICATIONS`, `CATALOG_IMPORT_MAX_OFFERS`, and `CATALOG_IMPORT_MAX_ERRORS`.

## Workflow and staging

The explicit sequence is receive, parse, normalize, validate, match identity, detect duplicates, stage, review, report a dry-run summary, and—only after all gates—commit to a local SQLite catalog. `catalog_import_records` holds only allow-listed normalized catalog fields, a deterministic checksum, controlled validation/review/action states, nullable resolved IDs, and short safe errors. It never holds raw files, credentials, headers, cookies, or tokens.

Batch lifecycle values are `received`, `parsing`, `validating`, `staged`, `review_required`, `ready`, `committing`, `completed`, `completed_with_errors`, `failed`, and `canceled`. Counts cover received, accepted, rejected, duplicate, ambiguous, staged, and committed records. Pending or blocked rows prevent `ready`.

Validation states are `VALID`, `INVALID`, `DUPLICATE`, `AMBIGUOUS`, and `BLOCKED`; review states are `PENDING`, `APPROVED`, `REJECTED`, and `NOT_REQUIRED`; proposed actions are `CREATE`, `UPDATE`, `SKIP`, `REVIEW`, and `REJECT`. Invalid records are retained as safe staging outcomes and never silently discarded.

## Identity, duplicates, and review

- Products match in strict order by normalized GTIN, normalized brand plus manufacturer part number, then an explicit valid product ID. Titles are never identities and fuzzy merges are prohibited.
- Stores match by explicit ID, normalized slug, then normalized exact name plus country. Country is required; this pipeline does not silently default it.
- Offers require resolved product and store identities plus store SKU. An existing store/SKU proposes update only for the same product; a conflict is ambiguous.
- Specifications and image metadata require an existing product. Price observations require an existing offer and remain append-only.
- Exact batch/catalog duplicates propose `SKIP`. Conflicting product, store, specification, offer, or primary-image identities propose `REVIEW` and cannot commit.
- Image imports store metadata only. They do not download or inspect remote content. Unknown or pending rights require review, duplicate checksums skip, and an approved-primary conflict requires review.
- Older prices may append history but do not replace current offer state. Negative prices, unsupported currency, bad URLs, and invalid timestamps are rejected.

Dependency-safe import order is stores, products, specifications, image metadata, offers, then price observations. Unresolved dependencies are blocked; placeholders are not created.

## Feature flags and dry run

All defaults remain safe-off:

```text
CATALOG_V2_ENABLED=false
CATALOG_IMPORT_ENABLED=false
CATALOG_WRITES_ENABLED=false
```

No import starts with the application. Missing `CATALOG_DATABASE_URL` does not affect startup. Dry run requires `CATALOG_IMPORT_ENABLED=true`; canonical commit additionally requires `CATALOG_WRITES_ENABLED=true`, a `READY` batch, approved/not-required rows, and a local SQLite session. There is no Catalog V2 public write route.

After applying migrations to a disposable local SQLite database, a synthetic fixture can be staged from `backend`:

```bash
CATALOG_IMPORT_ENABLED=true \
CATALOG_DATABASE_URL=sqlite:////tmp/catalog-import.sqlite3 \
python -m app.catalog.import_cli \
  --file tests/fixtures/catalog_import/valid_products.csv \
  --entity-type PRODUCT \
  --source synthetic-fixture \
  --dry-run
```

The CLI refuses a non-SQLite URL and prints only the batch ID, lifecycle status, and aggregate counts. It does not print normalized rows.

## Commit safeguards and safe errors

The internal commit operation checks both flags, local SQLite, `READY`, every review state, and every validation state. It runs one transaction, marks a failure clearly after rollback, appends offer price changes and price observations to history, and treats completed batches as idempotent. It is not connected to an HTTP route.

Persisted errors include only row number, entity type through the staged record, a stable code, and a short message. Codes cover malformed/unsupported input, required fields, categories, GTINs, currency, price, timestamps, URLs, unresolved identities, ambiguous identities, duplicates, image rights, and primary-image conflicts.

## Synthetic validation and rollback

Fixtures under `backend/tests/fixtures/catalog_import/` use only names beginning with “Synthetic Fixture” and reserved `.invalid` URLs. Tests also construct synthetic stores, offers, specifications, image metadata, conflicting identities, invalid prices, and duplicate observations in ephemeral in-memory SQLite databases. No real retailer or product record is present.

Local validation is:

```bash
cd backend
python -m pytest tests/test_catalog_import_pipeline.py -q
python -m pytest -q
CATALOG_DATABASE_URL=sqlite:////tmp/catalog-import.sqlite3 alembic upgrade head
CATALOG_DATABASE_URL=sqlite:////tmp/catalog-import.sqlite3 alembic downgrade base
cd ..
npm run test:release
git diff --check
```

Rollback is `alembic downgrade 0001_catalog_foundation` for the staging migration in a local test database, followed by reverting this focused commit. Production flags remain false. This iteration contacted no production PostgreSQL database, imported no production records, downloaded no images, mutated no Neo4j data, created no cloud resource, changed no secret, and performed no deployment.
