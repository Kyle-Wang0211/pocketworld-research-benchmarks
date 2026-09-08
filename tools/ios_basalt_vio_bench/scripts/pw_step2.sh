#!/bin/bash
# 第 2 步:ARKit 参考 600 s → 等凉 → thrbp 600 s
set -u; S=$(cd "$(dirname "$0")" && pwd)
"$S/pw_wait_cool.sh" || exit 1
"$S/pw_run_arm.sh" S2-arkit-live600 live-soak -PWAutoRunBackend arkit_reference -PWLiveFullResolution -PWAutoRunSeconds 600 || exit 1
"$S/pw_wait_cool.sh" || exit 1
"$S/pw_install_arm.sh" thrbp || exit 1
"$S/pw_run_arm.sh" S2-thrbp-live600 live-soak -PWLiveFullResolution -PWAutoRunSeconds 600
