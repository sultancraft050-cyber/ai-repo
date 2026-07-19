# Cloud SQL Catalog 5% Production Canary Result

## Summary

On 2026-07-19, a controlled traffic split was executed for the `hardware-intelligence-api` service, routing 5% of production traffic to the verified Cloud SQL catalog revision `hardware-intelligence-api-catalog-v2-20260719` and 95% of traffic to the existing production revision `hardware-intelligence-api-00005-kvd`. Bounded validation traffic was sent, and the canary succeeded with zero errors, zero pool timeouts, and zero data mutations.

---

## Coordinates & Settings

- **Starting commit**: `9011ab7`
- **Prerequisite CI run**: `29697610593` — SUCCESSFUL
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
| **Before 17:56 UTC** | Zero-traffic baseline | 100% | 0% |
| **After 17:56 UTC** | 5% Canary Shift | 95% | 5% |

**Service max Scale adjusted to 20** to allow division of instances among multiple active revisions.

---

## Observation Period

- **Start Time**: 2026-07-19T17:56:49Z
- **End Time**: 2026-07-19T18:09:56Z
- **Duration**: ~13 minutes (Observation timer successfully registered and run)

---

## Generated Bounded Read-Only Traffic

A sequence of 200 read-only requests was routed through the production endpoint:

| Route | Requests | Success (200 OK) | 404 Not Found (V1 fallback) | Details / Expected |
|---|---|---|---|---|
| `/health` | 100 | 100 | 0 | ok:true, neo4j:connected |
| `/components/options?kind=CPU` | 40 | 40 | 0 | Non-catalog read route |
| `/catalog/products` | 40 | 2 | 38 | Probabilistic split (5% target) |
| `/catalog/products/180` | 20 | 2 | 18 | Probabilistic split (5% target) |

**Total requests generated**: 200

### Request split per revision:
- **Old revision (V1)**: 156 requests handled
- **New revision (V2)**: 44 requests handled (including direct baseline health checks and probabilistic production traffic)

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

## Log Inspection

Logs from both revisions were inspected for anomalies:
- **Old Revision logs**: Only standard `INFO` logs and expected `WARNING` / `404` logs for endpoints that are only enabled on V2 (e.g. `/catalog/products`).
- **Canary Revision logs**: Successful `200 OK` logs for all catalog read requests.
- **Uncaught exceptions**: 0
- **Cloud SQL errors**: 0
- **Pool exhaustion or timeout errors**: 0
- **Neo4j errors**: 0
- **Scheduler, migration, or import startup logs**: None detected (correctly safe-off)
- **Credential / Secret leakage**: None
- **Complete database URL leakage**: None

---

## Rollback Evaluation

Rollback was **NOT** required during this iteration as all checks passed successfully.

### Rollback / Recovery Command (Pre-validated):
```powershell
gcloud run services update-traffic hardware-intelligence-api --region=me-central1 --to-revisions=hardware-intelligence-api-00005-kvd=100
```

---

## Safety Confirmations

- **No writes occurred**: Verified.
- **No data changed**: Checked.
- **No secrets were exposed**: Checked.
- **No code modification committed**: Confirmed.
