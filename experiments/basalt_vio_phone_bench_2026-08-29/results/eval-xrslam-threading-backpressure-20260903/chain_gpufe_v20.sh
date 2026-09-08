#!/bin/bash
echo "══ archive + bench (timestamps off) ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/assemble_and_build.sh 2>&1 | grep -vE "^\+" | grep -E "error:|BUILD|engine sha16|Traceback"
echo "══ replay gpu×1 ══"; ARMS="gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "installed|run=run|metrics|ATE|拒绝|退出" | cut -c1-250
echo "══ live 600 s (daytime) ══"; /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_live.sh 2>&1 | grep -avE "^t=\+|^\s*$|Launched|已拉取" | cut -c1-330
echo CHAIN_V20_DONE
