#!/bin/bash
# run_replays.sh — frame-5 replay arms on the SHIPPING core with the shipped GPU extractor (host Dawn/Metal).
# Takes the shared core lock (mkdir), waits while it exists, releases it at the end.
set -uo pipefail
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixD
L=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/.core_run.lock
until mkdir $L 2>/dev/null; do sleep 0.5; done
trap 'rmdir $L 2>/dev/null' EXIT
echo "lock acquired $(date)"
arm() {  # arm <label> <env...>
  local LAB=$1; shift
  local OUT=$W/runs/$LAB; rm -rf $OUT; mkdir -p $OUT/live
  local kb; kb=$(df -k /private/tmp | tail -1 | awk '{print $4}')
  [ "$kb" -lt $((2048*1024)) ] && { echo "STOP disk < 2GiB"; return 90; }
  env -i HOME=$W/home PATH=/usr/bin:/bin OFFICIAL_AETHER_LIVE_POSE_DUMP=$OUT/live FIXD_DECODE=cg "$@" \
    /usr/bin/time -l $W/build/fixd_replay_driver JPEG $W/inputs/feed_f5.jsonl $OUT > $OUT/run.log 2>&1
  echo "$LAB rc=$? $(grep -E '^RESULT' $OUT/run.log | cut -c1-200)"
}
arm G_fused   FIXD_GPU_EXTRACT=1
arm G_2pass   FIXD_GPU_EXTRACT=1 OFFICIAL_AETHER_GSS_FUSED=0
arm G_faultf5 FIXD_GPU_EXTRACT=1 FI_FRAME=5 "FI_SPEC=2:1152:4032:0:3024;3:1152:4032:0:3024;4:1152:4032:0:3024"
echo "done $(date)"
