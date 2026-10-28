"""Baseline command: initialize and ratchet down project baseline."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from aora_controls.check import run_check
from aora_controls.model import ProjectRegistry


def run_baseline(
    project_dir: Path,
    init: bool = False,
    controls_dirs: list[Path] | None = None,
) -> int:
    """Run baseline calculation and write to project's baseline.json atomically."""
    project_dir = project_dir.resolve()
    norms_file = project_dir / ".aora" / "norms.yaml"
    if not norms_file.is_file():
        print(f"Error: {norms_file} does not exist", file=sys.stderr)
        return 2

    try:
        registry = ProjectRegistry.from_yaml(norms_file.read_text(encoding="utf-8"))
    except Exception as err:
        print(f"Error reading {norms_file}: {err}", file=sys.stderr)
        return 2

    baseline_path = project_dir / registry.baseline

    if init and baseline_path.is_file():
        print(
            f"Error: Baseline already exists at {baseline_path}. Cannot use --init.",
            file=sys.stderr,
        )
        return 2

    if not init and not baseline_path.is_file():
        print(
            f"Error: Baseline file does not exist at {baseline_path}. Run with --init to initialize.",
            file=sys.stderr,
        )
        return 2

    # Load existing baseline if present
    existing_baseline: dict[str, int] = {}
    if baseline_path.is_file():
        try:
            existing_baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception as err:
            print(f"Error reading existing baseline: {err}", file=sys.stderr)
            return 2

    # Run check to get current effective violations
    exit_code, check_report, stderr_summary = run_check(
        project_dir=project_dir,
        controls_dirs=controls_dirs,
    )
    if exit_code == 2:
        print("Error: Could not evaluate controls to calculate baseline:", file=sys.stderr)
        sys.stderr.write(stderr_summary)
        return 2

    new_baseline: dict[str, int] = dict(existing_baseline)
    increases: list[str] = []

    for item in check_report.get("results", []):
        norm = item["norm"]
        current_count = item["effective_violations"]
        if not init and norm in existing_baseline:
            prev_count = existing_baseline[norm]
            if current_count > prev_count:
                increases.append(
                    f"Norm '{norm}': current violations ({current_count}) > existing baseline ({prev_count})"
                )
            else:
                new_baseline[norm] = current_count
        else:
            new_baseline[norm] = current_count

    if increases:
        print("Error: Refusing to increase baseline (baseline may only decrease):", file=sys.stderr)
        for inc in increases:
            print(f"  - {inc}", file=sys.stderr)
        return 1

    # Atomic write: write to temp file in the same directory, then rename
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_path_str = tempfile.mkstemp(
        dir=str(baseline_path.parent),
        prefix="baseline_",
        suffix=".tmp",
    )
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(new_baseline, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(temp_path, baseline_path)
    except Exception as err:
        if temp_path.exists():
            temp_path.unlink()
        print(f"Error writing baseline file {baseline_path}: {err}", file=sys.stderr)
        return 2

    action = "Initialized" if init else "Updated"
    print(f"{action} baseline at {baseline_path}:", file=sys.stderr)
    for norm, count in sorted(new_baseline.items()):
        print(f"  {norm}: {count}", file=sys.stderr)

    return 0
