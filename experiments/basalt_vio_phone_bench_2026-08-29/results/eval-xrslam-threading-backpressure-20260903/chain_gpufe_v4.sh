#!/bin/bash
while ! grep -q "CHAIN_GPUFE_REPLAY_DONE" /Users/kaidongwang/Developer/viobench-recordings/eval-xrslam-threading-backpressure-20260903/chain_gpufe_v3b.log 2>/dev/null; do sleep 10; done
echo "══ v3b (third sample) ══"; grep -E "run=run|metrics|telemetry|ATE|gpufe stats" /Users/kaidongwang/Developer/viobench-recordings/eval-xrslam-threading-backpressure-20260903/chain_gpufe_v3b.log | cut -c1-220
echo "══ rebuild with on-device audit ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/assemble_and_build.sh 2>&1 | grep -vE "^\+" | grep -E "error:|sha256|BUILD|engine sha16|Traceback"
echo "══ replay gpu×2 (audit) ══"; ARMS="gpu gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "══════|run=run|metrics|telemetry|ATE|gpufe stats|拒绝|✗"
echo CHAIN_V4_DONE
