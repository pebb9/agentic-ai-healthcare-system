#!/bin/bash
srun --mem=10G --cpus-per-task=8 --gres=gpu:1 --time=00:20:00 singularity exec --nv -B ../../agentic-ai-healthcare-system:/scratch/app -B ~/.cache/huggingface:/.cache/huggingface /ceph/container/pytorch/pytorch_26.02.sif bash /scratch/app/claaudia/run.sh
