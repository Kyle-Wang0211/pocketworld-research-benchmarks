#!/usr/bin/python3
"""Evaluate a model (core debug dump dir, or COLMAP TXT/BIN model dir) of a phone capture against the fed device poses:
per-frame centre residual after the core's own robust alignment (build/device_align_offline, σ=0.040 covariance path),
per-image #3D observations, per-image mean reprojection error (pycolmap), plus scale from verified-good frames.
usage: eval_model.py <cap> <model_dir> [label] [--good=f1,f2,...]"""
import json, os, subprocess, sys
import numpy as np, pycolmap
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); import prep_inputs as P  # noqa
PG = {r['cap']: r for r in json.load(open(W + '/results/phone_gate/phone_gate.json'))['rows']}
cap, md = sys.argv[1], sys.argv[2]; label = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else os.path.basename(md)
good = None
for a in sys.argv[3:]:
    if a.startswith('--good='):
        good = set()
        for tok in a[7:].split(','):
            if '-' in tok: lo, hi = map(int, tok.split('-')); good |= set(range(lo, hi + 1))
            else: good.add(int(tok))
d = PG[cap]['dir']
fed = {j['frameId']: j for j in (json.loads(l) for l in open(d + '/official_sfm_fed_frames.jsonl'))}
def to_colmap(q, t):
    w, x, y, z = q; n = (w*w+x*x+y*y+z*z) ** .5; w, x, y, z = w/n, x/n, y/n, z/n
    return [-x, w, -z, y], [t[0], -t[1], -t[2]]
r = pycolmap.Reconstruction(md)
stats = {}; lines = []
for iid, im in r.images.items():
    if not im.has_pose: continue
    f = int(''.join(c for c in im.name if c.isdigit()))
    if f not in fed: continue
    errs = []
    for p2 in im.points2D:
        if p2.has_point3D():
            errs.append(np.linalg.norm(im.project_point(r.points3D[p2.point3D_id].xyz) - p2.xy) if im.project_point(r.points3D[p2.point3D_id].xyz) is not None else np.nan)
    T = im.cam_from_world() if callable(im.cam_from_world) else im.cam_from_world
    q = T.rotation.quat  # xyzw
    stats[f] = dict(n_obs=im.num_points3D, reproj=float(np.nanmean(errs)) if errs else float('nan'))
    dq, dt = to_colmap(fed[f]['arkitCamFromWorldQwxyz'], fed[f]['arkitCamFromWorldTxyz'])
    lines.append('%d %s %s %s %s' % (f, ' '.join('%.17g' % v for v in [q[3], q[0], q[1], q[2]]), ' '.join('%.17g' % v for v in T.translation),
                                     ' '.join('%.17g' % v for v in dq), ' '.join('%.17g' % v for v in dt)))
os.makedirs(W + '/taskB/eval', exist_ok=True)
pf = W + f'/taskB/eval/{cap}__{label}.pairs.txt'; open(pf, 'w').write('\n'.join(lines) + '\n')
res = json.loads(subprocess.run([W + '/build/device_align_offline', pf, '0.04'], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
out = dict(cap=cap, label=label, n_reg=len(stats), n_fed=len(fed), n_points=len(r.points3D), status=res['status'],
           inliers=res['inliers_all'], n_pairs=res['n_pairs'], scale=res['scale'],
           outliers={f: round(e * 1e3, 1) for f, e, i in zip(res['frame_ids'], res['centre_err_all_m'], res['inlier_all']) if not i},
           centre_err_med_mm=1e3 * res['centre_err_m']['median'], mean_reproj=float(np.nanmean([s['reproj'] for s in stats.values()])))
if good:  # scale from verified-good frames only (Umeyama recon->device), compare with the robust fit
    ks = sorted(f for f in stats if f in good)
    C = {int(l.split()[0]): l.split() for l in lines}
    Cr = np.array([-P.q2R(*map(float, C[k][1:5])).T @ np.array(list(map(float, C[k][5:8]))) for k in ks])
    Cd = np.array([-P.q2R(*map(float, C[k][8:12])).T @ np.array(list(map(float, C[k][12:15]))) for k in ks])
    s, R, t = P.umeyama(Cr.T, Cd.T); out['scale_good_only'] = float(s); out['scale_diff_pct'] = 100 * (res['scale'] / s - 1)
    e = np.linalg.norm((s * (R @ Cr.T)).T + np.asarray(t).ravel() - Cd, axis=1); out['good_only_resid_mm_med_max'] = [1e3 * float(np.median(e)), 1e3 * float(e.max())]
out['frames_missing'] = sorted(set(fed) - set(stats))
out['weak_frames(<=40 obs)'] = {f: s['n_obs'] for f, s in sorted(stats.items()) if s['n_obs'] <= 40}
out['per_frame_obs_of_outliers'] = {f: stats[f] for f in out['outliers']}
print(json.dumps(out, default=float))
json.dump(out, open(W + f'/taskB/eval/{cap}__{label}.json', 'w'), indent=1, default=float)
