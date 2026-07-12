# Next Task

## Review Neo4j Operational-Node Retention Before Migration

The node-volume inventory explains 99.23% of capacity through the top-25 label populations and finds 1,382 relationship orphans concentrated in operational/audit groups. No deletion decision has been made. Review active-code producers and retention requirements before finalizing migration sizing.

### Scope

- Trace high-volume labels and orphan groups to their active code producers.
- Determine governance, audit, debugging, and user-facing retention requirements.
- Reconfirm Aura tier, utilization, quota, and target sizing after the retention review.
- Obtain separate approval before any retention action or migration execution.
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

Read `AGENTS.md`, all engineering state files, `docs/operations/NEO4J_CAPACITY_ASSESSMENT.md`, and `docs/operations/NEO4J_NODE_INVENTORY.md`. Inspect Git status and recent history. Trace the high-volume operational/audit labels and orphan groups to active code producers and documented retention needs without reading complete production records. Do not delete, prune, archive, migrate, or modify schema. Produce an evidence-backed retention proposal with owner approval gates, then reassess Aura target sizing. Preserve all three safe-off flags and keep production deployment unchanged.
