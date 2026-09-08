#!/bin/bash
# 等 2b 链结束 → 等凉 → 装(已修好的)thrbp bench → ARKit 600 s
set -u; S=$(cd "$(dirname "$0")" && pwd); E=~/Developer/viobench-recordings/eval-xrslam-threading-backpressure-20260903
echo "arkit-run chain start $(date '+%F %T')"
CH=$(ls -t "$E"/chain_step2_*.log | head -1); n=0
until grep -q "chain end" "$CH"; do n=$((n+1)); [ $n -ge 360 ] && { echo "等 2b 链结束超时"; exit 1; }; sleep 5; done
echo "2b chain ended $(date '+%T')"
"$S/pw_wait_cool.sh" || exit 1
"$S/pw_install_arm.sh" thrbp || exit 1
"$S/pw_run_arm.sh" S2-arkit-live600 live-soak -PWAutoRunBackend arkit_reference -PWLiveFullResolution -PWAutoRunSeconds 600
echo "arkit-run chain end rc=$? $(date '+%F %T')"
