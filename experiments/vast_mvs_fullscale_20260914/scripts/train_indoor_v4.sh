#!/bin/bash
# v4 = 最优解档。相对 v3 的三处变化:
#   1) 🔴 修好 LR 调度器单位(T_max/milestones 按 optimizer step 而非 batch)——v3 全程恒定 lr=0.001,退火从未发生
#   2) epochs 2 -> 6(用户拍板 C 档:总步数 89,826 = 官方 MonoMVSNet 16,912 步的 5.3 倍,且有完整余弦退火)
#   3) 验证集换成 tuple 级精确 19.30/41.41/39.29 的 val_exact.txt(217 scans/27,553 组,已扫过 0 坏样本)
# 起点仍是官方 bld_best.ckpt——不接 v3 的 finalmodel_0(那是恒定高LR的产物,且会破坏单变量归因)
set -u
cd /root/MonoMVSNet
mkdir -p checkpoints/indoor_v4
/venv/main/bin/python -m torch.distributed.run --master_port 12409 --nproc_per_node=1 train_bld.py \
  --logdir ./checkpoints/indoor_v4 --dataset=blendedmvs --batch_size=2 --accum_steps 8 --training_views 9 \
  --trainpath=/root/monotrain --summary_freq 200 --loadckpt checkpoints/bld_ft/bld_best.ckpt \
  --ndepths 8,8,4,4 --depth_inter_r 0.5,0.5,0.5,0.5 --lr 0.001 --wd 0.0001 \
  --lr_scheduler cos --epochs 6 --attn_temp 2 --iter_save_freq 30000 \
  --trainlist lists/ours/train_exact.txt --testlist lists/ours/val_exact.txt
echo TRAIN_V4_DONE
