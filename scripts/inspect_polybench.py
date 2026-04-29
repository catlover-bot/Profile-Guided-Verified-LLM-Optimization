from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vallmopt.datasets.polybench import PolyBenchLayout, discover_polybench_kernels, load_polybench_config  # noqa: E402
from vallmopt.utils.paths import ensure_parent  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect an external PolyBench/C directory.")
    parser.add_argument("--polybench-root", required=True, type=Path)
    parser.add_argument("--config", default=REPO_ROOT / "configs" / "polybench.default.yaml", type=Path)
    parser.add_argument("--out", type=Path, help="Optional JSON summary output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = load_polybench_config(args.config)
        layout = PolyBenchLayout(args.polybench_root)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    discovered = discover_polybench_kernels(layout.root, config)
    known = [str(name) for name in config.get("known_kernels", [])]
    missing = [name for name in known if name not in discovered]

    summary = {
        "polybench_root": str(layout.root),
        "config_path": str(args.config),
        "discovered_count": len(discovered),
        "missing_count": len(missing),
        "discovered": {
            name: {
                "category": kernel.category,
                "source_path": str(kernel.source_path),
                "extra_include_dirs": [str(path) for path in kernel.extra_include_dirs],
                "compile_defines": kernel.compile_defines,
            }
            for name, kernel in sorted(discovered.items())
        },
        "missing": missing,
    }

    print(f"PolyBench root: {layout.root}")
    print(f"Discovered kernels ({len(discovered)}):")
    for name in sorted(discovered):
        print(f"  - {name}: {discovered[name].source_path}")
    print(f"Missing kernels ({len(missing)}):")
    for name in missing:
        print(f"  - {name}")

    if args.out is not None:
        ensure_parent(args.out).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote summary: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
