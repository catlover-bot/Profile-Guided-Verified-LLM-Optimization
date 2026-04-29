from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vallmopt.utils.paths import ensure_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a local PolyBench/C checkout for later experiments without downloading it."
    )
    parser.add_argument("--source-dir", type=Path, help="Existing local PolyBench/C directory to copy from.")
    parser.add_argument("--out-dir", default=REPO_ROOT / "data" / "kernels" / "polybench", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.source_dir is None:
        ensure_dir(args.out_dir)
        print(f"Prepared placeholder directory: {args.out_dir}")
        print("No PolyBench/C source was downloaded. Pass --source-dir to copy an existing local checkout.")
        return 0

    if not args.source_dir.exists():
        print(f"Source directory does not exist: {args.source_dir}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Would copy {args.source_dir} to {args.out_dir}")
        return 0

    shutil.copytree(args.source_dir, args.out_dir, dirs_exist_ok=True)
    print(f"Copied local PolyBench/C tree to: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
