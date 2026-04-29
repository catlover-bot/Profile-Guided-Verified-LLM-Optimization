from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vallmopt.datasets.polybench import PolyBenchLayout, get_polybench_kernel, load_polybench_config


REPO_ROOT = Path(__file__).resolve().parents[1]
POLYBENCH_CONFIG = REPO_ROOT / "configs" / "polybench.default.yaml"
INSPECT_SCRIPT = REPO_ROOT / "scripts" / "inspect_polybench.py"
RUN_ONE_SCRIPT = REPO_ROOT / "scripts" / "run_polybench_one.py"


def make_fake_polybench_tree(tmp_path: Path, *, source_text: str | None = None) -> Path:
    root = tmp_path / "polybench"
    kernel_dir = root / "linear-algebra" / "blas" / "gemm"
    utilities_dir = root / "utilities"
    kernel_dir.mkdir(parents=True)
    utilities_dir.mkdir(parents=True)
    (kernel_dir / "gemm.c").write_text(
        source_text
        or '#include <stdio.h>\nint main(void) { printf("42\\n"); return 0; }\n',
        encoding="utf-8",
    )
    return root


def test_load_polybench_config() -> None:
    config = load_polybench_config(POLYBENCH_CONFIG)

    assert config["default_dataset_size"] == "LARGE"
    assert "gemm" in config["known_kernels"]
    assert config["kernel_categories"]["gemm"] == "linear-algebra/blas"


def test_polybench_layout_discovers_fake_kernel(tmp_path: Path) -> None:
    root = make_fake_polybench_tree(tmp_path)
    config = load_polybench_config(POLYBENCH_CONFIG)

    layout = PolyBenchLayout(root)
    available = layout.list_available_kernels(config)
    kernel = get_polybench_kernel(root, "gemm", config, size="SMALL")

    assert available == ["gemm"]
    assert kernel.name == "gemm"
    assert kernel.category == "linear-algebra/blas"
    assert kernel.source_path.name == "gemm.c"
    assert "SMALL_DATASET" in kernel.compile_defines


def test_inspect_polybench_script_on_fake_tree(tmp_path: Path) -> None:
    root = make_fake_polybench_tree(tmp_path)
    out = tmp_path / "inspect.json"

    result = subprocess.run(
        [
            sys.executable,
            str(INSPECT_SCRIPT),
            "--polybench-root",
            str(root),
            "--config",
            str(POLYBENCH_CONFIG),
            "--out",
            str(out),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Discovered kernels (1)" in result.stdout
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert "gemm" in summary["discovered"]
    assert summary["missing_count"] >= 1


def test_run_polybench_one_dry_run_writes_prompt_and_summary(tmp_path: Path) -> None:
    root = make_fake_polybench_tree(tmp_path)
    work_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(RUN_ONE_SCRIPT),
            "--polybench-root",
            str(root),
            "--kernel",
            "gemm",
            "--arch-tag",
            "skx-avx512",
            "--work-dir",
            str(work_dir),
            "--dry-run",
            "--skip-benchmark",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (work_dir / "prompt.txt").exists()
    assert (work_dir / "candidate.c").exists()
    assert (work_dir / "verify.jsonl").exists()
    summary = json.loads((work_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["dataset"] == "polybench"
    assert summary["kernel"] == "gemm"


def test_run_polybench_one_missing_kernel_has_clear_error(tmp_path: Path) -> None:
    root = tmp_path / "polybench"
    root.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(RUN_ONE_SCRIPT),
            "--polybench-root",
            str(root),
            "--kernel",
            "gemm",
            "--arch-tag",
            "skx-avx512",
            "--work-dir",
            str(tmp_path / "missing"),
            "--dry-run",
            "--skip-benchmark",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Could not find PolyBench kernel" in result.stderr


def test_safety_runs_when_polybench_build_is_skipped(tmp_path: Path) -> None:
    root = make_fake_polybench_tree(
        tmp_path,
        source_text='#include <polybench.h>\nint main(void) { return 0; }\n',
    )
    candidate = tmp_path / "candidate_forbidden.c"
    candidate.write_text(
        "int main(void) { void *p = 0; (void)__builtin_assume_aligned(p, 32); return 0; }\n",
        encoding="utf-8",
    )
    work_dir = tmp_path / "safety"

    result = subprocess.run(
        [
            sys.executable,
            str(RUN_ONE_SCRIPT),
            "--polybench-root",
            str(root),
            "--kernel",
            "gemm",
            "--arch-tag",
            "skx-avx512",
            "--candidate",
            str(candidate),
            "--work-dir",
            str(work_dir),
            "--skip-benchmark",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "polybench build glue not implemented yet" in result.stdout
    assert "__builtin_assume_aligned" in result.stdout
    verify_record = json.loads((work_dir / "verify_record.json").read_text(encoding="utf-8"))
    assert verify_record["gates"][0]["status"] == "skipped"
    assert verify_record["gates"][-1]["gate_name"] == "safety"
    assert verify_record["gates"][-1]["status"] == "fail"


def test_unknown_polybench_kernel_raises_clear_error(tmp_path: Path) -> None:
    root = make_fake_polybench_tree(tmp_path)
    config = load_polybench_config(POLYBENCH_CONFIG)

    with pytest.raises(KeyError, match="Unknown PolyBench kernel"):
        get_polybench_kernel(root, "not-a-kernel", config)
