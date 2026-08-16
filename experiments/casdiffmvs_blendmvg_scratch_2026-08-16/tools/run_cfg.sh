#!/usr/bin/env bash
# 用法: run_cfg.sh <A|B|C|D>
set -e
CFG=$1
source /venv/main/bin/activate
cd /workspace
export DIFFMVS_DIR=/workspace/diffmvs TIER=mvs
export MVS_ROOT=/workspace/data/BlendedMVS
export BLEND_CACHE=/workspace/cache
export OUT_ROOT=/workspace/runs
export NUM_WORKERS=${NUM_WORKERS:-12}
# 单进程独占 GPU(5090 32GB 只放得下一个),显存碎片保险
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
chmod +x ./train_blendmvg_scratch.sh
./train_blendmvg_scratch.sh $CFG
echo "CFG_${CFG}_DONE $(date)"
