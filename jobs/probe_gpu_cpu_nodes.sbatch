#!/bin/bash
#SBATCH --job-name=probe_gpu_cpu
#SBATCH --partition=gpu_short
#SBATCH --cpus-per-task=1
#SBATCH --time=00:20:00
#SBATCH --output=runs/system/arch_probe/probe_gpu_%j.out
#SBATCH --error=runs/system/arch_probe/probe_gpu_%j.err

set -euo pipefail

echo "===== job info ====="
date -Is
hostname
echo "SLURM_JOB_NODELIST=${SLURM_JOB_NODELIST:-}"
echo

echo "===== lscpu ====="
lscpu | egrep 'Model name|Architecture|CPU\(s\)|Thread|Core|Socket|MHz|Flags|NUMA'

echo
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

echo
echo "===== affinity ====="
grep Cpus_allowed_list /proc/self/status
taskset -pc $$ || true
