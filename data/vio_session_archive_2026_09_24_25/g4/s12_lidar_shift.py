import json, numpy as np
from g4lib import *
GRID = list(range(-12, 19, 3))
def work(key):
    run = Run(key); res = {}
    for nm, P0 in (('arkit', all_arkit(run)), ('xr', all_xr(run))):
        I = Interp(P0); M = []
        for s in GRID:
            P = {t: I(t + int(s * 1e6)) for t in run.ark}
            P = {t: p for t, p in P.items() if p is not None}
            M.append(ratios_of(run.measure(P)))
        M = np.vstack(M); n = M.shape[1]; rng = np.random.default_rng(2); am = []
        for _ in range(1000):
            idx = rng.integers(0, n, n)
            c = [between_iqr(M[i, idx][np.isfinite(M[i, idx])]) for i in range(len(GRID))]
            am.append(GRID[int(np.argmin(c))])
        am = np.array(am)
        c0 = [between_iqr(M[i][np.isfinite(M[i])]) for i in range(len(GRID))]
        res[nm] = dict(point=GRID[int(np.argmin(c0))], ci=[float(np.percentile(am, 2.5)), float(np.percentile(am, 97.5))],
                       hist={str(g): float(np.mean(am == g)) for g in GRID})
    return key, res
if __name__ == '__main__':
    import multiprocessing as mp
    with mp.get_context('fork').Pool(3) as p:
        outs = dict(p.map(work, list(RUNS)))
    json.dump(outs, open('s12.json', 'w'), indent=1)
    for k, r in outs.items():
        for nm, v in r.items():
            print(f"{k} {nm:5s}: LiDAR 帧对间 IQR 最小的位姿时移 = {v['point']:+d} ms,bootstrap 95% [{v['ci'][0]:+.0f}, {v['ci'][1]:+.0f}] ms;分布 " + ' '.join(f"{g}:{p:.2f}" for g, p in v['hist'].items() if p > 0.02))
