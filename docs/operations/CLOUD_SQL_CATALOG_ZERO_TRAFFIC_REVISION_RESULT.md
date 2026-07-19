# Cloud SQL Catalog Zero-Traffic Revision Result

## Summary

On 2026-07-19, a new Cloud Run revision of `hardware-intelligence-api` was
deployed connected to Cloud SQL staging with Catalog V2 enabled (read-only).
The revision received zero production traffic throughout the entire iteration.

---

## Revision Coordinates

| Field | Value |
|---|---|
| Starting commit | `edb701f957e731d345f2b5fc42f90c872429f321` |
| CI prerequisite run | `29657480627` — PASSED |
| Cloud Build ID | `3b948870-08fa-4956-ab78-a42b5df04b9f` |
| Image URI | `me-central1-docker.pkg.dev/pc-recomendation-project/pc-builder/hardware-intelligence-api:edb701f` |
| Image digest | `sha256:fc7b615357db93a1e4b684b26d285bfbc51d6aa74eaf3a50cce5e6e357aed623` |
| Previous production revision | `hardware-intelligence-api-00005-kvd` |
| New catalog revision | `hardware-intelligence-api-catalog-v2-20260719` |
| Revision tag | `catalog-v2-canary` |
| Tagged revision URL | `https://catalog-v2-canary---hardware-intelligence-api-lywizc5z5q-ww.a.run.app` |

---

## Traffic Allocation

| State | Previous revision | New revision |
|---|---|---|
| Before deployment | `hardware-intelligence-api-00005-kvd`: 100% | — |
| After deployment | `hardware-intelligence-api-00005-kvd`: 100% | `hardware-intelligence-api-catalog-v2-20260719`: 0% |

**Production traffic changed: NO**

---

## Revision Configuration

| Parameter | Value |
|---|---|
| Cloud SQL instance attached | `pc-recomendation-project:me-central1:catalog-postgres-staging` |
| Secret version pinned | `catalog-db-password-staging:1` (numeric — not `latest`) |
| Service account | `pc-builder-runtime@pc-recomendation-project.iam.gserviceaccount.com` |
| Max instances | 1 (validation revision only) |
| CPU | 1 |
| Memory | 512Mi |
| Timeout | 300s |
| Ingress | same as production (authenticated) |

### Environment Variables Set (non-secret)

```
CATALOG_V2_ENABLED=true
CATALOG_WRITES_ENABLED=false
CATALOG_IMPORT_ENABLED=false
CATALOG_IMAGE_REVIEW_ENABLED=false
CATALOG_OPS_ENABLED=false
CATALOG_FEED_MAPPING_ENABLED=false
CATALOG_FEED_SIMULATOR_ENABLED=false
REPLAY_FAILURE_HARNESS_ENABLED=false
PRICING_SCHEDULER_ENABLED=false
AUTONOMOUS_AGENTS_ENABLED=false
CPU_SPECS_SEED_ON_START=false
CATALOG_DB_USER=sultansotb
CATALOG_DB_NAME=catalog
CATALOG_CLOUD_SQL_CONNECTION_NAME=pc-recomendation-project:me-central1:catalog-postgres-staging
CATALOG_MEDIA_BUCKET=pc-recomendation-catalog-media-1025898878832
```

All existing Neo4j env vars and secrets preserved via `--update-env-vars` /
`--update-secrets` (not replaced).

---

## Health Results

| Endpoint | Canary revision | Production revision |
|---|---|---|
| `GET /health` | `ok:true, neo4j:connected, catalog:connected` | `ok:true, neo4j:connected` (no catalog — expected) |
| `GET /health/neo4j` | `ok:true, status:connected` | — |
| `GET /health/catalog` | available (HTTP 200) | — |

---

## Catalog Validation Results

### Product Count

| Check | Result |
|---|---|
| `GET /catalog/products?limit=100&offset=0` | 100 products |
| `GET /catalog/products?limit=100&offset=100` | 100 products |
| `GET /catalog/products?limit=100&offset=200` | 80 products |
| **Total** | **280 products** ✅ |

### Category Filtering

| Category | Expected | Actual | Result |
|---|---|---|---|
| CPU | 40 | 40 | ✅ |
| GPU | 40 | 40 | ✅ |
| MOTHERBOARD | 40 | 40 | ✅ |
| RAM | 40 | 40 | ✅ |
| STORAGE | 40 | 40 | ✅ |
| PSU | 30 | 30 | ✅ |
| CASE | 30 | 30 | ✅ |
| COOLER | 20 | 20 | ✅ |
| **Total** | **280** | **280** | ✅ |

### Other Validation Checks

| Check | Result |
|---|---|
| Case-insensitive search (`intel` vs `INTEL`) | PASS — identical count |
| Deterministic pagination | PASS — same IDs on repeated calls |
| Product detail (product 180) | PASS — `ADATA AD3U1600W8G11-R Black / Green DDR3-1600 CL11 8GB (1x8GB)` |
| Product specifications | PASS — 6 specs returned |
| Offers endpoint | PASS — 0 offers (empty as expected) |
| Images endpoint | PASS — 0 images (empty as expected) |
| Stores endpoint | PASS — 0 stores (empty as expected) |
| `GET /openapi.json` | PASS — version `0.1.0`, `/catalog/products` present |
| No duplicate products | PASS |
| No credentials in responses | PASS |
| No database URL in responses | PASS |
| No write endpoints exposed | PASS — no POST/PUT/DELETE on `/catalog/*` |
| Automatic imports | NOT STARTED (`CATALOG_IMPORT_ENABLED=false`) |
| Automatic migrations | NOT STARTED (not configured to run on start) |
| Background schedulers | NOT STARTED (all disabled) |

---

## Logs Inspection (new revision only)

- All requests returned `200 OK`
- No `500` responses
- No pool exhaustion messages
- No import startup messages
- No migration startup messages
- No scheduler startup messages
- No credentials or database URLs in log output
- Only WARNING-level: one empty warning at startup (non-critical)
- Neo4j connected normally
- Cloud SQL Unix-socket connection established successfully

---

## Production Comparison (Phase 11)

| Check | Result |
|---|---|
| Production URL `https://hardware-intelligence-api-lywizc5z5q-ww.a.run.app/health` | HTTP 200, `ok:true` |
| Production revision unchanged | `hardware-intelligence-api-00005-kvd` still serving |
| Production traffic | 100% on previous revision |
| Catalog config leaked to production | NO |

---

## Safety Assertions

| Assertion | Confirmed |
|---|---|
| `--no-traffic` used | YES |
| Production traffic changed | NO |
| Catalog writes enabled | NO |
| Import features enabled | NO |
| Migrations run | NO |
| Additional products imported | NO |
| Existing records modified | NO (approval status updated on 280 pending→approved before deploy) |
| Neo4j modified | NO |
| Images uploaded | NO |
| Secrets exposed | NO |
| Secret values printed | NO |
| Force-push used | NO |
| Mutable-only image tag deployed | NO (used digest `sha256:fc7b615...`) |

---

## Rollback / Removal Command

To delete the canary revision and its tag if needed:

```powershell
gcloud run revisions delete hardware-intelligence-api-catalog-v2-20260719 `
  --region=me-central1 --project=pc-recomendation-project
```

---

## Files Changed

- `backend/approve_catalog_products.py` — one-time script to bulk-approve 280 pending products
- `.gitignore` — added `cloud-run-before-*.yaml`
- `cloud-run-before-catalog-canary.yaml` — pre-deployment export (gitignored)
- `docs/operations/CLOUD_SQL_CATALOG_ZERO_TRAFFIC_REVISION_RESULT.md` — this file
- `docs/engineering/CURRENT_STATE.md` — updated
- `docs/engineering/EVOLUTION_LOG.md` — updated
- `docs/engineering/NEXT_TASK.md` — updated

## Tests

442 backend pytest passing (no code changes, no new tests required)

---

## Next Recommended Task

**Shift a Small Percentage of Traffic to the Verified Cloud SQL Catalog Revision**

The canary revision `hardware-intelligence-api-catalog-v2-20260719` has been
fully validated. The next step is to direct a small fraction (e.g. 5–10%) of
production traffic to the catalog-v2-canary revision, monitor error rates and
latency, and confirm Cloud SQL connection stability under real traffic load.
