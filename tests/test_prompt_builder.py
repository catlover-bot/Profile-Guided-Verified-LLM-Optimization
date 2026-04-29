from __future__ import annotations

from pathlib import Path

from vallmopt.arch import load_architectures
from vallmopt.generation.mock import MockGenerator
from vallmopt.prompts import PromptBuilder


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_prompt_builder_includes_arch_and_safety_constraints() -> None:
    architectures = load_architectures(REPO_ROOT / "configs" / "architectures.yaml")
    prompt = PromptBuilder(architectures).build_prompt(
        kernel_name="gemm",
        arch_tag="skx-avx512",
        reference_c_code="int main(void) { return 0; }\n",
        allowed_transformations=["tiling"],
        safety_constraints=["undefined behavior", "out-of-bounds access"],
    )

    assert "Target architecture tag: skx-avx512" in prompt
    assert "Target ISA class: avx512" in prompt
    assert "- tiling" in prompt
    assert "- undefined behavior" in prompt
    assert "Return exactly one complete C source file." in prompt
    assert "===== BEGIN REFERENCE C CODE =====" in prompt
    assert "int main(void) { return 0; }" in prompt


def test_mock_generator_returns_reference_code_unchanged() -> None:
    reference = "void kernel(void) {}\n"
    candidate = MockGenerator().generate(
        prompt="prompt",
        kernel_name="kernel",
        arch_tag="snb-avx",
        reference_c_code=reference,
    )

    assert candidate.candidate_c_code == reference
    assert candidate.metadata["generator"] == "mock"
