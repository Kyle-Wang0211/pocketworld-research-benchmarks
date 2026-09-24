#!/bin/bash
# run_phone.sh <jpeg|resume> <feed_or_cap> <cap_id> <label> <untrusted-list or -> [env...]
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
MODE=$1; FEED=$2; CAP=$3; LAB=$4; UT=$5; shift 5
if [ "$MODE" = jpeg ]; then
  $W/tools/locked.sh $W/tools/run_arm_jpeg.sh $FEED $LAB "$@" || { echo "run failed/skipped $LAB"; exit 1; }
  FF=$W/inputs/feed_${FEED}.jsonl
else
  if [ "$UT" != "-" ]; then export UNTRUSTED=$UT; fi
  $W/tools/locked.sh $W/tools/run_arm_resume.sh $CAP $LAB "$@" || { echo "run failed/skipped $LAB"; exit 1; }
  FF=$W/inputs/feed_rs_${CAP}.jsonl
fi
UA=""; [ "$UT" != "-" ] && UA="--untrusted=$UT"
/usr/bin/python3 $W/tools/fixc_metrics.py $W/runs/$LAB phone $FF $CAP $UA 2>&1 | tail -3
$W/tools/clean_big.sh $W/runs/$LAB
