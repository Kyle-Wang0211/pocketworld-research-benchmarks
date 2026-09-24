#!/bin/bash
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
cd /root
LOG "造阴性对照臂 (随机抽稀 thres=2 到 28,213,257 点)"
/venv/main/bin/python /root/nullctl.py
LOG "四档同口径量尺子"
/venv/main/bin/python -u /root/layerruler.py --bins /root/bins_gm --tags GM_t2 GM_t3 GM_dyn GM_rnd 2>&1 | grep -vE "less ref_view"
LOG "渲三档静图 (t2 / t3 / dyn)"
/venv/main/bin/python -u /root/orbit_gm3.py 2>&1 | tail -8
touch /root/NULL_DONE
