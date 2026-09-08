#!/bin/bash
# S4r:等 S3r 回放链结束 → 全分辨率回放 + freq2(bench 闸开)→ 与 freq1 基线比,归因 tracker_frequent 的精度代价
set -u; S=$(cd "$(dirname "$0")" && pwd); E=~/Developer/viobench-recordings/eval-xrslam-threading-backpressure-20260903
CH=$(ls -t "$E"/chain_lever1_replay_*.log | head -1); n=0
until grep -q "lever1-replay chain end" "$CH"; do n=$((n+1)); [ $n -ge 480 ] && { echo "等 S3r 超时"; exit 1; }; sleep 5; done
echo "S3r ended $(date '+%T'); S4r start"
"$S/pw_run_arm.sh" S4r-thrbp-replay1920-freq2 replay-device-recording -PWTrackerFrequent 2
echo "s4r chain end rc=$? $(date '+%F %T')"
