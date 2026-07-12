# Neo4j Retention Approval Package

Date: 2026-07-12
Status: `PENDING_OWNER_APPROVAL`
Decision context: `CLEANUP_BUYS_TIME_BUT_MIGRATION_REQUIRED`

This package proposes approvals and read-only previews only. It does not authorize or contain deletion queries, and no clone, export, secret change, or deployment has occurred.

## Confirmed evidence

- Source baseline: 200,000 nodes and 208,319 relationships; source is full/at capacity.
- Proposed timestamped archive population: up to 93,006 nodes.
- Estimated post-archive online population: 106,994 nodes, or 53.50% of the verified node limit.
- Historical burst: approximately 93,006 timestamped nodes over 5.3 days (~17,600/day); this is not assumed to be a steady-state rate.
- Protected core data and `ConfidenceState` are excluded. `DELETE_CANDIDATE` remains empty.

## Approval matrix

| Owner role | Decision required | Affected labels/window | Archive or consolidation impact | Evidence required | Status | Blocking questions / written reference |
|---|---|---|---|---|---|---|
| Database owner | Approve larger isolated clone, restore method, rehearsal limits, and rollback | All candidates; 30-day proposal | Clone-only batches; source untouched | Source/clone identity, capacity, snapshot health, baseline parity | PENDING_OWNER_APPROVAL | Clone URI/ID, capacity, restore owner, approval reference |
| Governance owner | Approve whether operational governance history may leave online storage | EvolutionAuditEvent, RollbackEvent, GovernanceSignal, StabilizationAction; 30 days proposed | Archive up to 52,330 nodes; parent/child relationship impact | Current-report behavior, audit obligations, archive accessibility | PENDING_OWNER_APPROVAL | Required history window and acceptable relationship changes |
| Security/legal owner | Set audit/legal retention | AuditEvent; 90 days proposed; governance audit groups | No AuditEvent removal proposed in first rehearsal | Legal policy, incident/audit lookup needs, export controls | PENDING_OWNER_APPROVAL | Jurisdiction, minimum retention, written approval reference |
| Pricing operations owner | Set terminal-job retention and ownership | PricingJob; 90 days after terminal state proposed | No first-rehearsal removal until status proof | Status distribution, retry/debug needs, operations runbook | PENDING_OWNER_APPROVAL | Terminal statuses, failed-job retention, owner reference |
| Cognition/AI owner | Confirm current state and autonomy-history needs | ConfidenceState permanent; autonomy children 30 days proposed | ConfidenceState excluded; autonomy archive up to 26,145 | Direct read paths, approval context, reproducibility | PENDING_OWNER_APPROVAL | Minimum autonomy history and approval-trace needs |
| Application owner | Approve parity suite and zero-difference rule | All candidate groups | Confirm no product/search/build/governance regression | Baseline responses, canonical keys, readiness, pricing, builds | PENDING_OWNER_APPROVAL | Test fixtures, acceptable performance threshold, sign-off reference |
| Google Cloud billing owner | Approve temporary clone/transfer costs and Marketplace path review | Clone and possible Marketplace AuraDB Professional | Billing only | Billing account, credits/commitments, transfer/storage estimate | PENDING_OWNER_APPROVAL | `MANUAL_BILLING_VERIFICATION_REQUIRED` |
| Neo4j billing owner | Approve Aura tier, region, capacity, snapshot/export features, clone lifetime | Larger AuraDB Professional target | Billing and service limits | Aura quote/console capacity and backup terms | PENDING_OWNER_APPROVAL | `MANUAL_BILLING_VERIFICATION_REQUIRED` |
| Deployment owner | Confirm production isolation and future cutover approval boundary | Cloud Run and Secret Manager excluded from rehearsal | No production connection or deployment | Service config, safe-off flags, rollback revision | PENDING_OWNER_APPROVAL | Written confirmation that clone is unreachable from production |

No person or team name is inferred. Each approval must provide a dated written reference.

## Protected labels

Every preview and rehearsal must exclude: `Product`, `CanonicalProduct`, `ProductFamily`, component labels, `Vendor`, `ProductURL`, `PriceSnapshot`, `RegionalPriceSnapshot`, `CanonicalEvidence`, `FieldEvidence`, `CanonicalSource`, `ConfidenceState`, `User`, `SavedBuild`, `WatchlistItem`, approval records, identity/policy roots, and all labels not explicitly approved in a candidate definition.

## Exact read-only candidate definitions

Parameters used below: `$cutoff` is a Neo4j datetime set to the approved UTC cutoff. The proposed 30-day window is not approved. Capped samples return IDs/labels/degree only and must run on the isolated clone after identity verification.

### EVOLUTION_TIMESTAMPED

- Labels/fields: `EvolutionAuditEvent.timestamp`, `RollbackEvent.created_at`
- Proposed rule: timestamp older than approved cutoff; proposed online window 30 days
- Expected nodes: 34,884; expected direct parent relationships: 34,884
- Approvals: database, governance, application; archive required; clone rehearsal required
- Rollback dependency: verified source snapshot/export plus clone baseline

```cypher
MATCH (n)
WHERE (n:EvolutionAuditEvent AND n.timestamp < $cutoff)
   OR (n:RollbackEvent AND n.created_at < $cutoff)
RETURN labels(n) AS labels, count(*) AS candidate_count
ORDER BY candidate_count DESC
```

```cypher
MATCH (n)
WHERE (n:EvolutionAuditEvent AND n.timestamp < $cutoff)
   OR (n:RollbackEvent AND n.created_at < $cutoff)
OPTIONAL MATCH (n)-[r]-()
RETURN count(DISTINCT n) AS nodes, count(r) AS incident_relationships,
       type(r) AS relationship_type
ORDER BY incident_relationships DESC
```

```cypher
MATCH (n)
WHERE (n:EvolutionAuditEvent AND n.timestamp < $cutoff)
   OR (n:RollbackEvent AND n.created_at < $cutoff)
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
RETURN n.id AS redacted_id, labels(n) AS labels, degree
LIMIT 10
```

### ALIGNMENT_TIMESTAMPED

- Labels/fields: `AlignmentAuditEvent.timestamp`, `AlignmentRollbackEvent.created_at`
- Proposed window: 30 days; expected nodes and direct parent relationships: 14,531
- Approvals: database, governance, application; archive required; clone rehearsal required

Use the three queries above with this predicate:

```cypher
(n:AlignmentAuditEvent AND n.timestamp < $cutoff)
OR (n:AlignmentRollbackEvent AND n.created_at < $cutoff)
```

### GOVERNANCE_TIMESTAMPED

- Labels/fields: `StabilizationAction.created_at`, `GovernanceSignal.detected_at`
- Proposed window: 30 days; expected nodes: 17,446; expected minimum parent relationships: 17,446
- Approvals: database, governance, application; archive required; clone rehearsal required
- Relationship preview must also reveal any signal-to-target relationships.

Use the same count/relationship/capped-sample query shapes with this predicate:

```cypher
(n:StabilizationAction AND n.created_at < $cutoff)
OR (n:GovernanceSignal AND n.detected_at < $cutoff)
```

### AUTONOMY_TIMESTAMPED

- Labels/field: `CognitionEvent`, `AgentTask`, `AgentSignal`, `AutonomousIntervention`, `HumanOversightAction`; each uses `created_at`
- Proposed window: 30 days; expected nodes and minimum parent relationships: 26,145
- Approvals: database, cognition/AI, governance, application; archive required; clone rehearsal required

Use the same query shapes with this predicate:

```cypher
(n:CognitionEvent OR n:AgentTask OR n:AgentSignal OR
 n:AutonomousIntervention OR n:HumanOversightAction)
AND n.created_at < $cutoff
```

### NON_TIMESTAMPED_CONSOLIDATION

- Labels: `PolicyEnforcement`, `PromotionDecision`, `SandboxEvaluation`, `ObjectiveTradeoff`, `MemoryDecision`
- Timestamp/cutoff: unavailable; no executable retention selector approved
- Current population: 101,745 label memberships
- Proposed rule: latest N per parent/report only after parent-order evidence is added
- Expected candidate count/relationships: `MANUAL_VERIFICATION_REQUIRED`
- Approvals: database, governance, cognition/AI, application; archive required; separate later clone rehearsal

Read-only discovery only:

```cypher
MATCH (parent)-[r]->(n)
WHERE n:PolicyEnforcement OR n:PromotionDecision OR n:SandboxEvaluation
   OR n:ObjectiveTradeoff OR n:MemoryDecision
RETURN labels(n) AS labels, type(r) AS relationship_type,
       count(DISTINCT n) AS nodes, count(DISTINCT parent) AS parents
ORDER BY nodes DESC
```

No consolidation execution belongs in the first rehearsal.

## Snapshot readiness checklist

Every item is `MANUAL_VERIFICATION_REQUIRED` in Aura Console:

- Exact Aura tier and contractual node/storage limits
- Source cloud and region
- Latest snapshot timestamp and completion/health
- Snapshot export availability and retention window
- Ability to create a new larger instance from snapshot
- Source/target Neo4j version and store compatibility
- Expected export/backup file size and checksum mechanism
- Download, restore, organization, and billing permissions
- Confirmation that a full source at capacity can still snapshot/export
- Restore downtime, overwrite, network, and version limitations
- Temporary clone, storage, transfer, and restore billing implications

Do not infer these values from Cypher metadata.

## Purchase-path decision

| Path | Benefits | Required verification | Status |
|---|---|---|---|
| AuraDB Professional via Google Cloud Marketplace | Consolidated billing and potential commitment accounting | Marketplace organization, region/capacity, price, credits/commitments; promotional credits are not assumed | MANUAL_BILLING_VERIFICATION_REQUIRED |
| AuraDB Professional direct | Direct Neo4j billing and standard Aura operations | Quote, region/capacity, payment owner, trial/credit terms | MANUAL_BILLING_VERIFICATION_REQUIRED |

The prior conclusion remains: do not choose self-hosting or Spanner Graph without new evidence.

## Approval outcome

All owner decisions, snapshot facts, clone identity, and billing eligibility remain pending. This package cannot authorize rehearsal execution.
