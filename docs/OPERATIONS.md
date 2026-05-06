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

The frontend “Founder Daily Brief” panel is the primary solo-founder admin surface.

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
