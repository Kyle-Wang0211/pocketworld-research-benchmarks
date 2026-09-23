#!/bin/bash
set -euo pipefail
RUN="$1"; GRID="${2:--4,0,4,8,12,16}"
R=$HOME/Developer/viobench-recordings; OUT="$R/$RUN"; SID=$(echo "$RUN" | cut -c5-12); E="$R/_euroc_${SID}_exphalf"
echo "── 4. 转 EuRoC(曝光中点,按时间戳配对)"; rm -rf "$E"
/usr/bin/python3 $HOME/Developer/arloopbench/tools/pwvi_to_euroc.py --exposure-half "$OUT" "$E" 2>&1 | grep -v "DeprecationWarning\|Image.fromarray\|^  帧 " 
echo "── 5. 本场内参 yaml"
k=$(head -1 "$OUT/intrinsics.jsonl" | /usr/bin/python3 -c "import json,sys; print(' '.join(map(str,json.loads(sys.stdin.read())['intrinsics_fxfycxcy'])))")
set -- $k; fx=$1; fy=$2; cx=$3; cy=$4
sed -E "s/^(  intrinsics: )\[.*\]/\1[$fx, $fy, $cx, $cy]/" $R/_sweep/device_bench.yaml > $R/_sweep/device_bench_${SID}.yaml
grep -n "intrinsics:" $R/_sweep/device_bench_${SID}.yaml
echo "── 6. 扫 cam0.time_offset(曝光/2 已加 ⇒ 极小点 = c)  网格 ms: $GRID"
/usr/bin/python3 -u $HOME/Developer/arloopbench/tools/sweep_euroc_td_ba.py \
  --runner /tmp/pw_euroc_new --seq "$E" \
  --slam-config $R/_sweep/slam_bench.yaml --device-config $R/_sweep/device_bench_${SID}.yaml \
  --gt "$OUT/arkit_poses.tum" --ate $R/ate.py --out $R/_sweep_c_${SID} --ref-y-up \
  "--td-ms=$GRID" "--ba=0,0,0"
echo "── 完成 $(date +%H:%M:%S)"
