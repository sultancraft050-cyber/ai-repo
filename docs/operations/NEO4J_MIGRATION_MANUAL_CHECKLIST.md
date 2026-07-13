# Neo4j Migration Manual Verification Checklist

**Status:** `MANUAL_AURA_CONSOLE_VERIFICATION_REQUIRED`
**Safety:** inspect and record summaries only; do not create an instance, snapshot, export, secret version, deployment, or traffic change from this checklist.

## Aura Console checklist

Record each value in the approval record without credentials, tokens, connection strings, or production records:

- [ ] Source organization and instance name/ID
- [ ] Current tier/edition, Neo4j version, and Cypher compatibility
- [ ] Current region, memory, storage, node/relationship limits, and utilization percentages
- [ ] Current node/relationship totals agree with 200,000 / 208,319 baseline
- [ ] Latest snapshot timestamp, completion state, health, retention window, and restore point
- [ ] Snapshot export availability, checksum/process, download/restore permissions
- [ ] Create-from-snapshot availability and target-size choices
- [ ] Aura Professional regions and acceptable fallback region
- [ ] Target memory/storage tier leaves restore, indexes, transaction logs, validation, and growth headroom
- [ ] Source/target version and store-format compatibility
- [ ] Expected restore downtime and final-freeze duration
- [ ] Temporary parallel-instance lifetime and teardown deadline
- [ ] Expected monthly cost and temporary overlap/transfer/storage cost
- [ ] Cancellation and teardown conditions documented

Do not paste URI, username, password, access token, or private account identifiers into Git.

## Google Cloud billing checklist

- [ ] Billing account and project confirmed: `pc-recomendation-project`
- [ ] Remaining promotional credit and expiry date verified
- [ ] Whether the specific Neo4j Marketplace SKU is credit/commitment eligible verified in writing
- [ ] Marketplace offer, region, term, and effective price verified
- [ ] Direct Neo4j quote/trial/credit terms compared
- [ ] Approved recurring monthly budget recorded
- [ ] Approved temporary overlap budget recorded
- [ ] Transfer, storage, snapshot, and restore charges reviewed
- [ ] Billing owner records a dated decision; no credit assumption is accepted

## Isolation checklist

- [ ] Unique non-production instance name and database name
- [ ] Unique URI and URI fingerprint recorded outside source control
- [ ] Unique credentials; production credentials never reused
- [ ] No production Cloud Run binding, Vercel access, scheduler, worker, or startup-seeding access
- [ ] No production Secret Manager version replacement
- [ ] No automatic traffic or writer enablement
- [ ] Clone organization/project, region, and network path independently confirmed
- [ ] Explicit deletion deadline and owner for temporary clone
- [ ] Source remains available for rollback

## Evidence package

- [ ] Snapshot/export identity, checksum, tool version, and timestamps
- [ ] Source/target aggregate parity manifest
- [ ] Schema/index/constraint parity
- [ ] Product identity/readiness/Saudi price/vendor/compatibility parity
- [ ] Health, OpenAPI, admin protection, search, pagination, sorting, generated-build, and shared-build results
- [ ] Capacity, latency, connection, rejected-write, and backup observations
- [ ] Stop-condition review and owner sign-off
