# Neo4j Capacity Assessment and Safe Migration Plan

Date: 2026-07-12
Scope: read-only assessment of the production graph and a migration plan; no database, secret, or deployment mutation was performed.

## Assessment verdict

The current Aura database is at a hard or near-hard capacity boundary: the read-only inventory returned exactly 200,000 nodes, and the Cloud Run log scan found 40 capacity/limit-related messages and 2 messages matching write-rejection patterns in the seven-day window ending 2026-07-12. The exact commercial Aura tier, quota meter, and storage utilization were not exposed by the Cypher metadata available to the application; confirm those values in Aura Console and billing before selecting a target.

The database reports Neo4j Kernel `5.27-aura`, edition `enterprise`, and Cypher versions `5` and `25`. The application uses the official Python `neo4j` driver with `Driver.execute_query`, named `database_` routing, parameterized Cypher, and `SHOW INDEXES`/`SHOW CONSTRAINTS`-compatible Neo4j 5 syntax.

## Read-only inventory

| Measure | Observed value |
|---|---:|
| Nodes | 200,000 |
| Relationships | 208,319 |
| Product | 202 |
| PriceSnapshot | 38 |
| RegionalPriceSnapshot | 32 |
| Vendor | 22 |
| ProductURL | 3 |
| CanonicalEvidence | 137 |
| CanonicalSource | 5 |
| FieldEvidence | 1,368 |
| Evidence/provenance nodes (labels containing Evidence or Source) | 1,510 |
| Distinct label types | 74 |
| Distinct relationship types | 58 |
| Indexes | 149 (149 ONLINE) |
| Constraints | 101 |

The largest label populations were `PolicyEnforcement` (40,698), `EvolutionAuditEvent` (29,070), `PromotionDecision` (23,256), `SandboxEvaluation` (23,256), `StabilizationAction` (11,630), and `AlignmentAuditEvent` (11,624). The largest relationship populations were `HAS_POLICY_ENFORCEMENT` (40,698), `HAS_EVOLUTION_AUDIT` (29,070), `HAS_PROMOTION_DECISION` (23,256), `HAS_SANDBOX_EVALUATION` (23,256), and `RECOMMENDS_STABILIZATION` (11,630). Counts are aggregate only; no records or properties were stored.

## Capacity, writes, and backup evidence

- Current Cloud Run region is `me-central1`; service revision is `hardware-intelligence-api-00005-kvd`.
- The application health path reports Neo4j connected, but the 200,000-node total and log matches indicate that capacity—not connectivity—is the immediate risk.
- The log scan was read-only and returned aggregate match counts only. It is evidence of rejected/failed write attempts, not proof that every rejected write was caused by the node cap; correlate the two matches with the Aura query log before changing workloads.
- No capacity percentage, disk quota, RAM allocation, or commercial tier was available through the application’s Cypher metadata. Capture those from Aura Console’s instance metrics/billing pages with a screenshot or exported summary, excluding credentials and records.
- Aura supports snapshots and export/create-from-snapshot workflows. Aura Professional documents daily snapshots with seven-day restore/export windows; Business Critical documents longer retention and point-in-time recovery. See [Aura backup, restore, and export](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/) and [Neo4j pricing](https://neo4j.com/pricing/).
- Native Neo4j dump/backup and Aura `neo4j-admin database upload` are possible migration paths, subject to version compatibility and target capacity. See [Neo4j dump/load](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/).

## Options comparison

| Option | Driver/Cypher compatibility | Rewrite | Complexity and operations | Backup/recovery | Cost/credits | Rollback and risk |
|---|---|---|---|---|---|---|
| AuraDB Professional via Google Cloud Marketplace | Highest; existing Python driver and Neo4j 5 Cypher remain the target contract | None expected; update endpoint/database secret only | Low; managed scaling, monitoring, and upgrades | Daily snapshots; Professional retention is documented as 7 days | Consolidated GCP billing may help commitments. Do not assume promotional credits apply: Neo4j states marketplace-provider credits cannot pay for Aura; verify the project billing account and current Marketplace offer | Keep old endpoint and secrets until observation completes. Low migration risk; confirm region and quota before purchase |
| AuraDB Professional purchased directly | Highest; same Neo4j protocol and Cypher | None expected; endpoint/database secret update only | Low; managed by Neo4j, separate billing relationship | Same Professional backup profile | Published Professional pricing starts at $65/GB/month with 1GB minimum; direct purchase avoids Marketplace-credit ambiguity. Verify any Neo4j trial/credit separately | Same dual-endpoint rollback. Low application risk |
| Self-hosted Neo4j Enterprise on Google Compute Engine | High; official driver and Cypher remain compatible | Usually none, but topology, TLS, plugins, and APOC must be revalidated | High; VM sizing, disks, patching, HA, firewall, backups, monitoring, and failover become owner duties | Operator-managed `neo4j-admin` backup/dump, tested restores, and off-VM retention | Compute/PD/network costs; Google Cloud credits generally apply to eligible GCP resources, but confirm account terms. Neo4j licensing/support is separate | DNS/secret rollback is straightforward, but operational failure risk is highest |
| Google Spanner Graph | Low as a drop-in target; Google documents openCypher-like queries but requires an explicit property-graph schema and differs in syntax, types, IDs, functions, and mutation semantics | Major rewrite: repository queries, schema, indexes/constraints, driver/API, migration tooling, and compatibility tests | High application and data-model complexity; managed regional database operations | Spanner backups/PITR are separate from Neo4j exports | Native GCP billing and possible credits, subject to billing verification | Rollback requires keeping Neo4j live and maintaining dual-read/dual-write or a full reverse migration; highest risk |

Google’s Marketplace pages say qualifying third-party purchases can draw down commitments, while Neo4j’s Marketplace documentation specifically says provider credits cannot pay for Aura. Treat promotional-credit eligibility as an approval-time billing question, not a planning assumption. Sources: [Neo4j Marketplace guidance](https://neo4j.com/docs/aura/cloud-providers/), [Google Cloud Marketplace](https://cloud.google.com/marketplace), and [Google Cloud free credits](https://cloud.google.com/free).

## Recommendation

Prefer a larger AuraDB Professional instance, with direct purchase as the default path unless billing confirms that the Google Cloud Marketplace subscription is advantageous for this project’s commitment/accounting requirements. This preserves the existing driver, Cypher, schema, readiness states, Saudi price semantics, and rollback model while removing the current capacity ceiling. Select the smallest Professional memory tier that provides measured headroom after import; do not size from node count alone because the graph includes 149 indexes, 101 constraints, and large operational/audit subgraphs.

Do not select Spanner Graph for this migration. It is a platform rewrite, not a capacity-only move. Select GCE only if regulatory, network-isolation, or cost requirements justify taking on database operations and Neo4j licensing responsibility.

## Non-destructive migration runbook

1. Freeze all write-producing jobs, including pricing, discovery, ingestion, audit, telemetry, autonomous-agent, and startup-seeding paths.
2. Confirm `PRICING_SCHEDULER_ENABLED=false`, `AUTONOMOUS_AGENTS_ENABLED=false`, and `CPU_SPECS_SEED_ON_START=false` in the deployment configuration and runtime environment.
3. Obtain approval for the target tier, region, billing path, maintenance window, and migration owner. Verify Marketplace/credit eligibility with the billing administrator.
4. Create the target managed database at a size with explicit node, relationship, storage, and index headroom. Do not point production at it yet.
5. Export or snapshot the existing database using an approved Aura snapshot/export or Neo4j backup/dump procedure. Record tool version, source version, checksum, and timestamp; do not store secrets or records in the repository.
6. Import/restore into the target using the compatible Neo4j 5.27 toolchain. Keep this step in the approved maintenance environment; it is the first write operation and requires a separate approval.
7. Compare aggregate node and relationship counts, every label and relationship type, the seven key domain counts above, indexes, constraints, and ONLINE state. Investigate any discrepancy before application testing.
8. Verify representative product searches for CPU, GPU, and another category; compare identity, readiness (`compatibility_ready_exact`, `compatibility_ready_family`, `metadata_only`, `conflict_requires_review`), Saudi prices, vendor, sorting, and pagination.
9. Create new Secret Manager versions only after approval. Keep previous versions enabled and do not print values.
10. Deploy a new Cloud Run revision only after approval, with the safe-off flags preserved and the target database endpoint isolated to that revision.
11. Run `/health`, `/health/neo4j`, OpenAPI checks, admin protection, and the production smoke workflow. Confirm API contract compatibility and zero required failures.
12. Keep the old database and previous Secret Manager versions available during an observation period. Monitor capacity, latency, rejected writes, errors, and result parity.
13. Roll back by restoring the previous Secret Manager versions and routing Cloud Run traffic to the previous revision. Keep the old database untouched until the rollback decision is closed.

## Approval gates and monitoring

Approval is required before any export/import write, target creation that incurs billing, Secret Manager version change, Cloud Run deployment, traffic change, or enabling any writer. Monitor node/relationship counts, storage/RAM/page-cache utilization, transaction failures, rejected writes, query latency, connection saturation, backup success, and product-search parity. Alert before the target reaches 70–80% of its measured capacity rather than waiting for a hard limit.

## Compatibility notes

The current backend uses `neo4j` Python driver queries against Neo4j 5, `execute_query`, named database routing, parameterized Cypher, labels, relationship types, indexes, uniqueness constraints, and Neo4j-specific administrative syntax. Aura Professional and GCE Neo4j preserve this contract. Spanner Graph does not: Google documents explicit graph schemas, different labels/edge terminology, GQL/openCypher differences, and unsupported Neo4j functions such as `id`, `startNode`, `endNode`, and `relationships`; a rewrite and dual validation suite would be required.
