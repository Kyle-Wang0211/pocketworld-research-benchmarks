#!/bin/bash
set -u
if [ "$(ls /root/lg_ep5/depth_est 2>/dev/null | wc -l)" != "132" ]; then
  echo "[$(date +%H:%M:%S)] ep5 推理"
  /root/infer_arm.sh /root/snap_ckpt/full_ep5.ckpt /root/lg_ep5 > /root/lg_ep5.infer.log 2>&1
  echo "  rc=$? depth=$(ls /root/lg_ep5/depth_est 2>/dev/null | wc -l)"
fi
echo "[$(date +%H:%M:%S)] 六个 epoch 同口径量多层"
/venv/main/bin/python /root/layer_gap_eps.py \
  ep0=/root/lg_ep0 ep1=/root/lg_ep1 ep2=/root/lg_ep2 ep3=/root/lg_ep3 ep4=/root/lg_ep4 ep5=/root/lg_ep5
echo DONE; touch /root/LG5.DONE
