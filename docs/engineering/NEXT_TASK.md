# Next Task

## Resolve Railway Deployment/Hostname Mismatch

The pushed release is confirmed on GitHub, but the known Railway hostname returns `404 Application not found`. Resolve the service URL or deployment mapping before attempting buyer or catalog work.

### Scope

- Confirm the Railway service’s actual public domain and deployed commit.
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
- The known 404 hostname is either corrected or explicitly retired from deployment documentation.
- No localhost/127.0.0.1 production target is detected.
- Admin-only routes reject unauthenticated requests.
- The workflow remains GET-only and returns useful exit codes.
- Backend tests/compile run in a Python-enabled environment.
- State files and the following iteration prompt are updated.

### Risk

Low; read-only verification only.
