#!/bin/bash
#SBATCH --job-name=cross_vec
#SBATCH --cpus-per-task=4
#SBATCH --time=01:00:00
#SBATCH --output=runs/logs/cross_vec_%j.out
#SBATCH --error=runs/logs/cross_vec_%j.err

set -euo pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310

NODE=$(hostname)
ARCH_LABEL=${ARCH_LABEL:-unknown}
PB="$HOME/workspace/polybench-c-4.2.1-beta"

echo "===== environment ====="
date -Is
echo "NODE=$NODE"
echo "ARCH_LABEL=$ARCH_LABEL"
lscpu | egrep 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|MHz|Flags|NUMA'
gcc --version | head -1

ITEMS=(
  "doitgen openai linear-algebra/kernels/doitgen doitgen.c runs/exp30_skx/candidates/doitgen/openai/candidate.c"
  "2mm openai linear-algebra/kernels/2mm 2mm.c runs/exp30_skx/candidates/2mm/openai/candidate.c"
)

for item in "${ITEMS[@]}"; do
  set -- $item
  k="$1"
  m="$2"
  dir="$3"
  file="$4"
  cand="$5"

  OUT="runs/reports/cross_arch_vec/${ARCH_LABEL}/${NODE}/${k}_${m}"
  mkdir -p "$OUT"

  ORIG="$PB/$dir/$file"

  echo "===== vector report: $ARCH_LABEL / $NODE / $k / $m ====="
  echo "ORIG=$ORIG"
  echo "CAND=$cand"

  gcc -std=c99 -O3 -march=native -Wall -Wextra \
    -I "$PB/$dir" \
    -I "$PB/utilities" \
    -DLARGE_DATASET -DPOLYBENCH_TIME \
    -fopt-info-vec-all="$OUT/reference.vec.all.txt" \
    "$ORIG" "$PB/utilities/polybench.c" \
    -o "$OUT/reference" -lm

  gcc -std=c99 -O3 -march=native -Wall -Wextra \
    -I "$(pwd)/$(dirname "$cand")" \
    -I "$PB/$dir" \
    -I "$PB/utilities" \
    -DLARGE_DATASET -DPOLYBENCH_TIME \
    -fopt-info-vec-all="$OUT/candidate.vec.all.txt" \
    "$cand" "$PB/utilities/polybench.c" \
    -o "$OUT/candidate" -lm

  {
    echo "===== reference optimized/missed ====="
    grep -E "optimized:|missed:" "$OUT/reference.vec.all.txt" | head -220 || true
    echo
    echo "===== candidate optimized/missed ====="
    grep -E "optimized:|missed:" "$OUT/candidate.vec.all.txt" | head -260 || true
  } > "$OUT/vectorization_summary.txt"

  echo "saved: $OUT/vectorization_summary.txt"
done

echo "===== done ====="
date -Is
