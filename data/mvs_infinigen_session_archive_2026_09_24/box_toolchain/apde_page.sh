#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
LOG "转 bin (BGR 版)"
/venv/main/bin/python /root/ply2bins_bgr.py /root/mvs_P16k/APD/APD.ply /root/bins_gate APDE12mp 2>&1 | tail -3
LOG "覆盖率"
/venv/main/bin/python -u cover2.py C768px1=/root/bins_gate APDE12mp=/root/bins_gate 2>&1 | tail -5
LOG "渲双窗 180 帧"
rm -rf /root/orb4 && mkdir -p /root/orb4
/venv/main/bin/python -u /root/orbit2.py --out /root/orb4 --w 1400 --h 1050 --frames 180 \
  --pane "A  CasDiffMVS  768x576::C768px1::/root/bins_gate" \
  --pane "B  APDe-MVS  4032x3024 native::APDE12mp::/root/bins_gate" 2>&1 | tail -2
ffmpeg -y -loglevel error -framerate 24 -i /root/orb4/f%05d.png \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p /root/orb_apde.mp4
LOG "完成 $(ls -la /root/orb_apde.mp4 | awk "{printf \"%.1f MB\", \$5/1e6}")"
rm -rf /root/orb4; touch /root/APDE_PAGE_DONE
