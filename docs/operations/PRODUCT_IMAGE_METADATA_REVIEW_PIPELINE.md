# Product Image Metadata Quality and Review Pipeline

**Status:** local metadata-only workflow; disabled by default

## Scope and safety

This workflow evaluates only metadata already present in `catalog_product_images` or synthetic fixtures. It never fetches a URL, follows a redirect, reads remote headers or EXIF, downloads or transforms bytes, calculates visual sharpness/perceptual hashes, generates thumbnails, or stores image files. No external host, retailer API, production PostgreSQL database, Neo4j graph, storage bucket, Secret Manager value, or deployment is used.

Safe defaults remain:

```text
CATALOG_V2_ENABLED=false
CATALOG_IMPORT_ENABLED=false
CATALOG_WRITES_ENABLED=false
CATALOG_IMAGE_REVIEW_ENABLED=false
PRICING_SCHEDULER_ENABLED=false
AUTONOMOUS_AGENTS_ENABLED=false
CPU_SPECS_SEED_ON_START=false
```

Evaluation requires `CATALOG_IMAGE_REVIEW_ENABLED=true`. Decisions additionally require `CATALOG_WRITES_ENABLED=true`. Nothing runs at application startup and a missing `CATALOG_DATABASE_URL` does not affect existing startup.

## URL, source, and rights policy

Root-relative local references are accepted when already supported by the catalog/frontend. External URLs must be HTTPS, have a host, contain no credentials or control characters, and be no longer than 2,048 characters. HTTP is rejected unless the explicit local `CATALOG_IMAGE_ALLOW_HTTP=true` override is set. External hosts must exactly match `CATALOG_IMAGE_ALLOWED_HOSTS`; an empty allowlist rejects all external hosts and wildcards are not interpreted.

Controlled source types are `MANUFACTURER`, `AUTHORIZED_DISTRIBUTOR`, `AUTHORIZED_RETAILER`, `PARTNER_FEED`, `MANUAL_UPLOAD`, `SYNTHETIC_FIXTURE`, and `UNKNOWN`. Source type does not grant rights. Rights are `APPROVED`, `PENDING`, `REJECTED`, `UNKNOWN`, and `EXPIRED`; only approved rights can become publicly eligible.

## Quality evaluation

The deterministic evaluator returns image/product IDs, URL and host-policy results, rights, dimensions, aspect ratio, format, file size, checksum, duplicate, category suitability, primary conflict, and recommended action. Classifications are `ACCEPTABLE`, `REVIEW_REQUIRED`, `REJECTED`, and `UNKNOWN` (unknown inputs resolve to review). Supported metadata formats are JPEG/JPG, PNG, WEBP, and AVIF; file contents are never inspected.

Defaults are minimum 320×240, maximum 4096×4096, maximum metadata file size 5,000,000 bytes, aspect ratio 0.5–4.0, verification freshness 180 days, and 12 images per product. All thresholds are bounded and configurable through the `CATALOG_IMAGE_*` variables in `backend/.env.example`.

Category heuristics are metadata-only: very wide GPUs may pass, tall CASE images may pass, portrait CPU/RAM/STORAGE images require review, and unknown categories require review. Missing dimensions, unsupported format, missing checksum, stale verification, and unknown source provenance never claim visual quality.

Stable reason codes include `URL_INVALID`, `HOST_NOT_APPROVED`, `RIGHTS_PENDING`, `RIGHTS_REJECTED`, `RIGHTS_EXPIRED`, `DIMENSIONS_MISSING`, `DIMENSIONS_TOO_SMALL`, `DIMENSIONS_TOO_LARGE`, `ASPECT_RATIO_REVIEW`, `FORMAT_UNSUPPORTED`, `FILE_SIZE_EXCEEDED`, `CHECKSUM_MISSING`, `DUPLICATE_SAME_PRODUCT`, `DUPLICATE_CROSS_PRODUCT`, `DUPLICATE_URL`, `METADATA_CONFLICT`, `CATEGORY_UNKNOWN`, `PRIMARY_CONFLICT`, `VERIFICATION_STALE`, `SOURCE_UNKNOWN`, `MAX_IMAGES_PER_PRODUCT`, and `ACCEPTABLE_METADATA`.

## Duplicates and primary safeguards

Duplicate detection is exact checksum and exact source URL only. Same-product checksum duplicates can be skipped by the import pipeline; cross-product checksums, conflicting dimensions/format, and duplicate URLs remain review outcomes. Nothing is deleted automatically and perceptual/fuzzy matching is not used.

An image can be primary only when its URL/host policy, approved rights, approved review, acceptable quality, dimensions, supported format, checksum, freshness, product identity, and duplicate checks all pass. A second approved primary never silently demotes the existing one. `APPROVE_PRIMARY` is an explicit guarded transaction that records the replacement audit and atomically changes the primary flags. Pending, rejected, expired, unknown-rights, and duplicate-conflicted images cannot be primary.

## Review audit history

Migration `0003_product_image_reviews` adds `catalog_product_image_reviews` with image foreign key, decision, stable reason code, bounded safe reason, non-secret reviewer identifier, prior/new rights/quality/review statuses, proposed-primary flag, and creation time. Indexes support image, decision, and chronological lookups. Decisions are append-only; no earlier audit row is edited or deleted. Reviewer emails, credentials, tokens, legal documents, and raw records are not stored.

Decisions are `APPROVE`, `REJECT`, `REQUEST_CHANGES`, `MARK_DUPLICATE`, `APPROVE_PRIMARY`, `REMOVE_PRIMARY`, and `EXPIRE_RIGHTS`. Approval cannot bypass failed metadata checks or invent rights. Review history is internal and is not exposed by public catalog responses.

## Public visibility and import integration

When image review is enabled, the existing read-only Catalog V2 image route returns only approved products with approved rights, approved review, acceptable quality, valid local/approved-host URL, and no unresolved duplicate conflict. Pending, rejected, expired, unknown-rights, unacceptable-quality, and internal audit fields remain excluded. When the flag is disabled, existing read-only behavior is preserved.

`PRODUCT_IMAGE_METADATA` staging invokes the evaluator only when image review is enabled. Failed URL/dimension/rights checks reject or review safely; pending rights, stale metadata, duplicate conflicts, and primary conflicts cannot become public; no image is downloaded. Existing import flags and commit safeguards remain unchanged.

## Internal CLI

After local migrations, use only a disposable SQLite database:

```bash
CATALOG_IMAGE_REVIEW_ENABLED=true \
CATALOG_DATABASE_URL=sqlite:////tmp/catalog-image-review.sqlite3 \
python -m app.catalog.image_review_cli evaluate-product --product-id 1
```

The CLI also supports `evaluate-image`, `list-pending`, `list-duplicates`, `show-history`, and guarded `decide`. Decision commands require both review and catalog-write flags, a local SQLite URL, explicit bounded reason/reviewer fields, and print no credentials or complete records. No web admin panel or public write endpoint was added.

## Synthetic validation and rollback

Synthetic tests cover approved manufacturer-style/partner-feed metadata, pending/rejected/expired rights, malformed and unapproved URLs, dimensions, sizes, formats, checksums, stale verification, GPU/case/category heuristics, same/cross-product duplicates, conflicting metadata, primary replacement, visibility, import integration, audit ordering, and feature gates. Fixture names and URLs are synthetic or reserved `.invalid` values; no real retailer/manufacturer URL is present.

Validate with focused image-review tests, catalog foundation/import tests, the full backend suite, temporary SQLite Alembic upgrade/downgrade, `npm run test:release`, and `git diff --check`. Rollback is `alembic downgrade 0002_catalog_import_staging` in a local database followed by reverting this commit. No image was downloaded, no network request occurred, no production data changed, and no deployment was performed.
