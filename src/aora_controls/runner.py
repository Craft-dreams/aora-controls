"""Execution engine for controls."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any

from aora_controls.model import ControlDescriptor, ControlResult, NormDecision, ValidationError


class ControlExecutionError(Exception):
    """Raised when control preparation or execution encounters an unrecoverable error."""


@dataclass
class ExecutionOutput:
    exit_code: int
    result: ControlResult | None = None
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""


def render_command(
    command_template: str,
    control_dir: Path | None = None,
    descriptor_params: dict[str, dict[str, Any]] | None = None,
    decision_params: dict[str, Any] | None = None,
) -> str:
    """Build the command string substituting {control_dir} and {params.<name>}."""
    # 1. Merge defaults with decision values
    resolved_params: dict[str, Any] = {}
    if descriptor_params:
        for p_name, p_spec in descriptor_params.items():
            if isinstance(p_spec, dict) and "default" in p_spec:
                resolved_params[p_name] = p_spec["default"]

    if decision_params:
        for p_name, p_val in decision_params.items():
            resolved_params[p_name] = p_val

    # 2. Check for missing required parameters referenced in command
    param_pattern = re.compile(r"\{params\.([a-zA-Z0-9_.-]+)\}")
    matches = param_pattern.findall(command_template)
    for param_name in matches:
        if param_name not in resolved_params or resolved_params[param_name] is None:
            raise ControlExecutionError(
                f"Parameter '{param_name}' has no default and was not provided in decision"
            )

    rendered = command_template
    for param_name, param_val in resolved_params.items():
        rendered = rendered.replace(f"{{params.{param_name}}}", str(param_val))

    # 3. Substitute {control_dir}
    if "{control_dir}" in rendered:
        if control_dir is None:
            raise ControlExecutionError("Command references {control_dir} but no control_dir was provided")
        rendered = rendered.replace("{control_dir}", str(control_dir))

    return rendered


def execute_control(
    cwd: Path,
    command_template: str,
    control_dir: Path | None = None,
    descriptor_params: dict[str, dict[str, Any]] | None = None,
    decision_params: dict[str, Any] | None = None,
    timeout: int = 120,
) -> ExecutionOutput:
    """Execute a single control command in cwd and validate the output."""
    try:
        command_str = render_command(
            command_template=command_template,
            control_dir=control_dir,
            descriptor_params=descriptor_params,
            decision_params=decision_params,
        )
    except ControlExecutionError as err:
        return ExecutionOutput(
            exit_code=2,
            error_message=str(err),
        )

    try:
        args = shlex.split(command_str)
    except ValueError as err:
        return ExecutionOutput(
            exit_code=2,
            error_message=f"Failed to parse command into shell arguments: {err}",
        )

    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            shell=False,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        return ExecutionOutput(
            exit_code=2,
            error_message=f"Control execution timed out after {timeout} seconds",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        )
    except FileNotFoundError as exc:
        return ExecutionOutput(
            exit_code=2,
            error_message=f"Executable not found: {exc}",
            stdout="",
            stderr=str(exc),
        )
    except Exception as exc:
        return ExecutionOutput(
            exit_code=2,
            error_message=f"Subprocess execution failed: {exc}",
            stdout="",
            stderr=str(exc),
        )

    # Validate output for exit code 0 or 1
    if proc.returncode in (0, 1):
        try:
            raw_json = json.loads(proc.stdout)
            result = ControlResult.from_dict(raw_json)
        except (json.JSONDecodeError, ValidationError, Exception) as err:
            return ExecutionOutput(
                exit_code=2,
                error_message=f"Control stdout was not valid JSON conforming to ControlResult: {err}",
                stdout=proc.stdout,
                stderr=proc.stderr,
            )

        if proc.returncode == 0 and len(result.violations) > 0:
            return ExecutionOutput(
                exit_code=2,
                result=result,
                error_message="Control returned exit code 0 but reported violations in output JSON",
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        if proc.returncode == 1 and len(result.violations) == 0:
            return ExecutionOutput(
                exit_code=2,
                result=result,
                error_message="Control returned exit code 1 but reported zero violations in output JSON",
                stdout=proc.stdout,
                stderr=proc.stderr,
            )

        return ExecutionOutput(
            exit_code=proc.returncode,
            result=result,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )

    # Exit code 2 or other unexpected return codes
    parsed_result = None
    try:
        parsed_result = ControlResult.from_dict(json.loads(proc.stdout))
    except Exception:
        pass

    err_msg = proc.stderr.strip() or f"Control exited with code {proc.returncode}"
    return ExecutionOutput(
        exit_code=2,
        result=parsed_result,
        error_message=err_msg,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
