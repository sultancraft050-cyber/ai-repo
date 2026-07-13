# Neo4j Minimal Cleanup Rehearsal Plan

**Result:** `READY_FOR_CLONE_CLEANUP_REHEARSAL`

This plan is ready for an isolated-clone rehearsal only. It does not authorize production deletion. No production query, mutation, snapshot, export, import, clone, secret change, deployment, or traffic change occurred while preparing it.

## Scope and protection

The documented source baseline is approximately 200,000 nodes and 208,319 relationships, at or near capacity. Up to approximately 93,006 timestamped operational/audit nodes may be archivable, leaving an estimated 106,994 nodes. Core product, customer, price, evidence, readiness, compatibility, current governance, and unknown/unreviewed labels are protected.

Candidate groups are limited to timestamped evolution, alignment, governance, and autonomy children; terminal PricingJob records older than 90 days; and AuditEvent records older than 90 days only after orphan ownership is resolved. PolicyEnforcement, PromotionDecision, SandboxEvaluation, ObjectiveTradeoff, and MemoryDecision are consolidation candidates only and are not deleted here.

## Retention rules

1. Retain the newest 30 days of timestamped operational child records.
2. Retain the newest 90 days of AuditEvent, with current-read and orphan ownership verified first.
3. Retain the newest 90 days of PricingJob; only completed, failed, or canceled jobs may be candidates.
4. Keep active, queued, running, unknown-state, protected-label, and unexpected-relationship records.
5. Run groups separately in this order: evolution, alignment, governance, autonomy, terminal PricingJob, AuditEvent, then a later consolidation design.

## Clone gate

Before any clone write, prove all of the following: clone identifier differs from production; URI fingerprint differs; production Cloud Run does not reference it; source and clone totals match 200,000/208,319; safe-off flags remain false; no production writer can reach it; and the clone is isolated from Vercel, schedulers, workers, startup seeding, and production Secret Manager.

## Read-only preview

Use `NEO4J_CLEANUP_SELECTOR_CATALOG.md` with an approved UTC cutoff. For each exact label group, capture only aggregate candidate count, relationship count/types, protected-endpoint count, orphan count, count by month, and a maximum 10-row redacted sample of stable ID/timestamp/status/labels. Rerun previews twice and require count stability within 1%.

## Bounded batch design (clone only)

The following is a static, parameterized design. It must be reviewed and executed only against the verified isolated clone, never production:

```cypher
// Example: EvolutionAuditEvent only. Copy this shape per catalog entry;
// substitute the exact approved label and timestamp predicate, never a broad match.
MATCH (n:EvolutionAuditEvent)
WHERE n.timestamp < $cutoff
  AND labels(n) = ['EvolutionAuditEvent']
  AND NOT any(label IN labels(n) WHERE label IN $protected_labels)
WITH n ORDER BY n.timestamp, n.id LIMIT $batch_size
DETACH DELETE n
RETURN count(*) AS deleted_in_batch;
```

The alignment, governance, autonomy, terminal PricingJob, and approved AuditEvent batches use the same bounded shape with their exact catalog predicate and label combination copied literally into the statement. `$batch_size` is 100 for the first batch and at most 500 after checkpoint approval.

The first batch is at most 100 nodes. Later batches are at most 500 only after a written checkpoint. Never substitute a broad `MATCH (n)` selector, never use an unbounded delete, and never use `MATCH (n) DETACH DELETE n`.

After every clone batch, run read-only total/label/type counts, relationship recount, protected-domain counts, orphan count, indexes, constraints, health, and application parity. Stop if any protected count or behavior changes, an active job appears, a protected endpoint is found, a count differs by more than 1%, or any capacity/transaction/health error occurs.

## Exact cleanup order

1. Evolution timestamped children.
2. Alignment timestamped children.
3. Governance timestamped children.
4. Autonomy timestamped children.
5. Terminal PricingJob records older than 90 days.
6. AuditEvent records older than 90 days only after ownership resolution.
7. Consolidation candidates in a separate later iteration.

Do not combine groups in one deletion transaction.

## Parity and rollback

Before and after each checkpoint compare exact total nodes/relationships, every label and relationship type, indexes, constraints, Product, Vendor, PriceSnapshot, RegionalPriceSnapshot, ProductURL, CanonicalEvidence, FieldEvidence, ConfidenceState, User, SavedBuild, SharedBuild, Watchlist, and compatibility/readiness records. Also compare health, Neo4j health, OpenAPI/admin protection, CPU/GPU/RAM search, pagination, sorting, Saudi price/vendor choice, readiness, compatibility, generated builds, and shared builds.

Rollback depends on a verified pre-rehearsal clone snapshot and retained source snapshot. On any stop condition, cease writes, preserve the clone and evidence, and restore the clone snapshot. Production remains untouched and cannot be redirected to the clone.

## Production gate

Production cleanup requires a recent successful snapshot, passed clone rehearsal, exact candidate counts, protected-data/application parity, a retained rollback snapshot, and explicit user approval. Those gates are not satisfied by this documentation commit.
