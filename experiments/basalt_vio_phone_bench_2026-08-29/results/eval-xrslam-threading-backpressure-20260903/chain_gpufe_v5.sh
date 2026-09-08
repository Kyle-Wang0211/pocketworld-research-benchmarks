#!/bin/bash
while ! grep -q "CHAIN_GPUFE_LIVE_DONE" /Users/kaidongwang/Developer/viobench-recordings/eval-xrslam-threading-backpressure-20260903/chain_gpufe_live_wrapper.log 2>/dev/null; do sleep 15; done
echo "══ rebuild (audit detail) ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/assemble_and_build.sh 2>&1 | grep -vE "^\+" | grep -E "error:|sha256|BUILD|engine sha16|Traceback"
echo "══ replay gpu×1 ══"; ARMS="gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "run=run|metrics|ATE|拒绝|✗"
ls -t  2>/dev/null | head -0
for f in $(ls -t ~/Developer/viobench-recordings/run-*_gpufe_stats_gpu.json | head -1); do echo "── $f"; python3 -c "import json;d=json.load(open('$f'));print(json.dumps(d['audit'],ensure_ascii=False))"; done
echo CHAIN_V5_DONE
