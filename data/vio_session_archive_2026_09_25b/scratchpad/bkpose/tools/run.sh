#!/bin/bash
# run.sh <tag> <scene 13f5|6d18|7353|fb5d> <bin base|tap> [extra runner args...]
# [bkpose 2026-09-25] 喂法逐项照抄 scratchpad/wobble/tools/run.sh(手机同款):box/3 → 640×480、
# 30 Hz 闸(0.8/R)、首个 IMU 之前的相机帧丢弃、逐帧 K、1× 实时节奏、曝光中点 t = PTS + exposure/2 + c
# (c = yaml cam0.time_offset = 0.003)。与另一个 agent 共用 scratchpad/.xrslam_run.lock(mkdir 锁),
# 两边的回放不会同时跑、不互相抢 CPU。
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
W=$SP/bkpose; R=$HOME/Developer/viobench-recordings
TAG=$1; SC=$2; BIN=$3; shift 3
SL=$W/cfg/slam_config.yaml; DEV=$W/cfg/dev_$SC.yaml; EXTRA=""
case $SC in
  13f5) RUN=$R/run-13f53d2f-5935-4b1a-a499-4dc8367ea935;;
  6d18) RUN=$R/run-6d187dff-403a-4882-b692-7bdc6c3cfa2a;;
  7353) RUN=$R/run-73538ad6-8418-4eaf-8b75-a63c9d32af46;;
  fb5d) RUN=$R/run-fb5d3a8f-6e31-463e-989d-bd73bb3a2def; EXTRA="--limit-frames 1060";;
  *) echo bad scene; exit 2;;
esac
BK=""; case "$BIN" in tap*) BK="--backend-out $W/runs/$TAG.backend.csv";; esac
L=$SP/.xrslam_run.lock
until mkdir $L 2>/dev/null; do sleep 3; done
echo "bkpose $$ $(date +%T) $TAG" > $L/owner
trap 'rm -f $L/owner; rmdir $L 2>/dev/null' EXIT
LOAD=$(sysctl -n vm.loadavg | awk '{print $2}')
echo "$TAG $SC bin=$BIN dev=$(basename $DEV) slam=$(basename $SL) $EXTRA $* loadavg1=$LOAD start=$(date +%T)" > $W/runs/$TAG.cmd
$W/v/$BIN/pwvi_runner $SL $DEV pwvi://$RUN $W/runs/$TAG.body.tum --downscale 3 --rate-hz 30 --rate-frac 0.8 --pace 1 \
   --drop-before-imu --intrinsics-jsonl --exposure-half $EXTRA --camera-out $W/runs/$TAG.cam.tum \
   --frame-map-out $W/runs/$TAG.map --hex-out $W/runs/$TAG.hex --keyed-out $W/runs/$TAG.keyed.csv $BK "$@" \
   > $W/runs/$TAG.log 2>&1
RC=$?
echo "end=$(date +%T) loadavg1_end=$(sysctl -n vm.loadavg | awk '{print $2}')" >> $W/runs/$TAG.cmd
echo "rc=$RC $TAG"; grep -E "^\[pwvi\]|=== " $W/runs/$TAG.log
