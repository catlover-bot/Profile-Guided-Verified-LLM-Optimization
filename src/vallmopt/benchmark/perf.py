"""Command builder for future perf stat usage."""

from __future__ import annotations

import shlex


DEFAULT_PERF_EVENTS = [
    "cycles",
    "instructions",
    "branches",
    "branch-misses",
    "cache-references",
    "cache-misses",
]


class PerfCommandBuilder:
    """Build perf stat command strings without executing them."""

    def __init__(self, events: list[str] | None = None):
        self.events = list(events or DEFAULT_PERF_EVENTS)

    def build(self, command: str) -> str:
        event_text = ",".join(self.events)
        return " ".join(["perf", "stat", "-e", shlex.quote(event_text), "--", command])
