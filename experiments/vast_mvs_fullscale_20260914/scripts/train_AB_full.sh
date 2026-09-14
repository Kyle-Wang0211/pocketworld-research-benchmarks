#!/bin/bash
# ============================================================================
# 完全版 A+B —— 与快档 /root/train_AB.sh 【逐字相同】, 只换两处:
#   --trainlist / --testlist   lists/ab/ -> lists/abfull/
# 起点权重、nviews、batch、epochs、lr、scale、所有 stage 参数一律不动,
# 所以 快档 vs 完全版 的唯一变量 = 数据量。
#
# 结构仍是官方 scripts/train/train_casdiffmvs.sh 第②段的两小段式
#   (官方 line 37-47 第一小段 --train_epochs=8; line 49-58 第二小段 --resume 切 --scale)
# ============================================================================
set -e
set -o pipefail
cd /root/diffmvs
MVS_TRAINING="/root/monotrain"
LOG_DIR="./checkpoints/casdiff_AB_full"
LOAD_CKPT="/root/diffmvs/checkpoints/casdiff_B_simpleproc/model_000015.ckpt"
mkdir -p $LOG_DIR
LOG="$LOG_DIR/train_AB_full.log"
PY=/venv/main/bin/python

echo "[起点权重] $(md5sum $LOAD_CKPT)"                    | tee -a $LOG
echo "[与快档同一起点: casdiff_B_simpleproc/model_000015]" | tee -a $LOG
echo "[train] $(wc -l < lists/abfull/train.txt) scans"     | tee -a $LOG
echo "[val  ] $(wc -l < lists/abfull/val.txt) scans"       | tee -a $LOG

$PY -u train.py --mode='train' --dataset=blend --batch_size=4 --epochs=16 \
    --train_epochs=8 --loadckpt=$LOAD_CKPT \
    --lr=0.001 --lr_sche onecycle \
    --logdir=$LOG_DIR --trainpath=$MVS_TRAINING \
    --trainviews=8 --testviews=8 \
    --numdepth=384 --numdepth_initial=48 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --min_radius 0.125 --max_radius 8 \
    --scale 0 0.25 0.05 --conf_weight 0.05 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --trainlist lists/abfull/train.txt --testlist lists/abfull/val.txt | tee -i -a $LOG

$PY -u train.py --mode='train' --dataset=blend --batch_size=4 --epochs=16 \
    --lr=0.001 --lr_sche onecycle --resume \
    --logdir $LOG_DIR --trainpath=$MVS_TRAINING \
    --trainviews=8 --testviews=8 \
    --numdepth=384 --numdepth_initial=48 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --min_radius 0.125 --max_radius 8 \
    --scale 0 0.125 0.025 --conf_weight 0.05 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --trainlist lists/abfull/train.txt --testlist lists/abfull/val.txt | tee -i -a $LOG
