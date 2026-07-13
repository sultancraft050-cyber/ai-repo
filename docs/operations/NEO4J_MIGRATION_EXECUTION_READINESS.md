# Neo4j Migration Execution Readiness

**Date:** 2026-07-13
**Status:** `READY_PENDING_MANUAL_APPROVALS`

This is an evidence-backed planning package only. No target was created, no snapshot/export was taken, no production query was issued in this iteration, and no production data, secret, traffic, or deployment state changed.

## Baseline and decision

The documented source baseline is approximately 200,000 nodes and 208,319 relationships. The source is at or near its node/capacity boundary. Up to 93,006 timestamped operational/audit nodes are archive candidates, but cleanup is not durable: the measured active-window rate was about 17,600 nodes/day and API writers remain callable. The production service is `hardware-intelligence-api`, region `me-central1`, revision `hardware-intelligence-api-00005-kvd`.

Recommend a larger managed AuraDB Professional target, migrate before any destructive cleanup, rehearse retention on an isolated clone/target, and retain the current source for rollback. Direct Aura purchase is the default billing path; Marketplace remains viable only after billing confirms the offer and credit treatment. Self-hosted Neo4j and Spanner Graph are not recommended without new evidence.

## Writer inventory and freeze plan

The audit identifies 18 writer families. “Active” means code can write when invoked; it does not mean a write was invoked here.

| Writer / source | Trigger and feature flag | Current state | Freeze and verification |
|---|---|---|---|
| Startup schema application and default agents (`backend/app/main.py`, repository `apply_schema`/`upsert_agents`) | Process startup; no safe-off flag | Active whenever Neo4j verifies | Stop new revisions before freeze; verify logs contain no startup schema/upsert activity |
| CPU startup seed (`main.py` → `_seed_cpu_specs_safely`) | `CPU_SPECS_SEED_ON_START` | Disabled (`false`) | Keep false; verify deployment env and startup logs |
| Pricing worker (`pricing_worker.py`) | Starts whenever Neo4j connects | Active | Stop worker during maintenance; verify no `PricingJob` status transitions |
| Pricing scheduler (`pricing_scheduler.py`) | `PRICING_SCHEDULER_ENABLED` | Disabled (`false`) | Keep false; verify no scheduler thread and no scheduled jobs |
| Pricing refresh/sync/discover (`api/pricing.py`, `pricing_ingestion.py`) | Protected POST APIs; manual/API callable | Active path | Disable route access or freeze operators; verify no new jobs/offers/snapshots |
| Intelligence refresh (`api/intelligence.py`, enrichment services) | Protected POST/API jobs | Active path | Freeze endpoint and worker queue; verify no job creation |
| Cognition worker (`cognition_worker.py`) | Starts whenever Neo4j connects | Active | Stop worker and verify no learning jobs |
| Cognition reports/predictions/outcomes (`api/cognition.py`) | `persist=true` defaults; POST/API | Active/manual | Reject or maintenance-gate routes; verify no confidence/validation writes |
| Autonomous agent worker (`autonomy_worker.py`) | `AUTONOMOUS_AGENTS_ENABLED` | Disabled (`false`) | Keep false; verify no worker startup and no autonomy jobs |
| Autonomy reports/events (`api/autonomy.py`, `autonomy_service.py`) | `persist=true`; POST/API | Active/manual | Freeze `/autonomy/*`; verify no event/task/intervention/approval writes |
| Governance (`api/governance.py`, `governance_service.py`) | GET product report defaults `persist=true`; refresh POST | Active/manual | Set maintenance deny or require `persist=false`; verify no signal/action/report writes |
| Evolution (`api/evolution.py`, `evolution_service.py`) | GET report defaults `persist=true`; policy/refresh/rollback POST | Active/manual | Freeze routes; verify no policy/report/rollback children |
| Alignment (`api/alignment.py`, `alignment_service.py`) | GET report defaults `persist=true`; refresh POST | Active/manual | Freeze routes; verify no identity/report/rollback children |
| Telemetry (`api/telemetry.py`, `telemetry_analysis.py`) | `persist=true` on analysis endpoints | Active/manual | Freeze telemetry writes; verify no snapshot/reasoning writes |
| Protected request analytics (`api/launch.py`, `launch_analytics.py`, `sources.py`) | `/analytics/events`, feedback, protected request hooks; `PUBLIC_ANALYTICS_ENABLED` | Active unless configuration disables | Disable/gate analytics and feedback; verify zero `AnalyticsEvent`/`FeedbackSubmission` writes |
| Catalog/product imports (`api/catalog.py`, `api/products.py`, `product_url_sources.py`) | Admin POST routes: stage, commit, evidence, enrichment, CPU import, image update | Active/manual | Freeze all import/admin credentials; verify no product/evidence/URL mutations |
| User data (`api/user_builds.py`, `user_builds.py`) | Users, saved builds, comparisons, watchlists | Active/manual | Maintenance-gate user writes; verify no user/build/watchlist changes |
| Ops/audit/approvals (`services/ops.py`, `sources.py`) | Protected actions and autonomy approvals | Active/manual | Freeze protected operations; verify no AuditEvent/Approval writes |

Safe-off flags remain exactly: `PRICING_SCHEDULER_ENABLED=false`, `AUTONOMOUS_AGENTS_ENABLED=false`, `CPU_SPECS_SEED_ON_START=false`. These flags do not freeze manual/API persistence; the route gate is still required.

## Secret-reference audit

Only names are recorded; values must never be read or printed.

| Secret/env name | Consumer | Cloud Run binding | Cutover role | Rollback role |
|---|---|---|---|---|
| `NEO4J_URI` | `backend/app/core/config.py`, driver | Secret Manager `latest` in deploy scripts | New target endpoint version after approval | Restore previous version |
| `NEO4J_USER` | settings/driver | Secret Manager `latest` | Target credential | Previous credential |
| `NEO4J_PASSWORD` | settings/driver | Secret Manager `latest` | Target credential | Previous credential |
| `NEO4J_DATABASE` | settings/driver/repositories | Secret Manager `latest` | Target database name | Previous database name |
| `ANALYST_API_KEY` | auth/deployment | Secret Manager `latest` | Unchanged application auth | Previous version |
| `ADMIN_API_KEY` | auth/deployment | Secret Manager `latest` | Unchanged application auth | Previous version |
| `SUPER_ADMIN_API_KEY` | auth/deployment | Secret Manager `latest` | Unchanged application auth | Previous version |
| `OBJECT_STORAGE_*`, `SERPAPI_KEY`, `EBAY_BROWSE_TOKEN`, `BESTBUY_API_KEY`, `AMAZON_PAAPI_*` | optional settings/providers | Not bound by current Cloud Run scripts | No migration role unless separately approved | Restore prior versions if ever bound |

No separate connection-tuning secret is currently bound. `NEO4J_*` are unversioned in the script reference (`:latest`); cutover must replace this with explicitly numbered versions and record the version numbers without values.

## Target sizing and provider decision

| Planning item | Recommendation | Verification |
|---|---|---|
| Minimum logical headroom | At least 400,000 logical nodes, with relationship/index/restore workspace beyond that | `MANUAL_AURA_CONSOLE_VERIFICATION_REQUIRED` |
| Initial memory tier | Larger AuraDB Professional tier than source; select from measured restore/query utilization, not node count alone | `MANUAL_AURA_CONSOLE_VERIFICATION_REQUIRED` |
| Growth headroom | Keep alerting below 70–80% measured capacity after restore | Console metrics and load test |
| Six-month target | ≥600,000 logical nodes or approved forecast-based equivalent | Growth forecast/manual verification |
| Twelve-month target | ≥1,000,000 logical nodes or approved forecast-based equivalent | Growth forecast/manual verification |
| Storage/log headroom | ≥2× verified backup/export size plus transaction-log and validation workspace | Snapshot/export size and target metrics |
| Version | Neo4j 5.27-compatible Aura target; preserve Cypher 5/25 behavior | Console/provider confirmation |
| Preferred region | Closest supported Aura GCP region to `me-central1` | Availability/compliance check |
| Fallback region | Another approved Aura GCP region with acceptable latency/compliance | Manual latency and billing check |

Exact capacity, memory, storage, limits, and prices must not be inferred from this repository. Promotional credits are not assumed to apply to Marketplace products; billing-owner verification is mandatory.

## Migration-method comparison

| Method | Assessment | Decision |
|---|---|---|
| Aura create-from-snapshot | Best compatibility and lowest application change; requires source snapshot health, same/compatible Neo4j version, console permissions, and target sizing. Downtime is limited to final freeze/snapshot and parity. Rollback is source + prior secrets/revision. | **Primary** |
| Aura export/import | Portable and auditable; transfer time, file size, checksums, import tooling, and schema/index recreation require verification. Longer cutover and more validation. | **Fallback** |
| `neo4j-admin database upload` | Requires compatible Neo4j 5.27 tooling, upload permissions, secure artifact handling, and careful store/version checks; operationally more complex and not executed on Aura without console confirmation. | Secondary fallback only |

No method is executed or authorized by this document.

## Read-only parity manifest

Before cutover, source and target must match exactly for total nodes/relationships, every label and relationship type, indexes and constraints/ONLINE state, duplicate identities, orphan totals, Product (202), Vendor (22), PriceSnapshot (38), RegionalPriceSnapshot (32), ProductURL (3), CanonicalEvidence (137), FieldEvidence (1,368), ConfidenceState (246), saved builds, users, and compatibility relationships. Exact parity is required for canonical identities, readiness states, Saudi prices/vendors, and compatibility. Operational/audit counts must also be exact after restore; any difference is a stop condition. Query latency may vary, but no material regression or capacity warning is acceptable.

Application checks are read-only: `/health`, `/health/neo4j`, OpenAPI/admin protection, CPU/GPU/RAM search, pagination/sorting, cheapest SAR price/vendor, readiness, compatibility, generated build, and shared build. Use synthetic or approved clone requests; never send these checks to production during rehearsal.

## Staged cutover

1. Obtain all approvals and verify billing.
2. Verify source snapshot health/version/export capability.
3. Create the larger isolated target.
4. Restore/import and run the parity manifest independently.
5. Freeze every writer and confirm safe-off flags.
6. Take final source snapshot; synchronize only through the approved method.
7. Re-run exact parity and application checks.
8. Create numbered Secret Manager versions only after approval.
9. Deploy a new Cloud Run revision without traffic.
10. Run health, admin-protection, release, and smoke checks.
11. Shift a small percentage only when supported and approved; then full traffic after approval.
12. Observe while retaining source, snapshots, and prior secret versions.
13. Re-enable writers one class at a time after approval.
14. Rehearse retention only on the target/clone; retire the source only after the rollback window closes.

## Stop conditions

Stop immediately on snapshot/restore failure, version mismatch, count/label/type/schema mismatch, identity/price/readiness/compatibility mismatch, health failure, latency regression, rejected writes, connection saturation, unexpected writer activity, wrong Secret Manager binding, Cloud Run traffic ambiguity, or billing limit overrun. Preserve evidence, leave source untouched, and notify owners.

## Rollback

During observation, restore the previous numbered `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` Secret Manager versions, redeploy only the previously approved Cloud Run revision, and restore its prior traffic allocation. Keep the original source database and pre-cutover snapshots intact. The minimum observation window is 7 days with stable health, latency, capacity, parity, and writer behavior; source retirement requires a separate approval.

## Readiness conclusion

`READY_PENDING_MANUAL_APPROVALS`: the technical path, writer map, parity plan, cutover sequence, and rollback are complete. Aura console facts, billing, target identity, and owner approvals remain outstanding. This is not `READY_FOR_MIGRATION`.
