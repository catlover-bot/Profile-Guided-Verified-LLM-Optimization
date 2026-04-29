"""Output-equivalence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from vallmopt.logging.schema import VerifyGateResult
from vallmopt.utils.subprocess import command_to_string, run_command
from vallmopt.utils.tools import find_executable
from vallmopt.verify.compile import build_gcc_command
from vallmopt.verify.runtime import build_run_command


TIMING_LINE_MARKERS = [
    "time in seconds",
    "polybench_time",
    "cycles",
]


def compare_text_outputs(reference_output: str, candidate_output: str) -> VerifyGateResult:
    """Compare captured reference and candidate stdout exactly."""

    if reference_output == candidate_output:
        return VerifyGateResult(gate_name="output", status="pass")
    return VerifyGateResult(
        gate_name="output",
        status="fail",
        failure_reason="candidate stdout differs from reference stdout",
    )


def normalize_output_text(text: str, *, ignore_timing: bool = True) -> str:
    """Normalize textual program output for deterministic exact comparison."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = normalized.splitlines()
    if ignore_timing:
        lines = [
            line.rstrip()
            for line in lines
            if not _looks_like_timing_line(line)
        ]
    else:
        lines = [line.rstrip() for line in lines]
    return "\n".join(lines).strip()


def select_output_stream(
    *,
    stdout: str,
    stderr: str,
    compare_stream: str,
    ignore_timing: bool = True,
) -> tuple[str, str]:
    """Select and normalize stdout/stderr/combined output for comparison."""

    if compare_stream not in {"auto", "stdout", "stderr", "combined"}:
        raise ValueError("compare_stream must be one of: auto, stdout, stderr, combined")
    stdout_norm = normalize_output_text(stdout, ignore_timing=ignore_timing)
    stderr_norm = normalize_output_text(stderr, ignore_timing=ignore_timing)
    if compare_stream == "stdout":
        return "stdout", stdout_norm
    if compare_stream == "stderr":
        return "stderr", stderr_norm
    if compare_stream == "combined":
        return "combined", normalize_output_text(f"{stdout}\n{stderr}", ignore_timing=ignore_timing)
    if stderr_norm:
        return "stderr", stderr_norm
    return "stdout", stdout_norm


def compare_program_outputs(
    *,
    reference_stdout: str,
    reference_stderr: str,
    candidate_stdout: str,
    candidate_stderr: str,
    compare_stream: str = "auto",
    ignore_timing: bool = True,
) -> tuple[VerifyGateResult, str]:
    """Compare selected normalized streams from two program runs."""

    stream, reference_output = select_output_stream(
        stdout=reference_stdout,
        stderr=reference_stderr,
        compare_stream=compare_stream,
        ignore_timing=ignore_timing,
    )
    candidate_stream, candidate_output = select_output_stream(
        stdout=candidate_stdout,
        stderr=candidate_stderr,
        compare_stream=stream if compare_stream == "auto" else compare_stream,
        ignore_timing=ignore_timing,
    )
    if stream != candidate_stream:
        return (
            VerifyGateResult(
                gate_name="output",
                status="fail",
                failure_reason=f"selected different output streams: reference={stream}, candidate={candidate_stream}",
            ),
            stream,
        )
    if reference_output == candidate_output:
        return VerifyGateResult(gate_name="output", status="pass"), stream
    return (
        VerifyGateResult(
            gate_name="output",
            status="fail",
            failure_reason=f"candidate {stream} differs from reference {stream} after normalization",
            stdout=candidate_output,
            stderr=reference_output,
        ),
        stream,
    )


def _looks_like_timing_line(line: str) -> bool:
    lowered = line.strip().lower()
    if any(marker in lowered for marker in TIMING_LINE_MARKERS):
        return True
    return lowered.startswith("==") and "timer" in lowered


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
    if find_executable(compiler) is None:
        return VerifyGateResult(
            gate_name="output",
            status="fail",
            command=command_text,
            failure_reason=f"compiler not found on PATH: {compiler}",
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
