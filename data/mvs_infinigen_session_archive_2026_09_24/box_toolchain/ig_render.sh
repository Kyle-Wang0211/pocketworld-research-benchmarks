#!/bin/bash
# Infinigen Indoors: 量【渲染一帧 + 深度真值】的成本 —— 这才是决定可行性的数。
# 🔴 纯 CPU (GPU 留给训练)。分辨率设成我们的训练分辨率 768x576。
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/ig_venv2/bin/python
cd /root/infinigen

LOG "查渲染相关的可配置项"
grep -rnE "resolution|num_samples|adaptive_threshold|image_size" \
  src/infinigen/core/rendering/render.py 2>/dev/null | head -8

rm -rf /root/ig_probe/frames
LOG "渲染 task=render (含 blender_gt 深度真值), 768x576"
T0=$(date +%s)
timeout 3600 $P -m infinigen_examples.generate_indoors \
  --seed 0 --task render \
  --input_folder /root/ig_probe/coarse \
  --output_folder /root/ig_probe/frames \
  -g fast_solve.gin singleroom.gin \
  -p compose_indoors.terrain_enabled=False \
     render_image.render_resolution_override=[768,576] \
  > /root/ig_render.log 2>&1
RC=$?
T1=$(date +%s)
LOG "render rc=$RC 用时 $((T1-T0)) 秒"
if [ $RC -ne 0 ]; then
  tail -18 /root/ig_render.log | sed 's/^/    /'
else
  du -sh /root/ig_probe/frames | sed 's/^/  产物 /'
  find /root/ig_probe/frames -type f | head -12 | sed 's/^/    /'
  echo "  文件数: $(find /root/ig_probe/frames -type f | wc -l)"
fi
touch /root/IGREND_DONE
