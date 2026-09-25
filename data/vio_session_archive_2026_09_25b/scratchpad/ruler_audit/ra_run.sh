#!/bin/bash
# ra_run.sh <tag> <scene> <mix all|none> <acc_ms> <td_ms> [extra runner args...]
# 只读调用积分 agent 的回放器(preint/v/mixas_nothr,单线程),喂法与 preint/tools/run.sh + batch_scale.sh 逐项相同;
# 产物写到 ruler_audit/fx_runs/;遵守共享锁 scratchpad/.xrslam_run.lock。
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
W=$SP/preint; R=$HOME/Developer/viobench-recordings; O=$SP/ruler_audit/fx_runs
TAG=$1; SC=$2; MIX=$3; A=$4; D=$5; shift 5
case $SC in
  13f5) RUN=$R/run-13f53d2f-5935-4b1a-a499-4dc8367ea935;;
  6d18) RUN=$R/run-6d187dff-403a-4882-b692-7bdc6c3cfa2a;;
  7353) RUN=$R/run-73538ad6-8418-4eaf-8b75-a63c9d32af46;;
esac
L=$SP/.xrslam_run.lock
until mkdir $L 2>/dev/null; do sleep 0.3; done
echo "ruler_audit $$ $(date +%T) $TAG" > $L/owner
trap 'rm -f $L/owner; rmdir $L 2>/dev/null' EXIT
if [ $MIX = all ]; then ENVP="env -u PW_MIX_NEW -u PW_DIAG_LOG"; else ENVP="env -u PW_DIAG_LOG PW_MIX_NEW=none"; fi
echo "$TAG $SC mix=$MIX acc=$A td=$D $* start=$(date +%T)" > $O/$TAG.cmd
$ENVP $W/v/mixas_nothr/pwvi_runner $W/cfg/slam_config.yaml $W/cfg/dev_$SC.yaml pwvi://$RUN $O/$TAG.body.tum \
   --downscale 3 --rate-hz 30 --rate-frac 0.8 --pace 1 --drop-before-imu --intrinsics-jsonl --exposure-half \
   --camera-out $O/$TAG.cam.tum --frame-map-out $O/$TAG.map --hex-out $O/$TAG.hex --keyed-out $O/$TAG.keyed.csv \
   --backend-out $O/$TAG.backend.csv --pace 0 --acc-shift-ms $A --td-extra-ms $D "$@" > $O/$TAG.log 2>&1
echo "rc=$? $TAG end=$(date +%T)" | tee -a $O/$TAG.cmd
