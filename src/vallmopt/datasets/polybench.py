"""PolyBench/C layout discovery.

PolyBench/C is intentionally not vendored by this project. This adapter works
against an external checkout and keeps the expected layout patterns
configurable because downstream mirrors sometimes differ slightly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vallmopt.config import load_yaml


@dataclass(frozen=True)
class PolyBenchKernel:
    """Metadata needed to prepare a one-kernel PolyBench workflow."""

    name: str
    category: str
    source_path: Path
    extra_include_dirs: list[Path]
    compile_defines: list[str]
    run_args: list[str]


def load_polybench_config(path: str | Path) -> dict[str, Any]:
    """Load and validate PolyBench configuration."""

    config = load_yaml(path)
    known = config.get("known_kernels")
    if not isinstance(known, list) or not all(isinstance(name, str) for name in known):
        raise ValueError("PolyBench config must contain a string list: known_kernels")
    patterns = config.get("source_patterns")
    if not isinstance(patterns, list) or not all(isinstance(pattern, str) for pattern in patterns):
        raise ValueError("PolyBench config must contain a string list: source_patterns")
    categories = config.get("kernel_categories")
    if not isinstance(categories, dict):
        raise ValueError("PolyBench config must contain a mapping: kernel_categories")
    return config


class PolyBenchLayout:
    """Discover kernels inside an external PolyBench/C root."""

    def __init__(self, polybench_root: str | Path):
        self.root = Path(polybench_root).expanduser().resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"PolyBench root does not exist: {self.root}")
        if not self.root.is_dir():
            raise NotADirectoryError(f"PolyBench root is not a directory: {self.root}")

    def list_available_kernels(self, config: dict[str, Any]) -> list[str]:
        """Return known kernels that can be found under this root."""

        return sorted(discover_polybench_kernels(self.root, config))

    def find_kernel_source(self, kernel_name: str, config: dict[str, Any]) -> Path:
        """Find one kernel source file, raising a clear error if it is missing."""

        return _find_kernel_source(self.root, kernel_name, config)

    def get_kernel(self, kernel_name: str, config: dict[str, Any], *, size: str | None = None) -> PolyBenchKernel:
        """Return metadata for one discovered kernel."""

        return get_polybench_kernel(self.root, kernel_name, config, size=size)


def discover_polybench_kernels(polybench_root: str | Path, config: dict[str, Any]) -> dict[str, PolyBenchKernel]:
    """Discover all configured kernels that exist in a PolyBench/C root."""

    layout = PolyBenchLayout(polybench_root)
    discovered: dict[str, PolyBenchKernel] = {}
    for name in config.get("known_kernels", []):
        try:
            discovered[name] = layout.get_kernel(str(name), config)
        except FileNotFoundError:
            continue
    return discovered


def get_polybench_kernel(
    polybench_root: str | Path,
    kernel_name: str,
    config: dict[str, Any],
    *,
    size: str | None = None,
) -> PolyBenchKernel:
    """Return metadata for one configured PolyBench/C kernel."""

    if kernel_name not in config.get("known_kernels", []):
        known = ", ".join(config.get("known_kernels", []))
        raise KeyError(f"Unknown PolyBench kernel {kernel_name!r}. Known kernels: {known}")

    root = Path(polybench_root).expanduser().resolve()
    source_path = _find_kernel_source(root, kernel_name, config)
    category = str(config.get("kernel_categories", {}).get(kernel_name, "unknown"))
    include_dirs = _include_dirs(root, source_path, config)
    selected_size = str(size or config.get("default_dataset_size", "LARGE")).upper()
    dataset_sizes = [str(item).upper() for item in config.get("dataset_sizes", [])]
    if dataset_sizes and selected_size not in dataset_sizes:
        allowed = ", ".join(dataset_sizes)
        raise ValueError(f"Invalid PolyBench dataset size {selected_size!r}. Allowed sizes: {allowed}")

    compile_defines = [str(item) for item in config.get("compile_defines", [])]
    define_template = config.get("dataset_define_template")
    if define_template:
        compile_defines.append(str(define_template).format(size=selected_size))

    return PolyBenchKernel(
        name=kernel_name,
        category=category,
        source_path=source_path,
        extra_include_dirs=include_dirs,
        compile_defines=compile_defines,
        run_args=[str(arg) for arg in config.get("run_args", [])],
    )


def _find_kernel_source(root: Path, kernel_name: str, config: dict[str, Any]) -> Path:
    category = str(config.get("kernel_categories", {}).get(kernel_name, ""))
    checked: list[str] = []
    for pattern in config.get("source_patterns", []):
        formatted = str(pattern).format(name=kernel_name, category=category)
        checked.append(formatted)
        if "**" in formatted:
            matches = sorted(path for path in root.glob(formatted) if path.is_file())
            if matches:
                return matches[0].resolve()
        else:
            candidate = root / formatted
            if candidate.is_file():
                return candidate.resolve()

    checked_text = ", ".join(checked)
    raise FileNotFoundError(
        f"Could not find PolyBench kernel {kernel_name!r} under {root}. Checked patterns: {checked_text}"
    )


def _include_dirs(root: Path, source_path: Path, config: dict[str, Any]) -> list[Path]:
    include_dirs = [source_path.parent.resolve()]
    for item in config.get("common_include_dirs", []):
        path = (root / str(item)).resolve()
        if path.exists():
            include_dirs.append(path)
    return _dedupe_paths(include_dirs)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    output: list[Path] = []
    for path in paths:
        if path not in seen:
            output.append(path)
            seen.add(path)
    return output
