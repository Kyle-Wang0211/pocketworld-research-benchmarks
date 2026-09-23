#!/usr/bin/python3
# make_subset_feeds.py <name> <first_frame> <step> : feeds for arms A / Xhost / Xdev640sweep on
# frames first, first+step, ... (all must have ARKit, both XRSLAM poses and a clean-COLMAP pose).
# Same conventions as prep_inputs.py (ARKit c2w -> CamFromWorld; XRSLAM T_WC = T_WB*T_BC etc.).
# Added 09-23 (takeover): start after ARKit leaves 'limited/initializing' (frames 2..73 of this
# recording carry zero translation; diagnostics.json tracking_limited_initializing=71), because the
# capture governor skips non-tracking frames (pocketworld feat/dense-stage
# lib/official_capture/auto_capture_governor.dart:253).
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P
name, first, step = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
ts = np.array([int(l.split(',')[0]) for l in list(open(P.REC + '/camera_index.csv'))[1:]]) * 1e-9
Kt, Kv = [], []
for ln in open(P.REC + '/intrinsics.jsonl'):
    j = json.loads(ln); Kt.append(j['t']); Kv.append(j['intrinsics_fxfycxcy'])
Kt = np.array(Kt)
def K(i):
    j = int(np.argmin(np.abs(Kt - ts[i]))); assert abs(Kt[j] - ts[i]) < 1e-6; return Kv[j]
A = {}
for r in P.load_tum(P.REC + '/arkit_poses.tum'):
    i = int(np.argmin(np.abs(ts - r[0])))
    if abs(ts[i] - r[0]) < 1e-6 and not (np.allclose(r[1:4], 0) and np.allclose(r[4:8], [0, 0, 0, 1])):
        A[i] = (P.q2R(r[7], r[4], r[5], r[6]), r[1:4])
def xr(path, td):
    d = {}
    for r in P.load_tum(path):
        tt = r[0] - td; i = int(np.argmin(np.abs(ts - tt)))
        if abs(tt - ts[i]) < 0.5e-3:
            Rwb = P.q2R(r[7], r[4], r[5], r[6])
            d[i] = (P.M_ZUP_TO_YUP @ Rwb @ P.R_BC @ P.F, P.M_ZUP_TO_YUP @ (r[1:4] + Rwb @ P.P_BC))
    return d
SRC = {'A': A, 'Xhost': xr(P.XR_SOURCES['xhost'][0], 0.008),
       'Xdev640sweep': xr(P.REC + '/replay/sweep_xrslam_640.tum', 0.0)}
col = set()
for l in [l for l in open(P.COLMAP_REF) if not l.startswith('#')][0::2]:
    col.add(int(l.split()[9][1:6]))
common = set.intersection(set(SRC['A']), set(SRC['Xhost']), set(SRC['Xdev640sweep']), col)
frames = [i for i in range(first, len(ts), step) if i in common]
for arm, src in SRC.items():
    with open(f'{P.OUT}/feed_{name}_{arm}.jsonl', 'w') as fo:
        for i in frames:
            R_wc, C = src[i]; Rw2c = R_wc.T
            fo.write(json.dumps({'frameIndex': i, 'byteOffset': i * P.FRAME_BYTES, 'w': P.W, 'h': P.H,
                                 'fxfycxcy': K(i), 'arkitCamFromWorldQwxyz': P.R2q(Rw2c).tolist(),
                                 'arkitCamFromWorldTxyz': (-Rw2c @ C).tolist()}) + '\n')
print(name, len(frames), frames[:3], '...', frames[-1])
