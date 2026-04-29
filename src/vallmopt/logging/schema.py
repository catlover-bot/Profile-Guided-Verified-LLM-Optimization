"""Dataclasses used for candidate, verification, and benchmark logs."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def git_commit(cwd: str | Path | None = None) -> str | None:
    """Return the current git commit hash if available."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


@dataclass
class VerifyGateResult:
    gate_name: str
    status: str
    command: str | None = None
    stdout: str = ""
    stderr: str = ""
    elapsed_sec: float = 0.0
    failure_reason: str | None = None


@dataclass
class CandidateRecord:
    kernel_name: str
    arch_tag: str
    isa: str
    generator_name: str | None
    prompt_hash: str
    reference_code_hash: str
    candidate_code_hash: str
    status: str
    timestamp: str = field(default_factory=utc_timestamp)
    model_name: str | None = None
    git_commit: str | None = None
    config_path: str | None = None
    failure_reason: str | None = None
    prompt_path: str | None = None
    candidate_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifyRecord:
    kernel_name: str
    arch_tag: str
    isa: str
    generator_name: str | None
    prompt_hash: str | None
    reference_code_hash: str
    candidate_code_hash: str
    status: str
    gates: list[VerifyGateResult] = field(default_factory=list)
    timestamp: str = field(default_factory=utc_timestamp)
    model_name: str | None = None
    git_commit: str | None = None
    config_path: str | None = None
    failure_reason: str | None = None
    work_dir: str | None = None
    compiler_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkRecord:
    kernel_name: str
    arch_tag: str
    isa: str
    generator_name: str | None
    prompt_hash: str | None
    reference_code_hash: str | None
    candidate_code_hash: str | None
    status: str
    baseline_cmd: str
    candidate_cmd: str
    repeats: int
    baseline_timings_sec: list[float] = field(default_factory=list)
    candidate_timings_sec: list[float] = field(default_factory=list)
    baseline_median_sec: float | None = None
    candidate_median_sec: float | None = None
    baseline_iqr_sec: float | None = None
    candidate_iqr_sec: float | None = None
    speedup: float | None = None
    timestamp: str = field(default_factory=utc_timestamp)
    model_name: str | None = None
    git_commit: str | None = None
    config_path: str | None = None
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentMetadata:
    experiment_name: str
    architectures: list[str]
    status: str
    timestamp: str = field(default_factory=utc_timestamp)
    git_commit: str | None = None
    config_path: str | None = None
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def to_jsonable(record: Any) -> dict[str, Any]:
    """Convert a dataclass record or mapping to a JSON-serializable mapping."""

    if is_dataclass(record):
        return asdict(record)
    if isinstance(record, dict):
        return dict(record)
    raise TypeError(f"Expected dataclass or dict record, got {type(record).__name__}")
