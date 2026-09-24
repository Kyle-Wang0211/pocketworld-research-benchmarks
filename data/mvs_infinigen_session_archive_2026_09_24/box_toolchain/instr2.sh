#!/bin/bash
set -u
cd /root
mkdir -p bins_instr
for a in office_lo office_hi delivery_area_lo delivery_area_hi; do
  [ -f /root/bins_instr/$a.pos ] || /venv/main/bin/python /root/ply2bins.py /root/eth_out2/$a/pc.ply /root/bins_instr $a 2>&1 | tail -1
done
