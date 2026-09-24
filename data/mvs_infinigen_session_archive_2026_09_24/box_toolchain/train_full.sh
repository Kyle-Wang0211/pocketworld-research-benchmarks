#!/bin/bash
# ============================================================================
# 全域全量版 —— 与快档 /root/train_AB.sh 逐字相同的官方两段式 (train_casdiffmvs.sh:37-58),
# 只有三处不同:
#   ① 仓库 = /root/diffmvs_full (官方 cd10d5c + 11 行 --domain_balance 补丁)
#   ② --domain_balance 100000 : 每 epoch 每个数据集等量抽 10 万 (DUSt3R arXiv 2312.14132 §4)
#      => 每 epoch 60 万样本, ×16 = 9.6M = SimpleProc 官方 max_steps 1.6M × batch 6
#   ③ list = lists/full_v3/ (六域全量, 每域 held-out: GSO 103 件 / ARKit 487 视频剔出 train; val = 六域合并 6,963 元组)
# 起点权重与快档相同: casdiff_B_simpleproc/model_000015.ckpt  => 快档 vs 全量 的变量 = 数据
# ============================================================================
set -e
set -o pipefail
cd /root/diffmvs_full
MVS_TRAINING="/root/monotrain"
LOG_DIR="./checkpoints/casdiff_full"
LOAD_CKPT="/root/diffmvs/checkpoints/casdiff_B_simpleproc/model_000015.ckpt"
mkdir -p $LOG_DIR
LOG="$LOG_DIR/train_full.log"
PY=/venv/main/bin/python

echo "[起点权重] $(md5sum $LOAD_CKPT)"                         | tee -a $LOG
echo "[仓库] $(git rev-parse --short HEAD) + $(git diff --stat | tail -1)" | tee -a $LOG
echo "[train] $(wc -l < lists/full_v3/train.txt) scans"           | tee -a $LOG
echo "[val  ] $(wc -l < lists/full_v3/val.txt) scans"             | tee -a $LOG

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
    --domain_balance 100000 \
    --trainlist lists/full_v3/train.txt --testlist lists/full_v3/val.txt | tee -i -a $LOG

$PY -u train.py --mode='train' --dataset=blend --batch_size=4 --epochs=16 \
    --lr=0.001 --lr_sche onecycle --resume \
    --logdir $LOG_DIR --trainpath=$MVS_TRAINING \
    --trainviews=8 --testviews=8 \
    --numdepth=384 --numdepth_initial=48 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --min_radius 0.125 --max_radius 8 \
    --scale 0 0.125 0.025 --conf_weight 0.05 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --domain_balance 100000 \
    --trainlist lists/full_v3/train.txt --testlist lists/full_v3/val.txt | tee -i -a $LOG
