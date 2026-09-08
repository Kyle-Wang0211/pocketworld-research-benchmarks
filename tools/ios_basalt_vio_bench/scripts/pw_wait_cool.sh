#!/bin/bash
# 等到 thermal_state==0(nominal),最多 20 分钟;读不到(-1)立刻重试不占 60 s
S=$(cd "$(dirname "$0")" && pwd)
for i in $(seq 1 14); do s=$("$S/pw_thermometer.sh"); echo "  thermal=$s ($(date +%H:%M:%S))"; [ "$s" = 0 ] && exit 0; [ "$s" = -1 ] && { sleep 5; continue; }; sleep 180; done
echo "  未回到 nominal"; exit 1
