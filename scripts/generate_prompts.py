from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vallmopt.arch import load_architectures  # noqa: E402
from vallmopt.config import load_yaml  # noqa: E402
from vallmopt.prompts import PromptBuilder  # noqa: E402
from vallmopt.utils.hashing import sha256_text  # noqa: E402
from vallmopt.utils.paths import ensure_parent  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an architecture-conditioned C optimization prompt.")
    parser.add_argument("--kernel-name", required=True)
    parser.add_argument("--arch-tag", required=True)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--architectures", default=REPO_ROOT / "configs" / "architectures.yaml", type=Path)
    parser.add_argument("--prompt-config", default=REPO_ROOT / "configs" / "prompts.default.yaml", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    architectures = load_architectures(args.architectures)
    prompt_config = load_yaml(args.prompt_config)
    reference_code = args.reference.read_text(encoding="utf-8")

    prompt = PromptBuilder(architectures).build_prompt(
        kernel_name=args.kernel_name,
        arch_tag=args.arch_tag,
        reference_c_code=reference_code,
        allowed_transformations=prompt_config.get("allowed_transformations"),
        safety_constraints=prompt_config.get("safety_constraints"),
        output_constraints=prompt_config.get("output_constraints"),
    )
    ensure_parent(args.out).write_text(prompt, encoding="utf-8")
    print(f"Wrote prompt: {args.out}")
    print(f"Prompt SHA-256: {sha256_text(prompt)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
