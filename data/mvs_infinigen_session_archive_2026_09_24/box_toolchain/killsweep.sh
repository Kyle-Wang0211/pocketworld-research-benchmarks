#!/bin/bash
# 只停被否决的那条(res_sweep.sh 1812886 + 它的 2016 融合 1813333)。
# 按 PID 停, 不用模式匹配 —— 避免误伤 12MP 那条和自杀。
kill -TERM 1813333 2>/dev/null; kill -TERM 1812886 2>/dev/null; sleep 5
kill -KILL 1813333 2>/dev/null; kill -KILL 1812886 2>/dev/null; sleep 3
echo "=== 剩下在跑的 ==="
ps -eo pid,ppid,args | awk '/res_sweep|res_12mp|fuse_only|test\.py/ && !/awk/' | cut -c1-110
echo
echo "=== 12MP 那条还好吗 ==="
echo "  depth_est: $(ls /root/arm_ep0_12mp/depth_est 2>/dev/null | wc -l) / 132"
echo "  res_12mp.sh: $(ps -p 1813062 >/dev/null && echo 活着 || echo 已退出)"
echo "  test.py:     $(ps -p 1813067 >/dev/null && echo 活着 || echo 已退出)"
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
echo
echo "=== 被否决那条留下的东西 ==="
du -sh /root/arm_ep0_r2016 2>/dev/null
