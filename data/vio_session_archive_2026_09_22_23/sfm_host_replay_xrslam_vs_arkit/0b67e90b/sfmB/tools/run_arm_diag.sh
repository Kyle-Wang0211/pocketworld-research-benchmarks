#!/bin/bash
# run_arm_diag.sh <subset> <arm> — same as run_arm.sh plus the core's own host-only,
# observation-only live dump (official_aether_sfm_c.cc:10536-10560, 11418-11430).
set -uo pipefail
B=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sfmB
FR=/Users/kaidongwang/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/frames.bin
SUB=$1; ARM=$2; OUT=$B/runs/diag_${SUB}_${ARM}; mkdir -p $OUT/live
avail_kb=$(df -k ~ | tail -1 | awk '{print $4}')
[ "$avail_kb" -lt $((1536*1024)) ] && { echo "STOP: disk < 1.5GiB"; exit 90; }
env -i HOME=$HOME PATH=/usr/bin:/bin OFFICIAL_AETHER_LIVE_POSE_DUMP=$OUT/live \
  $B/build/pwofficial_pose_ab_driver "$FR" $B/inputs/feed_${SUB}_${ARM}.jsonl $OUT > $OUT/run.log 2>&1
echo "rc=$? $(grep -E '^RESULT' $OUT/run.log)"
