"""Unit tests for models and YAML parser."""
from __future__ import annotations

import unittest

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
from aora_controls.yaml_parser import YamlParseError, parse_yaml


class TestYamlParser(unittest.TestCase):
    def test_parse_scalars(self) -> None:
        self.assertEqual(parse_yaml("num: 42"), {"num": 42})
        self.assertEqual(parse_yaml("pi: 3.14"), {"pi": 3.14})
        self.assertEqual(parse_yaml("flag: true"), {"flag": True})
        self.assertEqual(parse_yaml("no_val: null"), {"no_val": None})
        self.assertEqual(parse_yaml("str: 'hello world'"), {"str": "hello world"})
        self.assertEqual(parse_yaml('str2: "hello\\nworld"'), {"str2": "hello\nworld"})

    def test_parse_inline_structures(self) -> None:
        self.assertEqual(parse_yaml("items: [a, b, c]"), {"items": ["a", "b", "c"]})
        self.assertEqual(
            parse_yaml("params: {default: app/domain, description: text}"),
            {"params": {"default": "app/domain", "description": "text"}},
        )

    def test_parse_nested_and_comments(self) -> None:
        content = """
        # Comment header
        root:
          sub:
            val: 10 # inline comment
          list:
            - item1
            - item2
        """
        parsed = parse_yaml(content)
        self.assertEqual(parsed, {"root": {"sub": {"val": 10}, "list": ["item1", "item2"]}})

    def test_parse_top_level_list(self) -> None:
        content = """
        - norm: NORM-001
          path: src/legacy/*
        - norm: NORM-002
          path: app/*
        """
        parsed = parse_yaml(content)
        self.assertEqual(
            parsed,
            [
                {"norm": "NORM-001", "path": "src/legacy/*"},
                {"norm": "NORM-002", "path": "app/*"},
            ],
        )

    def test_invalid_syntax(self) -> None:
        with self.assertRaises(YamlParseError):
            parse_yaml("not a key value")


class TestModel(unittest.TestCase):
    def test_control_descriptor_valid(self) -> None:
        raw = """
        id: ARCH-LAYERS-001-py-ast
        norm: ARCH-LAYERS-001
        norm_hash: pending
        status: active
        kind: deterministic
        languages: [python]
        tool: python-ast
        params:
          domain: {default: app/domain, description: domain package}
        command: "python3 {control_dir}/check.py --domain {params.domain}"
        default_mode: ratchet
        owner: test-eng
        tests: {pass: tests/pass, fail: tests/fail}
        """
        descriptor = ControlDescriptor.from_yaml(raw)
        self.assertEqual(descriptor.id, "ARCH-LAYERS-001-py-ast")
        self.assertEqual(descriptor.status, "active")
        self.assertEqual(descriptor.kind, "deterministic")
        self.assertEqual(descriptor.default_mode, "ratchet")
        self.assertEqual(descriptor.tests["pass"], "tests/pass")

    def test_control_descriptor_invalid_judgment_block(self) -> None:
        raw = """
        id: REVIEW-001
        norm: REV-001
        norm_hash: pending
        status: active
        kind: judgment
        languages: [python]
        tool: reviewer
        command: "python3 check.py"
        default_mode: block
        owner: test-eng
        tests: {pass: tests/pass, fail: tests/fail}
        """
        with self.assertRaises(ValidationError) as ctx:
            ControlDescriptor.from_yaml(raw)
        self.assertIn("judgment cannot have default_mode: block", str(ctx.exception))

    def test_control_descriptor_invalid_enum(self) -> None:
        raw = """
        id: CTRL-001
        norm: NORM-001
        norm_hash: pending
        status: invalid_status
        kind: deterministic
        languages: [python]
        tool: python-ast
        command: "python3 check.py"
        default_mode: ratchet
        owner: test-eng
        tests: {pass: tests/pass, fail: tests/fail}
        """
        with self.assertRaises(ValidationError):
            ControlDescriptor.from_yaml(raw)

    def test_control_descriptor_missing_field(self) -> None:
        raw = """
        id: CTRL-001
        norm: NORM-001
        status: active
        """
        with self.assertRaises(ValidationError):
            ControlDescriptor.from_yaml(raw)

    def test_norm_decision_valid(self) -> None:
        decision = NormDecision.from_dict({
            "norm": "NORM-001",
            "norm_hash": "hash123",
            "control": "CTRL-001",
            "mode": "block",
            "decided_at": "2026-10-28",
            "decided_by": "alice",
            "reason": "security requirement",
        })
        self.assertEqual(decision.mode, "block")

    def test_norm_decision_missing_control_and_command(self) -> None:
        with self.assertRaises(ValidationError):
            NormDecision.from_dict({
                "norm": "NORM-001",
                "norm_hash": "hash123",
                "mode": "block",
            })

    def test_validate_decision_with_descriptor_judgment_block(self) -> None:
        desc = ControlDescriptor(
            id="REV-001",
            norm="NORM-001",
            norm_hash="hash123",
            status="active",
            kind="judgment",
            languages=["python"],
            tool="reviewer",
            command="python3 check.py",
            default_mode="report",
            owner="eng",
            tests={"pass": "p", "fail": "f"},
        )
        decision = NormDecision(
            norm="NORM-001",
            norm_hash="hash123",
            control="REV-001",
            mode="block",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_decision_with_descriptor(decision, desc)
        self.assertIn("cannot be adopted with mode: block", str(ctx.exception))

    def test_project_registry(self) -> None:
        raw = """
        controls_repo: {repository: Craft-dreams/aora-controls, ref: main}
        norms:
          - norm: NORM-001
            norm_hash: hash1
            control: CTRL-001
            mode: ratchet
        baseline: .aora/baseline.json
        exceptions: .aora/exceptions.yaml
        """
        reg = ProjectRegistry.from_yaml(raw)
        self.assertEqual(len(reg.norms), 1)
        self.assertEqual(reg.norms[0].norm, "NORM-001")

    def test_violation_and_result(self) -> None:
        v = Violation(file="app/model.py", line=15, message="unauthorized import")
        self.assertEqual(v.to_dict(), {"file": "app/model.py", "line": 15, "message": "unauthorized import"})

        res = ControlResult(
            norm="NORM-001",
            control="CTRL-001",
            norm_hash="pending",
            violations=[v],
        )
        data = res.to_dict()
        reconstructed = ControlResult.from_dict(data)
        self.assertEqual(len(reconstructed.violations), 1)
        self.assertEqual(reconstructed.violations[0].line, 15)

    def test_exception_rule(self) -> None:
        exc = ExceptionRule(
            norm="NORM-001",
            path="legacy/*.py",
            reason="refactor planned",
            owner="team",
            expires="2026-12-31",
        )
        self.assertTrue(exc.matches("NORM-001", "legacy/old.py"))
        self.assertFalse(exc.matches("NORM-001", "app/main.py"))
        self.assertFalse(exc.matches("OTHER-NORM", "legacy/old.py"))
        self.assertFalse(exc.is_expired(reference_date="2026-10-28"))
        self.assertTrue(exc.is_expired(reference_date="2027-01-01"))


if __name__ == "__main__":
    unittest.main()
