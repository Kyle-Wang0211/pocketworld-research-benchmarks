#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
for p in t1_768:T1768 t1_2016:T12016; do
  f=${p%%:*}; t=${p##*:}
  [ -f /root/bins_gate/$t.pos ] || { LOG "转 bin $t"; /venv/main/bin/python /root/ply2bins.py /root/$f.ply /root/bins_gate $t 2>&1 | tail -1; }
done
LOG "覆盖率对照 (thres=3 vs thres=1, 同分辨率)"
/venv/main/bin/python -u cover2.py \
  C768px1=/root/bins_gate T1768=/root/bins_gate \
  M2016px2625=/root/bins_gate T12016=/root/bins_gate 2>&1 | tail -8
touch /root/T1COV_DONE
