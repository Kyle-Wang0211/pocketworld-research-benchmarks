#!/bin/bash
# MonoMVSNet 室内微调 v2。相对 v1 的唯一变化 = 数据修好了:
#   - 深度范围改逐帧最优窗口(TartanAir 掏空帧 3.6%->0.5%, Hypersim 覆盖率 98%->100%)
#   - BlendedMVG 补齐到 v1.0.2 全量, 训练集 159,292 -> 256,656 组
# 超参与官方 train_bld.sh 逐字相同, 只有两处必要适配:
#   --accum_steps 8  : 单卡 batch2 累积成有效 batch 16 = 官方 4卡x4 的口径
#   --lr_scheduler cos --epochs 2 : 官方 16 epoch 是在 ~17k 组上, 我们一个 epoch 是它的 15 倍;
#                                   按"总优化步数"对齐(官方约 1.7 万步), cos 在真实预算上平滑退火
set -u
cd /root/MonoMVSNet
mkdir -p checkpoints/indoor_v2
/venv/main/bin/python -m torch.distributed.run --master_port 12405 --nproc_per_node=1 train_bld.py \
  --logdir ./checkpoints/indoor_v2 --dataset=blendedmvs --batch_size=2 --accum_steps 8 --training_views 9 \
  --trainpath=/root/monotrain --summary_freq 200 --loadckpt checkpoints/bld_ft/bld_best.ckpt \
  --ndepths 8,8,4,4 --depth_inter_r 0.5,0.5,0.5,0.5 --lr 0.001 --wd 0.0001 \
  --lr_scheduler cos --epochs 2 --attn_temp 2 \
  --trainlist lists/ours/train.txt --testlist lists/ours/val.txt
echo TRAIN_V2_DONE
