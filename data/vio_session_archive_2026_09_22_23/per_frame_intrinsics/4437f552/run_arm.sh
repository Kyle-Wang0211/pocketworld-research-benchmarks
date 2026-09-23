#!/bin/bash
# run_arm.sh <runner> <dev.yaml> <euroc_dir> <out.tum> [kcsv]
set -e
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad
SLAM=$HOME/Developer/viobench-recordings/_sweep/slam_bench.yaml
R="$1"; DEV="$2"; DIR="$3"; OUT="$4"; K="${5:-}"
if [ -n "$K" ]; then
  "$R" "$SLAM" "$DEV" "euroc://$DIR" "$OUT" --intrinsics-csv "$K" 2>&1 | tail -14
else
  "$R" "$SLAM" "$DEV" "euroc://$DIR" "$OUT" 2>&1 | tail -14
fi
