"""Mock generation implementation for infrastructure tests."""

from __future__ import annotations

from vallmopt.generation.base import CandidateGenerator, GeneratedCandidate


class MockGenerator(CandidateGenerator):
    """Return reference code unchanged while recording mock metadata."""

    def generate(
        self,
        *,
        prompt: str,
        kernel_name: str,
        arch_tag: str,
        reference_c_code: str,
    ) -> GeneratedCandidate:
        return GeneratedCandidate(
            candidate_c_code=reference_c_code,
            metadata={
                "generator": "mock",
                "kernel_name": kernel_name,
                "arch_tag": arch_tag,
                "prompt_length": len(prompt),
            },
        )
