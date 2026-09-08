#!/bin/bash
# 修 ARKit live-soak + -PWLiveFullResolution 的 invalidRoot(标定改写误用于 ARKit 描述文件),重编,
# 等当前 2b 链结束后:等凉 → 装修好的 bench → ARKit 600 s
set -u; S=$(cd "$(dirname "$0")" && pwd); B="$S/../BasaltVIOBench"; E=~/Developer/viobench-recordings/eval-xrslam-threading-backpressure-20260903
echo "fixchain start $(date '+%F %T')"
python3 - "$B/BenchmarkRunPreparation.swift" <<'PY'
import sys;p=sys.argv[1];L=open(p).read().split("\n")
idx=[i for i,l in enumerate(L) if "let scaled = DeviceRecordingIntrinsics(" in l]
assert len(idx)==1, f"scaled 锚点 {len(idx)}"
j=idx[0]
while j>0 and "if BenchResolution.liveFullResolutionRequested {" not in L[j]: j-=1
assert j>0 and idx[0]-j<40, "if 锚点未命中"
L[j]=L[j].replace("if BenchResolution.liveFullResolutionRequested {",
 "// [2026-09-03] ARKit owns its calibration; arkit_runtime_calibration.json is a\n"
 "            // descriptor (calibration_owner / intrinsics_source / pose_frame / status), not\n"
 "            // a Basalt-layout file. Rewriting it here threw invalidRoot before the started\n"
 "            // receipt, which is why the ARKit live-soak arm never ran.\n"
 "            if BenchResolution.liveFullResolutionRequested, backend != .arkit {")
open(p,"w").write("\n".join(L)); print("patched at line",j+1)
PY
"$S/pw_build_arms.sh" 2>&1 | grep -E "────|error:|BUILD|engine|vendor"
grep -q "BUILD FAILED" <(tail -20 "$0" 2>/dev/null) && exit 1
# 等当前链(2b)结束
CH=$(ls -t "$E"/chain_step2_*.log | head -1); n=0
until grep -q "chain end" "$CH"; do n=$((n+1)); [ $n -ge 360 ] && { echo "等 2b 链结束超时(30 min)"; exit 1; }; sleep 5; done
echo "2b chain ended $(date '+%T')"
"$S/pw_wait_cool.sh" || exit 1
"$S/pw_install_arm.sh" thrbp || exit 1
"$S/pw_run_arm.sh" S2-arkit-live600 live-soak -PWAutoRunBackend arkit_reference -PWLiveFullResolution -PWAutoRunSeconds 600
echo "fixchain end rc=$? $(date '+%F %T')"
