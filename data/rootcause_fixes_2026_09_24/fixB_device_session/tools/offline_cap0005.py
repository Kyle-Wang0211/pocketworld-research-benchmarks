#!/usr/bin/python3
"""Offline Sim3 + gate on cap_1789119308200005 with only trusted (reference-session) frames as pairs.
Pairs come from step2 (delivered CamFromWorld vs fed device CamFromWorld, keyed by refeed frameId);
the trust mask comes from the PATCHED Dart planner run read-only on the real capture dir."""
import json, subprocess, sys
F = sys.argv[1]; S2 = sys.argv[2]
TOOL = F + '/build/device_align_offline'
plan = json.load(open(F + '/results/cap0005_trust_plan.json'))['cap_1789119308200005']['frames']
trusted = {f['fid'] for f in plan if f['trusted']}
recorded = set(range(7, 23))            # what a per-photo session record would give (all of session 2)
not_ready = {8}                          # tap-79 sidecar tracking_state=limited_initializing (agent A's gate)
models = {'phone_delivered': S2 + '/results/phone_gate/cap_1789119308200005.pairs.txt',
          'host_replay_phr': S2 + '/taskB/eval/cap_1789119308200005__phr_cap_1789119308200005.pairs.txt',
          'resume_route_rs': S2 + '/taskB/eval/cap_1789119308200005__rs_cap_1789119308200005.pairs.txt'}
arms = {'before_all23_mixed': None, 'B_legacy_plan_15': trusted, 'B_recorded_16': recorded,
        'B_legacy_plus_A_14': trusted - not_ready, 'B_recorded_plus_A_15': recorded - not_ready}
out = {}
for mname, mp in models.items():
    lines = [l for l in open(mp).read().splitlines() if l.strip()]
    for aname, keep in arms.items():
        sel = [l for l in lines if keep is None or int(l.split()[0]) in keep]
        pf = f'{F}/results/cap0005__{mname}__{aname}.pairs.txt'
        open(pf, 'w').write('\n'.join(sel) + '\n')
        for sig in (0.04, 1.0):
            j = json.loads(subprocess.run([TOOL, pf, str(sig)], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
            out[f'{mname}|{aname}|{sig}'] = dict(status=j['status'], n=j['n_pairs'], inliers=j['inliers_all'], scale=j['scale'],
                max_err_m=j['max_error_m'], med_mm=1e3*j['centre_err_m']['median'], max_mm=1e3*j['centre_err_m']['max'],
                outliers=[f for f, i in zip(j['frame_ids'], j['inlier_all']) if not i])
json.dump(out, open(F + '/results/offline_cap0005.json', 'w'), indent=1)
for mname in models:
    print('==', mname)
    for aname in arms:
        a, b = out[f'{mname}|{aname}|0.04'], out[f'{mname}|{aname}|1.0']
        ref = out[f'{mname}|B_recorded_16|0.04']['scale']
        print(f'  {aname:22s} n={a["n"]:2d} σ=0.04:{a["status"]:21s} inl {a["inliers"]:2d} scale {a["scale"]:.5f} '
              f'({100*(a["scale"]/ref-1):+.2f}% vs recorded16) med/max {a["med_mm"]:.1f}/{a["max_mm"]:.1f} mm out {a["outliers"]} | '
              f'σ=1m:{b["status"]} scale {b["scale"]:.5f} ({100*(b["scale"]/ref-1):+.2f}%)')
