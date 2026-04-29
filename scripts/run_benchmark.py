from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vallmopt.benchmark.hyperfine import HyperfineCommandBuilder  # noqa: E402
from vallmopt.benchmark.perf import PerfCommandBuilder  # noqa: E402
from vallmopt.benchmark.runner import benchmark_commands  # noqa: E402
from vallmopt.logging.jsonl import append_jsonl  # noqa: E402
from vallmopt.logging.schema import to_jsonable  # noqa: E402
from vallmopt.utils.paths import ensure_parent  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or prepare repeated benchmark measurements.")
    parser.add_argument("--baseline-cmd", required=True)
    parser.add_argument("--candidate-cmd", required=True)
    parser.add_argument("--repeats", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--kernel-name", default="unknown")
    parser.add_argument("--arch-tag", default="unknown")
    parser.add_argument("--isa", default="unknown")
    parser.add_argument("--generator-name")
    parser.add_argument("--timeout-sec", type=float)
    parser.add_argument("--log-jsonl", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show-wrappers", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    record = benchmark_commands(
        baseline_cmd=args.baseline_cmd,
        candidate_cmd=args.candidate_cmd,
        repeats=args.repeats,
        kernel_name=args.kernel_name,
        arch_tag=args.arch_tag,
        isa=args.isa,
        generator_name=args.generator_name,
        dry_run=args.dry_run,
        timeout_sec=args.timeout_sec,
    )
    record_json = to_jsonable(record)
    if args.show_wrappers:
        record_json["hyperfine_command"] = HyperfineCommandBuilder().build(
            baseline_cmd=args.baseline_cmd,
            candidate_cmd=args.candidate_cmd,
            repeats=args.repeats,
            export_json=args.out.with_suffix(".hyperfine.json"),
        )
        record_json["perf_baseline_command"] = PerfCommandBuilder().build(args.baseline_cmd)
        record_json["perf_candidate_command"] = PerfCommandBuilder().build(args.candidate_cmd)

    ensure_parent(args.out).write_text(json.dumps(record_json, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.log_jsonl is not None:
        append_jsonl(args.log_jsonl, record)
    print(json.dumps(record_json, indent=2, sort_keys=True))
    return 0 if record.status in {"pass", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
