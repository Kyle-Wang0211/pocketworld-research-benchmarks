#!/bin/bash
# 重训 ep0 —— 与 /root/train_full.sh 第一段【逐字相同】, 唯一不同是 --logdir(避免覆盖老 ckpt)。
# 变量只有一个: /root/monotrain 里 TartanAir 的 cam 深度范围已用官方分割修正(skyfix)。
#   --epochs=16 --train_epochs=8 必须保持, 否则 OneCycle 在 epoch 0 的学习率轨迹就不同了 => 不是单变量。
# 跑完 epoch 0 (model_000000.ckpt) 自动停。
set -u
cd /root/diffmvs_full
MVS_TRAINING="/root/monotrain"
LOG_DIR="./checkpoints/casdiff_full_skyfix"
LOAD_CKPT="/root/diffmvs/checkpoints/casdiff_B_simpleproc/model_000015.ckpt"
mkdir -p $LOG_DIR
PY=/venv/main/bin/python
echo "[起点权重] $(md5sum $LOAD_CKPT)"
echo "[仓库] $(git rev-parse --short HEAD) + $(git diff --stat | tail -1)"
echo "[老 ep0] $(md5sum /root/diffmvs_full/checkpoints/casdiff_full/model_000000.ckpt)"

$PY -u train.py --mode=train --dataset=blend --batch_size=4 --epochs=16 \
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
    --trainlist lists/full_v3/train.txt --testlist lists/full_v3/val.txt &
TRAIN_PID=$!
echo "[pid] $TRAIN_PID"
# 看门狗: model_000000.ckpt 一落地就停(只要 ep0)
while kill -0 $TRAIN_PID 2>/dev/null; do
  if [ -f $LOG_DIR/model_000000.ckpt ]; then
    sleep 60
    echo "[watchdog] ep0 已落地, 停止训练"
    kill $TRAIN_PID 2>/dev/null; sleep 10; kill -9 $TRAIN_PID 2>/dev/null
    break
  fi
  sleep 60
done
echo "[done] $(ls -la $LOG_DIR/model_000000.ckpt 2>/dev/null || echo 未生成)"
touch /root/EP0SKY_DONE
