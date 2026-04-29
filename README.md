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

## Repository Structure

```text
.
├── configs/                 # Architecture, prompt, verification, and experiment configs
├── data/
│   ├── kernels/             # Placeholder for future kernel inputs
│   └── candidates/          # Placeholder for future generated candidates
├── scripts/                 # CLI entry points
├── src/vallmopt/            # Python package
└── tests/                   # Unit tests
```

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

The tests cover architecture config loading, prompt construction, mock generation, dry-run verification, safety policy checks, benchmark statistics, and JSONL logging.
