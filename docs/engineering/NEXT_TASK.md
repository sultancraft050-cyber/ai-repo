# Next Task

## Rehearse Neo4j Retention on a Larger Isolated Clone

The retention audit found up to 93,006 timestamped operational archive candidates and estimated 53.50% utilization after a 30-day clone rehearsal. Cleanup buys time, but the prior active-window rate could refill capacity in about five days; migration remains required.

### Scope

- Obtain owner decisions for governance history, security audit retention, pricing-job retention, and cognition state.
- Create or restore a larger isolated managed clone only after billing and database-owner approval.
- Implement read-only selector previews for the 93,006 timestamped candidates and non-timestamped consolidation groups.
- Rehearse archive/removal on the clone only, then run full count, relationship, product, readiness, Saudi-price, governance, and smoke parity checks.
- Keep production data and deployment configuration unchanged.

### Exclusions

- No deletion, pruning, archival, migration execution, cleanup, seeding, or schema changes without approval.
- No catalog staging, URL ingestion, or price mutation.
- No secret value exposure or rotation.
- No Cloud Run/Vercel deployment until parity checks pass.

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

Read `AGENTS.md`, all engineering state files, and all Neo4j operations documents. Inspect Git status and recent history. Obtain explicit governance, security/legal, operations, cognition, billing, and database-owner approvals. Provision or restore a larger isolated clone only after approval. Build exact read-only retention previews, then rehearse the proposed 30-day archive and any consolidation on the clone only. Compare all counts, relationships, schema, product search, readiness, Saudi prices, governance reports, approvals, and smoke results. Do not mutate the full production source, change secrets, or deploy until clone parity and rollback are approved. Preserve all safe-off flags.
