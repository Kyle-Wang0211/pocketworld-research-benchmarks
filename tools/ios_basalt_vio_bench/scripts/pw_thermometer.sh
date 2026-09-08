#!/bin/bash
# 无参数启动 bench 只为读 preflight.json 的 thermal_state;打印 0..3;读不到打印 -1
D=${PW_BENCH_DEVICE:-1B290474-D354-5B4C-AAB0-0805AC5DC832}
xcrun devicectl device process launch --device "$D" --terminate-existing com.kyle.viobench >/dev/null 2>&1
T=$(mktemp -d)
for i in 1 2 3 4; do
  sleep 3; rm -f "$T/p.json"
  xcrun devicectl device copy from --device "$D" --domain-type appDataContainer --domain-identifier com.kyle.viobench --user mobile --source Documents/preflight.json --destination "$T/p.json" >/dev/null 2>&1
  v=$(python3 -c "import json;print(json.load(open('$T/p.json')).get('thermal_state',-1))" 2>/dev/null) && [ -n "$v" ] && { echo "$v"; exit 0; }
done
echo -1
