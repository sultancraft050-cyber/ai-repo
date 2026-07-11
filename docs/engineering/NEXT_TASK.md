# Next Task

## Verify And Continue Product Search Performance Work

The first CPU optimization removes the confirmed N+1 price-query pattern and CI is green. Deployment is pending because this shell lacks `gcloud`; the next iteration should deploy from a gcloud-enabled environment and collect post-change measurements before selecting more work.

### Scope

- Confirm CI and production deployment of the batch-price-read optimization.
- Record cold and at least three warm CPU samples using the same request.
- Compare result identity, readiness, cheapest price, vendor, count, and payload size.
- Profile the remaining slowest stage before selecting another optimization.
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

Read `AGENTS.md` and all files under `docs/engineering/` first. Inspect Git status and preserve unrelated frontend edits. Verify CI and the deployed Cloud Run revision containing the batch product-search price query. Measure the same CPU request cold and at least three times warm, compare identity/readiness/price/vendor correctness, and profile the remaining slow stage. Implement at most one additional evidence-supported read-only optimization only if needed. Do not change readiness, compatibility, pricing semantics, solver, ingestion, or identity behavior. Run focused tests, full backend pytest, compile, release checks, production smoke, and `git diff --check`; update engineering state and generate the next standalone prompt.
