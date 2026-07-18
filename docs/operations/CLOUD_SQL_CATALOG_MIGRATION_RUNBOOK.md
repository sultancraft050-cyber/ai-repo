# Cloud SQL Catalog Migration Runbook

This runbook guides running schema migrations and inspecting database status on the Cloud SQL primary database.

## 1. Migration Command
To execute database schema migrations up to the head revision without starting the web server or connecting to Neo4j:
```bash
# Run inside backend environment with credentials configured
python -m app.catalog.migration_cli migrate
```
**Safety details:**
- Exits non-zero on migration failure.
- Prints only the safe target database URL with the password redacted.
- Reports the resulting migration revision on completion.

## 2. Inspection Command
To check the current database schema state, tables, and row counts:
```bash
# Run inside backend environment
python -m app.catalog.migration_cli inspect
```
**Output information:**
- Current database Alembic revision.
- Expected head revision.
- List of database tables.
- Total row count per table.

## 3. Dry-Run & Staging Verification
1. To run migrations in dry-run mode, configure a temporary SQLite database URL:
   ```bash
   export CATALOG_DATABASE_URL="sqlite:///./temp-test.sqlite3"
   python -m app.catalog.migration_cli migrate
   ```
2. Verify that `temp-test.sqlite3` is created and has the correct schema using the inspection command.

## 4. Rollback
In the event of database issues or migration failures:
1. Revert to a previous revision:
   ```bash
   # Run standard alembic downgrade
   alembic downgrade -1
   ```
2. If necessary, delete the local staging database or recreate tables from the clean schema.
