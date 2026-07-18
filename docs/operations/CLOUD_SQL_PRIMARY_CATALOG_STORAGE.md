# Cloud SQL Primary Catalog Storage Configuration

## 1. Existing Google Cloud Resources
- **Project:** `pc-recomendation-project`
- **Region:** `me-central1`
- **Cloud Run Service:** `hardware-intelligence-api`
- **Cloud Run Service Account:** `pc-builder-runtime@pc-recomendation-project.iam.gserviceaccount.com`
- **Cloud SQL Instance:** `catalog-postgres-staging`
- **Cloud SQL Database:** `catalog`
- **Cloud SQL Database User:** `sultansotb`
- **Cloud SQL Connection Name:** `pc-recomendation-project:me-central1:catalog-postgres-staging`
- **Database Password Secret:** `catalog-db-password-staging`
- **Cloud Storage Bucket:** `pc-recomendation-catalog-media-1025898878832`

## 2. Required Configuration
The backend accesses Cloud SQL using the following environment variables:
- `CATALOG_DATABASE_URL`: (Optional) Explicit database URL.
- `CATALOG_DB_USER`: `sultansotb`
- `CATALOG_DB_NAME`: `catalog`
- `CATALOG_DB_PASSWORD`: Password supplied at runtime via Secret Manager.
- `CATALOG_CLOUD_SQL_CONNECTION_NAME`: `pc-recomendation-project:me-central1:catalog-postgres-staging`
- `CATALOG_MEDIA_BUCKET`: `pc-recomendation-catalog-media-1025898878832`

## 3. Unix-Socket Connection
When running in Cloud Run, the Cloud SQL proxy mounts the database socket under `/cloudsql`.
The backend dynamically constructs the Unix-socket URL:
`postgresql+psycopg2://{user}:{password}@/catalog?host=/cloudsql/pc-recomendation-project:me-central1:catalog-postgres-staging`

## 4. Secret Manager Runtime Binding
- The database password is never checked into git or hardcoded.
- At runtime on Cloud Run, the secret version `catalog-db-password-staging` is exposed to the container environment variable `CATALOG_DB_PASSWORD`.

## 5. Cloud Storage Integration
- **Role:** Holds all approved product image files, optimized variants, feed archives, and logs.
- **SQL Parity:** PostgreSQL stores only object keys (e.g. `images/cpu/123.jpg`) and metadata records. No raw image bytes enter PostgreSQL.
- **Access Control:** The storage bucket is kept strictly private.

## 6. Coexistence with Neo4j
- **PostgreSQL:** Stores catalog master tables (products, specs, images, stores, offers, prices, imports).
- **Neo4j:** Stores compatibility relationships, user build configurations, autonomy graphs, and audit history.
- **Data Excluded from Migration:** Audit logs, telemetry, governance, autonomy, cognition, and evolution databases remain solely in Neo4j.
