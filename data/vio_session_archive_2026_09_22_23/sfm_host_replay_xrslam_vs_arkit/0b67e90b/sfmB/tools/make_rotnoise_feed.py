#!/usr/bin/python3
# Negative control #2 (my own design, NOT a product convention): the arm-X feed
# with an independent random attitude error per frame (axis uniform on S^2,
# angle ~ |N(0, sigma)|, seed fixed), camera centres unchanged. The core's
# upright-3pt TVG and the BA attitude anchor both consume per-frame attitude,
# so if they matter the metrics must degrade.
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P
sub, sigma_deg = sys.argv[1], float(sys.argv[2])
rng = np.random.default_rng(20260923)
out = f'{P.OUT}/feed_{sub}_Xrot{int(sigma_deg)}.jsonl'
with open(out, 'w') as fo:
    for l in open(f'{P.OUT}/feed_{sub}_Xhost.jsonl'):
        g = json.loads(l)
        R = P.q2R(*g['arkitCamFromWorldQwxyz']); t = np.array(g['arkitCamFromWorldTxyz'])
        C = -R.T @ t
        ax = rng.normal(size=3); ax /= np.linalg.norm(ax)
        ang = np.radians(abs(rng.normal(0, sigma_deg)))
        K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
        dR = np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K
        R2 = dR @ R; t2 = -R2 @ C
        g['arkitCamFromWorldQwxyz'] = P.R2q(R2).tolist(); g['arkitCamFromWorldTxyz'] = t2.tolist()
        fo.write(json.dumps(g) + '\n')
print(out)
