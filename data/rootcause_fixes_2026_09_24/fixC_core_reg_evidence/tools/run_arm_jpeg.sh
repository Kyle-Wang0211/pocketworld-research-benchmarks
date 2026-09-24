#!/bin/bash
# run_arm_jpeg.sh <feed_name> <run_label> [driver args / env assignments...] — run_arm.sh with the JPEG-mode driver input.
set -uo pipefail
B=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
FEED=$1; LAB=$2; shift 2
ENVS=(); ARGS=()
for a in "$@"; do case "$a" in --*) ARGS+=("$a");; *) ENVS+=("$a");; esac; done
OUT=$B/runs/$LAB; rm -rf "$OUT"; mkdir -p $OUT/live
avail_kb=$(df -k ~ | tail -1 | awk '{print $4}')
[ "$avail_kb" -lt $((1536*1024)) ] && { echo "STOP: disk < 1.5GiB"; exit 90; }
env -i HOME=$HOME PATH=/usr/bin:/bin OFFICIAL_AETHER_LIVE_POSE_DUMP=$OUT/live ${ENVS[@]+"${ENVS[@]}"} \
  /usr/bin/time -l $B/build/pwofficial_pose_ab_driver JPEG "$B/inputs/feed_${FEED}.jsonl" $OUT ${ARGS[@]+"${ARGS[@]}"} > $OUT/run.log 2>&1
rc=$?
rm -f $OUT/session.db $OUT/session.db-* 2>/dev/null
echo "$LAB rc=$rc $(grep -E '^DEVICE_ALIGN' $OUT/run.log) | $(grep -E '^RESULT' $OUT/run.log | cut -c1-160)"
