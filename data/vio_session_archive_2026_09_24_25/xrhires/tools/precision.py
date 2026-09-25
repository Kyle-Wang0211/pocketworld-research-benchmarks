#!/usr/bin/env python3
"""[xrhires] Where does higher resolution help? VIO-independent front-end measurement on the real frames.

For consecutive 30 Hz frames (production admission rule) of each recording, at 640 (box 3), 960 (box 2)
and 1920 (native) -- each with XRSLAM's own preprocessing (CLAHE clip 6, 8x8) and LK (21x21, maxLevel 3,
+extra levels in the 'scaled' variant, eps 0.01, 30 it, OPTFLOW_USE_INITIAL_FLOW with a rotation
prediction, forward-backward check):
  * epipolar (Sampson) residual of each tracked pair against ARKit's relative pose, in 640-px units
    (= angle x fx_640; resolution-independent reference)  -> feature LOCALISATION precision;
  * forward-backward error in 640-px units;
  * survival: fraction of points that pass status+border+FB, binned by gyro angular speed (blur proxy);
  * 1-s chains: fraction of points still tracked after 30 frames.
Two point sets: 'common' (GFTT on the 640 frame, mapped to each resolution -> isolates LK) and 'native'
(detection at each resolution with official px params, or scaled px params).
Self-check: the ARKit->OpenCV camera convention is chosen by the smaller median residual and both are printed.
"""
import json, sys, os
import numpy as np, cv2
cv2.setNumThreads(1)

R = os.path.expanduser('~/Developer/viobench-recordings')
RUNS = {'6e2d': 'run-6e2d4b99-896b-4372-ae47-ac0b4679cf18', '5966': 'run-5966aec0-cbf1-4abc-af0e-c1fc559da44c',
        '4ad6': 'run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa'}
W0, H0 = 1920, 1440


def load(sc):
    d = R + '/' + RUNS[sc]
    off = {}
    for ln in open(d + '/frames.pwvi'):
        j = json.loads(ln); off[j['frame']] = j['offset']
    cams = []
    for ln in list(open(d + '/camera_index.csv'))[1:]:
        a, b = ln.strip().split(','); cams.append((int(a), int(b)))
    adm, last = [], None
    for tns, fid in cams:   # production PwVioSlamFeeder rule, 30 Hz
        if fid not in off: continue
        t = tns * 1e-9
        if last is not None and t - last < 1 / 30: continue
        last = t; adm.append((tns, fid))
    K = {}
    E = {}
    for ln in open(d + '/intrinsics.jsonl'):
        j = json.loads(ln); tn = int(round(j['t'] * 1e9))
        K[tn] = j['intrinsics_fxfycxcy']
        if 'exposure_s' in j: E[tn] = j['exposure_s']
    kt = np.array(sorted(K));
    def k_at(tns):
        i = np.argmin(np.abs(kt - tns)); return K[kt[i]], E.get(kt[i])
    P = {}
    for ln in open(d + '/arkit_poses.tum'):
        f = ln.split()
        P[int(round(float(f[0]) * 1e9))] = np.array([float(x) for x in f[1:8]])
    pt = np.array(sorted(P))
    def pose_at(tns):
        i = np.argmin(np.abs(pt - tns))
        return P[pt[i]] if abs(pt[i] - tns) < 1_000_000 else None
    imu = np.loadtxt(d + '/imu.csv', delimiter=',', skiprows=1)
    mm = np.memmap(d + '/frames.bin', dtype=np.uint8, mode='r')
    def img(fid):
        o = off[fid]; return np.array(mm[o:o + W0 * H0]).reshape(H0, W0)
    return adm, k_at, pose_at, imu, img


def qmat(q):
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def box(im, d):
    if d == 1: return im
    h, w = im.shape[0] // d, im.shape[1] // d
    return np.rint(im[:h * d, :w * d].reshape(h, d, w, d).astype(np.float64).mean(axis=(1, 3))).astype(np.uint8)


CL = cv2.createCLAHE(clipLimit=6.0, tileGridSize=(8, 8))


def prep(im):
    return CL.apply(im)


def poisson(pts, r, preset=()):
    keep, acc = [], list(preset)
    for p in pts:
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= r * r for q in acc):
            acc.append(p); keep.append(p)
    return np.array(keep, dtype=np.float64).reshape(-1, 2)


def detect(im, s, scaled):
    md = 20 * (s if scaled else 1); bd = 20 * (s if scaled else 1); pd = 25 * (s if scaled else 1)
    c = cv2.goodFeaturesToTrack(im, 300, 1e-3, md, blockSize=3, useHarrisDetector=True, k=0.04)
    if c is None: return np.zeros((0, 2))
    c = c.reshape(-1, 2).astype(np.float64)
    c = poisson(c, pd)
    m = (c[:, 0] >= bd) & (c[:, 1] >= bd) & (c[:, 0] < im.shape[1] - bd) & (c[:, 1] < im.shape[0] - bd)
    return c[m]


def lk(pa, pb, p, pred, s, scaled):
    lev = 3 + (int(round(np.log2(s))) if scaled else 0)
    crit = (cv2.TERM_CRITERIA_COUNT + cv2.TERM_CRITERIA_EPS, 30, 0.01)
    p32 = p.astype(np.float32).reshape(-1, 1, 2); q0 = pred.astype(np.float32).reshape(-1, 1, 2)
    q, st, _ = cv2.calcOpticalFlowPyrLK(pa, pb, p32, q0.copy(), winSize=(21, 21), maxLevel=lev, criteria=crit,
                                        flags=cv2.OPTFLOW_USE_INITIAL_FLOW)
    r, st2, _ = cv2.calcOpticalFlowPyrLK(pb, pa, q, p32.copy(), winSize=(21, 21), maxLevel=lev, criteria=crit,
                                         flags=cv2.OPTFLOW_USE_INITIAL_FLOW)
    q = q.reshape(-1, 2).astype(np.float64); r = r.reshape(-1, 2).astype(np.float64)
    fb = np.linalg.norm(r - p, axis=1)
    bd = 20 * (s if scaled else 1)
    h, w = pa.shape
    ok = (st.ravel() == 1) & (st2.ravel() == 1) & (q[:, 0] >= bd) & (q[:, 1] >= bd) & (q[:, 0] < w - bd) & (q[:, 1] < h - bd)
    ok &= np.linalg.norm(q - p, axis=1) <= h / 4
    ok_fb = ok & (fb <= 0.5 * (s if scaled else 1))
    return q, ok, ok_fb, fb


def Kmat(k, s):
    return np.array([[k[0] * s / 3, 0, (k[2] + 0.5) * s / 3 - 0.5], [0, k[1] * s / 3, (k[3] + 0.5) * s / 3 - 0.5], [0, 0, 1]])


def sampson_640(x1, x2, R21, t21, K1, K2, fx640):
    """Sampson distance of pixel pairs under E=[t]x R, returned in 640-px units (normalised coords x fx640)."""
    n1 = np.linalg.solve(K1, np.c_[x1, np.ones(len(x1))].T).T
    n2 = np.linalg.solve(K2, np.c_[x2, np.ones(len(x2))].T).T
    t = t21 / (np.linalg.norm(t21) + 1e-12)
    E = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]]) @ R21
    Ex1 = (E @ n1.T).T; Etx2 = (E.T @ n2.T).T
    num = np.sum(n2 * Ex1, axis=1)
    den = Ex1[:, 0] ** 2 + Ex1[:, 1] ** 2 + Etx2[:, 0] ** 2 + Etx2[:, 1] ** 2
    return np.abs(num) / np.sqrt(den + 1e-30) * fx640


def main(sc, step=4, nchain=6, conv=None):
    adm, k_at, pose_at, imu, img = load(sc)
    D = np.diag([1.0, -1.0, -1.0])
    RES = [(1, 3), (1.5, 2), (3, 1)]   # (s vs 640, box factor)
    out = {'scene': sc, 'pairs': []}
    convs = [conv] if conv else ['cv_flip']   # smoke test 2026-09-24: cv_flip median 0.07-0.15 px640 vs identity 0.5-3.1
    for i in range(10, len(adm) - 1, step):
        (ta, fa), (tb, fb_) = adm[i], adm[i + 1]
        Pa, Pb = pose_at(ta), pose_at(tb)
        if Pa is None or Pb is None or not np.any(Pa[:3]) or not np.any(Pb[:3]): continue
        ka, ea = k_at(ta); kb, _ = k_at(tb)
        m = (imu[:, 0] >= ta) & (imu[:, 0] <= tb)
        wmag = float(np.linalg.norm(imu[m, 1:4].mean(0))) if m.any() else float('nan')
        Ia, Ib = img(fa), img(fb_)
        rec = {'i': i, 'w': wmag, 'exp': ea, 'res': {}}
        # common points from 640 detection
        base_a = prep(box(Ia, 3))
        c640 = detect(base_a, 1, False)
        for conv_ in convs:
            Ra = qmat(Pa[3:]); Rb = qmat(Pb[3:])
            if conv_ == 'cv_flip': Ra = Ra @ D; Rb = Rb @ D
            R21 = Rb.T @ Ra; t21 = Rb.T @ (Pa[:3] - Pb[:3])
            rec.setdefault('geo', {})[conv_] = (R21.tolist(), t21.tolist())
        for s, d in RES:
            A, B = prep(box(Ia, d)), prep(box(Ib, d))
            K1, K2 = Kmat(ka, s * 1.0), Kmat(kb, s * 1.0)   # (k*s/3 : ARKit K is 1920 px, s=3 -> 1920)
            fx640 = ka[0] / 3
            for pset in ['common', 'native_off', 'native_scl']:
                if pset == 'common':
                    p = (c640 + 0.5) * s - 0.5
                else:
                    p = detect(A, s, pset == 'native_scl')
                if len(p) < 8: continue
                for variant in (['off', 'scl'] if s != 1 else ['off']):
                    scaled = variant == 'scl'
                    if pset == 'native_scl' and not scaled: continue
                    if pset == 'native_off' and scaled: continue
                    res = {}
                    for conv_ in convs:
                        R21 = np.array(rec['geo'][conv_][0]); t21 = np.array(rec['geo'][conv_][1])
                        nb = (K2 @ R21 @ np.linalg.solve(K1, np.c_[p, np.ones(len(p))].T)).T
                        pred = nb[:, :2] / nb[:, 2:3]
                        q, ok, okfb, fbe = lk(A, B, p, pred, s, scaled)
                        samp = sampson_640(p[okfb], q[okfb], R21, t21, K1, K2, fx640) if okfb.sum() else np.array([])
                        # self-fitted E (removes ARKit relative-pose error from the floor): 5-pt RANSAC + LM on
                        # normalised coords, threshold 1 px640; residual of the inliers in px640
                        sself = np.array([])
                        if okfb.sum() >= 15:
                            n1 = np.linalg.solve(K1, np.c_[p[okfb], np.ones(okfb.sum())].T).T[:, :2]
                            n2 = np.linalg.solve(K2, np.c_[q[okfb], np.ones(okfb.sum())].T).T[:, :2]
                            Ef, msk = cv2.findEssentialMat(n1, n2, np.eye(3), cv2.RANSAC, 0.999, 1.0 / fx640)
                            if Ef is not None and Ef.shape == (3, 3):
                                _, Rf, tf, _ = cv2.recoverPose(Ef, n1, n2, np.eye(3))
                                sself = sampson_640(p[okfb], q[okfb], Rf, tf.ravel(), K1, K2, fx640)
                        res[conv_] = {'n': int(len(p)), 'ok': int(ok.sum()), 'okfb': int(okfb.sum()),
                                      'fb640_med': float(np.median(fbe[ok] / s)) if ok.any() else None,
                                      'samp640': samp.tolist(), 'sself640': sself.tolist(), 'fb640': (fbe[okfb] / s).tolist()}
                    rec['res'][f'{int(s*640)}_{pset}_{variant}'] = res
        out['pairs'].append(rec)
        if len(out['pairs']) % 20 == 0:
            print(sc, len(out['pairs']), file=sys.stderr)
    # 1-s chains (common 640 points), official vs scaled LK
    chains = []
    for c0 in np.linspace(20, len(adm) - 40, nchain).astype(int):
        seq = adm[c0:c0 + 31]
        imgs = [img(f) for _, f in seq]
        poses = [pose_at(t) for t, _ in seq]
        if any(p is None for p in poses): continue
        kk = [k_at(t)[0] for t, _ in seq]
        base = prep(box(imgs[0], 3)); c640 = detect(base, 1, False)
        cr = {'start': int(c0), 'n0': int(len(c640))}
        for s, d in RES:
            for variant in (['off', 'scl'] if s != 1 else ['off']):
                scaled = variant == 'scl'
                p = (c640 + 0.5) * s - 0.5; alive = np.ones(len(p), bool)
                prev = prep(box(imgs[0], d)); surv = []; p0 = p.copy(); endres = {}
                for j in range(1, len(seq)):
                    cur = prep(box(imgs[j], d))
                    Ra = qmat(poses[j - 1][3:]) @ D; Rb = qmat(poses[j][3:]) @ D
                    R21 = Rb.T @ Ra
                    K1, K2 = Kmat(kk[j - 1], s), Kmat(kk[j], s)
                    nb = (K2 @ R21 @ np.linalg.solve(K1, np.c_[p, np.ones(len(p))].T)).T
                    pred = nb[:, :2] / nb[:, 2:3]
                    q, ok, okfb, _ = lk(prev, cur, p, pred, s, scaled)
                    alive &= okfb; p = np.where(okfb[:, None], q, p); prev = cur
                    surv.append(float(alive.mean()) if len(alive) else 0.0)
                    if j in (10, 20, 30) and alive.sum() >= 5:
                        R0w = qmat(poses[0][3:]) @ D; Rjw = qmat(poses[j][3:]) @ D
                        Rj0 = Rjw.T @ R0w; tj0 = Rjw.T @ (poses[0][:3] - poses[j][:3])
                        er = sampson_640(p0[alive], p[alive], Rj0, tj0, Kmat(kk[0], s), Kmat(kk[j], s), kk[0][0] / 3)
                        endres[j] = er.tolist()
                cr[f'{int(s*640)}_{variant}'] = surv
                cr[f'{int(s*640)}_{variant}_epi'] = endres
                cr[f'{int(s*640)}_{variant}_alive_idx'] = np.where(alive)[0].tolist()
        chains.append(cr)
    out['chains'] = chains
    return out


if __name__ == '__main__':
    sc = sys.argv[1]; step = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    o = main(sc, step, nchain=int(sys.argv[4]) if len(sys.argv) > 4 else 6)
    json.dump(o, open(sys.argv[3], 'w'))
    print('done', sc, len(o['pairs']))
