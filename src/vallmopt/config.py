"""Configuration loading helpers.

The project uses YAML files for human-readable experiment configuration. PyYAML
is used when available, with a deliberately small fallback parser that supports
the simple mapping/list/scalar structures used by the bundled configs.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping from ``path``.

    Raises:
        ValueError: if the file does not contain a top-level mapping.
    """

    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        data = _load_minimal_yaml(text)

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level mapping in config file: {path}")
    return data


def _load_minimal_yaml(text: str) -> Any:
    lines = [
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return {}
    data, index = _parse_block(lines, 0, _indent(lines[0]))
    if index != len(lines):
        raise ValueError("Could not parse complete YAML document with fallback parser")
    return data


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index

    stripped = lines[index].strip()
    if stripped.startswith("- "):
        items: list[Any] = []
        while index < len(lines) and _indent(lines[index]) == indent:
            current = lines[index].strip()
            if not current.startswith("- "):
                break
            item_text = current[2:].strip()
            index += 1
            if item_text:
                items.append(_parse_scalar(item_text))
            else:
                nested, index = _parse_block(lines, index, indent + 2)
                items.append(nested)
        return items, index

    mapping: dict[str, Any] = {}
    while index < len(lines):
        line_indent = _indent(lines[index])
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ValueError(f"Unexpected indentation in line: {lines[index]!r}")

        stripped = lines[index].strip()
        if ":" not in stripped:
            raise ValueError(f"Expected key/value entry in line: {lines[index]!r}")
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        index += 1
        if value:
            mapping[key] = _parse_scalar(value)
        else:
            if index >= len(lines) or _indent(lines[index]) <= line_indent:
                mapping[key] = {}
            else:
                mapping[key], index = _parse_block(lines, index, line_indent + 2)
    return mapping, index


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_scalar(value: str) -> Any:
    if value in {"[]", "{}"}:
        return ast.literal_eval(value)
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        return ast.literal_eval(value)
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return ast.literal_eval(value)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
