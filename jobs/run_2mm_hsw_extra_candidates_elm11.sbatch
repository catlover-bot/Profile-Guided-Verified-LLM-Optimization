#!/bin/bash
#SBATCH --job-name=2mm_hsw_extra
#SBATCH --cpus-per-task=4
#SBATCH --time=03:00:00
#SBATCH --output=runs/logs/2mm_hsw_extra_%j.out
#SBATCH --error=runs/logs/2mm_hsw_extra_%j.err

set -u -o pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310

POLY_ROOT="$HOME/workspace/polybench-c-4.2.1-beta"
ARCH_LABEL="hsw_avx2_i7_5820k"
NODE=$(hostname)

echo "===== environment ====="
date -Is
echo "NODE=$NODE"
echo "ARCH_LABEL=$ARCH_LABEL"
grep Cpus_allowed_list /proc/self/status || true
lscpu | egrep 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|MHz|Flags|NUMA'
gcc --version | head -1

for sample in sample2 sample3; do
  cand="runs/target_arch_gen/candidates/2mm/openai_hsw_avx2_${sample}/candidate.c"
  model="openai_hsw_avx2_${sample}"

  echo "===== evaluate $model on $NODE ====="
  ls -lh "$cand"

  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel 2mm \
    --arch-tag hsw-avx2 \
    --candidate "$cand" \
    --work-dir "runs/target_arch_gen/$ARCH_LABEL/$NODE/verify_mini/2mm/$model" \
    --mode verify \
    --size MINI \
    --skip-benchmark || {
      echo "MINI_FAIL,$model"
      continue
    }

  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel 2mm \
    --arch-tag hsw-avx2 \
    --candidate "$cand" \
    --work-dir "runs/target_arch_gen/$ARCH_LABEL/$NODE/verify_large/2mm/$model" \
    --mode verify \
    --size LARGE \
    --skip-benchmark || {
      echo "LARGE_FAIL,$model"
      continue
    }

  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel 2mm \
    --arch-tag hsw-avx2 \
    --candidate "$cand" \
    --work-dir "runs/target_arch_gen/$ARCH_LABEL/$NODE/benchmark_large_r30/2mm/$model" \
    --mode benchmark \
    --size LARGE \
    --benchmark-repeats 30 || {
      echo "BENCH_FAIL,$model"
      continue
    }
done

python - <<'PY' > runs/summaries/2mm_hsw_avx2_extra_elm11_summary.csv
import json
from pathlib import Path

arch = "hsw_avx2_i7_5820k"
node = "elm11"
root = Path(f"runs/target_arch_gen/{arch}/{node}")

models = [
    "openai_hsw_avx2",
    "openai_hsw_avx2_sample2",
    "openai_hsw_avx2_sample3",
]

print("arch_label,node,kernel,model,mini_verify,large_verify,bench_status,speedup,baseline_median,candidate_median,repeats")
for model in models:
    mini = root / "verify_mini" / "2mm" / model / "verify_record.json"
    large = root / "verify_large" / "2mm" / model / "verify_record.json"
    bench = root / "benchmark_large_r30" / "2mm" / model / "benchmark_record.json"

    mini_s = json.loads(mini.read_text()).get("status") if mini.exists() else "missing"
    large_s = json.loads(large.read_text()).get("status") if large.exists() else "missing"

    if bench.exists():
        b = json.loads(bench.read_text())
        print(",".join(map(str, [
            arch, node, "2mm", model, mini_s, large_s,
            b.get("status"),
            b.get("speedup"),
            b.get("baseline_median_sec"),
            b.get("candidate_median_sec"),
            b.get("repeats"),
        ])))
    else:
        print(f"{arch},{node},2mm,{model},{mini_s},{large_s},missing,,,,")
PY

cat runs/summaries/2mm_hsw_avx2_extra_elm11_summary.csv

echo "===== done ====="
date -Is
