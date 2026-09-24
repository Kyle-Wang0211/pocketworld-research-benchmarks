#!/bin/bash
# 停全部训练。🔴 不能在 ssh 命令行里直接 pkill -f "train.py" —— 那条命令自己就含这个串, 会自杀。
# 写成脚本跑, 脚本的命令行只有 /root/stopall.sh, 不自匹配。
echo "[停] 先停会把训练拉起来的外层"
touch /root/WD.ABORT
pkill -f resume_full.sh   ; sleep 1
pkill -f gc_watchdog.sh   ; sleep 1
pkill -f train_full.sh    ; sleep 1
echo "[停] 再停训练进程"
pkill -INT -f "diffmvs.*train"  ; sleep 10
for p in $(ps -eo pid,args | awk '/python .*train\.py/ && !/awk/ {print $1}'); do
  kill -INT "$p" 2>/dev/null
done
sleep 10
for p in $(ps -eo pid,args | awk '/python .*train\.py/ && !/awk/ {print $1}'); do
  echo "  SIGKILL $p"; kill -KILL "$p" 2>/dev/null
done
sleep 5
echo
echo "=== 结果 ==="
n=$(ps -eo args | awk '/python .*train\.py/ && !/awk/' | wc -l)
echo "残留 train.py 进程: $n"
ps -eo args | awk '/resume_full|gc_watchdog|epoch_snapshot|train_full/ && !/awk/' | head -3
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
