# Next Task

## Design the Catalog-Powered Homepage Product Sections

The visual-audit baseline and theme capture were successfully completed, confirming a clean and error-free production baseline. The next step is to design and implement catalog-powered components on the homepage to showcase the 280 imported products from Cloud SQL, supporting categories, filters, search, and pagination.

### Acceptance criteria

- Define the layout and component structure for homepage catalog displays (e.g. CPU, GPU, Motherboard cards).
- Design and mock the component rendering states (loading, success, empty, error fallback).
- Add tests to cover homepage components behavior.
- Ensure all designs conform to the design token rules established in `docs/design/CURRENT_THEME_BASELINE.md`.
- No writes, imports, or deployments are within scope.

### Following iteration prompt

Read `AGENTS.md`, all engineering-state files, `docs/design/CURRENT_THEME_BASELINE.md`, and `docs/operations/HOMEPAGE_THEME_CAPTURE_RESULT.md`. Create homepage components to render catalog products from the database (read-only), complete with loading, empty, and error mock states. Verify visually and with unit tests. Do not enable writes, imports, or deploy.


## Add Fixture-Backed Workflow and Accessibility Coverage

Extend the local Playwright harness with deterministic fixtures for manual category loading/partial failure/retry, generated-builder validation/result/error states, and the dynamic shared-build route. Add 1280×800 and 768×1024 coverage and a lightweight axe check when compatible. Keep all production writes, databases, secrets, and deployments out of scope.

### Acceptance criteria

- Product selection/removal, missing price, readiness, retry, and duplicate suppression are covered with mocked responses.
- Generated validation, loading, success, no-result, server-error, compatibility, and Saudi-price states are covered.
- Shared-build route and intermediate viewports pass.
- Accessibility findings are explicit and no failures are suppressed.

### Following iteration prompt

Read `AGENTS.md`, the engineering state files, `docs/operations/WEBSITE_FEATURE_AUDIT.md`, and `docs/operations/WEBSITE_BROWSER_VERIFICATION.md`. Extend only the local Playwright fixtures and tests. Do not call production write endpoints, mutate Neo4j, change secrets, or deploy.

## Complete Browser-Level Frontend Verification

Add a small browser smoke/accessibility harness for every public route at desktop and mobile widths. Cover theme persistence and system preference, mobile menu keyboard behavior, route navigation, mocked API success/error/loading states, unknown-route handling, and a no-localhost production-target assertion. Keep all production writes, Neo4j operations, secret changes, and deployments out of scope.

### Acceptance criteria

- Browser tests pass for `/`, `/build/manual`, `/build/generate`, `/build/share/[slug]`, and `/release`.
- Theme toggle persists across reload and has correct accessible state.
- Mobile navigation is keyboard usable and closes predictably.
- API-backed flows use mocks or local fixtures only.
- No production data, secrets, Cloud Run, Vercel, or backend behavior changes.

### Following iteration prompt

Read `AGENTS.md`, the engineering state files, and `docs/operations/WEBSITE_FEATURE_AUDIT.md`. Install or use the repository-approved browser test runtime if available, then run a GET-only/local mocked browser audit at desktop and mobile widths. Do not call production write endpoints, change backend or data, or deploy.

## Supply Approvals and Verified Clone Inputs

The approval package and clone runbook are complete, but execution is not authorized. All owner approvals, Aura snapshot facts, billing eligibility, target sizing, and isolated clone identity remain pending.

### Scope

- Supply dated written approvals for all nine owner roles.
- Manually verify Aura tier/region/snapshot/export/version/permissions and both billing paths.
- Supply the approved larger clone ID, organization, URI fingerprint, capacity, region, isolation evidence, lifetime, and rollback snapshot reference.
- Do not start rehearsal until every prerequisite and stop-condition owner is assigned.
- Keep production data and deployment configuration unchanged.

### Exclusions

- No deletion, pruning, archival, migration execution, cleanup, seeding, or schema changes without approval.
- No catalog staging, URL ingestion, or price mutation.
- No secret value exposure or rotation.
- No Cloud Run/Vercel deployment until parity checks pass.

### Acceptance Criteria

- Backend CI must be green before query optimization is committed.
- Release compatibility reports `compatible`.
- Existing production smoke remains compatible after backend validation.
- No localhost/127.0.0.1 production target is detected.
- Admin-only routes reject unauthenticated requests.
- The workflow remains GET-only and returns useful exit codes.
- Backend tests and compile run in GitHub Actions' Python 3.12 environment.
- State files and the following iteration prompt are updated.

### Likely files

- product-search API and repository files identified by profiling
- focused product-search tests

### Risk

Low to medium; read-only query performance work.

### Following iteration prompt

Read `AGENTS.md`, all engineering-state files, `docs/operations/NEO4J_RETENTION_APPROVAL_PACKAGE.md`, and `docs/operations/NEO4J_CLONE_REHEARSAL_RUNBOOK.md`. Do not execute rehearsal until the user supplies dated approvals for every owner, completed Aura snapshot/readiness checks, `MANUAL_BILLING_VERIFICATION_REQUIRED` outcomes, and an isolated clone identity/capacity/URI fingerprint with proof it is not production. Once supplied, validate prerequisites and report any blockers before running even read-only clone previews. Never mutate the production source, change secrets, or deploy. Preserve all safe-off flags.

## Product Image Rendering Reliability

Completed 2026-07-13. Product imagery is centralized in `ProductImage`, with deterministic local fixture coverage and no production or data impact. The next standalone task is relational catalog execution design or Neo4j migration preparation; do not import images or execute a migration without approvals.

### Following iteration prompt

Read `AGENTS.md`, all engineering-state files, and `docs/operations/PRODUCT_IMAGE_RENDERING_IMPLEMENTATION.md`. Choose one bounded planning task: relational catalog execution design or Neo4j migration preparation. Keep production data, Neo4j, secrets, image downloads, Cloud Run/Vercel, and all write requests out of scope until explicit approvals are supplied.

## Neo4j Migration Execution Readiness

Completed 2026-07-13 with result `READY_PENDING_MANUAL_APPROVALS`. The writer map, provider checklist, parity manifest, cutover sequence, stop conditions, isolation requirements, and rollback plan are documented. No target or migration execution is authorized.

### Following iteration prompt

Read `AGENTS.md`, all engineering-state files, `docs/operations/NEO4J_MIGRATION_EXECUTION_READINESS.md`, `docs/operations/NEO4J_MIGRATION_MANUAL_CHECKLIST.md`, and `docs/operations/NEO4J_MIGRATION_APPROVAL_RECORD.md`. Do not execute migration. Collect only user-supplied/manual Aura Console, billing, target-isolation, and owner-approval facts; stop on missing or conflicting provider evidence. Preserve all safe-off flags and production rollback assets.

## Minimal Neo4j Migration Approval Gate

Completed 2026-07-13 with result `BLOCKED_MISSING_ESSENTIAL_FACTS`. The gate is intentionally limited to the essential provider, cost, budget, snapshot, target, and three approval fields.

### Following iteration prompt

Read the three Neo4j migration gate documents and collect only the missing essential facts from an authorized Aura Console/billing owner. Do not create a target, snapshot, export, restore, secret version, deployment, traffic change, or migration prompt unless the result becomes `READY_TO_CREATE_ISOLATED_TARGET`.

## Minimal Neo4j Cleanup Preparation

Completed 2026-07-13 with result `READY_FOR_CLONE_CLEANUP_REHEARSAL` only. The selectors and clone gates are prepared, but no clone or cleanup is authorized.

### Following iteration prompt

Read `NEO4J_MINIMAL_CLEANUP_PLAN.md`, `NEO4J_CLEANUP_SELECTOR_CATALOG.md`, `NEO4J_CLONE_CLEANUP_CHECKLIST.md`, and the existing retention/runbook documents. Do not create a clone or run deletion. First obtain explicit authorization and a verified isolated clone identity, then run only the documented aggregate previews and stop on any protection, parity, writer, capacity, or health mismatch.

## Relational Product Catalog Foundation

Completed 2026-07-13. Catalog V2 is a disabled parallel foundation; existing Neo4j-backed product behavior remains authoritative.

### Following iteration prompt

Read `docs/operations/PRODUCT_CATALOG_SCHEMA_IMPLEMENTATION.md` and the catalog models/repository/tests. Design a staged CSV/JSON Product and Store-Offer Import Pipeline using synthetic fixtures only. Keep `CATALOG_V2_ENABLED=false`, `CATALOG_WRITES_ENABLED=false`, all existing safe-off flags false, and do not import real products, connect production databases, mutate Neo4j, download images, or deploy.

## Product Image Metadata Quality and Review Pipeline

Add a disabled, local review service for already-staged product-image metadata. Validate dimensions, format, checksum, rights provenance, quality status, duplicate/primary conflicts, and reviewer decisions without downloading images or exposing a public write route. Use only synthetic metadata and ephemeral SQLite; keep all catalog flags and existing operational flags false.

### Acceptance criteria

- Only reviewed metadata can transition to approved; unknown or conflicting rights remain blocked.
- Duplicate checksum and approved-primary conflicts are deterministic and idempotent.
- No remote image request, production database, Neo4j operation, secret change, cloud resource, or deployment occurs.
- Focused tests, full backend tests, migration validation when needed, release tests, and diff checks pass.

### Following iteration prompt

Read `AGENTS.md`, all engineering-state files, `docs/operations/PRODUCT_CATALOG_SCHEMA_IMPLEMENTATION.md`, and `docs/operations/PRODUCT_CATALOG_IMPORT_PIPELINE.md`. Implement only a local Product Image Metadata Quality and Review Pipeline with synthetic fixtures. Do not download images, inspect remote files, enable catalog flags, connect production databases, mutate Neo4j, change secrets, create cloud resources, or deploy.

## Local Catalog Review and Import Operations Interface

Build a local-only, read/write-guarded operations interface for reviewing staged catalog products, offers, image metadata, and import batches. Use synthetic fixtures and ephemeral SQLite only; keep Catalog V2, imports, writes, and image review disabled by default. Do not add a public write API, connect production databases, touch Neo4j, download images, change secrets, or deploy.

### Acceptance criteria

- Review queues expose bounded summaries, stable IDs, safe reason codes, and append-only history without credentials or complete records.
- Product/store/offer/image decisions reuse existing identity, rights, primary, and commit safeguards and remain idempotent.
- Local CLI or internal service tests cover approval gates, rejection, retry, pagination, and audit chronology.
- Migration, focused tests, full backend tests, release tests, and diff checks pass with all safe-off defaults unchanged.

### Following iteration prompt

Read `AGENTS.md`, all engineering-state files, `docs/operations/PRODUCT_CATALOG_SCHEMA_IMPLEMENTATION.md`, `docs/operations/PRODUCT_CATALOG_IMPORT_PIPELINE.md`, and `docs/operations/PRODUCT_IMAGE_METADATA_REVIEW_PIPELINE.md`. Implement one local Catalog Review and Import Operations Interface using synthetic fixtures and ephemeral SQLite. Do not expose public write endpoints, enable production flags, connect production databases, mutate Neo4j, download images, change secrets, create cloud resources, or deploy.
## Next task

BuildCores OpenDB Bounded Import into Cloud SQL

### Following iteration prompt

Read `AGENTS.md`, all engineering-state files, `docs/operations/BUILDCORES_OPENDB_CATALOG_BOOTSTRAP.md`, and `docs/operations/CLOUD_SQL_PRIMARY_CATALOG_STORAGE.md`. Configure the import credentials and connect to the Cloud SQL staging instance. Run the OpenDB adapter to ingest real catalog records into Cloud SQL under the 300 product cap, verifying counts and schema relations without modifying production resources or Neo4j data.
