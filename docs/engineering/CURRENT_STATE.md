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
- Vercel frontend must use `NEXT_PUBLIC_API_BASE_URL` pointing to Railway.
- Production health must include application health and Neo4j connectivity.
- Secrets are environment-only and must never enter frontend configuration.
- Smoke command: `npm run smoke:production` with `SMOKE_BACKEND_URL`, `SMOKE_FRONTEND_URL`, and optionally `SMOKE_SHARED_BUILD_URL`.
- Backend release metadata: public `/health` JSON.
- Frontend release metadata: public `/release` JSON.
- Public release fields: `service`, `environment`, `release`, `git_sha`, `build_time`, `api_contract_version`.
- Current API contract version: `1`.
- Compatibility rule: matching API contract versions are compatible even when release identifiers or Git SHAs differ; mismatches are incompatible; missing metadata is unverifiable.
- Known Railway URL: `https://ai-repo-production-d0cb.up.railway.app`.
- The Vercel production URL and shared-build slug are not present in the repository.

## Risks And Invariants

- Startup graph mutation must remain explicitly opt-in.
- Catalog conflicts and inferred specifications require review/evidence.
- Saudi pricing coverage and freshness remain uneven by category.
- Readiness states are `compatibility_ready_exact`, `compatibility_ready_family`, `metadata_only`, and `conflict_requires_review`.
- Canonical-only operations do not mutate Saudi prices.
- Price history is append-only.
- The working tree contains unrelated edits in `frontend/components/SoloFounderOpsPanel.tsx` and `frontend/types/builder.ts`; preserve them.
- Live Railway requests were unavailable from the current network sandbox; no production result was fabricated.
- Smoke workflow syntax is valid; a run with only the known Railway URL correctly reports required checks as unavailable and exits non-zero.
- The release contract is implemented locally but not yet deployed or verified against live Railway/Vercel targets.

## Focused Release Status

- Branch: `master`, tracking `origin/master`.
- Release baseline: `811c63129053c08247c91a1805a75a703d1d446e`.
- Focused commit: `10d38581b2a991ad372064609838cb8ac8bff267` (`chore: add safe startup and release verification`).
- Push status: pushed to `origin/master`; remote verification returned the same SHA.
- CI status: no repository CI workflow was found; backend validation remains pending.
- Railway deployment: unverified/mismatched. The known hostname returns `404 Application not found` for `/health`, `/health/neo4j`, `/openapi.json`, and the admin checklist.
- Vercel deployment: pending; production URL unavailable locally.
- Live release compatibility: unverified until the correct Railway service URL and Vercel URL are confirmed.

## Google Cloud Run Migration

- Intended platform: Google Cloud Run.
- Service: `hardware-intelligence-api`.
- Region: `me-central2`.
- Deployment scripts: `scripts/deploy-cloud-run.ps1` and `scripts/deploy-cloud-run.sh`.
- Deployment method: Cloud Build from the `backend` source context into Artifact Registry, then Cloud Run.
- Resource target: request-based, 1 CPU, 512MiB, min 0, max 1, port 8080.
- Required secret names: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `ANALYST_API_KEY`, `ADMIN_API_KEY`, `SUPER_ADMIN_API_KEY`.
- Vercel API variable: `NEXT_PUBLIC_API_BASE_URL`; migration remains pending until the Cloud Run URL is verified.
- Cloud Run preparation validation: PowerShell deployment script parsed; frontend/release checks passed.
- Cloud Run deployment status: not attempted because `gcloud`, Docker, Python, and WSL are unavailable.

## Safe Startup Defaults

- `PRICING_SCHEDULER_ENABLED=false`
- `AUTONOMOUS_AGENTS_ENABLED=false`
- `CPU_SPECS_SEED_ON_START=false`

Workers and CPU seeding may be enabled intentionally through environment configuration after review.

## Approval Boundaries

Approval is required for protected-data deletion, production secret changes, destructive migrations, ambiguous identity merges, trusted-source conflict resolution, autonomous graph mutation, and recommendation-governance changes.
