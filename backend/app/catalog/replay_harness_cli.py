"""CLI for deterministic local replay and failure evidence."""
from __future__ import annotations

import argparse
import json
import sys

from app.catalog.replay_harness import HarnessError, compare, clean_run, list_scenarios, replay, retry, run, show_manifest, validate_scenario


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Run synthetic catalog replay scenarios locally.")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list-scenarios")
    validate = commands.add_parser("validate-scenario"); validate.add_argument("scenario")
    for name in ("run", "replay"):
        action = commands.add_parser(name); action.add_argument("--scenario", required=True); action.add_argument("--database-url", required=True); action.add_argument("--seed", type=int, required=True); action.add_argument("--timestamp-anchor", required=True); action.add_argument("--failure-point"); action.add_argument("--failure-mode"); action.add_argument("--replay-count", type=int, default=2); action.add_argument("--commit", action="store_true")
    retry_parser = commands.add_parser("retry"); retry_parser.add_argument("run_id"); retry_parser.add_argument("--database-url", required=True); retry_parser.add_argument("--retry-count", type=int, default=1)
    compare_parser = commands.add_parser("compare"); compare_parser.add_argument("first"); compare_parser.add_argument("second")
    manifest = commands.add_parser("show-manifest"); manifest.add_argument("run_id")
    suite = commands.add_parser("run-suite"); suite.add_argument("--database-url", required=True); suite.add_argument("--seed", type=int, required=True); suite.add_argument("--timestamp-anchor", required=True)
    clean = commands.add_parser("clean-run"); clean.add_argument("run_id")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "list-scenarios": result = list_scenarios()
        elif args.command == "validate-scenario": result = validate_scenario(args.scenario)
        elif args.command == "run": result = run(scenario_id=args.scenario, database_url=args.database_url, seed=args.seed, timestamp_anchor=args.timestamp_anchor, failure_point=args.failure_point, failure_mode=args.failure_mode, commit=args.commit).manifest
        elif args.command == "replay": result = [item.manifest for item in replay(scenario_id=args.scenario, database_url=args.database_url, seed=args.seed, timestamp_anchor=args.timestamp_anchor, replay_count=args.replay_count)]
        elif args.command == "retry": result = retry(args.run_id, database_url=args.database_url, retry_count=args.retry_count).manifest
        elif args.command == "compare": result = compare(args.first, args.second)
        elif args.command == "show-manifest": result = show_manifest(args.run_id)
        elif args.command == "run-suite": result = [run(scenario_id=item["scenario_id"], database_url=args.database_url, seed=args.seed, timestamp_anchor=args.timestamp_anchor).manifest for item in list_scenarios()]
        elif args.command == "clean-run": clean_run(args.run_id); result = {"cleaned": args.run_id}
        else: raise HarnessError("SCENARIO_NOT_FOUND")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)); return 0
    except HarnessError as error:
        print(json.dumps({"error": error.code, "message": str(error)}, sort_keys=True), file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
