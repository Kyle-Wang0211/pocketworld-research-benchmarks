#!/usr/bin/python3
"""Step-3 checks on the DEVICE-ALIGN-V1 host runs (step2/runs) against B's pre-fix runs.

Conventions: delivered_poses.txt = fid frameIndex reg qw qx qy qz tx ty tz (CamFromWorld, COLMAP axes);
feed = ARKit-axes CamFromWorld (centre = -R^T t is axis-independent). All Sim3 = Umeyama (prep_inputs.umeyama)
EXCEPT the held-out fit, which is the core's own code (build/device_align_offline).
"""
import json, os, re, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools')
import prep_inputs as P  # noqa: E402

RUNS, BRUNS = W + '/runs', W + '/base_sfmB/runs'
TOOL = W + '/build/device_align_offline'
OUT = W + '/results'; os.makedirs(OUT, exist_ok=True)


def feed(name):
    p = f'{W}/inputs/feed_{name}.jsonl'
    if not os.path.exists(p): p = f'{W}/base_sfmB/inputs/feed_{name}.jsonl'
    return [json.loads(l) for l in open(p)]


def dev_pose_colmap(f):  # core conversion mandatory_arkit_gravity_v1.cc:68-72
    w, x, y, z = f['arkitCamFromWorldQwxyz']; n = (w*w+x*x+y*y+z*z) ** .5; w, x, y, z = w/n, x/n, y/n, z/n
    t = f['arkitCamFromWorldTxyz']
    return [-x, w, -z, y], [t[0], -t[1], -t[2]]


def centre(q, t): R = P.q2R(*q); return -R.T @ np.asarray(t, float)


def delivered(d):
    out = {}
    for ln in open(d + '/delivered_poses.txt'):
        f = ln.split()
        if int(f[2]) != 1: continue
        out[int(f[0])] = ([float(v) for v in f[3:7]], [float(v) for v in f[7:10]])
    return out


def jsonl_align(d):
    for ln in open(d + '/sfm_match_fail.jsonl', errors='replace'):
        if '"device_alignment_v1"' in ln: return json.loads(ln)
    return None


def read_ply(p):
    b = open(p, 'rb').read(); h = b.index(b'end_header\n') + 11
    n = int(re.search(rb'element vertex (\d+)', b[:h]).group(1))
    a = np.frombuffer(b[h:h + n * 15], dtype=np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')]))
    return np.stack([a['x'], a['y'], a['z']], 1).astype(np.float64)


def sim3_scale(src, dst):  # scale of dst ~ s R src + t  (arrays n x 3)
    s, R, t = P.umeyama(np.asarray(src).T, np.asarray(dst).T); return float(s), R, t


def pairs_file(dl, fd, path):
    lines = []
    for k in sorted(dl):
        dq, dt = dev_pose_colmap(fd[k])
        q, t = dl[k]
        lines.append('%d %s %s %s %s' % (k, ' '.join('%.17g' % v for v in q), ' '.join('%.17g' % v for v in t),
                                         ' '.join('%.17g' % v for v in dq), ' '.join('%.17g' % v for v in dt)))
    open(path, 'w').write('\n'.join(lines) + '\n')


def offline(path, fit, sigma=0.040):
    r = subprocess.run([TOOL, path, str(sigma), fit], capture_output=True, text=True, check=True)
    return json.loads(r.stdout.strip().splitlines()[-1])


def summary_run(run, feedname):
    d = RUNS + '/' + run; fd = feed(feedname); dl = delivered(d)
    ks = sorted(dl)
    C = np.array([centre(*dl[k]) for k in ks]); D = np.array([centre(*dev_pose_colmap(fd[k])) for k in ks])
    s, _, _ = sim3_scale(D, C)  # delivered units per device metre
    ja = jsonl_align(d)
    log = open(d + '/run.log', errors='replace').read()
    m = re.search(r'^RESULT (.*)$', log, re.M)
    return dict(run=run, feed=feedname, n_reg=len(ks), deliv_units_per_device_m=s,
                align=ja, result=m.group(1) if m else None)


def held_out(run_dir, feedname, tag):
    """B's PRE-fix delivered model; core code fits on even (odd) frames, evaluate on the other half."""
    fd = feed(feedname); dl = delivered(run_dir); ks = sorted(dl)
    pf = f'{OUT}/heldout_{tag}.pairs.txt'; pairs_file(dl, fd, pf)
    C = np.array([centre(*dl[k]) for k in ks]); D = np.array([centre(*dev_pose_colmap(fd[k])) for k in ks])
    out = {'tag': tag, 'n': len(ks)}
    for fit, ev in (('even', 1), ('odd', 0)):
        r = offline(pf, fit)
        idx = np.array([i for i in range(len(ks)) if i % 2 == ev])
        s_before, _, _ = sim3_scale(D[idx], C[idx])        # units/device-m on held-out, no fix
        R = P.q2R(*r['q']); Ca = (r['scale'] * (R @ C.T)).T + np.array(r['t'])
        s_after, _, _ = sim3_scale(D[idx], Ca[idx])         # after the even-fit correction
        e = np.linalg.norm(Ca[idx] - D[idx], axis=1)          # residual w/o refit (device m)
        # residual of the uncorrected model on held-out after its own best Sim3 (= shape-only floor)
        sb, Rb, tb = sim3_scale(C[idx], D[idx]); eb = np.linalg.norm((sb * (Rb @ C[idx].T)).T + tb.ravel() - D[idx], axis=1)
        out['fit_' + fit] = dict(status=r['status'], n_fit=r['n_fit'], heldout_n=len(idx),
                                 heldout_scale_err_before_pct=100 * (s_before - 1), heldout_scale_err_after_pct=100 * (s_after - 1),
                                 heldout_resid_mm_median=1e3 * float(np.median(e)), heldout_resid_mm_max=1e3 * float(e.max()),
                                 heldout_resid_refit_floor_mm_median=1e3 * float(np.median(eb)))
    return out


def geometry_within(run, feedname):
    """Invert the applied Sim3 (from the jsonl record) -> pre-alignment model of the SAME run; compare
    shape metrics post vs pre (must be identical to fp precision) and pre vs B's run of the same feed."""
    d = RUNS + '/' + run; ja = jsonl_align(d)
    T_s, T_q, T_t = ja['scale'], [ja['qw'], ja['qx'], ja['qy'], ja['qz']], np.array([ja['tx'], ja['ty'], ja['tz']])
    R = P.q2R(*T_q)
    X = read_ply(d + '/cloud.ply')
    Xpre = (R.T @ ((X - T_t).T)).T / T_s
    dl = delivered(d); ks = sorted(dl)
    C = np.array([centre(*dl[k]) for k in ks]); Cpre = (R.T @ ((C - T_t).T)).T / T_s
    # shape metric: similarity-invariant self-consistency (NN of cloud to its own cameras' Sim3 fit is trivial),
    # so use pairwise-distance ratios: post/pre must equal T_s for every pair
    ii = np.random.default_rng(0).integers(0, len(X), size=(min(20000, len(X) * 4), 2))
    dpost = np.linalg.norm(X[ii[:, 0]] - X[ii[:, 1]], axis=1); dpre = np.linalg.norm(Xpre[ii[:, 0]] - Xpre[ii[:, 1]], axis=1)
    ok = dpre > 1e-6
    rel = dpost[ok] / dpre[ok] / T_s - 1
    return dict(run=run, n_points=len(X), applied_scale=T_s, pairwise_ratio_dev_max=float(np.abs(rel).max()),
                Cpre=Cpre, Xpre=Xpre, ks=ks)


if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    res = {}
    if what in ('all', 'summary'):
        res['summary'] = []
        for run, fn in [('fix_S_prod74_A', 'S_prod74_A'), ('fix_S_prod74_A_r2', 'S_prod74_A'), ('fix_S_prod74_Xhost', 'S_prod74_Xhost'),
                        ('fix_S_prod_A', 'S_prod_A'), ('fix_S_prod_Xhost', 'S_prod_Xhost'), ('off_S_prod74_A', 'S_prod74_A'),
                        ('fix_S_prod_Xdev', 'S_prod_Xdev'), ('fix_S_prod74_A_shuf', 'S_prod74_A_shuf'), ('fix_S_prod74_Xhost_shuf', 'S_prod74_Xhost_shuf'),
                        ('fix_S_prod74_A_x110', 'S_prod74_A_x110'), ('fix_S_prod74_Xhost_x110', 'S_prod74_Xhost_x110'),
                        ('fix_S_deb74_A', 'S_deb74_A'), ('fix_S_deb74_A_r2', 'S_deb74_A'), ('fix_S_deb74_Xhost', 'S_deb74_Xhost'),
                        ('fix_S_deb_A', 'S_deb_A'), ('fix_S_deb_A_r2', 'S_deb_A'), ('fix_S_deb_Xhost', 'S_deb_Xhost'),
                        ('fix_S_deb74_A_x110', 'S_deb74_A_x110')]:
            if not os.path.exists(f'{RUNS}/{run}/delivered_poses.txt'):
                print('missing', run); continue
            r = summary_run(run, fn); res['summary'].append(r)
            a = r['align'] or {}
            print('%-24s reg=%3d deliv_units/device_m=%.6f | %s inl=%s/%s scale=%.6f cerr_med=%.1fmm max=%.1fmm rot_med=%.2fdeg | %s' % (
                run, r['n_reg'], r['deliv_units_per_device_m'], a.get('status'), a.get('inliers_all'), a.get('n_pairs'), a.get('scale', 0),
                1e3 * a.get('centre_err_m', {}).get('median', 0), 1e3 * a.get('centre_err_m', {}).get('max', 0),
                a.get('rot_err_deg', {}).get('median', 0), (r['result'] or '')[:60]))
    if what in ('all', 'heldout'):
        res['heldout'] = []
        for rd, fn, tag in [(BRUNS + '/diag_S_prod74_A', 'S_prod74_A', 'B_S_prod74_A'), (BRUNS + '/diag_S_prod74_Xhost', 'S_prod74_Xhost', 'B_S_prod74_Xhost'),
                            (BRUNS + '/diag_S_prod_A', 'S_prod_A', 'B_S_prod_A'), (BRUNS + '/diag_S_prod_Xhost', 'S_prod_Xhost', 'B_S_prod_Xhost'),
                            (BRUNS + '/diag_S_deb74_A', 'S_deb74_A', 'B_S_deb74_A'), (BRUNS + '/diag_S_deb74_Xhost', 'S_deb74_Xhost', 'B_S_deb74_Xhost'),
                            (BRUNS + '/diag_S_deb_A', 'S_deb_A', 'B_S_deb_A'), (BRUNS + '/diag_S_deb_Xhost', 'S_deb_Xhost', 'B_S_deb_Xhost'),
                            (BRUNS + '/S_deb_A', 'S_deb_A', 'B_S_deb_A_rep')]:
            h = held_out(rd, fn, tag); res['heldout'].append(h)
            for k in ('fit_even', 'fit_odd'):
                x = h[k]
                print('%-18s %s n_fit=%3d heldout=%3d scale_err before %+7.2f%% -> after %+6.2f%% | heldout resid med %.1f max %.1f mm (refit floor %.1f) %s' % (
                    tag, k, x['n_fit'], x['heldout_n'], x['heldout_scale_err_before_pct'], x['heldout_scale_err_after_pct'],
                    x['heldout_resid_mm_median'], x['heldout_resid_mm_max'], x['heldout_resid_refit_floor_mm_median'], x['status']))
    json.dump(res, open(f'{OUT}/analyze_fix_{what}.json', 'w'), indent=1, default=float)


def centres_of(d):
    dl = delivered(d); return {k: centre(*v) for k, v in dl.items()}


def ratio(d_num, d_den):
    """scale of model d_num relative to d_den: Umeyama d_den -> d_num on common registered frames."""
    A, B = centres_of(d_num), centres_of(d_den); ks = sorted(set(A) & set(B))
    s, _, _ = sim3_scale(np.array([B[k] for k in ks]), np.array([A[k] for k in ks]))
    return s, len(ks)


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'pairs':
    out = {}
    for tag, num, den in [
            ('pos_x110 prod74 A  (fix)', RUNS + '/fix_S_prod74_A_x110', RUNS + '/fix_S_prod74_A'),
            ('pos_x110 prod74 X  (fix)', RUNS + '/fix_S_prod74_Xhost_x110', RUNS + '/fix_S_prod74_Xhost'),
            ('pos_x110 deb74 A   (fix)', RUNS + '/fix_S_deb74_A_x110', RUNS + '/fix_S_deb74_A'),
            ('pos_x110 prod74 A  (pre, same runs inverted)', RUNS + '/pre_fix_S_prod74_A_x110', RUNS + '/pre_fix_S_prod74_A'),
            ('pos_x110 deb74 A   (pre, same runs inverted)', RUNS + '/pre_fix_S_deb74_A_x110', RUNS + '/pre_fix_S_deb74_A'),
            ('rerun deb A   B before (rep/orig)', BRUNS + '/S_deb_A', BRUNS + '/diag_S_deb_A'),
            ('rerun deb A   fix r2/r1', RUNS + '/fix_S_deb_A_r2', RUNS + '/fix_S_deb_A'),
            ('rerun deb A   pre r2/r1 (core itself)', RUNS + '/pre_fix_S_deb_A_r2', RUNS + '/pre_fix_S_deb_A'),
            ('rerun deb74 A fix r2/r1', RUNS + '/fix_S_deb74_A_r2', RUNS + '/fix_S_deb74_A'),
            ('rerun deb74 A pre r2/r1 (core itself)', RUNS + '/pre_fix_S_deb74_A_r2', RUNS + '/pre_fix_S_deb74_A'),
            ('rerun prod74 A fix r2/r1', RUNS + '/fix_S_prod74_A_r2', RUNS + '/fix_S_prod74_A'),
            ('rerun deb X   B before (rep/orig)', BRUNS + '/S_deb_Xhost', BRUNS + '/diag_S_deb_Xhost')]:
        if not (os.path.exists(num + '/delivered_poses.txt') and os.path.exists(den + '/delivered_poses.txt')):
            print('missing', tag); continue
        s, n = ratio(num, den); out[tag] = dict(scale=s, n=n)
        print('%-46s scale=%.6f (%+.3f%%) n=%d' % (tag, s, 100 * (s - 1), n))
    json.dump(out, open(f'{OUT}/analyze_fix_pairs.json', 'w'), indent=1)
