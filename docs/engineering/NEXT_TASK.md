# Next Task

## Obtain Backend CI Failure Evidence And Resolve It

The backend full pytest step remains red, but the public GitHub API does not expose its logs without repository admin rights. The next iteration must obtain the exact failure from an authenticated GitHub Actions view or reproduce it under Python 3.12 before changing code.

### Scope

- Inspect run `29164807695`, especially the backend full-suite failure.
- Obtain the failed step log for job `86575990875` through an authorized GitHub Actions interface, or run the suite in Python 3.12.
- Reproduce the failing test under Python 3.12 when possible.
- Fix only a confirmed repository or CI issue; do not weaken assertions.
- Record test counts and any genuinely integration-only failures.
- Do not optimize category queries until the CI failure is understood.
- Do not guess at the failing test from job metadata alone.
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

Read `AGENTS.md` and all files under `docs/engineering/` first. Inspect Git status and preserve unrelated frontend edits. Obtain the backend failure log for GitHub Actions run `29164807695`, job `86575990875`, through an authorized interface or reproduce the suite under Python 3.12. Identify the exact test and root cause before editing. Fix only the confirmed issue, without changing Cloud Run, Vercel, Neo4j, catalog, pricing, URLs, secrets, readiness rules, or manual-picker behavior. Run the affected tests, compile, full pytest, frontend checks if needed, release checks, and `git diff --check`; review the complete diff; update the engineering state files; and generate the next standalone prompt.
