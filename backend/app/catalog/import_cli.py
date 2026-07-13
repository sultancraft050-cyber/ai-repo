from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.catalog.database import CatalogDatabase
from app.catalog.import_pipeline import CatalogImportPipeline, ImportLimits, read_file_bounded, stage_result
from app.catalog.models import ImageRightsStatus, ImportSource, SourceType


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage a bounded synthetic catalog import locally.")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--entity-type", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--format", choices=("csv", "json"))
    parser.add_argument("--dry-run", action="store_true", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    url = os.getenv("CATALOG_DATABASE_URL", "")
    if not url.startswith("sqlite:///"):
        raise SystemExit("Dry-run CLI requires an explicit local SQLite CATALOG_DATABASE_URL.")
    limits = ImportLimits()
    content = read_file_bounded(args.file, limits.max_file_size)
    file_format = args.format or args.file.suffix.lstrip(".").lower()
    database = CatalogDatabase()
    with database.session() as session:
        now = datetime.now(timezone.utc)
        source = session.scalar(select(ImportSource).where(ImportSource.name == args.source))
        if source is None:
            source = ImportSource(
                name=args.source,
                source_type=SourceType.CSV.value if file_format == "csv" else SourceType.JSON.value,
                rights_status=ImageRightsStatus.REVIEW.value,
                active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(source)
            session.flush()
        result = CatalogImportPipeline(session, limits).dry_run(
            content,
            file_format=file_format,
            entity_type=args.entity_type,
        )
        batch = stage_result(session, source, result)
        print(json.dumps({"batch_id": batch.id, "status": batch.status, **result.summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
