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
