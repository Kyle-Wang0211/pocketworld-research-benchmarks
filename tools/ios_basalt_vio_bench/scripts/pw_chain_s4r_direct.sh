#!/bin/bash
set -u; S=$(cd "$(dirname "$0")" && pwd); R=~/Developer/viobench-recordings
"$S/pw_run_arm.sh" S4r-thrbp-replay1920-freq2 replay-device-recording -PWTrackerFrequent 2
RUN=$(grep -oE "run=run-[a-f0-9-]{36}" "$(ls -t "$R"/eval-xrslam-threading-backpressure-20260903/S4r-*.log | head -1)" | tail -1 | cut -d= -f2)
echo "S4r ATE: $("$S/pw_ate.sh" "$R/$RUN")"; echo "s4r direct end $(date '+%F %T')"
