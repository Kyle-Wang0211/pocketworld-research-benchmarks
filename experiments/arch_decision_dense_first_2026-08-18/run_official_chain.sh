#!/bin/bash
set -e
PY=/Users/kaidongwang/.venv/pocketworld/bin/python
BASE=/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818
HERE=/Users/kaidongwang/Documents/progecttwo/_artifacts/lever1_source_reform_20260818
T=$HOME/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/mvs_pose_ablation_2026-08-18/tools
CKPT=$HOME/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/casdiffmvs_blendmvg_scratch_2026-08-16/ckpts/casdiffmvs_C_long_ep31.ckpt
MVS=$BASE/mvs_official
echo "[$(date +%H:%M:%S)] ① 建输入目录"
rm -rf $MVS && mkdir -p $MVS
ln -s $BASE/mvs_P16k/cams $MVS/cams
ln -s $BASE/mvs_P16k/images $MVS/images
cp $HERE/pair_official.txt $MVS/pair.txt
echo "[$(date +%H:%M:%S)] ② 推理 132 帧(MPS,固定噪声)"
$PY $HERE/run_arm_lever.py --mvs_in $MVS --out $BASE/out_official --ckpt $CKPT
echo "[$(date +%H:%M:%S)] ③ 官方融合"
$PY $T/fuse_arm.py --pair_folder $MVS --out_folder $BASE/out_official --ply $BASE/dense_official.ply
echo "[$(date +%H:%M:%S)] ④ 量测(雾窗口径)"
$PY $HERE/measure_fog.py --ply $BASE/dense_official.ply --out $HERE/fog_official.json
echo "[$(date +%H:%M:%S)] 完成"
