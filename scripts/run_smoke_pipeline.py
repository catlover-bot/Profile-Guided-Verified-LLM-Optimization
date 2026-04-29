from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vallmopt.analysis.summarize import summarize_records, write_summary  # noqa: E402
from vallmopt.arch import get_architecture, load_architectures  # noqa: E402
from vallmopt.benchmark.runner import benchmark_commands  # noqa: E402
from vallmopt.config import load_yaml  # noqa: E402
from vallmopt.generation import MockGenerator  # noqa: E402
from vallmopt.logging.jsonl import append_jsonl  # noqa: E402
from vallmopt.logging.schema import CandidateRecord, git_commit, to_jsonable  # noqa: E402
from vallmopt.prompts import PromptBuilder  # noqa: E402
from vallmopt.utils.hashing import sha256_file, sha256_text  # noqa: E402
from vallmopt.utils.paths import ensure_dir  # noqa: E402
from vallmopt.utils.tools import find_executable  # noqa: E402
from vallmopt.verify.pipeline import VerifyPipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local end-to-end smoke workflow on a toy C kernel.")
    parser.add_argument("--kernel", required=True, help="Toy kernel name under examples/kernels.")
    parser.add_argument("--arch-tag", required=True)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--candidate", type=Path, help="Optional candidate C file. Defaults to MockGenerator output.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--benchmark-repeats", type=int, default=3)
    parser.add_argument("--architectures", default=REPO_ROOT / "configs" / "architectures.yaml", type=Path)
    parser.add_argument("--prompt-config", default=REPO_ROOT / "configs" / "prompts.default.yaml", type=Path)
    parser.add_argument("--verify-config", default=REPO_ROOT / "configs" / "verify.default.yaml", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    work_dir = ensure_dir(args.work_dir)
    kernel_dir = REPO_ROOT / "examples" / "kernels" / args.kernel
    reference_path = kernel_dir / "reference.c"
    if not reference_path.exists():
        print(f"Toy kernel reference not found: {reference_path}", file=sys.stderr)
        return 1

    architecture = get_architecture(args.architectures, args.arch_tag)
    architectures = load_architectures(args.architectures)
    prompt_config = load_yaml(args.prompt_config)
    verify_config = load_yaml(args.verify_config)

    reference_code = reference_path.read_text(encoding="utf-8")
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
        candidate_source = None
        candidate_metadata = generated.metadata
    else:
        if not args.candidate.exists():
            print(f"Candidate file not found: {args.candidate}", file=sys.stderr)
            return 1
        candidate_code = args.candidate.read_text(encoding="utf-8")
        generator_name = "provided"
        candidate_source = str(args.candidate)
        candidate_metadata = {"source_path": candidate_source}

    candidate_path = work_dir / "candidate.c"
    candidate_path.write_text(candidate_code, encoding="utf-8")

    candidate_record = CandidateRecord(
        kernel_name=args.kernel,
        arch_tag=args.arch_tag,
        isa=architecture.isa,
        generator_name=generator_name,
        prompt_hash=prompt_hash,
        reference_code_hash=sha256_file(reference_path),
        candidate_code_hash=sha256_file(candidate_path),
        status="pass",
        git_commit=git_commit(REPO_ROOT),
        config_path=str(args.prompt_config),
        prompt_path=str(prompt_path),
        candidate_path=str(candidate_path),
        metadata=candidate_metadata,
    )
    candidate_json = to_jsonable(candidate_record)
    (work_dir / "candidate_record.json").write_text(
        json.dumps(candidate_json, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    append_jsonl(work_dir / "candidates.jsonl", candidate_record)

    verify_record = VerifyPipeline(verify_config, dry_run=args.dry_run).run(
        kernel_name=args.kernel,
        arch_tag=args.arch_tag,
        isa=architecture.isa,
        reference_path=reference_path,
        candidate_path=candidate_path,
        work_dir=work_dir,
        compiler_flags=architecture.cflags_extra,
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
        baseline_binary = work_dir / f"reference{suffix}"
        candidate_binary = work_dir / f"candidate{suffix}"
        benchmark_record = benchmark_commands(
            baseline_cmd=str(baseline_binary),
            candidate_cmd=str(candidate_binary),
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
    summary["prompt_path"] = str(prompt_path)
    summary["candidate_path"] = str(candidate_path)
    summary["candidate_log"] = str(work_dir / "candidates.jsonl")
    summary["verify_log"] = str(work_dir / "verify.jsonl")
    summary["benchmark_log"] = str(work_dir / "benchmark.jsonl") if benchmark_record else None
    summary["tools"] = {
        "gcc": find_executable("gcc"),
        "clang": find_executable("clang"),
        "hyperfine": find_executable("hyperfine"),
        "perf": find_executable("perf"),
    }
    write_summary(work_dir / "summary.json", summary)

    print(f"Smoke pipeline: {args.kernel} on {args.arch_tag}")
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
        if benchmark_record.speedup is not None:
            print(f"Speedup: {benchmark_record.speedup:.3f}x")
    elif args.skip_benchmark:
        print("Benchmark: skipped by request")
    else:
        print("Benchmark: skipped")
    print(f"Logs: {work_dir}")

    if verify_record.status == "fail" and not args.keep_going:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
