#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
rm -rf /root/orb5 && mkdir -p /root/orb5
LOG "渲 768 两档: thres=3 (现有) vs thres=1 (官方 ETH3D 口径)"
/venv/main/bin/python -u /root/orbit2.py --out /root/orb5 --w 1400 --h 1050 --frames 180 \
  --pane "A  768  geo_mask_thres=3  (current)::C768px1::/root/bins_gate" \
  --pane "B  768  geo_mask_thres=1  (official ETH3D)::T1768::/root/bins_gate" 2>&1 | tail -2
ffmpeg -y -loglevel error -framerate 24 -i /root/orb5/f%05d.png \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p /root/orb_thres.mp4
LOG "完成 $(ls -la /root/orb_thres.mp4 | awk "{printf \"%.1f MB\", \$5/1e6}")"
rm -rf /root/orb5; touch /root/T1VID_DONE
