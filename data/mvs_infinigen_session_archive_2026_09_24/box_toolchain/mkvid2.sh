#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
rm -rf /root/orb2 && mkdir -p /root/orb2
LOG "渲染 180 帧: C(768@1.0) vs A(12MP@5.25) —— 物理容差相同, 唯一变量是分辨率"
/venv/main/bin/python -u /root/orbit2.py --out /root/orb2 --w 1400 --h 1050 --frames 180 \
  --pane "A  768 x 576    (current)::C768px1::/root/bins_gate" \
  --pane "B  4032 x 3008  (12MP, gate matched)::A12mp_px525::/root/bins_gate"
LOG "编码"
ffmpeg -y -loglevel error -framerate 24 -i /root/orb2/f%05d.png \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p /root/orb_gatematched.mp4
LOG "完成 $(ls -la /root/orb_gatematched.mp4 | awk "{printf \"%.1f MB\", \$5/1e6}")"
rm -rf /root/orb2; touch /root/VID2_DONE
