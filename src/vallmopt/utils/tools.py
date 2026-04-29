"""Executable discovery helpers."""

from __future__ import annotations

import shutil


def find_executable(name: str) -> str | None:
    """Return the path to an executable if it is available on PATH."""

    return shutil.which(name)


def has_executable(name: str) -> bool:
    """Return whether an executable is available on PATH."""

    return find_executable(name) is not None


def require_executable(name: str) -> str:
    """Return an executable path or raise a clear error."""

    path = find_executable(name)
    if path is None:
        raise FileNotFoundError(f"Required executable not found on PATH: {name}")
    return path
