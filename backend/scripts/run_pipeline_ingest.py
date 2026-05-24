from __future__ import annotations

import argparse
import os
from pathlib import Path

from app.core.config import settings
from app.graph.driver import Neo4jSessionManager
from app.graph.pricing_repository import Neo4jPricingRepository
from app.models.catalog import CanonicalImportCommitRequest, CanonicalImportStageRequest


def _load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage pc-part-dataset records through the canonical import pipeline.")
    parser.add_argument("--category", required=True)
    parser.add_argument("--file", required=True, help="Path under data/imports, for example datasets/pc-part-dataset/cpu.json")
    parser.add_argument("--batch-limit", type=int, default=50)
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--commit-clean-only", action="store_true")
    parser.add_argument("--license-note", required=True)
    args = parser.parse_args()

    _load_dotenv()
    manager = Neo4jSessionManager(settings)
    repository = Neo4jPricingRepository(manager.driver)
    try:
        stage = repository.stage_canonical_import(
            CanonicalImportStageRequest(
                source_name="pc-part-dataset",
                source_type="community_repository",
                dataset_path=args.file,
                category=args.category,
                adapter="pc_part_dataset",
                batch_limit=args.batch_limit,
                license_note=args.license_note,
                dry_run=False,
            )
        )
        print(stage.model_dump_json(indent=2))
        if args.stage_only or not args.commit_clean_only:
            return
        if stage.conflict_candidates:
            print("commit_skipped=conflicts_require_founder_approval")
            return
        commit = repository.commit_canonical_import(
            CanonicalImportCommitRequest(
                source_name="pc-part-dataset",
                source_type="community_repository",
                category=args.category,
                batch_limit=args.batch_limit,
                commit=True,
                approval_required_for_conflicts=True,
            )
        )
        print(commit.model_dump_json(indent=2))
    finally:
        manager.close()


if __name__ == "__main__":
    main()
