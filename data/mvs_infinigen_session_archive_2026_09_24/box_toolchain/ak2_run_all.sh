#!/bin/bash
# ① highres 臂 2172 个 -> ② 救 117 个 SKIP (lowres 臂)。① 若因磁盘硬闸停手, ② 不启动。
set -u
echo "=== ① highres 臂 开始 $(date +'%m-%d %H:%M:%S') ==="
/root/ak2_batch.sh /root/ak2_run1.txt highres 8
if [ -f /root/AK2_STOP ]; then
  echo "=== ① 因磁盘硬闸停手, ② 不启动 ==="; exit 1
fi
echo "=== ② 救 SKIP (lowres 臂) 开始 $(date +'%m-%d %H:%M:%S') ==="
/root/ak2_batch.sh /root/ak2_run2.txt lowres 8
echo "=== ALL DONE $(date +'%m-%d %H:%M:%S') 场景 $(ls -d /root/ak_blend_v2/ak_* | wc -l) 剩余 $(df -BG --output=avail /root | tail -1) ==="
