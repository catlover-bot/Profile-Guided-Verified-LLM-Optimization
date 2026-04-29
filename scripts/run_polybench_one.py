from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vallmopt.analysis.summarize import summarize_records, write_summary  # noqa: E402
from vallmopt.arch import get_architecture, load_architectures  # noqa: E402
from vallmopt.benchmark.runner import benchmark_commands  # noqa: E402
from vallmopt.build.cbuild import construct_gcc_command  # noqa: E402
from vallmopt.build.polybench import PolyBenchBuildSpec  # noqa: E402
from vallmopt.config import load_yaml  # noqa: E402
from vallmopt.datasets.polybench import get_polybench_kernel, load_polybench_config  # noqa: E402
from vallmopt.generation import MockGenerator  # noqa: E402
from vallmopt.logging.jsonl import append_jsonl  # noqa: E402
from vallmopt.logging.schema import CandidateRecord, VerifyGateResult, VerifyRecord, git_commit, to_jsonable  # noqa: E402
from vallmopt.prompts import PromptBuilder  # noqa: E402
from vallmopt.utils.hashing import sha256_file, sha256_text  # noqa: E402
from vallmopt.utils.paths import ensure_dir  # noqa: E402
from vallmopt.utils.subprocess import command_to_string  # noqa: E402
from vallmopt.utils.tools import find_executable  # noqa: E402
from vallmopt.verify.pipeline import VerifyPipeline  # noqa: E402
from vallmopt.verify.safety import check_safety_file  # noqa: E402


POLYBENCH_BUILD_SKIP_REASON = "polybench build glue not implemented yet"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a one-kernel PolyBench/C infrastructure workflow.")
    parser.add_argument("--polybench-root", required=True, type=Path)
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--arch-tag", required=True)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--size", default=None, choices=["MINI", "SMALL", "MEDIUM", "LARGE", "EXTRALARGE"])
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

    compiler_flags = _polybench_compiler_flags(kernel, architecture.cflags_extra)
    build_spec = PolyBenchBuildSpec(
        source_path=candidate_path,
        include_dirs=kernel.extra_include_dirs,
        defines=kernel.compile_defines,
        cflags=architecture.cflags_extra,
        executable_path=work_dir / ("candidate.exe" if os.name == "nt" else "candidate"),
    )

    if _needs_full_polybench_build_glue(reference_code, kernel.name):
        verify_record = _build_glue_skipped_verify_record(
            kernel_name=args.kernel,
            arch_tag=args.arch_tag,
            isa=architecture.isa,
            reference_path=kernel.source_path,
            candidate_path=candidate_path,
            work_dir=work_dir,
            prompt_hash=prompt_hash,
            generator_name=generator_name,
            config_path=str(args.verify_config),
            compiler_flags=compiler_flags,
            build_spec=build_spec,
            dry_run=args.dry_run,
        )
    else:
        verify_record = VerifyPipeline(verify_config, dry_run=args.dry_run).run(
            kernel_name=args.kernel,
            arch_tag=args.arch_tag,
            isa=architecture.isa,
            reference_path=kernel.source_path,
            candidate_path=candidate_path,
            work_dir=work_dir,
            compiler_flags=compiler_flags,
            runtime_args=kernel.run_args,
            prompt_hash=prompt_hash,
            generator_name=generator_name,
            config_path=str(args.verify_config),
        )

    verify_json = to_jsonable(verify_record)
    (work_dir / "verify_record.json").write_text(
        json.dumps(verify_json, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    append_jsonl(work_dir / "verify.jsonl", verify_record)

    records_for_summary = [candidate_json, verify_json]
    benchmark_record = None
    if not args.skip_benchmark and verify_record.status == "pass" and not args.dry_run:
        suffix = ".exe" if os.name == "nt" else ""
        benchmark_record = benchmark_commands(
            baseline_cmd=str(work_dir / f"reference{suffix}"),
            candidate_cmd=str(work_dir / f"candidate{suffix}"),
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
            "polybench_root": str(Path(args.polybench_root).expanduser().resolve()),
            "polybench_source_path": str(kernel.source_path),
            "prompt_path": str(prompt_path),
            "candidate_path": str(candidate_path),
            "candidate_log": str(work_dir / "candidates.jsonl"),
            "verify_log": str(work_dir / "verify.jsonl"),
            "benchmark_log": str(work_dir / "benchmark.jsonl") if benchmark_record else None,
            "build_spec": _build_spec_json(build_spec),
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


def _polybench_compiler_flags(kernel: Any, arch_flags: list[str]) -> list[str]:
    flags: list[str] = []
    for include_dir in kernel.extra_include_dirs:
        flags.extend(["-I", str(include_dir)])
    for define in kernel.compile_defines:
        flags.append(define if str(define).startswith("-D") else f"-D{define}")
    flags.extend(arch_flags)
    return flags


def _needs_full_polybench_build_glue(source_text: str, kernel_name: str) -> bool:
    markers = [
        "polybench.h",
        "polybench_alloc_data",
        "polybench_free_data",
        "POLYBENCH_",
        f'"{kernel_name}.h"',
        f"<{kernel_name}.h>",
    ]
    return any(marker in source_text for marker in markers)


def _build_glue_skipped_verify_record(
    *,
    kernel_name: str,
    arch_tag: str,
    isa: str,
    reference_path: Path,
    candidate_path: Path,
    work_dir: Path,
    prompt_hash: str,
    generator_name: str,
    config_path: str,
    compiler_flags: list[str],
    build_spec: PolyBenchBuildSpec,
    dry_run: bool,
) -> VerifyRecord:
    compile_command = construct_gcc_command(
        source=build_spec.source_path,
        output=build_spec.executable_path or work_dir / "candidate",
        include_dirs=build_spec.include_dirs,
        defines=build_spec.defines,
        cflags=build_spec.cflags,
        ldflags=build_spec.ldflags,
    )
    gates = [
        VerifyGateResult(
            gate_name="compile",
            status="skipped",
            command=command_to_string(compile_command),
            failure_reason=POLYBENCH_BUILD_SKIP_REASON,
        ),
        VerifyGateResult(
            gate_name="runtime",
            status="skipped",
            failure_reason=POLYBENCH_BUILD_SKIP_REASON,
        ),
        VerifyGateResult(
            gate_name="output",
            status="skipped",
            failure_reason=POLYBENCH_BUILD_SKIP_REASON,
        ),
        VerifyGateResult(
            gate_name="sanitizer",
            status="skipped",
            failure_reason=POLYBENCH_BUILD_SKIP_REASON,
        ),
        check_safety_file(candidate_path),
    ]
    safety_gate = gates[-1]
    status = "fail" if safety_gate.status == "fail" else "skipped"
    failure_reason = safety_gate.failure_reason if safety_gate.status == "fail" else POLYBENCH_BUILD_SKIP_REASON
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
        compiler_flags=compiler_flags,
        metadata={
            "dry_run": dry_run,
            "polybench_build_glue": "not_implemented",
        },
    )


def _build_spec_json(spec: PolyBenchBuildSpec) -> dict[str, Any]:
    return {
        "source_path": str(spec.source_path),
        "include_dirs": [str(path) for path in spec.include_dirs],
        "defines": spec.defines,
        "cflags": spec.cflags,
        "ldflags": spec.ldflags,
        "executable_path": str(spec.executable_path) if spec.executable_path else None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
