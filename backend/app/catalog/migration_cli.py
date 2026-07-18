from __future__ import annotations

import argparse
import sys
from pathlib import Path
from alembic.config import Config
from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.catalog.database import build_db_url, redact_url

def main(args_list: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Catalog V2 Migration and Inspection Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command migrate
    subparsers.add_parser("migrate", help="Run database migrations to head")

    # Command inspect
    subparsers.add_parser("inspect", help="Inspect current migration and database state")

    args = parser.parse_args(args_list)

    db_url = build_db_url()
    if not db_url:
        print("ERROR: Database configuration is missing. Configure CATALOG_DATABASE_URL or Cloud SQL credentials.")
        sys.exit(1)

    backend_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = backend_root / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))

    if args.command == "migrate":
        print(f"Running migrations against target: {redact_url(db_url)}")
        try:
            command.upgrade(alembic_cfg, "head")
            engine = create_engine(db_url)
            with engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                current_rev = ctx.get_current_revision()
            print(f"SUCCESS: Migrations completed successfully. Current revision: {current_rev}")
        except Exception as e:
            print(f"ERROR: Migration failed: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "inspect":
        print(f"Database target: {redact_url(db_url)}")
        try:
            engine = create_engine(db_url)
            with engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                current_rev = ctx.get_current_revision()
            
            script = ScriptDirectory.from_config(alembic_cfg)
            head_rev = script.get_current_head()

            print(f"Current revision: {current_rev}")
            print(f"Expected head revision: {head_rev}")

            inspector = inspect(engine)
            tables = inspector.get_table_names()
            print("Tables and Row Counts:")
            with engine.connect() as conn:
                for table in sorted(tables):
                    try:
                        res = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = res.scalar()
                        print(f"  - {table}: {count}")
                    except Exception as te:
                        print(f"  - {table}: Error reading rows ({te})")
        except Exception as e:
            print(f"ERROR: Inspection failed: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
