#!/bin/bash
# 第 2b 步:唯一允许的杠杆——上游自己的 sliding_window.tracker_frequent 1→2,其余不变;thrbp 直播 600 s
set -u; S=$(cd "$(dirname "$0")" && pwd)
"$S/pw_wait_cool.sh" || exit 1
"$S/pw_install_arm.sh" thrbp || exit 1
"$S/pw_run_arm.sh" S2b-thrbp-live600-freq2 live-soak -PWLiveFullResolution -PWAutoRunSeconds 600 -PWTrackerFrequent 2
