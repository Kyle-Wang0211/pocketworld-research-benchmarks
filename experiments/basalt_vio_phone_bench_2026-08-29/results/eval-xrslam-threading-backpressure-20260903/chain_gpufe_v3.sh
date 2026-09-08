#!/bin/bash
echo "══ xrslam archive + bench app ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/assemble_and_build.sh 2>&1 | grep -vE "^\+" | grep -E "members|sha256|BUILD|engine sha16|vendor|Traceback|error"
echo "══ replay: ctrl + gpu×3 ══"; ARMS="ctrl gpu gpu gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "══════|run=run|metrics|telemetry|ATE|gpufe stats|拒绝|✗"
echo CHAIN_V3_DONE
