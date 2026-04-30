#!/bin/bash
#SBATCH --job-name=target_gen
#SBATCH --cpus-per-task=4
#SBATCH --time=04:00:00
#SBATCH --output=runs/logs/target_gen_%j.out
#SBATCH --error=runs/logs/target_gen_%j.err

set -u -o pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310

NODE=$(hostname)
ARCH_LABEL=${ARCH_LABEL:-unknown}
ARCH_TAG=${ARCH_TAG:-hsw-avx2}

POLY_ROOT="$HOME/workspace/polybench-c-4.2.1-beta"

echo "===== environment ====="
date -Is
echo "NODE=$NODE"
echo "ARCH_LABEL=$ARCH_LABEL"
echo "ARCH_TAG=$ARCH_TAG"
grep Cpus_allowed_list /proc/self/status || true
lscpu | egrep 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|MHz|Flags|NUMA'
gcc --version | head -1

ITEMS=(
  "doitgen openai_hsw_avx2 runs/target_arch_gen/candidates/doitgen/openai_hsw_avx2/candidate.c"
  "2mm openai_hsw_avx2 runs/target_arch_gen/candidates/2mm/openai_hsw_avx2/candidate.c"
)

for item in "${ITEMS[@]}"; do
  set -- $item
  k="$1"
  m="$2"
  cand="$3"

  echo "===== verify/benchmark: $ARCH_LABEL / $NODE / $k / $m ====="
  ls -lh "$cand"

  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag "$ARCH_TAG" \
    --candidate "$cand" \
    --work-dir "runs/target_arch_gen/${ARCH_LABEL}/${NODE}/verify_mini/$k/$m" \
    --mode verify \
    --size MINI \
    --skip-benchmark || {
      echo "MINI_FAIL,$ARCH_LABEL,$NODE,$k,$m"
      continue
    }

  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag "$ARCH_TAG" \
    --candidate "$cand" \
    --work-dir "runs/target_arch_gen/${ARCH_LABEL}/${NODE}/verify_large/$k/$m" \
    --mode verify \
    --size LARGE \
    --skip-benchmark || {
      echo "LARGE_FAIL,$ARCH_LABEL,$NODE,$k,$m"
      continue
    }

  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag "$ARCH_TAG" \
    --candidate "$cand" \
    --work-dir "runs/target_arch_gen/${ARCH_LABEL}/${NODE}/benchmark_large_r30/$k/$m" \
    --mode benchmark \
    --size LARGE \
    --benchmark-repeats 30 || {
      echo "BENCH_FAIL,$ARCH_LABEL,$NODE,$k,$m"
      continue
    }
done

python - <<PY > "runs/summaries/target_arch_gen_${ARCH_LABEL}_${NODE}.csv"
import json
from pathlib import Path

arch = "$ARCH_LABEL"
node = "$NODE"
root = Path(f"runs/target_arch_gen/{arch}/{node}")

items = [
    ("doitgen", "openai_hsw_avx2"),
    ("2mm", "openai_hsw_avx2"),
]

print("arch_label,node,kernel,model,mini_verify,large_verify,bench_status,speedup,baseline_median,candidate_median,baseline_iqr,candidate_iqr,repeats")

for k, m in items:
    mini_path = root / "verify_mini" / k / m / "verify_record.json"
    large_path = root / "verify_large" / k / m / "verify_record.json"
    bench_path = root / "benchmark_large_r30" / k / m / "benchmark_record.json"

    mini = json.loads(mini_path.read_text()).get("status") if mini_path.exists() else "missing"
    large = json.loads(large_path.read_text()).get("status") if large_path.exists() else "missing"

    if bench_path.exists():
        b = json.loads(bench_path.read_text())
        print(",".join(map(str, [
            arch, node, k, m, mini, large,
            b.get("status"),
            b.get("speedup"),
            b.get("baseline_median_sec"),
            b.get("candidate_median_sec"),
            b.get("baseline_iqr_sec"),
            b.get("candidate_iqr_sec"),
            b.get("repeats"),
        ])))
    else:
        print(f"{arch},{node},{k},{m},{mini},{large},missing,,,,,,")
PY

cat "runs/summaries/target_arch_gen_${ARCH_LABEL}_${NODE}.csv"

echo "===== done ====="
date -Is
