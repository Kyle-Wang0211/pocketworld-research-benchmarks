#!/usr/bin/python3
"""Offline gate false-positive estimate on the 90 step-1 phone captures.
For each capture: delivered registered poses (official_sfm_sparse_meta.json 'poses', CamFromWorld)
vs fed device poses (official_sfm_fed_frames.jsonl, ARKit camera axes -> COLMAP axes with the core's
own conversion, mandatory_arkit_gravity_v1.cc:68-72), paired by frame id; then the SAME C++ code the
core runs (device_pose_alignment_v1.h via build/device_align_offline). Every file is stat'ed for the
'dataless' flag immediately before it is opened; dataless files are never opened."""
import json, os, subprocess, sys, collections
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S1 = W + '/../step1'
TOOL = W + '/build/device_align_offline'
OUT = W + '/results/phone_gate'; os.makedirs(OUT, exist_ok=True)
SIDE = 'official_sfm_live.db.arkit_pose_v1'

def is_dataless(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    return r.returncode != 0 or 'dataless' in r.stdout

def to_colmap(q, t):  # q_C * q_arkit, t' = (tx,-ty,-tz)
    w, x, y, z = q; n = (w*w+x*x+y*y+z*z) ** 0.5; w, x, y, z = w/n, x/n, y/n, z/n
    return [-x, w, -z, y], [t[0], -t[1], -t[2]]

def run(pairs_path, sigma, fit='all'):
    r = subprocess.run([TOOL, pairs_path, str(sigma), fit], capture_output=True, text=True)
    if r.returncode != 0: raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout.strip().splitlines()[-1])

R = json.load(open(S1 + '/results.json'))['results']
rows = []; skipped = []
for cid, vs in sorted(R.items()):
    d = vs[0]['dir']
    meta_p, fed_p = d + '/official_sfm_sparse_meta.json', d + '/official_sfm_fed_frames.jsonl'
    if is_dataless(meta_p) or is_dataless(fed_p):
        skipped.append((cid, 'dataless')); continue
    meta = json.load(open(meta_p))
    fed = {}
    for ln in open(fed_p):
        try: j = json.loads(ln)
        except Exception: continue
        if 'arkitCamFromWorldQwxyz' in j and 'arkitCamFromWorldTxyz' in j:
            fed[j['frameId']] = to_colmap(j['arkitCamFromWorldQwxyz'], j['arkitCamFromWorldTxyz'])
        elif 'arkitCameraCenterWorld' in j:   # centre only: identity R, t=-C (rotation stat meaningless)
            C = j['arkitCameraCenterWorld']; fed[j['frameId']] = ([1, 0, 0, 0], [-C[0], -C[1], -C[2]], 'centre_only')
    lines = []
    for p in meta.get('poses', []):
        if not p.get('registered', True) or p['frame_id'] not in fed: continue
        q = p['quat_wxyz']
        if sum(v * v for v in q) < 1e-12: continue
        dq, dt = fed[p['frame_id']][:2]
        lines.append('%d %s %s %s %s' % (p['frame_id'], ' '.join('%.17g' % v for v in q), ' '.join('%.17g' % v for v in p['t']),
                                         ' '.join('%.17g' % v for v in dq), ' '.join('%.17g' % v for v in dt)))
    centre_only = any(len(v) == 3 for v in fed.values())
    pf = f'{OUT}/{cid}.pairs.txt'; open(pf, 'w').write('\n'.join(lines) + '\n')
    res = {s: run(pf, s) for s in (0.040, 1.0)}
    rows.append(dict(cap=cid, dir=d, n_pairs=len(lines), centre_only=centre_only,
                     step1_scale=vs[0]['robust']['scale'], step1_rms_mm=vs[0]['robust']['rms_mm_dev'],
                     r040=res[0.040], r100=res[1.0]))
json.dump(dict(rows=rows, skipped=skipped), open(OUT + '/phone_gate.json', 'w'), indent=1)
st = collections.Counter(r['r040']['status'] for r in rows)
st1 = collections.Counter(r['r100']['status'] for r in rows)
print('captures', len(rows), 'skipped', skipped)
print('sigma=0.040 status:', dict(st)); print('sigma=1.0 (COLMAP default) status:', dict(st1))
for r in rows:
    a = r['r040']
    if a['status'] != 'aligned':
        print(' TRIP', r['cap'], a['status'], 'inliers %d/%d' % (a['inliers_all'], a['n_pairs']), 'max_err_mm %.1f' % (1e3 * a['centre_err_m']['max']),
              'median_mm %.1f' % (1e3 * a['centre_err_m']['median']), 'scale %.4f' % a['scale'], 'step1_scale %.4f' % r['step1_scale'])
mx = np.array([r['r040']['centre_err_m']['max'] for r in rows]) * 1e3
md = np.array([r['r040']['centre_err_m']['median'] for r in rows]) * 1e3
print('per-capture centre err (mm): median-of-medians %.1f, p90 of max %.1f, max of max %.1f' % (np.median(md), np.percentile(mx, 90), mx.max()))
print('outlier frames total:', sum(r['r040']['n_pairs'] - r['r040']['inliers_all'] for r in rows), 'of', sum(r['r040']['n_pairs'] for r in rows))
for c in ('cap_1789119308200005', 'cap_1787733401226757'):
    r = [x for x in rows if x['cap'] == c][0]; a = r['r040']
    bad = [(f, round(e * 1e3, 1)) for f, e, i in zip(a['frame_ids'], a['centre_err_all_m'], a['inlier_all']) if not i]
    top = sorted(zip(a['centre_err_all_m'], a['frame_ids']), reverse=True)[:5]
    print(c, a['status'], 'inliers %d/%d' % (a['inliers_all'], a['n_pairs']), 'outliers', bad, 'top5 err mm', [(f, round(e * 1e3, 1)) for e, f in top])
