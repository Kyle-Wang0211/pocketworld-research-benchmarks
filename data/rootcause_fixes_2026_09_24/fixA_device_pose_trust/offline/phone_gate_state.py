#!/usr/bin/python3
"""fixA offline evidence: rerun the core's end-of-finalize Sim3 alignment + gate
(device_pose_alignment_v1.h via build/device_align_offline, the SAME code the
core runs) on the 90 step-1 phone captures, with and without the frames whose
recorded tracker state is not normal (devicePoseTrusted=false under fix A).

Pairing and axis conversion are copied verbatim from step2/tools/phone_gate_offline.py
(delivered poses = official_sfm_sparse_meta.json 'poses'; device poses =
official_sfm_fed_frames.jsonl, ARKit camera axes -> COLMAP axes). The per-frame
tracker state is read from the product's own official_photo_bundle.json
(frames[].trackingState / poseSource, joined on the JPEG basename), which is
exactly what the Dart rule in the patch reads (still.trackingStateName).

Every file is stat'ed for the 'dataless' flag right before it is opened;
dataless (iCloud placeholder) files are never opened.
Arms:
  all      : all registered fed frames (reproduces step2 phone_gate: 6/90 trips)
  trusted  : frames with trackingState == 'normal' only (fix A)
Also reports the scale difference per arm, and for captures that contain an
untrusted frame, a good-subset Umeyama reference (as step2/taskB/good_subset_scale.py).
"""
import collections
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SP = os.path.dirname(os.path.dirname(HERE))
S1 = SP + '/step1'
TOOL = HERE + '/build/device_align_offline'
OUT = HERE + '/results'
os.makedirs(OUT, exist_ok=True)


def is_dataless(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    return r.returncode != 0 or 'dataless' in r.stdout


def to_colmap(q, t):  # verbatim from phone_gate_offline.py (mandatory_arkit_gravity_v1.cc:68-72)
    w, x, y, z = q
    n = (w * w + x * x + y * y + z * z) ** 0.5
    w, x, y, z = w / n, x / n, y / n, z / n
    return [-x, w, -z, y], [t[0], -t[1], -t[2]]


def run(pairs_path, sigma):
    r = subprocess.run([TOOL, pairs_path, str(sigma), 'all'], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def q2R(w, x, y, z):
    n = (w * w + x * x + y * y + z * z) ** 0.5
    w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def umeyama(src, dst):  # src,dst: 3xN; returns s,R,t with dst ~ s R src + t
    mu_s, mu_d = src.mean(1, keepdims=True), dst.mean(1, keepdims=True)
    xs, xd = src - mu_s, dst - mu_d
    C = xd @ xs.T / src.shape[1]
    U, D, Vt = np.linalg.svd(C)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    var = (xs ** 2).sum() / src.shape[1]
    s = np.trace(np.diag(D) @ S) / var
    t = mu_d - s * R @ mu_s
    return s, R, t.ravel()


def centre(q, t):
    return -q2R(*q).T @ np.array(t)


R = json.load(open(S1 + '/results.json'))['results']
rows, skipped = [], []
for cid, vs in sorted(R.items()):
    d = vs[0]['dir']
    meta_p, fed_p, bun_p = (d + '/official_sfm_sparse_meta.json', d + '/official_sfm_fed_frames.jsonl',
                            d + '/official_photo_bundle.json')
    if is_dataless(meta_p) or is_dataless(fed_p):
        skipped.append((cid, 'dataless'))
        continue
    state_by_name = {}
    bundle_state = 'present'
    if not os.path.exists(bun_p):
        bundle_state = 'missing'
    elif is_dataless(bun_p):
        bundle_state = 'dataless'
    else:
        for f in json.load(open(bun_p)).get('frames', []):
            state_by_name[f.get('highresFilename')] = (f.get('trackingState'), f.get('poseSource'))
    meta = json.load(open(meta_p))
    fed, name_of = {}, {}
    for ln in open(fed_p):
        try:
            j = json.loads(ln)
        except Exception:
            continue
        if 'arkitCamFromWorldQwxyz' in j and 'arkitCamFromWorldTxyz' in j:
            fed[j['frameId']] = to_colmap(j['arkitCamFromWorldQwxyz'], j['arkitCamFromWorldTxyz'])
        elif 'arkitCameraCenterWorld' in j:
            C = j['arkitCameraCenterWorld']
            fed[j['frameId']] = ([1, 0, 0, 0], [-C[0], -C[1], -C[2]], 'centre_only')
        name_of[j['frameId']] = os.path.basename(j.get('jpegPath', ''))
    def sidecar_state(name):
        sc = d + '/photos_highres/' + name[:-4] + '.json' if name.endswith('.jpg') else None
        if not sc or not os.path.exists(sc) or is_dataless(sc):
            return None
        try:
            j = json.load(open(sc))
        except Exception:
            return None
        t = j.get('trackingStateName') or j.get('tracking_state')
        return (t, 'sidecar') if t else None
    lines_all, lines_tr, lines_fc, states, excluded, excluded_fc = [], [], [], {}, [], []
    for p in meta.get('poses', []):
        if not p.get('registered', True) or p['frame_id'] not in fed:
            continue
        q = p['quat_wxyz']
        if sum(v * v for v in q) < 1e-12:
            continue
        dq, dt = fed[p['frame_id']][:2]
        ln = '%d %s %s %s %s' % (p['frame_id'], ' '.join('%.17g' % v for v in q), ' '.join('%.17g' % v for v in p['t']),
                                 ' '.join('%.17g' % v for v in dq), ' '.join('%.17g' % v for v in dt))
        lines_all.append(ln)
        nm = name_of.get(p['frame_id']) or ''
        st = state_by_name.get(nm) or sidecar_state(nm)
        states[p['frame_id']] = st
        # 'trusted' arm (task definition): drop frames whose RECORDED tracker state is
        # not 'normal' (bundle first, then the native sidecar JSON). Frames with no
        # recorded state anywhere (JPEG + sidecar pruned) are kept here and counted.
        # 'failclosed' arm (the Dart rule, which never lacks a state at feed time):
        # additionally drops the no-record frames.
        if st is not None and st[0] != 'normal':
            excluded.append(p['frame_id']); excluded_fc.append(p['frame_id'])
        else:
            lines_tr.append(ln)
            if st is None:
                excluded_fc.append(p['frame_id'])
            else:
                lines_fc.append(ln)
    pa, pt, pf = (f'{OUT}/{cid}.all.pairs.txt', f'{OUT}/{cid}.trusted.pairs.txt', f'{OUT}/{cid}.failclosed.pairs.txt')
    open(pa, 'w').write('\n'.join(lines_all) + '\n')
    open(pt, 'w').write('\n'.join(lines_tr) + '\n')
    open(pf, 'w').write('\n'.join(lines_fc) + '\n')
    res = {'all': {s: run(pa, s) for s in (0.040, 1.0)}}
    res['trusted'] = {s: run(pt, s) for s in (0.040, 1.0)} if excluded else res['all']
    res['failclosed'] = ({s: run(pf, s) for s in (0.040, 1.0)} if len(lines_fc) >= 3 else None) if excluded_fc else res['all']
    missing_state = sum(1 for v in states.values() if v is None)
    rows.append(dict(cap=cid, dir=d, bundle=bundle_state, n_pairs=len(lines_all), n_excluded=len(excluded),
                     excluded=excluded, n_excluded_fc=len(excluded_fc), missing_state=missing_state,
                     sidecar_states=sum(1 for v in states.values() if v and v[1] == 'sidecar'), res=res))

json.dump(dict(rows=rows, skipped=skipped), open(OUT + '/phone_gate_state.json', 'w'), indent=1)

print('captures', len(rows), 'skipped', skipped)
print('bundle:', dict(collections.Counter(r['bundle'] for r in rows)))
for sig in (0.040, 1.0):
    for arm in ('all', 'trusted', 'failclosed'):
        print('sigma=%.3f arm=%-10s status:' % (sig, arm), dict(collections.Counter(
            (r['res'][arm][sig]['status'] if r['res'][arm] else 'too_few_pairs') for r in rows)))
print('captures with excluded frames:', sum(1 for r in rows if r['n_excluded']),
      '; excluded frames total:', sum(r['n_excluded'] for r in rows), 'of', sum(r['n_pairs'] for r in rows))
print('frames with no recorded state anywhere:', sum(r['missing_state'] for r in rows),
      'in', sum(1 for r in rows if r['missing_state']), 'captures; states taken from native sidecar:', sum(r['sidecar_states'] for r in rows))
print('failclosed arm: captures with excluded frames', sum(1 for r in rows if r['n_excluded_fc']), 'frames', sum(r['n_excluded_fc'] for r in rows))
print('\nper-capture changes (sigma=0.040):')
for r in rows:
    a, b = r['res']['all'][0.040], r['res']['trusted'][0.040]
    if r['n_excluded'] or a['status'] != 'aligned' or r['n_excluded_fc']:
        c = r['res']['failclosed']
        print('   failclosed excl=%d -> %s' % (r['n_excluded_fc'], (c[0.040]['status'] + ' max_err_mm %.1f scale %.5f' % (1e3 * c[0.040]['centre_err_m']['max'], c[0.040]['scale'])) if c else 'too_few_pairs'))
        print(' %s excl=%d %s -> %s | inliers %d/%d -> %d/%d | max_err_mm %.1f -> %.1f | scale %.5f -> %.5f (%+.2f%%)' % (
            r['cap'], r['n_excluded'], a['status'], b['status'], a['inliers_all'], a['n_pairs'], b['inliers_all'], b['n_pairs'],
            1e3 * a['centre_err_m']['max'], 1e3 * b['centre_err_m']['max'], a['scale'], b['scale'],
            100 * (b['scale'] / a['scale'] - 1)))

# Good-subset reference (same method as step2/taskB/good_subset_scale.py) for the captures
# that contain untrusted frames.  good = trusted frames after the last untrusted frame
# (i.e. the verified post-reinit segment); scale bias = robust-fit scale / good-only Umeyama scale - 1.
print('\ngood-subset reference (Umeyama on trusted frames after the last untrusted frame):')
for r in rows:
    if not r['n_excluded']:
        continue
    pa = f"{OUT}/{r['cap']}.all.pairs.txt"
    P = {int(l.split()[0]): [float(v) for v in l.split()[1:]] for l in open(pa) if l.strip()}
    last_bad = max(r['excluded'])
    good = sorted(k for k in P if k > last_bad)
    if len(good) < 3:
        print(' ', r['cap'], 'good subset too small', len(good))
        continue
    Cr = np.array([centre(P[k][0:4], P[k][4:7]) for k in good]).T
    Cd = np.array([centre(P[k][7:11], P[k][11:14]) for k in good]).T
    s_good = umeyama(Cr, Cd)[0]
    before = sorted(k for k in P if k < min(r['excluded']))
    out = dict(cap=r['cap'], good_ids='%d-%d' % (good[0], good[-1]), n_good=len(good), good_scale=s_good)
    for arm in ('all', 'trusted'):
        out[arm + '_bias_pct'] = 100 * (r['res'][arm][0.040]['scale'] / s_good - 1)
    # sensitivity: also drop the trusted frames that precede the untrusted window
    if before:
        lines = [l for l in open(pa) if l.strip() and int(l.split()[0]) not in set(r['excluded']) | set(before)]
        pp = f"{OUT}/{r['cap']}.trusted_postwindow.pairs.txt"
        open(pp, 'w').write(''.join(lines))
        rr = run(pp, 0.040)
        out['pre_window_ids'] = before
        out['trusted_postwindow_status'] = rr['status']
        out['trusted_postwindow_bias_pct'] = 100 * (rr['scale'] / s_good - 1)
    print(' ', json.dumps(out))
