# BuildCores OpenDB Bounded Import — Result

## Summary

On 2026-07-18, the first bounded BuildCores OpenDB product catalog batch was
successfully imported into the Cloud SQL `catalog` staging database.

---

## Import Parameters

| Field | Value |
|---|---|
| Starting commit | `43b56d3742a89a6bda9d729ebc00a5325e67ade9` |
| CI prerequisite run | `29656126639` — PASSED |
| OpenDB source commit | `784f6c2b5988bf5a7e94bd2121f9d56521386dd9` |
| License | ODC-By 1.0 |
| Attribution created | `docs/third-party/BUILDCORES_OPENDB_ATTRIBUTION.md` |
| Import date | 2026-07-18 |

---

## Source Inspection

| Field | Value |
|---|---|
| Categories scanned | CPU, GPU, MOTHERBOARD, RAM, STORAGE, PSU, CASE, COOLER |
| Files discovered | 25,699 |
| Records parsed | 280 |
| Schema-valid | All 280 (100%) |
| Schema-invalid | 0 |

---

## Dry-Run Results

| Field | Value |
|---|---|
| Records selected | 280 |
| Duplicate identities | 0 |
| Missing identities | 0 |
| Existing conflicts | 0 |
| Manual-review records | 0 |
| Price/offer/image data | None detected |
| Dry-run result | **PASSED** |

---

## Pre-Import Backup

| Field | Value |
|---|---|
| Backup ID | `1784401199081` |
| Backup status | `SUCCESSFUL` |
| Description | `pre-buildcores-bounded-import-20260718` |
| Instance | `catalog-postgres-staging` |

---

## Import Execution

| Field | Value |
|---|---|
| ImportSource ID | 7 |
| ImportBatch ID | 7 |
| ImportSource name | `BuildCores OpenDB (commit: 784f6c2b5988...)` |
| ImportBatch status | `COMPLETED` |

---

## Products Imported

| Category | Count |
|---|---|
| CPU | 40 |
| GPU | 40 |
| MOTHERBOARD | 40 |
| RAM | 40 |
| STORAGE | 40 |
| PSU | 30 |
| CASE | 30 |
| COOLER | 20 |
| **TOTAL** | **280** |

---

## Specifications Imported

| Field | Value |
|---|---|
| Total specifications | 1,562 |
| All have source_id | YES |
| All linked to product | YES |

---

## Explicit Exclusions Confirmed

| Excluded Type | Result |
|---|---|
| Prices | 0 imported |
| Retailer offers | 0 imported |
| Store offers | 0 imported |
| Price history rows | 0 imported |
| Product image rows | 0 imported |
| Cloud Storage objects | 0 uploaded |
| Neo4j records | 0 modified |
| Cloud Run | Not deployed |
| Traffic | Not changed |
| Secrets exposed | NO |

---

## Verification Results

| Check | Result |
|---|---|
| Total products in DB | 280 |
| Total specs in DB | 1,562 |
| Store offers | 0 |
| Price history | 0 |
| Product images | 0 |
| Duplicate GTINs | 0 |
| Duplicate brand+MPN | 0 |
| CPU sample reads | 3 records retrieved OK |
| GPU sample reads | 3 records retrieved OK |
| Pagination | page1=10, page2=10 OK |
| Products without source_id | 0 |
| **VERIFICATION** | **PASSED** |

---

## Idempotency Test

| Check | Result |
|---|---|
| Records scanned | 280 |
| Would insert | 0 |
| Would skip | 280 |
| **IDEMPOTENCY** | **PASSED** |

---

## Safety Assertions

| Assertion | Confirmed |
|---|---|
| Cloud Run deployed | NO |
| Traffic changed | NO |
| Neo4j modified | NO |
| Catalog V2 enabled in production | NO |
| Prices imported | NO |
| Images imported | NO |
| Offers imported | NO |
| Secrets printed/committed | NO |
| Force-push used | NO |

---

## Rollback Procedure

If rollback is required, restore from Cloud SQL backup:

```bash
gcloud sql backups restore 1784401199081 \
  --restore-instance=catalog-postgres-staging \
  --project=pc-recomendation-project
```

---

## Files Changed

- `backend/app/catalog/buildcores_import_cli.py` — Cloud SQL import CLI (new)
- `backend/app/catalog/buildcores_opendb_adapter.py` — Updated CATEGORY_LIMITS
- `backend/tests/test_buildcores_import_cli.py` — Import CLI tests (new)
- `backend/pyproject.toml` — Added tmp_path_retention_policy
- `docs/third-party/BUILDCORES_OPENDB_ATTRIBUTION.md` — ODC-By attribution (new)
- `docs/operations/BUILDCORES_OPENDB_IMPORT_RUNBOOK.md` — Import runbook (new)
- `docs/operations/BUILDCORES_OPENDB_BOUNDED_IMPORT_RESULT.md` — This file (new)
- `docs/engineering/CURRENT_STATE.md` — Updated
- `docs/engineering/EVOLUTION_LOG.md` — Updated
- `docs/engineering/NEXT_TASK.md` — Updated

---

## Tests

- 442 passed (with `--basetemp` to work around Windows AppData/Temp ACL issue)
- 41 new tests in `test_buildcores_import_cli.py`
- All pre-existing tests continue to pass
