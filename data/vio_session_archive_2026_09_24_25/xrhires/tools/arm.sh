#!/bin/bash
# [xrhires] arm.sh <tag> <slam.yaml> <dev.yaml> <scene 6e2d|5966|4ad6> <res 640|960|1280|1920> <pace> "<ENV=.. ENV=..>|-" [runner extra args...]
# Copy of xrofficial/tools/arm.sh (frames.bin direct, production 30 Hz admission rule, per-frame K,
# scored with scaleS1 scale_eval.py via scaleS2 ev.py) + resolution selection + PW_* env + zone stats.
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
W=$SP/xrhires; R=$HOME/Developer/viobench-recordings
TAG=$1; SL=$2; DV=$3; SC=$4; RES=$5; PACE=$6; ENVS=$7; shift 7
case $SC in
  6e2d) RUN=$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18;;
  5966) RUN=$R/run-5966aec0-cbf1-4abc-af0e-c1fc559da44c;;
  4ad6) RUN=$R/run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa;;
  *) echo bad scene; exit 2;;
esac
case $RES in
  640) RA="--downscale 3";; 960) RA="--downscale 2";; 1280) RA="--resize 1280x960";; 1920) RA="--downscale 1";;
  *) echo bad res; exit 2;;
esac
[ "$ENVS" = "-" ] && ENVS=""
if grep -q "\"tag\": \"$TAG\", .*\"rc\": 0" $W/runs/results.jsonl 2>/dev/null; then echo "skip $TAG (done)"; exit 0; fi
for i in $(seq 1 120); do
  FREE=$(df -k /System/Volumes/Data | tail -1 | awk '{print $4}')
  [ "$FREE" -ge 2097152 ] && break
  [ $i = 1 ] && echo "DISK<2GiB ($FREE KiB) -> waiting before $TAG"
  sleep 10
done
if [ "$FREE" -lt 2097152 ]; then echo "DISK<2GiB ($FREE KiB) -> abort $TAG"; exit 3; fi
REF=$RUN/arkit_poses.tum
until mkdir $SP/.xrslam_run.lock 2>/dev/null; do sleep 5; done
echo "xrhires $$ $(date +%T) $TAG" > $SP/.xrslam_run.lock/owner
t0=$(date +%s)
env $ENVS $W/v/hr/pwvi_runner $SL $DV pwvi://$RUN $W/runs/$TAG.body.tum $RA --rate-hz 30 --pace $PACE --intrinsics-jsonl \
   --camera-out $W/runs/$TAG.cam.tum --zone-stats $W/runs/$TAG.zones.jsonl --feed-ms-out $W/runs/$TAG.feed.txt "$@" > $W/runs/$TAG.log 2>&1
rc=$?
rm -f $SP/.xrslam_run.lock/owner; rmdir $SP/.xrslam_run.lock
t1=$(date +%s)
TD=$(grep -E "^\s*time_offset:" $DV | head -1 | awk '{print $2}')
/usr/bin/python3 $SP/scaleS2/tools/ev.py $W/runs/$TAG.cam.tum $REF $TD "$TAG" "hr|$(basename $SL)|$(basename $DV)|$SC|$RES|pace$PACE|$ENVS|$*" $rc $((t1-t0)) >> $W/runs/results.jsonl
tail -1 $W/runs/results.jsonl | /usr/bin/python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d['tag'], 'rc',d['rc'],'sec',d['sec'],'n',d.get('n'),'k=%.4f'%(d.get('k_sim3_fwd') or 0), 'ci',[round(x,4) for x in (d.get('k_sim3_fwd_ci95') or [])], 'ate_sim3 %.2fcm'%(d.get('ate_sim3_cm') or 0), d.get('err',''))"
