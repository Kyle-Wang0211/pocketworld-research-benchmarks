#!/bin/bash
# 第③段 = 官方 scripts/train/casdiffmvs.sh 的「第②段 BlendedMVS」逐字照搬,
# 只换 --trainpath / --trainlist / --testlist / --loadckpt 起点。零自定参数。
cd /root/diffmvs
MVS_TRAINING="/root/monotrain"
LOG_DIR="./checkpoints/casdiff_indoor"
LOAD_CKPT="/root/hs/ckpt_src/casdiffmvs_blendmvg.ckpt"
mkdir -p $LOG_DIR
/venv/main/bin/python -u train.py --mode='train' --dataset=blend --batch_size=4 --epochs=16 \
    --train_epochs=8 --loadckpt=$LOAD_CKPT \
    --lr=0.001 --lr_sche onecycle \
    --logdir=$LOG_DIR --trainpath=$MVS_TRAINING \
    --trainviews=9 --testviews=9 \
    --numdepth=384 --numdepth_initial=48 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --min_radius 0.125 --max_radius 8 \
    --scale 0 0.25 0.05 --conf_weight 0.05 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --trainlist /root/MonoMVSNet/lists/ours/train_exact.txt \
    --testlist  /root/MonoMVSNet/lists/ours/val_exact.txt
