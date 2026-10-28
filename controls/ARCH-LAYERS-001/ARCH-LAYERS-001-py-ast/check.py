#!/usr/bin/env python3
"""Detect imports from an infrastructure package inside a domain package."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

NORM_ID = "ARCH-LAYERS-001"
CONTROL_ID = "ARCH-LAYERS-001-py-ast"
NORM_HASH = "pending"


def package_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def resolved_import(current: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package = current.split(".")[:-1]
    if node.level > len(package) + 1:
        return node.module or ""
    prefix = package[: len(package) - node.level + 1]
    return ".".join(prefix + ([node.module] if node.module else []))


def is_infrastructure(name: str, prefixes: set[str]) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes if prefix)


def check(domain: Path, infrastructure: Path) -> list[dict[str, object]]:
    root = Path.cwd()
    domain_path = (root / domain).resolve()
    infrastructure_path = (root / infrastructure).resolve()

    if not domain_path.is_dir():
        return []

    domain_init = domain_path / "__init__.py"
    infra_init = infrastructure_path / "__init__.py"

    domain_prefix = package_name(domain_init, root) if domain_init.exists() else domain_path.name
    infra_prefix = package_name(infra_init, root) if infra_init.exists() else infrastructure_path.name
    prefixes = {infra_prefix, infrastructure_path.name}

    violations: list[dict[str, object]] = []

    for source in sorted(domain_path.rglob("*.py")):
        current = package_name(source, root)
        try:
            rel_file = str(source.relative_to(root))
        except ValueError:
            rel_file = str(source)

        try:
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        except (OSError, UnicodeError, SyntaxError) as exc:
            violations.append({
                "file": rel_file,
                "line": 1,
                "message": f"unable to parse: {exc}",
            })
            continue

        imported: list[tuple[str, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend((alias.name, node.lineno) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append((resolved_import(current, node), node.lineno))

        for name, line in imported:
            if is_infrastructure(name, prefixes):
                violations.append({
                    "file": rel_file,
                    "line": line,
                    "message": f"domain imports infrastructure module {name}",
                })

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that domain layer does not import infrastructure layer")
    parser.add_argument("--domain", type=Path, required=True, help="Path to domain package directory")
    parser.add_argument("--infra", type=Path, required=True, help="Path to infrastructure package directory")
    args = parser.parse_args()

    try:
        violations = check(args.domain, args.infra)
    except Exception as exc:
        print(f"Error executing check: {exc}", file=sys.stderr)
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
