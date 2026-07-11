# Next Task

## Verify The Focused Release In Production

After the focused commit is pushed, verify its automatic Railway/Vercel deployments from a network-enabled environment with the actual Vercel production URL.

### Scope

- Run `npm run smoke:production` against Railway and Vercel.
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
- No localhost/127.0.0.1 production target is detected.
- Admin-only routes reject unauthenticated requests.
- The workflow remains GET-only and returns useful exit codes.
- Backend tests/compile run in a Python-enabled environment.
- State files and the following iteration prompt are updated.

### Risk

Low; read-only verification only.
