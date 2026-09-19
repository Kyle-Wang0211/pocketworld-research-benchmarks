#!/bin/zsh
# 外挂看门狗:盯系统级可用内存(free+inactive+speculative页),低于阈值就杀推理进程。
# 盯系统而不是进程 RSS,因为 MPS 的统一内存分配不完全计入 RSS——前三次炸机就是这么漏掉的。
MIN_MB=${1:-2600}
PS=$(sysctl -n hw.pagesize)
while true; do
  P=$(pgrep -f "demo_images_only_inference" | head -1)
  if [ -n "$P" ]; then
    FREE=$(vm_stat | awk -F: '/Pages free|Pages inactive|Pages speculative/{gsub(/[ .]/,"",$2); s+=$2} END{print s}')
    MB=$(( FREE * PS / 1048576 ))
    if [ "$MB" -lt "$MIN_MB" ]; then
      echo "$(date +%H:%M:%S) 🔴 可用内存 ${MB}MB < ${MIN_MB}MB,杀 $P"; kill -9 $P
    fi
  fi
  sleep 0.4
done
