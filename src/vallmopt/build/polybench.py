"""PolyBench build metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PolyBenchBuildSpec:
    """Minimal build inputs for a one-kernel PolyBench executable."""

    source_path: Path
    include_dirs: list[Path] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)
    cflags: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)
    executable_path: Path | None = None
