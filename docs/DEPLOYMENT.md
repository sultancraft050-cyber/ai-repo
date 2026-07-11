# Saudi PC Buying Assistant Deployment Checklist

This MVP deploys as three pieces:

- Frontend: Next.js on Vercel
- Backend: FastAPI on Railway first, with Render or Fly.io as acceptable alternatives
- Database: Neo4j Aura

No ingestion, broad discovery, or known URL refresh should run during the first deployment unless the founder intentionally enables it later.

## 1. Neo4j Aura

1. Create a Neo4j AuraDB instance.
2. Save the connection URI, username, password, and database name in the backend platform secrets.
3. Use a `neo4j+s://...databases.neo4j.io` URI.
4. Do not paste Aura credentials into Vercel or any frontend env var.
5. After backend deploy, check `GET /health/neo4j`.

Required backend env:

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

## 2. Backend, Railway

Recommended Railway settings:

- Root directory: `backend`
- Build: Dockerfile or Python project auto-detect
- Start command if not using Dockerfile:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The backend Dockerfile also respects Railway's `PORT` env var.

Required backend env:

- `ENVIRONMENT=production`
- `MARKET_DATA_MODE=free`
- `BACKEND_VERSION=0.1.0`
- `FRONTEND_VERSION=0.1.0`
- `API_CONTRACT_VERSION=1`
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`
- `FRONTEND_URL=https://your-domain.example`
- `BACKEND_URL=https://api.your-domain.example`
- `CORS_ORIGINS=https://your-domain.example`
- `AUTH_REQUIRED=true`
- `ANALYST_API_KEY`
- `ADMIN_API_KEY`
- `SUPER_ADMIN_API_KEY`

Optional source keys:

- `SERPAPI_KEY`
- `EBAY_BROWSE_TOKEN`
- `BESTBUY_API_KEY`
- `AMAZON_PAAPI_ACCESS_KEY`
- `AMAZON_PAAPI_SECRET_KEY`
- `AMAZON_PAAPI_PARTNER_TAG`

For first launch with `MARKET_DATA_MODE=free`, leave optional source keys empty. Startup must not require SerpAPI.

Safe-off launch env:

- Startup graph mutation is opt-in. Keep these values explicitly disabled unless the founder is running a controlled operation:

- `CPU_SPECS_SEED_ON_START=false`
- `PRICING_SCHEDULER_ENABLED=false`
- `AUTONOMOUS_AGENTS_ENABLED=false`
- `PUBLIC_ANALYTICS_ENABLED=true`
- `PUBLIC_RATE_LIMIT_WINDOW_SECONDS=60`
- `PUBLIC_RATE_LIMIT_MAX_REQUESTS=120`

If a worker or seed is intentionally enabled, record the operation, verify affected graph counts, and return the flag to `false` before the next normal deployment.

## 3. Backend, Render or Fly.io

Render:

- Root directory: `backend`
- Environment: Docker or Python
- Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Fly.io:

- Use `backend/Dockerfile`.
- Set the same backend env vars as Railway.
- Verify the app binds to `${PORT:-8000}`.

## 4. Backend, Google Cloud Run

Cloud Run is the preferred replacement for the expired Railway service. The repository provides `scripts/deploy-cloud-run.ps1` and `scripts/deploy-cloud-run.sh`.

Defaults:

- Service: `hardware-intelligence-api`
- Region: `me-central2`
- Artifact Registry region: `me-central1` for this project; `me-central2` is rejected by the project’s registry location policy.
- CPU: `1`
- Memory: `512Mi`
- Minimum instances: `0`
- Maximum instances: `1`
- Container port: `8080`
- Ingress: public; application API-key authorization remains enabled

Required Secret Manager secret names:

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`
- `ANALYST_API_KEY`
- `ADMIN_API_KEY`
- `SUPER_ADMIN_API_KEY`

Create or update secret versions interactively without putting values in source control:

```powershell
gcloud secrets create SECRET_NAME --replication-policy=automatic
gcloud secrets versions add SECRET_NAME --data-file=PATH_TO_LOCAL_SECRET_FILE
```

Grant the Cloud Run runtime identity access only to these secrets:

```powershell
gcloud projects add-iam-policy-binding YOUR_GOOGLE_PROJECT_ID `
  --member="serviceAccount:pc-builder-runtime@YOUR_GOOGLE_PROJECT_ID.iam.gserviceaccount.com" `
  --role="roles/secretmanager.secretAccessor"
```

Required non-secret Cloud Run variables:

- `ENVIRONMENT=production`
- `MARKET_DATA_MODE=free`
- `FRONTEND_URL`
- `CORS_ORIGINS`
- `BACKEND_VERSION`
- `API_CONTRACT_VERSION=1`
- `PRICING_SCHEDULER_ENABLED=false`
- `AUTONOMOUS_AGENTS_ENABLED=false`
- `CPU_SPECS_SEED_ON_START=false`

Create the Artifact Registry repository and runtime service account through Google Cloud Console or `gcloud`, grant the runtime service account only `roles/secretmanager.secretAccessor`, then run:

```powershell
.\scripts\deploy-cloud-run.ps1 `
  -ProjectId "YOUR_GOOGLE_PROJECT_ID" `
  -FrontendUrl "https://YOUR_VERCEL_DOMAIN" `
  -RegistryRegion "me-central1"
```

The script builds only `backend/` with Cloud Build, deploys the existing Dockerfile, references Secret Manager by name, discovers the Cloud Run URL, and updates `BACKEND_URL` to that URL. It never prints secret values and does not modify Neo4j or Vercel.

Verify the returned service URL before changing Vercel:

```powershell
curl.exe -i "https://YOUR_CLOUD_RUN_URL/health"
curl.exe -i "https://YOUR_CLOUD_RUN_URL/health/neo4j"
curl.exe -i "https://YOUR_CLOUD_RUN_URL/openapi.json"
```

Then set Vercel’s existing `NEXT_PUBLIC_API_BASE_URL` to the Cloud Run URL and run `npm run smoke:production`.

## 5. Frontend, Vercel

Recommended Vercel settings:

- Root directory: `frontend`
- Install command: `npm ci`
- Build command: `npm run build`
- Output: Next.js default

Required frontend env:

- `NEXT_PUBLIC_API_BASE_URL=https://api.your-domain.example`
- `NEXT_PUBLIC_SITE_URL=https://your-domain.example`
- `NEXT_PUBLIC_APP_VERSION=0.1.0`
- `NEXT_PUBLIC_API_CONTRACT_VERSION=1`
- `NEXT_PUBLIC_GIT_SHA=` (optional public deployment SHA)
- `NEXT_PUBLIC_BUILD_TIME=` (optional public ISO-8601 build time)

Do not add backend secrets to Vercel. Only `NEXT_PUBLIC_*` values are allowed on the frontend.

## 6. Production Verification

Repeatable non-destructive smoke test from the repository root:

```powershell
$env:SMOKE_BACKEND_URL = "https://your-railway-domain.example"
$env:SMOKE_FRONTEND_URL = "https://your-vercel-domain.example"
$env:SMOKE_FRONTEND_API_URL = $env:SMOKE_BACKEND_URL
npm run smoke:production
```

Optional shared-build verification can be added with `SMOKE_SHARED_BUILD_URL`. The workflow uses GET requests only and returns a non-zero exit code for required failures.

Release compatibility is based on `api_contract_version`, not identical frontend/backend Git commits. Matching API contract versions are compatible; different versions are incompatible and fail the smoke command; unavailable or incomplete metadata is reported as unverifiable.

Run these after deployment.

Public checks:

- `GET /health`
- `GET /health/neo4j`
- Open `/`
- Open `/sitemap.xml`
- Open one known `/build/share/{slug}` if available

Founder/admin checks with analyst/admin API key:

- `GET /ops/deployment-checklist?region=SA`
- `GET /ops/runtime-health`
- `GET /ops/mvp-health-dashboard?region=SA`
- `GET /ops/build-failure-summary?region=SA`
- `GET /ops/market-coverage-summary?region=SA`

Deployment checklist should report:

- env completeness
- Neo4j connectivity
- source configuration
- runtime health
- build readiness
- launch blockers
- `launch_ready`
- frontend/backend version info

## 7. Launch Safety Checklist

- Confirm `/build/share/{slug}` does not expose user email, internal audit IDs, API traces, raw graph IDs, or secrets.
- Confirm public actions are rate limited: build generation, save build, deal submission, feedback, and analytics.
- Confirm `CORS_ORIGINS` only includes production frontend domains.
- Confirm no `.env` files are committed.
- Confirm source keys are backend-only and absent from frontend build output.
- Confirm `MARKET_DATA_MODE=free` works without SerpAPI.
- Confirm `PRICING_SCHEDULER_ENABLED=false` for first public deploy.
- Confirm no ingestion, discovery, or URL refresh jobs are enabled unless intentionally configured.
- Confirm warnings for VAT, shipping, warranty, marketplace risk, and stale pricing remain visible.

## 8. Founder Operating Loop

Review these daily after public launch:

- `GET /ops/build-failure-summary?region=SA`
- `GET /ops/market-coverage-summary?region=SA`
- `GET /ops/founder-insights?region=SA`
- `GET /ops/mvp-health-dashboard?region=SA`
- `GET /ops/catalog-growth-workflow?region=SA`

Use them to decide the next safe catalog improvement target. Prefer manual product URLs or controlled dry-runs over broad ingestion.

## 9. Rollback Guide

Frontend, Vercel:

1. Open the Vercel deployment list.
2. Promote the previous known-good deployment.
3. Recheck `/`, `/build/share/{slug}`, and the deal submission form.

Backend, Railway / Render / Fly.io:

1. Roll back to the previous image or commit.
2. Keep Neo4j untouched unless the incident is confirmed data corruption.
3. Recheck `/health`, `/health/neo4j`, and `/ops/deployment-checklist?region=SA`.
4. If the issue involved public mutations, review analytics, feedback, saved builds, and ProductURL writes before re-enabling traffic.

Neo4j Aura:

1. Prefer application rollback first.
2. Use Aura restore only for confirmed destructive graph corruption.
3. After restore, run deployment checklist and a Saudi build generation smoke test.

## 10. Incident Checklist

- Disable public write-heavy actions at the platform edge if abuse is active.
- Keep broad ingestion and refresh jobs off until the incident is understood.
- Check runtime health, slow endpoints, and deployment blockers.
- Review recent feedback and deal submissions for user-visible impact.
- Write a short founder note: impact, fix, verification, next prevention step.
