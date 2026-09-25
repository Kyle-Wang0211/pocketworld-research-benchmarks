#!/bin/bash
# run2.sh <tag> <scene 13f5|fb5d|6e2d|5966|4ad6> [--log] [--dev yaml] [--slam yaml] [runner args...]
# = run.sh with pwvi_runner2 (adds --limit-frames) and per-scene defaults. Phone-matching feed:
# box/3 -> 640x480, 30 Hz gate with 0.8/R, pre-IMU frames dropped, per-frame K, paced 1x.
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
W=$SP/dip13f; R=$HOME/Developer/viobench-recordings
TAG=$1; SC=$2; shift 2
LOG=0; SL=$W/cfg/slam_config.yaml; DEV=""; EXTRA=""
case $SC in
  13f5) RUN=$R/run-13f53d2f-5935-4b1a-a499-4dc8367ea935; DEV=$W/cfg/device_config.yaml;;
  fb5d) RUN=$R/run-fb5d3a8f-6e31-463e-989d-bd73bb3a2def; DEV=$W/cfg/dev_fb5d.yaml; EXTRA="--limit-frames 1060";;
  6e2d) RUN=$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18; DEV=$W/cfg/dev_6e2d.yaml;;
  5966) RUN=$R/run-5966aec0-cbf1-4abc-af0e-c1fc559da44c; DEV=$W/cfg/dev_5966.yaml;;
  4ad6) RUN=$R/run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa; DEV=$W/cfg/dev_4ad6.yaml;;
  *) echo bad scene; exit 2;;
esac
while [ $# -gt 0 ]; do
  case $1 in
    --log) LOG=1; shift;;
    --dev) DEV=$2; shift 2;;
    --slam) SL=$2; shift 2;;
    *) break;;
  esac
done
L=$SP/.xrslam_run.lock
until mkdir $L 2>/dev/null; do sleep 5; done
echo "dip13f $$ $(date +%T) $TAG" > $L/owner
trap 'rm -f $L/owner; rmdir $L 2>/dev/null' EXIT
if [ $LOG = 1 ]; then export PW_S3_LOG=$W/runs/$TAG.jsonl; else unset PW_S3_LOG; fi
echo "$TAG $SC dev=$(basename $DEV) slam=$(basename $SL) $EXTRA $*" > $W/runs/$TAG.cmd
$W/v/inst/pwvi_runner2 $SL $DEV pwvi://$RUN $W/runs/$TAG.body.tum --downscale 3 --rate-hz 30 --rate-frac 0.8 --pace 1 \
   --drop-before-imu --intrinsics-jsonl $EXTRA --camera-out $W/runs/$TAG.cam.tum "$@" > $W/runs/$TAG.log 2>&1
echo "rc=$? $TAG"; grep -E "^\[pwvi\]|=== s3" $W/runs/$TAG.log
