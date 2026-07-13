# Synthetic Authorized Feed Adapter Simulator

## Purpose and local-only scope

The simulator creates bounded, deterministic, obviously synthetic catalog feed files for exercising existing mapping and staging safeguards. It has no supplier connector, authentication, scheduler, network transport, URL fetch, image download, external-file input, production database access, Neo4j access, or cloud integration. No run starts automatically.

## Feature flags

`CATALOG_FEED_SIMULATOR_ENABLED=false` is the default. Generation and preview require both the simulator and existing `CATALOG_FEED_MAPPING_ENABLED=true`. Local staging additionally requires `CATALOG_IMPORT_ENABLED=true` and an explicit SQLite database. The simulator has no commit command; the existing guarded catalog commit continues to require `CATALOG_WRITES_ENABLED=true`. All catalog flags and `PRICING_SCHEDULER_ENABLED`, `AUTONOMOUS_AGENTS_ENABLED`, and `CPU_SPECS_SEED_ON_START` remain false by default.

## Adapter and scenario schemas

Versioned JSON adapter definitions live under `backend/tests/fixtures/catalog_feed_simulator/adapters/`. Controlled fields identify the immutable adapter/version, synthetic source and authorization, supported entities/formats, template reference, Saudi defaults, deterministic seed, bounded record limit, scenario, and creation anchor. Only `SYNTHETIC_FIXTURE` plus `SYNTHETIC_ONLY` is runnable. Credential, endpoint, token, and remote-connection fields are absent and invalid definitions are rejected before generation.

Versioned scenario definitions live under `backend/tests/fixtures/catalog_feed_simulator/scenarios/`. They describe initial load, incremental update, price/stock changes, new offer, duplicate replay, identity conflict, invalid pricing, image review, stale/out-of-order observations, partial interruption/retry, malformed records, and unauthorized-adapter rejection. Scenario inputs never contain real products, identifiers, prices, stores, or URLs.

## Deterministic generation and formats

Every run is defined by adapter/version, scenario, entity, seed, record count, output format, timestamp anchor, and controlled mutations. Identifiers, timestamps, ordering, run ID, and checksums derive only from those inputs; record generation does not read the system clock or use unseeded randomness. Supported entities are product, specification, image metadata, store, offer, and price observation. UTF-8 CSV, JSON array, and `{ "records": [...] }` output are supported.

Generated files and `manifest.json` are written only under `/tmp/catalog-feed-simulator/<run_id>/`. They are never written into tracked fixture directories and cleanup occurs only through an explicit `clean-run` action. The manifest contains safe identifiers, deterministic inputs, counts, template/file checksums, expected outcomes, and the timestamp anchor; it contains no records, environment values, credentials, or database URLs.

## Controlled mutation operators

The strict enum is `set_field`, `remove_field`, `duplicate_record`, `reorder_records`, `increment_decimal`, `decrement_decimal`, `change_stock_status`, `shift_timestamp`, `replace_controlled_value`, `add_unknown_field`, `introduce_identity_conflict`, and `truncate_feed`. Arbitrary Python, `eval`, `exec`, shell commands, dynamic imports, unrestricted regex, user callables, and network lookup are unsupported.

## Mapping and staging integration

Each generated record set is validated by the existing `FeedMappingService` and checked-in entity template. Template checksum/version, strict identity, unknown-field policy, SAR behavior, Asia/Riyadh timestamp meaning, image-rights review, and no-approval/no-primary safeguards remain unchanged. The simulator does not weaken mapping rules to accept a scenario.

Staging is deliberately separate from generation and reuses the existing import pipeline against explicit local SQLite only. Safe provenance can retain run ID, adapter/version, scenario/seed, and template version/checksum; raw generated files are not stored in the catalog database. No canonical commit occurs automatically or through the simulator CLI.

## CLI and local operations pages

From `backend`, enable only the local flags needed for the operation:

```sh
CATALOG_FEED_SIMULATOR_ENABLED=true \
CATALOG_FEED_MAPPING_ENABLED=true \
CATALOG_IMPORT_ENABLED=true \
python -m app.catalog.feed_simulator_cli generate-and-preview \
  --adapter synthetic-sa-retailer-v1 \
  --scenario initial-catalog-load \
  --format csv \
  --seed 20260713 \
  --timestamp-anchor 2026-07-13T09:00:00+03:00 \
  --output-dir /tmp/catalog-feed-simulator
```

Commands cover adapter/scenario listing, adapter validation, generation, generation with preview, guarded staging preparation, manifest display, run comparison, and explicit cleanup. Output is bounded and excludes complete raw files and database URLs.

The standalone loopback operations app adds `/feed-simulator`, adapter/scenario lists, generate/preview/stage actions, and explicit run cleanup. These pages are not mounted in the production FastAPI application, accept no definition upload, render no external asset, and show at most safe summaries. No production route was added.

## Bounded limits and safe failures

Defaults are 100 records/run, 1 MiB/file, 12 mutations, 1,000 characters/field, 20 retained-run target, and 10 preview rows. Non-positive or over-limit settings fail closed. Stable errors cover disabled flags, missing/invalid/unauthorized adapters and scenarios, unsupported formats, record/file/mutation limits, missing/mismatched templates, local-path restrictions, mapping failures, staging/SQLite requirements, missing runs, invalid manifests, and credential-like fields.

## Synthetic data and failure scenarios

Records use names such as Synthetic Riyadh Components, Fixture Electronics KSA, Test CPU Model A, and Test GPU Model A. URLs use `fixture.invalid`; identifiers and prices are invented fixtures. Invalid pricing and malformed-record cases are produced only through bounded controlled mutations, so complete raw failure payloads are not logged. Partial interruption truncates a local file and retry regenerates the complete deterministic file; it never simulates transport.

## Testing, cleanup, and rollback

Focused tests cover safe-off configuration, adapter authorization, repository definitions, deterministic files/checksums, all output formats, local-path and mutation limits, mapping previews, strict mutation enums, input immutability, and static network/arbitrary-execution prohibition. Existing mapping, import, image-review, operations, catalog, backend, and release suites remain required.

To clean one run, use `clean-run <run_id>`. Never remove unrelated temporary paths. Rollback is a normal Git revert of the focused simulator commit; no database migration was added.

No real feed was used, no external service was contacted, no image was downloaded, and production, PostgreSQL, Neo4j, Secret Manager, Cloud Run, and Vercel were untouched.
