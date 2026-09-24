#!/usr/bin/python3
"""Image-side arbiter for device-vs-recon disagreements (read-only on capture dirs).
For frame pairs (i,j): take the capture's OWN raw descriptor matches (official_sfm_live.db `matches`, i.e. before the
core's geometric verification) + keypoints, normalise with each frame's own PINHOLE K (db `cameras`), and estimate the
relative pose with OpenCV's official essential-matrix pipeline (cv2.findEssentialMat RANSAC, 5-point Nister, then
cv2.recoverPose cheirality). No hand-rolled geometry. Compare cam_j_from_cam_i of
  device (fed ARKit CamFromWorld, COLMAP axes = core conversion)   and   recon (delivered CamFromWorld)
with the image estimate: rotation angle difference (deg) and translation DIRECTION angle (deg, scale-free).
DB opened with sqlite URI immutable=1 (no -shm/-wal writes). Every file stat'ed for 'dataless' first."""
import json, os, sqlite3, subprocess, sys
import numpy as np, cv2, pycolmap
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG = {r['cap']: r for r in json.load(open(W + '/results/phone_gate/phone_gate.json'))['rows']}
MAXID = 2147483647
def ok(p):
    r = subprocess.run(['/usr/bin/stat', '-f', '%Sf', p], capture_output=True, text=True)
    if r.returncode != 0 or 'dataless' in r.stdout: raise SystemExit('dataless/missing ' + p)
    return p
def q2R(w, x, y, z):
    n = (w*w+x*x+y*y+z*z) ** .5; w, x, y, z = w/n, x/n, y/n, z/n
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
def rel(Ri, ti, Rj, tj):  # cam_j_from_cam_i
    R = Rj @ Ri.T; return R, tj - R @ ti
def ang(R): return np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
def dang(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float('nan') if na < 1e-12 or nb < 1e-12 else np.degrees(np.arccos(np.clip(a @ b / na / nb, -1, 1)))
class Cap:
    def __init__(self, cap):
        self.cap = cap; r = PG[cap]; d = r['dir']; self.a = r['r040']
        self.con = sqlite3.connect(f'file:{ok(d + "/official_sfm_live.db")}?immutable=1', uri=True)
        c = self.con.cursor()
        self.img = {}  # frame id -> (image_id, camera_id)
        for iid, name, cid in c.execute('select image_id,name,camera_id from images'):
            self.img[int(''.join(ch for ch in name if ch.isdigit()))] = (iid, cid)
        self.K = {cid: np.frombuffer(p, np.float64) for cid, p in c.execute('select camera_id,params from cameras')}
        self.pairs = {}
        for l in open(os.environ.get('PAIRS') or W + f'/results/phone_gate/{cap}.pairs.txt'):
            if not l.strip(): continue
            v = l.split(); f = int(v[0]); x = [float(t) for t in v[1:]]
            self.pairs[f] = ((q2R(*x[0:4]), np.array(x[4:7])), (q2R(*x[7:11]), np.array(x[11:14])))
        self.err = dict(zip(self.a['frame_ids'], self.a['centre_err_all_m'])); self.inl = dict(zip(self.a['frame_ids'], self.a['inlier_all']))
        self.fed = {j['frameId']: j for j in (json.loads(l) for l in open(ok(d + '/official_sfm_fed_frames.jsonl')))}
        self.kp = {}
    def kps(self, iid):
        if iid not in self.kp:
            r = self.con.execute('select rows,cols,data from keypoints where image_id=?', (iid,)).fetchone()
            self.kp[iid] = np.frombuffer(r[2], np.float32).reshape(r[0], r[1])[:, :2].astype(np.float64)
        return self.kp[iid]
    def matches(self, fi, fj, table='matches'):
        (ii, ci), (ij, cj) = self.img[fi], self.img[fj]
        a, b, sw = (ii, ij, False) if ii < ij else (ij, ii, True)
        r = self.con.execute(f'select rows,data from {table} where pair_id=?', (a * MAXID + b,)).fetchone()
        if not r or not r[0] or r[1] is None: return None
        m = np.frombuffer(r[1], np.uint32).reshape(r[0], 2).astype(np.int64)
        return m[:, ::-1] if sw else m
    def image_rel(self, fi, fj, seed=0):
        m = self.matches(fi, fj)
        if m is None or len(m) < 30: return None
        (ii, ci), (ij, cj) = self.img[fi], self.img[fj]
        def norm(p, k): return np.stack([(p[:, 0] - k[2]) / k[0], (p[:, 1] - k[3]) / k[1]], 1)
        x1 = norm(self.kps(ii)[m[:, 0]], self.K[ci]); x2 = norm(self.kps(ij)[m[:, 1]], self.K[cj])
        f = 0.5 * (self.K[ci][0] + self.K[cj][0])
        cv2.setRNGSeed(seed)
        E, mask = cv2.findEssentialMat(x1, x2, np.eye(3), method=cv2.RANSAC, prob=0.9999, threshold=1.0 / f)
        if E is None or E.shape != (3, 3): return None
        n, R, t, mask2 = cv2.recoverPose(E, x1, x2, np.eye(3), mask=mask.copy())
        out = dict(R=R, t=t.ravel(), n_raw=len(m), n_E=int(mask.sum()), n_pose=int(n))
        # Second, independent official estimator: COLMAP's own two-view geometry (E/F/H model selection incl. planar /
        # panoramic degeneracy, then relative pose) = pycolmap.estimate_calibrated_two_view_geometry, fixed seed.
        k1, k2 = self.K[ci], self.K[cj]
        c1 = pycolmap.Camera(model='PINHOLE', width=4032, height=3024, params=list(k1[:4]))
        c2 = pycolmap.Camera(model='PINHOLE', width=4032, height=3024, params=list(k2[:4]))
        o = pycolmap.TwoViewGeometryOptions(); o.compute_relative_pose = True; o.ransac.random_seed = 20260924
        g = pycolmap.estimate_calibrated_two_view_geometry(c1, self.kps(ii), c2, self.kps(ij), m.astype(np.uint32), o)
        out['colmap_config'] = {int(v): k for k, v in pycolmap.TwoViewGeometryConfiguration.__members__.items()}.get(int(g.config), str(g.config))
        out['colmap_inl'] = len(g.inlier_matches)
        try:
            T = g.cam2_from_cam1; out['R_c'] = np.asarray(T.rotation.matrix()); out['t_c'] = np.asarray(T.translation).ravel()
        except Exception:
            out['R_c'] = None
        return out
    def compare(self, fi, fj):
        out = dict(i=fi, j=fj, dt=self.fed[fj]['captureTimestamp'] - self.fed[fi]['captureTimestamp'])
        im = self.image_rel(fi, fj)
        if im is None or fi not in self.pairs or fj not in self.pairs:
            out['skip'] = 'no_matches' if im is None else 'unregistered'; return out
        (Rri, tri), (Rdi, tdi) = self.pairs[fi]; (Rrj, trj), (Rdj, tdj) = self.pairs[fj]
        Rr, tr = rel(Rri, tri, Rrj, trj); Rd, td = rel(Rdi, tdi, Rdj, tdj)
        # C = diag(1,-1,-1) applied by the core to ARKit camera axes; pairs.txt device poses are already COLMAP axes.
        out.update(n_raw=im['n_raw'], n_E=im['n_E'], n_pose=im['n_pose'],
                   rot_dev_vs_img=ang(Rd @ im['R'].T), rot_rec_vs_img=ang(Rr @ im['R'].T), rot_dev_vs_rec=ang(Rd @ Rr.T),
                   dir_dev_vs_img=dang(td, im['t']), dir_rec_vs_img=dang(tr, im['t']), dir_dev_vs_rec=dang(td, tr),
                   base_dev_m=float(np.linalg.norm(-Rdj.T @ tdj + Rdi.T @ tdi)))
        out['colmap_config'] = im['colmap_config']; out['colmap_inl'] = im['colmap_inl']
        if im.get('R_c') is not None and np.linalg.norm(im['t_c']) > 0:
            Rc, tc = im['R_c'], im['t_c']
            out.update(c_rot_dev=ang(Rd @ Rc.T), c_rot_rec=ang(Rr @ Rc.T), c_dir_dev=dang(td, tc), c_dir_rec=dang(tr, tc),
                       cv_vs_colmap_rot=ang(im['R'] @ Rc.T), cv_vs_colmap_dir=dang(im['t'], tc))
            # image testimony counts only when the two official estimators agree with each other
            out['img_ok'] = bool(out['cv_vs_colmap_rot'] < 2.0 and out['cv_vs_colmap_dir'] < 5.0 and im['colmap_config'] == 'CALIBRATED')
        else:
            out['img_ok'] = False
        return out
def fmt(o, cap):
    if 'skip' in o: return '  %3d->%3d  %s' % (o['i'], o['j'], o['skip'])
    fl = lambda f: ('*' if not cap.inl.get(f, 1) else ' ')
    s = ('  %3d%s->%3d%s dt=%6.2f base=%.3f raw=%4d cvE=%4d | CV rot dev/rec %5.2f/%5.2f dir %6.1f/%6.1f' % (
        o['i'], fl(o['i']), o['j'], fl(o['j']), o['dt'], o['base_dev_m'], o['n_raw'], o['n_E'],
        o['rot_dev_vs_img'], o['rot_rec_vs_img'], o['dir_dev_vs_img'], o['dir_rec_vs_img']))
    if 'c_rot_dev' in o:
        s += ' | COLMAP %s inl=%d rot dev/rec %5.2f/%5.2f dir %6.1f/%6.1f | cv~colmap %s' % (
            o['colmap_config'], o['colmap_inl'], o['c_rot_dev'], o['c_rot_rec'], o['c_dir_dev'], o['c_dir_rec'], 'OK' if o['img_ok'] else 'DISAGREE')
    else:
        s += ' | COLMAP %s (no pose)' % o['colmap_config']
    return s
if __name__ == '__main__':
    cap = Cap(sys.argv[1]); spec = sys.argv[2:]
    order = sorted(cap.fed, key=lambda k: cap.fed[k]['captureTimestamp'])
    res = []
    if spec == ['auto']:  # time-consecutive pairs and skip-one pairs over the whole capture
        prs = [(order[k], order[k + 1]) for k in range(len(order) - 1)] + [(order[k], order[k + 2]) for k in range(len(order) - 2)]
    else:
        prs = [tuple(int(v) for v in s.split(',')) for s in spec]
    for i, j in prs:
        o = cap.compare(i, j); res.append(o)
        if spec != ['auto']: print(fmt(o, cap))
    os.makedirs(W + '/taskB', exist_ok=True)
    json.dump(res, open(W + f'/taskB/twoview_{cap.cap}{os.environ.get("TAG", "")}.json', 'w'), indent=0, default=float)
    if spec == ['auto']:
        for o in res:
            if 'skip' in o: continue
            bad = (not cap.inl.get(o['i'], 1)) or (not cap.inl.get(o['j'], 1))
            if bad or o['dir_dev_vs_rec'] > 20 or o['rot_dev_vs_rec'] > 3: print(fmt(o, cap))
        allv = [o for o in res if 'skip' not in o and o.get('img_ok')]
        for k in ('c_dir_rec', 'c_rot_rec', 'c_dir_dev', 'c_rot_dev'):
            v = np.array([o[k] for o in allv])
            print('  [ALL valid pairs n=%d] %s median %.2f p90 %.2f max %.1f  n>20deg(dir)/>5deg(rot): %d' % (len(v), k, np.median(v), np.percentile(v, 90), v.max(),
                  int((v > (20 if 'dir' in k else 5)).sum())))
        good = [o for o in res if 'skip' not in o and o.get('img_ok') and cap.inl.get(o['i'], 1) and cap.inl.get(o['j'], 1)]
        print('  image testimony valid (cv & colmap agree, CALIBRATED): %d / %d pairs' % (sum(1 for o in res if o.get('img_ok')), sum(1 for o in res if 'skip' not in o)))
        for k in ('c_dir_dev', 'c_dir_rec', 'c_rot_dev', 'c_rot_rec'):
            v = np.array([o[k] for o in good])
            if len(v): print('  [inlier-only pairs n=%d] %s median %.2f p90 %.2f' % (len(v), k, np.median(v), np.percentile(v, 90)))
