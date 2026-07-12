# Next Task

## Profile The Remaining Product Search Stage

The batch price-read optimization is deployed and verified. CPU warm median improved from approximately 20.8 seconds to 1.000 second while count and payload remained stable. The next iteration should profile the remaining read-only CPU search stages before selecting at most one additional optimization.

### Scope

- Preserve the verified deployment baseline and repeat measurements only as needed for comparison.
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

Read `AGENTS.md` and all files under `docs/engineering/` first. Inspect Git status, recent history, and the complete diff. Use the verified CPU baseline (first 1.795s; warm 1.200s, 1.000s, 0.879s; 24 results; 47,514 bytes; smoke 14 passed, 1 optional skipped, 0 required failures) and profile the remaining read-only product-search stages. Implement at most one evidence-supported optimization only if a specific bottleneck is confirmed. Preserve identity, readiness, Saudi price, vendor, sorting, and pagination semantics. Do not deploy, mutate Neo4j, change secrets, or enable workers. Run focused tests, full backend pytest where available, compile, release checks, production smoke only if explicitly authorized, and `git diff --check`; update engineering state and generate the next standalone prompt.
