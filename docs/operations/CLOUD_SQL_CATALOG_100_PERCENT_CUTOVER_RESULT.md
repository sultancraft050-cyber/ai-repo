# Cloud SQL Catalog 100% Production Cutover Result

## Summary

On 2026-07-19, the production cutover for `hardware-intelligence-api` was completed by routing 100% of traffic to the verified Cloud SQL catalog revision `hardware-intelligence-api-catalog-v2-20260719` and 0% to the legacy revision `hardware-intelligence-api-00005-kvd`. Validation traffic was successfully generated, and the cutover completed with the service fully functional and healthy.

---

## Coordinates & Settings

- **Starting commit**: `4530279`
- **Service Name**: `hardware-intelligence-api`
- **Region**: `me-central1`
- **Production revision**: `hardware-intelligence-api-catalog-v2-20260719` (100% traffic)
- **Legacy revision**: `hardware-intelligence-api-00005-kvd` (0% traffic)
- **Staging Cloud SQL instance**: `catalog-postgres-staging`
- **Staging Catalog database**: `catalog`
- **Staging Database user**: `sultansotb`
- **Database password secret version pinned**: `catalog-db-password-staging:1`
- **Service account**: `pc-builder-runtime@pc-recomendation-project.iam.gserviceaccount.com`

---

## Traffic Allocation

| Time (UTC) | Action / State | Old revision | Catalog revision |
|---|---|---|---|
| **Before 20:44 UTC** | 50% Canary baseline | 50% | 50% |
| **After 20:44 UTC** | 100% Cutover | 0% | 100% |

---

## Generated Bounded Read-Only Traffic

A series of requests was executed to validate behavior under 100% split:

### 1. Through Production Endpoint (`PROD` URL)
- **150 requests** to `/health` (150 successful 200 OK)
- **50 requests** to `/health/neo4j` (50 successful 200 OK)
- **100 requests** to `/components/options?kind=CPU` (100 successful 200 OK)
- **40 requests** to `/catalog/products` (40 routed to canary V2 returning 200 OK, 0 fallback - 100% split verified)

### 2. Through Canary Endpoint (`CANARY` URL)
- **50 requests** to `/catalog/products` with pagination (50 successful 200 OK)
- **20 requests** to `/catalog/products/180` (20 successful 200 OK)
- **5 checks** to `/catalog/products/180/offers` (5 successful 200 OK)
- **5 checks** to `/catalog/products/180/images` (5 successful 200 OK)
- **5 checks** to `/catalog/stores` (5 successful 200 OK)

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

- **Staging db-f1-micro connection limits**: The staging database allows a maximum of 25 connections.
- **Transient slot warning**: A transient FATAL error (`remaining connection slots are reserved for non-replication superuser connections`) was observed at `20:47:38Z` during the rapid burst of validation requests (150 health requests in 15 seconds) combined with load balancer probes. The connection pool successfully recovered, and subsequent health checks resolved with `200 OK` (ok:true, catalog:connected).
- **Uncaught exceptions**: 0
- **Credential / Secret leakage**: None
- **Complete database URL leakage**: None
- **Startup / scheduler / import activity**: None (safely off)

---

## Safety Confirmations

- **No writes occurred**: Verified.
- **No data changed**: Checked.
- **No secrets were exposed**: Checked.
- **No code modification committed**: Confirmed.
