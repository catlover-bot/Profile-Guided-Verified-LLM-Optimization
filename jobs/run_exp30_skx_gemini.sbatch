#!/bin/bash
#SBATCH --job-name=exp30_gemini
#SBATCH --partition=lang_week
#SBATCH --account=lang
#SBATCH --cpus-per-task=4
#SBATCH --time=24:00:00
#SBATCH --output=runs/logs/exp30_gemini_%j.out
#SBATCH --error=runs/logs/exp30_gemini_%j.err

set -u -o pipefail

cd ~/workspace/Profile-Guided-Verified-LLM-Optimization
source ~/miniconda3/etc/profile.d/conda.sh
conda activate vallmopt_py310
source ~/.secrets/vallmopt_api.env

export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3-flash-preview}"
export GEMINI_PROVIDER="${GEMINI_PROVIDER:-gemini}"

bash scripts/run_exp30_skx_gemini.sh
