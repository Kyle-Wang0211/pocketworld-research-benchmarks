#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
LOG "三档覆盖率 (物理容差全部相同)"
/venv/main/bin/python -u cover2.py C768px1=/root/bins_gate M2016px2625=/root/bins_gate A12mp_px525=/root/bins_gate 2>&1 | tail -6
LOG "渲三窗 180 帧"
rm -rf /root/orb3 && mkdir -p /root/orb3
/venv/main/bin/python -u /root/orbit2.py --out /root/orb3 --w 1200 --h 900 --frames 180 \
  --pane "A   768 x 576   (current)::C768px1::/root/bins_gate" \
  --pane "B  2016 x 1504::M2016px2625::/root/bins_gate" \
  --pane "C  4032 x 3008  (12MP)::A12mp_px525::/root/bins_gate" 2>&1 | tail -3
ffmpeg -y -loglevel error -framerate 24 -i /root/orb3/f%05d.png \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p /root/orb_ladder.mp4
LOG "完成 $(ls -la /root/orb_ladder.mp4 | awk "{printf \"%.1f MB\", \$5/1e6}")"
rm -rf /root/orb3; touch /root/LAD_DONE
