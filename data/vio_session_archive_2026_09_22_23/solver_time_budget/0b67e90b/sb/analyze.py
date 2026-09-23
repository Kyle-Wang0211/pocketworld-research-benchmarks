#!/usr/bin/python3
# analyze.py — timing + ATE tables for the solver-budget matrix (run with /usr/bin/python3: numpy)
import csv, glob, hashlib, os, re, subprocess, sys
import numpy as np

S = os.path.dirname(os.path.abspath(__file__))
ATE = '/Users/kaidongwang/Developer/viobench-recordings/ate.py'
REF = {
    '6e2d4b99': ('/Users/kaidongwang/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum', True),
    'V1_01': ('/Users/kaidongwang/Developer/xrslam/pw_tools/regression/out/V1_01_easy_gt.tum', False),
    'V1_02': ('/Users/kaidongwang/Developer/xrslam/pw_tools/regression/out/V1_02_medium_gt.tum', False),
    'V1_03': ('/Users/kaidongwang/Developer/xrslam/pw_tools/regression/out/V1_03_difficult_gt.tum', False),
}
ARMS = ['basenr_prod', 'branch_prod', 'branch_prod_b0.035', 'branch_prod_b0.0233',
        'branch_prod_b0.010', 'branch_prod_b0.005', 'branch_prod_b0']
LABEL = {'basenr_prod': 'OFF 未改库(对照)', 'branch_prod': 'OFF 0.1s/10', 'branch_prod_b0.035': 'ON 35ms',
         'branch_prod_b0.0233': 'ON 23.3ms', 'branch_prod_b0.010': 'ON 10ms',
         'branch_prod_b0.005': 'ON 5ms', 'branch_prod_b0': 'ON 0ms(仅 minIter=3)'}
Q = [50, 95, 99, 100]


def ate(tum, sc):
    ref, yup = REF[sc]
    cmd = ['/usr/bin/python3', ATE, tum, ref] + (['--ref-y-up'] if yup else [])
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    m = re.search(r'Sim3 ATE ([\d.]+) cm \| 尺度偏差 ([\d.]+)% \| SE3 ATE ([\d.]+) cm', out)
    p = re.search(r'posyaw\(4DOF,VIO 标准\) ATE ([\d.]+) cm', out)
    return dict(sim3=float(m.group(1)), scale=float(m.group(2)), se3=float(m.group(3)),
                posyaw=float(p.group(1)))


def timing(csvf):
    r = list(csv.DictReader(open(csvf)))
    f = lambda k: np.array([float(x[k]) for x in r])
    # 「跟踪帧」= 这一帧周期里 SlidingWindowTracker::track() 跑过(frontend_worker.cpp 的 pw_bk_track_n
    # 增加);新旧两个库都有这个计数,口径一致。初始化完成前的帧不计入。
    trk = f('bk_track_n') > 0
    d = dict(frames=len(r), trk=int(trk.sum()))
    for k in ['wall_ms', 'cpu_ms', 'sw_solver_ms']:
        a = f(k)[trk]
        d[k] = np.percentile(a, Q) if np.all(np.isfinite(a)) and len(a) else np.full(4, np.nan)
    for k in ['stop_budget', 'stop_time', 'stop_iter', 'stop_conv', 'sw_iters', 'sw_solves']:
        a = f(k)
        d[k] = int(a[a >= 0].sum())
    d['init_ms'] = float(np.nansum(f('init_solver_ms')))
    return d


def main():
    rows = {}
    for sc in REF:
        for arm in ARMS:
            reps = sorted(glob.glob(f'{S}/out/{sc}/{arm}_r[0-9].tum'))
            reps = [t for t in reps if os.path.exists(t[:-4] + '.csv')]
            if not reps:
                continue
            T = [timing(t[:-4] + '.csv') for t in reps]
            A = [ate(t, sc) for t in reps]
            H = [hashlib.sha256(open(t, 'rb').read()).hexdigest()[:12] for t in reps]
            rows[(sc, arm)] = (T, A, H)
    import json
    out = {}
    for (sc, arm), (T, A, H) in rows.items():
        med = lambda k: np.median(np.stack([t[k] for t in T]), axis=0)
        rng = lambda k, i: (min(t[k][i] for t in T), max(t[k][i] for t in T))
        out[f'{sc}|{arm}'] = dict(
            n=len(T), sha=H, trk=T[0]['trk'],
            wall=med('wall_ms').tolist(), cpu=med('cpu_ms').tolist(), sw=med('sw_solver_ms').tolist(),
            wall_p99_rng=rng('wall_ms', 2), wall_max_rng=rng('wall_ms', 3), sw_p99_rng=rng('sw_solver_ms', 2),
            stop_budget=[t['stop_budget'] for t in T], stop_iter=[t['stop_iter'] for t in T],
            stop_time=[t['stop_time'] for t in T], iters=[t['sw_iters'] for t in T], solves=[t['sw_solves'] for t in T],
            init_ms=[t['init_ms'] for t in T],
            ate={k: [a[k] for a in A] for k in A[0]})
    json.dump(out, open(f'{S}/results.json', 'w'), indent=1, default=float)

    for sc in REF:
        base = out.get(f'{sc}|branch_prod')
        if not base:
            continue
        print(f'\n### {sc}  (tracking frames {base["trk"]}; 每臂 n={base["n"]} 次,分位数取各次的中位数)')
        print('| 臂 | 帧墙钟 p50 | p95 | p99 | max | 帧CPU p95 | p99 | 滑窗求解 p95 | p99 | max | 预算截停/求解次数 | 迭代合计 | SE3 ATE cm | posyaw cm | Sim3 cm | 尺度 % | 轨迹sha(各次) |')
        print('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
        for arm in ARMS:
            o = out.get(f'{sc}|{arm}')
            if not o:
                continue
            w, c, s = o['wall'], o['cpu'], o['sw']
            rat = lambda v, b: f'{v:.1f}' if arm == 'branch_prod' or not np.isfinite(v) else f'{v:.1f} ({v / b:.2f}×)'
            a = o['ate']
            ms = lambda k: (f'{np.mean(a[k]):.2f}' if max(a[k]) - min(a[k]) < 1e-9
                            else f'{np.mean(a[k]):.2f} [{min(a[k]):.2f}–{max(a[k]):.2f}]')
            sb = '–' if arm == 'basenr_prod' else f'{int(np.median(o["stop_budget"]))}/{int(np.median(o["solves"]))}'
            it = '–' if arm == 'basenr_prod' else f'{int(np.median(o["iters"]))}'
            print(f'| {LABEL[arm]} | {w[0]:.1f} | {rat(w[1], base["wall"][1])} | {rat(w[2], base["wall"][2])} | '
                  f'{rat(w[3], base["wall"][3])} | {rat(c[1], base["cpu"][1])} | {rat(c[2], base["cpu"][2])} | '
                  f'{rat(s[1], base["sw"][1])} | {rat(s[2], base["sw"][2])} | {rat(s[3], base["sw"][3])} | {sb} | {it} | '
                  f'{ms("se3")} | {ms("posyaw")} | {ms("sim3")} | {ms("scale")} | {",".join(sorted(set(o["sha"])))} |')


if __name__ == '__main__':
    main()
