#!/bin/bash
# control: the stream-patched runner fed the SAME EuRoC PNGs via FIFO must reproduce the file-based run bit for bit.
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata
S=${1:-V1_02_medium}; L=${2:-S}; E=$HOME/Developer/euroc/$S/mav0
F=$W/work/fifo_selftest_$L; rm -f $F; mkfifo $F
OUT=$W/runs/euroc/$S.$L.stream.tum
PW_RAW_STREAM=$F PW_RAW_W=752 PW_RAW_H=480 $W/tools/locked.sh $W/work/build-$L/pw_euroc_runner_stream \
  $W/xrslam-wt-$L/configs/euroc_slam.yaml $W/xrslam-wt-$L/configs/euroc_sensor.yaml euroc://$E $OUT > $OUT.log 2>&1 &
RP=$!
/opt/homebrew/bin/python3.11 - "$E" "$F" <<'PY'
import sys, cv2, numpy as np
E, F = sys.argv[1], sys.argv[2]
rows = sorted((int(l.split(',')[0]), l.strip().split(',')[1]) for l in open(E + '/cam0/data.csv') if not l.startswith('#') and l.strip())
with open(F, 'wb') as f:
    for t, fn in rows:
        im = cv2.imread(E + '/cam0/data/' + fn, cv2.IMREAD_UNCHANGED)
        f.write(np.ascontiguousarray(im).tobytes())
print('fed', len(rows))
PY
wait $RP; rm -f $F
shasum -a 256 $W/runs/euroc/$S.$L.tum $OUT | cut -c1-64
cmp $W/runs/euroc/$S.$L.tum $OUT && echo "STREAM_SELFTEST_IDENTICAL $S $L"
