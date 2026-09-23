#!/usr/bin/python3
# prep_inputs.py — build the two arms' per-frame feed lists for the host replay
# of the SHIPPING official SfM route (Aether3D 7dc00642 == a313ede0 core,
# = phone builds 165..169 PWOfficialSfm, stamp "Sep 16 2026 10:55:14").
#
# Every convention below is cited; nothing is fitted.
#
#  ARKit pose (arm A): arkit_poses.tum rows are world_from_camera
#     (calibration.json "pose_frame":"world_from_camera"), ARKit camera axes
#     (+X right, +Y up, looks along -Z: auto_capture_geometry.dart:5-6),
#     gravity-aligned world with +Y up (config.json "world_alignment":"gravity";
#     mandatory_arkit_gravity_v1.h:25-27 "ARKit's gravity-aligned world uses +Y up").
#  Product ABI pose: CamFromWorld of that same ARKit camera, quaternion wxyz:
#     R_w2c = R_c2w^T, t_w2c = -R_w2c * C
#     (pocketworld lib/official_capture/sfm_live_recon.dart:741-756).
#  XRSLAM pose (arm X): TUM rows are the body/IMU pose world_from_body
#     (output.q_bo/p_bo = identity: sb/cfg/phone_slam_prod.yaml:2-4;
#      core/detail.cpp:266-268 output = state * output_to_body),
#     world gravity = (0,0,-g) i.e. z-up (xrslam core/detail.cpp:20,
#     initializer.cpp:536).
#  body->camera: T_BC = [R_bc | p_bc] with q_bc(xyzw) = [-0.7071068,0.7071068,0,0]
#     -> R_bc = [[0,-1,0],[-1,0,0],[0,0,-1]], p_bc(iPhone15,2) =
#     [0.03290364,-0.00696553,-0.00286231]
#     (pocketworld lib/vio/ffi/xrslam_extrinsics.dart:31-40,90;
#      identical to sb/cfg/dev_6e2d4b99_td+8.yaml cam0.T_BS).
#     T_WC = T_WB * T_BC  (memory project_pocketworld_ate_vs_arkit_had_uncorrected_3_4cm_lever_arm).
#  XRSLAM camera axes = OpenCV (x right, y down, z forward):
#     geometry/stereo.h:8-10 apply_k = (x/z*fx+cx, y/z*fy+cy).
#  OpenCV cam -> ARKit cam: diag(1,-1,-1) (the same C the product uses in
#     mandatory_arkit_gravity_v1.h:25-26 / .cc:69-73).
#  z-up world -> y-up world: inverse of ate.py:161 Rx90 ((x,y,z)->(x,-z,y) maps
#     y-up to z-up), i.e. M = Rx90^T : (x,y,z)->(x,z,-y).
#  XRSLAM output time = image time + cam0.time_offset
#     (xrslam-pc/player/src/IO/euroc_dataset_reader.cpp:16).
#
# Frame subsets (product shutter is motion-driven, not timed; we can only
# approximate it with pose-free documented cadences, identical for both arms):
#  S_prod : one frame per 2.133 s = the phone's median shutter gap
#           (pocketworld commit 35c3046 message) = every 128th frame at 60 Hz.
#  S_deb  : one frame per 0.25 s = the governor's debounce floor
#           (lib/official_capture/auto_capture_governor.dart:53,57) = every 15th.
# Per-frame K from intrinsics.jsonl (ARFrame.camera.intrinsics), same K both arms
# (product passes per-frame K: sfm_live_recon.dart:736-739; core keeps one
#  PINHOLE camera per image: official_aether_sfm_c.cc:9263-9265).
import json, sys, os
import numpy as np

REC = os.path.expanduser('~/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18')
SCR = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad'
OUT = SCR + '/sfmB/inputs'
COLMAP_REF = os.path.expanduser('~/Developer/colmap-6e2d4b99/sparse_all/images.txt')
W, H = 1920, 1440
FRAME_BYTES = W * H

XR_SOURCES = {
    # the viobench app's on-device replay of this recording (iPhone15,2, 08-31)
    'xdev': (REC + '/replay/xrslam_poses.tum', None),
    # host replay, xrslam fork 04c0e83, prod profile, per-frame K, td=+8ms (09-23)
    'xhost': (SCR + '/sb/out/6e2d4b99/base_prod_r1.tum', 0.008),
}

R_BC = np.array([[0., -1., 0.], [-1., 0., 0.], [0., 0., -1.]])
P_BC = np.array([0.03290364, -0.00696553, -0.00286231])
F = np.diag([1., -1., -1.])
RX90 = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])  # ate.py:161
M_ZUP_TO_YUP = RX90.T


def q2R(w, x, y, z):
    n = np.sqrt(w*w + x*x + y*y + z*z); w, x, y, z = w/n, x/n, y/n, z/n
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def R2q(R):  # wxyz, w>=0
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2; w = 0.25*s
        x = (R[2, 1]-R[1, 2])/s; y = (R[0, 2]-R[2, 0])/s; z = (R[1, 0]-R[0, 1])/s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0+R[0, 0]-R[1, 1]-R[2, 2])*2; w = (R[2, 1]-R[1, 2])/s
        x = 0.25*s; y = (R[0, 1]+R[1, 0])/s; z = (R[0, 2]+R[2, 0])/s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0+R[1, 1]-R[0, 0]-R[2, 2])*2; w = (R[0, 2]-R[2, 0])/s
        x = (R[0, 1]+R[1, 0])/s; y = 0.25*s; z = (R[1, 2]+R[2, 1])/s
    else:
        s = np.sqrt(1.0+R[2, 2]-R[0, 0]-R[1, 1])*2; w = (R[1, 0]-R[0, 1])/s
        x = (R[0, 2]+R[2, 0])/s; y = (R[1, 2]+R[2, 1])/s; z = 0.25*s
    q = np.array([w, x, y, z]); q /= np.linalg.norm(q)
    return q if q[0] >= 0 else -q


def load_tum(p):
    rows = []
    for ln in open(p):
        f = ln.split()
        if len(f) < 8 or ln.startswith('#'):
            continue
        rows.append([float(v) for v in f[:8]])
    return np.array(rows)


def ang(Ra, Rb):
    c = (np.trace(Ra.T @ Rb) - 1) / 2
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


def vang(a, b):
    return np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1)))


def umeyama(X, Y):
    mx, my = X.mean(1, keepdims=True), Y.mean(1, keepdims=True)
    Xc, Yc = X-mx, Y-my
    S = Yc @ Xc.T / X.shape[1]
    U, D, Vt = np.linalg.svd(S); d = np.ones(3)
    if np.linalg.det(U)*np.linalg.det(Vt) < 0: d[2] = -1
    R = U @ np.diag(d) @ Vt
    s = (D*d).sum() / ((Xc**2).sum()/X.shape[1])
    return s, R, my - s*R@mx


def main():
    # frames
    ts_ns = {}
    for ln in list(open(REC + '/camera_index.csv'))[1:]:
        a, b = ln.strip().split(',')
        ts_ns[int(b)] = int(a)
    n_frames = len(ts_ns)
    ts = np.array([ts_ns[i] for i in range(n_frames)]) * 1e-9
    Kt, Kv = [], []
    for ln in open(REC + '/intrinsics.jsonl'):
        j = json.loads(ln)
        Kt.append(j['t']); Kv.append(j['intrinsics_fxfycxcy'])
    Kt = np.array(Kt)
    Kf = []
    for i in range(n_frames):
        j = int(np.argmin(np.abs(Kt - ts[i])))
        assert abs(Kt[j] - ts[i]) < 1e-6, 'per-frame K missing'
        Kf.append(Kv[j])

    # ARKit
    ark = load_tum(REC + '/arkit_poses.tum')
    ark_idx = {}
    for r in ark:
        i = int(np.argmin(np.abs(ts - r[0])))
        if abs(ts[i] - r[0]) < 1e-6:
            ark_idx[i] = r
    A = {}  # i -> (R_wc_arkitcam, C)
    for i, r in ark_idx.items():
        C = r[1:4]; R = q2R(r[7], r[4], r[5], r[6])
        if np.allclose(C, 0) and np.allclose(R, np.eye(3)):
            continue  # ARKit not yet tracking (first rows are exact identity/zero)
        A[i] = (R, C)

    # XRSLAM sources
    X = {}
    tstats = {}
    for name, (path, td) in XR_SOURCES.items():
        tr = load_tum(path)
        d = {}
        res = []
        for r in tr:
            tt = r[0] - (td or 0.0)
            i = int(np.argmin(np.abs(ts - tt)))
            res.append(tt - ts[i])
            if abs(tt - ts[i]) < 0.5e-3:
                R_wb = q2R(r[7], r[4], r[5], r[6]); p_wb = r[1:4]
                R_wc_cv = R_wb @ R_BC; C_z = p_wb + R_wb @ P_BC
                R_wc_ark = M_ZUP_TO_YUP @ R_wc_cv @ F
                d[i] = (R_wc_ark, M_ZUP_TO_YUP @ C_z, R_wb, p_wb)
        res = np.abs(np.array(res)) * 1e3
        tstats[name] = (len(tr), len(d), float(np.median(res)), float(res.max()))
        X[name] = d

    # clean COLMAP reference (no ARKit, no XRSLAM): CamFromWorld, OpenCV axes
    Rcol = {}
    lines = [l for l in open(COLMAP_REF) if not l.startswith('#')]
    for k in range(0, len(lines), 2):
        f = lines[k].split()
        nm = f[9]; i = int(nm[1:6])
        Rcol[i] = q2R(*[float(v) for v in f[1:5]])

    report = {'time_association_ms': tstats}

    def cv_R_cw(R_wc_ark):  # CamFromWorld in OpenCV axes (what COLMAP stores)
        return (R_wc_ark @ F).T

    def gcam(R_wc_ark):  # product's gravity_cam (COLMAP axes) = R_cw_cv*(0,-1,0)
        return cv_R_cw(R_wc_ark) @ np.array([0., -1., 0.])

    common_all = sorted(set(A) & set(X['xdev']) & set(X['xhost']) & set(Rcol))
    report['n_common_frames'] = len(common_all)
    report['first_last_common'] = [common_all[0], common_all[-1]]

    # subsets: anchored at the first frame every source has a pose for
    first = common_all[0]
    subsets = {
        'S_prod': [i for i in range(first, n_frames, 128) if i in common_all],
        'S_deb': [i for i in range(first, n_frames, 15) if i in common_all],
    }
    report['subsets'] = {k: {'n': len(v), 'frames': v} for k, v in subsets.items()}

    # ---------------- diagnostics (each must be able to fail) ----------------
    def rel_rot_err(src, frames, lag=1):
        e = []
        for a, b in zip(frames[:-lag], frames[lag:]):
            Ra, Rb = cv_R_cw(src[a][0]), cv_R_cw(src[b][0])
            Rrel_src = Rb @ Ra.T
            Rrel_col = Rcol[b] @ Rcol[a].T
            e.append(ang(Rrel_src, Rrel_col))
        return np.array(e)

    def pair_list(frames, src):
        # product-like pairs: view-axis angle < 45 deg (official_sfm_c.h:71-75),
        # chosen on ARKit poses for BOTH arms so the pair set is identical.
        P = []
        for ii, a in enumerate(frames):
            for b in frames[ii+1:]:
                fa = A[a][0] @ np.array([0, 0, -1.]); fb = A[b][0] @ np.array([0, 0, -1.])
                if vang(fa, fb) < 45.0:
                    P.append((a, b))
        return P

    def grav_pair_eps(src, pairs):
        # upright-3pt assumes g_b == R_ba * g_a exactly (upright_relative_pose_v1.h:40-47).
        # eps = how far the source's two gravity vectors violate that, using the
        # image-only COLMAP relative rotation as the reference.
        e = []
        for a, b in pairs:
            ga, gb = gcam(src[a][0]), gcam(src[b][0])
            Rba = Rcol[b] @ Rcol[a].T
            e.append(vang(Rba @ ga, gb))
        return np.array(e)

    def stats(v):
        return {'n': int(v.size), 'median': float(np.median(v)), 'p90': float(np.percentile(v, 90)),
                'max': float(v.max())}

    srcs = {'arkit': A, 'xdev': X['xdev'], 'xhost': X['xhost']}
    diag = {}
    for sname, sub in subsets.items():
        pairs = pair_list(sub, A)
        dd = {'n_pairs_lt45deg': len(pairs)}
        for nm, src in srcs.items():
            e_rel = rel_rot_err(src, sub)
            e_g = grav_pair_eps(src, pairs)
            fx_med = float(np.median([Kf[i][0] for i in sub]))
            dd[nm] = {'rel_rot_err_deg_consecutive': stats(e_rel),
                      'gravity_pair_violation_deg': stats(e_g),
                      'gravity_pair_violation_px_at_fx': {
                          'median': float(np.radians(np.median(e_g)) * fx_med),
                          'p90': float(np.radians(np.percentile(e_g, 90)) * fx_med)},
                      'frac_pairs_violation_gt_4px': float(np.mean(np.radians(e_g) * fx_med > 4.0)),
                      'frac_pairs_violation_gt_1px': float(np.mean(np.radians(e_g) * fx_med > 1.0))}
        # tilt disagreement X vs ARKit per frame (what the >30deg anchor gate sees)
        for nm in ('xdev', 'xhost'):
            t = np.array([vang(gcam(A[i][0]), gcam(X[nm][i][0])) for i in sub])
            dd[nm]['tilt_vs_arkit_deg'] = stats(t)
            CA = np.array([A[i][1] for i in sub]).T
            CX = np.array([X[nm][i][1] for i in sub]).T
            s, R, t0 = umeyama(CX, CA)
            e = np.linalg.norm(s*R@CX + t0 - CA, axis=0)
            dd[nm]['sim3_centers_vs_arkit'] = {'scale_x_to_arkit': float(s),
                                               'rmse_m': float(np.sqrt((e**2).mean())),
                                               'yaw_only_rot_residual_tilt_deg': float(np.degrees(np.arccos(np.clip(R[1, 1], -1, 1))))}
        diag[sname] = dd

    # negative controls on S_deb (a wrong convention must blow up the metrics)
    sub = subsets['S_deb']; pairs = pair_list(sub, A)
    neg = {}
    tr = X['xdev']
    wrong_world = {i: (v[0] if False else (v[2] @ R_BC @ F), None) for i, v in tr.items()}  # no z->y
    wrong_cam = {i: (M_ZUP_TO_YUP @ v[2] @ F, None) for i, v in tr.items()}                 # no R_bc
    for nm, src in (('no_world_zup_to_yup', wrong_world), ('no_body_to_cam_rotation', wrong_cam)):
        neg[nm] = {'rel_rot_err_deg_consecutive': stats(rel_rot_err(src, sub)),
                   'tilt_vs_arkit_deg': stats(np.array([vang(gcam(A[i][0]), gcam(src[i][0])) for i in sub])),
                   'gravity_pair_violation_deg': stats(grav_pair_eps(src, pairs))}
    diag['negative_controls_S_deb_xdev'] = neg
    report['diagnostics'] = diag

    # ---------------- feed files ----------------
    os.makedirs(OUT, exist_ok=True)
    for sname, sub in subsets.items():
        for arm, src in (('A', A), ('Xdev', X['xdev']), ('Xhost', X['xhost'])):
            with open(f'{OUT}/feed_{sname}_{arm}.jsonl', 'w') as fo:
                for i in sub:
                    R_wc, C = src[i][0], src[i][1]
                    R_w2c = R_wc.T; t_w2c = -R_w2c @ C
                    q = R2q(R_w2c)
                    fo.write(json.dumps({'frameIndex': i, 'byteOffset': i * FRAME_BYTES,
                                         'w': W, 'h': H, 'fxfycxcy': Kf[i],
                                         'arkitCamFromWorldQwxyz': q.tolist(),
                                         'arkitCamFromWorldTxyz': t_w2c.tolist()}) + '\n')
    json.dump(report, open(OUT + '/prep_report.json', 'w'), indent=1)
    print(json.dumps(report, indent=1)[:12000])


if __name__ == '__main__':
    main()
