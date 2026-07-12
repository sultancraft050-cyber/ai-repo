# Next Task

## Approve and Execute a Staged Neo4j Capacity Migration

The read-only capacity assessment found exactly 200,000 nodes, 208,319 relationships, 149 online indexes, 101 constraints, and capacity/write-rejection evidence in recent Cloud Run logs. A larger AuraDB Professional target is recommended, subject to tier, quota, region, and billing-credit verification.

### Scope

- Verify Aura tier, storage/RAM utilization, node/relationship quota, backup exportability, target region, and billing/Marketplace credit treatment.
- Obtain explicit approval for the target, maintenance window, writer freeze, export/import, Secret Manager versions, and Cloud Run deployment.
- Execute the staged migration runbook in `docs/operations/NEO4J_CAPACITY_ASSESSMENT.md` without changing readiness, identity, Saudi price, or pagination semantics.
- Keep production data and deployment configuration unchanged.

### Exclusions

- No migration execution without approval.
- No catalog staging, URL ingestion, price mutation, cleanup, pruning, seeding, or schema changes.
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

Read `AGENTS.md`, all files under `docs/engineering/`, and `docs/operations/NEO4J_CAPACITY_ASSESSMENT.md`. Inspect Git status and recent history. Verify Aura tier, quota, storage/RAM utilization, backup/export options, region, and billing-credit treatment with authorized console access. Obtain explicit approval before any target creation, export/import, Secret Manager version, or deployment. If approved, freeze all writers, preserve the three safe-off flags, create a larger AuraDB Professional target, migrate using a compatible Neo4j 5.27 toolchain, compare aggregate counts and schema, verify representative product searches/readiness/Saudi prices, then deploy and smoke test only after parity passes. Keep the old database and previous secrets/revision for rollback. Do not select Spanner Graph without a separate rewrite project.
