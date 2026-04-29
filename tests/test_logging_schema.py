from __future__ import annotations

from vallmopt.logging.jsonl import append_jsonl, read_jsonl
from vallmopt.logging.schema import CandidateRecord


def test_jsonl_logging_writes_and_reads_records(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    record = CandidateRecord(
        kernel_name="gemm",
        arch_tag="skx-avx512",
        isa="avx512",
        generator_name="mock",
        prompt_hash="prompt",
        reference_code_hash="reference",
        candidate_code_hash="candidate",
        status="pass",
    )

    append_jsonl(path, record)
    rows = read_jsonl(path)

    assert len(rows) == 1
    assert rows[0]["kernel_name"] == "gemm"
    assert rows[0]["generator_name"] == "mock"
    assert rows[0]["status"] == "pass"
