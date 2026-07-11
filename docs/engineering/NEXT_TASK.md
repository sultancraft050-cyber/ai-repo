# Next Task

## Inspect And Resolve The First Automated CI Run

The reliability workflow is now defined, but its first GitHub-hosted run must confirm that backend tests and repository checks work in the supported environment.

### Scope

- Inspect the first workflow run for backend, frontend, and contract/tooling jobs.
- Fix only workflow-caused failures or clearly isolated CI configuration issues.
- Record test counts and any genuinely integration-only failures.
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

Read `AGENTS.md` and all files under `docs/engineering/` first. Inspect Git status and preserve unrelated frontend edits. Inspect the first GitHub Actions run for `.github/workflows/ci.yml`, then fix only workflow-caused failures. Do not change Cloud Run, Vercel, Neo4j, catalog, pricing, URLs, secrets, or readiness rules. Run the affected checks, `git diff --check`, review the complete diff, update `CURRENT_STATE.md`, append `EVOLUTION_LOG.md`, replace `NEXT_TASK.md`, and generate the next standalone prompt.
