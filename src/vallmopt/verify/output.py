"""Output-equivalence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from vallmopt.logging.schema import VerifyGateResult
from vallmopt.utils.subprocess import command_to_string, run_command
from vallmopt.verify.compile import build_gcc_command
from vallmopt.verify.runtime import build_run_command


def compare_text_outputs(reference_output: str, candidate_output: str) -> VerifyGateResult:
    """Compare captured reference and candidate stdout exactly."""

    if reference_output == candidate_output:
        return VerifyGateResult(gate_name="output", status="pass")
    return VerifyGateResult(
        gate_name="output",
        status="fail",
        failure_reason="candidate stdout differs from reference stdout",
    )


def compare_candidate_to_reference(
    *,
    reference_source: str | Path,
    candidate_binary: str | Path,
    reference_binary: str | Path,
    compiler: str = "gcc",
    cflags: Sequence[str] | None = None,
    ldflags: Sequence[str] | None = None,
    runtime_args: Sequence[str] | None = None,
    timeout_sec: float = 10,
    dry_run: bool = False,
) -> VerifyGateResult:
    """Compile the reference, run both binaries, and compare stdout."""

    compile_command = build_gcc_command(
        source=reference_source,
        output=reference_binary,
        compiler=compiler,
        cflags=cflags,
        ldflags=ldflags,
    )
    candidate_command = build_run_command(candidate_binary, runtime_args)
    reference_command = build_run_command(reference_binary, runtime_args)
    command_text = (
        f"{command_to_string(compile_command)} && "
        f"{command_to_string(reference_command)} && "
        f"{command_to_string(candidate_command)}"
    )
    if dry_run:
        return VerifyGateResult(
            gate_name="output",
            status="skipped",
            command=command_text,
            failure_reason="dry-run",
        )

    compile_result = run_command(compile_command)
    elapsed = compile_result.elapsed_sec
    if compile_result.returncode != 0:
        return VerifyGateResult(
            gate_name="output",
            status="fail",
            command=command_text,
            stdout=compile_result.stdout,
            stderr=compile_result.stderr,
            elapsed_sec=elapsed,
            failure_reason=f"reference compiler exited with status {compile_result.returncode}",
        )

    reference_result = run_command(reference_command, timeout_sec=timeout_sec)
    elapsed += reference_result.elapsed_sec
    if reference_result.timed_out or reference_result.returncode != 0:
        reason = (
            f"reference runtime exceeded timeout of {timeout_sec} seconds"
            if reference_result.timed_out
            else f"reference binary exited with status {reference_result.returncode}"
        )
        return VerifyGateResult(
            gate_name="output",
            status="fail",
            command=command_text,
            stdout=reference_result.stdout,
            stderr=reference_result.stderr,
            elapsed_sec=elapsed,
            failure_reason=reason,
        )

    candidate_result = run_command(candidate_command, timeout_sec=timeout_sec)
    elapsed += candidate_result.elapsed_sec
    if candidate_result.timed_out or candidate_result.returncode != 0:
        reason = (
            f"candidate runtime exceeded timeout of {timeout_sec} seconds"
            if candidate_result.timed_out
            else f"candidate binary exited with status {candidate_result.returncode}"
        )
        return VerifyGateResult(
            gate_name="output",
            status="fail",
            command=command_text,
            stdout=candidate_result.stdout,
            stderr=candidate_result.stderr,
            elapsed_sec=elapsed,
            failure_reason=reason,
        )

    comparison = compare_text_outputs(reference_result.stdout, candidate_result.stdout)
    comparison.command = command_text
    comparison.stdout = candidate_result.stdout
    comparison.stderr = candidate_result.stderr
    comparison.elapsed_sec = elapsed
    return comparison
