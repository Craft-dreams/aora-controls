"""Unit tests for selftest command."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from aora_controls.selftest import run_selftest


class TestSelfTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.controls_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_control(
        self,
        norm: str,
        control_id: str,
        status: str,
        pass_code: int = 0,
        fail_code: int = 1,
    ) -> Path:
        ctrl_path = self.controls_dir / norm / control_id
        ctrl_path.mkdir(parents=True, exist_ok=True)
        pass_dir = ctrl_path / "tests" / "pass"
        fail_dir = ctrl_path / "tests" / "fail"
        pass_dir.mkdir(parents=True, exist_ok=True)
        fail_dir.mkdir(parents=True, exist_ok=True)

        check_py = ctrl_path / "check.py"
        script = f"""
import json, sys
from pathlib import Path

# If cwd ends in pass, exit with {pass_code}; if fail, exit with {fail_code}
is_pass = Path.cwd().name == "pass"
code = {pass_code} if is_pass else {fail_code}
violations = [] if code == 0 else [{{"file": "a.py", "line": 1, "message": "v"}}]
payload = {{
    "norm": "{norm}",
    "control": "{control_id}",
    "norm_hash": "pending",
    "violations": violations,
}}
print(json.dumps(payload))
sys.exit(code)
"""
        check_py.write_text(script, encoding="utf-8")

        yaml_content = f"""
        id: {control_id}
        norm: {norm}
        norm_hash: pending
        status: {status}
        kind: deterministic
        languages: [python]
        tool: custom
        command: "{sys.executable} {{control_dir}}/check.py"
        default_mode: ratchet
        owner: test-team
        tests: {{pass: tests/pass, fail: tests/fail}}
        """
        (ctrl_path / "control.yaml").write_text(yaml_content, encoding="utf-8")
        return ctrl_path

    def test_selftest_active_pass(self) -> None:
        self._create_control("NORM-001", "CTRL-001", status="active", pass_code=0, fail_code=1)
        exit_code = run_selftest(self.controls_dir)
        self.assertEqual(exit_code, 0)

    def test_selftest_active_fail(self) -> None:
        # Active control fails tests/pass (returns 1 instead of 0)
        self._create_control("NORM-001", "CTRL-FAIL", status="active", pass_code=1, fail_code=1)
        exit_code = run_selftest(self.controls_dir)
        self.assertEqual(exit_code, 1)

    def test_selftest_experimental_reported_only(self) -> None:
        # Experimental control fails tests/pass, but should only report and return 0
        self._create_control("NORM-001", "CTRL-EXP", status="experimental", pass_code=1, fail_code=1)
        exit_code = run_selftest(self.controls_dir)
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
