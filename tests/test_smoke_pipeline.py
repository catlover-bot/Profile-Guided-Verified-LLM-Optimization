from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vallmopt.utils.tools import has_executable


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_smoke_pipeline.py"


def run_smoke(*args: str, work_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--work-dir", str(work_dir)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_toy_kernel_files_exist() -> None:
    expected = [
        REPO_ROOT / "examples" / "kernels" / "vector_add" / "reference.c",
        REPO_ROOT / "examples" / "kernels" / "vector_add" / "candidate_same.c",
        REPO_ROOT / "examples" / "kernels" / "vector_add" / "candidate_forbidden_alignment.c",
        REPO_ROOT / "examples" / "kernels" / "vector_add" / "input.txt",
        REPO_ROOT / "examples" / "kernels" / "vector_add" / "expected.txt",
        REPO_ROOT / "examples" / "kernels" / "dot_product" / "reference.c",
        REPO_ROOT / "examples" / "kernels" / "dot_product" / "candidate_same.c",
        REPO_ROOT / "examples" / "kernels" / "dot_product" / "input.txt",
        REPO_ROOT / "examples" / "kernels" / "dot_product" / "expected.txt",
    ]

    for path in expected:
        assert path.exists(), path


def test_smoke_pipeline_dry_run_writes_prompt_and_verify_log(tmp_path: Path) -> None:
    work_dir = tmp_path / "smoke"
    result = run_smoke(
        "--kernel",
        "vector_add",
        "--arch-tag",
        "skx-avx512",
        "--dry-run",
        "--skip-benchmark",
        work_dir=work_dir,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (work_dir / "prompt.txt").exists()
    assert (work_dir / "candidate.c").exists()
    assert (work_dir / "candidates.jsonl").exists()
    assert (work_dir / "verify.jsonl").exists()
    summary = json.loads((work_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["verify_log"].endswith("verify.jsonl")


def test_safety_failure_candidate_is_rejected(tmp_path: Path) -> None:
    if not has_executable("gcc"):
        pytest.skip("gcc is unavailable; skipping compile-based smoke safety test")

    candidate = REPO_ROOT / "examples" / "kernels" / "vector_add" / "candidate_forbidden_alignment.c"
    result = run_smoke(
        "--kernel",
        "vector_add",
        "--arch-tag",
        "skx-avx512",
        "--candidate",
        str(candidate),
        "--skip-benchmark",
        work_dir=tmp_path / "safety_fail",
    )

    assert result.returncode == 1
    assert "Verify status: fail" in result.stdout
    assert "__builtin_assume_aligned" in result.stdout
    verify_record = json.loads((tmp_path / "safety_fail" / "verify_record.json").read_text(encoding="utf-8"))
    assert verify_record["status"] == "fail"


def test_missing_external_tool_is_reported_without_exception(tmp_path: Path) -> None:
    from vallmopt.verify.compile import compile_source

    source = tmp_path / "main.c"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    result = compile_source(
        source=source,
        output=tmp_path / "main",
        compiler="vallmopt_definitely_missing_compiler",
    )

    assert result.status == "fail"
    assert "not found on PATH" in (result.failure_reason or "")
