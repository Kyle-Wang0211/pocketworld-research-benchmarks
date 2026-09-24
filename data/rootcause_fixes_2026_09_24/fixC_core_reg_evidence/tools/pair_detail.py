#!/usr/bin/python3
"""pair_detail.py <run_dir> <feed> <cap> i,j ... — for listed fid pairs: recon vs image two-view and DEVICE vs image
two-view (rotation diff deg / translation-direction diff deg), plus baseline length (device, m) and two-view inliers."""
import json, os, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); import prep_inputs as P
rd, feedf, cap = sys.argv[1:4]
feed = [json.loads(l) for l in open(feedf) if l.strip()]
cache = json.load(open(W + f'/results/twoview_cache_{cap}.json'))
def to_colmap(q, t):
    w, x, y, z = q; n = (w*w+x*x+y*y+z*z) ** .5; w, x, y, z = w/n, x/n, y/n, z/n
    return [-x, w, -z, y], [t[0], -t[1], -t[2]]
dl = {}
for l in open(rd + '/delivered_poses.txt'):
    v = l.split()
    if int(v[2]) == 1: dl[int(v[0])] = (list(map(float, v[3:7])), list(map(float, v[7:10])))
def rel(a, b): Ra, ta = P.q2R(*a[0]), np.array(a[1]); Rb, tb = P.q2R(*b[0]), np.array(b[1]); R = Rb @ Ra.T; return R, tb - R @ ta
def dang(a, b): return float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1))))
for s in sys.argv[4:]:
    a, b = map(int, s.split(','))
    fa, fb = feed[a]['frameIndex'], feed[b]['frameIndex']; c = cache.get(f'{fa},{fb}')
    if not c: print(a, b, 'no twoview'); continue
    Rc, tc = np.array(c['R_c']), np.array(c['t_c'])
    da = to_colmap(feed[a]['arkitCamFromWorldQwxyz'], feed[a]['arkitCamFromWorldTxyz']); db = to_colmap(feed[b]['arkitCamFromWorldQwxyz'], feed[b]['arkitCamFromWorldTxyz'])
    Rd, td = rel(da, db); Rr, tr = rel(dl[a], dl[b])
    base = np.linalg.norm(-P.q2R(*db[0]).T @ np.array(db[1]) + P.q2R(*da[0]).T @ np.array(da[1]))
    print('%3d-%3d base=%.3fm inl=%s ok=%s | recon vs img rot %.2f dir %.1f | device vs img rot %.2f dir %.1f | recon vs device rot %.2f dir %.1f' % (
        a, b, base, c['inl'], c['ok'], P.ang(Rr, Rc), dang(tr, tc), P.ang(Rd, Rc), dang(td, tc), P.ang(Rr, Rd), dang(tr, td)))
