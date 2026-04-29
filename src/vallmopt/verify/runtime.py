"""Runtime-gate helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from vallmopt.logging.schema import VerifyGateResult
from vallmopt.utils.subprocess import command_to_string, run_command


def build_run_command(binary: str | Path, args: Sequence[str] | None = None) -> list[str]:
    """Construct a command for running a compiled binary."""

    return [str(binary), *(args or [])]


def run_binary(
    *,
    binary: str | Path,
    args: Sequence[str] | None = None,
    timeout_sec: float = 10,
    dry_run: bool = False,
) -> VerifyGateResult:
    """Run or dry-run a binary."""

    command = build_run_command(binary, args)
    if dry_run:
        return VerifyGateResult(
            gate_name="runtime",
            status="skipped",
            command=command_to_string(command),
            failure_reason="dry-run",
        )

    result = run_command(command, timeout_sec=timeout_sec)
    if result.timed_out:
        return VerifyGateResult(
            gate_name="runtime",
            status="fail",
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_sec=result.elapsed_sec,
            failure_reason=f"runtime exceeded timeout of {timeout_sec} seconds",
        )
    if result.returncode == 0:
        return VerifyGateResult(
            gate_name="runtime",
            status="pass",
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_sec=result.elapsed_sec,
        )
    return VerifyGateResult(
        gate_name="runtime",
        status="fail",
        command=result.command,
        stdout=result.stdout,
        stderr=result.stderr,
        elapsed_sec=result.elapsed_sec,
        failure_reason=f"binary exited with status {result.returncode}",
    )
