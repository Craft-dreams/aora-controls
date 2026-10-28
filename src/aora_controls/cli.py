"""Command-line interface entry point for aora-controls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from aora_controls.check import run_check


def main(argv: list[str] | None = None) -> int:
    args_list = argv if argv is not None else sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="aora-controls",
        description="Reusable controls and runner for Knowledge Hub norms",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # check
    check_parser = subparsers.add_parser("check", help="Run project controls and evaluate baseline/exceptions")
    check_parser.add_argument("--project", type=Path, default=Path.cwd(), help="Target project root directory")
    check_parser.add_argument(
        "--controls-dir",
        type=Path,
        action="append",
        default=[],
        help="Directory containing controls (can specify multiple times)",
    )

    # baseline
    baseline_parser = subparsers.add_parser("baseline", help="Update or initialize project baseline")
    baseline_parser.add_argument("--project", type=Path, default=Path.cwd(), help="Target project root directory")
    baseline_parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize baseline for the first time (fails if baseline already exists)",
    )
    baseline_parser.add_argument(
        "--controls-dir",
        type=Path,
        action="append",
        default=[],
        help="Directory containing controls",
    )

    # coverage
    cov_parser = subparsers.add_parser("coverage", help="Analyze norms coverage against project decisions and Hub")
    cov_parser.add_argument("--project", type=Path, default=Path.cwd(), help="Target project root directory")
    cov_parser.add_argument(
        "--hub-norms",
        type=Path,
        default=None,
        help="Path to JSON file containing Hub norms export",
    )

    # selftest
    selftest_parser = subparsers.add_parser("selftest", help="Run pass/fail test cases for all controls")
    selftest_parser.add_argument(
        "--controls-dir",
        type=Path,
        default=None,
        help="Directory containing controls",
    )

    try:
        parsed = parser.parse_args(args_list)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 2)

    if not parsed.subcommand:
        parser.print_help(sys.stderr)
        return 0

    if parsed.subcommand == "check":
        controls_dirs = [p.resolve() for p in parsed.controls_dir]
        exit_code, report, stderr_summary = run_check(
            project_dir=parsed.project,
            controls_dirs=controls_dirs,
        )
        sys.stderr.write(stderr_summary)
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
        return exit_code

    if parsed.subcommand == "baseline":
        from aora_controls.baseline import run_baseline

        controls_dirs = [p.resolve() for p in parsed.controls_dir]
        return run_baseline(project_dir=parsed.project, init=parsed.init, controls_dirs=controls_dirs)

    if parsed.subcommand == "coverage":
        from aora_controls.coverage import run_coverage

        return run_coverage(project_dir=parsed.project, hub_norms_path=parsed.hub_norms)

    if parsed.subcommand == "selftest":
        from aora_controls.selftest import run_selftest

        return run_selftest(controls_dir=parsed.controls_dir)

    print(f"Unknown command: {parsed.subcommand}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
