"""Unit tests for the control runner."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from aora_controls.runner import ControlExecutionError, execute_control, render_command


class TestRunner(unittest.TestCase):
    def test_render_command_substitution(self) -> None:
        template = "python3 {control_dir}/check.py --domain {params.domain} --infra {params.infra}"
        control_dir = Path("/tmp/ctrl")
        desc_params = {
            "domain": {"default": "app/domain"},
            "infra": {"default": "app/infrastructure"},
        }
        rendered = render_command(
            template,
            control_dir=control_dir,
            descriptor_params=desc_params,
            decision_params={"domain": "custom/domain"},
        )
        self.assertEqual(
            rendered,
            "python3 /tmp/ctrl/check.py --domain custom/domain --infra app/infrastructure",
        )

    def test_render_command_missing_param_error(self) -> None:
        template = "python3 check.py --key {params.api_key}"
        with self.assertRaises(ControlExecutionError) as ctx:
            render_command(template, descriptor_params={}, decision_params={})
        self.assertIn("api_key", str(ctx.exception))

    def test_render_command_missing_control_dir(self) -> None:
        template = "python3 {control_dir}/check.py"
        with self.assertRaises(ControlExecutionError):
            render_command(template, control_dir=None)

    def test_execute_control_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            script = tmppath / "fake_check.py"
            payload = {
                "norm": "NORM-001",
                "control": "CTRL-001",
                "norm_hash": "pending",
                "violations": [],
            }
            script.write_text(
                f"import sys\nprint({json.dumps(json.dumps(payload))})\nsys.exit(0)\n",
                encoding="utf-8",
            )
            out = execute_control(
                cwd=tmppath,
                command_template=f"{sys.executable} {script}",
            )
            self.assertEqual(out.exit_code, 0)
            self.assertIsNotNone(out.result)
            self.assertEqual(len(out.result.violations), 0)

    def test_execute_control_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            script = tmppath / "fake_check.py"
            payload = {
                "norm": "NORM-001",
                "control": "CTRL-001",
                "norm_hash": "pending",
                "violations": [{"file": "app/main.py", "line": 10, "message": "bad import"}],
            }
            script.write_text(
                f"import sys\nprint({json.dumps(json.dumps(payload))})\nsys.exit(1)\n",
                encoding="utf-8",
            )
            out = execute_control(
                cwd=tmppath,
                command_template=f"{sys.executable} {script}",
            )
            self.assertEqual(out.exit_code, 1)
            self.assertIsNotNone(out.result)
            self.assertEqual(len(out.result.violations), 1)

    def test_execute_control_error_code_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            script = tmppath / "fake_check.py"
            script.write_text(
                "import sys\nsys.stderr.write('Missing argument\\n')\nsys.exit(2)\n",
                encoding="utf-8",
            )
            out = execute_control(
                cwd=tmppath,
                command_template=f"{sys.executable} {script}",
            )
            self.assertEqual(out.exit_code, 2)
            self.assertIn("Missing argument", out.error_message or "")

    def test_execute_control_inconsistent_code_and_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            script = tmppath / "fake_check.py"
            payload = {
                "norm": "NORM-001",
                "control": "CTRL-001",
                "norm_hash": "pending",
                "violations": [{"file": "app/a.py", "line": 1, "message": "err"}],
            }
            # Exit code 0 but has violations
            script.write_text(
                f"import sys\nprint({json.dumps(json.dumps(payload))})\nsys.exit(0)\n",
                encoding="utf-8",
            )
            out = execute_control(
                cwd=tmppath,
                command_template=f"{sys.executable} {script}",
            )
            self.assertEqual(out.exit_code, 2)
            self.assertIn("reported violations in output JSON", out.error_message or "")

    def test_execute_control_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            script = tmppath / "fake_check.py"
            script.write_text("import sys\nprint('not json')\nsys.exit(0)\n", encoding="utf-8")
            out = execute_control(
                cwd=tmppath,
                command_template=f"{sys.executable} {script}",
            )
            self.assertEqual(out.exit_code, 2)
            self.assertIn("not valid JSON", out.error_message or "")


if __name__ == "__main__":
    unittest.main()
