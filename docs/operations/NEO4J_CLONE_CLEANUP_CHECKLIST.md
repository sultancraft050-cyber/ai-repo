# Neo4j Clone Cleanup Rehearsal Checklist

Do not execute until every checkbox is verified. This checklist is for an isolated clone; production deletion is out of scope.

## Identity and isolation

- [ ] Clone identifier is different from production.
- [ ] Clone URI fingerprint is different from production; do not record credentials or full URI.
- [ ] Production Cloud Run does not reference the clone.
- [ ] Vercel, production Secret Manager, schedulers, workers, and startup seeding cannot reach the clone.
- [ ] No production writer can reach the clone.
- [ ] Source and clone baseline match: approximately 200,000 nodes and 208,319 relationships.
- [ ] `PRICING_SCHEDULER_ENABLED=false`.
- [ ] `AUTONOMOUS_AGENTS_ENABLED=false`.
- [ ] `CPU_SPECS_SEED_ON_START=false`.

## Preview gate

- [ ] Approved UTC cutoff recorded.
- [ ] Exact labels and timestamp fields selected from the catalog.
- [ ] Candidate count query run twice; stable within 1%.
- [ ] Relationship-impact query shows zero protected endpoints.
- [ ] Product, Vendor, price, evidence, compatibility, readiness, user, build, watchlist, and current-governance-root intersections are zero.
- [ ] Orphan and month counts recorded.
- [ ] Only capped redacted samples were viewed.
- [ ] Active/queued/running/unknown PricingJob records are excluded.
- [ ] AuditEvent orphan ownership is resolved before selection.

## Batch gate

- [ ] First batch is no more than 100 nodes.
- [ ] Later batches are no more than 500 nodes and have checkpoint approval.
- [ ] Exact approved predicate and exact labels are parameterized; no broad selector is used.
- [ ] Pre-batch counts, labels, relationships, indexes, constraints, and protected-domain counts recorded.
- [ ] Post-batch counts and application parity pass.
- [ ] No capacity, transaction, health, unexpected-writer, or protected-endpoint stop condition occurred.

## Order

- [ ] Evolution timestamped children
- [ ] Alignment timestamped children
- [ ] Governance timestamped children
- [ ] Autonomy timestamped children
- [ ] Terminal PricingJob records older than 90 days
- [ ] AuditEvent records older than 90 days after ownership resolution
- [ ] Consolidation groups deferred to a separate plan

## Rollback and production gate

- [ ] Pre-rehearsal clone snapshot is restorable.
- [ ] Source snapshot remains available.
- [ ] Stop procedure and evidence retention owner are known.
- [ ] Production cleanup has not been attempted.
- [ ] Recent snapshot, passed rehearsal, exact counts, parity, rollback snapshot, and explicit user approval are all present before any production action.
