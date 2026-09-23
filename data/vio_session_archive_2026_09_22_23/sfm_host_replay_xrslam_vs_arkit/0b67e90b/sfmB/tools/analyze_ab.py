#!/usr/bin/python3
# analyze_ab.py <runs_dir> <subset> <armA> <armX> [<armX2> ...]
# Reads runs/<subset>_<arm>/{per_frame.jsonl,delivered_poses.txt,cloud.ply,run.log}
# and the matching inputs/feed_<subset>_<arm>.jsonl; writes ab_<subset>.json +
# PNG renders. Metrics are chosen so that a bad arm CAN fail:
#   * registered/fed, finalize status, gate log lines (grep of the core's own tags)
#   * delivered-vs-clean-COLMAP shape error (Sim3, % of path) — independent reference
#   * delivered-vs-own-prior Sim3 (how far BA moved the device poses)
#   * delivered X vs delivered A Sim3 scale, and the same ratio on the INPUT poses
#   * cloud-to-cloud NN distances after mapping X into A's frame with that Sim3
import json, os, sys, re
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P

RUNS, SUB = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else (None, None)
ARMS = sys.argv[3:]
INP = P.OUT


def load_run(arm):
    d = f'{RUNS}/{SUB}_{arm}'
    r = {'dir': d}
    feed = [json.loads(l) for l in open(f'{INP}/feed_{SUB}_{arm}.jsonl')]
    r['feed'] = {f['frameIndex']: f for f in feed}
    pf = [json.loads(l) for l in open(f'{d}/per_frame.jsonl')]
    r['per_frame'] = pf
    fid2fi = {p['fid']: p['frameIndex'] for p in pf if p['rc'] == 'AETHER_SFM_OK' or p['fid'] >= 0}
    log = open(f'{d}/run.log', errors='replace').read()
    r['log'] = log
    m = re.search(r'^RESULT (.*)$', log, re.M)
    r['result_line'] = m.group(1) if m else None
    m = re.search(r'^STREAMED (.*)$', log, re.M)
    r['streamed_line'] = m.group(1) if m else None
    tags = {}
    for tag in ['ARKIT-POSE-REJECT', '[AETHER gravity] injected', '[AETHER gravity] MISSING',
                '[AETHER gravity] INCONSISTENT', 'mandatory-ARKit refine blocked',
                'mandatory ARKit recovery blocked', '[gravity-ra]']:
        lines = [l for l in log.splitlines() if tag in l]
        tags[tag] = {'count': len(lines), 'last': lines[-1][-200:] if lines else None}
    r['gate_tags'] = tags
    inj = re.findall(r'\[AETHER gravity\] injected (\d+)/(\d+)', log)
    r['gravity_injected_totals'] = [int(sum(int(a) for a, b in inj)), int(sum(int(b) for a, b in inj))] if inj else None
    poses = {}
    if os.path.exists(f'{d}/delivered_poses.txt'):
        for ln in open(f'{d}/delivered_poses.txt'):
            f = ln.split()
            fid, reg = int(f[0]), int(f[2])
            if not reg: continue
            q = [float(v) for v in f[3:7]]; t = np.array([float(v) for v in f[7:10]])
            R = P.q2R(*q)
            fi = fid2fi.get(fid)
            if fi is None: continue
            poses[fi] = (R, -R.T @ t)
    r['poses'] = poses
    if os.path.exists(f'{d}/cloud.ply'):
        b = open(f'{d}/cloud.ply', 'rb').read()
        h = b.index(b'end_header\n') + len(b'end_header\n')
        n = int(re.search(rb'element vertex (\d+)', b[:h]).group(1))
        dt = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')])
        a = np.frombuffer(b[h:h + n * 15], dtype=dt)
        r['xyz'] = np.stack([a['x'], a['y'], a['z']], 1).astype(np.float64)
        r['rgb'] = np.stack([a['r'], a['g'], a['b']], 1)
    return r


def prior_centers(run, frames):
    out = []
    for fi in frames:
        f = run['feed'][fi]
        R = P.q2R(*f['arkitCamFromWorldQwxyz']); t = np.array(f['arkitCamFromWorldTxyz'])
        out.append(-R.T @ t)
    return np.array(out).T


def sim3(X, Y):
    s, R, t = P.umeyama(X, Y)
    e = np.linalg.norm(s * R @ X + t - Y, axis=0)
    return s, R, t, e


def colmap_ref_centers(frames):
    lines = [l for l in open(P.COLMAP_REF) if not l.startswith('#')]
    C = {}
    for k in range(0, len(lines), 2):
        f = lines[k].split(); i = int(f[9][1:6])
        R = P.q2R(*[float(v) for v in f[1:5]]); t = np.array([float(v) for v in f[5:8]])
        C[i] = (R, -R.T @ t)
    return C


def main():
    runs = {a: load_run(a) for a in ARMS}
    ref = colmap_ref_centers(None)
    out = {'subset': SUB}
    for a, r in runs.items():
        fr = sorted(r['poses'])
        o = {'result': r['result_line'], 'streamed': r['streamed_line'],
             'gate_tags': r['gate_tags'], 'gravity_anchor_injected_sum': r['gravity_injected_totals'],
             'n_fed_rows': len(r['per_frame']),
             'n_rejected_rows': sum(1 for p in r['per_frame'] if p['rc'] != 'AETHER_SFM_OK'),
             'n_registered': len(fr),
             'extract_ms_median': float(np.median([p['extract_ms'] for p in r['per_frame']])),
             'match_ms_median': float(np.median([p['match_ms'] for p in r['per_frame']]))}
        if len(fr) >= 3:
            D = np.array([r['poses'][i][1] for i in fr]).T
            s, R, t, e = sim3(D, prior_centers(r, fr))
            o['delivered_vs_own_prior'] = {'scale_delivered_to_prior': float(s), 'rmse_prior_units': float(np.sqrt((e**2).mean())),
                                           'max_prior_units': float(e.max())}
            Cref = np.array([ref[i][1] for i in fr]).T
            s2, R2, t2, e2 = sim3(D, Cref)
            path = float(np.sum(np.linalg.norm(np.diff(Cref, axis=1), axis=0)))
            o['delivered_vs_clean_colmap'] = {'rmse_pct_of_path': float(100 * np.sqrt((e2**2).mean()) / path),
                                              'max_pct_of_path': float(100 * e2.max() / path)}
            # rotation agreement with the clean reference after the Sim3 frame change
            rot = []
            for i in fr:
                Rd = r['poses'][i][0]   # CamFromWorld (delivered world)
                Rr = ref[i][0]          # CamFromWorld (colmap world)
                # world_ref = s2 R2 world_del + t2  => R_cw_del_in_ref = Rd @ R2.T
                rot.append(P.ang(Rd @ R2.T, Rr))
            o['delivered_vs_clean_colmap']['rot_err_deg_median'] = float(np.median(rot))
            o['delivered_vs_clean_colmap']['rot_err_deg_max'] = float(np.max(rot))
        if 'xyz' in r:
            o['cloud_points'] = int(len(r['xyz']))
        out[a] = o

    A = runs[ARMS[0]]
    renders = {}
    for x in ARMS[1:]:
        X = runs[x]
        com = sorted(set(A['poses']) & set(X['poses']))
        if len(com) < 3: continue
        DA = np.array([A['poses'][i][1] for i in com]).T
        DX = np.array([X['poses'][i][1] for i in com]).T
        s, R, t, e = sim3(DX, DA)
        PA = prior_centers(A, com); PX = prior_centers(X, com)
        s_in, _, _, e_in = sim3(PX, PA)
        cmp = {'n_common_registered': len(com),
               'delivered_sim3_scale_X_to_A': float(s),
               'delivered_implied_scale_X_over_A': float(1 / s),
               'input_prior_sim3_scale_X_to_A': float(s_in),
               'input_implied_scale_X_over_A': float(1 / s_in),
               'delivered_center_rmse_after_sim3_A_units': float(np.sqrt((e**2).mean())),
               'input_center_rmse_after_sim3_A_units': float(np.sqrt((e_in**2).mean()))}
        if 'xyz' in X and 'xyz' in A:
            Xm = (s * R @ X['xyz'].T + t).T
            ta, tx = cKDTree(A['xyz']), cKDTree(Xm)
            dxa, _ = ta.query(Xm); dax, _ = tx.query(A['xyz'])
            nnA, _ = ta.query(A['xyz'], k=2)
            cmp['cloud_X_to_A_nn_m'] = {'median': float(np.median(dxa)), 'p90': float(np.percentile(dxa, 90)),
                                        'frac_gt_2cm': float(np.mean(dxa > 0.02)), 'frac_gt_5cm': float(np.mean(dxa > 0.05))}
            cmp['cloud_A_to_X_nn_m'] = {'median': float(np.median(dax)), 'p90': float(np.percentile(dax, 90)),
                                        'frac_gt_2cm': float(np.mean(dax > 0.02)), 'frac_gt_5cm': float(np.mean(dax > 0.05))}
            cmp['cloud_A_self_nn_m_median'] = float(np.median(nnA[:, 1]))
            renders[x] = Xm
        out[f'{x}_vs_{ARMS[0]}'] = cmp
    json.dump(out, open(f'{RUNS}/ab_{SUB}.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))

    # renders: A and each X (mapped into A's frame), top (x-z) and side (x-y)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    if 'xyz' not in A: return
    clouds = [(ARMS[0], A['xyz'])] + [(x, renders[x]) for x in renders]
    allp = np.concatenate([c for _, c in clouds])
    lo = np.percentile(allp, 1, axis=0); hi = np.percentile(allp, 99, axis=0)
    pad = 0.1 * (hi - lo); lo -= pad; hi += pad
    fig, ax = plt.subplots(2, len(clouds), figsize=(7 * len(clouds), 12), squeeze=False)
    for j, (nm, c) in enumerate(clouds):
        keep = np.all((c >= lo) & (c <= hi), axis=1)
        cc = c[keep]
        for i, (u, v, lab) in enumerate([(0, 2, 'top view (x-z, ARKit y-up world)'), (0, 1, 'side view (x-y)')]):
            ax[i, j].scatter(cc[:, u], cc[:, v], s=0.2, c='k', alpha=0.35, linewidths=0)
            ax[i, j].set_xlim(lo[u], hi[u]); ax[i, j].set_ylim(lo[v], hi[v])
            ax[i, j].set_aspect('equal'); ax[i, j].set_title(f'{nm} — {lab}  n={len(c)}')
    fig.tight_layout()
    fig.savefig(f'{RUNS}/render_{SUB}.png', dpi=110)
    print('wrote', f'{RUNS}/render_{SUB}.png')


if __name__ == '__main__':
    main()
