#!/bin/bash
# tracker_frequent=2 的回放精度再取两个样本(线程非确定性),每场后算 ATE
set -u; S=$(cd "$(dirname "$0")" && pwd); R=~/Developer/viobench-recordings; E=$R/eval-xrslam-threading-backpressure-20260903
for k in 2 3; do
  "$S/pw_run_arm.sh" "S4r${k}-thrbp-replay1920-freq2" replay-device-recording -PWTrackerFrequent 2 | grep -E "run=|poses=|processed_fps" | head -3
  RUN=$(grep -oE "run=run-[a-f0-9-]{36}" "$(ls -t "$E"/S4r${k}-*.log | head -1)" | tail -1 | cut -d= -f2)
  echo "S4r${k} ATE: $("$S/pw_ate.sh" "$R/$RUN")"; sleep 20
done
echo "freq2 samples end $(date '+%F %T')"
