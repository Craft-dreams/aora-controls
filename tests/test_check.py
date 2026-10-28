"""Unit tests for the check command."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from aora_controls.check import run_check


class TestCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.tmp.name)
        self.aora_dir = self.project_dir / ".aora"
        self.aora_dir.mkdir(parents=True)
        self.controls_dir = self.project_dir / "test_controls"
        self.controls_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_control(
        self,
        norm: str,
        control_id: str,
        status: str = "active",
        kind: str = "deterministic",
        violations: list[dict] | None = None,
        exit_code: int = 0,
    ) -> Path:
        ctrl_path = self.controls_dir / norm / control_id
        ctrl_path.mkdir(parents=True, exist_ok=True)
        payload = {
            "norm": norm,
            "control": control_id,
            "norm_hash": "pending",
            "violations": violations or [],
        }
        check_py = ctrl_path / "check.py"
        if exit_code == 2:
            check_py.write_text(
                "import sys\nsys.stderr.write('fatal tool crash\\n')\nsys.exit(2)\n",
                encoding="utf-8",
            )
        else:
            check_py.write_text(
                f"import sys\nprint({json.dumps(json.dumps(payload))})\nsys.exit({exit_code})\n",
                encoding="utf-8",
            )
        yaml_content = f"""
        id: {control_id}
        norm: {norm}
        norm_hash: pending
        status: {status}
        kind: {kind}
        languages: [python]
        tool: custom
        command: "{sys.executable} {{control_dir}}/check.py"
        default_mode: ratchet
        owner: test-team
        tests: {{pass: tests/pass, fail: tests/fail}}
        """
        (ctrl_path / "control.yaml").write_text(yaml_content, encoding="utf-8")
        return ctrl_path

    def _write_registry(self, norms_list: list[dict], baseline: str = ".aora/baseline.json", exceptions: str = ".aora/exceptions.yaml") -> None:
        lines = [
            "controls_repo: {repository: repo, ref: main}",
            "norms:",
        ]
        for n in norms_list:
            lines.append(f"  - norm: {n['norm']}")
            lines.append(f"    norm_hash: {n.get('norm_hash', 'pending')}")
            if "control" in n:
                lines.append(f"    control: {n['control']}")
            if "command" in n:
                lines.append(f"    command: \"{n['command']}\"")
            lines.append(f"    mode: {n.get('mode', 'ratchet')}")
        lines.append(f"baseline: {baseline}")
        lines.append(f"exceptions: {exceptions}")
        (self.aora_dir / "norms.yaml").write_text("\n".join(lines), encoding="utf-8")

    def test_block_pass_and_fail(self) -> None:
        # Pass
        self._create_control("NORM-001", "CTRL-001", violations=[], exit_code=0)
        self._write_registry([{"norm": "NORM-001", "control": "CTRL-001", "mode": "block"}])
        code, report, _ = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["results"][0]["status"], "pass")

        # Fail
        self._create_control(
            "NORM-001",
            "CTRL-001",
            violations=[{"file": "app/a.py", "line": 1, "message": "bad"}],
            exit_code=1,
        )
        code, report, _ = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["results"][0]["status"], "fail")

    def test_ratchet_equal_below_above(self) -> None:
        # Baseline = 2
        (self.aora_dir / "baseline.json").write_text(json.dumps({"NORM-001": 2}), encoding="utf-8")

        # Equal (2 violations == baseline 2) -> pass
        violations_2 = [
            {"file": "app/a.py", "line": 1, "message": "v1"},
            {"file": "app/b.py", "line": 2, "message": "v2"},
        ]
        self._create_control("NORM-001", "CTRL-001", violations=violations_2, exit_code=1)
        self._write_registry([{"norm": "NORM-001", "control": "CTRL-001", "mode": "ratchet"}])
        code, report, _ = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 0)
        self.assertEqual(report["results"][0]["status"], "pass")

        # Below (1 violation < baseline 2) -> pass
        violations_1 = [{"file": "app/a.py", "line": 1, "message": "v1"}]
        self._create_control("NORM-001", "CTRL-001", violations=violations_1, exit_code=1)
        code, report, _ = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 0)
        self.assertEqual(report["results"][0]["status"], "pass")

        # Above (3 violations > baseline 2) -> fail
        violations_3 = violations_2 + [{"file": "app/c.py", "line": 3, "message": "v3"}]
        self._create_control("NORM-001", "CTRL-001", violations=violations_3, exit_code=1)
        code, report, _ = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 1)
        self.assertEqual(report["results"][0]["status"], "fail")

    def test_exception_valid_and_expired(self) -> None:
        # Control with 1 violation in legacy/old.py
        violations = [{"file": "legacy/old.py", "line": 10, "message": "legacy issue"}]
        self._create_control("NORM-001", "CTRL-001", violations=violations, exit_code=1)
        self._write_registry([{"norm": "NORM-001", "control": "CTRL-001", "mode": "block"}])

        # Active exception
        exc_content = """
        - norm: NORM-001
          path: "legacy/*"
          reason: "migrating"
          owner: alice
          expires: "2026-12-31"
        """
        (self.aora_dir / "exceptions.yaml").write_text(exc_content, encoding="utf-8")
        code, report, _ = run_check(self.project_dir, [self.controls_dir], reference_date="2026-10-28")
        self.assertEqual(code, 0)
        self.assertEqual(report["results"][0]["effective_violations"], 0)
        self.assertEqual(report["results"][0]["exempted_violations"], 1)

        # Expired exception -> error
        exc_expired = """
        - norm: NORM-001
          path: "legacy/*"
          reason: "migrating"
          owner: alice
          expires: "2026-10-01"
        """
        (self.aora_dir / "exceptions.yaml").write_text(exc_expired, encoding="utf-8")
        code, report, _ = run_check(self.project_dir, [self.controls_dir], reference_date="2026-10-28")
        self.assertEqual(code, 2)
        self.assertEqual(report["results"][0]["status"], "error")
        self.assertIn("Exception expired", report["results"][0]["error_message"])

    def test_control_exit_code_2(self) -> None:
        self._create_control("NORM-001", "CTRL-001", exit_code=2)
        self._write_registry([{"norm": "NORM-001", "control": "CTRL-001", "mode": "ratchet"}])
        code, report, _ = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 2)
        self.assertEqual(report["results"][0]["status"], "error")

    def test_control_non_existent(self) -> None:
        self._write_registry([{"norm": "NORM-001", "control": "NON-EXISTENT", "mode": "ratchet"}])
        code, report, _ = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 2)
        self.assertEqual(report["results"][0]["status"], "error")
        self.assertIn("not found", report["results"][0]["error_message"])

    def test_control_status_experimental_rejected(self) -> None:
        self._create_control("NORM-001", "CTRL-EXP", status="experimental", exit_code=0)
        self._write_registry([{"norm": "NORM-001", "control": "CTRL-EXP", "mode": "ratchet"}])
        code, report, _ = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 2)
        self.assertEqual(report["results"][0]["status"], "error")
        self.assertIn("experimental", report["results"][0]["error_message"])

    def test_project_command(self) -> None:
        payload = {
            "norm": "NORM-CUSTOM",
            "control": "project-command",
            "norm_hash": "pending",
            "violations": [],
        }
        cmd = f"{sys.executable} -c 'import json; print(json.dumps({json.dumps(payload)}))'"
        self._write_registry([{"norm": "NORM-CUSTOM", "command": cmd, "mode": "block"}])
        code, report, stderr_str = run_check(self.project_dir, [self.controls_dir])
        self.assertEqual(code, 0)
        self.assertEqual(report["results"][0]["status"], "pass")
        self.assertIn("NORM-CUSTOM", stderr_str)


if __name__ == "__main__":
    unittest.main()
