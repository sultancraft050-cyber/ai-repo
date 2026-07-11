# Next Task

## Diagnose The Backend Full-Suite CI Failure

The picker now renders categories progressively, but the first GitHub-hosted workflow run still has a backend full-suite failure. The next iteration should identify that exact failing test before deeper backend query optimization.

### Scope

- Inspect run `29164807695`, especially the backend full-suite failure.
- Reproduce the failing test under Python 3.12 when possible.
- Fix only a confirmed repository or CI issue; do not weaken assertions.
- Record test counts and any genuinely integration-only failures.
- Do not optimize category queries until the CI failure is understood.
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
- Backend tests and compile run in GitHub Actions' Python 3.12 environment.
- State files and the following iteration prompt are updated.

### Likely files

- `.github/workflows/ci.yml`
- backend test configuration only if a CI-specific issue is proven

### Risk

Low; CI-only validation and configuration correction.

### Following iteration prompt

Read `AGENTS.md` and all files under `docs/engineering/` first. Inspect Git status and preserve unrelated frontend edits. Diagnose the backend full pytest failure in GitHub Actions run `29164807695` under Python 3.12. Reproduce and fix only the confirmed issue, without changing Cloud Run, Vercel, Neo4j, catalog, pricing, URLs, secrets, readiness rules, or manual-picker behavior. Run the affected tests plus compile, frontend checks, release checks, and `git diff --check`; review the complete diff; update the engineering state files; and generate the next standalone prompt.
