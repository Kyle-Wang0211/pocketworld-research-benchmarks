#!/bin/bash
# pw_relative_verdict.sh <candidate-run-dir> <arkit-reference-run-dir> —— 逐项"不劣于 ARKit"判决(离线,读 receipt/diagnostics/telemetry)
python3 - "$1" "$2" <<'PY'
import json,os,sys,collections
def load(r):
    rc=json.load(open(os.path.join(r,'receipt.json'))); dg=json.load(open(os.path.join(r,'diagnostics.json')))
    m=dict(rc.get('metrics',{})); nc=dg.get('native_counters',{}); tc=dg.get('transport_counters',{})
    rows=[json.loads(l) for l in open(os.path.join(r,'telemetry.jsonl')) if l.strip()] if os.path.exists(os.path.join(r,'telemetry.jsonl')) else []
    dur=m.get('measurement_duration_seconds') or m.get('diagnostic_elapsed_seconds') or (rows[-1]['monotonicSeconds']-rows[0]['monotonicSeconds'] if rows else 0)
    poses=nc.get('poses_produced') or m.get('diagnostic_pose_count') or 0
    fps_metric=m.get('processed_fps') or m.get('diagnostic_processed_fps')
    th=collections.Counter(x.get('thermalState') for x in rows)
    fp=max(((x.get('physicalFootprintBytes') or 0)/1048576 for x in rows), default=m.get('peak_phys_footprint_mb') or 0)
    cpu=[x.get('cpuCoreEquivalent',0) for x in rows if x.get('cpuCoreEquivalent')]
    cam_off=nc.get('camera_offered') or nc.get('frames_received') or tc.get('camera_inputs') or 0
    return dict(
        engine=rc['app'].get('engine_id'), state=rc.get('state'), reason=rc.get('termination',{}).get('reason_code'), dur=dur,
        fps=(fps_metric if fps_metric else (poses/dur if dur else 0)), p95=m.get('p95_pipeline_latency_ms') or m.get('diagnostic_p95_pipeline_latency_ms'),
        first=m.get('first_usable_pose_latency_ms') or m.get('diagnostic_first_usable_pose_latency_ms'),
        fp_peak=fp, serious=th.get('serious',0), critical=th.get('critical',0), cpu=sum(cpu)/max(1,len(cpu)),
        drops=sum(v for k,v in tc.items() if k.startswith('camera_drops')), finite=m.get('finite_pose_ratio'), cam_fps=cam_off/dur if dur else 0)
c,a=load(sys.argv[1]),load(sys.argv[2])
print(f"候选 {c['engine']} ({os.path.basename(sys.argv[1])[:12]}, {c['state']}/{c['reason']}, {c['dur']:.0f}s) vs 参考 {a['engine']} ({os.path.basename(sys.argv[2])[:12]}, {a['state']}/{a['reason']}, {a['dur']:.0f}s)")
def row(name,cv,av,higher_better,fmt="{:.1f}"):
    if cv is None or av is None: print(f"  {name:<22} {str(cv):>10} {str(av):>10}  无法比"); return None
    ok = (cv>=av) if higher_better else (cv<=av)
    print(f"  {name:<22} {fmt.format(cv):>10} {fmt.format(av):>10}  {'不劣于' if ok else '劣于'}"); return ok
print(f"  {'指标':<22} {'候选':>10} {'ARKit':>10}")
res=[row("位姿/s",c['fps'],a['fps'],True), row("相机交付 fps",c['cam_fps'],a['cam_fps'],True), row("p95 延迟 ms",c['p95'],a['p95'],False),
     row("首个可用位姿 ms",c['first'],a['first'],False,"{:.0f}"), row("footprint 峰 MB",c['fp_peak'],a['fp_peak'],False,"{:.0f}"),
     row("serious 秒",c['serious'],a['serious'],False,"{:.0f}"), row("critical 秒",c['critical'],a['critical'],False,"{:.0f}"),
     row("CPU 核当量",c['cpu'],a['cpu'],False,"{:.2f}"), row("平台丢帧",c['drops'],a['drops'],False,"{:.0f}")]
known=[r for r in res if r is not None]
print(f"  ⇒ {sum(known)}/{len(known)} 项不劣于 ARKit;{'全部不劣于 ⇒ 过' if all(known) else '有劣于项 ⇒ 未过'}")
PY
