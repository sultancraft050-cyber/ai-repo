# Next Task

## Deploy And Verify Cloud Run Backend

The repository is prepared for Cloud Run, while the known Railway hostname returns `404 Application not found`. Deploy the existing backend to Cloud Run and verify it before moving Vercel traffic.

### Scope

- Confirm Google Cloud project, billing, Artifact Registry, Secret Manager, and runtime service-account access.
- Run `scripts/deploy-cloud-run.ps1` or `scripts/deploy-cloud-run.sh`.
- Verify Cloud Run `/health`, `/health/neo4j`, and `/openapi.json`.
- Update Vercel `NEXT_PUBLIC_API_BASE_URL` only after Cloud Run passes verification.
- Run `npm run smoke:production` against the correct Railway and Vercel URLs.
- Confirm backend `/health` and frontend `/release` expose API contract version `1`.
- Capture Railway version, health, Neo4j health, OpenAPI paths, admin protection, public routes, and API routing.
- Provide a shared-build URL if one exists and verify it loads.
- Record whether frontend/backend release metadata is compatible.

### Exclusions

- No catalog staging or commit.
- No URL ingestion or price mutation.
- No Neo4j cleanup or count-changing operation.
- No secret value changes; optional public release variables may be configured only through the deployment provider.
- No worker, scheduler, or startup seeding enablement.

### Acceptance Criteria

- All required checks pass or have a documented external blocker.
- Release compatibility reports `compatible`.
- Cloud Run exposes `api_contract_version: "1"` and the smoke workflow reports `compatible`.
- The Cloud Run URL is recorded and Vercel routes to it.
- No localhost/127.0.0.1 production target is detected.
- Admin-only routes reject unauthenticated requests.
- The workflow remains GET-only and returns useful exit codes.
- Backend tests/compile run in a Python-enabled environment.
- State files and the following iteration prompt are updated.

### Risk

Low; read-only verification only.
