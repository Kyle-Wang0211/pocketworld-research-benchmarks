#!/bin/bash
# 拆开「分辨率」与「几何闸」两个被我混在一起的变量。
# 三场都用【已在盘上的同一批深度图】重融, 零重新推理, 唯一变量是 geo_pixel_thres。
#
#   焦距比实测: 768 臂 scale=0.190476 ; 12MP 臂 scale_w=1.0 / scale_h=0.99471
#   ⇒ 同一个「1.0 像素」在 12MP 上对应的物理距离是 768 上的 1/5.25。
#
#   C  768  @ 1.0       阳性对照: 必须复现 36,232,793 点, 否则 lg_ep0 不是那条臂
#   B  768  @ 0.190476  把 768 臂收紧到 12MP 的物理容差
#   A  12MP @ 5.25      把 12MP 臂放宽回 768 的物理容差
# geo_mask_thres 三场都是 3, 与既有口径一致。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
LOG "C  768 @ px=1.0 (阳性对照)"
/venv/main/bin/python /root/fuse_px.py /root/lg_ep0 3 /root/gate_C_768_px1.ply 1.0 2>&1 | tail -2
LOG "B  768 @ px=0.190476"
/venv/main/bin/python /root/fuse_px.py /root/lg_ep0 3 /root/gate_B_768_px019.ply 0.190476 2>&1 | tail -2
LOG "A  12MP @ px=5.25"
/venv/main/bin/python /root/fuse_px.py /root/arm_ep0_12mp 3 /root/gate_A_12mp_px525.ply 5.25 2>&1 | tail -2
LOG "点数:"
for f in /root/gate_C_768_px1.ply /root/gate_B_768_px019.ply /root/gate_A_12mp_px525.ply; do
  n=$(head -c 400 "$f" | grep -a "element vertex" | head -1 | awk "{print \$3}")
  printf "  %-34s %s\n" "$(basename $f)" "$n"
done
touch /root/GATE_DONE
