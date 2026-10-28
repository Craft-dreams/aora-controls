"""Coverage command: analyzes norms coverage against project decisions and Hub export."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from aora_controls.model import ProjectRegistry


def analyze_coverage(
    project_dir: Path,
    hub_norms_path: Path | None = None,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    norms_file = project_dir / ".aora" / "norms.yaml"
    if not norms_file.is_file():
        raise FileNotFoundError(f"{norms_file} does not exist")

    registry = ProjectRegistry.from_yaml(norms_file.read_text(encoding="utf-8"))
    active_decisions = {d.norm: d for d in registry.norms if not d.superseded_at}

    rows: list[dict[str, Any]] = []

    if hub_norms_path and hub_norms_path.is_file():
        hub_data = json.loads(hub_norms_path.read_text(encoding="utf-8"))
        if not isinstance(hub_data, list):
            raise ValueError("Hub norms JSON must be a list of objects")

        seen_norms = set()
        for item in hub_data:
            norm_id = str(item.get("id", ""))
            seen_norms.add(norm_id)
            hub_hash = str(item.get("content_hash", ""))
            if norm_id in active_decisions:
                dec = active_decisions[norm_id]
                if dec.norm_hash == "pending":
                    status = "pending"
                elif hub_hash and dec.norm_hash != hub_hash:
                    status = "outdated"
                else:
                    status = "up_to_date"
                rows.append({
                    "norm": norm_id,
                    "status": status,
                    "norm_hash": dec.norm_hash,
                    "hub_hash": hub_hash,
                    "control": dec.control or dec.command or "-",
                    "mode": dec.mode,
                })
            else:
                rows.append({
                    "norm": norm_id,
                    "status": "missing",
                    "norm_hash": "-",
                    "hub_hash": hub_hash,
                    "control": "-",
                    "mode": "-",
                })

        # Project decisions not in Hub
        for norm_id, dec in sorted(active_decisions.items()):
            if norm_id not in seen_norms:
                status = "pending" if dec.norm_hash == "pending" else "recorded"
                rows.append({
                    "norm": norm_id,
                    "status": status,
                    "norm_hash": dec.norm_hash,
                    "hub_hash": "-",
                    "control": dec.control or dec.command or "-",
                    "mode": dec.mode,
                })
    else:
        for norm_id, dec in sorted(active_decisions.items()):
            status = "pending" if dec.norm_hash == "pending" else "recorded"
            rows.append({
                "norm": norm_id,
                "status": status,
                "norm_hash": dec.norm_hash,
                "hub_hash": "-",
                "control": dec.control or dec.command or "-",
                "mode": dec.mode,
            })

    return {"norms": rows}


def run_coverage(
    project_dir: Path,
    hub_norms_path: Path | None = None,
) -> int:
    """Analyze coverage and output table to stderr + JSON to stdout."""
    try:
        report = analyze_coverage(project_dir=project_dir, hub_norms_path=hub_norms_path)
    except Exception as err:
        print(f"Error analyzing coverage: {err}", file=sys.stderr)
        return 2

    # Print summary table to stderr
    # Columns: norma  status  norm_hash  controle  modo
    lines = [
        f"{'norma':<20} {'status':<12} {'norm_hash':<14} {'controle':<28} {'modo':<8}"
    ]
    for r in report["norms"]:
        h = r["norm_hash"][:12] if r["norm_hash"] != "-" else "-"
        lines.append(f"{r['norm']:<20} {r['status']:<12} {h:<14} {r['control']:<28} {r['mode']:<8}")

    sys.stderr.write("\n".join(lines) + "\n")
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0
