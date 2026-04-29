"""Candidate generation interfaces."""

from vallmopt.generation.base import CandidateGenerator, GeneratedCandidate
from vallmopt.generation.mock import MockGenerator

__all__ = ["CandidateGenerator", "GeneratedCandidate", "MockGenerator"]
