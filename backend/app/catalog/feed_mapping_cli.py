"""Safe local CLI for synthetic feed mapping templates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.catalog.feed_mapping import FeedMappingService, MappingError

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = (ROOT / "tests" / "fixtures").resolve()


def _fixture(path: str) -> Path:
    value = Path(path).expanduser().resolve()
    if FIXTURES not in value.parents or not value.is_file():
        raise MappingError("TEMPLATE_INVALID")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Map synthetic catalog feeds locally.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-template"); validate.add_argument("--template", required=True)
    listing = sub.add_parser("list-templates"); listing.add_argument("--directory", default=str(FIXTURES / "catalog_feed_mappings"))
    preview = sub.add_parser("preview"); preview.add_argument("--template", required=True); preview.add_argument("--file", required=True)
    stage = sub.add_parser("stage"); stage.add_argument("--template", required=True); stage.add_argument("--file", required=True)
    compare = sub.add_parser("compare-versions"); compare.add_argument("--from", dest="first", required=True); compare.add_argument("--to", dest="second", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        service = FeedMappingService()
        if args.command == "list-templates":
            directory = Path(args.directory).expanduser().resolve()
            if FIXTURES not in directory.parents or not directory.is_dir(): raise MappingError("TEMPLATE_INVALID")
            result = [{"template_id": item.template_id, "template_version": item.version, "checksum": item.checksum, "entity_type": item.entity_type} for item in service.list_templates(directory)]
        elif args.command == "validate-template":
            item = service.load_template(_fixture(args.template)); result = {"valid": True, "template_id": item.template_id, "template_version": item.version, "checksum": item.checksum, "entity_type": item.entity_type}
        elif args.command == "compare-versions":
            result = service.compare_versions(service.load_template(_fixture(args.first)), service.load_template(_fixture(args.second)))
        else:
            template = service.load_template(_fixture(args.template)); results = service.map_file(template, _fixture(args.file).read_bytes())
            result = {"template_id": template.template_id, "template_version": template.version, "template_checksum": template.checksum, "record_count": len(results), "validation_counts": {status: sum(item.validation_status == status for item in results) for status in sorted({item.validation_status for item in results})}, "records": [item.safe_dict() for item in results]}
            if args.command == "stage":
                if os.getenv("CATALOG_DATABASE_URL", "").startswith("sqlite:///") and os.getenv("CATALOG_IMPORT_ENABLED", "false").lower() in {"1", "true", "yes"}:
                    from app.catalog.database import CatalogDatabase
                    with CatalogDatabase().session() as session: result["batch_id"] = service.stage(session, template, results).id
                else: raise MappingError("TEMPLATE_INVALID")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (MappingError, OSError, UnicodeError) as error:
        print(json.dumps({"error_code": getattr(error, "code", "TEMPLATE_INVALID"), "message": str(error).split(":", 1)[-1].strip()}, sort_keys=True))
        return 2


if __name__ == "__main__": raise SystemExit(main())
