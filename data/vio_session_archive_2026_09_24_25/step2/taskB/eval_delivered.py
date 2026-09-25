#!/usr/bin/python3
"""Per-frame device residuals of a core replay run from its delivered_poses.txt (kept after >5 MB cleanup) with the
core's own alignment code (build/device_align_offline, σ=0.040 covariance path). usage: eval_delivered.py <cap> <run_dir>"""
import json, os, subprocess, sys
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG = {r['cap']: r for r in json.load(open(W + '/results/phone_gate/phone_gate.json'))['rows']}
cap, rd = sys.argv[1], sys.argv[2]
fed = {j['frameId']: j for j in (json.loads(l) for l in open(PG[cap]['dir'] + '/official_sfm_fed_frames.jsonl'))}
def to_colmap(q, t):
    w, x, y, z = q; n = (w*w+x*x+y*y+z*z) ** .5; w, x, y, z = w/n, x/n, y/n, z/n
    return [-x, w, -z, y], [t[0], -t[1], -t[2]]
lines = []
for l in open(rd + '/delivered_poses.txt'):
    v = l.split()
    if int(v[2]) != 1: continue
    f = int(v[1]) if int(v[1]) in fed else int(v[0])
    f = int(v[0])
    dq, dt = to_colmap(fed[f]['arkitCamFromWorldQwxyz'], fed[f]['arkitCamFromWorldTxyz'])
    lines.append('%d %s %s %s' % (f, ' '.join(v[3:10]), ' '.join('%.17g' % x for x in dq), ' '.join('%.17g' % x for x in dt)))
pf = W + f'/taskB/eval/{cap}__{os.path.basename(rd)}.pairs.txt'; os.makedirs(os.path.dirname(pf), exist_ok=True); open(pf, 'w').write('\n'.join(lines) + '\n')
r = json.loads(subprocess.run([W + '/build/device_align_offline', pf, '0.04'], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
err = {f: round(e * 1e3, 1) for f, e in zip(r['frame_ids'], r['centre_err_all_m'])}
print(json.dumps(dict(cap=cap, run=os.path.basename(rd), status=r['status'], inliers=r['inliers_all'], n=r['n_pairs'], scale=r['scale'],
                      outliers={f: err[f] for f, i in zip(r['frame_ids'], r['inlier_all']) if not i}, max_mm=max(err.values()),
                      median_mm=1e3 * r['centre_err_m']['median'], per_frame_mm=err, missing=sorted(set(fed) - set(err)))))
