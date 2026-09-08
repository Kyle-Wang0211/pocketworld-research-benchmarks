#!/bin/bash
while pgrep -f pw_chain_gpufe_live.sh >/dev/null; do sleep 20; done
echo "live chain finished at $(date +%H:%M:%S)"
echo "══ iOS lib ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/build_gpufe_ios.sh 2>&1 | tail -1
echo "══ archive + bench ══"; /Users/kaidongwang/Developer/viobench-build/gpufe/assemble_and_build.sh 2>&1 | grep -vE "^\+" | grep -E "error:|BUILD|engine sha16|Traceback"
echo "══ replay gpu×1 (fused dispatches) ══"; ARMS="gpu" /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts/pw_chain_gpufe_replay.sh 2>&1 | grep -E "installed|run=run|metrics|ATE|拒绝|退出" | cut -c1-250
D=1B290474-D354-5B4C-AAB0-0805AC5DC832; T=$(mktemp -d); xcrun devicectl device copy from --device $D --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/xrslam_gpufe_stats.json" --destination $T/st.json >/dev/null 2>&1
python3 -c "
s=open('$T/st.json').read(); import re
for k in ('frames','fallbacks','avg_preprocess_ms','avg_detect_ms','avg_track_ms'): m=re.search(k+r'\":([0-9.]+)',s); print(k, m.group(1) if m else '?')
i=s.find('\"audit\"'); print(s[i:i+110]); i=s.find('\"breakdown_ms\"'); print(s[i:i+190])"
echo CHAIN_V24_DONE
