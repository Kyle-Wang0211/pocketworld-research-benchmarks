#!/bin/bash
# run_arm.sh <feed_name> <run_label> [extra env assignments...]
# Same invocation as sfmB/tools/run_arm_diag.sh (env -i, frames.bin, driver args);
# only the binary (step2 build with DEVICE-ALIGN-V1) and output dir differ.
set -uo pipefail
B=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/step2
FR=${FRAMES_BIN:-/Users/kaidongwang/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/frames.bin}
FEED=$1; LAB=$2; shift 2
OUT=$B/runs/$LAB; rm -rf "$OUT"; mkdir -p $OUT/live
avail_kb=$(df -k ~ | tail -1 | awk '{print $4}')
[ "$avail_kb" -lt $((3*1024*1024)) ] && { echo "STOP: disk < 3GiB"; exit 90; }
FEEDF=$B/inputs/feed_${FEED}.jsonl; [ -f "$FEEDF" ] || FEEDF=$B/base_sfmB/inputs/feed_${FEED}.jsonl
env -i HOME=$HOME PATH=/usr/bin:/bin OFFICIAL_AETHER_LIVE_POSE_DUMP=$OUT/live "$@" \
  /usr/bin/time -l $B/build/pwofficial_pose_ab_driver "$FR" "$FEEDF" $OUT > $OUT/run.log 2>&1
rc=$?
rm -f $OUT/session.db $OUT/session.db-* 2>/dev/null
echo "$LAB rc=$rc $(grep -E '^DEVICE_ALIGN' $OUT/run.log) | $(grep -E '^RESULT' $OUT/run.log | cut -c1-120)"
