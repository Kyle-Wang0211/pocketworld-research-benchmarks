#!/bin/bash
S=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts; D=1B290474-D354-5B4C-AAB0-0805AC5DC832
SECS=600 $S/pw_chain_gpufe_live.sh 2>&1 | grep -aE "run=run|metrics|camera off|telemetry|退出|⇒|劣于|指标|首次" | cut -c1-300
T=$(mktemp -d); xcrun devicectl device copy from --device $D --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source "Documents/xrslam_gpufe_stats.json" --destination $T/st.json >/dev/null 2>&1
python3 -c "
s=open('$T/st.json').read(); import re
for k in ('prefetch_declined','frames','fallbacks','avg_preprocess_ms','avg_detect_ms','avg_track_ms','empty_submit_ms'): m=re.search(k+r'\":(-?[0-9.]+)',s); print(k, m.group(1) if m else '?')
for key in ('\"audit\"','\"buckets_per1000\"','\"last_fallback\"'): i=s.find(key); print(s[i:i+200])"
echo CHAIN_V34_DONE
