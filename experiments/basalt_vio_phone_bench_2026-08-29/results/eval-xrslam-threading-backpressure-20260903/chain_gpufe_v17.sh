#!/bin/bash
echo "══ iOS lib ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/build_gpufe_ios.sh 2>&1 | tail -1
echo "══ archive + bench ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/assemble_and_build.sh 2>&1 | grep -vE "^\+" | grep -E "error:|sha256|BUILD|engine sha16|Traceback"
echo "══ replay gpu×3 ══"; ARMS="gpu gpu gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "run=run|metrics|ATE|拒绝|退出|gpufe stats" | cut -c1-330
echo "══ live 600 s ══"; /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_live.sh 2>&1 | grep -vE "^t=\+|^\s*$|Launched|已拉取"
echo CHAIN_V17_DONE
