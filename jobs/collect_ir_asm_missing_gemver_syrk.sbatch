#!/bin/bash
#SBATCH --job-name=ir_asm_gs
#SBATCH --cpus-per-task=4
#SBATCH --time=00:30:00
#SBATCH --output=runs/logs/ir_asm_gs_%j.out
#SBATCH --error=runs/logs/ir_asm_gs_%j.err

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
gcc --version | head -1
lscpu | egrep 'Model name|CPU max MHz|CPU min MHz|Flags' || true
grep Cpus_allowed_list /proc/self/status || true

collect_one () {
  k="$1"
  m="$2"
  dir="$3"
  file="$4"
  cand_rel="$5"

  OUT="runs/reports/ir_asm/${ARCH_LABEL}/${NODE}/${k}_${m}"
  mkdir -p "$OUT/gimple_ref" "$OUT/gimple_cand"

  ORIG="$PB/$dir/$file"
  CAND="$(pwd)/$cand_rel"

  echo "===== collect: $k / $m ====="
  echo "ORIG=$ORIG"
  echo "CAND=$CAND"
  ls -lh "$ORIG" "$CAND"

  gcc -std=c99 -O3 -march=native -Wall -Wextra \
    -I "$PB/$dir" \
    -I "$PB/utilities" \
    -DLARGE_DATASET -DPOLYBENCH_TIME \
    -S -fverbose-asm \
    "$ORIG" \
    -o "$OUT/reference.s"

  gcc -std=c99 -O3 -march=native -Wall -Wextra \
    -I "$(dirname "$CAND")" \
    -I "$PB/$dir" \
    -I "$PB/utilities" \
    -DLARGE_DATASET -DPOLYBENCH_TIME \
    -S -fverbose-asm \
    "$CAND" \
    -o "$OUT/candidate.s"

  (
    cd "$OUT/gimple_ref"
    gcc -std=c99 -O3 -march=native -Wall -Wextra \
      -I "$PB/$dir" \
      -I "$PB/utilities" \
      -DLARGE_DATASET -DPOLYBENCH_TIME \
      -fdump-tree-optimized \
      -fdump-tree-vect-details \
      -c "$ORIG" \
      -o reference.o
  )

  (
    cd "$OUT/gimple_cand"
    gcc -std=c99 -O3 -march=native -Wall -Wextra \
      -I "$(dirname "$CAND")" \
      -I "$PB/$dir" \
      -I "$PB/utilities" \
      -DLARGE_DATASET -DPOLYBENCH_TIME \
      -fdump-tree-optimized \
      -fdump-tree-vect-details \
      -c "$CAND" \
      -o candidate.o
  )

  {
    echo "===== reference asm vector-like instructions ====="
    grep -E '\b(v?mul|v?add|v?fmadd|vmov|ymm|zmm|xmm)\b' "$OUT/reference.s" | head -160 || true
    echo
    echo "===== candidate asm vector-like instructions ====="
    grep -E '\b(v?mul|v?add|v?fmadd|vmov|ymm|zmm|xmm)\b' "$OUT/candidate.s" | head -220 || true
    echo
    echo "===== dump files ====="
    find "$OUT" -maxdepth 3 -type f | sort
  } > "$OUT/asm_gimple_key_lines.txt"

  echo "saved: $OUT"
}

collect_one gemver claude linear-algebra/blas/gemver gemver.c runs/exp30_skx/candidates/gemver/claude/candidate.c
collect_one syrk claude linear-algebra/blas/syrk syrk.c runs/exp30_skx/candidates/syrk/claude/candidate.c

echo "===== done ====="
date -Is
