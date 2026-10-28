"""Minimal custom YAML parser supporting the subset used by aora-controls.

Supports mappings, lists (block and inline), strings, numbers, booleans, and nulls.
No external dependencies.
"""
from __future__ import annotations

import ast
import re
from typing import Any


class YamlParseError(ValueError):
    """Raised when parsing custom YAML fails."""


def _strip_comment(line: str) -> str:
    """Strip comments not enclosed in quotes."""
    in_single = False
    in_double = False
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and (in_single or in_double):
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i].rstrip()
    return line.rstrip()


def _split_top_level(text: str, delimiter: str = ",") -> list[str]:
    """Split text by delimiter only when not enclosed in quotes, braces or brackets."""
    parts: list[str] = []
    curr: list[str] = []
    in_single = False
    in_double = False
    brace_depth = 0
    bracket_depth = 0
    escaped = False

    for ch in text:
        if escaped:
            curr.append(ch)
            escaped = False
            continue
        if ch == "\\" and (in_single or in_double):
            curr.append(ch)
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            curr.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            curr.append(ch)
        elif not in_single and not in_double:
            if ch == "{":
                brace_depth += 1
                curr.append(ch)
            elif ch == "}":
                brace_depth -= 1
                curr.append(ch)
            elif ch == "[":
                bracket_depth += 1
                curr.append(ch)
            elif ch == "]":
                bracket_depth -= 1
                curr.append(ch)
            elif ch == delimiter and brace_depth == 0 and bracket_depth == 0:
                parts.append("".join(curr).strip())
                curr = []
            else:
                curr.append(ch)
        else:
            curr.append(ch)

    if curr:
        parts.append("".join(curr).strip())
    return parts


def parse_scalar(text: str) -> Any:
    """Parse inline scalar, list, or mapping."""
    text = text.strip()
    if not text:
        return None

    # Quoted string
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        if text.startswith('"'):
            try:
                return ast.literal_eval(text)
            except Exception:
                return text[1:-1]
        else:
            return text[1:-1].replace("''", "'")

    # Inline mapping
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        if not inner:
            return {}
        items = _split_top_level(inner, ",")
        result: dict[str, Any] = {}
        for item in items:
            kv = _split_top_level(item, ":")
            if len(kv) >= 2:
                k = parse_scalar(kv[0])
                v = parse_scalar(":".join(kv[1:]))
                result[str(k)] = v
            else:
                raise YamlParseError(f"Invalid inline mapping entry: '{item}'")
        return result

    # Inline list
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        items = _split_top_level(inner, ",")
        return [parse_scalar(it) for it in items]

    # Booleans
    lower = text.lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False

    # Null
    if lower in ("null", "~", "none"):
        return None

    # Numbers
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)

    # Bare string
    return text


def _find_key_split(text: str) -> tuple[str, str] | None:
    """Find the top-level colon separating key and value."""
    in_single = False
    in_double = False
    escaped = False

    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and (in_single or in_double):
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == ":" and not in_single and not in_double:
            if i + 1 == len(text) or text[i + 1] in (" ", "\t"):
                key = text[:i].strip()
                val = text[i + 1 :].strip()
                return key, val
    return None


class _Line:
    __slots__ = ("indent", "text", "line_no")

    def __init__(self, indent: int, text: str, line_no: int):
        self.indent = indent
        self.text = text
        self.line_no = line_no


def parse_yaml(content: str) -> Any:
    """Parse a YAML document string into Python structures."""
    raw_lines = content.splitlines()
    lines: list[_Line] = []
    for line_no, raw in enumerate(raw_lines, start=1):
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append(_Line(indent, stripped.strip(), line_no))

    if not lines:
        return {}

    def parse_node(idx: int, min_indent: int) -> tuple[Any, int]:
        if idx >= len(lines):
            return None, idx

        curr_indent = lines[idx].indent
        if curr_indent < min_indent:
            return None, idx

        # List
        if lines[idx].text.startswith("- ") or lines[idx].text == "-":
            res_list: list[Any] = []
            while idx < len(lines) and lines[idx].indent == curr_indent and (
                lines[idx].text.startswith("- ") or lines[idx].text == "-"
            ):
                item_text = lines[idx].text[1:].strip()
                item_line_no = lines[idx].line_no
                idx += 1
                if not item_text:
                    sub_val, idx = parse_node(idx, curr_indent + 1)
                    res_list.append(sub_val)
                else:
                    split = _find_key_split(item_text)
                    if split is not None:
                        dict_indent = curr_indent + 2
                        first_line = _Line(dict_indent, item_text, item_line_no)
                        sub_lines = [first_line]
                        while idx < len(lines) and lines[idx].indent >= dict_indent and not (
                            lines[idx].indent == curr_indent and (
                                lines[idx].text.startswith("- ") or lines[idx].text == "-"
                            )
                        ):
                            sub_lines.append(lines[idx])
                            idx += 1
                        dict_val = parse_sub_block(sub_lines)
                        res_list.append(dict_val)
                    else:
                        scalar = parse_scalar(item_text)
                        res_list.append(scalar)
            return res_list, idx

        # Mapping
        res_dict: dict[str, Any] = {}
        while idx < len(lines) and lines[idx].indent == curr_indent:
            split = _find_key_split(lines[idx].text)
            if split is None:
                raise YamlParseError(f"Line {lines[idx].line_no}: expected 'key: value', got '{lines[idx].text}'")
            k, v_str = split
            k_val = parse_scalar(k)
            idx += 1
            if not v_str:
                if idx < len(lines) and lines[idx].indent > curr_indent:
                    val, idx = parse_node(idx, curr_indent + 1)
                else:
                    val = None
            else:
                val = parse_scalar(v_str)
            res_dict[str(k_val)] = val
        return res_dict, idx

    def parse_sub_block(sub_lines: list[_Line]) -> Any:
        nonlocal lines
        saved_lines = lines
        lines = sub_lines
        val, _ = parse_node(0, 0)
        lines = saved_lines
        return val

    res, _ = parse_node(0, 0)
    return res if res is not None else {}
