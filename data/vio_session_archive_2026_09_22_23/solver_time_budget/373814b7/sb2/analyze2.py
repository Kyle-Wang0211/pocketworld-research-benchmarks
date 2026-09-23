#!/usr/bin/python3
# analyze2.py — timing + ATE tables for this session's solver-budget matrix.
# Adapted from the previous agent's sb/analyze.py (same ATE tool, same "tracking frame" filter).
# Run with /usr/bin/python3 (numpy).
import csv, glob, hashlib, json, os, re, subprocess, sys
import numpy as np

S = os.path.dirname(os.path.abspath(__file__))
ATE = '/Users/kaidongwang/Developer/viobench-recordings/ate.py'
REF = {
    'V1_01': ('/Users/kaidongwang/Developer/xrslam/pw_tools/regression/out/V1_01_easy_gt.tum', False),
    'V1_02': ('/Users/kaidongwang/Developer/xrslam/pw_tools/regression/out/V1_02_medium_gt.tum', False),
    'V1_03': ('/Users/kaidongwang/Developer/xrslam/pw_tools/regression/out/V1_03_difficult_gt.tum', False),
    '6e2d4b99': ('/Users/kaidongwang/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum', True),
}
BUDGET = {'branch_prod_b0.035': 35.0, 'branch_prod_b0.0233': 23.3, 'branch_prod_b0.0117': 11.7}
ARMS = ['basenr_prod', 'branch_prod', 'branch_prod_b0.035', 'branch_prod_b0.0233', 'branch_prod_b0.0117']
LABEL = {'basenr_prod': 'OFF, unmodified lib (04c0e83)', 'branch_prod': 'OFF (keys unset) 0.1 s/10',
         'branch_prod_b0.035': 'ON 35 ms (OKVIS default)', 'branch_prod_b0.0233': 'ON 23.3 ms (0.7x33.3ms, 30 Hz)',
         'branch_prod_b0.0117': 'ON 11.7 ms (0.7x16.67ms, 60 Hz)'}
Q = [50, 95, 99, 100]


def ate(tum, sc):
    ref, yup = REF[sc]
    out = subprocess.run(['/usr/bin/python3', ATE, tum, ref] + (['--ref-y-up'] if yup else []),
                         capture_output=True, text=True).stdout
    m = re.search(r'Sim3 ATE ([\d.]+) cm \| 尺度偏差 ([\d.]+)% \| SE3 ATE ([\d.]+) cm', out)
    p = re.search(r'posyaw\(4DOF,VIO 标准\) ATE ([\d.]+) cm', out)
    return dict(sim3=float(m.group(1)), scale=float(m.group(2)), se3=float(m.group(3)), posyaw=float(p.group(1)))


def timing(csvf, budget_ms):
    r = list(csv.DictReader(open(csvf)))
    f = lambda k: np.array([float(x[k]) for x in r])
    trk = f('bk_track_n') > 0          # frames where SlidingWindowTracker::track() ran
    d = dict(frames=len(r), trk=int(trk.sum()))
    for k in ['wall_ms', 'cpu_ms', 'sw_solver_ms']:
        a = f(k)[trk]
        d[k] = np.percentile(a, Q) if len(a) and np.all(np.isfinite(a)) else np.full(4, np.nan)
    d['wall_gt100'] = int((f('wall_ms') > 100).sum())
    for k in ['stop_budget', 'stop_time', 'stop_iter', 'stop_conv', 'sw_iters', 'sw_solves']:
        a = f(k)
        d[k] = int(a[a >= 0].sum()) if np.any(a >= 0) else -1
    sw = f('sw_solver_ms')[trk]
    if budget_ms and np.all(np.isfinite(sw)):
        over = sw > budget_ms
        d['over_rate'] = float(over.mean())
        d['over_max'] = float((sw - budget_ms).max())
    return d


def main():
    out = {}
    for sc in REF:
        for arm in ARMS + ['basenr_upstream', 'branch_upstream']:
            reps = sorted(glob.glob(f'{S}/out/{sc}/{arm}_r[0-9].tum'))
            if not reps:
                continue
            T = [timing(t[:-4] + '.csv', BUDGET.get(arm)) for t in reps]
            A = [ate(t, sc) for t in reps] if 'upstream' not in arm else []
            H = [hashlib.sha256(open(t, 'rb').read()).hexdigest()[:16] for t in reps]
            med = lambda k: np.median(np.stack([t[k] for t in T]), axis=0).tolist()
            out[f'{sc}|{arm}'] = dict(
                n=len(T), sha=H, trk=T[0]['trk'], wall=med('wall_ms'), cpu=med('cpu_ms'), sw=med('sw_solver_ms'),
                sw_all=[t['sw_solver_ms'].tolist() for t in T], wall_all=[t['wall_ms'].tolist() for t in T],
                wall_gt100=[t['wall_gt100'] for t in T],
                stop_budget=[t['stop_budget'] for t in T], stop_iter=[t['stop_iter'] for t in T],
                stop_time=[t['stop_time'] for t in T], stop_conv=[t['stop_conv'] for t in T],
                iters=[t['sw_iters'] for t in T], solves=[t['sw_solves'] for t in T],
                over_rate=[t.get('over_rate') for t in T], over_max=[t.get('over_max') for t in T],
                ate={k: [a[k] for a in A] for k in (A[0] if A else {})})
    json.dump(out, open(f'{S}/results2.json', 'w'), indent=1, default=float)

    print('## identity (sha256[:16] of the TUM output)')
    for sc in REF:
        for pair in [('basenr_prod', 'branch_prod'), ('basenr_upstream', 'branch_upstream')]:
            a, b = out.get(f'{sc}|{pair[0]}'), out.get(f'{sc}|{pair[1]}')
            if a and b:
                ok = len(set(a['sha'] + b['sha'])) == 1
                print(f'{sc:9s} {pair[0]:16s} {a["sha"]}  {pair[1]:16s} {b["sha"]}  -> {"IDENTICAL" if ok else "DIFFER"}'
                      f'  (base frames>100ms wall {a["wall_gt100"]}, branch stop_time {b["stop_time"]})')

    for sc in REF:
        base = out.get(f'{sc}|branch_prod')
        if not base:
            continue
        print(f'\n### {sc}  (tracking frames {base["trk"]}; n={base["n"]} reps per arm; each quantile = median over reps)')
        print('| arm | solve p50 | p95 | p99 | max | overrun>budget | frame wall p95 | p99 | max | CPU p99 | budget stops/solves | iters | SE3 cm | posyaw cm | Sim3 cm | scale % | sha |')
        print('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
        for arm in ARMS:
            o = out.get(f'{sc}|{arm}')
            if not o:
                continue
            w, c, s = o['wall'], o['cpu'], o['sw']
            def rat(v, b):
                if not np.isfinite(v):
                    return '–'
                return f'{v:.1f}' if arm == 'branch_prod' else f'{v:.1f} ({v / b:.2f}×)'
            a = o['ate']
            ms = lambda k: (f'{np.mean(a[k]):.2f}' if max(a[k]) - min(a[k]) < 1e-9
                            else f'{np.mean(a[k]):.2f} [{min(a[k]):.2f}–{max(a[k]):.2f}]')
            ov = '–' if o['over_rate'][0] is None else f'{100*np.median(o["over_rate"]):.1f}% / +{np.median(o["over_max"]):.1f}ms'
            sb = '–' if arm == 'basenr_prod' else f'{int(np.median(o["stop_budget"]))}/{int(np.median(o["solves"]))}'
            it = '–' if arm == 'basenr_prod' else f'{int(np.median(o["iters"]))}'
            print(f'| {LABEL[arm]} | {rat(s[0], base["sw"][0])} | {rat(s[1], base["sw"][1])} | {rat(s[2], base["sw"][2])} | '
                  f'{rat(s[3], base["sw"][3])} | {ov} | {rat(w[1], base["wall"][1])} | {rat(w[2], base["wall"][2])} | '
                  f'{rat(w[3], base["wall"][3])} | {rat(c[2], base["cpu"][2])} | {sb} | {it} | '
                  f'{ms("se3")} | {ms("posyaw")} | {ms("sim3")} | {ms("scale")} | {",".join(sorted(set(o["sha"])))[:40]} |')


if __name__ == '__main__':
    main()
