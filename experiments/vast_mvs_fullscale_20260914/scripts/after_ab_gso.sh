#!/bin/bash
# AB 快档训练进程退出后 -> 起 GSO 渲染(两工人, 断点续跑)
LOG=/root/after_ab_gso.log; exec >> $LOG 2>&1
echo "=== [$(date +%m-%d\ %H:%M)] 等 AB 训练退出 ==="
while ps -eo command | awk "/train.py/ && /casdiff_AB/ && !/awk/" | grep -q .; do sleep 60; done
echo "[$(date +%H:%M)] AB 已退出; ckpt: $(ls /root/diffmvs/checkpoints/casdiff_AB/*.ckpt | wc -l) 个; 最后一行: $(grep -o "Epoch [0-9]*/16" /root/diffmvs/checkpoints/casdiff_AB/train_AB.log | tail -1)"
sleep 30
echo "[$(date +%H:%M)] 起 GSO"; bash /root/gso_launch.sh
