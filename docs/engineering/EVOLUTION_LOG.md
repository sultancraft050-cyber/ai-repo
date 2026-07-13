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

## 2026-07-12 — Iteration 16: Neo4j Node-Volume Inventory

- Objective: document the completed read-only aggregate inventory explaining the 200,000-node capacity use.
- Findings: 74 labels, 58 relationship types, 1,382 relationship-orphan nodes, 0 unlabeled nodes, and 1,545 nodes outside the top-25 groups. Top-25 label populations total 198,455 memberships (99.23%); multi-label overlap is explicit.
- Dominant groups: PolicyEnforcement, EvolutionAuditEvent, PromotionDecision, SandboxEvaluation, StabilizationAction, AlignmentAuditEvent, ObjectiveTradeoff, and related governance/audit groups.
- High-volume orphans: AuditEvent 504, PricingJob 353, and ConfidenceState 246. These are code-review signals, not deletion candidates.
- Safety: results came from read-only aggregate queries; no production data, schema, secrets, deployments, or application code changed.
- Decision: no deletion recommendation or approval. The next task is active-code producer and retention-policy review.

## 2026-07-12 — Iteration 17: Neo4j Operational Retention Audit

- Objective: trace high-volume operational labels to active code producers and propose evidence-based retention without mutation.
- CI prerequisite: run `29184971667` passed for commit `cd97a6c`.
- Producers: governance/evolution/alignment/autonomy APIs can persist by default; autonomous scheduling is disabled. Pricing APIs and worker remain active while the pricing scheduler is disabled. Audit and cognition state producers remain active.
- Growth: timestamped audited labels show zero 7-day and 30-day growth; 93,006 nodes were concentrated in the May 22–27 cohort, approximately 17,600/day during that window.
- Classification: ConfidenceState is KEEP_PERMANENTLY; AuditEvent and PricingJob require retention policies; 93,006 timestamped operational children are ARCHIVE_CANDIDATE; non-timestamped repeated decision children are CONSOLIDATE_CANDIDATE; DELETE_CANDIDATE is empty.
- Capacity proposal: clone rehearsal could reduce estimated online nodes to 106,994 (53.50%), but the measured active rate could refill headroom in about five days.
- Decision: `CLEANUP_BUYS_TIME_BUT_MIGRATION_REQUIRED`.
- Safety: no data/schema mutation, retention execution, secret change, deployment, or application-code change occurred.

## 2026-07-12 — Iteration 18: Neo4j Retention Approval and Clone-Rehearsal Preparation

- Objective: prepare owner approvals, exact read-only candidate previews, clone requirements, snapshot checks, parity controls, stop conditions, and rollback requirements.
- CI prerequisite: run `29185252408` passed for commit `3f1ea06`.
- Approval state: all nine owner roles remain `PENDING_OWNER_APPROVAL`; no names or approvals were inferred.
- Candidate package: four timestamped groups total up to 93,006 nodes; non-timestamped consolidation is deferred to a separate rehearsal. Core product, pricing, evidence, identity, user, and ConfidenceState labels are protected.
- Clone requirement: Neo4j 5.27-compatible managed target with capacity strictly above the 200,000-node source, isolated credentials/URI/network, and no production workers or Cloud Run connection.
- Rehearsal controls: first batch at most 100, later batches at most 500 after checkpoint approval, recount after each batch, zero-difference parity, >1% candidate drift stop, and no first-run consolidation.
- Billing/snapshot status: all console and credit questions are `MANUAL_VERIFICATION_REQUIRED` or `MANUAL_BILLING_VERIFICATION_REQUIRED`.
- Safety: documentation only; no snapshot/export, clone, data/schema mutation, deletion query, retention execution, secret change, deployment, or application-code change occurred.

## 2026-07-12 — Iteration 19: Website-Wide Feature Audit and Frontend Reliability Pass

- Objective: audit public routes and browser-facing controls and repair the highest-impact frontend interaction defects.
- Findings: the theme button had no handler or persistence, mobile navigation had no drawer, and two logo anchors were dead `#` links.
- Fixes: added a ThemeProvider with system preference/local-storage support and pre-paint bootstrap, accessible theme state labels, a responsive mobile navigation drawer, and root logo links.
- Validation: theme contract test, frontend typecheck, production build, UI contract check, release tests, and `git diff --check`; browser automation was unavailable and is explicitly deferred.
- Safety: no production API writes, Neo4j operations, secrets, Cloud Run/Vercel deployments, or application backend changes occurred.

## 2026-07-12 — Iteration 20: Browser Smoke and Accessibility Verification

- Objective: verify public frontend interactions against a local production build with Playwright and mocked API behavior.
- Coverage: home/theme, desktop and mobile navigation, `/build/manual`, `/build/generate`, `/release`, unknown-route recovery, console/page errors, and production localhost-target guard.
- Findings/fixes: Escape and outside-click did not close the mobile drawer; unknown routes lacked a home recovery link. Added deterministic drawer dismissal and a branded `not-found.tsx`.
- Validation: 7 Playwright tests passed, frontend typecheck/build/UI checks passed, release tests passed, and diff whitespace remained clean. Successful home light/dark desktop/mobile screenshots are generated only in ignored local test artifacts.
- Safety: API traffic was mocked locally; no production writes, Neo4j operations, secrets, Cloud Run/Vercel deployment, or data changes occurred.

## 2026-07-12 — Iteration 21: Frontend Production Verification

- Objective: validate the existing Vercel production alias after the frontend interaction work using local preflight and GET-only live checks.
- Local validation: `npm ci`, expected-target production build, typecheck, UI checks, seven Playwright tests, release tests, and diff checks passed.
- Live evidence: the known Vercel alias returned 200 for `/`, `/build/manual`, `/build/generate`, and `/release`, 404 for an unknown route, and passed live theme persistence and mobile drawer checks at 390×844. No production form was submitted.
- Deployment status: Vercel CLI/authentication was unavailable, so no deployment or project relinking occurred. Exact deployment ID/source SHA/environment-variable presence remains a manual Dashboard verification gate.
- Safety: no Cloud Run deployment, backend/configuration change, Neo4j operation, secret change, or production data mutation occurred.

## 2026-07-12 — Iteration 22: Verified Vercel Production Metadata

- Objective: record only the Vercel production metadata manually verified and supplied by the user.
- Provenance: team `sultancraft050-7155s-projects`, project `frontend`, deployment status `READY`, production alias `frontend-lac-nine-09j4x45cj5.vercel.app`, repository `sultancraft050-cyber/ai-repo`, branch `master`, source `33db991`, Next.js, and root `frontend`.
- Configuration: build command `npm run build`, install command `npm install`; the Production `NEXT_PUBLIC_API_BASE_URL` is present and its target was verified as the expected Cloud Run service.
- Conclusion: production provenance is `VERIFIED`; source `33db991` is newer than frontend feature commit `4222233`.
- Safety: documentation only; no Vercel connection/deployment, environment change, backend change, Neo4j operation, secret access, or data mutation occurred.

## 2026-07-12 — Iteration 23: Deterministic Workflow Fixtures and Accessibility Coverage

- Objective: exercise critical frontend workflows locally with deterministic synthetic fixtures and automated axe checks.
- Coverage: manual category loading/failure/retry and selection states; generated success/no-result/400/429/500/network/malformed states; shared-build success/failure; laptop/tablet layouts; light/dark/mobile/404 axe scans.
- Fixes: added category-only manual retry, filtered cleared failure warnings, corrected light-theme contrast override precedence, and added a no-compatible-build recovery notice.
- Dependency: added `@axe-core/playwright` only; no broad dependency upgrade or audit fix.
- Safety: all workflow requests were mocked locally; no production writes, Neo4j operations, secrets, environment changes, Cloud Run/Vercel deployments, or production payloads.

## 2026-07-12 — Iteration 24: Frontend Interaction Edge Cases

- Objective: close the remaining local interaction-test gaps without changing product semantics or contacting production.
- Coverage: 30 synthetic CPU products across the implemented load-more boundary, dedicated incomplete generated-build state, mobile drawer focus containment/return, and reduced-motion emulation.
- Fixes: corrected manual search filtering, attached the focus ref to the actual mobile menu trigger, added deterministic focus return, and added scoped reduced-motion rules.
- Safety: all requests remained fixture-backed; no production writes, Neo4j operations, secrets, environment changes, Cloud Run/Vercel deployments, or production payloads occurred.

## 2026-07-12 — Iteration 25: Static Audit of Unexpected Production POST Sources

- Objective: identify repository mechanisms capable of browser POST requests without sending any network request.
- Confirmed automatic source: homepage mount records `landing_page_visit` through `/analytics/events`; backend code attempts a Neo4j analytics-event write when connected.
- No Vercel Analytics, Speed Insights, third-party telemetry/error SDK, beacon, or service-worker producer is active. All other frontend POST callers require selection, submission, generation, workspace, or privileged control interaction.
- Attribution remains unknown because the four observed POST URLs were not captured. Theme static result is `LIKELY_TEST_SELECTOR_PROBLEM`.
- Missing document result: `WEBSITE_INTERACTION_EDGE_VERIFICATION.md` was never tracked; Iteration 24 updated the existing workflow-verification document.
- Safety: documentation-only static inspection; no production/backend request, browser navigation, Neo4j operation, secret access, or deployment occurred.

## 2026-07-12 — Iteration 26: Blocked-Request Production Verification

- Objective: prove a browser guard aborts every non-GET/HEAD request before transmission and run a guarded initial production load.
- Guard self-test: synthetic GET/HEAD continued, synthetic POST was aborted, and the local server received zero POSTs.
- Production: a fresh context with service workers blocked and routing installed before page creation observed zero blocked non-GET requests during initial load; no non-GET/HEAD request reached production.
- Closeout: the interaction sequence stopped returning output, so no unguarded retry was made and theme/drawer/manual/generated/404 interaction results remain unclaimed.
- Safety: no production write, Neo4j operation, secret change, deployment, or request body/header/cookie capture occurred.

## 2026-07-12 — Recovery: Guarded Initial-Load Verification

- Status: `PARTIAL_SAFE_VERIFICATION`.
- Preserved completed evidence only: synthetic GET/HEAD continued, synthetic POST aborted before transmission, synthetic server received zero POSTs, service workers were blocked, and routing preceded page creation/navigation.
- One guarded production initial load completed with zero blocked POST/PUT/PATCH/DELETE and zero non-GET/HEAD requests reaching production.
- Historical four-POST attribution remains unresolved; homepage `/analytics/events` remains a plausible static source only. No harmlessness or Neo4j effect was inferred.
- Theme, drawer, manual, generated, shared-build, reduced-motion, and full route interactions were not verified in recovery. No additional production request occurred.

## 2026-07-13 — Iteration 27: Product Image Rendering Reliability

- Objective: standardize visible product imagery without changing product records, API contracts, or selection behavior.
- Audit: the only active product-image renderers were the manual picker card artwork and selected-part summary row; generated/shared/saved/comparison contexts currently expose no image renderers.
- Implementation: added the strict `ProductImage` component with card, build-summary, and detail variants, explicit dimensions, contain fitting, category-aware local SVG placeholders, safe URL handling, accessible descriptions, and one-shot failure fallback.
- Tests: added synthetic Playwright coverage for approved external/local URLs, missing/unsafe URLs, stable frames, lazy loading, category placeholders, and fallback behavior. Existing workflow and axe suites remain fixture-backed.
- Safety: no production navigation, production write, image download, Neo4j operation, secret change, cloud-resource creation, or deployment occurred.

## 2026-07-13 — Iteration 28: Neo4j Migration Execution Readiness

- Objective: prepare an evidence-backed migration-readiness package without creating a target or touching production data.
- Audit: mapped 18 Neo4j writer families across startup, workers, schedulers, protected/API persistence, analytics, imports, user builds, telemetry, cognition, governance, evolution, alignment, autonomy, and ops/audit paths. Background scheduler/agent/startup-seed flags remain false, but manual/API writers require an explicit freeze.
- Decision: `READY_PENDING_MANUAL_APPROVALS`; recommend larger AuraDB Professional, migration before cleanup, clone-rehearsed retention, and source retention for rollback. Direct versus Marketplace purchase remains a billing-owner decision.
- Deliverables: execution-readiness plan, manual Aura/billing checklist, and approval record with parity, cutover, stop-condition, isolation, and rollback gates.
- Safety: repository-only inspection; no production query, mutation, snapshot/export, target creation, secret change, cloud cost, deployment, or traffic change occurred.

## 2026-07-13 — Iteration 29: Minimal Neo4j Migration Approval Gate

- Objective: reduce target-creation readiness to essential provider and approval facts only.
- Result: `BLOCKED_MISSING_ESSENTIAL_FACTS`; no source identifier, Aura tier/region/version/capacity verification, snapshot status, target selection/costs, budget, or approvals were supplied, so no readiness was inferred.
- Documentation: simplified the checklist, approval record, and readiness document; optional operational details were removed from the gate.
- Safety: documentation-only; no production query or mutation, snapshot/export/restore, target creation, secret change, deployment, traffic change, or cloud cost occurred.

## 2026-07-13 — Iteration 30: Minimal Neo4j Cleanup Preparation

- Objective: prepare exact technical selectors and a bounded clone-rehearsal procedure without executing cleanup.
- Result: `READY_FOR_CLONE_CLEANUP_REHEARSAL` only; production cleanup remains prohibited.
- Scope: 30-day timestamped operational children, terminal PricingJob records older than 90 days, AuditEvent records only after ownership resolution, and a separate non-destructive consolidation plan for non-timestamped groups.
- Safety: added selector, protection, batch, clone identity, parity, stop-condition, and rollback documentation. No production query, mutation, snapshot/export, clone, secret, deployment, traffic change, or cloud cost occurred.

## 2026-07-13 — Iteration 31: Relational Product Catalog Foundation

- Objective: add a disabled, local PostgreSQL-compatible foundation for canonical products, specifications, image metadata, stores, offers, price history, and import provenance without changing Neo4j behavior.
- Implementation: added SQLAlchemy/Alembic models and migration, lazy database configuration, read-only gated `/catalog/*` routes, synthetic SQLite tests, and catalog documentation. Catalog writes and startup seeding remain disabled.
- Safety: no production database connection, real import, external image download, storage resource, Neo4j operation, secret change, deployment, or cloud resource was used.

## 2026-07-13 — Iteration 32: Staged CSV/JSON Catalog Import Pipeline

- Objective: add a bounded local staging and review path for products, specifications, image metadata, stores, offers, and append-only price observations without exposing a write API.
- Implementation: added safe-off import configuration, strict normalization/identity matching, duplicate and ambiguity handling, dependency blocking, safe staged records/errors, lifecycle counts, an internal local-only CLI, and an atomic guarded commit service.
- Validation: synthetic CSV/JSON fixtures, focused parsing/matching/review/commit tests, full backend regression tests, and Alembic upgrade/downgrade rehearsal against disposable SQLite.
- Safety: all catalog/import/write flags remain false by default. No production database, real product/store/offer, external image, Neo4j operation, cloud resource, secret, or deployment was touched.

## 2026-07-13 — Iteration 33: Product Image Metadata Quality and Review Pipeline

- Objective: add deterministic metadata-only image evaluation, guarded review decisions, public eligibility filtering, and append-only review history without fetching image bytes.
- Implementation: added bounded URL/host policy, rights/provenance and metadata-quality checks, category heuristics, exact duplicate handling, primary replacement safeguards, `catalog_product_image_reviews`, local CLI commands, and staged-import integration behind a new safe-off flag.
- Validation: synthetic image fixtures and focused review/import/catalog tests, migration rehearsal, full backend tests, release tests, and diff checks. No external URL, production database, image, Neo4j graph, cloud resource, secret, or deployment was touched.
## 2026-07-13 — Iteration 34: Local Catalog Review and Import Operations Interface

Added a manually started, SQLite-only loopback operations interface for synthetic catalog fixture dry-runs, batch and staged-row review, guarded idempotent commits, image metadata decisions, duplicate groups, and local catalog inspection. The routes live only in a standalone app and are not mounted into production. No external URL or image is fetched, and no production database, Neo4j, cloud resource, secret, or deployment was touched. Catalog operations, import, image review, and writes remain opt-in and disabled by default.

## 2026-07-13 — Iteration 35: Authorized Product and Store Feed Mapping Templates

Added disabled, local-only, versioned JSON mappings for synthetic product, store, offer, specification, image metadata, and price observation feeds. The service validates authorization, entity/source types, strict identity requirements, Saudi country/currency/timezone rules, unknown fields, credential-like names, deterministic transform whitelists, version checksums, and safe provenance before reusing the existing staged import pipeline. Standalone operations pages and a fixture-only CLI provide validation, preview, comparison, and guarded staging. No real feed, connector, external request, image, production database, Neo4j operation, secret, cloud resource, or deployment was used.
