"""Command-line interface entry point for aora-controls."""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: aora-controls <command> [options]")
        print("commands: check, baseline, coverage, selftest")
        return 0
    print(f"Unknown command: {args[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
