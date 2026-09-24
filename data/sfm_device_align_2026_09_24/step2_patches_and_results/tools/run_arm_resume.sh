#!/bin/bash
# run_arm_resume.sh <cap_id> <run_label> [env assignments...] — [TASKB-RESUME] re-finalize a phone capture from a COPY
# of its db + ARKit pose store through the core's own resume route. Source copied with sqlite's online backup from an
# immutable=1 read-only handle (capture dir never written); every source file stat'ed for 'dataless' first.
set -uo pipefail
B=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/step2
CAP=$1; LAB=$2; shift 2
OUT=$B/runs/$LAB; rm -rf "$OUT"; mkdir -p $OUT/live
avail_kb=$(df -k ~ | tail -1 | awk '{print $4}'); [ "$avail_kb" -lt $((1536*1024)) ] && { echo "STOP: disk < 1.5GiB"; exit 90; }
/usr/bin/python3 - "$CAP" "$OUT" "$B" <<'PY'
import json, os, sqlite3, subprocess, sys, shutil
cap, out, B = sys.argv[1:4]
d = {r['cap']: r for r in json.load(open(B + '/results/phone_gate/phone_gate.json'))['rows']}[cap]['dir']
def ok(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    if r.returncode != 0 or 'dataless' in r.stdout: raise SystemExit('dataless/missing ' + p)
    return p
src = sqlite3.connect(f'file:{ok(d + "/official_sfm_live.db")}?immutable=1', uri=True)
dst = sqlite3.connect(out + '/session.db'); src.backup(dst); dst.close(); src.close()
shutil.copyfile(ok(d + '/official_sfm_live.db.arkit_pose_v1'), out + '/session.db.arkit_pose_v1')
fed = [json.loads(l) for l in open(ok(d + '/official_sfm_fed_frames.jsonl'))]
with open(B + f'/inputs/feed_rs_{cap}.jsonl', 'w') as f:
    for j in fed:
        f.write(json.dumps({'frameIndex': j['frameId'], 'byteOffset': 0, 'w': j['grayW'], 'h': j['grayH'], 'fxfycxcy': [1, 1, 1, 1],
                            'arkitCamFromWorldQwxyz': j['arkitCamFromWorldQwxyz'], 'arkitCamFromWorldTxyz': j['arkitCamFromWorldTxyz']}) + '\n')
PY
env -i HOME=$HOME PATH=/usr/bin:/bin OFFICIAL_AETHER_LIVE_POSE_DUMP=$OUT/live ${@+"$@"} \
  /usr/bin/time -l $B/build/pwofficial_pose_ab_driver RESUME "$B/inputs/feed_rs_${CAP}.jsonl" $OUT > $OUT/run.log 2>&1
rc=$?
rm -f $OUT/session.db $OUT/session.db-* 2>/dev/null
echo "$LAB rc=$rc $(grep -E '^DEVICE_ALIGN' $OUT/run.log) | $(grep -E '^RESULT|^FINALIZE_ASYNC' $OUT/run.log | cut -c1-200 | tr '\n' ' ')"
