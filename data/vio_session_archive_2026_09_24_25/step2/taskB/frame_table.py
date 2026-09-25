#!/usr/bin/python3
"""Task B per-frame table for the tripped captures (read-only on capture dirs; every file stat'ed for
'dataless' before opening). Columns: frame id, photo, ARKit timestamp + dt, tracking state (photo sidecar
written by the native thin executor), device centre step, delivered-model centre step (x fitted scale),
post-alignment centre error at sigma=0.040 (phone_gate.json, core header code), inlier flag."""
import json, os, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG = json.load(open(W + '/results/phone_gate/phone_gate.json'))['rows']
def ok(p, soft=False):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    if r.returncode != 0 or 'dataless' in r.stdout:
        if soft: return None
        raise SystemExit('dataless/missing ' + p)
    return p
def q2R(w, x, y, z):
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
def centre(q, t): return -q2R(*q).T @ np.asarray(t)
for cap in sys.argv[1:]:
    row = [r for r in PG if r['cap'] == cap][0]; d = row['dir']; a = row['r040']
    fed = {j['frameId']: j for j in (json.loads(l) for l in open(ok(d + '/official_sfm_fed_frames.jsonl')))}
    pairs = {int(l.split()[0]): [float(v) for v in l.split()[1:]] for l in open(W + f'/results/phone_gate/{cap}.pairs.txt') if l.strip()}
    err = dict(zip(a['frame_ids'], a['centre_err_all_m'])); inl = dict(zip(a['frame_ids'], a['inlier_all']))
    print(f'== {cap} status={a["status"]} inliers {a["inliers_all"]}/{a["n_pairs"]} scale(device/recon)={a["scale"]:.4f} max_error={a["max_error_m"]*1e3:.0f}mm')
    man = d + '/official_capture_manifest.json'
    if os.path.exists(man): print('   manifest:', {k: v for k, v in json.load(open(ok(man))).items() if k not in ('frames',)})
    dead = sorted(f for f in os.listdir(d) if '.dead-' in f)
    if dead: print('   dead-session files:', dead)
    prevD = prevC = prevT = None
    order = sorted(fed, key=lambda k: fed[k]['captureTimestamp']) if '--time' in os.environ.get('FT_OPTS', '') else sorted(fed)
    for fid in order:
        j = fed[fid]; b = os.path.basename(j['jpegPath']); sp = ok(d + '/photos_highres/' + b[:-4] + '.json', soft=True)
        sc = json.load(open(sp)) if sp else {'tracking_state': '(no sidecar)'}
        D = np.array(j['arkitCameraCenterWorld']); t = j['captureTimestamp']
        C = centre(pairs[fid][0:4], pairs[fid][4:7]) * a['scale'] if fid in pairs else None
        sd = np.linalg.norm(D - prevD) if prevD is not None else 0.0
        sc_ = np.linalg.norm(C - prevC) if (C is not None and prevC is not None) else float('nan')
        print('   %3d %-24s t=%10.3f dt=%6.3f trk=%-22s dev_step=%.3f rec_step=%.3f err=%7.1fmm %s' % (
            fid, b, t, t - prevT if prevT else 0, sc.get('tracking_state'), sd, sc_, 1e3 * err.get(fid, float('nan')),
            '' if inl.get(fid, 1) else '<-- OUTLIER'))
        prevD, prevT = D, t
        prevC = C if C is not None else prevC
