#!/bin/bash
# official arm on ADVIO: 60 Hz video -> 30 Hz (even frames 0,2,4,... kept, same stamps), 360x640 luma,
# slam_O.yaml, --pace 1, threading on.  frames.mov re-fetched by advio_prep.py and deleted afterwards.
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata
NN=$1; n=$((10#$NN)); D=$W/ds/advio/$NN; R=$W/runs/advio
cd $W/work && /opt/homebrew/bin/python3.11 $W/tools/advio_prep.py $n | grep -E "fetched|STOP" || exit 1
mkdir -p $D/mav0_30/cam0; ln -sfn ../mav0/imu0 $D/mav0_30/imu0
/opt/homebrew/bin/python3.11 - "$D" <<'PY'
import sys
D = sys.argv[1]
L = open(D + "/mav0/cam0/data.csv", newline="").read().split("\r\n")
rows = [l for l in L[1:] if l.strip()]
with open(D + "/mav0_30/cam0/data.csv", "w", newline="\r\n") as f:
    f.write(L[0] + "\n")
    for l in rows[::2]:
        f.write(l + "\n")
print("30Hz rows", len(rows[::2]), "of", len(rows))
PY
F=$W/work/fifo_advio_${NN}_O; rm -f $F; mkfifo $F
OUT=$R/$NN.O.tum
sed -n '/^imu:/,/^cam0:/p' $W/xrslam-wt-O/configs/iphonex.yaml | sed '$d' > /dev/null
DEV=$D/device_S.yaml
PW_RAW_STREAM=$F PW_RAW_W=360 PW_RAW_H=640 $W/tools/locked.sh $W/work/build-O/pw_euroc_runner_stream \
   $W/cfg/slam_O.yaml $DEV euroc://$D/mav0_30 $OUT --pace 1 --camera-out $R/$NN.O.cam.tum > $OUT.log 2>&1 &
RP=$!
ffmpeg -v error -nostdin -i $D/frames.mov -vf "select=not(mod(n\,2)),scale=360:640:flags=area,format=gray" -fps_mode passthrough \
   -f rawvideo -pix_fmt gray -y $F 2> $OUT.ffmpeg.log
FR=$?; wait $RP; RC=$?; rm -f $F $D/frames.mov
echo "[advio-$NN/O] ffmpeg=$FR runner=$RC poses=$(wc -l < $OUT) -> $OUT"
