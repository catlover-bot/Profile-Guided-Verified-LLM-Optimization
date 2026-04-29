from __future__ import annotations

from pathlib import Path

from vallmopt.verify.pipeline import VerifyPipeline
from vallmopt.verify.safety import check_safety_policy


def test_safety_checker_rejects_forbidden_alignment_assumptions() -> None:
    result = check_safety_policy("float *p = __builtin_assume_aligned(x, 64);")

    assert result.status == "fail"
    assert "alignment" in (result.failure_reason or "")


def test_verify_pipeline_can_run_in_dry_run_mode(tmp_path: Path) -> None:
    reference = tmp_path / "reference.c"
    candidate = tmp_path / "candidate.c"
    source = "int main(void) { return 0; }\n"
    reference.write_text(source, encoding="utf-8")
    candidate.write_text(source, encoding="utf-8")

    record = VerifyPipeline(dry_run=True).run(
        kernel_name="trivial",
        arch_tag="skx-avx512",
        isa="avx512",
        reference_path=reference,
        candidate_path=candidate,
        work_dir=tmp_path / "work",
    )

    assert record.status == "skipped"
    assert [gate.gate_name for gate in record.gates] == [
        "compile",
        "runtime",
        "output",
        "sanitizer",
        "safety",
    ]
    assert record.gates[0].status == "skipped"
    assert record.gates[-1].status == "pass"
