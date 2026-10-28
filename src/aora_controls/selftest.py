"""Selftest command: validates that controls satisfy their tests/pass and tests/fail suites."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from aora_controls.model import ControlDescriptor
from aora_controls.runner import execute_control


@dataclass
class ControlSelfTestResult:
    control_id: str
    status: str
    pass_ok: bool
    fail_ok: bool
    passed: bool
    error_message: str | None = None


def run_selftest(controls_dir: Path | None = None) -> int:
    """Run tests/pass and tests/fail for each control in controls_dir."""
    if controls_dir is None:
        controls_dir = Path(__file__).resolve().parent.parent.parent / "controls"

    controls_dir = controls_dir.resolve()
    if not controls_dir.is_dir():
        print(f"Controls directory not found: {controls_dir}", file=sys.stderr)
        return 0

    control_yamls = sorted(controls_dir.glob("*/*/control.yaml"))
    if not control_yamls:
        print(f"No controls found under {controls_dir}", file=sys.stderr)
        return 0

    results: list[ControlSelfTestResult] = []
    has_active_failure = False

    for yaml_path in control_yamls:
        ctrl_dir = yaml_path.parent
        try:
            desc = ControlDescriptor.from_yaml(yaml_path.read_text(encoding="utf-8"))
        except Exception as err:
            results.append(
                ControlSelfTestResult(
                    control_id=ctrl_dir.name,
                    status="error",
                    pass_ok=False,
                    fail_ok=False,
                    passed=False,
                    error_message=f"Failed to load descriptor: {err}",
                )
            )
            has_active_failure = True
            continue

        pass_path = ctrl_dir / desc.tests.get("pass", "tests/pass")
        fail_path = ctrl_dir / desc.tests.get("fail", "tests/fail")

        pass_ok = False
        fail_ok = False
        err_msg = None

        if not pass_path.is_dir():
            err_msg = f"Directory not found: {pass_path}"
        elif not fail_path.is_dir():
            err_msg = f"Directory not found: {fail_path}"
        else:
            # Run pass test (expects exit_code 0)
            pass_output = execute_control(
                cwd=pass_path,
                command_template=desc.command,
                control_dir=ctrl_dir,
                descriptor_params=desc.params,
                decision_params={},
            )
            pass_ok = pass_output.exit_code == 0

            # Run fail test (expects exit_code 1)
            fail_output = execute_control(
                cwd=fail_path,
                command_template=desc.command,
                control_dir=ctrl_dir,
                descriptor_params=desc.params,
                decision_params={},
            )
            fail_ok = fail_output.exit_code == 1

            if not pass_ok or not fail_ok:
                reasons = []
                if not pass_ok:
                    reasons.append(
                        f"tests/pass returned exit code {pass_output.exit_code} "
                        f"(error: {pass_output.error_message or 'expected 0'})"
                    )
                if not fail_ok:
                    reasons.append(
                        f"tests/fail returned exit code {fail_output.exit_code} "
                        f"(error: {fail_output.error_message or 'expected 1'})"
                    )
                err_msg = "; ".join(reasons)

        ctrl_passed = pass_ok and fail_ok
        if desc.status == "active" and not ctrl_passed:
            has_active_failure = True

        results.append(
            ControlSelfTestResult(
                control_id=desc.id,
                status=desc.status,
                pass_ok=pass_ok,
                fail_ok=fail_ok,
                passed=ctrl_passed,
                error_message=err_msg,
            )
        )

    # Print summary table
    print(f"{'controle':<32} {'status':<14} {'pass':<8} {'fail':<8} {'resultado':<10}", file=sys.stderr)
    for r in results:
        pass_str = "OK" if r.pass_ok else "FAIL"
        fail_str = "OK" if r.fail_ok else "FAIL"
        res_str = "PASS" if r.passed else ("REPORT" if r.status == "experimental" else "FAIL")
        print(
            f"{r.control_id:<32} {r.status:<14} {pass_str:<8} {fail_str:<8} {res_str:<10}",
            file=sys.stderr,
        )
        if r.error_message:
            print(f"  ↳ {r.error_message}", file=sys.stderr)

    return 1 if has_active_failure else 0
