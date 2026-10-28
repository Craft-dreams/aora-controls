#!/usr/bin/env python3
"""Detect direct environment variable and dotenv access inside forbidden packages."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

NORM_ID = "CONFIG-ENV-001"
CONTROL_ID = "CONFIG-ENV-001-py-ast"
NORM_HASH = "pending"


def check_file(source_path: Path, root: Path) -> list[dict[str, object]]:
    try:
        rel_file = str(source_path.relative_to(root))
    except ValueError:
        rel_file = str(source_path)

    try:
        content = source_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(source_path))
    except Exception as exc:
        return [{
            "file": rel_file,
            "line": 1,
            "message": f"unable to parse python file: {exc}",
        }]

    violations: list[dict[str, object]] = []

    for node in ast.walk(tree):
        # 1. Imports from dotenv or os.environ / os.getenv
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "dotenv" or alias.name.startswith("dotenv."):
                    violations.append({
                        "file": rel_file,
                        "line": node.lineno,
                        "message": f"direct import of {alias.name} is prohibited in this layer",
                    })
        elif isinstance(node, ast.ImportFrom):
            if node.module == "dotenv" or (node.module and node.module.startswith("dotenv.")):
                violations.append({
                    "file": rel_file,
                    "line": node.lineno,
                    "message": f"direct import from dotenv ({node.module}) is prohibited in this layer",
                })
            elif node.module == "os":
                for alias in node.names:
                    if alias.name in ("environ", "getenv"):
                        violations.append({
                            "file": rel_file,
                            "line": node.lineno,
                            "message": f"direct import of os.{alias.name} is prohibited in this layer",
                        })

        # 2. os.environ or os.getenv attribute access
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                if node.attr in ("environ", "getenv"):
                    violations.append({
                        "file": rel_file,
                        "line": node.lineno,
                        "message": f"direct access to os.{node.attr} is prohibited in this layer",
                    })

        # 3. Direct calls to getenv, environ, load_dotenv
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in ("getenv", "load_dotenv"):
                    violations.append({
                        "file": rel_file,
                        "line": node.lineno,
                        "message": f"direct call to {node.func.id}() is prohibited in this layer",
                    })

        # 4. Direct subscript on environ[...] (e.g. if imported)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "environ":
                violations.append({
                    "file": rel_file,
                    "line": node.lineno,
                    "message": "direct subscript access to environ[...] is prohibited in this layer",
                })

    # Deduplicate violations on identical line and message
    unique_violations: list[dict[str, object]] = []
    seen = set()
    for v in violations:
        key = (v["line"], v["message"])
        if key not in seen:
            seen.add(key)
            unique_violations.append(v)

    return sorted(unique_violations, key=lambda x: int(x["line"]))


def check(packages: list[str]) -> list[dict[str, object]]:
    root = Path.cwd()
    violations: list[dict[str, object]] = []

    for pkg_rel in packages:
        pkg_dir = (root / pkg_rel).resolve()
        if not pkg_dir.is_dir():
            continue
        for source in sorted(pkg_dir.rglob("*.py")):
            violations.extend(check_file(source, root))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that domain/application layers do not directly access env")
    parser.add_argument(
        "--packages",
        default="app/domain,app/application",
        help="Comma-separated package directory paths to check",
    )
    args = parser.parse_args()

    pkg_list = [p.strip() for p in args.packages.split(",") if p.strip()]

    try:
        violations = check(pkg_list)
    except Exception as exc:
        print(f"Error checking env usage: {exc}", file=sys.stderr)
        return 2

    output = {
        "norm": NORM_ID,
        "control": CONTROL_ID,
        "norm_hash": NORM_HASH,
        "violations": violations,
    }
    sys.stdout.write(json.dumps(output, indent=2) + "\n")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
