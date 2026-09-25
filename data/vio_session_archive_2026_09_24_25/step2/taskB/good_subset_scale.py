#!/usr/bin/python3
"""Accuracy of the delivered model after the robust alignment, judged on a VERIFIED-GOOD subset of frames:
Umeyama Sim3 recon->device on the good subset only vs the core's robust fit (device_align_offline, σ=0.040, all pairs).
Reports the scale difference (robust fit vs good-subset fit) and the residuals of the robust-fit-aligned model on the good
frames. usage: good_subset_scale.py <pairs.txt> <good frame ids comma-separated or lo-hi>"""
import json, os, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); import prep_inputs as P  # noqa
pf, spec = sys.argv[1], sys.argv[2]
good = set()
for tok in spec.split(','):
    if '-' in tok: a, b = map(int, tok.split('-')); good |= set(range(a, b + 1))
    else: good.add(int(tok))
rows = {int(l.split()[0]): [float(v) for v in l.split()[1:]] for l in open(pf) if l.strip()}
cen = lambda q, t: -P.q2R(*q).T @ np.array(t)
ks = sorted(k for k in rows if k in good)
Cr = np.array([cen(rows[k][0:4], rows[k][4:7]) for k in ks]); Cd = np.array([cen(rows[k][7:11], rows[k][11:14]) for k in ks])
s, R, t = P.umeyama(Cr.T, Cd.T); t = np.asarray(t).ravel()
e_good = np.linalg.norm((s * (R @ Cr.T)).T + t - Cd, axis=1)
r = json.loads(subprocess.run([W + '/build/device_align_offline', pf, '0.04'], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
Rf = P.q2R(*r['q']); tf = np.array(r['t'])
e_fit = np.linalg.norm((r['scale'] * (Rf @ Cr.T)).T + tf - Cd, axis=1)
ext = np.linalg.norm(Cd - Cd.mean(0), axis=1).max() * 2
print(json.dumps(dict(pairs=os.path.basename(pf), n_good=len(ks), robust_fit_scale=r['scale'], good_only_scale=float(s),
      scale_diff_pct=100 * (r['scale'] / s - 1), robust_inliers=r['inliers_all'], n=r['n_pairs'],
      good_resid_under_good_fit_mm=[round(1e3 * float(np.median(e_good)), 1), round(1e3 * float(e_good.max()), 1)],
      good_resid_under_robust_fit_mm=[round(1e3 * float(np.median(e_fit)), 1), round(1e3 * float(e_fit.max()), 1)],
      good_extent_m=round(float(ext), 3))))
