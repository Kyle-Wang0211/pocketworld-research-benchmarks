#!/bin/bash
# 对照: 空箱下再测一次 N=1 (第一次 N=1 是在 load 21-43 下测的), 确认并行结论不是负载假象
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*" | tee -a /root/igq7.log; }
P=/root/ig_venv2/bin/python; cd /root/infinigen
: > /root/igq7.log
d=/root/igq7/ctl; rm -rf $d; mkdir -p $d
LOG "对照 N=1 @768x576 空箱  开跑前 load=$(cut -d\" \" -f1-3 /proc/loadavg)  GPU=$(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader|tr \"\\n\" \" \")"
T0=$(date +%s)
$P -m infinigen_examples.generate_indoors --seed 0 --task render \
  --input_folder /root/igq2/coarse43 --output_folder $d/out \
  -g fast_solve.gin singleroom.gin -p compose_indoors.terrain_enabled=False \
  execute_tasks.generate_resolution=\(768,576\) get_sensor_coords.W=768 get_sensor_coords.H=576 \
  configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True \
  "full/render_image.passes_to_save=[]" > $d/log 2>&1
rc=$?; T1=$(date +%s)
LOG "  对照 N=1 rc=$rc 墙钟 $((T1-T0))s | $(grep -oE \"\\[Actual rendering\\] finished in [0-9:.]+\" $d/log|tail -1) | 收尾 load=$(cut -d\" \" -f1-3 /proc/loadavg)"
touch /root/IGQ7_DONE
