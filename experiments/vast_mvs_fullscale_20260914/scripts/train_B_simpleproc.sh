#!/bin/bash
# ============================================================================
# B 臂: CasDiffMVS + SimpleProc (princeton-vl, BSD-3)
#
# 逐字照搬官方 scripts/train/train_casdiffmvs.sh 的【第②段 BlendedMVS】两段式
# (官方 line 37-47 第一段, line 49-58 第二段 --resume 切 --scale)。
#
# 相对官方只改这 5 处,逐条列明:
#   1) --trainpath   /root/monotrain                       [数据位置]
#   2) --trainlist   lists/sp/train.txt                    [数据位置]
#   3) --testlist    lists/sp/val.txt                      [数据位置]
#   4) --loadckpt    casdiffmvs_mvgZeroDTU.ckpt (md5 108098f9859d21)
#                    [起点权重: 三份官方权重都带 DTU 血统, DTU 无许可声明]
#   5) --trainviews / --testviews  9 -> 8
#      🔴 这是【唯一的配方偏离】,不是选择:
#         SimpleProc 每场景恰 8 张 (add_cameras.py:71 num_cameras=8),
#         blend.py:41 `if len(src_views) < self.nviews-1: continue`
#         => nviews=9 会把全部 7864 条元组跳光 (已实测: 0 条)。
#         8 有数据方官方出处: 44k_scenes.yaml `num_images_in_tuple: 8`。
# 其余每一个数字都与官方逐字一致。
# ============================================================================
set -e
set -o pipefail   # cmd|tee 的退出码默认是 tee 的,不加这行 python 崩了也不会停
cd /root/diffmvs
MVS_TRAINING="/root/monotrain"
LOG_DIR="./checkpoints/casdiff_B_simpleproc"
LOAD_CKPT="/root/ckpt_src/casdiffmvs_mvgZeroDTU.ckpt"
mkdir -p $LOG_DIR
LOG="$LOG_DIR/train_B.log"
PY=/venv/main/bin/python

echo "[起点权重 md5] $(md5sum $LOAD_CKPT)"           | tee -a $LOG
echo "[train 場景] $(wc -l < lists/sp/train.txt)"     | tee -a $LOG
echo "[val   場景] $(wc -l < lists/sp/val.txt)"       | tee -a $LOG

# ---- 第一段 (官方 line 37-47) ----
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
    --trainlist lists/sp/train.txt --testlist lists/sp/val.txt | tee -i -a $LOG

# ---- 第二段 (官方 line 49-58): --resume, --scale 切到 0 0.125 0.025 ----
$PY -u train.py --mode=train --dataset=blend --batch_size=4 --epochs=16 \
    --lr=0.001 --lr_sche onecycle --resume \
    --logdir $LOG_DIR --trainpath=$MVS_TRAINING \
    --trainviews=8 --testviews=8 \
    --numdepth=384 --numdepth_initial=48 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --min_radius 0.125 --max_radius 8 \
    --scale 0 0.125 0.025 --conf_weight 0.05 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --trainlist lists/sp/train.txt --testlist lists/sp/val.txt | tee -i -a $LOG
