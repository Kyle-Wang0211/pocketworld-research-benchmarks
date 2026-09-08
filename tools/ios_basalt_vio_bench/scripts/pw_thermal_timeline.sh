#!/bin/bash
# pw_thermal_timeline.sh <run-dir> —— 按分钟汇总 telemetry.jsonl:热状态、footprint 峰、CPU 核当量均值
python3 - "$1" <<'PY'
import json,os,sys,collections
r=sys.argv[1]; tp=os.path.join(r,'telemetry.jsonl')
rows=[json.loads(l) for l in open(tp) if l.strip()]
if not rows: print("telemetry 空"); sys.exit(0)
t0=rows[0]['monotonicSeconds']
buckets=collections.defaultdict(list)
for x in rows: buckets[int((x['monotonicSeconds']-t0)//60)].append(x)
print(f"{'min':>3} {'thermal(占比)':<28} {'fp峰MB':>7} {'cpu核':>6} {'样本':>4}")
first_serious=None; first_critical=None
for m in sorted(buckets):
    b=buckets[m]; th=collections.Counter(x.get('thermalState') for x in b)
    fp=max((x.get('physicalFootprintBytes') or 0) for x in b)/1048576
    cpu=[x.get('cpuCoreEquivalent',0) for x in b if x.get('cpuCoreEquivalent')]
    print(f"{m:>3} {str(dict(th)):<28} {fp:>7.0f} {sum(cpu)/max(1,len(cpu)):>6.2f} {len(b):>4}")
for x in rows:
    s=x.get('thermalState'); t=x['monotonicSeconds']-t0
    if s=='serious' and first_serious is None: first_serious=t
    if s=='critical' and first_critical is None: first_critical=t
print(f"首次 serious: {first_serious if first_serious is None else round(first_serious)} s | 首次 critical: {first_critical if first_critical is None else round(first_critical)} s | 总时长 {round(rows[-1]['monotonicSeconds']-t0)} s")
PY
