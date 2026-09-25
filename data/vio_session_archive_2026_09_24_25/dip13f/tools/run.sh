#!/bin/bash
# run.sh <tag> <variant> <scene 13f5|fb5d> [--log] [--dev <device.yaml>] [runner extra args...]
# Phone-matching replay: pwvi frames.bin, box/3 -> 640x480, 30 Hz gate with 0.8/R (PwXrslamOfficialFeed.admits),
# leading pre-IMU frames dropped, per-frame K, paced 1x. Under the shared xrslam lock.
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
W=$SP/dip13f; R=$HOME/Developer/viobench-recordings
TAG=$1; V=$2; SC=$3; shift 3
LOG=0; DEV=$W/cfg/device_config.yaml; SL=$W/cfg/slam_config.yaml; NOK=0
while [ $# -gt 0 ]; do
  case $1 in
    --log) LOG=1; shift;;
    --dev) DEV=$2; shift 2;;
    --slam) SL=$2; shift 2;;
    --no-k) NOK=1; shift;;
    *) break;;
  esac
done
case $SC in
  13f5) RUN=$R/run-13f53d2f-5935-4b1a-a499-4dc8367ea935;;
  fb5d) RUN=$R/run-fb5d3a8f-6e31-463e-989d-bd73bb3a2def;;
  *) echo bad scene; exit 2;;
esac
KARG=--intrinsics-jsonl; [ $NOK = 1 ] && KARG=
L=$SP/.xrslam_run.lock
until mkdir $L 2>/dev/null; do sleep 5; done
echo "dip13f $$ $(date +%T) $TAG" > $L/owner
trap 'rm -f $L/owner; rmdir $L 2>/dev/null' EXIT
if [ $LOG = 1 ]; then export PW_S3_LOG=$W/runs/$TAG.jsonl; else unset PW_S3_LOG; fi
$W/v/$V/pwvi_runner $SL $DEV pwvi://$RUN $W/runs/$TAG.body.tum --downscale 3 --rate-hz 30 --rate-frac 0.8 --pace 1 \
   --drop-before-imu $KARG --camera-out $W/runs/$TAG.cam.tum "$@" > $W/runs/$TAG.log 2>&1
echo "rc=$? $TAG"; grep -E "^\[pwvi\]|=== s3" $W/runs/$TAG.log
