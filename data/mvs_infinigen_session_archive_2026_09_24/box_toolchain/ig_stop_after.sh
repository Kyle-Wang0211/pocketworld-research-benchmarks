#!/bin/bash
# 等四档分辨率测完 -> 停掉一切 Infinigen 作业, 把 CPU 全让给训练。
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
while [ ! -f /root/IGR_DONE ]; do sleep 30; done
LOG "四档测完, 停 Infinigen"
pkill -f "generate_indoors" 2>/dev/null
pkill -f "ig_res.sh" 2>/dev/null
pkill -f "ig_sweep.sh" 2>/dev/null
sleep 3
LOG "残留 Infinigen 进程: $(pgrep -cf 'generate_indoors|ig_.*\.sh' || echo 0)"
LOG "训练: $(grep -oE 'Iter [0-9]+/150000' /root/train_ep0_skyfix.log | tail -1)"
touch /root/IG_STOPPED
