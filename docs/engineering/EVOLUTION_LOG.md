# Evolution Log

## 2026-07-11 — Iteration 1: Safe Startup Defaults

### Objective

Establish persistent evolution state and prevent graph-mutating startup behavior when deployment flags are omitted.

### Why Selected

The backend previously defaulted CPU seeding, pricing scheduling, and autonomous agents to enabled. This conflicted with the documented safe-off production policy and could create unexpected Neo4j writes during restart or deployment.

### Baseline

- Git HEAD: `811c631`.
- Frontend typecheck passed.
- Backend Python tests were blocked locally because `python` was unavailable.
- Unrelated frontend changes existed and were preserved.

### Changes

- Added `AGENTS.md` and the engineering state files.
- Changed scheduler, autonomous-agent, and CPU-seeding defaults to disabled.
- Updated the backend environment example and deployment documentation.
- Added focused startup safety tests.

### Validation

- Frontend typecheck: passed.
- Frontend production build: passed.
- Frontend UI contract checks: passed.
- `git diff --check`: passed.
- Backend tests and compile: pending Python-enabled environment; this machine has no `python` or `py` launcher.

### Data And Deployment Impact

No catalog, evidence, pricing, vendor, URL, approval, or Neo4j data changes. Deployments with explicit `true` flags retain opt-in behavior; deployments relying on omitted variables become safe-off.

### Rollback

Revert this focused commit. For a temporary controlled operation, explicitly enable the required flag, then restore it to `false` and redeploy.

### Remaining Risks

Backend validation requires a Python-enabled shell. Deployment parity still needs a separate smoke-test iteration.

## 2026-07-11 — Iteration 2: Deployment Parity Smoke Workflow

### Objective

Create and validate a repeatable, non-destructive smoke workflow for Railway and Vercel.

### Precondition Verdict

PARTIAL GO. Node.js and PowerShell are available. The Railway URL is known, but the current network sandbox could not connect to it. No Vercel production URL or shared-build slug was discoverable locally. No credentials were requested or exposed.

### Baseline

- Git HEAD: `811c631`.
- Unrelated frontend changes remained untouched.
- Existing deployment configuration uses a frontend API environment variable and backend health/version metadata.

### Implementation

- Added `scripts/smoke-production.mjs`.
- Added root command `npm run smoke:production`.
- Added deployment usage documentation.
- The workflow accepts backend/frontend/shared URLs through environment variables or arguments, uses GET requests only, applies timeouts, follows redirects, checks health, Neo4j health, OpenAPI critical paths, admin protection, public frontend routes, release metadata, and local API targets in HTML and bounded Next.js script assets.

### Commands Run

- Railway GET checks for `/health`, `/health/neo4j`, `/openapi.json`, and admin protection endpoint: unavailable because the shell network could not connect.
- Smoke command syntax check: passed; execution returned non-zero as expected because Railway was unavailable and Vercel was not configured.
- Frontend typecheck: passed.
- Frontend production build: passed.
- Frontend UI contract checks: passed.
- `git diff --check`: passed.

### Skipped Or Unverified

- Vercel route checks: unavailable because no production URL was present locally.
- Shared-build check: unavailable because no slug was present locally.
- Backend pytest/compile: unavailable because Python is not installed.
- Neo4j before/after counts: not queried; the workflow performs no writes and no authorized read-only count endpoint was available to the shell.

### Data And Deployment Impact

No production data, Neo4j nodes, prices, evidence, URLs, approvals, or workers were changed. The new script performs only HTTP GET requests.

### Problems Discovered

- The known Railway hostname could not be reached from this execution sandbox.
- The repository does not identify the Vercel production hostname.
- The frontend source still contains development fallback values in local example configuration; production environment verification remains external to the repository.

### Rollback

Remove the smoke script, root npm command, and documentation addition. No runtime or database rollback is needed because the workflow is read-only.

### Remaining Risks

Production parity is not fully verified until Railway and Vercel URLs are supplied through the environment or accessible from a network-enabled shell. Python backend validation remains pending.

## 2026-07-11 — Iteration 3: Deployment Release-Version Contract

### Objective

Provide safe, structured release metadata for frontend and backend deployments and verify API compatibility in the production smoke workflow.

### Baseline And Selection

The backend exposed version and Git SHA fields through `/health`, but there was no explicit API compatibility version. The frontend had no structured release endpoint. Smoke testing therefore could not establish deployment compatibility reliably.

### Implementation

- Added API contract version `1` to backend release metadata and `/health`.
- Added frontend public JSON route `/release`.
- Added safe environment examples for frontend API contract, Git SHA, and build time.
- Added reusable release compatibility comparison and Node tests.
- Updated the smoke workflow to fetch both contracts and report compatible, incompatible, or unverifiable.
- Confirmed incompatibility now causes a non-zero smoke exit; network unavailability remains distinct.

### Compatibility Behavior

- Compatible: both services expose the same `api_contract_version`.
- Incompatible: versions differ; smoke verification fails.
- Unverifiable: either target or required metadata is unavailable.
- Release identifiers and Git SHAs may differ because Vercel and Railway are separate deployment units.

### Validation

- Release contract Node tests: 3 passed.
- Smoke script syntax: passed.
- Frontend production build: passed and emitted `/release`.
- Frontend typecheck: passed after the build; an initial parallel run raced with `.next/types` regeneration and was rerun sequentially.
- Frontend UI checks: passed.
- `git diff --check`: passed.
- Backend tests/compile: pending; Python, Docker, and WSL are unavailable.
- Live smoke: unavailable from the current network sandbox and without a Vercel production URL.

### Data And Deployment Impact

No data or Neo4j mutations. Public metadata contains only safe release fields. Deployment must provide optional SHA/build-time variables to improve observability; unknown values remain honest null/unknown values.

### Rollback

Remove the frontend `/release` route, backend contract fields, comparison module/tests, and smoke integration. Existing `/health` fields remain backward compatible if only the new fields are reverted.

### Remaining Risks

The contract is not live until deployed. Backend Python validation and production parity checks remain pending.

## 2026-07-11 — Iteration 4: Focused Release Preparation

### Objective And Verdict

Package Iterations 1–3 into one isolated reviewed commit and attempt the existing push/deployment path. Verdict: PARTIAL GO. Git identity, branch, upstream, and remote are configured; provider credentials, Python, Docker, WSL, and the Vercel production URL are unavailable locally.

### Baseline

- Branch: `master`, tracking `origin/master`.
- HEAD before release: `811c63129053c08247c91a1805a75a703d1d446e`.
- Unrelated frontend modifications were preserved and excluded.
- No repository CI workflow was found.

### Release Manifest

Included: repository rules and engineering state, safe startup defaults, startup tests, backend/frontend release metadata, release comparison tests, GET-only production smoke tooling, package commands, environment examples, and deployment/operations documentation.

Excluded: `frontend/components/SoloFounderOpsPanel.tsx`, `frontend/types/builder.ts`, generated frontend output, local environment files, catalog data, and pricing data.

### Validation

- Release comparison tests: 3 passed.
- Smoke script syntax: passed.
- Frontend production build: passed.
- Frontend typecheck: passed sequentially after build.
- Frontend UI contract checks: passed.
- `git diff --check`: passed.
- Backend pytest/compile: not run because no supported Python, Docker, WSL, or CI runtime is available.

### Security And Data Safety

No secrets or local environment files are included. Public release metadata is allow-listed. Smoke tooling uses GET only. Scheduler, agents, and startup seeding default to disabled. No Neo4j, catalog, vendor, URL, approval, or price mutation is performed.

### Commit And Deployment

- Focused commit: `10d38581b2a991ad372064609838cb8ac8bff267`.
- Subject: `chore: add safe startup and release verification`.
- Pushed successfully to `origin/master`.
- Remote `refs/heads/master` matches the focused commit.
- Known Railway hostname returned `404 Application not found` for all four read-only checks; deployment is not verified.
- Vercel deployment remains unverified because its public URL is unavailable locally.

### Rollback

Use `git revert <focused-commit-sha>` and redeploy the previous Railway/Vercel release. Verify the previous `/health` and `/release` behavior, then rerun `npm run smoke:production`. No database rollback is required.

### Remaining Risks

Backend tests remain unverified until a Python-enabled environment is available. Production release compatibility remains unverified because the known Railway hostname is not serving the application and the Vercel URL is unknown.

## 2026-07-11 — Iteration 5: Cloud Run Migration Preparation

### Objective

Prepare the existing FastAPI backend for Cloud Run as the replacement for the expired Railway deployment while retaining Vercel and Neo4j Aura.

### Precondition Verdict

PARTIAL GO. Runtime requirements were fully discoverable from the repository, but `gcloud`, Docker, Python, and WSL are unavailable in this environment. No Google Cloud authentication, billing, project ID, Vercel access, or secret values were available.

### Runtime Audit

- FastAPI entry point: `app.main:app`.
- Python runtime: `python:3.12-slim`.
- Existing container binds `0.0.0.0` and honors `${PORT:-8080}`.
- Backend requires the existing Neo4j and API-key variable names.
- Startup seeding, pricing scheduling, and autonomous agents remain safe-off.
- Docker context excludes tests, local environments, the raw pc-part-dataset tree, and build artifacts.

### Implementation

- Added non-root `appuser` execution to the backend image.
- Added Cloud Run deployment scripts for PowerShell and Bash.
- Added Cloud Run deployment documentation, Secret Manager names, non-secret variables, service sizing, rollback, and verification commands.
- Kept Vercel, Neo4j Aura, Railway resources, catalog data, pricing data, and authorization behavior unchanged.

### Validation

- Repository state and deployment configuration inspected.
- Cloud Run deployment not executed because Google Cloud tooling and credentials are unavailable.
- Backend tests/compile pending a Python-enabled environment.
- Frontend validation remains available from prior iteration; rerun before deployment.

### Data And Deployment Impact

No production data, Neo4j nodes, prices, products, URLs, vendors, approvals, or secrets changed. Cloud Run deployment is prepared but not executed. Railway was not deleted or modified.

### Rollback

Keep prior Cloud Run revisions. Route traffic to the previous revision with `gcloud run services update-traffic`, restore Vercel’s prior `NEXT_PUBLIC_API_BASE_URL`, redeploy Vercel, and rerun the smoke test. No Neo4j rollback is expected.

### Remaining Risks

Cloud Run deployment, health, Neo4j connectivity, Vercel routing, and production smoke verification remain pending. The known Railway hostname remains an expired/mismatched fallback.

## 2026-07-11 — Iteration 7: Remove Production Local API Fallback

### Objective

Remove localhost and loopback API fallbacks from production frontend JavaScript while preserving development convenience and improve smoke diagnostics.

### Baseline

- Cloud Run backend: healthy at `https://hardware-intelligence-api-lywizc5z5q-ww.a.run.app`.
- Vercel frontend: healthy at `https://frontend-lac-nine-09j4x45cj5.vercel.app`.
- Smoke workflow had one required failure because a local API target was detected in generated assets.
- The source fallback was `frontend/lib/api.ts`; `frontend/app/sitemap.ts` also used a development fallback.
- The remaining local string was traced to Next.js’s generated third-party polyfill, not application API configuration.

### Implementation

- API base uses the configured public API URL.
- Development may still use the loopback fallback.
- Production uses a relative safe fallback when the public API variable is missing.
- Sitemap uses the same development-only fallback policy.
- Smoke asset scanning skips third-party `polyfills-*` assets and reports the exact offending asset URL for actual local HTTP API targets.

### Validation

- `npm install`: passed.
- `npm run build`: passed.
- `npm run typecheck`: passed.
- `npm run ui:check`: passed.
- Generated application static JavaScript: zero local HTTP API targets.
- Production smoke: 14 passed, 1 optional shared-build check skipped, 0 required failures.
- Cloud Run `/health`: HTTP 200; Neo4j connected.
- Cloud Run `/openapi.json`: HTTP 200; critical paths present.
- Admin protection: HTTP 403 without credentials.
- Vercel `/`, `/build/manual`, `/build/generate`, and `/release`: HTTP 200.
- Release compatibility: `COMPATIBLE`, API contract version `1`.
- `git diff --check`: passed.

### Data Impact

None. The smoke workflow uses GET requests only. No catalog, pricing, Neo4j, URL, vendor, approval, or audit data was changed.

### Deployment Impact

The focused frontend/smoke change requires a Vercel deployment. The supplied production smoke target is already healthy and compatible after deployment verification.

### Rollback

Revert the focused commit, redeploy Vercel, and rerun `npm run smoke:production`. No backend or database rollback is required.

### Remaining Risks

No shared-build URL was supplied, so that optional route remains unverified. Backend Python tests remain a separate environment limitation.

### Validation Update

- `npm run test:release`: 3 passed.
- `node --check scripts/release-contract.mjs`: passed.
- `node --check scripts/smoke-production.mjs`: passed.
- `npm run build`: passed.
- `npm run typecheck`: passed.
- `npm run ui:check`: passed.
- PowerShell deployment script parse: passed.
- `git diff --check`: passed.
- Cloud Run deployment: not attempted; `gcloud`, Docker, Python, and WSL are unavailable.
- Current Google Cloud preflight: authenticated account and project confirmed; billing and required APIs enabled; required secrets present; runtime service account and per-secret access bindings created; Artifact Registry repository created in `me-central1` after `me-central2` was rejected.
- Cloud Build: succeeded as `dfd3d99f-4624-4867-9a92-269764064053`; image was built in Artifact Registry.
- Cloud Run deployment: intentionally not started because the verified Vercel production URL is not available for safe CORS configuration.
## 2026-07-11 — Iteration 8: Automated Reliability CI

- Objective: Add deterministic GitHub Actions validation for backend, frontend, release contracts, and deployment tooling.
- Why selected: backend validation was the main remaining gap, and local Python availability was unreliable.
- Baseline: no workflow existed; frontend checks passed locally; backend tests required a Python-enabled environment; unrelated frontend edits were present.
- Files changed: `.github/workflows/ci.yml`, this state record, `CURRENT_STATE.md`, and `NEXT_TASK.md`.
- Workflow: pull requests and pushes to `master`, least-privilege `contents: read`, concurrency cancellation.
- Backend checks: Python 3.12, pip cache, editable test install, compileall, startup-safety tests, release/security tests, full pytest; safe-off worker and seeding flags are explicit.
- Frontend checks: Node 22, deterministic npm install, sequential typecheck/build/UI checks, `/release` artifact verification.
- Contract/tooling checks: release tests, Node syntax checks, `bash -n` for Cloud Run deployment, safe-default and secret-file checks, `git diff --check`.
- Data impact: none; no Neo4j, catalog, evidence, vendor, URL, or price access.
- Deployment impact: none; workflow does not deploy or call production services.
- Tests: local equivalent frontend/release checks remain the available validation; GitHub Actions is authoritative for Python tests.
- Rollback: revert the CI commit or remove `.github/workflows/ci.yml`; no Cloud Run, Vercel, or database rollback is required.
- Remaining risks: GitHub-hosted dependency availability and any backend tests that unexpectedly require external infrastructure will be visible as CI failures.
- First run result: frontend passed; contract/tooling initially failed because `.env.example` templates matched the secret-file pattern; backend compile, focused safety, and release/security checks passed, but the full pytest step failed.
- Follow-up `2c1c823`: excluded `.example` templates from the secret-file check. Contract/tooling and frontend then passed; backend full pytest still failed. No test was weakened and no production access was added.

## 2026-07-11 — Iteration 9: Manual Picker Progressive Loading

- Objective: Reduce the time before `/build/manual` shows usable categories.
- Why selected: the picker already issued eight independent requests concurrently, but React state was published only after `Promise.allSettled` completed, so the UI behaved as all-or-nothing.
- Baseline: eight concurrent category requests; a read-only Cloud Run sample took about 20.7s overall, dominated by CPU at about 20.7s. GPU was about 11.8s and RAM about 6.7s. Payloads were about 16-58KB per category.
- Implementation: `ManualPartPicker` now publishes each category as its request settles, tracks loading per category, and preserves independent failures without blocking other rows.
- Files changed: `frontend/components/ManualPartPicker.tsx`, this state record, `CURRENT_STATE.md`, and `NEXT_TASK.md`.
- Tests: frontend typecheck, production build, UI contract checks, release tests, and diff check passed.
- Data impact: none; only read-only frontend request/render behavior changed.
- Deployment impact: frontend deployment only; no backend, Cloud Run, Neo4j, catalog, pricing, or schema changes.
- Post-change production measurement: pending Vercel deployment; pre-deployment measurements are recorded above.
- Rollback: revert the focused frontend commit; no data rollback is required.
- Remaining risks: the slow CPU endpoint and payload sizes remain backend-side bottlenecks; this iteration improves time-to-first-category, not total API completion time.

## 2026-07-11 — Iteration 10: Backend CI Diagnosis Blocked

- Objective: Resolve the full backend pytest failure from run `29164807695`.
- Diagnosis performed: confirmed job `86575990875` and failed step `Backend test suite`; compile, startup safety, release/security, frontend, and contract/tooling steps passed.
- Blocker: GitHub’s public workflow-log endpoint returned HTTP 403 requiring repository admin rights, and the public check-log page could not be retrieved. The exact failing test, exception, and traceback therefore cannot be established without repository access or a Python-enabled reproduction.
- Fix applied: none; no evidence-supported code change was possible.
- Data/deployment impact: none.
- Rollback: none required.
- Remaining risk: the backend full suite remains red; guessing or weakening tests would violate the iteration rules.

## 2026-07-11 — Iteration 11: Self-Diagnosing Backend CI

- Objective: retain enough structured pytest evidence to diagnose backend CI failures without repository-admin log access.
- Baseline: full backend pytest failed in run `29164807695`; compile and focused tests passed; public workflow-log download returned HTTP 403.
- Implementation: `.github/workflows/ci.yml` now runs pytest with `--tb=short -ra --junitxml=pytest-results.xml`, captures combined output in `pytest-output.log`, preserves `PIPESTATUS[0]`, uploads both files with artifact `backend-pytest-results`, writes a bounded summary, and explicitly fails when the captured exit code is non-zero.
- Validation: release tests and `git diff --check` passed locally. A new GitHub Actions run is required to collect the exact failing tests.
- Security: summaries and artifacts contain test output only; no environment dumps, tokens, credentials, production payloads, or production endpoints are used.
- Data/deployment impact: none; no backend behavior, Neo4j, catalog, pricing, URL, or deployment configuration changed.
- Rollback: revert the focused CI commit; no data rollback is required.
- Remaining risks: the underlying backend test failure is intentionally unresolved until the new artifact and summary provide evidence.
- Diagnostic run `29165405260`: artifact creation succeeded with size approximately 8.25KB; backend stayed red as intended, while frontend and contract/tooling passed. Public artifact download returned HTTP 401, so no test names or traceback were inferred.

## 2026-07-11 — Iteration 12: Fix Backend Test Fixture Paths

- Objective: Fix three confirmed pytest failures caused by cwd-dependent canonical-spec fixture paths.
- Original run: `29165405260`; Python 3.12.13; 285 collected, 282 passed, 3 failed.
- Failed tests: the current-gen GPU variant fixture check, GPU exact-card fixture check, and narrow AM5 motherboard fixture check in `test_pc_part_dataset_adapter.py`.
- Root cause: `Path("backend/data/...")` resolved to `backend/backend/data/...` because CI runs pytest from `backend`.
- Fix: define `BACKEND_ROOT` from `Path(__file__).resolve()` and resolve all three fixtures through `BACKEND_ROOT / "data" / "canonical_specs"`.
- Files changed: backend test module and engineering-state files only. Fixture contents, production code, assertions, and test selection are unchanged.
- Local validation: all three paths resolved from repository-root and backend working directories; release tests and `git diff --check` passed. Python tests remain authoritative in CI.
- Data/deployment impact: none.
- Rollback: revert the focused fixture-path commit; no data or deployment rollback is required.
- GitHub verification: run `29166175755` completed successfully; backend, frontend, and contract/tooling jobs passed; full pytest reported 285 passed; artifact `backend-pytest-results` uploaded successfully.

## 2026-07-11 — Iteration 13: Batch Product Search Price Reads

- Objective: reduce CPU `/products/search` latency with one evidence-supported read-only optimization.
- Baseline request: `/products/search?q=&limit=24&offset=0&category=CPU&region=SA`; prior sample approximately 20.7s, 24 results, approximately 47.5KB.
- Primary bottleneck: N+1 Neo4j reads. The search candidate query requests at least 100 candidates, then calls `vendor_prices()` once for every candidate.
- Optimization: replace per-product reads with one parameterized batch query returning the same latest-per-vendor snapshot fields, then reuse unchanged `_snapshot_view`, `_price_rollups`, filtering, CPU grouping, sorting, and pagination logic.
- Query count: approximately 101 before, 2 after for the default candidate pool.
- Files changed: pricing repository, focused pricing test, and engineering state files.
- Test coverage: verifies two total driver calls, one batch price query, unchanged CPU identity/readiness, and unchanged cheapest Saudi vendor/price rollup.
- Schema/index changes: none.
- Data impact: none; all profiling and repository operations are read-only.
- Deployment impact: backend code change; CI and Cloud Run verification required before production measurements.
- Rollback: revert the focused commit and redeploy the previous Cloud Run revision; no schema or data rollback is required.
- CI verification: run `29166403191` passed backend, frontend, and contract/tooling jobs.
- Deployment attempt: safely stopped before deployment because `gcloud` is unavailable in this shell. No Cloud Run revision or production data changed; post-change production measurements remain pending.

## 2026-07-12 — Iteration 14: Correct Cloud Run Deployment Region Defaults

- Objective: prevent future deployment commands from accidentally targeting a region other than the existing production Cloud Run service.
- Confirmed state: project `pc-recomendation-project`; service `hardware-intelligence-api`; production and Artifact Registry regions `me-central1`; current revision `hardware-intelligence-api-00005-kvd`.
- Files corrected: both Cloud Run deployment scripts, active deployment documentation, CI region-default assertions, and engineering state files.
- Guard: both scripts reject empty service or registry regions and reject a service region other than `me-central1` before invoking `gcloud`, unless the caller explicitly opts into a non-production region. Intentional parameter and environment overrides remain supported.
- Safe defaults preserved: pricing scheduler, autonomous agents, and CPU startup seeding remain disabled.
- Validation: PowerShell static structure inspection, Bash syntax and isolated rejection-path checks, active region search, release tests, diff check, and complete diff review.
- Historical records: the earlier `me-central2` location-policy failure remains unchanged in prior evolution entries.
- Production impact: none; no Cloud Build, image push, Cloud Run deployment, traffic change, Vercel change, or production command ran.
- Data impact: none; no Neo4j, pricing, catalog, evidence, vendor, URL, or secret access.
- Risk: low. A non-production region now requires a deliberate opt-in; production defaults match the live service.
- Rollback: `git revert` the focused commit. No runtime or data rollback is needed because this iteration does not deploy.
- Performance record: first CPU request 1.795s; warm requests 1.200s, 1.000s, and 0.879s; median warm improved from approximately 20.8s to 1.000s; result count 24; payload 47,514 bytes.
- Production smoke record: 14 passed, 1 optional skipped, 0 required failures.

## 2026-07-12 — Iteration 15: Neo4j Capacity Assessment and Migration Plan

- Objective: assess production Neo4j capacity with read-only queries and prepare a reversible migration plan.
- CI prerequisite: GitHub Actions run `29183468092` for deployment-region commit `20d5dcde327d5d4751437d693794ca766b26228b` passed.
- Evidence: Neo4j reported Kernel `5.27-aura`, Enterprise edition, Cypher `5`/`25`; aggregate inventory returned 200,000 nodes, 208,319 relationships, 149 ONLINE indexes, and 101 constraints.
- Domain counts: 202 Products, 38 PriceSnapshots, 32 RegionalPriceSnapshots, 22 Vendors, 3 ProductURLs, 137 CanonicalEvidence, 5 CanonicalSources, and 1,368 FieldEvidence nodes.
- Capacity evidence: a seven-day read-only Cloud Run log scan found 40 capacity/limit matches and 2 write-rejection-pattern matches. Exact Aura tier, capacity percentage, storage, and RAM utilization were not exposed by Cypher and require Aura Console/billing verification.
- Options compared: AuraDB Professional through Google Cloud Marketplace, direct AuraDB Professional, self-hosted Neo4j Enterprise on Compute Engine, and Spanner Graph. Recommendation is larger AuraDB Professional; direct purchase is the default pending billing verification because provider promotional-credit treatment is not assumed.
- Runbook recorded: freeze writers; confirm safe-off flags; create target; snapshot/export; import; compare counts/schema; verify searches/readiness/Saudi prices; approve secret versions; approve Cloud Run revision; smoke test; observe; rollback via previous secrets/revision.
- Safety: no database mutation, import/export, index/constraint change, secret change, Cloud Run/Vercel deployment, Neo4j mutation, or production data change occurred.
- Rollback: this documentation-only iteration is reverted with `git revert`; the future migration rollback is previous Secret Manager versions plus the prior Cloud Run revision while retaining the old database.
