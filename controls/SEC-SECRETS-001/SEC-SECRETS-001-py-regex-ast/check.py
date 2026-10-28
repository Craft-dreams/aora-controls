#!/usr/bin/env python3
"""Detect hardcoded secret literals and logging of secret identifiers."""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
from pathlib import Path
import re
import sys

NORM_ID = "SEC-SECRETS-001"
CONTROL_ID = "SEC-SECRETS-001-py-regex-ast"
NORM_HASH = "pending"

REGEX_PATTERNS = [
    ("PEM private key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("API secret key", re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b")),
    ("GitHub personal token", re.compile(r"\b(ghp_[A-Za-z0-9]{36})\b")),
    (
        "Hardcoded secret assignment",
        re.compile(r"(?i)\b(password|senha|secret|token|api_key)\s*=\s*[\"'][^\"']{8,}[\"']"),
    ),
]

SECRET_IDENTIFIER_PATTERN = re.compile(r"(?i)(secret|token|password|senha|api_key)")
LOGGING_ATTRS = {"info", "warning", "warn", "error", "debug", "critical", "exception", "log"}


def is_excluded(path: Path, root: Path, exclude_patterns: list[str]) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path

    parts = rel.parts
    for pat in exclude_patterns:
        if not pat:
            continue
        # Check against path parts or glob
        if any(fnmatch.fnmatch(part, pat) for part in parts):
            return True
        if fnmatch.fnmatch(str(rel), pat):
            return True
    return False


def is_logging_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id == "print" or node.func.id.lower().startswith("log")
    if isinstance(node.func, ast.Attribute):
        attr = node.func.attr.lower()
        if attr == "print" or attr.startswith("log") or attr in LOGGING_ATTRS:
            # Check receiver
            if isinstance(node.func.value, ast.Name):
                val_id = node.func.value.id.lower()
                return "log" in val_id or val_id in ("logger", "app", "logging")
            return True
    return False


def find_secret_arg_names(node: ast.Call) -> list[tuple[str, int]]:
    flagged: list[tuple[str, int]] = []
    # Positional args
    for arg in node.args:
        for child in ast.walk(arg):
            if isinstance(child, ast.Name) and SECRET_IDENTIFIER_PATTERN.search(child.id):
                flagged.append((child.id, getattr(child, "lineno", node.lineno)))
    # Keyword args
    for kw in node.keywords:
        for child in ast.walk(kw.value):
            if isinstance(child, ast.Name) and SECRET_IDENTIFIER_PATTERN.search(child.id):
                flagged.append((child.id, getattr(child, "lineno", node.lineno)))
    return flagged


def check(paths: list[str], excludes: list[str]) -> list[dict[str, object]]:
    root = Path.cwd()
    violations: list[dict[str, object]] = []

    files_to_check: list[Path] = []
    for p_str in paths:
        target = (root / p_str).resolve()
        if target.is_file():
            files_to_check.append(target)
        elif target.is_dir():
            for f in target.rglob("*"):
                if f.is_file():
                    files_to_check.append(f)

    # Deduplicate and sort
    sorted_files = sorted(set(files_to_check))

    for filepath in sorted_files:
        if is_excluded(filepath, root, excludes):
            continue

        try:
            rel_file = str(filepath.relative_to(root))
        except ValueError:
            rel_file = str(filepath)

        # 1. Regex line-by-line literal check
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        lines = content.splitlines()
        for lineno, line in enumerate(lines, start=1):
            for name, pattern in REGEX_PATTERNS:
                if pattern.search(line):
                    violations.append({
                        "file": rel_file,
                        "line": lineno,
                        "message": f"found secret pattern: {name}",
                    })
                    break

        # 2. Python AST logging check (only for .py files)
        if filepath.suffix == ".py":
            try:
                tree = ast.parse(content, filename=str(filepath))
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and is_logging_call(node):
                    flagged = find_secret_arg_names(node)
                    for arg_name, lineno in flagged:
                        violations.append({
                            "file": rel_file,
                            "line": lineno,
                            "message": f"identifier '{arg_name}' matching secret patterns passed to log/print",
                        })

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan for secrets and leaked variables in logs")
    parser.add_argument("--paths", default=".", help="Comma-separated paths to check")
    parser.add_argument("--exclude", default="tests,fixtures,.git", help="Comma-separated exclude patterns")
    args = parser.parse_args()

    paths_list = [p.strip() for p in args.paths.split(",") if p.strip()]
    exclude_list = [e.strip() for e in args.exclude.split(",") if e.strip()]

    try:
        violations = check(paths_list, exclude_list)
    except Exception as exc:
        print(f"Error executing secrets check: {exc}", file=sys.stderr)
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
