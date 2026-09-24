#!/bin/bash
# 同一个 ckpt 再推一遍, 与今早那份比 —— 量的是 layer_gap2 这把尺子的【重跑噪声地板】。
# 今早报的 ep0..ep4 差值(白墙 >0.1m 从 6.34% 到 9.10%)只有在远大于地板时才成立。
set -u
if [ "$(ls /root/lg_ep0b/depth_est 2>/dev/null | wc -l)" != "132" ]; then
  echo "[$(date +%H:%M:%S)] 用同一个 full_ep0.ckpt 再推一遍 -> /root/lg_ep0b"
  /root/infer_arm.sh /root/snap_ckpt/full_ep0.ckpt /root/lg_ep0b > /root/lg_ep0b.infer.log 2>&1
  echo "  rc=$? depth=$(ls /root/lg_ep0b/depth_est 2>/dev/null | wc -l)"
fi
echo "[$(date +%H:%M:%S)] 同权重两次推理的 layer_gap2 (= 噪声地板)"
/venv/main/bin/python /root/layer_gap_eps.py ep0_run1=/root/lg_ep0 ep0_run2=/root/lg_ep0b
echo DONE; touch /root/NF.DONE
