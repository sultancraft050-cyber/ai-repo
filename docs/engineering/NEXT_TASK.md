# Next Task

## Supply Approvals and Verified Clone Inputs

The approval package and clone runbook are complete, but execution is not authorized. All owner approvals, Aura snapshot facts, billing eligibility, target sizing, and isolated clone identity remain pending.

### Scope

- Supply dated written approvals for all nine owner roles.
- Manually verify Aura tier/region/snapshot/export/version/permissions and both billing paths.
- Supply the approved larger clone ID, organization, URI fingerprint, capacity, region, isolation evidence, lifetime, and rollback snapshot reference.
- Do not start rehearsal until every prerequisite and stop-condition owner is assigned.
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

Read `AGENTS.md`, all engineering-state files, `docs/operations/NEO4J_RETENTION_APPROVAL_PACKAGE.md`, and `docs/operations/NEO4J_CLONE_REHEARSAL_RUNBOOK.md`. Do not execute rehearsal until the user supplies dated approvals for every owner, completed Aura snapshot/readiness checks, `MANUAL_BILLING_VERIFICATION_REQUIRED` outcomes, and an isolated clone identity/capacity/URI fingerprint with proof it is not production. Once supplied, validate prerequisites and report any blockers before running even read-only clone previews. Never mutate the production source, change secrets, or deploy. Preserve all safe-off flags.
