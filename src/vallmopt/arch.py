"""Architecture metadata loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vallmopt.config import load_yaml


@dataclass(frozen=True)
class Architecture:
    """A CPU/ISA metadata record used to condition prompts and runs."""

    tag: str
    isa: str
    description: str
    cflags_extra: list[str]


def load_architectures(path: str | Path) -> dict[str, Architecture]:
    """Load architecture records keyed by architecture tag."""

    raw = load_yaml(path)
    architectures: dict[str, Architecture] = {}
    for tag, value in raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"Architecture entry {tag!r} must be a mapping")
        try:
            isa = str(value["isa"])
            description = str(value["description"])
        except KeyError as exc:
            raise ValueError(f"Architecture entry {tag!r} missing key {exc.args[0]!r}") from exc
        cflags = value.get("cflags_extra", [])
        if not isinstance(cflags, list) or not all(isinstance(flag, str) for flag in cflags):
            raise ValueError(f"Architecture entry {tag!r} has invalid cflags_extra")
        architectures[tag] = Architecture(
            tag=tag,
            isa=isa,
            description=description,
            cflags_extra=list(cflags),
        )
    return architectures


def get_architecture(path: str | Path, arch_tag: str) -> Architecture:
    """Load one architecture by tag."""

    architectures = load_architectures(path)
    try:
        return architectures[arch_tag]
    except KeyError as exc:
        known = ", ".join(sorted(architectures))
        raise KeyError(f"Unknown architecture tag {arch_tag!r}. Known tags: {known}") from exc
