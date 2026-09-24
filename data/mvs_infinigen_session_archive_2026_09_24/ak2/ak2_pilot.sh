#!/bin/bash
# 试点: 逐视频 取资产 -> 转换 -> 量磁盘/耗时 -> 删 raw (用完即删)。
# 用法: ak2_pilot.sh <Training|Validation> <highres|lowres> <vid...>
set -u
SPLIT=$1; MODE=$2; shift 2
RAW=/root/ak2_pilot; OUT=/root/ak_blend_v2; PY=/venv/main/bin/python
if [ "$MODE" = highres ]; then A="lowres_wide.traj wide wide_intrinsics highres_depth"
else A="lowres_wide.traj vga_wide vga_wide_intrinsics lowres_depth"; fi
for v in "$@"; do
  t0=$(date +%s)
  /root/ak2_fetch.sh "$SPLIT" "$v" "$RAW" $A || { echo "[dl fail] $v"; continue; }
  t1=$(date +%s)
  RAWSZ=$(du -sm "$RAW/raw/$SPLIT/$v" | cut -f1)
  $PY /root/arkit2blend_v2.py --raw "$RAW/raw/$SPLIT" --out "$OUT" --vids "$v" --depth "$MODE" 2>&1 | grep -E "ak_|SKIP"
  t2=$(date +%s)
  OUTSZ=$(du -sm "$OUT/ak_$v" 2>/dev/null | cut -f1); OUTSZ=${OUTSZ:-0}
  NF=$(ls "$OUT/ak_$v/blended_images" 2>/dev/null | wc -l)
  echo "    [资源] $v($MODE): 下载 $((t1-t0))s / 转换 $((t2-t1))s | raw 峰值 ${RAWSZ} MB | 产物 ${OUTSZ} MB / ${NF} 帧"
  rm -rf "$RAW/raw/$SPLIT/$v/wide" "$RAW/raw/$SPLIT/$v/wide_intrinsics" \
         "$RAW/raw/$SPLIT/$v/highres_depth" "$RAW/raw/$SPLIT/$v/vga_wide" \
         "$RAW/raw/$SPLIT/$v/vga_wide_intrinsics" "$RAW/raw/$SPLIT/$v/lowres_depth"
done
df -h /root | tail -1
