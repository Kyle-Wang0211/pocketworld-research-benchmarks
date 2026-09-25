import sys, json, pickle, numpy as np, time
from g4lib import *
res = {}
for key in RUNS:
    t0 = time.time()
    run = Run(key)
    rep = json.load(open(run.cfg['report']))
    out = {}
    for name, poses in (('arkit', run.ark), ('xr', run.xr)):
        cur = run.curve(poses)
        cr = {o: ratios_of(v) for o, v in cur.items()}
        c, amin = g4_from_curve(cr)
        k = 1 / np.nanmedian(cr[0])
        old = rep['trajectories'][name]
        oldc = old['alignment_curve_between_rel_iqr_by_depth_row_offset']
        print(key, name, 'k=%.4f (报告 %.4f)' % (k, old['estimate']['k']), 'n=%d' % np.isfinite(cr[0]).sum(),
              'curve', {o: round(v, 4) for o, v in c.items()}, 'argmin', amin,
              '报告', {o: round(oldc[str(o)], 4) for o in c})
        out[name] = {'curve_pairs': cur}
    res[key] = out
    pickle.dump(out, open(f'curve_{key}.pkl', 'wb'))
    print(key, '用时 %.0fs' % (time.time() - t0), flush=True)
