# Current Engineering State

Updated: 2026-07-11

## Objective

Provide trustworthy Saudi PC component discovery, manual picking, and build generation using confirmed specifications, explicit compatibility rules, and Saudi market evidence.

## Architecture

- Frontend: Next.js App Router, React, TypeScript, Tailwind, XState.
- Backend: FastAPI with Neo4j repositories and compatibility/build services.
- Database: Neo4j is the graph source of truth.
- Deployment: Railway backend, Vercel frontend, Neo4j deployment.
- Canonical flow: dataset -> staged record -> evidence/enrichment -> hybrid review -> controlled commit.
- Pricing flow: Product/Vendor/ProductURL plus append-only PriceSnapshot and RegionalPriceSnapshot nodes.

## Commands And Baseline

- Backend: `python -m pytest`, `python -m compileall app` from `backend`.
- Frontend: `npm run typecheck`, `npm run build`, `npm run ui:check` from `frontend`.
- Repository: `git diff --check`.
- Frontend typecheck, production build, and UI contract checks pass for the current worktree.
- The local shell provides Node.js but not `python`, `py`, Docker, or an installed WSL distribution; backend tests and compile require CI or another Python-enabled environment.

## Deployment And Health

- Railway backend uses the backend Dockerfile and exposes `/health`.
- Vercel frontend uses `NEXT_PUBLIC_API_BASE_URL` pointing to Cloud Run.
- Production health must include application health and Neo4j connectivity.
- Secrets are environment-only and must never enter frontend configuration.
- Smoke command: `npm run smoke:production` with `SMOKE_BACKEND_URL`, `SMOKE_FRONTEND_URL`, and optionally `SMOKE_SHARED_BUILD_URL`.
- Backend release metadata: public `/health` JSON.
- Frontend release metadata: public `/release` JSON.
- Public release fields: `service`, `environment`, `release`, `git_sha`, `build_time`, `api_contract_version`.
- Current API contract version: `1`.
- Compatibility rule: matching API contract versions are compatible even when release identifiers or Git SHAs differ; mismatches are incompatible; missing metadata is unverifiable.
- Cloud Run URL: `https://hardware-intelligence-api-lywizc5z5q-ww.a.run.app`.
- Vercel URL: `https://frontend-lac-nine-09j4x45cj5.vercel.app`.
- Shared-build slug: not configured for smoke testing.

## Risks And Invariants

- Startup graph mutation must remain explicitly opt-in.
- Catalog conflicts and inferred specifications require review/evidence.
- Saudi pricing coverage and freshness remain uneven by category.
- Readiness states are `compatibility_ready_exact`, `compatibility_ready_family`, `metadata_only`, and `conflict_requires_review`.
- Canonical-only operations do not mutate Saudi prices.
- Price history is append-only.
- The working tree contains unrelated edits in `frontend/components/SoloFounderOpsPanel.tsx` and `frontend/types/builder.ts`; preserve them.
- Production Cloud Run/Vercel smoke verification is passing; no production result was fabricated.
- Smoke workflow syntax is valid; a run with only the known Railway URL correctly reports required checks as unavailable and exits non-zero.
- The release contract is implemented locally but not yet deployed or verified against live Railway/Vercel targets.

## Focused Release Status

- Branch: `master`, tracking `origin/master`.
- Release baseline: `811c63129053c08247c91a1805a75a703d1d446e`.
- Focused commit: `10d38581b2a991ad372064609838cb8ac8bff267` (`chore: add safe startup and release verification`).
- Push status: pushed to `origin/master`; remote verification returned the same SHA.
- CI status: no repository CI workflow was found; backend validation remains pending.
- Railway deployment: retired historical fallback; the old hostname returned `404 Application not found`.
- Cloud Run deployment: healthy at the recorded Cloud Run URL.
- Vercel deployment: healthy at the recorded Vercel URL.
- Live release compatibility: compatible; API contract version `1`.

## Google Cloud Run Migration

- Intended platform: Google Cloud Run.
- Service: `hardware-intelligence-api`.
- Region: `me-central2`.
- Artifact Registry region: `me-central1`; repository creation in `me-central2` was rejected by Google Cloud, so the deployment script supports separate Cloud Run and registry regions.
- Deployment scripts: `scripts/deploy-cloud-run.ps1` and `scripts/deploy-cloud-run.sh`.
- Deployment method: Cloud Build from the `backend` source context into Artifact Registry, then Cloud Run.
- Resource target: request-based, 1 CPU, 512MiB, min 0, max 1, port 8080.
- Required secret names: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `ANALYST_API_KEY`, `ADMIN_API_KEY`, `SUPER_ADMIN_API_KEY`.
- Vercel API variable: `NEXT_PUBLIC_API_BASE_URL`; migration remains pending until the Cloud Run URL is verified.
- Cloud Run preparation validation: PowerShell deployment script parsed; frontend/release checks passed.
- Cloud Run deployment status: healthy and smoke-verified.
- Cloud Run image build: `dfd3d99f-4624-4867-9a92-269764064053`; image tag `me-central1-docker.pkg.dev/pc-recomendation-project/pc-builder/hardware-intelligence-api:ac6f32b`.
- Google Cloud preflight: authenticated project `pc-recomendation-project`, billing enabled, required APIs enabled, seven secrets present, runtime service account created, per-secret accessor bindings created, Artifact Registry `pc-builder` created in `me-central1`.

## Safe Startup Defaults

- `PRICING_SCHEDULER_ENABLED=false`
- `AUTONOMOUS_AGENTS_ENABLED=false`
- `CPU_SPECS_SEED_ON_START=false`

Workers and CPU seeding may be enabled intentionally through environment configuration after review.

## Approval Boundaries

Approval is required for protected-data deletion, production secret changes, destructive migrations, ambiguous identity merges, trusted-source conflict resolution, autonomous graph mutation, and recommendation-governance changes.
