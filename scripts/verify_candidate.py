from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vallmopt.arch import get_architecture  # noqa: E402
from vallmopt.config import load_yaml  # noqa: E402
from vallmopt.logging.jsonl import append_jsonl  # noqa: E402
from vallmopt.logging.schema import to_jsonable  # noqa: E402
from vallmopt.utils.paths import ensure_parent  # noqa: E402
from vallmopt.verify.pipeline import VerifyPipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a generated C candidate through staged gates.")
    parser.add_argument("--kernel-name", required=True)
    parser.add_argument("--arch-tag", required=True)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--architectures", default=REPO_ROOT / "configs" / "architectures.yaml", type=Path)
    parser.add_argument("--verify-config", default=REPO_ROOT / "configs" / "verify.default.yaml", type=Path)
    parser.add_argument("--log-jsonl", default=REPO_ROOT / "runs" / "verify.jsonl", type=Path)
    parser.add_argument("--compiler-flag", action="append", default=[])
    parser.add_argument("--runtime-arg", action="append", default=[])
    parser.add_argument("--prompt-hash")
    parser.add_argument("--generator-name")
    parser.add_argument("--model-name")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    architecture = get_architecture(args.architectures, args.arch_tag)
    config = load_yaml(args.verify_config)
    record = VerifyPipeline(config, dry_run=args.dry_run).run(
        kernel_name=args.kernel_name,
        arch_tag=args.arch_tag,
        isa=architecture.isa,
        reference_path=args.reference,
        candidate_path=args.candidate,
        work_dir=args.work_dir,
        compiler_flags=[*architecture.cflags_extra, *args.compiler_flag],
        runtime_args=args.runtime_arg,
        prompt_hash=args.prompt_hash,
        generator_name=args.generator_name,
        model_name=args.model_name,
        config_path=str(args.verify_config),
    )
    record_json = to_jsonable(record)
    ensure_parent(args.work_dir / "verify_record.json").write_text(
        json.dumps(record_json, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    append_jsonl(args.log_jsonl, record)
    print(json.dumps(record_json, indent=2, sort_keys=True))
    return 0 if record.status in {"pass", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
