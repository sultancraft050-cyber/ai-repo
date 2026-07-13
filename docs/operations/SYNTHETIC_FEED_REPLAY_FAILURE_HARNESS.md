# Synthetic Feed Replay and Failure-Injection Harness

## Purpose and local-only scope

The harness exercises exact replay, duplicate handling, interrupted staging, bounded retry, guarded local commit behavior, parser/mapping/validation failures, review gates, stale observations, and state-equivalence summaries around the existing simulator and catalog services. It uses only checked-in synthetic definitions, generated temporary files, ephemeral SQLite, and existing mapping/staging/commit code. It never contacts suppliers, PostgreSQL, Neo4j, Cloud Run, Vercel, Secret Manager, or any external service.

## Feature flags and local database

`REPLAY_FAILURE_HARNESS_ENABLED=false` is the new default. Execution requires it plus `CATALOG_FEED_SIMULATOR_ENABLED=true`, `CATALOG_FEED_MAPPING_ENABLED=true`, `CATALOG_IMPORT_ENABLED=true`, and an explicit `sqlite:///` URL. Scenarios that invoke the existing commit service additionally require `CATALOG_WRITES_ENABLED=true`. Catalog operations, V2, imports, image review, writes, mapping, simulator, pricing scheduler, autonomous agents, and CPU startup seeding remain false by default. Nothing runs at startup.

Remote URLs, PostgreSQL URLs, network paths, arbitrary external files, real records, and credentials are rejected. Full database URLs and raw feed records are never printed or persisted as evidence.

## Failure points and modes

Failure points are explicit `FailurePoint` enum values from generation through mapping, batch creation, staging, review, commit, price history, and primary-image boundaries. Failure modes are explicit `FailureMode` values for controlled exceptions, rollback, truncation, malformed records, duplicates, checksum mismatch, stale/out-of-order observations, identity/review gates, SQLite lock simulation, status conflicts, and bounded commit retry. There is no monkey-patching, dynamic import, callable lookup, `eval`, `exec`, shell command, or uncontrolled randomness.

## Replay, retry, and idempotency

Each run uses fixed scenario/version, seed, timestamp anchor, failure point, replay number, and retry count. The run ID and generated checksum are deterministic. Exact replay reuses the same simulator output; duplicate replay remains a staged/review event and cannot create duplicate canonical identities. Retry is bounded to three attempts by default (configurable lower/upper bounded value); malformed and identity failures are not silently retried.

The harness delegates normalization, identity matching, mapping, staging, image review, and commit to existing services. It does not implement a second importer or commit path. Existing commit idempotency returns zero work for completed batches and rolls back the SQLite transaction on exceptions.

## Transaction rollback and state summaries

Evidence includes deterministic before/after summaries for products, stores, offers, price history, specifications, images, approved/primary images, batches, staged records, and business-identity/offer/price checksums. Volatile timestamps, insertion order, credentials, and raw payloads are excluded from checksums. Controlled commit failure is classified as rollback or uncertain status; no partial commit is treated as success.

## Required scenarios

Checked-in definitions cover exact replay, interrupted staging, commit rollback, post-commit status uncertainty, partial/full retry, price replay, identity conflict, image-review replay, malformed-input retry, batch-status conflict, SQLite lock simulation, and clean-run equivalence. Definitions point to existing simulator scenarios and contain only safe expected outcomes.

## CLI and local operations interface

Example:

```sh
REPLAY_FAILURE_HARNESS_ENABLED=true \
CATALOG_FEED_SIMULATOR_ENABLED=true \
CATALOG_FEED_MAPPING_ENABLED=true \
CATALOG_IMPORT_ENABLED=true \
CATALOG_DATABASE_URL=sqlite:////tmp/catalog-replay.sqlite3 \
python -m app.catalog.replay_harness_cli run \
  --scenario interrupted-staging \
  --seed 20260713 \
  --timestamp-anchor 2026-07-13T09:00:00+03:00 \
  --failure-point DURING_STAGING
```

Commands include scenario listing/validation, run, replay, retry, compare, manifest display, bounded suite execution, and explicit cleanup. The standalone loopback operations app adds `/replay-harness`, scenario/run/compare views, run/retry/replay/compare actions, and run cleanup. No production route was added.

## Evidence artifacts and classifications

Safe JSON evidence is written only under `/tmp/catalog-feed-replay/<run_id>/`: manifest, generated summary, before/after state, retry events, and result classification. It contains checksums and aggregate counts only. Classifications include `PASS_EXPECTED_FAILURE_RECOVERED`, `PASS_IDEMPOTENT_REPLAY`, `PASS_CLEAN_RUN_EQUIVALENT`, `PASS_EXPECTED_BLOCK`, and explicit failure classes for non-idempotency, partial commit, state mismatch, retry exhaustion, unexpected outcomes, or unsafe evidence.

## Testing, cleanup, and rollback

Focused tests cover flags, local SQLite restrictions, deterministic replay, every representative failure boundary, bounded retry, evidence redaction, and network/arbitrary-execution prohibition. Existing simulator, mapping, import, image-review, operations, backend, and release suites remain required. Temporary evidence is removed only with the explicit `clean-run` command; SQLite files are never committed. Rollback is a normal Git revert of this focused commit.

No real feed was used, no external service was contacted, no image was downloaded, no production database was connected, no Neo4j operation occurred, no cloud resource was created, no secret changed, and no deployment occurred.
