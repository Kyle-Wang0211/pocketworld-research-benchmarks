#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
rm -rf /root/orb && mkdir -p /root/orb
LOG "渲染 180 帧 (两臂全量, 同机位)"
/venv/main/bin/python -u /root/orbit.py --mode video --out /root/orb --w 1400 --h 1050 --frames 180
LOG "ffmpeg 编码"
ffmpeg -y -loglevel error -framerate 24 -i /root/orb/f%05d.png \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p /root/orb_12mp_vs_768.mp4
LOG "完成: $(ls -la /root/orb_12mp_vs_768.mp4 | awk "{printf \"%.1f MB\", \$5/1e6}")"
rm -rf /root/orb
touch /root/VID_DONE
