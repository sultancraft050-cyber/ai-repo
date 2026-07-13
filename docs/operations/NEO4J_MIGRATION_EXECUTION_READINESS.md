# Neo4j Migration Execution Readiness

**Result:** `BLOCKED_MISSING_ESSENTIAL_FACTS`

This iteration reduces the gate to the minimum facts required before creating an isolated larger target. No target, snapshot, export, restore, production query, mutation, secret change, deployment, or cloud-cost event occurred.

## Confirmed planning facts

- Source: approximately 200,000 nodes and 208,319 relationships; at or near capacity.
- Recommended target: larger Neo4j 5.27-compatible AuraDB Professional.
- Migration order: migrate before destructive cleanup; retain the current source for rollback.
- Planning capacity: at least 400,000 logical nodes; preferred six-month target approximately 600,000; preferred twelve-month target approximately 1,000,000.
- Safe-off flags remain `PRICING_SCHEDULER_ENABLED=false`, `AUTONOMOUS_AGENTS_ENABLED=false`, and `CPU_SPECS_SEED_ON_START=false`.

## Essential facts still required

The following are not available as reliable user/provider facts in the repository and therefore block readiness:

- Source database identifier
- Current Aura tier
- Current region
- Neo4j version
- Current nodes and verified capacity limit
- Latest successful snapshot date and status
- Create-from-snapshot availability
- Selected target tier or capacity
- Selected target region
- Estimated monthly cost
- Estimated temporary overlap cost
- Purchase path
- Promotional-credit result
- Approved monthly budget
- Migration owner approval
- Billing approval
- Deployment approval
- Approval date

No optional facts are listed as blockers. Do not treat placeholders, `UNKNOWN`, `PENDING`, or blank values as approval. Do not generate a target-creation or migration-execution prompt until all required facts and approvals are supplied. A single responsible person may hold all three approval roles when explicitly documented.
