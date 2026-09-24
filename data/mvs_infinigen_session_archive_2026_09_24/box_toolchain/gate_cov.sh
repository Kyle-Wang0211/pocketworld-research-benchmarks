#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
LOG "转 bin (4.6 亿点)"
/venv/main/bin/python /root/ply2bins.py /root/gate_A_12mp_px525.ply /root/bins_gate A12mp_px525 2>&1 | tail -2
ls -la /root/bins_gate/A12mp_px525.* | awk '{printf "  %.2f GB  %s\n", $5/1e9, $9}'
LOG "整圈覆盖 (36 机位)"
cd /root && /venv/main/bin/python -u cover2.py \
  C768px1=/root/bins_gate B768px019=/root/bins_gate \
  ep0_12mp=/root/bins_12mp A12mp_px525=/root/bins_gate 2>&1 | tail -10
touch /root/COV_DONE
