"""Subprocess wrappers with elapsed-time capture."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CommandResult:
    command: str
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_sec: float
    timed_out: bool = False


def command_to_string(command: Sequence[str] | str) -> str:
    """Render a command for logs."""

    if isinstance(command, str):
        return command
    return " ".join(command)


def run_command(
    command: Sequence[str] | str,
    *,
    timeout_sec: float | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    shell: bool = False,
) -> CommandResult:
    """Run a command and capture stdout, stderr, and elapsed time."""

    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            shell=shell,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
        elapsed = time.perf_counter() - start
        return CommandResult(
            command=command_to_string(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_sec=elapsed,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        return CommandResult(
            command=command_to_string(command),
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            elapsed_sec=elapsed,
            timed_out=True,
        )
