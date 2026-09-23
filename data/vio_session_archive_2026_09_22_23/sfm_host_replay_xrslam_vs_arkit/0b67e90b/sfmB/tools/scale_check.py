#!/usr/bin/python3
# scale_check.py <runs_dir> <subset> <arm>... : absolute-scale bookkeeping.
# Reference metric = ARKit over the WHOLE run (1644 frames with every source),
# shape reference = clean COLMAP 4.1.1 model (no ARKit/XRSLAM input).
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P, analyze_ab as AB
RUNS, SUB = sys.argv[1], sys.argv[2]
AB.RUNS, AB.SUB = RUNS, SUB
ref = AB.colmap_ref_centers(None)
ark = P.load_tum(P.REC + '/arkit_poses.tum')
ts = np.array([int(l.split(',')[0]) for l in list(open(P.REC + '/camera_index.csv'))[1:]]) * 1e-9
A = {}
for r in ark:
    i = int(np.argmin(np.abs(ts - r[0])))
    if not np.allclose(r[1:4], 0): A[i] = r[1:4]
fr = sorted(set(A) & set(ref))
Cc = np.array([ref[i][1] for i in fr]).T; Ca = np.array([A[i] for i in fr]).T
s_ca, _, _, e = AB.sim3(Cc, Ca)
print(f'COLMAP->ARKit(full run, n={len(fr)}) scale={s_ca:.5f} m/unit rmse={np.sqrt((e**2).mean())*1000:.1f} mm')
xh = P.load_tum(P.XR_SOURCES['xhost'][0])
X = {}
for r in xh:
    i = int(np.argmin(np.abs(ts - (r[0] - 0.008))))
    Rwb = P.q2R(r[7], r[4], r[5], r[6]); X[i] = P.M_ZUP_TO_YUP @ (r[1:4] + Rwb @ P.P_BC)
fr2 = sorted(set(X) & set(ref))
s_cx, _, _, e2 = AB.sim3(np.array([ref[i][1] for i in fr2]).T, np.array([X[i] for i in fr2]).T)
print(f'COLMAP->XRSLAM(full run, n={len(fr2)}) scale={s_cx:.5f}  => XRSLAM/ARKit = {s_cx/s_ca:.4f}')
for arm in sys.argv[3:]:
    r = AB.load_run(arm)
    f = sorted(r['poses'])
    D = np.array([r['poses'][i][1] for i in f]).T
    s_cd, _, _, e3 = AB.sim3(np.array([ref[i][1] for i in f]).T, D)
    print(f'{SUB}_{arm}: delivered = {s_cd/s_ca:.4f} x ARKit-full-run metric '
          f'({s_cd/s_cx:.4f} x XRSLAM-full-run), n={len(f)}')
