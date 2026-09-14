#!/bin/bash
cd /root/MonoMVSNet
/venv/main/bin/python -m torch.distributed.run --master_port 12411 --nproc_per_node=1 train_bld.py \
  --logdir ./checkpoints/indoor_v4 --dataset=blendedmvs --batch_size=2 --accum_steps 8 --training_views 9 \
  --trainpath=/root/monotrain --summary_freq 200 --resume \
  --ndepths 8,8,4,4 --depth_inter_r 0.5,0.5,0.5,0.5 --lr 0.001 --wd 0.0001 \
  --lr_scheduler cos --epochs 6 --attn_temp 2 --iter_save_freq 30000 \
  --trainlist lists/ours/train_exact.txt --testlist lists/ours/val_exact.txt
echo TRAIN_V4_RESUME_DONE
