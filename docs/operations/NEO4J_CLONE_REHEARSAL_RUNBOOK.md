# Neo4j Isolated-Clone Retention Rehearsal Runbook

Date: 2026-07-12
Execution status: `NOT_AUTHORIZED`

This is a plan, not permission to execute. The next iteration must not begin until written approvals, snapshot verification, billing verification, and an identified isolated clone are supplied.

## Clone target requirements

- Neo4j version compatible with source `5.27-aura` and Cypher 5/25 behavior.
- Managed capacity strictly larger than the 200,000-node source; planning minimum supports at least 400,000 logical nodes plus indexes, relationships, restore transaction logs, and cleanup working space. Final Aura sizing is `MANUAL_VERIFICATION_REQUIRED` because Aura Professional is memory/storage based.
- Storage working headroom of at least 2x the verified backup/export size plus logs and temporary transaction space.
- Isolated organization/project, credentials, URI, database name, and audit trail. Never reuse production credentials.
- No route from production Cloud Run, production workers, schedulers, startup seeding, Vercel, or production Secret Manager versions.
- Safe-off flags fixed to false. Clone access limited to the named rehearsal operator and reviewers.
- Preferred cloud/region: closest supported Aura GCP region to Cloud Run `me-central1`, subject to Neo4j availability, compliance, latency, and billing approval.
- Restore method: verified Aura create-from-snapshot or compatible export/backup restore; console capability is `MANUAL_VERIFICATION_REQUIRED`.
- Clone lifetime: proposed maximum 7 days after rehearsal completion; actual lifetime requires owner approval.
- Before clone deletion retain approvals, snapshot ID/checksum, clone ID, baseline/final aggregate manifests, batch journal, parity results, errors, timing/storage metrics, and rollback evidence. Then delete through the approved console procedure and retain deletion confirmation.
- Temporary billing estimate: `MANUAL_BILLING_VERIFICATION_REQUIRED` for both Marketplace and direct purchase paths.

## Required preconditions

1. All nine owner approvals in the approval package have dated references.
2. Aura tier, region, snapshot/export, version, permissions, size, and billing checks are verified manually.
3. Production writer-freeze plan is approved, including API persistence paths—not only background flags.
4. Clone identifier, URI fingerprint, organization/project, database name, and credentials are documented outside source control.
5. Rollback snapshot/export is verified restorable.

## Clone-only sequence

1. Obtain all required approvals.
2. Freeze every production write path: governance/evolution/alignment/autonomy persist routes, pricing/intelligence jobs, audit-producing admin activity, cognition workers, schedulers, ingestion, and seeding.
3. Confirm `PRICING_SCHEDULER_ENABLED=false`, `AUTONOMOUS_AGENTS_ENABLED=false`, and `CPU_SPECS_SEED_ON_START=false`.
4. Take a fresh production snapshot using approved Aura controls.
5. Verify snapshot completion, health, timestamp, checksum/identity, and export/create-instance availability.
6. Create or restore the larger isolated clone.
7. Prove it is not production: compare approved clone ID, organization, URI fingerprint, database name, region, credentials, and network path; stop on any ambiguity.
8. Record baseline total nodes/relationships, every label/type count, indexes, constraints, and ONLINE state. Expected source baseline is 200,000 nodes and 208,319 relationships.
9. Run the exact read-only candidate previews from the approval package.
10. Compare preview node and relationship counts with approved estimates.
11. Stop if any candidate differs by more than 1% or a protected label appears.
12. Rehearse the approved timestamped archive group only; do not include consolidation.
13. First batch maximum: 100 records. The separately reviewed execution procedure must use deterministic IDs from the approved preview; this document intentionally contains no deletion query.
14. Verify relationship impact and all protected-label counts after the first batch.
15. Increase to no more than 500 records per batch only after written checkpoint approval.
16. Recount totals, candidate remainder, labels, relationships, indexes, and constraints after every batch; append to the batch journal.
17. Run the full parity suite after the first batch, each material checkpoint, and completion.
18. Record query/API performance, transaction errors, capacity warnings, storage, and restore behavior.
19. Do not rehearse non-timestamped consolidation in the same first execution.
20. Preserve evidence, obtain reviewer sign-off, then delete the clone using the approved procedure and retain confirmation.

## Parity manifest

No difference is automatically acceptable. Verify before/after:

- Product 202; Vendor 22; PriceSnapshot 38; RegionalPriceSnapshot 32; ProductURL 3; CanonicalEvidence 137; FieldEvidence 1,368; ConfidenceState 246
- Product canonical keys and duplicate-product detection
- Readiness states and counts
- Compatibility results and reasons
- Cheapest SAR price and selected vendor
- Sorting and pagination
- CPU, GPU, and RAM searches with result identity/count/payload comparisons
- Generated builds and saved/user build behavior
- Governance, evolution, alignment, and autonomy latest reports
- Approval and audit-history behavior
- Health, Neo4j health, OpenAPI, admin protection, release/API contract, and production-equivalent smoke checks against the clone-isolated application
- Indexes, constraints, labels, relationship types, unexpected orphans, and duplicate IDs

## Stop conditions

Stop immediately if:

- Connection identity could be production or cannot be proven to be the approved clone.
- Snapshot/restore baseline differs from 200,000 nodes or 208,319 relationships without an approved explanation.
- Candidate count differs from approval by more than 1%.
- A protected label appears in any candidate.
- Product identity, readiness, price, vendor, compatibility, sorting, pagination, ConfidenceState, builds, governance, approvals, health, or API contract changes.
- Unexpected relationships, indexes, or constraints change.
- Any transaction/capacity error occurs, performance regresses materially, or restore reliability is uncertain.
- Batch size exceeds 100 initially or 500 after checkpoint approval.

On stop: cease all clone writes, preserve evidence, retain the clone, notify owners, and restore the pre-rehearsal clone snapshot if required. Never redirect production to the clone.

## Cleanup rehearsal versus migration

Cleanup rehearsal tests whether an approved archive can recover temporary headroom. It does not make the full source safe and does not stop active API producers.

A larger managed database migration remains the durable solution. Compare AuraDB Professional through Google Cloud Marketplace with direct AuraDB Professional only after `MANUAL_BILLING_VERIFICATION_REQUIRED`. Promotional-credit eligibility is not assumed. No production Secret Manager version or Cloud Run revision changes during clone rehearsal.

## Evidence and rollback

Rollback on the clone is restoration of the verified pre-rehearsal clone snapshot. A later production migration requires its own approved rollback using the preserved source database, previous Secret Manager versions, and previous Cloud Run revision. No production rollback action is authorized here.
