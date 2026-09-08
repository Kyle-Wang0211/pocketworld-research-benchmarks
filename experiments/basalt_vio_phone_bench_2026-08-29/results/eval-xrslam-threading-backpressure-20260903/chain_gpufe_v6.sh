#!/bin/bash
echo "══ iOS lib ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/build_gpufe_ios.sh 2>&1 | tail -1
echo "══ archive + bench ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/assemble_and_build.sh 2>&1 | grep -vE "^\+" | grep -E "error:|sha256|BUILD|engine sha16|Traceback"
echo "══ replay gpu×1 ══"; ARMS="gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "run=run|metrics|ATE|拒绝|✗"
f=$(ls -t ~/Developer/viobench-recordings/run-*_gpufe_stats_gpu.json | head -1); echo "── $f"; python3 -c "import json;d=json.load(open('$f'));print('audit',json.dumps(d['audit'],ensure_ascii=False));print('selfcheck',json.dumps(d.get('selfcheck'),ensure_ascii=False))"
echo CHAIN_V6_DONE
