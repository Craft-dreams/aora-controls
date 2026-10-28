"""Data models and validation for aora-controls."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import fnmatch
from typing import Any

from aora_controls.yaml_parser import YamlParseError, parse_yaml


class ValidationError(ValueError):
    """Raised when descriptor or decision data fails validation."""


VALID_STATUSES = frozenset({"active", "experimental", "retired"})
VALID_KINDS = frozenset({"deterministic", "judgment"})
VALID_MODES = frozenset({"block", "ratchet", "report"})


@dataclass
class Violation:
    file: str
    line: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Violation:
        if not isinstance(data, dict):
            raise ValidationError(f"Expected violation dict, got {type(data).__name__}")
        file = str(data.get("file", ""))
        try:
            line = int(data.get("line", 0))
        except (ValueError, TypeError):
            line = 0
        message = str(data.get("message", ""))
        return cls(file=file, line=line, message=message)


@dataclass
class ControlResult:
    norm: str
    control: str
    norm_hash: str
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "norm": self.norm,
            "control": self.control,
            "norm_hash": self.norm_hash,
            "violations": [v.to_dict() for v in self.violations],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlResult:
        if not isinstance(data, dict):
            raise ValidationError(f"Expected control result dict, got {type(data).__name__}")
        norm = data.get("norm")
        control = data.get("control")
        norm_hash = data.get("norm_hash")
        if norm is None or control is None or norm_hash is None:
            raise ValidationError("ControlResult missing required fields ('norm', 'control', 'norm_hash')")
        raw_violations = data.get("violations", [])
        if not isinstance(raw_violations, list):
            raise ValidationError("ControlResult 'violations' must be a list")
        violations = [Violation.from_dict(v) for v in raw_violations]
        return cls(norm=str(norm), control=str(control), norm_hash=str(norm_hash), violations=violations)


@dataclass
class ControlDescriptor:
    id: str
    norm: str
    norm_hash: str
    status: str
    kind: str
    languages: list[str]
    tool: str
    command: str
    default_mode: str
    owner: str
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    tests: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        required_fields = {
            "id": self.id,
            "norm": self.norm,
            "norm_hash": self.norm_hash,
            "status": self.status,
            "kind": self.kind,
            "tool": self.tool,
            "command": self.command,
            "default_mode": self.default_mode,
            "owner": self.owner,
        }
        for name, val in required_fields.items():
            if not val or not str(val).strip():
                raise ValidationError(f"ControlDescriptor field '{name}' is required and cannot be empty")

        if not isinstance(self.languages, list) or not self.languages:
            raise ValidationError("ControlDescriptor 'languages' must be a non-empty list")

        if self.status not in VALID_STATUSES:
            raise ValidationError(
                f"Invalid status '{self.status}'. Expected one of: {sorted(VALID_STATUSES)}"
            )

        if self.kind not in VALID_KINDS:
            raise ValidationError(
                f"Invalid kind '{self.kind}'. Expected one of: {sorted(VALID_KINDS)}"
            )

        if self.default_mode not in VALID_MODES:
            raise ValidationError(
                f"Invalid default_mode '{self.default_mode}'. Expected one of: {sorted(VALID_MODES)}"
            )

        if self.kind == "judgment" and self.default_mode == "block":
            raise ValidationError("A control with kind: judgment cannot have default_mode: block")

        if not isinstance(self.tests, dict):
            raise ValidationError("ControlDescriptor 'tests' must be a mapping with 'pass' and 'fail' paths")

        if "pass" not in self.tests or "fail" not in self.tests:
            raise ValidationError("ControlDescriptor 'tests' must specify both 'pass' and 'fail'")

        if not isinstance(self.params, dict):
            raise ValidationError("ControlDescriptor 'params' must be a mapping")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlDescriptor:
        if not isinstance(data, dict):
            raise ValidationError(f"Expected dict for ControlDescriptor, got {type(data).__name__}")
        descriptor = cls(
            id=str(data.get("id", "")),
            norm=str(data.get("norm", "")),
            norm_hash=str(data.get("norm_hash", "")),
            status=str(data.get("status", "")),
            kind=str(data.get("kind", "")),
            languages=list(data.get("languages", [])),
            tool=str(data.get("tool", "")),
            command=str(data.get("command", "")),
            default_mode=str(data.get("default_mode", "")),
            owner=str(data.get("owner", "")),
            params=dict(data.get("params", {}) or {}),
            tests=dict(data.get("tests", {}) or {}),
        )
        descriptor.validate()
        return descriptor

    @classmethod
    def from_yaml(cls, content: str) -> ControlDescriptor:
        parsed = parse_yaml(content)
        return cls.from_dict(parsed)


@dataclass
class NormDecision:
    norm: str
    norm_hash: str
    control: str | None = None
    command: str | None = None
    mode: str = "ratchet"
    params: dict[str, Any] = field(default_factory=dict)
    decided_at: str = ""
    decided_by: str = ""
    reason: str = ""
    superseded_at: str | None = None

    def validate(self) -> None:
        if not self.norm or not str(self.norm).strip():
            raise ValidationError("NormDecision 'norm' is required and cannot be empty")
        if not self.norm_hash or not str(self.norm_hash).strip():
            raise ValidationError("NormDecision 'norm_hash' is required and cannot be empty")
        if not self.control and not self.command:
            raise ValidationError(f"NormDecision for '{self.norm}' must specify either 'control' or 'command'")
        if self.mode not in VALID_MODES:
            raise ValidationError(
                f"Invalid mode '{self.mode}' for norm '{self.norm}'. Expected one of: {sorted(VALID_MODES)}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormDecision:
        if not isinstance(data, dict):
            raise ValidationError(f"Expected dict for NormDecision, got {type(data).__name__}")
        decision = cls(
            norm=str(data.get("norm", "")),
            norm_hash=str(data.get("norm_hash", "")),
            control=str(data["control"]) if data.get("control") is not None else None,
            command=str(data["command"]) if data.get("command") is not None else None,
            mode=str(data.get("mode", "ratchet")),
            params=dict(data.get("params", {}) or {}),
            decided_at=str(data.get("decided_at", "") or ""),
            decided_by=str(data.get("decided_by", "") or ""),
            reason=str(data.get("reason", "") or ""),
            superseded_at=str(data["superseded_at"]) if data.get("superseded_at") is not None else None,
        )
        decision.validate()
        return decision


@dataclass
class ExceptionRule:
    norm: str
    path: str
    reason: str
    owner: str
    expires: str

    def is_expired(self, reference_date: str | None = None) -> bool:
        ref = reference_date if reference_date is not None else date.today().isoformat()
        return self.expires < ref

    def matches(self, norm: str, file_path: str) -> bool:
        if self.norm != norm:
            return False
        # Normalize leading ./ in path comparison
        clean_target = file_path.removeprefix("./")
        clean_glob = self.path.removeprefix("./")
        return fnmatch.fnmatch(clean_target, clean_glob)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExceptionRule:
        if not isinstance(data, dict):
            raise ValidationError(f"Expected dict for ExceptionRule, got {type(data).__name__}")
        for field_name in ("norm", "path", "reason", "owner", "expires"):
            if not data.get(field_name):
                raise ValidationError(f"ExceptionRule missing required field '{field_name}'")
        return cls(
            norm=str(data["norm"]),
            path=str(data["path"]),
            reason=str(data["reason"]),
            owner=str(data["owner"]),
            expires=str(data["expires"]),
        )


@dataclass
class ProjectRegistry:
    controls_repo: dict[str, str] | None = None
    norms: list[NormDecision] = field(default_factory=list)
    baseline: str = ".aora/baseline.json"
    exceptions: str = ".aora/exceptions.yaml"

    def validate(self) -> None:
        if not isinstance(self.norms, list):
            raise ValidationError("ProjectRegistry 'norms' must be a list")
        for decision in self.norms:
            decision.validate()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectRegistry:
        if not isinstance(data, dict):
            raise ValidationError(f"Expected dict for ProjectRegistry, got {type(data).__name__}")
        controls_repo = data.get("controls_repo")
        if controls_repo is not None and not isinstance(controls_repo, dict):
            raise ValidationError("ProjectRegistry 'controls_repo' must be a mapping")

        raw_norms = data.get("norms", [])
        if not isinstance(raw_norms, list):
            raise ValidationError("ProjectRegistry 'norms' must be a list")
        norms = [NormDecision.from_dict(item) for item in raw_norms]

        baseline = str(data.get("baseline", ".aora/baseline.json"))
        exceptions = str(data.get("exceptions", ".aora/exceptions.yaml"))

        registry = cls(
            controls_repo=dict(controls_repo) if controls_repo else None,
            norms=norms,
            baseline=baseline,
            exceptions=exceptions,
        )
        registry.validate()
        return registry

    @classmethod
    def from_yaml(cls, content: str) -> ProjectRegistry:
        parsed = parse_yaml(content)
        return cls.from_dict(parsed)


def validate_decision_with_descriptor(decision: NormDecision, descriptor: ControlDescriptor) -> None:
    """Validate that a decision is compatible with its control descriptor."""
    if descriptor.kind == "judgment" and decision.mode == "block":
        raise ValidationError(
            f"Control '{descriptor.id}' has kind: judgment and cannot be adopted with mode: block "
            f"for norm '{decision.norm}'"
        )
    if descriptor.norm != decision.norm:
        raise ValidationError(
            f"Control '{descriptor.id}' targets norm '{descriptor.norm}', "
            f"which does not match decision norm '{decision.norm}'"
        )
