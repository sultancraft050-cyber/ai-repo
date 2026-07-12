# Neo4j Operational Retention Audit

Date: 2026-07-12
Decision: `CLEANUP_BUYS_TIME_BUT_MIGRATION_REQUIRED`

## Executive summary

The database is full at 200,000 nodes. The dominant records are generated operational/governance children, not product, pricing, readiness, compatibility, vendor, or user-build records. Static code tracing found active API producers with `persist=true` defaults; the autonomous background worker and pricing scheduler are disabled, but their API and manual-admin paths remain callable.

The timestamped operational cohort contains 93,006 nodes, all older than 30 days as of this audit. A clone-rehearsed 30-day online-retention policy could therefore archive up to 93,006 nodes and reduce the online graph to approximately 106,994 nodes (53.50% of the verified 200,000-node limit). During its May 22–27 active window this cohort grew by approximately 17,600 nodes/day; including non-timestamped children from the same report runs would make the effective rate higher. Cleanup buys headroom, but an enabled or repeatedly invoked producer could consume it again within days, so managed-database migration remains required.

No retention policy was executed. No deletion is approved.

## Producer and reference map

| Labels | Producer | Persistence path | Current activation | Read/use path | Key/lifecycle |
|---|---|---|---|---|---|
| PolicyEnforcement, SandboxEvaluation, PromotionDecision, MemoryDecision, EvolutionAuditEvent, RollbackEvent | `EvolutionOrchestrator` in `backend/app/services/evolution.py` | `Neo4jEvolutionRepository.upsert_report/_upsert_children` | Active through `/evolution/products/{id}` (`persist=true`), `/evolution/refresh`, `/evolution/rollback`, and autonomy orchestration; not feature-flagged | Latest parent `EvolutionOrchestration` payload is read; child labels have no direct application read query | UUID per decision/run; append-like children attached to one stable per-product parent report |
| ObjectiveTradeoff, AlignmentAuditEvent, AlignmentRollbackEvent | alignment service in `backend/app/services/alignment.py` | `Neo4jAlignmentRepository.upsert_report/_upsert_children` | Active through `/alignment/products/{id}` (`persist=true`), `/alignment/refresh`, evolution/autonomy chains; not feature-flagged | Latest parent `AlignmentReport` payload is read; child labels have no direct read query | UUID per inspection/run; historical/observability children |
| GovernanceSignal, StabilizationAction | governance service in `backend/app/services/governance.py` | `Neo4jGovernanceRepository` child upserts | Active through `/governance/products/{id}` (`persist=true`), `/governance/refresh`, evolution/autonomy chains; not feature-flagged | Latest parent governance report drives evolution; no direct child read query found | UUID per generated signal/action; relationship to stable per-product governance report |
| CognitionEvent, AgentTask, AgentSignal, AutonomousIntervention, HumanOversightAction | `AutonomousCognitionEngine` in `backend/app/services/autonomy.py` | `Neo4jAutonomyRepository.upsert_event/upsert_report/_upsert_children` | Background worker disabled by `AUTONOMOUS_AGENTS_ENABLED=false`; APIs `/autonomy/products/{id}`, `/autonomy/run`, `/autonomy/events` can still persist | Latest parent autonomy report and queue/event queries; children are operational history/approval context | UUID per event/task/signal/action; append-like per run |
| AuditEvent | middleware and protected operations in `backend/app/main.py`, `backend/app/api/sources.py`, `backend/app/services/ops.py` | `Neo4jOpsRepository.create_audit_event` | Active for protected requests and manual operations; not feature-flagged | Recent audit feed, endpoint/idempotency lookup, ops/capacity summaries | UUID per protected action; valid standalone audit record, relationship optional |
| PricingJob | pricing APIs, `PricingWorker`, `PricingScheduler`, intelligence refresh | `Neo4jPricingRepository.create_job/update_job` | Worker starts whenever Neo4j connects; scheduler disabled by `PRICING_SCHEDULER_ENABLED=false`; pricing/intelligence APIs still enqueue | Job status/backlog/ops summaries and updates by ID | UUID per job; standalone terminal job is expected |
| ConfidenceState | cognition engine/service | `Neo4jCognitionRepository.upsert_confidence_states` | Cognition worker starts whenever Neo4j connects; cognition paths remain active | `confidence_states(product_id)` feeds cognition/reliability | Deterministic state IDs; current state, not append-only history |

Tests instantiate these models but do not write production. Startup schema application and default-agent upserts remain active, but the three required safe-off flags remain false.

## Growth evidence

Aggregate read-only queries found zero nodes created in the last 7 or 30 days for all timestamped audited labels. All ID duplicate counts were zero. Date coverage and active-window rates are:

| Cohort | Count | Date range | Approx. active-window rate |
|---|---:|---|---:|
| EvolutionAuditEvent | 29,070 | May 22–27 | ~5,500/day |
| AlignmentAuditEvent | 11,624 | May 22–27 | ~2,200/day |
| StabilizationAction | 11,630 | May 22–27 | ~2,200/day |
| GovernanceSignal | 5,816 | May 22–27 | ~1,100/day |
| RollbackEvent | 5,814 | May 22–27 | ~1,100/day |
| AgentSignal | 5,810 | May 22–27 | ~1,100/day |
| AgentTask | 5,810 | May 22–27 | ~1,100/day |
| CognitionEvent | 5,810 | May 22–27 | ~1,100/day |
| HumanOversightAction | 5,810 | May 22–27 | ~1,100/day |
| AlignmentRollbackEvent | 2,907 | May 22–27 | ~550/day |
| AutonomousIntervention | 2,905 | May 22–27 | ~550/day |
| Timestamped operational total | 93,006 | concentrated in ~5.3 days | ~17,600/day |

PolicyEnforcement, PromotionDecision, SandboxEvaluation, ObjectiveTradeoff, and MemoryDecision expose no timestamp field, so 7/30-day growth is unavailable. Their UUID-per-run design and parent relationships show repeated decisions, but exact temporal allocation cannot be inferred safely. Projected capacity exhaustion is 0 days today because the source already contains 200,000 nodes. After the proposed archive rehearsal, a recurrence of the measured timestamped rate could consume the 93,006-node headroom in roughly 5 days.

## High-volume classification and proposed policy

| Labels | Classification | Proposed online retention | Estimated archive/consolidation | Relationship impact and risk |
|---|---|---|---:|---|
| ConfidenceState (246) | KEEP_PERMANENTLY | Current state indefinitely | 0 | Direct cognition read; deterministic IDs; orphan status is expected standalone state |
| AuditEvent (507) | KEEP_WITH_RETENTION_POLICY | 90 days online, longer archive subject to security/legal owner | 0 now; all currently within historical review window decision | Direct recent/idempotency reads; legal/audit owner approval required |
| PricingJob (353) | KEEP_WITH_RETENTION_POLICY | 90 days after terminal state | 0 now pending terminal-state proof | Ops/backlog reads and job updates; operations owner approval required |
| Timestamped evolution/alignment/governance/autonomy children (93,006) | ARCHIVE_CANDIDATE | 30 days online after clone rehearsal | Up to 93,006 | Removing children breaks parent-child relationships but parent payloads retain current report; governance/product owner approval and restore artifact required |
| PolicyEnforcement (40,698), PromotionDecision (23,256), SandboxEvaluation (23,256), ObjectiveTradeoff (8,721), MemoryDecision (5,814) | CONSOLIDATE_CANDIDATE | Latest N per parent/report plus approved historical archive | Unknown until timestamp/parent-run selector is designed | No direct reads found; attached to current parent reports. Exact selector and audit requirements unresolved |
| AuditEvent orphans (504) | UNKNOWN | No change | 0 approved | Likely valid standalone protected-request audit records; relationships are not required by repository design |
| PricingJob orphans (353) | UNKNOWN | No change until terminal statuses are aggregated | 0 approved | Standalone job design explains degree zero; incomplete/terminal distribution unavailable |
| ConfidenceState orphans (246) | KEEP_PERMANENTLY | Current deterministic state | 0 | Repository reads standalone state by product ID; no relationship is expected |

`DELETE_CANDIDATE`: none. No label satisfies the required ownership, legal-retention, relationship, selector, and rehearsal criteria.

## Application impact

The audited operational children do not participate directly in product search, Saudi price selection, readiness classification, compatibility checks, vendor ranking, build generation, or user-build persistence. Evolution/alignment/governance/autonomy parent reports can influence governance and approvals, and parent payloads embed their current child details. AuditEvent, PricingJob, and ConfidenceState have direct read paths and require stricter retention handling.

No existing automated retention policy applies to the high-volume labels. The existing prune tooling allow-lists separate temporary/import labels and does not authorize these operational groups.

## Orphan findings

- AuditEvent: 504 of 507 are degree zero. Creation is standalone by design; direct recent/idempotency reads do not require relationships. Classification remains UNKNOWN pending audit/legal ownership.
- PricingJob: 353 of 353 are degree zero. Jobs are standalone queue/terminal records created by active APIs and the always-started worker; the scheduler is disabled. Classification remains UNKNOWN until terminal-state counts are measured.
- ConfidenceState: 246 of 246 are degree zero. Deterministic upserts and direct product-scoped reads make these valid standalone current-state records. Classification is KEEP_PERMANENTLY.

No orphan is classified as failed, abandoned, legacy, sample, or safe to delete without further evidence.

## Approval, rehearsal, and rollback

Owners required: product/governance owner for evolution/alignment/autonomy history; security/legal owner for AuditEvent; operations owner for PricingJob; cognition owner for ConfidenceState; database owner for export, rehearsal, and execution.

Before any retention execution:

1. Export/snapshot the database and verify restore.
2. Restore to an isolated larger clone.
3. Implement a read-only selector preview with exact counts and relationship impacts.
4. Rehearse archival/removal on the clone only.
5. Compare all labels, relationships, indexes, constraints, product searches, readiness states, Saudi prices, governance reports, approvals, and smoke checks.
6. Keep the source and archive for rollback; do not reuse the existing production prune endpoint without a separately reviewed allow-list and signed approval.

Rollback requires restoring the pre-rehearsal clone snapshot or, after a separately approved production action, restoring the exported database and previous Cloud Run/Secret Manager configuration.

## Remaining unknowns

- Legal/business retention obligations for audit and governance records.
- Terminal status distribution for PricingJob.
- A safe temporal selector for non-timestamped evolution/alignment children.
- Exact number of nodes with no active application reference; static code can prove label-level readers, not per-node reachability.
- Whether the May cohort was generated by a one-time script, manual API sweep, or formerly enabled autonomous worker.

## Conclusion

`CLEANUP_BUYS_TIME_BUT_MIGRATION_REQUIRED`

A clone-rehearsed archive of the 93,006 timestamped operational nodes could reduce estimated utilization to 53.50%, below the 70–80% planning threshold. However, the source is already full, API producers remain active despite background flags, and the measured active-window growth could refill that headroom in about five days. Proceed first with a larger managed clone, retention-owner approvals, and rehearsal; do not execute cleanup on the full source database.

No database mutation, retention execution, secret change, or deployment occurred during this audit.
