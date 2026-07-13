# Neo4j Migration Approval Record

Record only the essential provider and approval facts below. Do not invent values or record credentials, connection URIs, or private account identifiers.

| Essential fact | Value | Status |
|---|---|---|
| Source database identifier | `[INSERT ONE RELIABLE INSTANCE NAME OR ID]` | REQUIRED |
| Current Aura tier | `[INSERT]` | REQUIRED |
| Current region | `[INSERT]` | REQUIRED |
| Neo4j version | `[INSERT]` | REQUIRED |
| Current nodes and verified capacity limit | `[INSERT]` | REQUIRED |
| Latest successful snapshot | `[INSERT DATE AND STATUS]` | REQUIRED |
| Create-from-snapshot available | `[YES / NO]` | REQUIRED |
| Target tier or target capacity | `[INSERT]` | REQUIRED |
| Target region | `[INSERT]` | REQUIRED |
| Estimated monthly cost | `[INSERT]` | REQUIRED |
| Estimated temporary overlap cost | `[INSERT]` | REQUIRED |
| Purchase path | `[MARKETPLACE / DIRECT]` | REQUIRED |
| Promotional credit usable | `[YES / NO / UNKNOWN]` | REQUIRED; UNKNOWN blocks |
| Approved monthly budget | `[INSERT]` | REQUIRED |
| Migration owner approval | `[APPROVED / PENDING]` | REQUIRED; PENDING blocks |
| Billing approval | `[APPROVED / PENDING]` | REQUIRED; PENDING blocks |
| Deployment approval | `[APPROVED / PENDING]` | REQUIRED; PENDING blocks |
| Approval date | `[INSERT]` | REQUIRED |

## Gate rule

The result is `READY_TO_CREATE_ISOLATED_TARGET` only when every required value is supplied, all three approvals are `APPROVED`, the snapshot is recent and successful, create-from-snapshot is confirmed, and the current source remains intact for rollback. Otherwise the result is `BLOCKED_MISSING_ESSENTIAL_FACTS`.
