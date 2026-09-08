#!/bin/bash
# 第 1 步剩余:闸臂 live 120 s(对照臂 run-8a4df815 已完成)
set -u; S=$(cd "$(dirname "$0")" && pwd)
"$S/pw_wait_cool.sh" || exit 1
"$S/pw_install_arm.sh" thrbp || exit 1
"$S/pw_run_arm.sh" S1-thrbp-live120 live-soak -PWLiveFullResolution -PWAutoRunSeconds 120
