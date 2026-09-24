#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
LOG "r2016 @ px=2.625 (物理容差与 768@1.0 相同), geo_mask_thres=3"
/venv/main/bin/python /root/fuse_px.py /root/arm_ep0_r2016 3 /root/gate_M_2016_px2625.ply 2.625 2>&1 | tail -2
/venv/main/bin/python /root/ply2bins.py /root/gate_M_2016_px2625.ply /root/bins_gate M2016px2625 2>&1 | tail -1
touch /root/MID_DONE
