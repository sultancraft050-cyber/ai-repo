# Neo4j Migration Approval Record

**Project:** `pc-recomendation-project`
**Source service:** `hardware-intelligence-api`
**Source revision:** `hardware-intelligence-api-00005-kvd`
**Decision:** `PENDING_OWNER_APPROVAL`

No names, approvals, billing facts, target identity, or dates are invented here. Each owner must supply a dated written reference before execution.

| Owner | Exact decision required | Required evidence | Blocking questions | Status | Approval reference | Date |
|---|---|---|---|---|---|---|
| Database owner | Approve source snapshot, target size, method, and rollback | Snapshot health, parity plan, source retention | Is restore proven and is source retained? | `PENDING_OWNER_APPROVAL` | — | — |
| Application owner | Approve zero-difference parity and maintenance window | Search/build/readiness/price/compatibility checks | What latency tolerance and test evidence are required? | `PENDING_OWNER_APPROVAL` | — | — |
| Governance owner | Approve writer freeze and retention boundaries | Writer map, protected-label list, audit trail | Which governance history must remain online? | `PENDING_OWNER_APPROVAL` | — | — |
| Security/legal owner | Approve data handling, credentials, retention, and archive | Isolation proof, secret procedure, retention obligations | What legal retention/archive period applies? | `PENDING_OWNER_APPROVAL` | — | — |
| Billing owner | Approve Marketplace/direct path and overlap budget | Console quote, credit eligibility, budget | Do credits apply to this exact SKU? | `PENDING_OWNER_APPROVAL` | — | — |
| Deployment owner | Approve Cloud Run/Secret Manager cutover and rollback | Revision/traffic plan, numbered secret versions | What window and rollback authority apply? | `PENDING_OWNER_APPROVAL` | — | — |
| Neo4j account owner | Approve Aura target tier, region, snapshot/export permissions | Tier, limits, version, snapshot/export facts | Which method and target capacity are contractually available? | `PENDING_OWNER_APPROVAL` | — | — |

## Execution gate

Execution remains prohibited until every row has an explicit approval reference and date, the manual Aura and billing checklists are complete, the isolated target identity is proven non-production, and the final parity/rollback owner signs off. Approval of this document does not authorize target creation, snapshot/export, secret changes, deployment, traffic changes, or retention.
