#!/bin/bash
#SBATCH --job-name=doitgen_tset
#SBATCH --partition=lang_week
#SBATCH --account=lang
#SBATCH --cpus-per-task=4
#SBATCH --time=02:00:00
#SBATCH --output=runs/logs/doitgen_taskset_%j.out
#SBATCH --error=runs/logs/doitgen_taskset_%j.err

set -euo pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310

echo "===== environment ====="
date -Is
hostname
lscpu | egrep 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|MHz|Flags'
grep Cpus_allowed_list /proc/self/status
taskset -pc $$ || true

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

echo "Using CPU=$CPU"

REF="runs/exp30_skx/benchmark_large_r30/doitgen/openai/reference"
CAND_EXE="runs/exp30_skx/benchmark_large_r30/doitgen/openai/candidate"

ls -lh "$REF" "$CAND_EXE"

echo "===== smoke taskset run ====="
taskset -c "$CPU" "$REF" >/dev/null
taskset -c "$CPU" "$CAND_EXE" >/dev/null

python - <<PY
import subprocess
import time
import statistics
import random
import csv
from pathlib import Path

cpu = "$CPU"
ref = "runs/exp30_skx/benchmark_large_r30/doitgen/openai/reference"
cand = "runs/exp30_skx/benchmark_large_r30/doitgen/openai/candidate"

pairs = []
for _ in range(15):
    pairs.append(("ref", ["taskset", "-c", cpu, ref]))
    pairs.append(("cand", ["taskset", "-c", cpu, cand]))

random.seed(30)
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

print("ref median", ref_med)
print("cand median", cand_med)
print("speedup", speedup)

out = Path("runs/summaries/doitgen_openai_taskset_interleaved.csv")
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["label", "n", "median", "min", "max"])
    for label in ["ref", "cand"]:
        xs = times[label]
        w.writerow([label, len(xs), statistics.median(xs), min(xs), max(xs)])
    w.writerow(["speedup", "", speedup, "", ""])

print("saved", out)
PY

echo "===== done ====="
date -Is
