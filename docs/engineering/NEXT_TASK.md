# Next Task

## Extend Fixture Coverage for Full Pagination and Focus Details

Add explicit page-number controls only if the product contract introduces them; otherwise keep the current load-more contract. Extend fixture assertions for 24-item request metadata, incomplete category detail text, drawer outside-click focus return, and reduced-motion loading indicators. Do not use production writes or credentials.

### Acceptance criteria

- Manual picker selection, removal, retry, missing-price, and duplicate suppression pass with fixtures.
- Generated success, no-result, server-error, compatibility, SAR price, and vendor states pass.
- Shared-build rendering passes at desktop, tablet, and mobile sizes.
- Axe findings are explicit and no accessibility failures are silently suppressed.

### Following iteration prompt

Read `AGENTS.md`, the engineering state files, `docs/operations/WEBSITE_BROWSER_VERIFICATION.md`, and `docs/operations/WEBSITE_PRODUCTION_VERIFICATION.md`. Extend only local Playwright fixtures and tests for manual/generated/shared-build states, 1280×800 and 768×1024 viewports, and axe checks. Do not call production write endpoints, mutate Neo4j, change secrets, or deploy.

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
