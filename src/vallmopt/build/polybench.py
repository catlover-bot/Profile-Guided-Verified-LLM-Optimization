"""PolyBench build metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from vallmopt.build.cbuild import construct_gcc_command_multi_source

if TYPE_CHECKING:
    from vallmopt.datasets.polybench import PolyBenchKernel

@dataclass(frozen=True)
class PolyBenchBuildSpec:
    """Minimal build inputs for a one-kernel PolyBench executable."""

    source_path: Path
    utility_sources: list[Path] = field(default_factory=list)
    include_dirs: list[Path] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)
    cflags: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)
    executable_path: Path | None = None
    compiler: str = "gcc"


DEFAULT_POLYBENCH_CFLAGS = ["-std=c99", "-O3", "-march=native", "-Wall", "-Wextra"]
DEFAULT_POLYBENCH_LDFLAGS = ["-lm"]
DATASET_SIZES = {"MINI", "SMALL", "MEDIUM", "LARGE", "EXTRALARGE"}


def make_polybench_build_spec(
    *,
    polybench_root: Path,
    kernel: "PolyBenchKernel",
    source_path: Path,
    output_path: Path,
    size: str,
    mode: str,
    compiler: str = "gcc",
    cflags: list[str] | None = None,
) -> PolyBenchBuildSpec:
    """Create a build spec for one PolyBench/C source plus utilities."""

    normalized_size = size.upper()
    if normalized_size not in DATASET_SIZES:
        allowed = ", ".join(sorted(DATASET_SIZES))
        raise ValueError(f"Invalid PolyBench dataset size {size!r}. Allowed sizes: {allowed}")
    if mode not in {"verify", "benchmark"}:
        raise ValueError("PolyBench build mode must be 'verify' or 'benchmark'")

    root = Path(polybench_root).expanduser().resolve()
    utilities_dir = root / "utilities"
    utility_sources = [utilities_dir / "polybench.c"]
    include_dirs = _dedupe_paths([source_path.parent, kernel.source_path.parent, utilities_dir, *kernel.extra_include_dirs])
    base_defines = [
        define
        for define in kernel.compile_defines
        if not _is_dataset_define(define)
        and define not in {"POLYBENCH_TIME", "-DPOLYBENCH_TIME", "POLYBENCH_DUMP_ARRAYS", "-DPOLYBENCH_DUMP_ARRAYS"}
    ]
    defines = [*base_defines, f"{normalized_size}_DATASET"]
    if mode == "verify":
        defines.append("POLYBENCH_DUMP_ARRAYS")
    else:
        defines.append("POLYBENCH_TIME")

    return PolyBenchBuildSpec(
        source_path=Path(source_path),
        utility_sources=utility_sources,
        include_dirs=include_dirs,
        defines=defines,
        cflags=list(cflags or DEFAULT_POLYBENCH_CFLAGS),
        ldflags=list(DEFAULT_POLYBENCH_LDFLAGS),
        executable_path=Path(output_path),
        compiler=compiler,
    )


def construct_polybench_compile_command(spec: PolyBenchBuildSpec) -> list[str]:
    """Construct the compiler command for a PolyBench build spec."""

    if spec.executable_path is None:
        raise ValueError("PolyBenchBuildSpec.executable_path is required")
    return construct_gcc_command_multi_source(
        sources=[spec.source_path, *spec.utility_sources],
        output=spec.executable_path,
        include_dirs=spec.include_dirs,
        defines=spec.defines,
        cflags=spec.cflags,
        ldflags=spec.ldflags,
        compiler=spec.compiler,
    )


def _is_dataset_define(define: str) -> bool:
    normalized = define.removeprefix("-D")
    return any(normalized == f"{size}_DATASET" for size in DATASET_SIZES)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    output: list[Path] = []
    for path in (Path(item).resolve() for item in paths):
        if path not in seen:
            output.append(path)
            seen.add(path)
    return output
