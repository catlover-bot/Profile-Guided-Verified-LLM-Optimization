"""Compile-gate helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from vallmopt.logging.schema import VerifyGateResult
from vallmopt.utils.subprocess import command_to_string, run_command


def build_gcc_command(
    *,
    source: str | Path,
    output: str | Path,
    compiler: str = "gcc",
    cflags: Sequence[str] | None = None,
    ldflags: Sequence[str] | None = None,
) -> list[str]:
    """Construct a C compiler command for a single source file."""

    return [
        compiler,
        *(cflags or []),
        str(source),
        "-o",
        str(output),
        *(ldflags or []),
    ]


def compile_source(
    *,
    source: str | Path,
    output: str | Path,
    compiler: str = "gcc",
    cflags: Sequence[str] | None = None,
    ldflags: Sequence[str] | None = None,
    dry_run: bool = False,
) -> VerifyGateResult:
    """Run or dry-run the compile gate."""

    command = build_gcc_command(
        source=source,
        output=output,
        compiler=compiler,
        cflags=cflags,
        ldflags=ldflags,
    )
    if dry_run:
        return VerifyGateResult(
            gate_name="compile",
            status="skipped",
            command=command_to_string(command),
            failure_reason="dry-run",
        )

    result = run_command(command)
    if result.returncode == 0:
        return VerifyGateResult(
            gate_name="compile",
            status="pass",
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_sec=result.elapsed_sec,
        )
    return VerifyGateResult(
        gate_name="compile",
        status="fail",
        command=result.command,
        stdout=result.stdout,
        stderr=result.stderr,
        elapsed_sec=result.elapsed_sec,
        failure_reason=f"compiler exited with status {result.returncode}",
    )
