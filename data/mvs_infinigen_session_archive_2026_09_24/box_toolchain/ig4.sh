#!/bin/bash
# 补上漏掉的一格: 8192 + 去噪 = 画质上限。再与 256+去噪 对比, 判断 256 是否丢真细节。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/ig_venv2/bin/python
cd /root/infinigen
rm -rf /root/ig4 /root/ig3/frames /root/frames
T0=$(date +%s)
timeout 2400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
  --input_folder /root/ig_probe/coarse --output_folder /root/ig4 \
  -g fast_solve.gin singleroom.gin \
  -p compose_indoors.terrain_enabled=False \
     configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True \
  > /root/ig4.log 2>&1
LOG "8192+去噪 rc=$? 用时 $(( $(date +%s)-T0 ))s  $(grep -oE "^Time: [0-9:.]+" /root/ig4.log | tail -1)"
F=""
for c in /root/ig4/frames/Image/camera_0/Image_*.png /root/frames/Image/camera_0/Image_*.png /root/ig4/Image_*.png; do
  [ -f "$c" ] && { F="$c"; break; }
done
[ -n "$F" ] && cp "$F" /root/ig4_s8192_dn.png && echo "  -> /root/ig4_s8192_dn.png" || echo "  🔴 没找到图"
touch /root/IG4_DONE
