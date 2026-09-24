#!/bin/bash
# run_mac.sh <feed> <label> [env...] — one Mac-recording run under the shared lock, metrics, >5MB cleanup.
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
FEED=$1; LAB=$2; shift 2
$W/tools/locked.sh $W/tools/run_arm.sh $FEED $LAB "$@" || { echo "run failed/skipped $LAB"; exit 1; }
FF=$W/inputs/feed_${FEED}.jsonl; [ -f "$FF" ] || FF=$W/base_sfmB/inputs/feed_${FEED}.jsonl
/usr/bin/python3 $W/tools/fixc_metrics.py $W/runs/$LAB mac $FF 2>&1 | tail -3
$W/tools/clean_big.sh $W/runs/$LAB
