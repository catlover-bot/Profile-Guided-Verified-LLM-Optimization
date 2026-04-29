# Verified Architecture-Conditioned LLM Optimization for C Kernels

This repository contains experiment infrastructure for studying whether LLM-generated C loop-kernel optimizations can be conditioned on CPU architecture / ISA tags and verified before benchmarking.

The initial target setting is PolyBench/C-style kernels across x86 ISA classes such as AVX, AVX2, and AVX-512. The repository is designed so real generation, verification, and benchmarking can be launched later in a reproducible way.

This repository currently provides the experiment infrastructure only. It does not yet include real LLM API calls, real PolyBench downloads, or completed experimental results.

## What Is Implemented

- Architecture metadata for the initial tags:
  - `snb-avx`
  - `hsw-avx2`
  - `skx-avx512`
  - `icl-avx512`
- Prompt construction with explicit architecture tags, ISA class, allowed transformations, safety constraints, reference code delimiters, and strict output rules.
- A `CandidateGenerator` interface plus a `MockGenerator` that returns reference C code unchanged.
- A staged verification pipeline with compile, runtime, output-equivalence, sanitizer, and safety-policy gates.
- Lightweight safety-policy checks for forbidden alignment assumptions, fast-math, `Ofast`, and unsafe functions such as `gets`.
- Benchmark utilities for repeated timings, median, IQR, speedup, and command builders for future `hyperfine` and `perf stat` use.
- JSONL logging utilities and structured dataclasses for candidate, verification, benchmark, and experiment records.
- A toy-kernel smoke workflow under `examples/kernels/` and `scripts/run_smoke_pipeline.py`.
- PolyBench/C discovery and one-kernel workflow infrastructure for external PolyBench checkouts.
- CLI wrappers under `scripts/`.
- Unit tests runnable with `pytest`.

## What Is Not Implemented Yet

- Real external LLM API calls.
- Automatic PolyBench/C download or vendoring.
- Real experimental campaigns.
- Completed benchmark result datasets.
- Full formal C verification.

## Installation

Use Python 3.10 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
```

On macOS/Linux, activate with:

```bash
source .venv/bin/activate
```

With `uv`:

```bash
uv sync --extra dev
```

## Repository Structure

```text
.
|-- configs/                 # Architecture, prompt, verification, and experiment configs
|-- data/
|   |-- kernels/             # Placeholder for future kernel inputs
|   `-- candidates/          # Placeholder for future generated candidates
|-- examples/kernels/        # Tiny local C kernels for smoke tests
|-- scripts/                 # CLI entry points
|-- src/vallmopt/            # Python package
`-- tests/                   # Unit tests
```

## Smoke Test Workflow

The smoke workflow uses small local C kernels. It builds an architecture-conditioned prompt, generates or copies a candidate, verifies the candidate, writes structured logs, and summarizes the run. It does not call external LLM APIs or download PolyBench/C.

Windows PowerShell:

```powershell
uv sync --extra dev
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe scripts/run_smoke_pipeline.py --kernel vector_add --arch-tag skx-avx512 --work-dir runs/smoke/vector_add_skx-avx512
```

Linux/macOS:

```bash
uv sync --extra dev
.venv/bin/python -m pytest
.venv/bin/python scripts/run_smoke_pipeline.py --kernel vector_add --arch-tag skx-avx512 --work-dir runs/smoke/vector_add_skx-avx512
```

To test the safety failure path on Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/run_smoke_pipeline.py --kernel vector_add --arch-tag skx-avx512 --candidate examples/kernels/vector_add/candidate_forbidden_alignment.c --work-dir runs/smoke/vector_add_safety_fail
```

Expected result: the safety gate fails and reports that `__builtin_assume_aligned` is forbidden.

Smoke run outputs are written under the selected `--work-dir`, including `prompt.txt`, `candidate.c`, `candidates.jsonl`, `verify.jsonl`, `verify_record.json`, and `summary.json`. If benchmarking runs, `benchmark.jsonl` and `benchmark_record.json` are also written.

## Example Commands

Generate a prompt:

```bash
python scripts/generate_prompts.py \
  --kernel-name gemm \
  --arch-tag skx-avx512 \
  --reference path/to/gemm.c \
  --out prompts/gemm_skx-avx512.txt
```

Verify a candidate in dry-run mode:

```bash
python scripts/verify_candidate.py \
  --kernel-name gemm \
  --arch-tag skx-avx512 \
  --reference path/to/gemm.c \
  --candidate path/to/candidate.c \
  --work-dir runs/verify/gemm_skx-avx512 \
  --dry-run
```

Benchmark command preparation or local timing:

```bash
python scripts/run_benchmark.py \
  --baseline-cmd "./baseline" \
  --candidate-cmd "./candidate" \
  --repeats 7 \
  --out runs/benchmark/result.json \
  --dry-run
```

Summarize JSONL records:

```bash
python scripts/summarize_results.py \
  --input "runs/**/*.jsonl" \
  --out runs/summary.json
```

## PolyBench/C Integration

PolyBench/C is not included in this repository. Download or clone PolyBench/C separately, then point the scripts at that external directory.

Inspect a PolyBench/C root on Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/inspect_polybench.py --polybench-root C:\path\to\polybench-c-4.2.1-beta --config configs/polybench.default.yaml --out runs/polybench/inspect.json
```

Inspect on Linux/macOS:

```bash
.venv/bin/python scripts/inspect_polybench.py --polybench-root /path/to/polybench-c-4.2.1-beta --config configs/polybench.default.yaml --out runs/polybench/inspect.json
```

Run a one-kernel dry workflow on Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/run_polybench_one.py --polybench-root C:\path\to\polybench-c-4.2.1-beta --kernel gemm --arch-tag skx-avx512 --work-dir runs/polybench/gemm_skx-avx512 --dry-run --skip-benchmark
```

Run a one-kernel dry workflow on Linux/macOS:

```bash
.venv/bin/python scripts/run_polybench_one.py --polybench-root /path/to/polybench-c-4.2.1-beta --kernel gemm --arch-tag skx-avx512 --work-dir runs/polybench/gemm_skx-avx512 --dry-run --skip-benchmark
```

### One-Kernel PolyBench Verification

The one-kernel workflow expects an external PolyBench/C root with the usual structure:

```text
polybench-c-4.2.1-beta/
|-- utilities/
|   |-- polybench.h
|   `-- polybench.c
`-- linear-algebra/
    `-- blas/
        `-- gemm/
            |-- gemm.c
            `-- gemm.h
```

Verify one kernel with dumped arrays on Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/run_polybench_one.py --polybench-root C:\path\to\polybench-c-4.2.1-beta --kernel gemm --arch-tag skx-avx512 --work-dir runs/polybench/gemm_verify --mode verify --size LARGE --skip-benchmark
```

Verify one kernel on Linux/macOS:

```bash
.venv/bin/python scripts/run_polybench_one.py --polybench-root /path/to/polybench-c-4.2.1-beta --kernel gemm --arch-tag skx-avx512 --work-dir runs/polybench/gemm_verify --mode verify --size LARGE --skip-benchmark
```

Benchmark-mode build preparation uses `POLYBENCH_TIME` instead of dumped arrays:

```bash
.venv/bin/python scripts/run_polybench_one.py --polybench-root /path/to/polybench-c-4.2.1-beta --kernel gemm --arch-tag skx-avx512 --work-dir runs/polybench/gemm_benchmark --mode benchmark
```

In verify mode, the script compiles the reference source and candidate source with the same PolyBench utility source, include directories, dataset macro, and linker flags. It runs both executables and compares normalized dumped output. PolyBench commonly writes dumps to `stderr`, so the default `--compare-stream auto` compares normalized `stderr` when present, otherwise normalized `stdout`. Use `--compare-stream stdout|stderr|combined` to force a stream.

Current PolyBench support includes configurable layout discovery, architecture-conditioned prompt generation, mock candidate generation, one-kernel compilation against `utilities/polybench.c`, normalized dumped-output comparison, structured logging, optional sanitizer execution, and safety-policy checking.

Remaining before real experiments:

- Real LLM generator integration.
- Slurm experiment launcher.
- Multi-architecture benchmark execution.
- Result aggregation and experiment dashboards.

Current limitations:

- Only the one-kernel workflow is supported.
- No real LLM API is integrated yet.
- No multi-architecture orchestration is implemented yet.
- No full result aggregation or dashboards are implemented yet.

## Expected Future Workflow

1. Place or prepare PolyBench/C kernels under `data/kernels/`.
2. Generate architecture-conditioned prompts for each kernel and architecture tag.
3. Use a real generator implementation to produce candidate C files.
4. Verify every candidate through the staged gates.
5. Benchmark verified candidates against `gcc -O3 -march=native`.
6. Summarize logs and compare optimization behavior across architecture tags.

## Tests

```bash
python -m pytest
```

The tests cover architecture config loading, prompt construction, mock generation, dry-run verification, smoke workflow execution, safety policy checks, benchmark statistics, and JSONL logging.
