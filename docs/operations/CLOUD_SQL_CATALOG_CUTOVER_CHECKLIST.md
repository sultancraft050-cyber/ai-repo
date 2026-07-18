# Cloud SQL Catalog Cutover Checklist

This checklist details the exact migration and deployment sequence for transition to the Cloud SQL primary database.

## 1. Preflight Checklist
- [ ] Verify that `catalog-postgres-staging` is active and running in `me-central1`.
- [ ] Confirm secret name `catalog-db-password-staging` contains the correct database user credentials.
- [ ] Ensure `pc-recomendation-catalog-media-1025898878832` GCS bucket is active and private.
- [ ] Confirm full test suite passes locally.

## 2. No-Traffic Schema Setup
- [ ] Start Cloud SQL proxy locally or run a temporary admin job.
- [ ] Run the migration CLI against the staging instance:
  ```bash
  python -m app.catalog.migration_cli migrate
  ```
- [ ] Execute database inspection to verify that all catalog tables are successfully created:
  ```bash
  python -m app.catalog.migration_cli inspect
  ```

## 3. Deployment Configuration (No Traffic)
- [ ] Deploy the updated container image to Cloud Run service `hardware-intelligence-api` with 0% traffic allocation.
- [ ] Attach `catalog-db-password-staging` secret as `CATALOG_DB_PASSWORD`.
- [ ] Set `CATALOG_V2_ENABLED="true"` and `CATALOG_WRITES_ENABLED="false"`.
- [ ] Verify the service starts cleanly and registers `connected` or `disabled` on the health endpoints without crash loops.

## 4. Rollback Plan
If any step fails or health check is degraded:
- [ ] Downgrade the schema using `alembic downgrade`.
- [ ] Revert environment variables `CATALOG_V2_ENABLED` to `false` and restart service.
