#!/bin/bash
S=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts
echo "══ rebuild gpufe bench app ══"; $S/pw_build_gpufe_arm.sh 2>&1 | tail -4
echo "══ install + GPU replay ══"; ARMS=gpu $S/pw_chain_gpufe_replay.sh 2>&1 | grep -vE "^t=\+|^\s*$"
echo FIX_RERUN_DONE
