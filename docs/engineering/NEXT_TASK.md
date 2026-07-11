# Next Task

## Profile And Optimize The CPU Product Search Endpoint

After the fixture-path correction is verified green in CI, the highest measured product issue is the CPU search endpoint at approximately 20.7 seconds, which dominates manual-picker completion time.

### Scope

- Measure CPU `/products/search` execution time, Neo4j query time, and response construction separately.
- Inspect the exact query and returned fields before changing code.
- Apply only evidence-supported, read-only query or payload optimization.
- Preserve readiness, identity, Saudi price, and pagination semantics.
- Keep production data and deployment configuration unchanged.

### Exclusions

- No catalog staging or commit.
- No URL ingestion or price mutation.
- No Neo4j cleanup or count-changing operation.
- No secret value changes; optional public release variables may be configured only through the deployment provider.
- No worker, scheduler, or startup seeding enablement.

### Acceptance Criteria

- Backend CI must be green before query optimization is committed.
- Release compatibility reports `compatible`.
- Existing production smoke remains compatible after backend validation.
- No localhost/127.0.0.1 production target is detected.
- Admin-only routes reject unauthenticated requests.
- The workflow remains GET-only and returns useful exit codes.
- Backend tests and compile run in GitHub Actions' Python 3.12 environment.
- State files and the following iteration prompt are updated.

### Likely files

- product-search API and repository files identified by profiling
- focused product-search tests

### Risk

Low to medium; read-only query performance work.

### Following iteration prompt

Read `AGENTS.md` and all files under `docs/engineering/` first. Inspect Git status and preserve unrelated frontend edits. Confirm the backend CI run after the fixture-path fix is green. Then profile the CPU `/products/search` path without mutating production data. Separate HTTP, repository, Neo4j, and response-serialization time; inspect only the relevant query and payload fields; and implement one evidence-supported read-only optimization. Do not change readiness, compatibility, pricing, solver, ingestion, or identity behavior. Run focused tests, full backend pytest, compile, release checks, frontend checks when applicable, and `git diff --check`; update engineering state and generate the next standalone prompt.
