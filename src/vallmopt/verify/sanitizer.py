"""Sanitizer-gate helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from vallmopt.logging.schema import VerifyGateResult
from vallmopt.utils.subprocess import command_to_string, run_command
from vallmopt.utils.tools import find_executable
from vallmopt.verify.compile import build_gcc_command
from vallmopt.verify.runtime import build_run_command


def build_clang_sanitizer_command(
    *,
    source: str | Path,
    output: str | Path,
    compiler: str = "clang",
    cflags: Sequence[str] | None = None,
    ldflags: Sequence[str] | None = None,
) -> list[str]:
    """Construct a clang ASan/UBSan compile command."""

    effective_cflags = list(cflags or ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"])
    effective_ldflags = list(ldflags or ["-fsanitize=address,undefined"])
    return build_gcc_command(
        source=source,
        output=output,
        compiler=compiler,
        cflags=effective_cflags,
        ldflags=effective_ldflags,
    )


def run_sanitizer_gate(
    *,
    source: str | Path,
    output: str | Path,
    compiler: str = "clang",
    cflags: Sequence[str] | None = None,
    ldflags: Sequence[str] | None = None,
    runtime_args: Sequence[str] | None = None,
    timeout_sec: float = 10,
    dry_run: bool = False,
    required: bool = False,
    skip_if_unavailable: bool = True,
    skip_on_windows: bool = True,
) -> VerifyGateResult:
    """Build and run a sanitizer-instrumented candidate binary."""

    compile_command = build_clang_sanitizer_command(
        source=source,
        output=output,
        compiler=compiler,
        cflags=cflags,
        ldflags=ldflags,
    )
    run_command_text = build_run_command(output, runtime_args)
    command_text = f"{command_to_string(compile_command)} && {command_to_string(run_command_text)}"
    if dry_run:
        return VerifyGateResult(
            gate_name="sanitizer",
            status="skipped",
            command=command_text,
            failure_reason="dry-run",
        )
    if os.name == "nt" and skip_on_windows and not required:
        return VerifyGateResult(
            gate_name="sanitizer",
            status="skipped",
            command=command_text,
            failure_reason="optional sanitizer gate skipped on Windows",
        )
    if find_executable(compiler) is None:
        if skip_if_unavailable and not required:
            return VerifyGateResult(
                gate_name="sanitizer",
                status="skipped",
                command=command_text,
                failure_reason=f"optional sanitizer compiler not available: {compiler}",
            )
        return VerifyGateResult(
            gate_name="sanitizer",
            status="fail",
            command=command_text,
            failure_reason=f"sanitizer compiler not found on PATH: {compiler}",
        )

    compile_result = run_command(compile_command)
    elapsed = compile_result.elapsed_sec
    if compile_result.returncode != 0:
        return VerifyGateResult(
            gate_name="sanitizer",
            status="fail",
            command=command_text,
            stdout=compile_result.stdout,
            stderr=compile_result.stderr,
            elapsed_sec=elapsed,
            failure_reason=f"sanitizer compiler exited with status {compile_result.returncode}",
        )

    runtime_result = run_command(run_command_text, timeout_sec=timeout_sec)
    elapsed += runtime_result.elapsed_sec
    if runtime_result.timed_out:
        return VerifyGateResult(
            gate_name="sanitizer",
            status="fail",
            command=command_text,
            stdout=runtime_result.stdout,
            stderr=runtime_result.stderr,
            elapsed_sec=elapsed,
            failure_reason=f"sanitizer runtime exceeded timeout of {timeout_sec} seconds",
        )
    if runtime_result.returncode == 0:
        return VerifyGateResult(
            gate_name="sanitizer",
            status="pass",
            command=command_text,
            stdout=runtime_result.stdout,
            stderr=runtime_result.stderr,
            elapsed_sec=elapsed,
        )
    return VerifyGateResult(
        gate_name="sanitizer",
        status="fail",
        command=command_text,
        stdout=runtime_result.stdout,
        stderr=runtime_result.stderr,
        elapsed_sec=elapsed,
        failure_reason=f"sanitizer binary exited with status {runtime_result.returncode}",
    )
