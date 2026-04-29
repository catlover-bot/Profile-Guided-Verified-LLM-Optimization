"""Helpers for compact architecture labels in reports."""

from __future__ import annotations


def arch_tag_to_label(arch_tag: str) -> str:
    """Convert an architecture tag into a display label."""

    return arch_tag.replace("-", " ").upper()


def attach_arch_labels(records: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return copies of records with an ``arch_label`` field."""

    output: list[dict[str, object]] = []
    for record in records:
        copy = dict(record)
        copy["arch_label"] = arch_tag_to_label(str(copy.get("arch_tag", "unknown")))
        output.append(copy)
    return output
