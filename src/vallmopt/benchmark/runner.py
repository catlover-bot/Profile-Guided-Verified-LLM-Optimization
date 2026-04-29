"""Local benchmark runner utilities."""

from __future__ import annotations

import time
from pathlib import Path

from vallmopt.benchmark.stats import summarize_timings
from vallmopt.logging.schema import BenchmarkRecord, git_commit
from vallmopt.utils.subprocess import run_command


def time_command(command: str, *, timeout_sec: float | None = None) -> float:
    """Run a shell command once and return elapsed wall-clock seconds."""

    start = time.perf_counter()
    result = run_command(command, timeout_sec=timeout_sec, shell=True)
    elapsed = time.perf_counter() - start
    if result.timed_out:
        raise TimeoutError(f"Command exceeded timeout of {timeout_sec} seconds: {command}")
    if result.returncode != 0:
        raise RuntimeError(f"Command exited with status {result.returncode}: {command}\n{result.stderr}")
    return elapsed


def repeated_timings(
    command: str,
    *,
    repeats: int,
    timeout_sec: float | None = None,
) -> list[float]:
    """Run a command repeatedly and return elapsed timings."""

    if repeats <= 0:
        raise ValueError("repeats must be positive")
    return [time_command(command, timeout_sec=timeout_sec) for _ in range(repeats)]


def benchmark_commands(
    *,
    baseline_cmd: str,
    candidate_cmd: str,
    repeats: int,
    kernel_name: str = "unknown",
    arch_tag: str = "unknown",
    isa: str = "unknown",
    generator_name: str | None = None,
    dry_run: bool = False,
    timeout_sec: float | None = None,
    config_path: str | None = None,
) -> BenchmarkRecord:
    """Run or dry-run repeated benchmark measurements."""

    if dry_run:
        return BenchmarkRecord(
            kernel_name=kernel_name,
            arch_tag=arch_tag,
            isa=isa,
            generator_name=generator_name,
            prompt_hash=None,
            reference_code_hash=None,
            candidate_code_hash=None,
            status="skipped",
            baseline_cmd=baseline_cmd,
            candidate_cmd=candidate_cmd,
            repeats=repeats,
            git_commit=git_commit(Path.cwd()),
            config_path=config_path,
            failure_reason="dry-run",
            metadata={"dry_run": True},
        )

    baseline = repeated_timings(baseline_cmd, repeats=repeats, timeout_sec=timeout_sec)
    candidate = repeated_timings(candidate_cmd, repeats=repeats, timeout_sec=timeout_sec)
    summary = summarize_timings(baseline, candidate)
    return BenchmarkRecord(
        kernel_name=kernel_name,
        arch_tag=arch_tag,
        isa=isa,
        generator_name=generator_name,
        prompt_hash=None,
        reference_code_hash=None,
        candidate_code_hash=None,
        status="pass",
        baseline_cmd=baseline_cmd,
        candidate_cmd=candidate_cmd,
        repeats=repeats,
        baseline_timings_sec=baseline,
        candidate_timings_sec=candidate,
        git_commit=git_commit(Path.cwd()),
        config_path=config_path,
        **summary,
    )
