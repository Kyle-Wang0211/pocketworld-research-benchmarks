#!/bin/bash
# 杠杆 1 的精度守卫:等 lever1 直播链结束 → 回放同一录制 @640×480(-PWDiagnosticDownscale),thrbp+freq2,bench 闸开 → ATE/尺度 vs ARKit 轨迹
set -u; S=$(cd "$(dirname "$0")" && pwd); R=~/Developer/viobench-recordings; E=$R/eval-xrslam-threading-backpressure-20260903
CH=$(ls -t "$E"/chain_lever1_[0-9]*.log | head -1); n=0
until grep -q "lever1 chain end" "$CH"; do n=$((n+1)); [ $n -ge 360 ] && { echo "等 lever1 超时"; exit 1; }; sleep 5; done
echo "lever1 ended $(date '+%T'); replay start"
"$S/pw_run_arm.sh" S3r-thrbp-replay640-freq2 replay-device-recording -PWDiagnosticDownscale -PWTrackerFrequent 2
RUN=$(grep -oE "run=run-[a-f0-9-]{36}" "$(ls -t "$E"/S3r-thrbp-replay640-freq2_*.log | head -1)" | tail -1 | cut -d= -f2)
REF=$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum
[ -f "$R/$RUN/poses.tum" ] && { echo "── ATE/scale vs ARKit (ate.py) ──"; python3 "$R/ate.py" "$R/$RUN/poses.tum" "$REF" 2>&1 | tail -8; }
echo "lever1-replay chain end $(date '+%F %T')"
