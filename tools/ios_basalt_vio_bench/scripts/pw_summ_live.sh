#!/bin/bash
# pw_summ_live.sh <run-dir>
python3 - "$1" <<'PY'
import json,os,sys,collections
r=sys.argv[1]; rc=json.load(open(os.path.join(r,'receipt.json'))); dg=json.load(open(os.path.join(r,'diagnostics.json')))
m=rc['metrics']; t=rc.get('termination',{})
print(f"run={os.path.basename(r)[:12]} engine={rc['app'].get('engine_id')} channel={rc.get('channel')} state={rc.get('state')} reason={t.get('reason_code')} eng_sha={rc['identities']['engine_artifact_sha256'][:8]}")
print("  metrics:", {k:(round(v,2) if isinstance(v,float) else v) for k,v in m.items()})
nc=dg.get('native_counters',{}); ec=dg.get('effective_configuration',{}); tc=dg.get('transport_counters',{})
print(f"  camera off/acc={nc.get('camera_offered')}/{nc.get('camera_accepted')} imu={nc.get('imu_accepted')} poses={nc.get('poses_produced')} backlog_peak={ec.get('xrslam_engine_backlog_peak')} drops_late={tc.get('camera_drops_late')} handoff_peak={dg.get('queue_measurements',{}).get('xrslam_sensor_handoff_peak')}")
tp=os.path.join(r,'telemetry.jsonl'); rows=[json.loads(l) for l in open(tp) if l.strip()] if os.path.exists(tp) else []
if rows:
    fp=[(x.get('physicalFootprintBytes') or 0)/1048576 for x in rows]; th=collections.Counter(x.get('thermalState') for x in rows); cpu=[x.get('cpuCoreEquivalent',0) for x in rows if x.get('cpuCoreEquivalent')]
    q=max(1,len(fp)//4)
    print(f"  telemetry n={len(rows)} footprint MB start={fp[0]:.0f} q1max={max(fp[:q]):.0f} q2max={max(fp[q:2*q]):.0f} q3max={max(fp[2*q:3*q]):.0f} end={fp[-1]:.0f} max={max(fp):.0f} thermal={dict(th)} cpu核当量 均值{sum(cpu)/max(1,len(cpu)):.2f} 峰{max(cpu) if cpu else 0:.2f}")
else: print("  telemetry 空")
PY
