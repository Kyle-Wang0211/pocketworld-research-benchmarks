#!/usr/bin/python3
"""fixc_metrics.py <run_dir> <mac|phone> <feed_file> [cap_id] [--untrusted=a-b,c]
Metrics that can fail, per core run (written to <run_dir>/metrics.json):
  * log: n_reg, n_points, mean reproj, stream/finalize ms, RSS, device-align gate, REG_EVIDENCE counters, frame-loss
  * device residual per registered TRUSTED frame after the core's own robust Sim3 (build/device_align_offline, σ=0.04
    covariance path = the core's header) -> misplaced = centre error > max_error (112 mm)
  * untrusted frames: Sim3 of their delivered centres onto their OWN (old-session) device centres (self-consistency),
    and the same residual through the trusted fit (expected large: different device world)
  * mac: relative pose (consecutive + skip-one registered pairs) vs the clean COLMAP 4.1.1 reference (no device poses):
    rotation diff and translation-direction diff; >20 deg dir = disagreement. Cloud -> reference NN distance in ARKit
    metres (analyze_takeover.py method), delivered-vs-reference camera rmse, delivered units per ARKit metre.
  * phone: same pairwise check against verified two-view geometry of the capture's own raw matches (twoview_check.py:
    OpenCV 5-pt E + pycolmap calibrated TVG, counted only where both agree); image estimates cached per capture."""
import json, os, re, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); sys.path.insert(0, W + '/tools')
import prep_inputs as P  # noqa
rd, kind, feedf = sys.argv[1], sys.argv[2], sys.argv[3]
cap = sys.argv[4] if len(sys.argv) > 4 and not sys.argv[4].startswith('--') else None
untrusted = set()
for a in sys.argv[3:]:
    if a.startswith('--untrusted='):
        for tok in a.split('=', 1)[1].split(','):
            if '-' in tok: lo, hi = map(int, tok.split('-')); untrusted |= set(range(lo, hi + 1))
            elif tok: untrusted.add(int(tok))
MAXERR = 0.111819339
out = {'run': os.path.basename(rd), 'kind': kind, 'cap': cap}
log = open(rd + '/run.log', errors='replace').read()
def grab(prefix):
    m = re.search(rf'^{prefix} (.*)$', log, re.M)
    return dict(kv.split('=', 1) for kv in m.group(1).split() if '=' in kv) if m else None
res = grab('RESULT'); da = grab('DEVICE_ALIGN'); rev = grab('REG_EVIDENCE')
out['result'] = res; out['device_align'] = da; out['reg_evidence'] = rev
m = re.search(r'(\d+)\s+maximum resident set size', log); out['max_rss_MB'] = int(m.group(1)) / 2**20 if m else None
out['frame_loss'] = re.findall(r'\[frame-loss\] (.*)', log)
jl = rd + '/sfm_match_fail.jsonl'
ev = []; passes = []; fvr = None
if os.path.exists(jl):
    for l in open(jl, errors='replace'):
        if '"reg_evidence_v1"' in l: ev.append(json.loads(l))
        elif '"reg_pending_pass_v1"' in l: passes.append(json.loads(l))
        elif '"finalize_via_resume_v1"' in l: fvr = json.loads(l)
out['reg_evidence_lines'] = ev; out['pending_passes'] = passes; out['finalize_via_resume'] = fvr
feed = [json.loads(l) for l in open(feedf) if l.strip()]
def to_colmap(q, t):
    w, x, y, z = q; n = (w*w+x*x+y*y+z*z) ** .5; w, x, y, z = w/n, x/n, y/n, z/n
    return [-x, w, -z, y], [t[0], -t[1], -t[2]]
def centre(q, t): R = P.q2R(*q); return -R.T @ np.asarray(t, float)
dl = {}
for l in open(rd + '/delivered_poses.txt'):
    v = l.split()
    if int(v[2]) == 1: dl[int(v[0])] = (list(map(float, v[3:7])), list(map(float, v[7:10])))
out['n_fed'] = len(feed); out['n_reg'] = len(dl)
out['unregistered_fids'] = sorted(set(range(len(feed))) - set(dl))
dev = {k: to_colmap(feed[k]['arkitCamFromWorldQwxyz'], feed[k]['arkitCamFromWorldTxyz']) for k in range(len(feed))}
tr = sorted(k for k in dl if k not in untrusted)
lines = ['%d %s %s %s %s' % (k, ' '.join('%.17g' % x for x in dl[k][0]), ' '.join('%.17g' % x for x in dl[k][1]),
                               ' '.join('%.17g' % x for x in dev[k][0]), ' '.join('%.17g' % x for x in dev[k][1])) for k in tr]
pf = rd + '/eval_pairs.txt'; open(pf, 'w').write('\n'.join(lines) + '\n')
r = json.loads(subprocess.run([W + '/build/device_align_offline', pf, '0.04'], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
err = {f: e * 1e3 for f, e in zip(r['frame_ids'], r['centre_err_all_m'])}
out['offline_align'] = {k: r[k] for k in ('status', 'n_pairs', 'inliers_all', 'scale', 'max_error_m')}
out['centre_err_mm'] = {'median': float(np.median(list(err.values()))) if err else float('nan'), 'max': float(max(err.values())) if err else float('nan'),
                        'misplaced_gt112': {f: round(e, 1) for f, e in err.items() if e > MAXERR * 1e3}}
out['per_frame_err_mm'] = {f: round(e, 1) for f, e in err.items()}
if untrusted:
    ku = sorted(k for k in dl if k in untrusted)
    out['untrusted_registered'] = ku; out['untrusted_unregistered'] = sorted(untrusted - set(dl))
    if len(ku) >= 3:
        Cd = np.array([centre(*dl[k]) for k in ku]).T; Cv = np.array([centre(*dev[k]) for k in ku]).T
        s, R, t = P.umeyama(Cd, Cv); e = np.linalg.norm(s * R @ Cd + t - Cv, axis=0)
        out['untrusted_self_sim3'] = {'n': len(ku), 'resid_mm_median': float(np.median(e) * 1e3), 'resid_mm_max': float(e.max() * 1e3)}
        # trusted-fit Sim3 (Umeyama on trusted inliers) applied to untrusted frames
        ki = [k for k in tr if err.get(k, 1e9) <= MAXERR * 1e3]
        Ct = np.array([centre(*dl[k]) for k in ki]).T; Cvt = np.array([centre(*dev[k]) for k in ki]).T
        s2, R2, t2 = P.umeyama(Ct, Cvt); e2 = np.linalg.norm(s2 * R2 @ Cd + t2 - Cv, axis=0)
        out['untrusted_via_trusted_fit_mm'] = {k: round(float(x * 1e3), 1) for k, x in zip(ku, e2)}
# per-frame evidence in the delivered model (#observations, mean reprojection) — for misplaced frames and overall
try:
    import pycolmap
    if os.path.exists(rd + '/images.bin'):
        R_ = pycolmap.Reconstruction(rd)
        pf_obs = {}
        for iid, im in R_.images.items():
            if not im.has_pose: continue
            f = int(''.join(c for c in im.name if c.isdigit()))
            errs = []
            for p2 in im.points2D:
                if p2.has_point3D():
                    pr = im.project_point(R_.points3D[p2.point3D_id].xyz)
                    if pr is not None: errs.append(float(np.linalg.norm(pr - p2.xy)))
            pf_obs[f] = (len(errs), float(np.mean(errs)) if errs else float('nan'))
        out['frame_obs_min'] = min(v[0] for v in pf_obs.values()) if pf_obs else None
        out['frames_le30_obs'] = {f: v[0] for f, v in pf_obs.items() if v[0] <= 30}
        out['misplaced_obs'] = {f: pf_obs.get(int(f)) for f in out['centre_err_mm']['misplaced_gt112']}
except Exception as ex:
    out['frame_obs_error'] = str(ex)
# live-model stages (host dump): where does a misplacement first appear?
import colmap_bin as CB  # noqa
out['live_stages'] = {}
for stage in ('live_end_pre_resume', 'live_end'):
    ib = rd + f'/live/{stage}/images.bin'
    if not os.path.exists(ib): continue
    try:
        L = {}
        for iid, (q, t, nm) in CB.read_images_bin(ib).items():
            L[int(''.join(c for c in nm if c.isdigit()))] = (list(q), list(t))
        kl = sorted(k for k in L if k not in untrusted and k < len(feed))
        ln = ['%d %s %s %s %s' % (k, ' '.join('%.17g' % x for x in L[k][0]), ' '.join('%.17g' % x for x in L[k][1]),
                                   ' '.join('%.17g' % x for x in dev[k][0]), ' '.join('%.17g' % x for x in dev[k][1])) for k in kl]
        pf2 = rd + f'/eval_pairs_{stage}.txt'; open(pf2, 'w').write('\n'.join(ln) + '\n')
        r2 = json.loads(subprocess.run([W + '/build/device_align_offline', pf2, '0.04'], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
        e2 = {f: e * 1e3 for f, e in zip(r2['frame_ids'], r2['centre_err_all_m'])}
        out['live_stages'][stage] = {'n': len(kl), 'status': r2['status'], 'median_mm': float(np.median(list(e2.values()))), 'max_mm': float(max(e2.values())),
                                     'misplaced_gt112': {f: round(e, 1) for f, e in e2.items() if e > MAXERR * 1e3}}
    except Exception as ex:
        out['live_stages'][stage] = {'error': str(ex)}
def rel(Ri, ti, Rj, tj): R = Rj @ Ri.T; return R, tj - R @ ti
def dang(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float('nan') if na < 1e-12 or nb < 1e-12 else float(np.degrees(np.arccos(np.clip(a @ b / na / nb, -1, 1))))
ks = sorted(dl)
prs = [(ks[i], ks[i + 1]) for i in range(len(ks) - 1)] + [(ks[i], ks[i + 2]) for i in range(len(ks) - 2)]
if kind == 'mac':
    from scipy.spatial import cKDTree
    refC = {}
    lns = [l for l in open(W + '/base_sfmB/inputs/colmap411_ref_images_poses.txt') if l.strip()]
    for l in lns:
        f = l.split(); i = int(f[9][1:6]); R = P.q2R(*map(float, f[1:5])); t = np.array(list(map(float, f[5:8]))); refC[i] = (R, t)
    fi = [f['frameIndex'] for f in feed]
    rows = []
    for a, b in prs:
        if fi[a] not in refC or fi[b] not in refC: continue
        Ra, ta = P.q2R(*dl[a][0]), np.array(dl[a][1]); Rb, tb = P.q2R(*dl[b][0]), np.array(dl[b][1])
        Rr, trr = rel(Ra, ta, Rb, tb); Rg, tg = rel(*refC[fi[a]], *refC[fi[b]])
        rows.append((a, b, P.ang(Rr, Rg), dang(trr, tg)))
    out['relpose_vs_reference'] = {'n_pairs': len(rows), 'rot_deg_median': float(np.median([x[2] for x in rows])) if rows else None,
                                   'dir_deg_median': float(np.nanmedian([x[3] for x in rows])) if rows else None,
                                   'n_dir_gt20': int(sum(1 for x in rows if x[3] > 20)), 'n_rot_gt5': int(sum(1 for x in rows if x[2] > 5)),
                                   'bad': [[a, b, round(r_, 2), round(d_, 1)] for a, b, r_, d_ in rows if d_ > 20 or r_ > 5]}
    # cloud & cameras vs reference, in ARKit metres (analyze_takeover.py method)
    arkfull = P.load_tum(P.REC + '/arkit_poses.tum')
    ts = np.array([int(l.split(',')[0]) for l in list(open(P.REC + '/camera_index.csv'))[1:]]) * 1e-9
    AF = {}
    for rr in arkfull:
        i = int(np.argmin(np.abs(ts - rr[0])))
        if abs(ts[i] - rr[0]) < 1e-6 and not np.allclose(rr[1:4], 0): AF[i] = rr[1:4]
    refCC = {i: -R.T @ t for i, (R, t) in refC.items()}
    fr = sorted(set(AF) & set(refCC))
    s_c2a, R_c2a, t_c2a = P.umeyama(np.array([refCC[i] for i in fr]).T, np.array([AF[i] for i in fr]).T)
    to_ark = lambda X: (s_c2a * R_c2a @ X.T + t_c2a).T
    kk = [k for k in ks if fi[k] in refCC]
    Dc = np.array([centre(*dl[k]) for k in kk]).T; Rc = np.array([refCC[fi[k]] for k in kk]).T
    s_dc, R_dc, t_dc = P.umeyama(Dc, Rc); e_dc = np.linalg.norm(s_dc * R_dc @ Dc + t_dc - Rc, axis=0)
    Ak = np.array([AF.get(fi[k], [np.nan] * 3) for k in kk]).T
    ok = ~np.isnan(Ak).any(0)
    s_da, _, _ = P.umeyama(Dc[:, ok], Ak[:, ok])
    out['cameras_vs_reference'] = {'n': len(kk), 'rmse_mm': float(np.sqrt((e_dc ** 2).mean()) * s_c2a * 1e3), 'max_mm': float(e_dc.max() * s_c2a * 1e3)}
    out['delivered_units_per_arkit_m'] = float(1 / s_da)
    ply = rd + '/cloud.ply'
    if os.path.exists(ply):
        b = open(ply, 'rb').read(); h = b.index(b'end_header\n') + 11
        n = int(re.search(rb'element vertex (\d+)', b[:h]).group(1))
        a_ = np.frombuffer(b[h:h + n * 15], dtype=np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')]))
        X = np.stack([a_['x'], a_['y'], a_['z']], 1).astype(np.float64)
        Xa = to_ark((s_dc * R_dc @ X.T + t_dc).T)
        ref = to_ark(np.loadtxt(W + '/base_sfmB/inputs/colmap411_sparse_all_points_xyz.txt')[:, :3])
        d, _ = cKDTree(ref).query(Xa)
        out['cloud_to_reference'] = {'n_points': int(n), 'median_mm': float(np.median(d) * 1e3), 'p90_mm': float(np.percentile(d, 90) * 1e3),
                                     'frac_gt_2cm': float(np.mean(d > 0.02)), 'frac_gt_5cm': float(np.mean(d > 0.05))}
elif kind == 'phone' and cap:
    import twoview_check as TV
    cachef = W + f'/results/twoview_cache_{cap}.json'
    cache = json.load(open(cachef)) if os.path.exists(cachef) else {}
    os.environ['PAIRS'] = pf
    C = TV.Cap(cap)
    fid_of = lambda k: int(feed[k]['frameIndex'])  # capture frame id (JPEG/RESUME feeds keep it)
    rows = []; dirty = False
    for a, b in prs:
        fa, fb = fid_of(a), fid_of(b); key = f'{fa},{fb}'
        if key not in cache:
            im = C.image_rel(fa, fb); dirty = True
            if im is None or im.get('R_c') is None or np.linalg.norm(im['t_c']) == 0: cache[key] = None
            else:
                okk = bool(TV.ang(im['R'] @ im['R_c'].T) < 2.0 and TV.dang(im['t'], im['t_c']) < 5.0 and im['colmap_config'] == 'CALIBRATED')
                cache[key] = {'R_c': np.asarray(im['R_c']).tolist(), 't_c': np.asarray(im['t_c']).tolist(), 'ok': okk, 'inl': im['colmap_inl']}
        c = cache[key]
        if not c or not c['ok']: continue
        Ra, ta = P.q2R(*dl[a][0]), np.array(dl[a][1]); Rb, tb = P.q2R(*dl[b][0]), np.array(dl[b][1])
        Rr, trr = rel(Ra, ta, Rb, tb); Rc_, tc_ = np.array(c['R_c']), np.array(c['t_c'])
        rows.append((a, b, P.ang(Rr, Rc_), dang(trr, tc_)))
    if dirty: json.dump(cache, open(cachef, 'w'))
    out['relpose_vs_twoview'] = {'n_pairs': len(rows), 'rot_deg_median': float(np.median([x[2] for x in rows])) if rows else None,
                                 'dir_deg_median': float(np.nanmedian([x[3] for x in rows])) if rows else None,
                                 'n_dir_gt20': int(sum(1 for x in rows if x[3] > 20)), 'n_rot_gt5': int(sum(1 for x in rows if x[2] > 5)),
                                 'bad': [[a, b, round(r_, 2), round(d_, 1)] for a, b, r_, d_ in rows if d_ > 20 or r_ > 5]}
json.dump(out, open(rd + '/metrics.json', 'w'), indent=1, default=float)
rv = out.get('relpose_vs_reference') or out.get('relpose_vs_twoview') or {}
cl = out.get('cloud_to_reference') or {}
print('%-34s reg=%s/%d pts=%s reproj=%s gate=%s scale=%s misplaced>112=%s cerr med/max=%.1f/%.1f relpose>20=%s/%s rot>5=%s cloud med=%s >2cm=%s stream=%s fin=%s ev=%s' % (
    out['run'], out['n_reg'], out['n_fed'], (res or {}).get('n_points'), (res or {}).get('mean_reproj_px'), (da or {}).get('status'),
    (da or {}).get('scale', '')[:8], sorted(out['centre_err_mm']['misplaced_gt112']), out['centre_err_mm']['median'], out['centre_err_mm']['max'],
    rv.get('n_dir_gt20'), rv.get('n_pairs'), rv.get('n_rot_gt5'), '%.1f' % cl['median_mm'] if cl else '-', '%.3f' % cl['frac_gt_2cm'] if cl else '-',
    (res or {}).get('stream_ms'), (res or {}).get('finalize_ms'), rev))
