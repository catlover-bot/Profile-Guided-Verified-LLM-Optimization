"""Path helpers."""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    """Create a directory and return it as a ``Path``."""

    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent(path: str | Path) -> Path:
    """Create the parent directory for a path and return the path."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def repo_root_from(path: str | Path) -> Path:
    """Find the nearest parent containing ``.git``, or return the input directory."""

    current = Path(path).resolve()
    if current.is_file():
        current = current.parent
    for parent in (current, *current.parents):
        if (parent / ".git").exists():
            return parent
    return current
