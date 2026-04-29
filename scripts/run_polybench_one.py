from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vallmopt.analysis.summarize import summarize_records, write_summary  # noqa: E402
from vallmopt.arch import get_architecture, load_architectures  # noqa: E402
from vallmopt.benchmark.runner import benchmark_commands  # noqa: E402
from vallmopt.build.polybench import (  # noqa: E402
    DEFAULT_POLYBENCH_CFLAGS,
    PolyBenchBuildSpec,
    construct_polybench_compile_command,
    make_polybench_build_spec,
)
from vallmopt.config import load_yaml  # noqa: E402
from vallmopt.datasets.polybench import PolyBenchKernel, get_polybench_kernel, load_polybench_config  # noqa: E402
from vallmopt.generation import MockGenerator  # noqa: E402
from vallmopt.logging.jsonl import append_jsonl  # noqa: E402
from vallmopt.logging.schema import CandidateRecord, VerifyGateResult, VerifyRecord, git_commit, to_jsonable  # noqa: E402
from vallmopt.prompts import PromptBuilder  # noqa: E402
from vallmopt.utils.hashing import sha256_file, sha256_text  # noqa: E402
from vallmopt.utils.paths import ensure_dir  # noqa: E402
from vallmopt.utils.subprocess import CommandResult, command_to_string, run_command  # noqa: E402
from vallmopt.utils.tools import find_executable  # noqa: E402
from vallmopt.verify.output import compare_program_outputs  # noqa: E402
from vallmopt.verify.runtime import build_run_command  # noqa: E402
from vallmopt.verify.safety import check_safety_file  # noqa: E402


DATASET_SIZES = ["MINI", "SMALL", "MEDIUM", "LARGE", "EXTRALARGE"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a one-kernel PolyBench/C workflow.")
    parser.add_argument("--polybench-root", required=True, type=Path)
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--arch-tag", required=True)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--size", default="LARGE", choices=DATASET_SIZES)
    parser.add_argument("--mode", default="verify", choices=["verify", "benchmark"])
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--cflags-extra", action="append", default=[], help="Extra compiler flags, shell-split.")
    parser.add_argument("--compare-stream", default="auto", choices=["auto", "stdout", "stderr", "combined"])
    parser.add_argument("--dump-arrays", dest="dump_arrays", action="store_true", default=None)
    parser.add_argument("--no-dump-arrays", dest="dump_arrays", action="store_false")
    parser.add_argument("--polybench-config", default=REPO_ROOT / "configs" / "polybench.default.yaml", type=Path)
    parser.add_argument("--arch-config", default=REPO_ROOT / "configs" / "architectures.yaml", type=Path)
    parser.add_argument("--prompt-config", default=REPO_ROOT / "configs" / "prompts.default.yaml", type=Path)
    parser.add_argument("--verify-config", default=REPO_ROOT / "configs" / "verify.default.yaml", type=Path)
    parser.add_argument("--benchmark-repeats", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    work_dir = ensure_dir(args.work_dir)

    try:
        polybench_config = load_polybench_config(args.polybench_config)
        architecture = get_architecture(args.arch_config, args.arch_tag)
        architectures = load_architectures(args.arch_config)
        prompt_config = load_yaml(args.prompt_config)
        verify_config = load_yaml(args.verify_config)
        kernel = get_polybench_kernel(
            args.polybench_root,
            args.kernel,
            polybench_config,
            size=args.size,
        )
    except (FileNotFoundError, KeyError, NotADirectoryError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    reference_code = kernel.source_path.read_text(encoding="utf-8")
    prompt = PromptBuilder(architectures).build_prompt(
        kernel_name=args.kernel,
        arch_tag=args.arch_tag,
        reference_c_code=reference_code,
        allowed_transformations=prompt_config.get("allowed_transformations"),
        safety_constraints=prompt_config.get("safety_constraints"),
        output_constraints=prompt_config.get("output_constraints"),
    )
    prompt_path = work_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    prompt_hash = sha256_text(prompt)

    if args.candidate is None:
        generated = MockGenerator().generate(
            prompt=prompt,
            kernel_name=args.kernel,
            arch_tag=args.arch_tag,
            reference_c_code=reference_code,
        )
        candidate_code = generated.candidate_c_code
        generator_name = str(generated.metadata.get("generator", "mock"))
        candidate_metadata: dict[str, Any] = dict(generated.metadata)
    else:
        if not args.candidate.exists():
            print(f"Candidate file not found: {args.candidate}", file=sys.stderr)
            return 1
        candidate_code = args.candidate.read_text(encoding="utf-8")
        generator_name = "provided"
        candidate_metadata = {"source_path": str(args.candidate)}

    candidate_path = work_dir / "candidate.c"
    candidate_path.write_text(candidate_code, encoding="utf-8")

    candidate_record = CandidateRecord(
        kernel_name=args.kernel,
        arch_tag=args.arch_tag,
        isa=architecture.isa,
        generator_name=generator_name,
        prompt_hash=prompt_hash,
        reference_code_hash=sha256_file(kernel.source_path),
        candidate_code_hash=sha256_file(candidate_path),
        status="pass",
        git_commit=git_commit(REPO_ROOT),
        config_path=str(args.polybench_config),
        prompt_path=str(prompt_path),
        candidate_path=str(candidate_path),
        metadata={
            **candidate_metadata,
            "dataset": "polybench",
            "polybench_source_path": str(kernel.source_path),
            "polybench_category": kernel.category,
        },
    )
    candidate_json = to_jsonable(candidate_record)
    (work_dir / "candidate_record.json").write_text(
        json.dumps(candidate_json, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    append_jsonl(work_dir / "candidates.jsonl", candidate_record)

    dump_arrays = args.dump_arrays if args.dump_arrays is not None else args.mode == "verify"
    build_mode = "verify" if dump_arrays else "benchmark"
    cflags = _merge_flags(DEFAULT_POLYBENCH_CFLAGS, architecture.cflags_extra, _split_cflags(args.cflags_extra))
    suffix = ".exe" if os.name == "nt" else ""
    polybench_root = Path(args.polybench_root).expanduser().resolve()
    reference_spec = make_polybench_build_spec(
        polybench_root=polybench_root,
        kernel=kernel,
        source_path=kernel.source_path,
        output_path=work_dir / f"reference{suffix}",
        size=args.size,
        mode=build_mode,
        compiler=args.compiler,
        cflags=cflags,
    )
    candidate_spec = make_polybench_build_spec(
        polybench_root=polybench_root,
        kernel=kernel,
        source_path=candidate_path,
        output_path=work_dir / f"candidate{suffix}",
        size=args.size,
        mode=build_mode,
        compiler=args.compiler,
        cflags=cflags,
    )

    verify_record = _run_polybench_verification(
        kernel_name=args.kernel,
        arch_tag=args.arch_tag,
        isa=architecture.isa,
        reference_path=kernel.source_path,
        candidate_path=candidate_path,
        reference_spec=reference_spec,
        candidate_spec=candidate_spec,
        kernel=kernel,
        work_dir=work_dir,
        prompt_hash=prompt_hash,
        generator_name=generator_name,
        config_path=str(args.verify_config),
        verify_config=verify_config,
        dry_run=args.dry_run,
        compare_stream=args.compare_stream,
        dump_arrays=dump_arrays,
        mode=args.mode,
    )
    verify_json = to_jsonable(verify_record)
    (work_dir / "verify_record.json").write_text(
        json.dumps(verify_json, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    append_jsonl(work_dir / "verify.jsonl", verify_record)

    records_for_summary = [candidate_json, verify_json]
    benchmark_record = None
    if not args.skip_benchmark and not args.dry_run and not _has_failed_gate(verify_record):
        benchmark_record = benchmark_commands(
            baseline_cmd=str(reference_spec.executable_path),
            candidate_cmd=str(candidate_spec.executable_path),
            repeats=args.benchmark_repeats,
            kernel_name=args.kernel,
            arch_tag=args.arch_tag,
            isa=architecture.isa,
            generator_name=generator_name,
        )
        benchmark_json = to_jsonable(benchmark_record)
        (work_dir / "benchmark_record.json").write_text(
            json.dumps(benchmark_json, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        append_jsonl(work_dir / "benchmark.jsonl", benchmark_record)
        records_for_summary.append(benchmark_json)

    summary = summarize_records(records_for_summary)
    summary.update(
        {
            "dataset": "polybench",
            "kernel": args.kernel,
            "mode": args.mode,
            "size": args.size,
            "dump_arrays": dump_arrays,
            "compare_stream_requested": args.compare_stream,
            "compare_stream_used": verify_record.metadata.get("compare_stream_used"),
            "polybench_root": str(polybench_root),
            "polybench_source_path": str(kernel.source_path),
            "prompt_path": str(prompt_path),
            "candidate_path": str(candidate_path),
            "candidate_log": str(work_dir / "candidates.jsonl"),
            "verify_log": str(work_dir / "verify.jsonl"),
            "benchmark_log": str(work_dir / "benchmark.jsonl") if benchmark_record else None,
            "reference_build_spec": _build_spec_json(reference_spec),
            "candidate_build_spec": _build_spec_json(candidate_spec),
            "tools": {
                "gcc": find_executable("gcc"),
                "clang": find_executable("clang"),
                "hyperfine": find_executable("hyperfine"),
                "perf": find_executable("perf"),
            },
        }
    )
    write_summary(work_dir / "summary.json", summary)

    print(f"PolyBench one-kernel workflow: {args.kernel} on {args.arch_tag}")
    print(f"PolyBench source: {kernel.source_path}")
    print(f"Prompt: {prompt_path}")
    print(f"Candidate: {candidate_path}")
    print(f"Verify status: {verify_record.status}")
    if verify_record.failure_reason:
        print(f"Failure reason: {verify_record.failure_reason}")
    for gate in verify_record.gates:
        detail = f" ({gate.failure_reason})" if gate.failure_reason else ""
        print(f"  - {gate.gate_name}: {gate.status}{detail}")
    if verify_record.metadata.get("compare_stream_used"):
        print(f"Compared stream: {verify_record.metadata['compare_stream_used']}")
    if benchmark_record is not None:
        print(f"Benchmark status: {benchmark_record.status}")
    elif args.skip_benchmark:
        print("Benchmark: skipped by request")
    else:
        print("Benchmark: skipped")
    print(f"Logs: {work_dir}")

    if verify_record.status == "fail" and not args.keep_going:
        return 1
    return 0


def _run_polybench_verification(
    *,
    kernel_name: str,
    arch_tag: str,
    isa: str,
    reference_path: Path,
    candidate_path: Path,
    reference_spec: PolyBenchBuildSpec,
    candidate_spec: PolyBenchBuildSpec,
    kernel: PolyBenchKernel,
    work_dir: Path,
    prompt_hash: str,
    generator_name: str,
    config_path: str,
    verify_config: dict[str, Any],
    dry_run: bool,
    compare_stream: str,
    dump_arrays: bool,
    mode: str,
) -> VerifyRecord:
    gates: list[VerifyGateResult] = []
    compare_stream_used: str | None = None

    compile_gate = _compile_polybench_pair(reference_spec, candidate_spec, dry_run=dry_run)
    gates.append(compile_gate)
    reference_run: CommandResult | None = None
    candidate_run: CommandResult | None = None

    if compile_gate.status == "fail":
        gates.extend(_skipped_after_failure("runtime", "output", "sanitizer", "safety"))
    else:
        runtime_gate, reference_run, candidate_run = _run_polybench_pair(
            reference_spec,
            candidate_spec,
            run_args=kernel.run_args,
            timeout_sec=float(verify_config.get("runtime", {}).get("timeout_sec", 10)),
            dry_run=dry_run,
        )
        gates.append(runtime_gate)

        if runtime_gate.status == "fail":
            gates.extend(_skipped_after_failure("output", "sanitizer", "safety"))
        else:
            if not dump_arrays or mode != "verify":
                output_gate = VerifyGateResult(
                    gate_name="output",
                    status="skipped",
                    failure_reason="dumped output comparison disabled outside verify mode",
                )
            elif reference_run is None or candidate_run is None:
                output_gate = VerifyGateResult(
                    gate_name="output",
                    status="skipped",
                    failure_reason="dry-run",
                )
            else:
                output_gate, compare_stream_used = compare_program_outputs(
                    reference_stdout=reference_run.stdout,
                    reference_stderr=reference_run.stderr,
                    candidate_stdout=candidate_run.stdout,
                    candidate_stderr=candidate_run.stderr,
                    compare_stream=compare_stream,
                    ignore_timing=True,
                )
                output_gate.command = f"compare normalized {compare_stream_used}"
                output_gate.elapsed_sec = 0.0
            gates.append(output_gate)

            if output_gate.status == "fail":
                gates.extend(_skipped_after_failure("sanitizer", "safety"))
            else:
                sanitizer_gate = _run_polybench_sanitizer_gate(
                    candidate_spec,
                    verify_config=verify_config,
                    run_args=kernel.run_args,
                    dry_run=dry_run,
                )
                gates.append(sanitizer_gate)

                if sanitizer_gate.status == "fail":
                    gates.extend(_skipped_after_failure("safety"))
                else:
                    gates.append(check_safety_file(candidate_path))

    status, failure_reason = _overall_status(gates)
    return VerifyRecord(
        kernel_name=kernel_name,
        arch_tag=arch_tag,
        isa=isa,
        generator_name=generator_name,
        prompt_hash=prompt_hash,
        reference_code_hash=sha256_file(reference_path),
        candidate_code_hash=sha256_file(candidate_path),
        status=status,
        gates=gates,
        git_commit=git_commit(REPO_ROOT),
        config_path=config_path,
        failure_reason=failure_reason,
        work_dir=str(work_dir),
        compiler_flags=candidate_spec.cflags,
        metadata={
            "dry_run": dry_run,
            "polybench_build_glue": "implemented",
            "compare_stream_requested": compare_stream,
            "compare_stream_used": compare_stream_used,
            "dump_arrays": dump_arrays,
            "mode": mode,
        },
    )


def _compile_polybench_pair(
    reference_spec: PolyBenchBuildSpec,
    candidate_spec: PolyBenchBuildSpec,
    *,
    dry_run: bool,
) -> VerifyGateResult:
    reference_command = construct_polybench_compile_command(reference_spec)
    candidate_command = construct_polybench_compile_command(candidate_spec)
    command_text = f"{command_to_string(reference_command)} && {command_to_string(candidate_command)}"
    if dry_run:
        return VerifyGateResult(
            gate_name="compile",
            status="skipped",
            command=command_text,
            failure_reason="dry-run",
        )
    if find_executable(reference_spec.compiler) is None:
        return VerifyGateResult(
            gate_name="compile",
            status="fail",
            command=command_text,
            failure_reason=f"compiler not found on PATH: {reference_spec.compiler}",
        )
    reference_result = run_command(reference_command)
    if reference_result.returncode != 0:
        return VerifyGateResult(
            gate_name="compile",
            status="fail",
            command=command_text,
            stdout=reference_result.stdout,
            stderr=reference_result.stderr,
            elapsed_sec=reference_result.elapsed_sec,
            failure_reason=f"reference compiler exited with status {reference_result.returncode}",
        )
    candidate_result = run_command(candidate_command)
    elapsed = reference_result.elapsed_sec + candidate_result.elapsed_sec
    if candidate_result.returncode != 0:
        return VerifyGateResult(
            gate_name="compile",
            status="fail",
            command=command_text,
            stdout=candidate_result.stdout,
            stderr=candidate_result.stderr,
            elapsed_sec=elapsed,
            failure_reason=f"candidate compiler exited with status {candidate_result.returncode}",
        )
    return VerifyGateResult(
        gate_name="compile",
        status="pass",
        command=command_text,
        stdout=f"{reference_result.stdout}{candidate_result.stdout}",
        stderr=f"{reference_result.stderr}{candidate_result.stderr}",
        elapsed_sec=elapsed,
    )


def _run_polybench_pair(
    reference_spec: PolyBenchBuildSpec,
    candidate_spec: PolyBenchBuildSpec,
    *,
    run_args: list[str],
    timeout_sec: float,
    dry_run: bool,
) -> tuple[VerifyGateResult, CommandResult | None, CommandResult | None]:
    reference_command = build_run_command(reference_spec.executable_path or "reference", run_args)
    candidate_command = build_run_command(candidate_spec.executable_path or "candidate", run_args)
    command_text = f"{command_to_string(reference_command)} && {command_to_string(candidate_command)}"
    if dry_run:
        return (
            VerifyGateResult(
                gate_name="runtime",
                status="skipped",
                command=command_text,
                failure_reason="dry-run",
            ),
            None,
            None,
        )

    reference_result = run_command(reference_command, timeout_sec=timeout_sec)
    if reference_result.timed_out or reference_result.returncode != 0:
        reason = (
            f"reference runtime exceeded timeout of {timeout_sec} seconds"
            if reference_result.timed_out
            else f"reference binary exited with status {reference_result.returncode}"
        )
        return (
            VerifyGateResult(
                gate_name="runtime",
                status="fail",
                command=command_text,
                stdout=reference_result.stdout,
                stderr=reference_result.stderr,
                elapsed_sec=reference_result.elapsed_sec,
                failure_reason=reason,
            ),
            reference_result,
            None,
        )

    candidate_result = run_command(candidate_command, timeout_sec=timeout_sec)
    elapsed = reference_result.elapsed_sec + candidate_result.elapsed_sec
    if candidate_result.timed_out or candidate_result.returncode != 0:
        reason = (
            f"candidate runtime exceeded timeout of {timeout_sec} seconds"
            if candidate_result.timed_out
            else f"candidate binary exited with status {candidate_result.returncode}"
        )
        return (
            VerifyGateResult(
                gate_name="runtime",
                status="fail",
                command=command_text,
                stdout=candidate_result.stdout,
                stderr=candidate_result.stderr,
                elapsed_sec=elapsed,
                failure_reason=reason,
            ),
            reference_result,
            candidate_result,
        )

    return (
        VerifyGateResult(
            gate_name="runtime",
            status="pass",
            command=command_text,
            stdout=candidate_result.stdout,
            stderr=candidate_result.stderr,
            elapsed_sec=elapsed,
        ),
        reference_result,
        candidate_result,
    )


def _run_polybench_sanitizer_gate(
    candidate_spec: PolyBenchBuildSpec,
    *,
    verify_config: dict[str, Any],
    run_args: list[str],
    dry_run: bool,
) -> VerifyGateResult:
    sanitizer_cfg = verify_config.get("sanitizer", {})
    compiler = str(sanitizer_cfg.get("compiler", "clang"))
    required = bool(sanitizer_cfg.get("required", False))
    skip_if_unavailable = bool(sanitizer_cfg.get("skip_if_unavailable", True))
    skip_on_windows = bool(sanitizer_cfg.get("skip_on_windows", True))
    cflags = _merge_flags(["-std=c99"], list(sanitizer_cfg.get("cflags", [])))
    ldflags = list(sanitizer_cfg.get("ldflags", []))
    sanitizer_spec = replace(
        candidate_spec,
        compiler=compiler,
        cflags=cflags,
        ldflags=ldflags,
        executable_path=candidate_spec.executable_path.with_name(f"{candidate_spec.executable_path.stem}_san{candidate_spec.executable_path.suffix}")
        if candidate_spec.executable_path is not None
        else None,
    )
    compile_command = construct_polybench_compile_command(sanitizer_spec)
    run_text = build_run_command(sanitizer_spec.executable_path or "candidate_san", run_args)
    command_text = f"{command_to_string(compile_command)} && {command_to_string(run_text)}"
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
    if compile_result.returncode != 0:
        return VerifyGateResult(
            gate_name="sanitizer",
            status="fail",
            command=command_text,
            stdout=compile_result.stdout,
            stderr=compile_result.stderr,
            elapsed_sec=compile_result.elapsed_sec,
            failure_reason=f"sanitizer compiler exited with status {compile_result.returncode}",
        )
    runtime_result = run_command(run_text, timeout_sec=float(verify_config.get("runtime", {}).get("timeout_sec", 10)))
    elapsed = compile_result.elapsed_sec + runtime_result.elapsed_sec
    if runtime_result.timed_out:
        return VerifyGateResult(
            gate_name="sanitizer",
            status="fail",
            command=command_text,
            stdout=runtime_result.stdout,
            stderr=runtime_result.stderr,
            elapsed_sec=elapsed,
            failure_reason=f"sanitizer runtime exceeded timeout of {verify_config.get('runtime', {}).get('timeout_sec', 10)} seconds",
        )
    if runtime_result.returncode != 0:
        return VerifyGateResult(
            gate_name="sanitizer",
            status="fail",
            command=command_text,
            stdout=runtime_result.stdout,
            stderr=runtime_result.stderr,
            elapsed_sec=elapsed,
            failure_reason=f"sanitizer binary exited with status {runtime_result.returncode}",
        )
    return VerifyGateResult(
        gate_name="sanitizer",
        status="pass",
        command=command_text,
        stdout=runtime_result.stdout,
        stderr=runtime_result.stderr,
        elapsed_sec=elapsed,
    )


def _skipped_after_failure(*gate_names: str) -> list[VerifyGateResult]:
    return [
        VerifyGateResult(
            gate_name=gate_name,
            status="skipped",
            failure_reason="previous gate failed",
        )
        for gate_name in gate_names
    ]


def _overall_status(gates: list[VerifyGateResult]) -> tuple[str, str | None]:
    for gate in gates:
        if gate.status == "fail":
            return "fail", gate.failure_reason
    skipped = [gate for gate in gates if gate.status == "skipped"]
    optional_skips = [
        gate
        for gate in skipped
        if gate.gate_name == "sanitizer"
        and (
            (gate.failure_reason or "").startswith("optional sanitizer compiler not available")
            or (gate.failure_reason or "") == "optional sanitizer gate skipped on Windows"
        )
    ]
    if skipped and len(optional_skips) != len(skipped):
        return "skipped", "one or more gates were skipped"
    return "pass", None


def _has_failed_gate(record: VerifyRecord) -> bool:
    return any(gate.status == "fail" for gate in record.gates)


def _split_cflags(values: list[str]) -> list[str]:
    flags: list[str] = []
    for value in values:
        flags.extend(shlex.split(value))
    return flags


def _merge_flags(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for flag in group:
            if flag not in merged:
                merged.append(flag)
    return merged


def _build_spec_json(spec: PolyBenchBuildSpec) -> dict[str, Any]:
    return {
        "source_path": str(spec.source_path),
        "utility_sources": [str(path) for path in spec.utility_sources],
        "include_dirs": [str(path) for path in spec.include_dirs],
        "defines": spec.defines,
        "cflags": spec.cflags,
        "ldflags": spec.ldflags,
        "executable_path": str(spec.executable_path) if spec.executable_path else None,
        "compiler": spec.compiler,
        "command": command_to_string(construct_polybench_compile_command(spec)),
    }


if __name__ == "__main__":
    raise SystemExit(main())
