"""Unit tests for baseline and coverage commands."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from aora_controls.baseline import run_baseline
from aora_controls.coverage import analyze_coverage, run_coverage


class TestBaselineAndCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.tmp.name)
        self.aora_dir = self.project_dir / ".aora"
        self.aora_dir.mkdir(parents=True)
        self.controls_dir = self.project_dir / "controls"
        self.controls_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_control(self, norm: str, control_id: str, violation_count: int) -> None:
        ctrl_path = self.controls_dir / norm / control_id
        ctrl_path.mkdir(parents=True, exist_ok=True)
        violations = [{"file": f"app/f{i}.py", "line": i, "message": "msg"} for i in range(violation_count)]
        payload = {
            "norm": norm,
            "control": control_id,
            "norm_hash": "pending",
            "violations": violations,
        }
        (ctrl_path / "check.py").write_text(
            f"import sys\nprint({json.dumps(json.dumps(payload))})\nsys.exit({1 if violation_count else 0})\n",
            encoding="utf-8",
        )
        yaml_content = f"""
        id: {control_id}
        norm: {norm}
        norm_hash: pending
        status: active
        kind: deterministic
        languages: [python]
        tool: custom
        command: "{sys.executable} {{control_dir}}/check.py"
        default_mode: ratchet
        owner: test-team
        tests: {{pass: tests/pass, fail: tests/fail}}
        """
        (ctrl_path / "control.yaml").write_text(yaml_content, encoding="utf-8")

    def _write_registry(self, norms_list: list[dict]) -> None:
        lines = [
            "controls_repo: {repository: repo, ref: main}",
            "norms:",
        ]
        for n in norms_list:
            lines.append(f"  - norm: {n['norm']}")
            lines.append(f"    norm_hash: {n.get('norm_hash', 'pending')}")
            lines.append(f"    control: {n['control']}")
            lines.append(f"    mode: {n.get('mode', 'ratchet')}")
        lines.append("baseline: .aora/baseline.json")
        lines.append("exceptions: .aora/exceptions.yaml")
        (self.aora_dir / "norms.yaml").write_text("\n".join(lines), encoding="utf-8")

    def test_baseline_init_success_and_conflict(self) -> None:
        self._create_control("NORM-001", "CTRL-001", violation_count=3)
        self._write_registry([{"norm": "NORM-001", "control": "CTRL-001"}])

        # Init when none exists
        exit_code = run_baseline(self.project_dir, init=True, controls_dirs=[self.controls_dir])
        self.assertEqual(exit_code, 0)
        baseline_file = self.aora_dir / "baseline.json"
        self.assertTrue(baseline_file.is_file())
        data = json.loads(baseline_file.read_text(encoding="utf-8"))
        self.assertEqual(data.get("NORM-001"), 3)

        # Init again -> must fail because already exists
        exit_code2 = run_baseline(self.project_dir, init=True, controls_dirs=[self.controls_dir])
        self.assertEqual(exit_code2, 2)

    def test_baseline_ratchet_down_and_refuse_increase(self) -> None:
        baseline_file = self.aora_dir / "baseline.json"
        baseline_file.write_text(json.dumps({"NORM-001": 5}), encoding="utf-8")

        # Violations decreased to 2 -> baseline should update to 2
        self._create_control("NORM-001", "CTRL-001", violation_count=2)
        self._write_registry([{"norm": "NORM-001", "control": "CTRL-001"}])
        exit_code = run_baseline(self.project_dir, init=False, controls_dirs=[self.controls_dir])
        self.assertEqual(exit_code, 0)
        data = json.loads(baseline_file.read_text(encoding="utf-8"))
        self.assertEqual(data.get("NORM-001"), 2)

        # Violations increased to 4 -> baseline refuses to increase
        self._create_control("NORM-001", "CTRL-001", violation_count=4)
        exit_code_increase = run_baseline(self.project_dir, init=False, controls_dirs=[self.controls_dir])
        self.assertEqual(exit_code_increase, 1)
        data_after = json.loads(baseline_file.read_text(encoding="utf-8"))
        self.assertEqual(data_after.get("NORM-001"), 2)  # Remains 2!

    def test_baseline_without_init_when_missing(self) -> None:
        self._create_control("NORM-001", "CTRL-001", violation_count=0)
        self._write_registry([{"norm": "NORM-001", "control": "CTRL-001"}])
        exit_code = run_baseline(self.project_dir, init=False, controls_dirs=[self.controls_dir])
        self.assertEqual(exit_code, 2)

    def test_coverage_analysis(self) -> None:
        self._write_registry([
            {"norm": "ARCH-001", "control": "CTRL-A", "norm_hash": "pending"},
            {"norm": "SEC-001", "control": "CTRL-B", "norm_hash": "hash_old"},
            {"norm": "CONF-001", "control": "CTRL-C", "norm_hash": "hash_exact"},
        ])
        hub_norms_data = [
            {"id": "ARCH-001", "status": "active", "content_hash": "hash_arch"},
            {"id": "SEC-001", "status": "active", "content_hash": "hash_new"},
            {"id": "CONF-001", "status": "active", "content_hash": "hash_exact"},
            {"id": "MISSING-001", "status": "active", "content_hash": "hash_missing"},
        ]
        hub_file = self.project_dir / "hub_norms.json"
        hub_file.write_text(json.dumps(hub_norms_data), encoding="utf-8")

        report = analyze_coverage(self.project_dir, hub_norms_path=hub_file)
        by_norm = {r["norm"]: r for r in report["norms"]}

        self.assertEqual(by_norm["ARCH-001"]["status"], "pending")
        self.assertEqual(by_norm["SEC-001"]["status"], "outdated")
        self.assertEqual(by_norm["CONF-001"]["status"], "up_to_date")
        self.assertEqual(by_norm["MISSING-001"]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
