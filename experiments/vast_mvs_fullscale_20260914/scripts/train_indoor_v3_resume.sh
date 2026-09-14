#!/bin/bash
# v3 相对 v2 的唯一算法变化 = 训练列表换成 tuple 级精确 19.3/41.4/39.3 的 train_exact.txt
#   (v2 实测 19.8/42.5/37.7,偏差来自建表后又剪掉的 21 个坏 scan)
# 另加一项仪表:--iter_save_freq 60000 每 1.5 万迭代存一次盘,免得 11 小时才有第一个信号
set -u
cd /root/MonoMVSNet
mkdir -p checkpoints/indoor_v3
/venv/main/bin/python -m torch.distributed.run --master_port 12408 --nproc_per_node=1 train_bld.py   --logdir ./checkpoints/indoor_v3 --dataset=blendedmvs --batch_size=2 --accum_steps 8 --training_views 9   --trainpath=/root/monotrain --summary_freq 200 --resume   --ndepths 8,8,4,4 --depth_inter_r 0.5,0.5,0.5,0.5 --lr 0.001 --wd 0.0001   --lr_scheduler cos --epochs 2 --attn_temp 2 --iter_save_freq 60000   --trainlist lists/ours/train_exact.txt --testlist lists/ours/val.txt
echo TRAIN_V3_DONE
