#!/bin/bash
#SBATCH --job-name=cross_arch
#SBATCH --cpus-per-task=4
#SBATCH --time=04:00:00
#SBATCH --output=runs/logs/cross_arch_%j.out
#SBATCH --error=runs/logs/cross_arch_%j.err

set -u -o pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310

mkdir -p runs/cross_arch runs/system/cross_arch runs/summaries runs/logs

NODE=$(hostname)
ARCH_LABEL=${ARCH_LABEL:-unknown}
ARCH_TAG=${ARCH_TAG:-skx-avx512}

echo "===== environment ====="
date -Is
echo "NODE=$NODE"
echo "ARCH_LABEL=$ARCH_LABEL"
echo "ARCH_TAG=$ARCH_TAG"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "SLURM_JOB_NODELIST=${SLURM_JOB_NODELIST:-}"
grep Cpus_allowed_list /proc/self/status || true
taskset -pc $$ || true
lscpu | egrep 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|MHz|Flags|NUMA'

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
} > "runs/system/cross_arch/${ARCH_LABEL}_${NODE}_${SLURM_JOB_ID:-nojob}.txt"

POLY_ROOT="$HOME/workspace/polybench-c-4.2.1-beta"

ITEMS=(
  "doitgen openai runs/exp30_skx/candidates/doitgen/openai/candidate.c"
  "2mm openai runs/exp30_skx/candidates/2mm/openai/candidate.c"
)

for item in "${ITEMS[@]}"; do
  set -- $item
  k="$1"
  m="$2"
  cand="$3"

  echo "===== candidate: $k / $m ====="
  ls -lh "$cand"

  echo "===== MINI verify: $k / $m on $ARCH_LABEL ====="
  python scripts/run_polybench_one.py \
    --polybench-root "$POLY_ROOT" \
    --kernel "$k" \
    --arch-tag "$ARCH_TAG" \
    --candidate "$cand" \
    --work-dir "runs/cross_arch/${ARCH_LABEL}/${NODE}/verify_mini/$k/$m" \
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
    --work-dir "runs/cross_arch/${ARCH_LABEL}/${NODE}/verify_large/$k/$m" \
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
    --work-dir "runs/cross_arch/${ARCH_LABEL}/${NODE}/benchmark_large_r30/$k/$m" \
    --mode benchmark \
    --size LARGE \
    --benchmark-repeats 30 || {
      echo "BENCH_FAIL,$ARCH_LABEL,$NODE,$k,$m"
      continue
    }

  echo "===== taskset interleaved: $k / $m on $ARCH_LABEL ====="
  CPU=$(python - <<'PY'
import re
from pathlib import Path
text = Path("/proc/self/status").read_text()
m = re.search(r"Cpus_allowed_list:\s*(\S+)", text)
s = m.group(1)
first = s.split(",")[0]
print(first.split("-")[0] if "-" in first else first)
PY
)

  REF="runs/cross_arch/${ARCH_LABEL}/${NODE}/benchmark_large_r30/$k/$m/reference"
  CAND_EXE="runs/cross_arch/${ARCH_LABEL}/${NODE}/benchmark_large_r30/$k/$m/candidate"

  python - <<PY
import subprocess, time, statistics, random, csv
from pathlib import Path

cpu = "$CPU"
arch = "$ARCH_LABEL"
node = "$NODE"
k = "$k"
m = "$m"
ref = "$REF"
cand = "$CAND_EXE"

pairs = []
for _ in range(15):
    pairs.append(("ref", ["taskset", "-c", cpu, ref]))
    pairs.append(("cand", ["taskset", "-c", cpu, cand]))

random.seed(100)
random.shuffle(pairs)

times = {"ref": [], "cand": []}
for label, cmd in pairs:
    t0 = time.perf_counter()
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    dt = time.perf_counter() - t0
    times[label].append(dt)
    print(label, dt)

ref_med = statistics.median(times["ref"])
cand_med = statistics.median(times["cand"])
speedup = ref_med / cand_med

print("taskset_ref_median", ref_med)
print("taskset_cand_median", cand_med)
print("taskset_speedup", speedup)

out = Path(f"runs/summaries/cross_arch_{arch}_{node}_{k}_{m}_taskset.csv")
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["arch_label","node","kernel","model","label","n","median","min","max"])
    for label in ["ref", "cand"]:
        xs = times[label]
        w.writerow([arch,node,k,m,label,len(xs),statistics.median(xs),min(xs),max(xs)])
    w.writerow([arch,node,k,m,"speedup","",speedup,"",""])
print("saved", out)
PY

done

echo "===== write summary ====="
python - <<PY > "runs/summaries/cross_arch_${ARCH_LABEL}_${NODE}.csv"
import json
from pathlib import Path

arch = "$ARCH_LABEL"
node = "$NODE"
root = Path(f"runs/cross_arch/{arch}/{node}")

items = [
    ("doitgen", "openai"),
    ("2mm", "openai"),
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

cat "runs/summaries/cross_arch_${ARCH_LABEL}_${NODE}.csv"

echo "===== done ====="
date -Is
