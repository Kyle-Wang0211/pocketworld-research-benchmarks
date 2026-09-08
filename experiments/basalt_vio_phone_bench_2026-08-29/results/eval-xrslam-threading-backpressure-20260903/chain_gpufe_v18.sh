#!/bin/bash
echo "══ replay gpu×3 (engine 3b3528bd) ══"; ARMS="gpu gpu gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "installed|run=run|metrics|ATE|拒绝|退出|gpufe stats" | cut -c1-420
echo "══ live 600 s ══"; /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_live.sh 2>&1 | grep -vE "^t=\+|^\s*$|Launched|已拉取"
echo CHAIN_V18_DONE
