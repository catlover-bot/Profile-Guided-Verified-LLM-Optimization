"""Lightweight static safety-policy checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from vallmopt.logging.schema import VerifyGateResult


@dataclass(frozen=True)
class SafetyRule:
    name: str
    pattern: re.Pattern[str]
    message: str


DEFAULT_SAFETY_RULES = [
    SafetyRule(
        name="builtin_assume_aligned",
        pattern=re.compile(r"__builtin_assume_aligned"),
        message="new alignment assumptions via __builtin_assume_aligned are forbidden",
    ),
    SafetyRule(
        name="attribute_aligned",
        pattern=re.compile(r"__attribute__\s*\(\s*\(\s*aligned"),
        message="new alignment attributes are forbidden",
    ),
    SafetyRule(
        name="gcc_ofast",
        pattern=re.compile(r"#\s*pragma\s+GCC\s+optimize\s*\(\s*\"Ofast\"\s*\)"),
        message="Ofast pragmas are forbidden",
    ),
    SafetyRule(
        name="fast_math",
        pattern=re.compile(r"-ffast-math"),
        message="fast-math is forbidden in code comments or configuration text",
    ),
    SafetyRule(
        name="gets",
        pattern=re.compile(r"\bgets\s*\("),
        message="unsafe function gets is forbidden",
    ),
]


def check_safety_policy(source_text: str, *, extra_text: str = "") -> VerifyGateResult:
    """Run lightweight source/config text checks for disallowed constructs."""

    combined = f"{source_text}\n{extra_text}"
    for rule in DEFAULT_SAFETY_RULES:
        if rule.pattern.search(combined):
            return VerifyGateResult(
                gate_name="safety",
                status="fail",
                failure_reason=f"{rule.name}: {rule.message}",
            )
    return VerifyGateResult(gate_name="safety", status="pass")


def check_safety_file(path: str | Path, *, extra_text: str = "") -> VerifyGateResult:
    """Run safety checks against a source file."""

    return check_safety_policy(Path(path).read_text(encoding="utf-8"), extra_text=extra_text)
