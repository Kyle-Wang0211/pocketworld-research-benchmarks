#!/bin/bash
echo "══ iOS lib (unchanged) ══"
echo "══ archive + bench ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/assemble_and_build.sh 2>&1 | grep -vE "^\+" | grep -E "error:|sha256|BUILD|engine sha16|Traceback"
D=1B290474-D354-5B4C-AAB0-0805AC5DC832
echo "══ replay gpu×1 ══"; ARMS="gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "run=run|metrics|ATE|退出|完成|拒绝|✗"
T=$(mktemp -d); xcrun devicectl device copy from --device $D --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/xrslam_gpufe_init.log" --destination $T/init.log >/dev/null 2>&1; echo "── init markers:"; tail -8 $T/init.log 2>/dev/null | cut -c1-600
xcrun devicectl device copy from --device $D --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/xrslam_gpufe_stats.json" --destination $T/st.json >/dev/null 2>&1; echo "── stats:"; cut -c1-900 $T/st.json 2>/dev/null
echo CHAIN_V8_DONE
