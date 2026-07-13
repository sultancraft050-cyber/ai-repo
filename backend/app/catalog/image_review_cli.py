from __future__ import annotations

import argparse
import json
import os

from app.catalog.database import CatalogDatabase
from app.catalog.image_review import ImageReviewService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Metadata-only local product image review CLI.")
    parser.add_argument("command", choices=("evaluate-image", "evaluate-product", "list-pending", "list-duplicates", "show-history", "decide"))
    parser.add_argument("--image-id", type=int)
    parser.add_argument("--product-id", type=int)
    parser.add_argument("--decision")
    parser.add_argument("--reason-code")
    parser.add_argument("--reason")
    parser.add_argument("--reviewer")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    url = os.getenv("CATALOG_DATABASE_URL", "")
    if not url.startswith("sqlite:///"):
        raise SystemExit("Image review CLI requires an explicit local SQLite CATALOG_DATABASE_URL.")
    database = CatalogDatabase()
    with database.session() as session:
        service = ImageReviewService(session)
        if args.command == "evaluate-image":
            if args.image_id is None:
                raise SystemExit("--image-id is required")
            output = service.evaluate_image(args.image_id).as_dict()
        elif args.command == "evaluate-product":
            if args.product_id is None:
                raise SystemExit("--product-id is required")
            output = [item.as_dict() for item in service.evaluate_product(args.product_id)]
        elif args.command == "list-pending":
            output = [{"image_id": image.id, "product_id": image.product_id} for image in service.list_pending()]
        elif args.command == "list-duplicates":
            output = service.list_duplicate_groups()
        elif args.command == "show-history":
            if args.image_id is None:
                raise SystemExit("--image-id is required")
            output = [{"id": item.id, "decision": item.decision, "reason_code": item.reason_code, "safe_reason": item.safe_reason, "created_at": item.created_at.isoformat()} for item in service.review_history(args.image_id)]
        else:
            required = (args.image_id, args.decision, args.reason_code, args.reason, args.reviewer)
            if any(value in (None, "") for value in required):
                raise SystemExit("decide requires --image-id, --decision, --reason-code, --reason, and --reviewer")
            audit = service.record_decision(args.image_id, args.decision, reason_code=args.reason_code, safe_reason=args.reason, reviewer_identifier=args.reviewer)
            output = {"audit_id": audit.id, "image_id": audit.image_id, "decision": audit.decision, "reason_code": audit.reason_code}
        print(json.dumps(output, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
