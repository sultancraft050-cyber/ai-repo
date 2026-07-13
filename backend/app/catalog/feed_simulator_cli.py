"""Command line interface for the local synthetic feed simulator."""
from __future__ import annotations

import argparse
import json
import sys

from app.catalog.feed_simulator import (
    SimulatorError, clean_run, compare_runs, generate, list_adapters, list_scenarios,
    load_run, preview, read_manifest, stage_run, validate_adapter,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate bounded synthetic catalog feeds locally.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-adapters")
    commands.add_parser("list-scenarios")
    validate = commands.add_parser("validate-adapter"); validate.add_argument("--adapter", required=True)
    generate_parser = commands.add_parser("generate"); _generate_args(generate_parser)
    preview_parser = commands.add_parser("generate-and-preview"); _generate_args(preview_parser)
    preview_existing = commands.add_parser("preview"); preview_existing.add_argument("run_id")
    stage_parser = commands.add_parser("generate-and-stage"); _generate_args(stage_parser)
    stage_parser.add_argument("--database-url", required=True)
    manifest = commands.add_parser("show-manifest"); manifest.add_argument("run_id")
    compare = commands.add_parser("compare-runs"); compare.add_argument("first"); compare.add_argument("second")
    clean = commands.add_parser("clean-run"); clean.add_argument("run_id")
    return parser


def _generate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--adapter", default="synthetic-sa-retailer-v1")
    parser.add_argument("--scenario", default="initial-catalog-load")
    parser.add_argument("--entity-type")
    parser.add_argument("--format", dest="output_format", choices=("csv", "json-array", "json-records"), default="csv")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--record-count", type=int)
    parser.add_argument("--timestamp-anchor", default="2026-07-13T09:00:00+03:00")
    parser.add_argument("--output-dir")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "list-adapters": result = list_adapters()
        elif args.command == "list-scenarios": result = list_scenarios()
        elif args.command == "validate-adapter": result = validate_adapter(args.adapter)
        elif args.command in {"generate", "generate-and-preview", "generate-and-stage"}:
            if args.command == "generate-and-stage":
                from app.catalog.feed_simulator import require_enabled
                require_enabled(staging=True)
            run = generate(adapter_id=args.adapter, scenario_id=args.scenario, entity_type=args.entity_type, output_format=args.output_format, seed=args.seed, timestamp_anchor=args.timestamp_anchor, record_count=args.record_count, output_dir=args.output_dir)
            result = {"run_id": run.run_id, "manifest": run.manifest}
            if args.command == "generate-and-preview": result["preview"] = preview(run)
            if args.command == "generate-and-stage": result["staging"] = stage_run(run, args.database_url)
        elif args.command == "show-manifest": result = read_manifest(args.run_id)
        elif args.command == "preview": result = preview(load_run(args.run_id))
        elif args.command == "compare-runs": result = compare_runs(args.first, args.second)
        elif args.command == "clean-run": clean_run(args.run_id); result = {"cleaned": args.run_id}
        else: raise SimulatorError("SCENARIO_INVALID")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except SimulatorError as error:
        print(json.dumps({"error": error.code, "message": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
