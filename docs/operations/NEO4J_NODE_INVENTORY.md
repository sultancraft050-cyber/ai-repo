# Neo4j Node-Volume Inventory

Date: 2026-07-12
Scope: aggregate, read-only production inventory. No credentials, records, property dumps, or secret values are included.

## Database baseline

| Measure | Count |
|---|---:|
| Nodes | 200,000 |
| Relationships | 208,319 |
| Labels | 74 |
| Relationship types | 58 |
| Unlabeled nodes | 0 |
| Relationship-orphan nodes | 1,382 |

The completed query used read-only access only. No production data changed.

## Top-25 labels

The top 25 label populations sum to 198,455 label memberships, 99.23% of the 200,000-node baseline. These are memberships, not necessarily unique nodes, because nodes can have multiple labels. There are 1,545 nodes outside the top-25 groups.

| Rank | Label | Count | Baseline share |
|---:|---|---:|---:|
| 1 | PolicyEnforcement | 40,698 | 20.349% |
| 2 | EvolutionAuditEvent | 29,070 | 14.535% |
| 3 | PromotionDecision | 23,256 | 11.628% |
| 4 | SandboxEvaluation | 23,256 | 11.628% |
| 5 | StabilizationAction | 11,630 | 5.815% |
| 6 | AlignmentAuditEvent | 11,624 | 5.812% |
| 7 | ObjectiveTradeoff | 8,721 | 4.361% |
| 8 | GovernanceSignal | 5,816 | 2.908% |
| 9 | MemoryDecision | 5,814 | 2.907% |
| 10 | RollbackEvent | 5,814 | 2.907% |
| 11 | AgentSignal | 5,810 | 2.905% |
| 12 | AgentTask | 5,810 | 2.905% |
| 13 | CognitionEvent | 5,810 | 2.905% |
| 14 | HumanOversightAction | 5,810 | 2.905% |
| 15 | AlignmentRollbackEvent | 2,907 | 1.454% |
| 16 | AutonomousIntervention | 2,905 | 1.453% |
| 17 | FieldEvidence | 1,368 | 0.684% |
| 18 | AuditEvent | 507 | 0.254% |
| 19 | PricingJob | 353 | 0.177% |
| 20 | AlignmentReport | 246 | 0.123% |
| 21 | AutonomousCognitionReport | 246 | 0.123% |
| 22 | ConfidenceState | 246 | 0.123% |
| 23 | EthicsAssessment | 246 | 0.123% |
| 24 | EvolutionOrchestration | 246 | 0.123% |
| 25 | HardwareCognition | 246 | 0.123% |

## Multi-label combinations

The top combinations match the top single-label operational groups above. Notable multi-label domain combinations are:

| Combination | Count |
|---|---:|
| CPU + Product | 96 |
| CanonicalProduct + GPU + Product | 41 |
| PriceSnapshot + RegionalPriceSnapshot | 32 |
| Product only | 28 |
| CanonicalProduct + Product + RAM | 21 |
| CanonicalProduct + Product + Storage | 7 |
| CPU + Component | 5 |
| CanonicalProduct + Motherboard + Product | 5 |
| CPU + CanonicalProduct + Product | 2 |

The top 25 combination counts are the same as the top-25 label table because those dominant cohorts use a single label each. Multi-label overlap occurs primarily in lower-volume product/component groups.

## Relationship types

| Type | Count | Type | Count |
|---|---:|---|---:|
| HAS_POLICY_ENFORCEMENT | 40,698 | HAS_EVOLUTION_AUDIT | 29,070 |
| HAS_PROMOTION_DECISION | 23,256 | HAS_SANDBOX_EVALUATION | 23,256 |
| RECOMMENDS_STABILIZATION | 11,630 | HAS_ALIGNMENT_AUDIT | 11,624 |
| HAS_OBJECTIVE_TRADEOFF | 8,721 | PERFORMED | 8,715 |
| RAISES_GOVERNANCE_SIGNAL | 5,816 | HAS_MEMORY_DECISION | 5,814 |
| HAS_ROLLBACK_EVENT | 5,814 | HAS_AGENT_SIGNAL | 5,810 |
| HAS_AGENT_TASK | 5,810 | HAS_COGNITION_EVENT | 5,810 |
| HAS_HUMAN_OVERSIGHT | 5,810 | HAS_ALIGNMENT_ROLLBACK | 2,907 |
| HAS_AUTONOMOUS_INTERVENTION | 2,905 | HAS_FIELD_EVIDENCE | 1,368 |
| ASSERTS_IDENTITY | 246 | ENFORCES_POLICY | 246 |
| HAS_ALIGNMENT_REPORT | 246 | HAS_AUTONOMY_REPORT | 246 |
| HAS_COGNITION | 246 | HAS_ETHICS_ASSESSMENT | 246 |
| HAS_EVOLUTION_ORCHESTRATION | 246 | HAS_INTELLIGENCE | 246 |
| HAS_REASONING_GOVERNANCE | 246 | MADE_BY | 151 |
| FROM_SOURCE | 137 | HAS_CANONICAL_EVIDENCE | 137 |
| FITS_IN_CASE | 108 | HAS_APPROVAL_STATE | 105 |
| REQUIRES_SOCKET | 103 | VARIANT_OF | 100 |
| USES_PCIe_LANES | 72 | HAS_SPEC_AUDIT_ITEM | 50 |
| FROM_VENDOR | 41 | HAS_PRICE | 38 |
| SOLD_BY | 37 | SHARES_BANDWIDTH | 36 |
| SUPPORTS_MEMORY | 26 | COMPATIBLE_WITH | 24 |
| HAS_GPU_FAMILY | 24 | HAS_SOCKET | 11 |
| SUMMARIZES | 10 | SUPPORTS_SOCKET | 10 |
| QVL_VALIDATED_ON | 9 | HAS_OBJECTIVE | 6 |
| SUPPORTS_MEMORY_TYPE | 6 | HAS_CHIPSET | 5 |
| SUPPORTS_FORM_FACTOR | 5 | USES_MEMORY_TYPE | 5 |
| AFFECTS_ENTITY | 4 | AUDITED_BY | 3 |
| FOR_PRODUCT | 3 | BLOCKS_PHYSICAL_SPACE | 2 |
| HAS_EFFICIENCY_RATING | 2 | PROTECTED_BY | 1 |

## Relationship orphans

There are 1,382 nodes with no relationships and zero unlabeled nodes. High-volume label orphan counts are:

| Label | Total | Orphans |
|---|---:|---:|
| AuditEvent | 507 | 504 |
| PricingJob | 353 | 353 |
| ConfidenceState | 246 | 246 |
| Other top-25 labels | — | 0 |

This is a review signal only. It does not establish that any orphan is obsolete or safe to delete.

## Timestamp fields and ranges

Only aggregate timestamp-key availability and string min/max values were collected.

| Label | Field | Populated | Oldest | Newest |
|---|---|---:|---|---|
| EvolutionAuditEvent | `timestamp` | 29,070 | 2026-05-22 | 2026-05-27 |
| AlignmentAuditEvent | `timestamp` | 11,624 | 2026-05-22 | 2026-05-27 |
| StabilizationAction | `created_at` | 11,630 | 2026-05-22 | 2026-05-27 |
| GovernanceSignal | `detected_at` | 5,816 | 2026-05-22 | 2026-05-27 |
| AgentSignal | `created_at` | 5,810 | 2026-05-22 | 2026-05-27 |
| AgentTask | `created_at` | 5,810 | 2026-05-22 | 2026-05-27 |
| CognitionEvent | `created_at` | 5,810 | 2026-05-22 | 2026-05-27 |
| HumanOversightAction | `created_at` | 5,810 | 2026-05-22 | 2026-05-27 |
| RollbackEvent | `created_at` | 5,814 | 2026-05-22 | 2026-05-27 |
| AlignmentRollbackEvent | `created_at` | 2,907 | 2026-05-22 | 2026-05-27 |
| AutonomousIntervention | `created_at` | 2,905 | 2026-05-22 | 2026-05-27 |
| FieldEvidence | `timestamp` | 1,368 | 2026-05-06 | 2026-05-24 |
| AuditEvent | `timestamp` | 507 | 2026-05-06 | 2026-05-26 |
| PricingJob | `created_at`, `updated_at` | 353 | 2026-05-06 | 2026-05-27 |
| HardwareCognition | `generated_at` | 246 | 2026-05-26 | 2026-07-10 |

`PromotionDecision`, `SandboxEvaluation`, `ObjectiveTradeoff`, `MemoryDecision`, and `EthicsAssessment` exposed no timestamp-like field in the aggregate key scan. No age-based deletion inference is made.

## Temporary, staging, test-like, and operational labels

Name-pattern review found `StagedCanonicalRecord` (182), `CanonicalStageRun` (15), `CanonicalImportRun` (11), `PricingJob` (353), `AgentTask` (5,810), `SpecAuditItem` (50), `SpecAuditRun` (5), `EvolutionAuditEvent` (29,070), `AlignmentAuditEvent` (11,624), `AuditEvent` (507), `AnalyticsEvent` (60), `CognitionEvent` (5,810), and `RollbackEvent` (5,814). No label containing crawl, cache, session, sample, test, temporary, observation, or telemetry was present in the 74-label aggregate.

## Groups requiring active-code review

The dominant volume is operational/governance/audit data rather than products or prices. Active-code producer and retention review is required for `PolicyEnforcement`, `EvolutionAuditEvent`, `PromotionDecision`, `SandboxEvaluation`, `StabilizationAction`, `AlignmentAuditEvent`, `ObjectiveTradeoff`, `GovernanceSignal`, `MemoryDecision`, `RollbackEvent`, `AgentSignal`, `AgentTask`, `CognitionEvent`, `HumanOversightAction`, `AutonomousIntervention`, `PricingJob`, `AuditEvent`, and `FieldEvidence`.

No deletion decision has been made. No record is classified as safe to delete. Any retention, archival, pruning, or migration action requires a separate approved task, backup verification, and aggregate before/after parity checks.

## Safety confirmation

The production query was read-only and aggregate-only. No database mutation, schema change, secret change, deployment, scheduler enablement, agent enablement, or startup seeding occurred. The safe-off flags remain `PRICING_SCHEDULER_ENABLED=false`, `AUTONOMOUS_AGENTS_ENABLED=false`, and `CPU_SPECS_SEED_ON_START=false`.
