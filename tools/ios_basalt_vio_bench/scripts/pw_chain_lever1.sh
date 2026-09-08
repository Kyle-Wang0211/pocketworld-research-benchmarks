#!/bin/bash
# 杠杆 1:分辨率回到生产 XRSLAM 的 640×480(省略 -PWLiveFullResolution),其余与 S2b 完全一致
set -u; S=$(cd "$(dirname "$0")" && pwd)
echo "lever1 chain start $(date '+%F %T')"
"$S/pw_wait_cool.sh" || exit 1
"$S/pw_run_arm.sh" S3-thrbp-live600-freq2-640 live-soak -PWAutoRunSeconds 600 -PWTrackerFrequent 2
echo "lever1 chain end rc=$? $(date '+%F %T')"
