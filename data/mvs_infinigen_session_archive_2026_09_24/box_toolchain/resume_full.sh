#!/bin/bash
# 从 casdiff_full 最新 ckpt 按官方 --resume 续训 (只在 epoch 边界; 官方 train.py:327-337 取 logdir 里最新 ckpt, start_epoch=epoch+1,
# OneCycle last_epoch=len*start_epoch-1)。自动判断在官方两段式的哪一段: 最新 epoch < 7 -> 第一段 (scale 0 0.25 0.05, train_epochs=8);
# 否则第二段 (scale 0 0.125 0.025)。可选 REPEAT_CAP=<N> 打开 UniMax 封顶 (总量不变, 步数不变, 调度不变)。
set -e; set -o pipefail
cd /root/diffmvs_full
LOG_DIR=./checkpoints/casdiff_full; LOG=$LOG_DIR/train_full.log; PY=/venv/main/bin/python
LAST=$(ls $LOG_DIR/model_*.ckpt | sort | tail -1); EP=$(basename $LAST .ckpt | sed "s/model_0*//"); EP=${EP:-0}
CAP=${REPEAT_CAP:-0}
echo "[resume] 最新 ckpt $LAST (epoch $EP) md5=$(md5sum $LAST | cut -c1-12)  repeat_cap=$CAP  $(date +%m-%d\ %H:%M)" | tee -a $LOG
COMMON="--mode=train --dataset=blend --batch_size=4 --epochs=16 --lr=0.001 --lr_sche onecycle --resume --logdir $LOG_DIR --trainpath=/root/monotrain --trainviews=8 --testviews=8 --numdepth=384 --numdepth_initial=48 --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 --min_radius 0.125 --max_radius 8 --conf_weight 0.05 --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 --domain_balance 100000 --repeat_cap $CAP --trainlist lists/full_v3/train.txt --testlist lists/full_v3/val.txt"
if [ "$EP" -lt 7 ]; then
  $PY -u train.py $COMMON --train_epochs=8 --scale 0 0.25 0.05 | tee -i -a $LOG
fi
$PY -u train.py $COMMON --scale 0 0.125 0.025 | tee -i -a $LOG
