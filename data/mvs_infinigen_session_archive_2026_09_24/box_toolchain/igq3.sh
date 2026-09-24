#!/bin/bash
# D. 单卡并行 N 路 Blender 的总吞吐 + 显存 ; E. CPU coarse 与 GPU render 重叠
set -u
W=${1:-768}; H=${2:-576}
LOG(){ echo "[$(date +%H:%M:%S)] $*" | tee -a /root/igq3.log; }
P=/root/ig_venv2/bin/python
cd /root/infinigen
COARSE=/root/igq2/coarse43
COMMON="-g fast_solve.gin singleroom.gin -p compose_indoors.terrain_enabled=False"
QUAL="configure_render_cycles.num_samples=8192 configure_render_cycles.denoise=True"
RES="execute_tasks.generate_resolution=($W,$H) get_sensor_coords.W=$W get_sensor_coords.H=$H"
: > /root/igq3.log; mkdir -p /root/igq3

one(){
  $P -m infinigen_examples.generate_indoors --seed 0 --task render \
     --input_folder $COARSE --output_folder $1/out $COMMON $QUAL $RES \
     "full/render_image.passes_to_save=[]" > $1/log 2>&1
  echo $? > $1/rc
}

par(){
  local N
  N=$1
  local d
  d=/root/igq3/n$N
  rm -rf $d; mkdir -p $d; : > $d/gpu.csv
  ( while :; do nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader >> $d/gpu.csv; sleep 2; done ) &
  local MON=$!
  local PIDS=""
  local T0; T0=$(date +%s)
  local i
  for i in $(seq 1 $N); do mkdir -p $d/s$i; one $d/s$i & PIDS="$PIDS $!"; done
  for p in $PIDS; do wait $p; done
  local T1; T1=$(date +%s)
  kill $MON 2>/dev/null; wait $MON 2>/dev/null
  local WALL=$((T1-T0))
  local RCS; RCS=$(cat $d/s*/rc 2>/dev/null | tr '\n' ',')
  local PEAK; PEAK=$(awk -F',' '{gsub(/ MiB/,"",$1); if($1+0>m) m=$1+0} END{print m+0}' $d/gpu.csv)
  local MEANU; MEANU=$(awk -F',' '{gsub(/ %/,"",$2); s+=$2+0; n++} END{if(n)printf "%.0f", s/n; else print 0}' $d/gpu.csv)
  local ARS; ARS=$(for i in $(seq 1 $N); do grep -oE "\[Actual rendering\] finished in [0-9:.]+" $d/s$i/log 2>/dev/null | tail -1 | grep -oE "[0-9:.]+$"; done | tr '\n' ' ')
  LOG "  N=$N 墙钟 ${WALL}s => $(awk "BEGIN{printf \"%.1f\", $N*3600/$WALL}") 帧/小时 (单路等效 $(awk "BEGIN{printf \"%.1f\", $WALL/$N}")s/帧) | rc=$RCS | 显存峰 ${PEAK}MiB | GPU均值 ${MEANU}% | 各路: $ARS"
}

LOG "D. 单卡并行吞吐 @ ${W}x${H}, 8192+去噪, passes_to_save=[]"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | sed 's/^/     卡: /' | tee -a /root/igq3.log
LOG "   基线: $(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader | tr '\n' ' ') | 系统负载 $(cut -d' ' -f1-3 /proc/loadavg)"
par 1
par 2
par 3
par 4
LOG "   收尾负载 $(cut -d' ' -f1-3 /proc/loadavg)"

LOG "E. CPU coarse 与 GPU render 重叠 (对照 = 上面的 N=1)"
rm -rf /root/igq3/ov; mkdir -p /root/igq3/ov/s1
T0=$(date +%s)
nice -n 5 $P -m infinigen_examples.generate_indoors --seed 7 --task coarse \
   --output_folder /root/igq3/ov/coarse $COMMON $RES > /root/igq3/ov/coarse.log 2>&1 &
CO=$!
one /root/igq3/ov/s1
T1=$(date +%s)
LOG "  重叠时 GPU 单路: $((T1-T0))s | $(grep -oE '\[Actual rendering\] finished in [0-9:.]+' /root/igq3/ov/s1/log|tail -1)"
wait $CO; CRC=$?; T2=$(date +%s)
LOG "  同时跑的 coarse rc=$CRC 总 $((T2-T0))s"
touch /root/IGQ3_DONE
LOG "== PHASE D/E DONE =="
