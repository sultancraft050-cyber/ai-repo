# Neo4j Migration Approval Gate Checklist

Documentation-only gate. Do not create a target, operate on snapshots, change secrets, deploy, or incur cloud cost while completing this checklist.

| Essential fact | User/provider value | Status |
|---|---|---|
| Source database identifier | `[INSERT ONE RELIABLE INSTANCE NAME OR ID]` | REQUIRED |
| Current Aura tier | `[INSERT]` | REQUIRED |
| Current region | `[INSERT]` | REQUIRED |
| Neo4j version | `[INSERT]` | REQUIRED |
| Current nodes and verified capacity limit | `[INSERT]` | REQUIRED |
| Latest successful snapshot | `[INSERT DATE AND STATUS]` | REQUIRED |
| Create-from-snapshot available | `[YES / NO]` | REQUIRED |
| Selected target capacity | `[INSERT TARGET TIER OR CAPACITY]` | REQUIRED |
| Selected target region | `[INSERT]` | REQUIRED |
| Estimated monthly cost | `[INSERT]` | REQUIRED |
| Estimated temporary overlap cost | `[INSERT]` | REQUIRED |
| Purchase path | `[MARKETPLACE / DIRECT]` | REQUIRED |
| Promotional-credit result | `[YES / NO / UNKNOWN]` | REQUIRED; UNKNOWN blocks |
| Approved monthly budget | `[INSERT]` | REQUIRED |
| Migration owner approval | `[APPROVED / PENDING]` | REQUIRED; PENDING blocks |
| Billing approval | `[APPROVED / PENDING]` | REQUIRED; PENDING blocks |
| Deployment approval | `[APPROVED / PENDING]` | REQUIRED; PENDING blocks |
| Approval date | `[INSERT]` | REQUIRED |

## Confirmed planning baseline

- Source: approximately 200,000 nodes and 208,319 relationships; at or near capacity.
- Recommendation: larger Neo4j 5.27-compatible AuraDB Professional target.
- Sequence: migrate before destructive cleanup; keep the current source intact for rollback.
- Planning capacity: at least 400,000 logical nodes; preferred six-month target approximately 600,000; preferred twelve-month target approximately 1,000,000.
- Safe-off flags: `PRICING_SCHEDULER_ENABLED=false`, `AUTONOMOUS_AGENTS_ENABLED=false`, `CPU_SPECS_SEED_ON_START=false`.

Do not treat placeholders, `UNKNOWN`, `PENDING`, or blank values as approval. One responsible person may hold the migration, billing, and deployment roles if explicitly documented.
