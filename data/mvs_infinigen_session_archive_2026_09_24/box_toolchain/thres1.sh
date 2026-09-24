#!/bin/bash
# 官方 ETH3D 口径重融: geo_mask_thres = 1 (test.py:237-263 表, 25 个场景里 24 个是 1)
# 我们此前一直用 3 (argparse 默认是 2, 我们连默认都没用, 更严)。
# 像素闸保持物理等价不动, 唯一变量 = 投票数。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
LOG "768  @ px=1.0    thres=1"
/venv/main/bin/python /root/fuse_px.py /root/lg_ep0          1 /root/t1_768.ply   1.0   2>&1 | tail -1
LOG "2016 @ px=2.625  thres=1"
/venv/main/bin/python /root/fuse_px.py /root/arm_ep0_r2016   1 /root/t1_2016.ply  2.625 2>&1 | tail -1
LOG "4032 @ px=5.25   thres=1"
/venv/main/bin/python /root/fuse_px.py /root/arm_ep0_12mp    1 /root/t1_4032.ply  5.25  2>&1 | tail -1
LOG "点数:"
for f in /root/t1_768.ply /root/t1_2016.ply /root/t1_4032.ply; do
  n=$(head -c 400 "$f" | grep -a "element vertex" | awk "{print \$3}")
  printf "  %-18s %s\n" "$(basename $f)" "$n"
done
touch /root/T1_DONE
