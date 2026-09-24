#!/usr/bin/python3
"""cross_pairs.py <run_dir> <feed> <cap> <untrusted spec> — every pair (u, t), u in the untrusted set, t outside it, both
registered in the delivered model and with >= 30 raw matches in the capture db: delivered relative pose vs verified image
two-view geometry (twoview_check.image_rel, counted only when OpenCV & COLMAP agree). Writes 'cross_pairs' into metrics.json."""
import json, os, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); sys.path.insert(0, W + '/tools')
import prep_inputs as P, twoview_check as TV
rd, feedf, cap, spec = sys.argv[1:5]
U = set()
for tok in spec.split(','):
    if '-' in tok: lo, hi = map(int, tok.split('-')); U |= set(range(lo, hi + 1))
    elif tok: U.add(int(tok))
feed = [json.loads(l) for l in open(feedf) if l.strip()]
cachef = W + f'/results/twoview_cache_{cap}.json'
cache = json.load(open(cachef)) if os.path.exists(cachef) else {}
os.environ['PAIRS'] = '/dev/null'
C = TV.Cap(cap)
dl = {}
for l in open(rd + '/delivered_poses.txt'):
    v = l.split()
    if int(v[2]) == 1: dl[int(v[0])] = (list(map(float, v[3:7])), list(map(float, v[7:10])))
def rel(a, b): Ra, ta = P.q2R(*a[0]), np.array(a[1]); Rb, tb = P.q2R(*b[0]), np.array(b[1]); R = Rb @ Ra.T; return R, tb - R @ ta
def dang(a, b): return float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1))))
rows = []; dirty = False
for u in sorted(U):
    for t in range(len(feed)):
        if t in U or u not in dl or t not in dl: continue
        a, b = (u, t) if u < t else (t, u)
        fa, fb = feed[a]['frameIndex'], feed[b]['frameIndex']; key = f'{fa},{fb}'
        if key not in cache:
            im = C.image_rel(fa, fb); dirty = True
            if im is None or im.get('R_c') is None or np.linalg.norm(im['t_c']) == 0: cache[key] = None
            else:
                ok = bool(TV.ang(im['R'] @ im['R_c'].T) < 2.0 and TV.dang(im['t'], im['t_c']) < 5.0 and im['colmap_config'] == 'CALIBRATED')
                cache[key] = {'R_c': np.asarray(im['R_c']).tolist(), 't_c': np.asarray(im['t_c']).tolist(), 'ok': ok, 'inl': im['colmap_inl']}
        c = cache[key]
        if not c or not c['ok']: continue
        Rr, tr = rel(dl[a], dl[b]); rr, dr = P.ang(Rr, np.array(c['R_c'])), dang(tr, np.array(c['t_c']))
        rows.append((a, b, rr, dr))
if dirty: json.dump(cache, open(cachef, 'w'))
out = {'n_pairs': len(rows), 'rot_deg_median': float(np.median([r[2] for r in rows])) if rows else None,
       'dir_deg_median': float(np.median([r[3] for r in rows])) if rows else None,
       'n_bad': sum(1 for r in rows if r[3] > 20 or r[2] > 5), 'rot_deg_max': float(max(r[2] for r in rows)) if rows else None,
       'bad': [[a, b, round(r, 2), round(d, 1)] for a, b, r, d in rows if d > 20 or r > 5][:30]}
m = json.load(open(rd + '/metrics.json')); m['cross_pairs'] = out; json.dump(m, open(rd + '/metrics.json', 'w'), indent=1, default=float)
print(os.path.basename(rd), json.dumps(out)[:400])
