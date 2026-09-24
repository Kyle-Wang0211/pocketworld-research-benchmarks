#!/bin/bash
# 用户 09-24 拍板: coarse 超过 3 小时判失败、让出名额。官方单机模式不设时限 (slurm.gin:19 为 48h), 3h 是用户定的数值。
LIM=10800; LOG=/root/ig7_coarse_timeout.log
while true; do
  for p in $(ps -eo pid,etimes,args | awk -v L=$LIM '/generate_[i]ndoors/ && /--task coarse/ && $2>L {print $1}'); do
    s=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -o -- "--seed [0-9a-f]*" | awk '{print $2}')
    o=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -o -- "--output_folder [^ ]*" | awk '{print $2}')
    e=$(ps -o etimes= -p $p | tr -d ' ')
    kill $p && echo "[$(date +%F' '%T)] 超 3h 判失败: seed=$s 已跑 $((e/60)) 分钟 $o" >> $LOG
  done
  sleep 300
done
