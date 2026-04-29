"""JSONL read/write helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from vallmopt.logging.schema import to_jsonable
from vallmopt.utils.paths import ensure_parent


def append_jsonl(path: str | Path, record: Any) -> None:
    """Append one record to a JSONL file."""

    path = ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(to_jsonable(record), sort_keys=True) + "\n")


def write_jsonl(path: str | Path, records: Iterable[Any]) -> None:
    """Write records to a JSONL file, replacing any existing file."""

    path = ensure_parent(path)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(to_jsonable(record), sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dictionaries."""

    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object on line {line_number} of {path}")
            rows.append(value)
    return rows
