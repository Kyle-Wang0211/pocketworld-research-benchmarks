#!/bin/bash
# arm_M.sh <tag> <slam.yaml> <dev.yaml> <dataset_dir> <ref.tum>   -- M lineage runner (/tmp/pw_euroc_new, ~/Developer/xrslam@1fe750c build-pc)
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
S=$SP/scaleS2
TAG=$1; SL=$2; DV=$3; DS=$4; REF=$5
until mkdir $SP/.xrslam_run.lock 2>/dev/null; do sleep 5; done
t0=$(date +%s)
/tmp/pw_euroc_new $SL $DV euroc://$DS $S/runs/$TAG.body.tum > $S/runs/$TAG.log 2>&1
rc=$?
rmdir $SP/.xrslam_run.lock
t1=$(date +%s)
TD=$(grep -E "^\s*time_offset:" $DV | head -1 | awk '{print $2}')
/usr/bin/python3 $S/tools/ev.py $S/runs/$TAG.cam.tum $REF $TD "$TAG" "M|$(basename $SL)|$(basename $DV)|$(basename $DS)" $rc $((t1-t0)) >> $S/runs/results.jsonl
tail -1 $S/runs/results.jsonl
