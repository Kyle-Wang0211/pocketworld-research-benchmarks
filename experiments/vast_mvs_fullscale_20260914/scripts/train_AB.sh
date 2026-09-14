#!/bin/bash
# ============================================================================
# 第②段 A+B: SimpleProc + 真实室内 混合训练
#
# 结构逐字照搬官方 scripts/train/train_casdiffmvs.sh 第②段的两小段式
#   (官方 line 37-47 第一小段 --train_epochs=8; line 49-58 第二小段 --resume 切 --scale)
#
# 相对官方改动,逐条列明:
#   1) --loadckpt  = ①段产物 model_000015.ckpt (md5 1c95e17a870360)
#      理由: 官方分段就是每段接上一段;且要保住①段拿到的「粘连消失」
#   2) --trainlist/--testlist = lists/ab/{train,val}.txt
#      SimpleProc 7,080 (33.0%) + 室内 14,386 (67.0%), 室内两域按原始比例抽
#   3) --trainviews/--testviews = 8
#      🔴 混合训练必须统一 nviews,而 SimpleProc 每场景仅 8 张
#         (add_cameras.py:71 num_cameras=8 写死) => 只能 8。
#         官方自己也按数据选值: DTU段=5(line17), BlendedMVS段=9(line41)。
#         train 模式是 random.sample(src_views, nviews-1) [blend.py:81],
#         即每步从 10 个 src 随机抽 7 个,16 epoch 下全部 10 个都会被反复采到。
# 其余每一个数字与官方逐字一致。
# ============================================================================
set -e
set -o pipefail
cd /root/diffmvs
MVS_TRAINING="/root/monotrain"
LOG_DIR="./checkpoints/casdiff_AB"
LOAD_CKPT="/root/diffmvs/checkpoints/casdiff_B_simpleproc/model_000015.ckpt"
mkdir -p $LOG_DIR
LOG="$LOG_DIR/train_AB.log"
PY=/venv/main/bin/python
echo "[起点权重] $(md5sum $LOAD_CKPT)"        | tee -a $LOG
echo "[train] $(wc -l < lists/ab/train.txt) scans" | tee -a $LOG
echo "[val  ] $(wc -l < lists/ab/val.txt) scans"   | tee -a $LOG

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
    --trainlist lists/ab/train.txt --testlist lists/ab/val.txt | tee -i -a $LOG

$PY -u train.py --mode=train --dataset=blend --batch_size=4 --epochs=16 \
    --lr=0.001 --lr_sche onecycle --resume \
    --logdir $LOG_DIR --trainpath=$MVS_TRAINING \
    --trainviews=8 --testviews=8 \
    --numdepth=384 --numdepth_initial=48 \
    --stage_iters 1 3 3 --cost_dim_stage 4 4 4 --CostNum 0 4 4 \
    --min_radius 0.125 --max_radius 8 \
    --scale 0 0.125 0.025 --conf_weight 0.05 \
    --hidden_dim 0 32 20 --context_dim 32 32 16 --unet_dim 0 16 8 \
    --trainlist lists/ab/train.txt --testlist lists/ab/val.txt | tee -i -a $LOG
