#!/bin/bash
# 杠杆 2(待定值):等 lever1 回放链结束 → 等凉 → 装含 -PWYamlOverride 的 bench → 直播 640 freq2 600 s + 一个上游键覆盖
# 用法: pw_chain_lever2.sh <label> <section.key=value>
set -u; S=$(cd "$(dirname "$0")" && pwd); E=~/Developer/viobench-recordings/eval-xrslam-threading-backpressure-20260903
LABEL=$1; OVR=$2
CH=$(ls -t "$E"/chain_lever1_replay_*.log | head -1); n=0
until grep -q "lever1-replay chain end" "$CH"; do n=$((n+1)); [ $n -ge 480 ] && { echo "等 lever1 回放链超时"; exit 1; }; sleep 5; done
APP=~/Developer/viobench-build/bench-dd-thrbp/Build/Products/Release-iphoneos/VIOReplacementBench.app
until strings "$APP/VIOReplacementBench" 2>/dev/null | grep -q PWYamlOverride; do echo "等 YamlOverride 构建"; sleep 20; done
"$S/pw_wait_cool.sh" || exit 1
"$S/pw_install_arm.sh" thrbp || exit 1
"$S/pw_run_arm.sh" "$LABEL" live-soak -PWAutoRunSeconds 600 -PWTrackerFrequent 2 -PWYamlOverride "$OVR"
echo "lever2 chain end rc=$? $(date '+%F %T')"
