#!/usr/bin/python3
# Negative control for the A/B itself: the SAME XRSLAM trajectory with the
# z-up -> y-up world rotation deliberately omitted (ate.py:156-161 says the two
# conventions differ by 90 deg). Positions/relative motion are untouched; only
# the gravity direction the core derives (mandatory_arkit_gravity_v1.cc:75-77)
# becomes ~90 deg wrong. If the gravity-dependent steps did not bite, this arm
# would look like arm X — so it tests whether the A/B can fail at all.
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P
sub = sys.argv[1]
good = [json.loads(l) for l in open(f'{P.OUT}/feed_{sub}_Xhost.jsonl')]
tr = P.load_tum(P.XR_SOURCES['xhost'][0])
ts = np.array([int(l.split(',')[0]) for l in list(open(P.REC + '/camera_index.csv'))[1:]]) * 1e-9
byi = {}
for r in tr:
    i = int(np.argmin(np.abs(ts - (r[0] - 0.008))))
    byi[i] = r
with open(f'{P.OUT}/feed_{sub}_XnoWorldRot.jsonl', 'w') as fo:
    for g in good:
        r = byi[g['frameIndex']]
        Rwb = P.q2R(r[7], r[4], r[5], r[6])
        Rwc = Rwb @ P.R_BC @ P.F          # world left z-up (WRONG on purpose)
        C = r[1:4] + Rwb @ P.P_BC
        Rw2c = Rwc.T; t = -Rw2c @ C
        g2 = dict(g); g2['arkitCamFromWorldQwxyz'] = P.R2q(Rw2c).tolist(); g2['arkitCamFromWorldTxyz'] = t.tolist()
        fo.write(json.dumps(g2) + '\n')
print('ok', len(good))
