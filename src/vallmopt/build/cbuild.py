"""Small C build command constructors."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


def construct_gcc_command(
    *,
    source: str | Path,
    output: str | Path,
    include_dirs: Sequence[str | Path] | None = None,
    defines: Sequence[str] | None = None,
    cflags: Sequence[str] | None = None,
    ldflags: Sequence[str] | None = None,
    compiler: str = "gcc",
) -> list[str]:
    """Construct a gcc-style command for one C source file."""

    command = [compiler, *(cflags or [])]
    for include_dir in include_dirs or []:
        command.extend(["-I", str(include_dir)])
    for define in defines or []:
        command.append(define if define.startswith("-D") else f"-D{define}")
    command.extend([str(source), "-o", str(output), *(ldflags or [])])
    return command


def construct_clang_sanitizer_command(
    *,
    source: str | Path,
    output: str | Path,
    include_dirs: Sequence[str | Path] | None = None,
    defines: Sequence[str] | None = None,
    cflags: Sequence[str] | None = None,
    ldflags: Sequence[str] | None = None,
    compiler: str = "clang",
) -> list[str]:
    """Construct a clang ASan/UBSan command for one C source file."""

    sanitizer_cflags = ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    sanitizer_ldflags = ["-fsanitize=address,undefined"]
    return construct_gcc_command(
        source=source,
        output=output,
        include_dirs=include_dirs,
        defines=defines,
        cflags=[*sanitizer_cflags, *(cflags or [])],
        ldflags=[*sanitizer_ldflags, *(ldflags or [])],
        compiler=compiler,
    )
