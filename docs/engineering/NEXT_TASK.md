# Next Task

## Run Backend Validation In A Supported Python Environment

Production Cloud Run/Vercel smoke verification now passes. The highest remaining validation gap is backend pytest/compile, which cannot run in the current shell because Python is unavailable.

### Scope

- Run `python -m pytest` from `backend` in CI or a supported Python environment.
- Run `python -m compileall app` from `backend`.
- Record the backend test result and any environment-specific failures.
- Keep production data and deployment configuration unchanged.

### Exclusions

- No catalog staging or commit.
- No URL ingestion or price mutation.
- No Neo4j cleanup or count-changing operation.
- No secret value changes; optional public release variables may be configured only through the deployment provider.
- No worker, scheduler, or startup seeding enablement.

### Acceptance Criteria

- All required checks pass or have a documented external blocker.
- Release compatibility reports `compatible`.
- Existing production smoke remains compatible after backend validation.
- No localhost/127.0.0.1 production target is detected.
- Admin-only routes reject unauthenticated requests.
- The workflow remains GET-only and returns useful exit codes.
- Backend tests/compile run in a Python-enabled environment.
- State files and the following iteration prompt are updated.

### Risk

Low; read-only verification only.
