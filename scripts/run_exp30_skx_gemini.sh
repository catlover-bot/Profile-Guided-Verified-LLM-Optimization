#!/usr/bin/env bash
set -u -o pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310
source ~/.secrets/vallmopt_api.env

EXP_ROOT="runs/exp30_skx_gemini"
BASE_EXP_ROOT="runs/exp30_skx"
POLY_ROOT="$HOME/workspace/polybench-c-4.2.1-beta"

GEMINI_PROVIDER="${GEMINI_PROVIDER:-gemini}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3-flash-preview}"

mkdir -p "$EXP_ROOT" runs/summaries runs/logs

KERNELS=(
  2mm 3mm adi atax bicg cholesky correlation covariance deriche doitgen
  durbin fdtd-2d floyd-warshall gemm gemver gesummv gramschmidt heat-3d
  jacobi-1d jacobi-2d lu ludcmp mvt nussinov seidel-2d symm syr2k syrk
  trisolv trmm
)

echo "===== environment ====="
date -Is
hostname
grep Cpus_allowed_list /proc/self/status || true
echo "GEMINI_PROVIDER=$GEMINI_PROVIDER"
echo "GEMINI_MODEL=$GEMINI_MODEL"

echo "===== ensure prompts ====="
for k in "${KERNELS[@]}"; do
  src="$BASE_EXP_ROOT/prompts/$k/prompt.txt"
  dst="$EXP_ROOT/prompts/$k/prompt.txt"

  if [ -f "$dst" ]; then
    echo "skip existing prompt: $k"
    continue
  fi

  mkdir -p "$(dirname "$dst")"

  if [ -f "$src" ]; then
    cp "$src" "$dst"
    echo "copied prompt: $k"
  else
    echo "make prompt: $k"
    python scripts/run_polybench_one.py \
      --polybench-root "$POLY_ROOT" \
      --kernel "$k" \
      --arch-tag skx-avx512 \
      --work-dir "$EXP_ROOT/prompts/$k" \
      --mode verify \
      --size MINI \
      --skip-benchmark || echo "PROMPT_FAIL,$k"
  fi
done

echo "===== generate Gemini candidates ====="
for k in "${KERNELS[@]}"; do
  out_dir="$EXP_ROOT/candidates/$k/gemini"
  cand="$out_dir/candidate.c"
  prompt="$EXP_ROOT/prompts/$k/prompt.txt"

  if [ -f "$cand" ]; then
    echo "skip existing candidate: $k / gemini"
    wc -l -c "$cand"
    continue
  fi

  if [ ! -f "$prompt" ]; then
    echo "missing prompt, skip: $k"
    continue
  fi

  mkdir -p "$out_dir"

  echo "===== generate: $k / gemini ====="
  if ! python scripts/generate_llm_candidate_once.py \
    --provider "$GEMINI_PROVIDER" \
    --model "$GEMINI_MODEL" \
    --prompt "$prompt" \
    --out-dir "$out_dir" \
    --max-tokens 4096 \
    --temperature 0.2; then
    echo "GENERATION_FAIL,$k,gemini"
    continue
  fi

  wc -l -c "$cand" || true
done

echo "===== MINI verify ====="
for k in "${KERNELS[@]}"; do
  cand="$EXP_ROOT/candidates/$k/gemini/candidate.c"
  work="$EXP_ROOT/verify_mini/$k/gemini"

  if [ ! -f "$cand" ]; then
    echo "missing candidate, skip MINI: $k"
    continue
  fi

  if [ -f "$work/verify_record.json" ]; then
    echo "skip existing MINI: $k"
    continue
  fi

  echo "===== MINI verify: $k / gemini ====="
  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag skx-avx512 \
    --candidate "$cand" \
    --work-dir "$work" \
    --mode verify \
    --size MINI \
    --skip-benchmark || echo "MINI_VERIFY_ERROR,$k,gemini"
done

echo "===== LARGE verify for MINI-pass ====="
for k in "${KERNELS[@]}"; do
  mini="$EXP_ROOT/verify_mini/$k/gemini/verify_record.json"
  cand="$EXP_ROOT/candidates/$k/gemini/candidate.c"
  work="$EXP_ROOT/verify_large/$k/gemini"

  status=$(python -c "import json, pathlib; p=pathlib.Path('$mini'); print(json.loads(p.read_text()).get('status') if p.exists() else 'missing')")

  echo "MINI status: $k / gemini = $status"

  if [ "$status" != "pass" ]; then
    echo "skip LARGE: $k"
    continue
  fi

  if [ -f "$work/verify_record.json" ]; then
    echo "skip existing LARGE: $k"
    continue
  fi

  echo "===== LARGE verify: $k / gemini ====="
  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag skx-avx512 \
    --candidate "$cand" \
    --work-dir "$work" \
    --mode verify \
    --size LARGE \
    --skip-benchmark || echo "LARGE_VERIFY_ERROR,$k,gemini"
done

echo "===== LARGE benchmark r7 for LARGE-pass ====="
for k in "${KERNELS[@]}"; do
  large="$EXP_ROOT/verify_large/$k/gemini/verify_record.json"
  cand="$EXP_ROOT/candidates/$k/gemini/candidate.c"
  work="$EXP_ROOT/benchmark_large_r7/$k/gemini"

  status=$(python -c "import json, pathlib; p=pathlib.Path('$large'); print(json.loads(p.read_text()).get('status') if p.exists() else 'missing')")

  echo "LARGE status: $k / gemini = $status"

  if [ "$status" != "pass" ]; then
    echo "skip r7: $k"
    continue
  fi

  if [ -f "$work/benchmark_record.json" ]; then
    echo "skip existing r7: $k"
    continue
  fi

  echo "===== benchmark r7: $k / gemini ====="
  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag skx-avx512 \
    --candidate "$cand" \
    --work-dir "$work" \
    --mode benchmark \
    --size LARGE \
    --benchmark-repeats 7 || echo "BENCH_R7_ERROR,$k,gemini"
done

echo "===== write r7 summary ====="
python - <<'PY' > runs/summaries/exp30_skx_gemini_r7_summary.csv
import json
from pathlib import Path

EXP_ROOT = Path("runs/exp30_skx_gemini")
kernels = [
    "2mm", "3mm", "adi", "atax", "bicg", "cholesky", "correlation", "covariance",
    "deriche", "doitgen", "durbin", "fdtd-2d", "floyd-warshall", "gemm",
    "gemver", "gesummv", "gramschmidt", "heat-3d", "jacobi-1d", "jacobi-2d",
    "lu", "ludcmp", "mvt", "nussinov", "seidel-2d", "symm", "syr2k", "syrk",
    "trisolv", "trmm",
]

print("kernel,model,mini_verify,large_verify,bench_status,speedup,baseline_median,candidate_median,baseline_iqr,candidate_iqr,repeats")

for k in kernels:
    m = "gemini"
    mini_path = EXP_ROOT / "verify_mini" / k / m / "verify_record.json"
    large_path = EXP_ROOT / "verify_large" / k / m / "verify_record.json"
    bench_path = EXP_ROOT / "benchmark_large_r7" / k / m / "benchmark_record.json"

    mini = json.loads(mini_path.read_text()).get("status") if mini_path.exists() else "missing"
    large = json.loads(large_path.read_text()).get("status") if large_path.exists() else "missing"

    if bench_path.exists():
        b = json.loads(bench_path.read_text())
        print(",".join(map(str, [
            k, m, mini, large,
            b.get("status"),
            b.get("speedup"),
            b.get("baseline_median_sec"),
            b.get("candidate_median_sec"),
            b.get("baseline_iqr_sec"),
            b.get("candidate_iqr_sec"),
            b.get("repeats"),
        ])))
    else:
        print(f"{k},{m},{mini},{large},missing,,,,,,")
PY

cat runs/summaries/exp30_skx_gemini_r7_summary.csv

echo "===== r30 for speedup >= 1.10 ====="
for k in "${KERNELS[@]}"; do
  bench="$EXP_ROOT/benchmark_large_r7/$k/gemini/benchmark_record.json"
  cand="$EXP_ROOT/candidates/$k/gemini/candidate.c"
  work="$EXP_ROOT/benchmark_large_r30/$k/gemini"

  sp=$(python -c "import json, pathlib; p=pathlib.Path('$bench'); print(json.loads(p.read_text()).get('speedup', 0) if p.exists() else 0)")

  echo "r30 candidate: $k / gemini speedup=$sp"

  python -c "import sys; sys.exit(0 if float('$sp') >= 1.10 else 1)"
  if [ $? -ne 0 ]; then
    echo "skip r30: $k"
    continue
  fi

  if [ -f "$work/benchmark_record.json" ]; then
    echo "skip existing r30: $k"
    continue
  fi

  echo "===== benchmark r30: $k / gemini ====="
  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag skx-avx512 \
    --candidate "$cand" \
    --work-dir "$work" \
    --mode benchmark \
    --size LARGE \
    --benchmark-repeats 30 || echo "BENCH_R30_ERROR,$k,gemini"
done

echo "===== write final summary ====="
python - <<'PY' > runs/summaries/exp30_skx_gemini_final_summary.csv
import json
from pathlib import Path

EXP_ROOT = Path("runs/exp30_skx_gemini")
kernels = [
    "2mm", "3mm", "adi", "atax", "bicg", "cholesky", "correlation", "covariance",
    "deriche", "doitgen", "durbin", "fdtd-2d", "floyd-warshall", "gemm",
    "gemver", "gesummv", "gramschmidt", "heat-3d", "jacobi-1d", "jacobi-2d",
    "lu", "ludcmp", "mvt", "nussinov", "seidel-2d", "symm", "syr2k", "syrk",
    "trisolv", "trmm",
]

print("kernel,model,mini_verify,large_verify,best_run,bench_status,speedup,baseline_median,candidate_median,baseline_iqr,candidate_iqr,repeats")

for k in kernels:
    m = "gemini"
    mini_path = EXP_ROOT / "verify_mini" / k / m / "verify_record.json"
    large_path = EXP_ROOT / "verify_large" / k / m / "verify_record.json"
    r30_path = EXP_ROOT / "benchmark_large_r30" / k / m / "benchmark_record.json"
    r7_path = EXP_ROOT / "benchmark_large_r7" / k / m / "benchmark_record.json"

    mini = json.loads(mini_path.read_text()).get("status") if mini_path.exists() else "missing"
    large = json.loads(large_path.read_text()).get("status") if large_path.exists() else "missing"

    if r30_path.exists():
        run = "r30"
        p = r30_path
    elif r7_path.exists():
        run = "r7"
        p = r7_path
    else:
        print(f"{k},{m},{mini},{large},missing,missing,,,,,,")
        continue

    b = json.loads(p.read_text())
    print(",".join(map(str, [
        k, m, mini, large, run,
        b.get("status"),
        b.get("speedup"),
        b.get("baseline_median_sec"),
        b.get("candidate_median_sec"),
        b.get("baseline_iqr_sec"),
        b.get("candidate_iqr_sec"),
        b.get("repeats"),
    ])))
PY

cat runs/summaries/exp30_skx_gemini_final_summary.csv

echo "===== candidate hashes ====="
python - <<'PY' > runs/summaries/exp30_skx_gemini_candidate_hashes.csv
import hashlib
from pathlib import Path

EXP_ROOT = Path("runs/exp30_skx_gemini")
kernels = [
    "2mm", "3mm", "adi", "atax", "bicg", "cholesky", "correlation", "covariance",
    "deriche", "doitgen", "durbin", "fdtd-2d", "floyd-warshall", "gemm",
    "gemver", "gesummv", "gramschmidt", "heat-3d", "jacobi-1d", "jacobi-2d",
    "lu", "ludcmp", "mvt", "nussinov", "seidel-2d", "symm", "syr2k", "syrk",
    "trisolv", "trmm",
]

print("kernel,model,candidate_sha256,candidate_path")
for k in kernels:
    p = EXP_ROOT / "candidates" / k / "gemini" / "candidate.c"
    if p.exists():
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        print(f"{k},gemini,{h},{p}")
    else:
        print(f"{k},gemini,missing,{p}")
PY

cat runs/summaries/exp30_skx_gemini_candidate_hashes.csv

echo "===== done ====="
date -Is
