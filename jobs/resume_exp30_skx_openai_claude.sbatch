#!/bin/bash
#SBATCH --job-name=exp30_skx
#SBATCH --partition=lang_week
#SBATCH --account=lang
#SBATCH --cpus-per-task=4
#SBATCH --time=24:00:00
#SBATCH --output=runs/logs/exp30_skx_%j.out
#SBATCH --error=runs/logs/exp30_skx_%j.err

set -u -o pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310
source ~/.secrets/vallmopt_api.env

echo "===== resume exp30 ====="
date -Is
hostname
grep Cpus_allowed_list /proc/self/status || true
echo "OPENAI_MODEL=${OPENAI_MODEL:-missing}"
echo "ANTHROPIC_MODEL=${ANTHROPIC_MODEL:-missing}"

bash scripts/run_exp30_skx_openai_claude.sh

echo "===== done ====="
date -Is
