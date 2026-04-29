"""Summarize JSON and JSONL experiment outputs."""

from __future__ import annotations

import glob
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from vallmopt.logging.jsonl import read_jsonl
from vallmopt.utils.paths import ensure_parent


def load_records(patterns: list[str]) -> list[dict[str, Any]]:
    """Load records from JSONL glob patterns."""

    records: list[dict[str, Any]] = []
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        for match in matches:
            records.extend(read_jsonl(match))
    return records


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a compact status summary from records."""

    by_status = Counter(str(record.get("status", "unknown")) for record in records)
    by_arch: dict[str, Counter[str]] = defaultdict(Counter)
    by_kernel: dict[str, Counter[str]] = defaultdict(Counter)

    for record in records:
        status = str(record.get("status", "unknown"))
        by_arch[str(record.get("arch_tag", "unknown"))][status] += 1
        by_kernel[str(record.get("kernel_name", "unknown"))][status] += 1

    return {
        "total_records": len(records),
        "by_status": dict(by_status),
        "by_arch_tag": {key: dict(value) for key, value in sorted(by_arch.items())},
        "by_kernel": {key: dict(value) for key, value in sorted(by_kernel.items())},
    }


def write_summary(path: str | Path, summary: dict[str, Any]) -> None:
    """Write a JSON summary."""

    path = ensure_parent(path)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
