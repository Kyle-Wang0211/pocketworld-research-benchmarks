#!/bin/bash
set -u
rm -rf /root/orb6 && mkdir -p /root/orb6
/venv/main/bin/python -u /root/orbit2.py --out /root/orb6 --w 1400 --h 1050 --frames 180 \
  --pane "A   768 x  576  (training res)::T1768::/root/bins_gate" \
  --pane "B  2048 x 1536  (official scale)::T1_2048::/root/bins_gate" 2>&1 | tail -2
ffmpeg -y -loglevel error -framerate 24 -i /root/orb6/f%05d.png \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p /root/orb_2048.mp4
echo "完成 $(ls -la /root/orb_2048.mp4 | awk "{printf \"%.1f MB\", \$5/1e6}")"
rm -rf /root/orb6; touch /root/V2048_DONE
