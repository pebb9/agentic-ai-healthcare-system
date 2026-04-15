#!/usr/bin/env bash

#SBATCH --job-name=medgemma-evaluation
#SBATCH --output=evaluation_runs/medgemma-evaluation.out
#SBATCH --error=evaluation_runs/medgemma-evaluation.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=58G
#SBATCH --gres=gpu:3
#SBATCH --time=01:30:00

set -e

echo "Job starting..."

singularity exec --nv \
    -B ../../agentic-ai-healthcare-system:/scratch/app \
    -B ~/.cache/huggingface:/.cache/huggingface \
    /ceph/container/pytorch/pytorch_26.02.sif \
    bash /scratch/app/claaudia/run_evaluation.sh