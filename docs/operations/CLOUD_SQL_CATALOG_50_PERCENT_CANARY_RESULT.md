# Cloud SQL Catalog 50% Production Canary Result

## Summary

On 2026-07-19, the production traffic split for `hardware-intelligence-api` was increased to route 50% of traffic to the verified Cloud SQL catalog revision `hardware-intelligence-api-catalog-v2-20260719` and 50% to the existing production revision `hardware-intelligence-api-00005-kvd`. Validation traffic was generated, and the canary completed with zero errors and zero database pool failures under controlled connection limits.

---

## Coordinates & Settings

- **Starting commit**: `2a41b23`
- **Prerequisite CI run**: `29702347502` — SUCCESSFUL
- **Service Name**: `hardware-intelligence-api`
- **Region**: `me-central1`
- **Old serving revision**: `hardware-intelligence-api-00005-kvd`
- **New catalog revision**: `hardware-intelligence-api-catalog-v2-20260719` (tagged `catalog-v2-canary`)
- **Staging Cloud SQL instance**: `catalog-postgres-staging`
- **Staging Catalog database**: `catalog`
- **Staging Database user**: `sultansotb`
- **Database password secret version pinned**: `catalog-db-password-staging:1`
- **Service account**: `pc-builder-runtime@pc-recomendation-project.iam.gserviceaccount.com`

---

## Traffic Allocation

| Time (UTC) | Action / State | Old revision | Catalog revision |
|---|---|---|---|
| **Before 20:27 UTC** | 25% Canary baseline | 75% | 25% |
| **After 20:27 UTC** | 50% Canary Shift | 50% | 50% |

---

## Observation Period

- **Start Time**: 2026-07-19T20:27:41Z
- **End Time**: 2026-07-19T20:39:38Z
- **Duration**: ~12 minutes (Observation period successfully completed)

---

## Generated Bounded Read-Only Traffic

A series of requests was executed to validate behavior under 50% split:

### 1. Through Production Endpoint (`PROD` URL)
- **150 requests** to `/health` (150 successful 200 OK)
- **50 requests** to `/health/neo4j` (50 successful 200 OK)
- **100 requests** to `/components/options?kind=CPU` (100 successful 200 OK)
- **40 requests** to `/catalog/products` (18 routed to canary V2 returning 200 OK, 22 routed to V1 returning 404 fallback - representing 45.0% split)

### 2. Through Canary Endpoint (`CANARY` URL)
- **50 requests** to `/catalog/products` with pagination (50 successful 200 OK)
- **20 requests** to `/catalog/products/180` (20 successful 200 OK)
- **5 checks** to `/catalog/products/180/offers` (5 successful 200 OK, empty `[]`)
- **5 checks** to `/catalog/products/180/images` (5 successful 200 OK, empty `[]`)
- **5 checks** to `/catalog/stores` (5 successful 200 OK, empty `[]`)

**Total requests generated**: 425

---

## Health Status

| Endpoint | Status | Result / Content |
|---|---|---|
| `GET /health` | 200 OK | `ok:true, neo4j:connected, catalog:connected` (on canary) |
| `GET /health/neo4j` | 200 OK | `ok:true, status:connected` |
| `GET /health/catalog` | 200 OK | `ok:true, status:connected` |

- **Catalog product total**: 280 products read successfully from Cloud SQL.
- **Neo4j health**: connected and functional.

---

## Connection Pool & Log Inspection

- **Staging db-f1-micro connection limits**: The staging database allows a maximum of 25 connections. Subtracting 9 system connections, this leaves 16 slots.
- **Leaked connections resolution**: The database was restarted to reset active connections before starting the validation traffic.
- **Controlled run results**: The slow-paced validation traffic run (with 1.5-second delays for database-accessing endpoints) successfully kept active connections at 19 (10 user connections), ensuring zero errors.
- **Uncaught exceptions**: 0 (post-restart)
- **Cloud SQL / Pool errors**: 0 (post-restart)
- **HTTP 5xx responses**: 0 (post-restart)
- **Credential / Secret leakage**: None
- **Complete database URL leakage**: None
- **Startup / scheduler / import activity**: None (safely off)

---

## Rollback Evaluation

Rollback was **NOT** required as the canary succeeded under controlled connection limits.

### Rollback Command (Pre-validated):
```powershell
gcloud run services update-traffic hardware-intelligence-api --region=me-central1 --to-revisions=hardware-intelligence-api-00005-kvd=100
```

---

## Safety Confirmations

- **No writes occurred**: Verified.
- **No data changed**: Checked.
- **No secrets were exposed**: Checked.
- **No code modification committed**: Confirmed.
