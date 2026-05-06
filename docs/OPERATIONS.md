# Production Operations

This platform is designed for one technical founder. The default operating model is:

- Level 0 actions run automatically.
- Level 1 actions run automatically and write audit logs.
- Level 2 actions create approval items.
- Level 3 actions are manual only and are never executed by autonomous workers.

## Security

Set API keys in backend environment variables:

- `VIEWER_API_KEY`
- `ANALYST_API_KEY`
- `ADMIN_API_KEY`
- `SUPER_ADMIN_API_KEY`

The frontend only receives `NEXT_PUBLIC_API_BASE_URL`. Vendor API keys remain backend-only.

## Protected Operations

Protected endpoints require `X-API-Key`.

- Analyst: safe refreshes, telemetry ingestion, cognition refreshes, governance/alignment refreshes.
- Admin: discovery, autonomy runs, approval center operations.
- Super admin: policy creation and rollback.

All protected requests receive an `X-Trace-ID` response header and write an `AuditEvent` node to Neo4j.

## Idempotency

Mutation clients should send `X-Idempotency-Key`. If a completed audit event already exists for the same endpoint and idempotency key, the backend rejects the duplicate request.

## Backups

Backups must not be stored inside the app source folder.

Use:

```powershell
.\scripts\neo4j-backup.ps1 -OutputDirectory D:\pc-builder-backups
```

Restore is manual and destructive. Confirm the target environment before running:

```powershell
.\scripts\neo4j-restore.ps1 -DumpFile D:\pc-builder-backups\neo4j-20260506-010000.dump
```

## Daily Founder Brief

`GET /ops/daily-report` summarizes:

- Neo4j health
- worker status
- failed jobs
- successful refreshes
- new products discovered
- source configuration
- telemetry gaps
- cognition risks
- pending approvals
- recent audit events

The frontend "Founder Daily Brief" panel is the top of the solo-founder command center. It keeps successful automatic work separate from items that need attention.

## Autonomy Queue

`GET /ops/autonomy-queue` groups jobs into:

- running now
- waiting approval
- failed or needs attention
- recently completed
- scheduled next

Jobs include risk level, retry count, trace ID, bounded retry metadata, and whether approval is required. `POST /ops/autonomy-queue/{job_id}/cancel` only works for cancellable bounded jobs and writes an audit event.

## Approval Center

`GET /approvals/pending` and `GET /approvals/{id}` expose pending high-risk actions with reasoning, evidence, affected entities, expected impact, and rollback plan.

Decision endpoints:

- `POST /approvals/{id}/approve`
- `POST /approvals/{id}/reject`
- `POST /approvals/{id}/defer`
- `POST /approvals/{id}/mark-reviewed`

All decisions are audited. Level 3 manual-only actions cannot be approved for autonomous execution.

## Live Source Onboarding

Live vendor credentials must be placed only in `backend/.env`; never in frontend files or committed source.

Safe source visibility:

- `GET /ops/source-config`
- shows source name, configured flag, health, last success/failure, sanitized error, and quota status
- never returns raw key values

Controlled discovery dry run:

```json
{
  "category": "GPU",
  "query": "RTX 4070 Super",
  "region": "US",
  "limit": 10,
  "dry_run": true
}
```

Dry run fetches configured sources, normalizes listings, validates quality, reports canonical merge decisions, and does not mutate product/vendor/price nodes.

Live controlled ingestion uses the same payload with `"dry_run": false`. It is Level 1 automation: audit-required, bounded, idempotency-aware, and not approval-gated unless it proposes a high-impact graph mutation.

Canonicalization validation:

- `POST /pricing/canonicalize`
- validates naming variants such as `RTX4070SUPER`, `RTX 4070 Super`, and `NVIDIA GeForce RTX 4070 Super`
- returns normalized name, canonical key, merge decision, confidence, and reason

## Deployment

Local production stack:

```bash
docker compose up --build
```

Before deployment:

- copy `backend/.env.example` to a secure environment provider
- set Neo4j credentials
- set admin API keys
- set only the vendor API keys you actually use
- keep `AUTH_REQUIRED=true`
