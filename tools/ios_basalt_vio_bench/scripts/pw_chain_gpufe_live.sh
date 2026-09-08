#!/bin/bash
# gpufe live-soak 600 s (1920x1440 @30 fps, GPU front end) vs ARKit reference run-f3d525c9 — relative verdict
set -uo pipefail
S=$(cd "$(dirname "$0")" && pwd); D=${PW_BENCH_DEVICE:-1B290474-D354-5B4C-AAB0-0805AC5DC832}; DEST=~/Developer/viobench-recordings
SECS=${SECS:-300}; REF=${REF:-$DEST/run-f3d525c9-d065-4ba9-aac5-0939b96ae93f}   # 300 s = 产品拍摄上限 5 分钟 (09-04 用户)
LOG=$DEST/eval-xrslam-threading-backpressure-20260903/chain_gpufe_live_$(date +%m%d_%H%M%S).log; exec > >(tee -a "$LOG") 2>&1
[ "${INSTALL:-0}" = 1 ] && "$S/pw_install_arm.sh" gpufe 2>&1 | tail -1   # INSTALL=1: install the freshly built app first (09-05: a live run silently used the previous app — always check eng_sha in the receipt)
[ "${SKIP_COOL:-0}" = 1 ] || "$S/pw_wait_cool.sh" 2>&1 | tail -2   # SKIP_COOL=1: cooling was done separately (so the user can be told before capture starts)
OUT=$("$S/pw_run_arm.sh" "gpufe_live_gpu" live-soak -PWAutoRunSeconds $SECS -PWLiveFullResolution -PWXrslamGpuFrontend ${EXTRA:-} 2>&1 | tee /dev/stderr); RUN=$(echo "$OUT" | grep -oE "run=run-[a-f0-9-]{36}" | head -1 | cut -d= -f2)
echo "── live gpu run=$RUN"
[ -n "$RUN" ] && { "$S/pw_thermal_timeline.sh" "$DEST/$RUN" 2>/dev/null | tail -3; echo "── 相对 ARKit 判决:"; "$S/pw_relative_verdict.sh" "$DEST/$RUN" "$REF"; }
T=$(mktemp -d); xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/xrslam_gpufe_stats.json" --destination "$T/st.json" >/dev/null 2>&1; echo -n "gpufe stats: "; cat "$T/st.json" 2>/dev/null || echo "(none)"; cp "$T/st.json" "$DEST/${RUN:-none}_gpufe_stats_live.json" 2>/dev/null
echo CHAIN_GPUFE_LIVE_DONE
