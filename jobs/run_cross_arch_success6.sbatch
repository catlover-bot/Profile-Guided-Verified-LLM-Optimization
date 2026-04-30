#!/bin/bash
#SBATCH --job-name=cross_s6
#SBATCH --cpus-per-task=4
#SBATCH --time=04:00:00
#SBATCH --output=runs/logs/cross_success6_%j.out
#SBATCH --error=runs/logs/cross_success6_%j.err

set -u -o pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310

NODE=$(hostname)
ARCH_LABEL=${ARCH_LABEL:-unknown}
ARCH_TAG=${ARCH_TAG:-hsw-avx2}
POLY_ROOT="$HOME/workspace/polybench-c-4.2.1-beta"

mkdir -p runs/cross_arch_success6 runs/system/cross_arch_success6 runs/summaries runs/logs

echo "===== environment ====="
date -Is
echo "NODE=$NODE"
echo "ARCH_LABEL=$ARCH_LABEL"
echo "ARCH_TAG=$ARCH_TAG"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
grep Cpus_allowed_list /proc/self/status || true
taskset -pc $$ || true
lscpu | egrep 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|MHz|Flags|NUMA'
gcc --version | head -1

{
  echo "===== date ====="
  date -Is
  echo "===== hostname ====="
  hostname
  echo "===== slurm ====="
  env | grep -E '^SLURM_' | sort || true
  echo "===== lscpu ====="
  lscpu | egrep 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|MHz|Flags|NUMA'
  echo "===== cpufreq ====="
  for f in \
    /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor \
    /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq \
    /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq \
    /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq \
    /sys/devices/system/cpu/intel_pstate/no_turbo
  do
    echo "===== $f ====="
    cat "$f" 2>/dev/null || echo "N/A"
  done
  echo "===== affinity ====="
  grep Cpus_allowed_list /proc/self/status || true
  taskset -pc $$ || true
  echo "===== gcc ====="
  gcc --version | head -1
  echo "===== uname ====="
  uname -a
} > "runs/system/cross_arch_success6/${ARCH_LABEL}_${NODE}_${SLURM_JOB_ID:-nojob}.txt"

ITEMS=(
  "2mm openai runs/exp30_skx/candidates/2mm/openai/candidate.c"
  "doitgen openai runs/exp30_skx/candidates/doitgen/openai/candidate.c"
  "bicg openai runs/exp30_skx/candidates/bicg/openai/candidate.c"
  "2mm claude runs/exp30_skx/candidates/2mm/claude/candidate.c"
  "gemver claude runs/exp30_skx/candidates/gemver/claude/candidate.c"
  "syrk claude runs/exp30_skx/candidates/syrk/claude/candidate.c"
)

for item in "${ITEMS[@]}"; do
  set -- $item
  k="$1"
  m="$2"
  cand="$3"

  echo "===== candidate: $k / $m ====="
  if [ ! -f "$cand" ]; then
    echo "MISSING_CANDIDATE,$ARCH_LABEL,$NODE,$k,$m,$cand"
    continue
  fi
  ls -lh "$cand"

  echo "===== MINI verify: $k / $m on $ARCH_LABEL ====="
  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag "$ARCH_TAG" \
    --candidate "$cand" \
    --work-dir "runs/cross_arch_success6/${ARCH_LABEL}/${NODE}/verify_mini/$k/$m" \
    --mode verify \
    --size MINI \
    --skip-benchmark || {
      echo "MINI_VERIFY_FAIL,$ARCH_LABEL,$NODE,$k,$m"
      continue
    }

  echo "===== LARGE verify: $k / $m on $ARCH_LABEL ====="
  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag "$ARCH_TAG" \
    --candidate "$cand" \
    --work-dir "runs/cross_arch_success6/${ARCH_LABEL}/${NODE}/verify_large/$k/$m" \
    --mode verify \
    --size LARGE \
    --skip-benchmark || {
      echo "LARGE_VERIFY_FAIL,$ARCH_LABEL,$NODE,$k,$m"
      continue
    }

  echo "===== LARGE benchmark r30: $k / $m on $ARCH_LABEL ====="
  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag "$ARCH_TAG" \
    --candidate "$cand" \
    --work-dir "runs/cross_arch_success6/${ARCH_LABEL}/${NODE}/benchmark_large_r30/$k/$m" \
    --mode benchmark \
    --size LARGE \
    --benchmark-repeats 30 || {
      echo "BENCH_FAIL,$ARCH_LABEL,$NODE,$k,$m"
      continue
    }
done

echo "===== write summary ====="
python - <<PY > "runs/summaries/cross_arch_success6_${ARCH_LABEL}_${NODE}.csv"
import json
from pathlib import Path

arch = "$ARCH_LABEL"
node = "$NODE"
root = Path(f"runs/cross_arch_success6/{arch}/{node}")

items = [
    ("2mm", "openai"),
    ("doitgen", "openai"),
    ("bicg", "openai"),
    ("2mm", "claude"),
    ("gemver", "claude"),
    ("syrk", "claude"),
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

cat "runs/summaries/cross_arch_success6_${ARCH_LABEL}_${NODE}.csv"

echo "===== done ====="
date -Is
