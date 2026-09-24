#!/bin/bash
# run_arm_pdb.sh <feed_name> <cap_id> <run_label> [env...] — live route replay with the capture's OWN db features
# (driver PHONEDB mode; db opened read-only immutable=1; dataless-checked here first).
set -uo pipefail
B=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
FEED=$1; CAP=$2; LAB=$3; shift 3
DB=$(/usr/bin/python3 -c "import json;print({r['cap']:r for r in json.load(open('$B/results/phone_gate/phone_gate.json'))['rows']}['$CAP']['dir']+'/official_sfm_live.db')")
case "$(/usr/bin/stat -f %Sf "$DB")" in *dataless*) echo "dataless $DB"; exit 8;; esac
OUT=$B/runs/$LAB; rm -rf "$OUT"; mkdir -p $OUT/live
avail_kb=$(df -k ~ | tail -1 | awk '{print $4}'); [ "$avail_kb" -lt $((1536*1024)) ] && { echo "STOP: disk < 1.5GiB"; exit 90; }
env -i HOME=$HOME PATH=/usr/bin:/bin OFFICIAL_AETHER_LIVE_POSE_DUMP=$OUT/live ${@+"$@"} \
  /usr/bin/time -l $B/build/pwofficial_pose_ab_driver "PHONEDB:$DB" "$B/inputs/feed_${FEED}.jsonl" $OUT > $OUT/run.log 2>&1
rc=$?
rm -f $OUT/session.db $OUT/session.db-* 2>/dev/null
echo "$LAB rc=$rc $(grep -E '^DEVICE_ALIGN' $OUT/run.log) | $(grep -E '^RESULT' $OUT/run.log | cut -c1-160)"
