"""Abstract candidate generation interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GeneratedCandidate:
    """Generated C source plus generation metadata."""

    candidate_c_code: str
    metadata: dict[str, Any] = field(default_factory=dict)


class CandidateGenerator(ABC):
    """Interface implemented by candidate generators."""

    @abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        kernel_name: str,
        arch_tag: str,
        reference_c_code: str,
    ) -> GeneratedCandidate:
        """Generate a candidate C source file."""
