#!/usr/bin/python3
# analyze_takeover.py <subset> <label=run_dir[:feed_arm]> ...   (first label = ARKit arm)
# Takeover-session analysis (09-23). Differences vs analyze_ab.py:
#   * every length is in METRES: clouds/cameras are mapped run -> clean COLMAP 4.1.1
#     reference (Sim3 on the same frames' camera centres) -> ARKit world (one Sim3
#     fitted on the full 1644-frame run). No arm is the reference for another.
#   * scale is reported at three points: device prior, live model at end of capture
#     (live_end dump, if present), delivered model — all against ARKit metres.
#   * cloud checks against the independent COLMAP cloud (100,194 pts, all frames,
#     no device poses) + A<->X mutual NN; renders top/side + error-coloured top view.
import json, os, re, sys
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P, colmap_bin as CB

B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUB = sys.argv[1]
ARMS = []
RENDER = [x for x in os.environ.get('RENDER_ARMS', '').split(',') if x]
for a in sys.argv[2:]:
    lab, rest = a.split('=', 1)
    d, feed_arm = (rest.split(':') + [None])[:2]
    ARMS.append((lab, os.path.join(B, 'runs', d), feed_arm or lab))
REF_XYZ = os.path.join(B, 'inputs', 'colmap411_sparse_all_points_xyz.txt')  # awk of ~/Developer/colmap-6e2d4b99/sparse_all/points3D.txt: X Y Z err 2*track_len


def load_feed(arm):
    return [json.loads(l) for l in open(f'{P.OUT}/feed_{SUB}_{arm}.jsonl')]


def prior_C(f):
    R = P.q2R(*f['arkitCamFromWorldQwxyz']); return -R.T @ np.array(f['arkitCamFromWorldTxyz'])


def sim3(X, Y):
    s, R, t = P.umeyama(X, Y); e = np.linalg.norm(s * R @ X + t - Y, axis=0); return s, R, t, e


def model_centres(d):  # COLMAP bin dir -> {fid: (R_cw_colmap, C)}
    out = {}
    for iid, (q, t, nm) in CB.read_images_bin(d + '/images.bin').items():
        k = int(''.join(c for c in nm if c.isdigit())); R = P.q2R(*q); out[k] = (R, -R.T @ t)
    return out


def delivered(d):  # delivered_poses.txt -> {fid: (R, C)} registered only
    out = {}
    for ln in open(d + '/delivered_poses.txt'):
        f = ln.split()
        if int(f[2]) != 1: continue
        R = P.q2R(*map(float, f[3:7])); t = np.array(list(map(float, f[7:10])))
        out[int(f[0])] = (R, -R.T @ t)
    return out


def read_ply(p):
    b = open(p, 'rb').read(); h = b.index(b'end_header\n') + 11
    n = int(re.search(rb'element vertex (\d+)', b[:h]).group(1))
    a = np.frombuffer(b[h:h + n * 15], dtype=np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')]))
    return np.stack([a['x'], a['y'], a['z']], 1).astype(np.float64)


def nn_stats(d):
    return {'median_mm': float(np.median(d) * 1e3), 'p90_mm': float(np.percentile(d, 90) * 1e3),
            'frac_gt_1cm': float(np.mean(d > 0.01)), 'frac_gt_2cm': float(np.mean(d > 0.02)),
            'frac_gt_5cm': float(np.mean(d > 0.05))}


def main():
    featA = load_feed(ARMS[0][2])
    fid2fi = [f['frameIndex'] for f in featA]
    ark = {k: prior_C(f) for k, f in enumerate(featA)}  # ARKit centres per fid (arm-A feed)
    # clean COLMAP reference cameras (CamFromWorld, OpenCV axes) keyed by recording frameIndex
    lines = [l for l in open(P.COLMAP_REF) if not l.startswith('#')]
    refC = {}
    for k in range(0, len(lines), 2):
        f = lines[k].split(); i = int(f[9][1:6]); R = P.q2R(*map(float, f[1:5])); t = np.array(list(map(float, f[5:8])))
        refC[i] = (R, -R.T @ t)
    # COLMAP -> ARKit world, fitted once on the whole run (all frames with ARKit translation)
    arkfull = P.load_tum(P.REC + '/arkit_poses.tum')
    ts = np.array([int(l.split(',')[0]) for l in list(open(P.REC + '/camera_index.csv'))[1:]]) * 1e-9
    AF = {}
    for r in arkfull:
        i = int(np.argmin(np.abs(ts - r[0])))
        if abs(ts[i] - r[0]) < 1e-6 and not np.allclose(r[1:4], 0): AF[i] = r[1:4]
    fr = sorted(set(AF) & set(refC))
    s_c2a, R_c2a, t_c2a, e_c2a = sim3(np.array([refC[i][1] for i in fr]).T, np.array([AF[i] for i in fr]).T)
    to_ark = lambda X: (s_c2a * R_c2a @ X.T + t_c2a).T
    ref_raw = np.loadtxt(REF_XYZ)
    ref_ark = to_ark(ref_raw[:, :3])
    out = {'subset': SUB, 'colmap_to_arkit_fullrun': {'n': len(fr), 'metres_per_colmap_unit': float(s_c2a),
                                                     'rmse_mm': float(np.sqrt((e_c2a ** 2).mean()) * 1e3)}}
    tree_ref = cKDTree(ref_ark)
    clouds = {}
    for lab, d, farm in ARMS:
        feed = load_feed(farm)
        assert [f['frameIndex'] for f in feed] == fid2fi, 'frame lists differ between arms'
        assert all(f['fxfycxcy'] == g['fxfycxcy'] for f, g in zip(feed, featA)), 'K differs between arms'
        o = {'run_dir': os.path.relpath(d, B)}
        log = open(d + '/run.log', errors='replace').read()
        for key in ('RESULT', 'STREAMED', 'FINALIZE_ASYNC'):
            m = re.search(rf'^{key} (.*)$', log, re.M); o[key.lower()] = m.group(1) if m else None
        tags = {}
        for tag in ['ARKIT-POSE-REJECT', '[AETHER gravity] MISSING', '[AETHER gravity] INCONSISTENT',
                    'mandatory-ARKit refine blocked', 'mandatory ARKit recovery blocked', '[gravity-ra]',
                    'add failed', 'Failed to fix Gauge']:
            tags[tag] = sum(1 for l in log.splitlines() if tag in l)
        o['gate_tag_counts'] = tags
        inj = re.findall(r'\[AETHER gravity\] injected (\d+)/(\d+)', log)
        o['gravity_anchor_injected'] = [sum(int(a) for a, _ in inj), sum(int(b) for _, b in inj)]
        m = re.search(r'(\d+)\s+maximum resident set size', log); o['max_rss_MB'] = int(m.group(1)) / 2**20 if m else None
        pf = [json.loads(l) for l in open(d + '/per_frame.jsonl')]
        o['per_frame_rejected'] = sum(1 for p in pf if p['rc'] != 'AETHER_SFM_OK')
        o['extract_ms_median'] = float(np.median([p['extract_ms'] for p in pf]))
        o['match_ms_median'] = float(np.median([p['match_ms'] for p in pf]))
        # scales vs ARKit metres (Sim3 of camera centres on the registered frames)
        D = delivered(d); ks = sorted(D)
        Pr = np.array([prior_C(feed[k]) for k in ks]).T; Ak = np.array([ark[k] for k in ks]).T
        Dc = np.array([D[k][1] for k in ks]).T
        s_pa, _, _, e_pa = sim3(Pr, Ak)
        o['prior_vs_arkit'] = {'metres_per_arkit_metre': float(1 / s_pa), 'rmse_mm': float(np.sqrt((e_pa ** 2).mean()) * 1e3)}
        if os.path.exists(d + '/live/live_end/images.bin'):
            L = model_centres(d + '/live/live_end'); kl = sorted(k for k in L if k in D)
            s_la, _, _, e_la = sim3(np.array([L[k][1] for k in kl]).T, np.array([ark[k] for k in kl]).T)
            o['live_end_vs_arkit'] = {'units_per_arkit_metre': float(1 / s_la), 'rmse_mm_after_sim3': float(np.sqrt((e_la ** 2).mean()) * 1e3)}
            # gauge: image 1 (fid 0) held fixed? baseline fid0->fid1 live vs final
            Lb = model_centres(d + '/live/live_end'); Fb = model_centres(d)
            s_lf, _, _, _ = sim3(np.array([Lb[k][1] for k in kl]).T, np.array([Fb[k][1] for k in kl]).T)
            o['finalize_gauge'] = {'fid0_centre_shift': float(np.linalg.norm(Lb[0][1] - Fb[0][1])),
                                   'global_scale_final_over_live': float(s_lf),
                                   'baseline01_live': float(np.linalg.norm(Lb[1][1] - Lb[0][1])),
                                   'baseline01_final': float(np.linalg.norm(Fb[1][1] - Fb[0][1])),
                                   'baseline01_prior_m': float(np.linalg.norm(prior_C(feed[1]) - prior_C(feed[0])))}
        s_da, R_da, t_da, e_da = sim3(Dc, Ak)
        o['delivered_vs_arkit'] = {'units_per_arkit_metre': float(1 / s_da), 'rmse_mm_after_sim3': float(np.sqrt((e_da ** 2).mean()) * 1e3)}
        # shape vs clean COLMAP (independent of device poses)
        Rc = np.array([refC[fid2fi[k]][1] for k in ks]).T
        s_dc, R_dc, t_dc, e_dc = sim3(Dc, Rc)
        path = float(np.sum(np.linalg.norm(np.diff(Rc, axis=1), axis=0)))
        rot = [P.ang(D[k][0] @ R_dc.T, refC[fid2fi[k]][0]) for k in ks]
        o['delivered_vs_clean_colmap'] = {'n': len(ks), 'rmse_pct_of_path': float(100 * np.sqrt((e_dc ** 2).mean()) / path),
                                          'rmse_mm': float(np.sqrt((e_dc ** 2).mean()) * s_c2a * 1e3),
                                          'rot_err_deg_median': float(np.median(rot)), 'rot_err_deg_max': float(np.max(rot))}
        # cloud -> reference frame (via own cameras) -> ARKit metres
        X = read_ply(d + '/cloud.ply')
        Xa = to_ark((s_dc * R_dc @ X.T + t_dc).T)
        dref, _ = tree_ref.query(Xa)
        o['cloud'] = {'n_points': int(len(X)), 'to_reference_nn': nn_stats(dref)}
        clouds[lab] = (Xa, dref, {k: to_ark((s_dc * R_dc @ D[k][1][:, None] + t_dc).T)[0] for k in ks})
        out[lab] = o
    # mutual A <-> X, and delivered X vs delivered A Sim3 (the requested "scale relative to ARKit arm")
    labA = ARMS[0][0]; XA = clouds[labA][0]; tA = cKDTree(XA)
    DA = delivered(ARMS[0][1])
    for lab, d, _ in ARMS[1:]:
        DX = delivered(d); com = sorted(set(DA) & set(DX))
        s, _, _, e = sim3(np.array([DX[k][1] for k in com]).T, np.array([DA[k][1] for k in com]).T)
        XX = clouds[lab][0]; tX = cKDTree(XX)
        dxa, _ = tA.query(XX); dax, _ = tX.query(XA)
        out[f'{lab}_vs_{labA}'] = {'n_common_registered': len(com), 'delivered_sim3_X_to_A_scale': float(s),
                                   'delivered_X_units_over_A_units': float(1 / s),
                                   'X_to_A_nn': nn_stats(dxa), 'A_to_X_nn(holes in X)': nn_stats(dax)}
    json.dump(out, open(f'{B}/runs/takeover_{SUB}.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))

    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    labs = [a[0] for a in ARMS if a[0] in RENDER] if RENDER else [a[0] for a in ARMS]
    camsA = np.array(list(clouds[labs[0]][2].values()))
    allp = np.concatenate([clouds[labs[0]][0], camsA])
    lo = np.percentile(allp, 0.5, axis=0); hi = np.percentile(allp, 99.5, axis=0)
    lo = np.minimum(lo, camsA.min(0)); hi = np.maximum(hi, camsA.max(0)); pad = 0.05 * (hi - lo); lo -= pad; hi += pad
    fig, ax = plt.subplots(3, len(labs), figsize=(5.0 * len(labs), 14.5), squeeze=False, constrained_layout=True)
    for j, l in enumerate(labs):
        c, dref, cams = clouds[l]
        keep = np.all((c >= lo) & (c <= hi), axis=1)
        cc, dd = c[keep], dref[keep]
        cam = np.array([cams[k] for k in sorted(cams)])
        for i, (u, v, name) in enumerate([(0, 2, 'top: x-z (m)'), (0, 1, 'side: x-y, y=up (m)')]):
            ax[i, j].scatter(cc[:, u], cc[:, v], s=0.15, c='k', alpha=0.35, linewidths=0)
            ax[i, j].plot(cam[:, u], cam[:, v], '.-', c='tab:blue', lw=0.7, ms=2)
            ax[i, j].set_xlim(lo[u], hi[u]); ax[i, j].set_ylim(lo[v], hi[v]); ax[i, j].set_aspect('equal')
            ax[i, j].set_title(f'{l} | {name}\n{len(c)} pts ({int(keep.sum())} in view)', fontsize=9)
        sc = ax[2, j].scatter(cc[:, 0], cc[:, 2], s=0.4, c=np.clip(dd * 100, 0, 5), cmap='inferno_r', vmin=0, vmax=5, linewidths=0)
        ax[2, j].set_xlim(lo[0], hi[0]); ax[2, j].set_ylim(lo[2], hi[2]); ax[2, j].set_aspect('equal')
        ax[2, j].set_title(f'{l} | top, colour = dist. to clean COLMAP\nmedian {np.median(dref)*1e3:.1f} mm, >2 cm {np.mean(dref>0.02)*100:.1f}%', fontsize=9)
    fig.colorbar(sc, ax=ax[2, :].tolist(), shrink=0.6, label='distance to reference cloud (cm)')
    fig.suptitle(f'{SUB}: delivered clouds in ARKit world (metres) via Sim3 to clean-COLMAP cameras; blue = delivered cameras', fontsize=11)
    fig.savefig(f'{B}/runs/takeover_render_{SUB}.png', dpi=90)
    print('wrote', f'{B}/runs/takeover_render_{SUB}.png')


if __name__ == '__main__':
    main()
