# Neo4j Cleanup Selector Catalog

Technical catalog for an isolated-clone rehearsal only. The Cypher below is a design artifact; no query in this document was executed in this iteration. Do not run any mutation against production.

## Common parameters and protections

Set `$cutoff` to an approved UTC datetime and `$protected_labels` to the complete protected-label set. Unknown or unreviewed labels are protected by default. Every candidate must have the exact approved label set; labels with extra or unknown labels are excluded.

Protected labels include `Product`, `Vendor`, `PriceSnapshot`, `RegionalPriceSnapshot`, `ProductURL`, `CanonicalEvidence`, `FieldEvidence`, `ConfidenceState`, `User`, `SavedBuild`, `SharedBuild`, `Watchlist`, compatibility/readiness/canonical-identity records, and any unreviewed label.

Reusable read-only checks for a predicate `PREDICATE` and exact labels `$expected_labels`:

```cypher
// Candidate count
MATCH (n)
WHERE PREDICATE
  AND labels(n) = $expected_labels
  AND NOT any(label IN labels(n) WHERE label IN $protected_labels)
RETURN count(n) AS candidate_nodes;

// Relationship impact, including protected endpoints
MATCH (n)
WHERE PREDICATE AND labels(n) = $expected_labels
OPTIONAL MATCH (n)-[r]-()
RETURN count(DISTINCT n) AS candidate_nodes,
       count(r) AS affected_relationships,
       count(CASE WHEN any(label IN labels(endNode(r)) WHERE label IN $protected_labels)
                  OR any(label IN labels(startNode(r)) WHERE label IN $protected_labels)
             THEN 1 END) AS protected_endpoint_relationships,
       collect(DISTINCT type(r))[..100] AS relationship_types;

// Orphans
MATCH (n)
WHERE PREDICATE AND labels(n) = $expected_labels
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
RETURN count(CASE WHEN degree = 0 THEN 1 END) AS orphan_nodes,
       count(n) AS candidate_nodes;

// Count by UTC month
MATCH (n)
WHERE PREDICATE AND labels(n) = $expected_labels
WITH coalesce(n.timestamp, n.created_at) AS event_time
RETURN toString(event_time)[0..7] AS utc_month, count(*) AS nodes
ORDER BY utc_month;

// Capped redacted sample
MATCH (n)
WHERE PREDICATE AND labels(n) = $expected_labels
RETURN n.id AS stable_id,
       coalesce(n.timestamp, n.created_at) AS event_time,
       n.status AS status,
       labels(n) AS labels
ORDER BY event_time ASC, stable_id ASC
LIMIT 10;
```

The protected-endpoint count must be zero. Separate read-only checks must also return zero for Product, Vendor, price, compatibility, readiness, User, build, and current-governance-root relationships. Candidate counts must be rerun twice and remain stable before any clone batch.

## Timestamped operational groups

| Group | Exact label | Timestamp field | Retention cutoff | Documented expected candidates | Documented relationship expectation |
|---|---|---|---|---:|---:|
| Evolution audit children | `EvolutionAuditEvent` | `timestamp` | newest 30 days retained | 29,070 | 29,070 direct parent relationships minimum |
| Evolution rollback children | `RollbackEvent` | `created_at` | newest 30 days retained | 5,814 | included in evolution total |
| Alignment audit children | `AlignmentAuditEvent` | `timestamp` | newest 30 days retained | 11,624 | 11,624 direct parent relationships minimum |
| Alignment rollback children | `AlignmentRollbackEvent` | `created_at` | newest 30 days retained | 2,907 | included in alignment total |
| Governance signals | `GovernanceSignal` | `detected_at` | newest 30 days retained | 5,816 | parent/target relationships must be reviewed |
| Governance actions | `StabilizationAction` | `created_at` | newest 30 days retained | 11,630 | 11,630 direct parent relationships minimum |
| Autonomy/cognition children | `CognitionEvent`, `AgentTask`, `AgentSignal`, `AutonomousIntervention`, `HumanOversightAction` | `created_at` | newest 30 days retained | 26,145 combined | parent/approval relationships must be reviewed |

The combined timestamped planning total is up to 93,006 nodes, with an estimated post-archive baseline of approximately 106,994 nodes. These are preview expectations, not authorization or current counts.

For each row, substitute the exact predicate below into the common checks:

```text
EvolutionAuditEvent: n:EvolutionAuditEvent AND n.timestamp < $cutoff
RollbackEvent: n:RollbackEvent AND n.created_at < $cutoff
AlignmentAuditEvent: n:AlignmentAuditEvent AND n.timestamp < $cutoff
AlignmentRollbackEvent: n:AlignmentRollbackEvent AND n.created_at < $cutoff
GovernanceSignal: n:GovernanceSignal AND n.detected_at < $cutoff
StabilizationAction: n:StabilizationAction AND n.created_at < $cutoff
Autonomy: (n:CognitionEvent OR n:AgentTask OR n:AgentSignal OR n:AutonomousIntervention OR n:HumanOversightAction) AND n.created_at < $cutoff
```

For the combined autonomy selector, run one exact-label query per label, not a single mixed-label delete. `labels(n) = ['Label']` is required for each individual batch.

## AuditEvent selector

`AuditEvent.timestamp` is the timestamp. Retain 90 days. Orphan ownership is unresolved, so orphan candidates remain protected until the audit/security owner confirms that current recent/idempotency reads do not require them.

```cypher
MATCH (n:AuditEvent)
WHERE n.timestamp < $audit_cutoff
  AND labels(n) = ['AuditEvent']
RETURN count(n) AS candidate_nodes;
```

Run the common relationship, protected-intersection, orphan, month, and capped-sample checks with `PREDICATE = n:AuditEvent AND n.timestamp < $audit_cutoff`. Expected removable count and relationship count: `MANUAL_VERIFICATION_REQUIRED`; do not infer them from the 507-node inventory or 504 orphan count.

## PricingJob selector

`PricingJob.created_at` is the age field. Retain 90 days. Only terminal statuses are candidates: `completed`, `failed`, and `canceled`. `queued`, `running`, and unknown statuses are protected.

```cypher
MATCH (n:PricingJob)
WHERE n.created_at < $job_cutoff
  AND n.status IN ['completed', 'failed', 'canceled']
  AND labels(n) = ['PricingJob']
RETURN count(n) AS candidate_nodes;
```

Run the common checks with the same predicate. Expected removable count and relationship count: `MANUAL_VERIFICATION_REQUIRED`; first obtain terminal-state distribution and verify no active job is selected.

## Consolidation-only groups

`PolicyEnforcement`, `PromotionDecision`, `SandboxEvaluation`, `ObjectiveTradeoff`, and `MemoryDecision` have no approved timestamp selector. Do not delete them in this rehearsal. The separate consolidation plan must first establish parent identity, latest-N semantics, audit retention, relationship impact, and exact parity requirements.

## Protected relationship query

Run this read-only check for every candidate predicate and stop unless every count is zero:

```cypher
MATCH (n)-[r]-()
WHERE PREDICATE AND labels(n) = $expected_labels
WITH type(r) AS relationship_type,
     labels(startNode(r)) AS start_labels,
     labels(endNode(r)) AS end_labels
RETURN relationship_type, start_labels, end_labels, count(*) AS relationships
ORDER BY relationships DESC;
```

Explicitly reject any relationship to Product, Vendor, PriceSnapshot, RegionalPriceSnapshot, ProductURL, evidence, ConfidenceState, compatibility/readiness, User, SavedBuild, SharedBuild, Watchlist, or a current governance root.

## Reproducibility

Record only cutoff, expected labels, query revision, candidate count, relationship count, protected-intersection count, orphan count, and checksum of the aggregate manifest. Rerun the read-only preview twice; any difference greater than 1% or any new protected endpoint blocks the rehearsal.
