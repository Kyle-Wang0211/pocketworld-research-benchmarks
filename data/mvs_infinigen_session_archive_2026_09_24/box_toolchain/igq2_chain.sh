#!/bin/bash
# 等第一轮扫描(iggpures.sh)结束再跑第二轮, 避免 GPU 争抢
for i in $(seq 1 240); do
  [ -f /root/IGQ_DONE ] && break
  pgrep -f "iggpures.sh" >/dev/null || break
  sleep 15
done
exec /root/igq2.sh
