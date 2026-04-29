"""Command builder for future hyperfine usage."""

from __future__ import annotations

import shlex
from pathlib import Path


class HyperfineCommandBuilder:
    """Build hyperfine command strings without executing them."""

    def __init__(self, *, warmup: int = 1):
        self.warmup = warmup

    def build(
        self,
        *,
        baseline_cmd: str,
        candidate_cmd: str,
        repeats: int,
        export_json: str | Path | None = None,
    ) -> str:
        parts = [
            "hyperfine",
            "--runs",
            str(repeats),
            "--warmup",
            str(self.warmup),
        ]
        if export_json is not None:
            parts.extend(["--export-json", str(export_json)])
        parts.extend([baseline_cmd, candidate_cmd])
        return " ".join(shlex.quote(part) for part in parts)
