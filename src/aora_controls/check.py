"""Check command: evaluates project decisions against controls and baseline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

from aora_controls.model import (
    ControlDescriptor,
    ControlResult,
    ExceptionRule,
    NormDecision,
    ProjectRegistry,
    ValidationError,
    Violation,
    validate_decision_with_descriptor,
)
from aora_controls.runner import ExecutionOutput, execute_control
from aora_controls.yaml_parser import YamlParseError, parse_yaml


def find_control(control_id: str, search_dirs: list[Path]) -> tuple[Path, ControlDescriptor]:
    """Search for controls/<NORM-ID>/<control-id>/control.yaml across search_dirs."""
    for root in search_dirs:
        if not root.is_dir():
            continue
        # Direct search: root / * / control_id / control.yaml or root / control_id / control.yaml
        matches = list(root.glob(f"*/{control_id}/control.yaml")) + list(
            root.glob(f"{control_id}/control.yaml")
        )
        if matches:
            yaml_path = matches[0]
            content = yaml_path.read_text(encoding="utf-8")
            descriptor = ControlDescriptor.from_yaml(content)
            return yaml_path.parent, descriptor
    raise FileNotFoundError(f"Control '{control_id}' not found in {[str(p) for p in search_dirs]}")


def load_exceptions(exceptions_path: Path) -> list[ExceptionRule]:
    if not exceptions_path.is_file():
        return []
    content = exceptions_path.read_text(encoding="utf-8")
    raw = parse_yaml(content)
    rules: list[ExceptionRule] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                rules.append(ExceptionRule.from_dict(item))
    elif isinstance(raw, dict):
        raw_list = raw.get("exceptions", [])
        if isinstance(raw_list, list):
            for item in raw_list:
                if isinstance(item, dict):
                    rules.append(ExceptionRule.from_dict(item))
    return rules


def load_baseline(baseline_path: Path) -> dict[str, int]:
    if not baseline_path.is_file():
        return {}
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): int(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


@dataclass
class NormCheckResult:
    norm: str
    control: str
    mode: str
    norm_hash: str
    baseline: int
    total_violations: int
    exempted_violations: int
    effective_violations: int
    passed: bool
    status: str  # "pass", "fail", "error"
    violations: list[Violation] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "norm": self.norm,
            "control": self.control,
            "mode": self.mode,
            "norm_hash": self.norm_hash,
            "baseline": self.baseline,
            "total_violations": self.total_violations,
            "exempted_violations": self.exempted_violations,
            "effective_violations": self.effective_violations,
            "passed": self.passed,
            "status": self.status,
            "violations": [v.to_dict() for v in self.violations],
            "error_message": self.error_message,
        }


def run_check(
    project_dir: Path,
    controls_dirs: list[Path] | None = None,
    reference_date: str | None = None,
) -> tuple[int, dict[str, Any], str]:
    """Execute check command. Returns (exit_code, report_dict, stderr_summary)."""
    project_dir = project_dir.resolve()
    norms_file = project_dir / ".aora" / "norms.yaml"
    if not norms_file.is_file():
        err = f"Error: {norms_file} does not exist"
        return 2, {"error": err, "passed": False, "results": []}, err + "\n"

    try:
        registry = ProjectRegistry.from_yaml(norms_file.read_text(encoding="utf-8"))
    except (YamlParseError, ValidationError, Exception) as err:
        msg = f"Error loading {norms_file}: {err}"
        return 2, {"error": msg, "passed": False, "results": []}, msg + "\n"

    # Default controls search paths
    search_dirs: list[Path] = []
    if controls_dirs:
        search_dirs.extend(controls_dirs)
    # Package repo controls
    repo_controls = Path(__file__).resolve().parent.parent.parent / "controls"
    if repo_controls.is_dir() and repo_controls not in search_dirs:
        search_dirs.append(repo_controls)
    # Project controls if any
    proj_controls = project_dir / "controls"
    if proj_controls.is_dir() and proj_controls not in search_dirs:
        search_dirs.append(proj_controls)

    # Load baseline
    baseline_path = project_dir / registry.baseline
    baseline_data = load_baseline(baseline_path)

    # Load exceptions
    exceptions_path = project_dir / registry.exceptions
    try:
        exception_rules = load_exceptions(exceptions_path)
    except Exception as err:
        msg = f"Error loading exceptions from {exceptions_path}: {err}"
        return 2, {"error": msg, "passed": False, "results": []}, msg + "\n"

    # Check for expired exceptions
    expired_rules_by_norm: dict[str, list[ExceptionRule]] = {}
    active_rules: list[ExceptionRule] = []
    for rule in exception_rules:
        if rule.is_expired(reference_date=reference_date):
            expired_rules_by_norm.setdefault(rule.norm, []).append(rule)
        else:
            active_rules.append(rule)

    results: list[NormCheckResult] = []
    has_failure = False
    has_error = False

    for decision in registry.norms:
        if decision.superseded_at:
            continue

        control_name = decision.control or "project-command"
        norm_baseline = baseline_data.get(decision.norm, 0)

        # Check expired exceptions for this norm
        if decision.norm in expired_rules_by_norm:
            expired = expired_rules_by_norm[decision.norm]
            err_msg = (
                f"Exception expired on {expired[0].expires} for path '{expired[0].path}': "
                f"{expired[0].reason}"
            )
            results.append(
                NormCheckResult(
                    norm=decision.norm,
                    control=control_name,
                    mode=decision.mode,
                    norm_hash=decision.norm_hash,
                    baseline=norm_baseline,
                    total_violations=0,
                    exempted_violations=0,
                    effective_violations=0,
                    passed=False,
                    status="error",
                    error_message=err_msg,
                )
            )
            has_error = True
            continue

        # Resolve control
        if decision.control:
            try:
                control_dir, descriptor = find_control(decision.control, search_dirs)
            except FileNotFoundError as err:
                results.append(
                    NormCheckResult(
                        norm=decision.norm,
                        control=control_name,
                        mode=decision.mode,
                        norm_hash=decision.norm_hash,
                        baseline=norm_baseline,
                        total_violations=0,
                        exempted_violations=0,
                        effective_violations=0,
                        passed=False,
                        status="error",
                        error_message=str(err),
                    )
                )
                has_error = True
                continue

            # Validate descriptor status
            if descriptor.status != "active":
                err_msg = (
                    f"Control '{descriptor.id}' status is '{descriptor.status}', "
                    "only 'active' controls can be enforced in check"
                )
                results.append(
                    NormCheckResult(
                        norm=decision.norm,
                        control=control_name,
                        mode=decision.mode,
                        norm_hash=decision.norm_hash,
                        baseline=norm_baseline,
                        total_violations=0,
                        exempted_violations=0,
                        effective_violations=0,
                        passed=False,
                        status="error",
                        error_message=err_msg,
                    )
                )
                has_error = True
                continue

            # Validate decision compatibility
            try:
                validate_decision_with_descriptor(decision, descriptor)
            except ValidationError as err:
                results.append(
                    NormCheckResult(
                        norm=decision.norm,
                        control=control_name,
                        mode=decision.mode,
                        norm_hash=decision.norm_hash,
                        baseline=norm_baseline,
                        total_violations=0,
                        exempted_violations=0,
                        effective_violations=0,
                        passed=False,
                        status="error",
                        error_message=str(err),
                    )
                )
                has_error = True
                continue

            output = execute_control(
                cwd=project_dir,
                command_template=descriptor.command,
                control_dir=control_dir,
                descriptor_params=descriptor.params,
                decision_params=decision.params,
            )
        else:
            # Project command
            output = execute_control(
                cwd=project_dir,
                command_template=decision.command or "",
                control_dir=None,
                descriptor_params=None,
                decision_params=decision.params,
            )

        if output.exit_code == 2 or output.error_message:
            err_msg = output.error_message or "Control execution error (exit code 2)"
            results.append(
                NormCheckResult(
                    norm=decision.norm,
                    control=control_name,
                    mode=decision.mode,
                    norm_hash=decision.norm_hash,
                    baseline=norm_baseline,
                    total_violations=0,
                    exempted_violations=0,
                    effective_violations=0,
                    passed=False,
                    status="error",
                    error_message=err_msg,
                )
            )
            has_error = True
            continue

        raw_violations = output.result.violations if output.result else []
        effective_violations: list[Violation] = []
        exempted_violations: list[Violation] = []

        for v in raw_violations:
            if any(rule.matches(decision.norm, v.file) for rule in active_rules):
                exempted_violations.append(v)
            else:
                effective_violations.append(v)

        eff_count = len(effective_violations)
        passed = True
        status = "pass"

        if decision.mode == "block":
            if eff_count > 0:
                passed = False
                status = "fail"
                has_failure = True
        elif decision.mode == "ratchet":
            if eff_count > norm_baseline:
                passed = False
                status = "fail"
                has_failure = True
        elif decision.mode == "report":
            passed = True
            status = "pass"

        results.append(
            NormCheckResult(
                norm=decision.norm,
                control=control_name,
                mode=decision.mode,
                norm_hash=decision.norm_hash,
                baseline=norm_baseline,
                total_violations=len(raw_violations),
                exempted_violations=len(exempted_violations),
                effective_violations=eff_count,
                passed=passed,
                status=status,
                violations=effective_violations,
            )
        )

    # Format stderr summary table
    # format: norma  controle  modo  violações/baseline  resultado
    lines = [
        f"{'norma':<20} {'controle':<28} {'modo':<9} {'violações/baseline':<20} {'resultado':<10}"
    ]
    for r in results:
        counts = f"{r.effective_violations}/{r.baseline}" if r.mode == "ratchet" else f"{r.effective_violations}/-"
        res_str = r.status.upper()
        lines.append(f"{r.norm:<20} {r.control:<28} {r.mode:<9} {counts:<20} {res_str:<10}")
        if r.error_message:
            lines.append(f"  ↳ erro: {r.error_message}")

    stderr_summary = "\n".join(lines) + "\n"

    overall_passed = not has_failure and not has_error
    if has_error:
        exit_code = 2
    elif has_failure:
        exit_code = 1
    else:
        exit_code = 0

    report = {
        "passed": overall_passed,
        "results": [r.to_dict() for r in results],
        "summary": {
            "total_norms": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if r.status == "fail"),
            "errors": sum(1 for r in results if r.status == "error"),
        },
    }

    return exit_code, report, stderr_summary
