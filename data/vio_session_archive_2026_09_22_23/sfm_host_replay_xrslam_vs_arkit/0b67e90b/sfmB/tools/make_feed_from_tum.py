#!/usr/bin/python3
# make_feed_from_tum.py <subset> <arm_name> <xrslam_tum> <td_s>
# Same frames / byteOffset / per-frame K as the existing arm-A feed of <subset>;
# only the pose fields are replaced by the given XRSLAM body trajectory, converted
# with EXACTLY the prep_inputs.py chain (T_WC = T_WB*T_BC, OpenCV->ARKit cam
# diag(1,-1,-1), z-up->y-up Rx90^T; citations in prep_inputs.py header).
# Added 09-23 (takeover session) for the on-device 640x480 XRSLAM replay.
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P
sub, arm, tum, td = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
ts = np.array([int(l.split(',')[0]) for l in list(open(P.REC + '/camera_index.csv'))[1:]]) * 1e-9
byi = {}
for r in P.load_tum(tum):
    tt = r[0] - td
    i = int(np.argmin(np.abs(ts - tt)))
    if abs(ts[i] - tt) < 0.5e-3:
        byi[i] = r
out = f'{P.OUT}/feed_{sub}_{arm}.jsonl'
n = 0
with open(out, 'w') as fo:
    for l in open(f'{P.OUT}/feed_{sub}_A.jsonl'):
        g = json.loads(l)
        r = byi[g['frameIndex']]          # KeyError = frame missing -> abort, never substitute
        Rwb = P.q2R(r[7], r[4], r[5], r[6])
        Rwc = P.M_ZUP_TO_YUP @ Rwb @ P.R_BC @ P.F
        C = P.M_ZUP_TO_YUP @ (r[1:4] + Rwb @ P.P_BC)
        Rw2c = Rwc.T
        g['arkitCamFromWorldQwxyz'] = P.R2q(Rw2c).tolist()
        g['arkitCamFromWorldTxyz'] = (-Rw2c @ C).tolist()
        fo.write(json.dumps(g) + '\n'); n += 1
print(out, n)
