#!/bin/bash
# advio_run.sh NN : replay ADVIO NN (prepared by advio_prep.py) through S and M, frames streamed from the
# official H.264 mov via ffmpeg (autorotate to portrait 720x1280 as calibrated, area 2x2 -> 360x640, luma)
# into a FIFO -> pw_euroc_runner_stream.  No frame files on disk; frames.mov deleted at the end.
set -u
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata
NN=$1; D=$W/ds/advio/$NN; R=$W/runs/advio; mkdir -p $R
for L in ${2:-S M}; do
  F=$W/work/fifo_advio_${NN}_$L; rm -f $F; mkfifo $F
  OUT=$R/$NN.$L.tum
  PW_RAW_STREAM=$F PW_RAW_W=360 PW_RAW_H=640 $W/tools/locked.sh $W/work/build-$L/pw_euroc_runner_stream \
     $W/xrslam-wt-$L/configs/iphone_slam.yaml $D/device_$L.yaml euroc://$D/mav0 $OUT > $OUT.log 2>&1 &
  RP=$!
  ffmpeg -v error -nostdin -i $D/frames.mov -vf "scale=360:640:flags=area,format=gray" -fps_mode passthrough \
     -f rawvideo -pix_fmt gray -y $F 2> $OUT.ffmpeg.log
  FR=$?
  wait $RP; RC=$?
  rm -f $F
  echo "[advio-$NN/$L] ffmpeg=$FR runner=$RC poses=$(wc -l < $OUT 2>/dev/null) -> $OUT"
done
