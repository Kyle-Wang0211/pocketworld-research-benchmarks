#!/bin/bash
# gpufe 臂回放门: 同一 build 两场(单变量 = -PWXrslamGpuFrontend), 各拉 xrslam_gpufe_stats.json, 算 ATE
set -uo pipefail
S=$(cd "$(dirname "$0")" && pwd); D=${PW_BENCH_DEVICE:-1B290474-D354-5B4C-AAB0-0805AC5DC832}; DEST=~/Developer/viobench-recordings
LOG=$DEST/eval-xrslam-threading-backpressure-20260903/chain_gpufe_replay_$(date +%m%d_%H%M%S).log; exec > >(tee -a "$LOG") 2>&1
"$S/pw_install_arm.sh" gpufe || exit 1
pull_stats() { xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/xrslam_gpufe_stats.json" --destination "$1" >/dev/null 2>&1 && cat "$1" || echo "(no gpufe stats file)"; }
xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/xrslam_gpufe_stats.json" --destination /tmp/_old_stats.json >/dev/null 2>&1 && echo "note: stale stats file existed on device before runs"
for ARM in ${ARMS:-ctrl gpu}; do
  FL=""; [ "$ARM" = gpu ] && FL="-PWXrslamGpuFrontend"; [ "${AUDIT:-0}" = 1 ] && FL="$FL -PWXrslamGpuFrontendAudit"
  OUT=$("$S/pw_run_arm.sh" "gpufe_replay_$ARM" replay-device-recording -PWFeederGateOff $FL 2>&1 | tee /dev/stderr); RUN=$(echo "$OUT" | grep -oE "run=run-[a-f0-9-]{36}" | head -1 | cut -d= -f2)
  echo "── $ARM run=$RUN"; [ -n "$RUN" ] && { python3 -c "import json;r=json.load(open('$DEST/$RUN/receipt.json'));print('receipt backend=',r['app']['backend'],'engine_sha16=',r['identities']['engine_artifact_sha256'][:16],'state=',r['state'])"; echo -n "ATE: "; "$S/pw_ate.sh" "$DEST/$RUN"; }
  echo -n "gpufe stats ($ARM): "; pull_stats "$DEST/${RUN:-none}_gpufe_stats_$ARM.json"
done
echo "对照基线: R2b run-2de39ccd (thrbp, 无旗) ATE: $("$S/pw_ate.sh" $DEST/run-2de39ccd* 2>/dev/null)"
echo CHAIN_GPUFE_REPLAY_DONE
