#!/bin/bash
# B 流水线:拉回新 run → 验 exposure_s → 转 EuRoC(--exposure-half)→ 本场内参 yaml → 扫 cam0.time_offset 得 c
set -euo pipefail
DEV=1B290474-D354-5B4C-AAB0-0805AC5DC832; BUNDLE=com.kyle.viobench
R=$HOME/Developer/viobench-recordings; SP=$(cd "$(dirname "$0")" && pwd)
GRID="${1:--4,0,4,8,12,16}"

echo "── 1. 找新 run(与录制前 7 条做差)"
xcrun devicectl device info files --device $DEV --domain-type appDataContainer --domain-identifier $BUNDLE --username mobile 2>/dev/null \
  | grep -oE "run-[a-f0-9-]{36}" | sort -u > $SP/runs_after.txt
NEW=$(comm -13 $SP/runs_before.txt $SP/runs_after.txt)
[ -z "$NEW" ] && { echo "🔴 手机上没有新 run"; exit 1; }
echo "新 run: $NEW"; [ "$(echo "$NEW" | wc -l)" -gt 1 ] && { echo "🔴 不止一条新 run,先人工挑"; exit 1; }
OUT="$R/$NEW"; mkdir -p "$OUT"

echo "── 2. 拉回(只拉这一条)"
xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier $BUNDLE --user mobile \
  --source "Documents/VIOBenchRuns/$NEW" --destination "$OUT" >/dev/null
[ -d "$OUT/$NEW" ] && { mv "$OUT/$NEW"/* "$OUT"/ 2>/dev/null || true; rmdir "$OUT/$NEW" 2>/dev/null || true; }
(cd "$OUT" && shasum -a 256 -c SHA256SUMS --quiet 2>/dev/null && echo "✓ SHA256SUMS 校验通过" && touch .backup_complete) || echo "⚠️ 校验未通过/无 SHA256SUMS(继续,但记着)"
du -sh "$OUT" | awk '{print "大小 "$1}'

echo "── 3. 验 exposure_s 真的写进去了(这是本次录制存在的理由)"
/usr/bin/python3 - "$OUT" <<'PY'
import json,sys,os
rows=[json.loads(l) for l in open(os.path.join(sys.argv[1],'intrinsics.jsonl')) if l.strip()]
e=[r['exposure_s'] for r in rows if 'exposure_s' in r]
print(f"帧 {len(rows)}  带 exposure_s {len(e)}")
if not e: sys.exit("🔴 没有 exposure_s —— 录的是旧版 app,这场不能用")
import statistics as st
print(f"曝光 ms min/median/max = {min(e)*1e3:.2f}/{st.median(e)*1e3:.2f}/{max(e)*1e3:.2f}  ⇒ exposure/2 均值 {st.mean(e)*5e2:.2f} ms")
k=rows[0]['intrinsics_fxfycxcy']; print(f"第0帧内参 fx={k[0]:.4f} fy={k[1]:.4f} cx={k[2]:.4f} cy={k[3]:.4f}")
open(os.path.join(sys.argv[1],'_first_intrinsics.txt'),'w').write(' '.join(map(str,k)))
PY

echo "── 4. 转 EuRoC(曝光中点)"
SID=$(echo "$NEW" | cut -c5-12); E="$R/_euroc_${SID}_exphalf"
/usr/bin/python3 $HOME/Developer/arloopbench/tools/pwvi_to_euroc.py --exposure-half "$OUT" "$E" 2>&1 | grep -v DeprecationWarning | tail -6

echo "── 5. 本场内参的 device yaml"
read fx fy cx cy < "$OUT/_first_intrinsics.txt"
sed -E "s/^(  intrinsics: )\[.*\]/\1[$fx, $fy, $cx, $cy]/" $R/_sweep/device_bench.yaml > $R/_sweep/device_bench_${SID}.yaml
grep -n "intrinsics:" $R/_sweep/device_bench_${SID}.yaml

echo "── 6. 扫 cam0.time_offset(此时曝光/2 已加,极小点 = c)  网格 ms: $GRID"
/usr/bin/python3 -u $HOME/Developer/arloopbench/tools/sweep_euroc_td_ba.py \
  --runner /tmp/pw_euroc_new --seq "$E" \
  --slam-config $R/_sweep/slam_bench.yaml --device-config $R/_sweep/device_bench_${SID}.yaml \
  --gt "$OUT/arkit_poses.tum" --ate $R/ate.py --out $R/_sweep_c_${SID} --ref-y-up \
  "--td-ms=$GRID" "--ba=0,0,0"
