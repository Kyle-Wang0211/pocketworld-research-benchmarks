#!/bin/bash
# 脱离会话的第 2 步链:等凉 → ARKit 600 s → 等凉 → 2b(thrbp + tracker_frequent 2,600 s)
set -u; S=$(cd "$(dirname "$0")" && pwd)
echo "chain start $(date '+%F %T')"
"$S/pw_wait_cool.sh" || { echo "cool timeout before arkit"; exit 1; }
"$S/pw_run_arm.sh" S2-arkit-live600 live-soak -PWAutoRunBackend arkit_reference -PWLiveFullResolution -PWAutoRunSeconds 600
echo "arkit done rc=$? $(date '+%T')"
"$S/pw_step2b.sh"
echo "chain end rc=$? $(date '+%F %T')"
