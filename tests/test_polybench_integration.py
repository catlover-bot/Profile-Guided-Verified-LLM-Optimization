from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vallmopt.build.polybench import construct_polybench_compile_command, make_polybench_build_spec
from vallmopt.datasets.polybench import PolyBenchLayout, get_polybench_kernel, load_polybench_config
from vallmopt.utils.tools import has_executable


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
    (utilities_dir / "polybench.h").write_text(
        "#ifndef POLYBENCH_H\n#define POLYBENCH_H\n#endif\n",
        encoding="utf-8",
    )
    (utilities_dir / "polybench.c").write_text(
        "void polybench_stub(void) {}\n",
        encoding="utf-8",
    )
    (kernel_dir / "gemm.c").write_text(
        source_text
        or (
            '#include <stdio.h>\n'
            '#include "polybench.h"\n'
            "int main(void) {\n"
            "#ifdef POLYBENCH_DUMP_ARRAYS\n"
            '    fprintf(stderr, "begin dump: gemm\\n42\\nend dump: gemm\\n");\n'
            "#else\n"
            '    printf("gemm benchmark stub\\n");\n'
            "#endif\n"
            "    return 0;\n"
            "}\n"
        ),
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


def test_polybench_build_spec_contains_utility_source_and_verify_defines(tmp_path: Path) -> None:
    root = make_fake_polybench_tree(tmp_path)
    config = load_polybench_config(POLYBENCH_CONFIG)
    kernel = get_polybench_kernel(root, "gemm", config, size="MINI")

    spec = make_polybench_build_spec(
        polybench_root=root,
        kernel=kernel,
        source_path=kernel.source_path,
        output_path=tmp_path / "gemm",
        size="MINI",
        mode="verify",
    )
    command = construct_polybench_compile_command(spec)

    assert root / "utilities" / "polybench.c" in spec.utility_sources
    assert "MINI_DATASET" in spec.defines
    assert "POLYBENCH_DUMP_ARRAYS" in spec.defines
    assert "POLYBENCH_TIME" not in spec.defines
    assert any(str(root / "utilities" / "polybench.c") == part for part in command)


def test_polybench_build_spec_contains_benchmark_define(tmp_path: Path) -> None:
    root = make_fake_polybench_tree(tmp_path)
    config = load_polybench_config(POLYBENCH_CONFIG)
    kernel = get_polybench_kernel(root, "gemm", config, size="LARGE")

    spec = make_polybench_build_spec(
        polybench_root=root,
        kernel=kernel,
        source_path=kernel.source_path,
        output_path=tmp_path / "gemm",
        size="LARGE",
        mode="benchmark",
    )

    assert "LARGE_DATASET" in spec.defines
    assert "POLYBENCH_TIME" in spec.defines
    assert "POLYBENCH_DUMP_ARRAYS" not in spec.defines


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
    assert summary["dump_arrays"] is True


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


def test_run_polybench_one_fake_gemm_compile_and_compare_passes_when_gcc_available(tmp_path: Path) -> None:
    if not has_executable("gcc"):
        pytest.skip("gcc is unavailable; skipping real fake-PolyBench compile test")

    root = make_fake_polybench_tree(tmp_path)
    work_dir = tmp_path / "real"

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
            "--size",
            "MINI",
            "--skip-benchmark",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Verify status: pass" in result.stdout
    assert "Compared stream: stderr" in result.stdout
    verify_record = json.loads((work_dir / "verify_record.json").read_text(encoding="utf-8"))
    assert verify_record["status"] == "pass"
    assert verify_record["metadata"]["compare_stream_used"] == "stderr"


def test_safety_failure_candidate_fails_with_real_polybench_glue(tmp_path: Path) -> None:
    if not has_executable("gcc"):
        pytest.skip("gcc is unavailable; skipping real fake-PolyBench safety test")

    root = make_fake_polybench_tree(
        tmp_path,
        source_text=(
            '#include <stdio.h>\n'
            '#include "polybench.h"\n'
            "int main(void) {\n"
            "#ifdef POLYBENCH_DUMP_ARRAYS\n"
            '    fprintf(stderr, "begin dump: gemm\\n42\\nend dump: gemm\\n");\n'
            "#endif\n"
            "    return 0;\n"
            "}\n"
        ),
    )
    candidate = tmp_path / "candidate_forbidden.c"
    candidate.write_text(
        (
            '#include <stdio.h>\n'
            '#include "polybench.h"\n'
            "int main(void) {\n"
            "    void *p = 0;\n"
            "    (void)__builtin_assume_aligned(p, 32);\n"
            "#ifdef POLYBENCH_DUMP_ARRAYS\n"
            '    fprintf(stderr, "begin dump: gemm\\n42\\nend dump: gemm\\n");\n'
            "#endif\n"
            "    return 0;\n"
            "}\n"
        ),
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
    assert "__builtin_assume_aligned" in result.stdout
    verify_record = json.loads((work_dir / "verify_record.json").read_text(encoding="utf-8"))
    assert verify_record["gates"][0]["status"] == "pass"
    assert verify_record["gates"][-1]["gate_name"] == "safety"
    assert verify_record["gates"][-1]["status"] == "fail"


def test_unknown_polybench_kernel_raises_clear_error(tmp_path: Path) -> None:
    root = make_fake_polybench_tree(tmp_path)
    config = load_polybench_config(POLYBENCH_CONFIG)

    with pytest.raises(KeyError, match="Unknown PolyBench kernel"):
        get_polybench_kernel(root, "not-a-kernel", config)
