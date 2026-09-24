#!/usr/bin/python3
"""Like twoview_check.py, but the correspondences come from a FRESH OpenCV SIFT extraction on the capture's own JPEGs
(cv2.SIFT_create, half resolution 2016x1512, K scaled 0.5; BFMatcher L2 k=2, Lowe ratio 0.8 + mutual check), i.e.
independent of the phone-side features/matches. Poses: pycolmap.estimate_calibrated_two_view_geometry + cv2 5-point."""
import json, os, sys
import numpy as np, cv2, pycolmap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import twoview_check as T
cap = T.Cap(sys.argv[1]); prs = [tuple(int(v) for v in s.split(',')) for s in sys.argv[2:]]
d = T.PG[cap.cap]['dir']; S = 0.5; cache = {}
sift = cv2.SIFT_create(nfeatures=8000)
def feat(f):
    if f not in cache:
        jp = T.ok(d + '/photos_highres/' + os.path.basename(cap.fed[f]['jpegPath']))
        g = cv2.resize(cv2.imread(jp, cv2.IMREAD_GRAYSCALE), None, fx=S, fy=S, interpolation=cv2.INTER_AREA)
        kp, de = sift.detectAndCompute(g, None); cache[f] = (np.array([k.pt for k in kp], np.float64) + 0.5, de)
    return cache[f]
def matches(a, b):
    (pa, da), (pb, db) = feat(a), feat(b); bf = cv2.BFMatcher(cv2.NORM_L2)
    m1 = bf.knnMatch(da, db, k=2); m2 = bf.knnMatch(db, da, k=1)
    back = {m[0].queryIdx: m[0].trainIdx for m in m2}
    return np.array([(x.queryIdx, x.trainIdx) for x, y in m1 if x.distance < 0.8 * y.distance and back.get(x.trainIdx) == x.queryIdx], np.int64).reshape(-1, 2)
for i, j in prs:
    m = matches(i, j)
    (pa, _), (pb, _) = feat(i), feat(j)
    ki = cap.K[cap.img[i][1]] * S; kj = cap.K[cap.img[j][1]] * S
    c1 = pycolmap.Camera(model='PINHOLE', width=2016, height=1512, params=list(ki[:4])); c2 = pycolmap.Camera(model='PINHOLE', width=2016, height=1512, params=list(kj[:4]))
    o = pycolmap.TwoViewGeometryOptions(); o.compute_relative_pose = True; o.ransac.random_seed = 20260924
    g = pycolmap.estimate_calibrated_two_view_geometry(c1, pa, c2, pb, m.astype(np.uint32), o) if len(m) >= 15 else None
    (Rri, tri), (Rdi, tdi) = cap.pairs[i]; (Rrj, trj), (Rdj, tdj) = cap.pairs[j]
    Rr, tr = T.rel(Rri, tri, Rrj, trj); Rd, td = T.rel(Rdi, tdi, Rdj, tdj)
    cfg = {int(v): k for k, v in pycolmap.TwoViewGeometryConfiguration.__members__.items()}.get(int(g.config)) if g is not None else 'NONE'
    if g is None or cfg != 'CALIBRATED':
        print('  %3d->%3d fresh-SIFT mutual=%4d  COLMAP %s (no calibrated pose)' % (i, j, len(m), cfg)); continue
    Rc = np.asarray(g.cam2_from_cam1.rotation.matrix()); tc = np.asarray(g.cam2_from_cam1.translation).ravel()
    print('  %3d%s->%3d%s fresh-SIFT mutual=%4d COLMAP inl=%4d | rot dev/rec %5.2f/%5.2f  dir dev/rec %6.1f/%6.1f  (dev-rec dir %5.1f)' % (
        i, '*' if not cap.inl.get(i, 1) else ' ', j, '*' if not cap.inl.get(j, 1) else ' ', len(m), len(g.inlier_matches),
        T.ang(Rd @ Rc.T), T.ang(Rr @ Rc.T), T.dang(td, tc), T.dang(tr, tc), T.dang(td, tr)))
