#!/bin/bash
# APDe-MVS (MIT, Zhaojie Zeng 2025) 跑我们自己的 132 张原生 12MP。
#   -d 直接吃 /root/mvs_P16k (cams/images/pair.txt), 零格式转换
#   -s 0 关掉 SAM 插件 (我们没有 SAM 分割结果, 且要保持零强制权重)
#   其余全默认 = 论文档。它自带图像金字塔 (scale 2^(round-1-i)) 和迭代内几何一致性。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root/APDe-MVS
LOG "开跑 (132 张 @ 4032x3024, 原生)"
nvidia-smi --query-gpu=memory.used --format=csv,noheader
./build/APD -d /root/mvs_P16k -s 0 -c 1
LOG "结束"
ls -la /root/mvs_P16k/APD.ply 2>/dev/null | awk "{printf \"  APD.ply %.2f GB\n\", \$5/1e9}"
touch /root/APDE_RUN_DONE
