#!/usr/bin/python3
# render_scale.py : delivered camera paths in their OWN delivered units, rigidly (SE3, no scale)
# aligned to the ARKit path, top view — makes the finalize scale change visible.
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
B = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def deliv(d):
    o = {}
    for ln in open(f'{B}/runs/{d}/delivered_poses.txt'):
        f = ln.split(); R = P.q2R(*map(float, f[3:7])); t = np.array(list(map(float, f[7:10]))); o[int(f[0])] = -R.T @ t
    return o
def se3(X, Y):
    mx, my = X.mean(1, keepdims=True), Y.mean(1, keepdims=True)
    U, _, Vt = np.linalg.svd((Y - my) @ (X - mx).T); d = np.ones(3); d[2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ np.diag(d) @ Vt; return R, my - R @ mx
panels = {'S_prod': [('A', 'diag_S_prod_A'), ('Xhost', 'diag_S_prod_Xhost'), ('Xdev640sweep', 'diag_S_prod_Xdev640sweep')],
          'S_prod74': [('A', 'diag_S_prod74_A'), ('Xhost', 'diag_S_prod74_Xhost'), ('Xdev640sweep', 'diag_S_prod74_Xdev640sweep')],
          'S_deb74': [('A', 'diag_S_deb74_A'), ('Xhost', 'diag_S_deb74_Xhost')],
          'S_deb': [('A run1', 'S_deb_A'), ('A run2', 'diag_S_deb_A'), ('Xhost run1', 'S_deb_Xhost'), ('Xhost run2', 'diag_S_deb_Xhost'), ('Xdev640sweep', 'diag_S_deb_Xdev640sweep')]}
fig, ax = plt.subplots(2, 2, figsize=(16, 13), constrained_layout=True); ax = ax.ravel()
for j, (sub, arms) in enumerate(panels.items()):
    feed = [json.loads(l) for l in open(f'{P.OUT}/feed_{sub}_A.jsonl')]
    ark = np.array([-P.q2R(*f['arkitCamFromWorldQwxyz']).T @ np.array(f['arkitCamFromWorldTxyz']) for f in feed]).T
    ax[j].plot(ark[0], ark[2], 'k.-', lw=2, ms=3, label='ARKit prior (metres)')
    for lab, d in arms:
        D = deliv(d); ks = sorted(D); X = np.array([D[k] for k in ks]).T
        R, t = se3(X, ark[:, ks]); Y = R @ X + t
        s = P.umeyama(X, ark[:, ks])[0]
        ax[j].plot(Y[0], Y[2], '.-', lw=1, ms=2, label=f'{lab}: delivered, {1/s:.2f} units per ARKit m')
    ax[j].set_aspect('equal'); ax[j].legend(fontsize=8, loc='best'); ax[j].set_title(f'{sub}: delivered camera paths in their own units (rigid alignment only), top view x-z')
fig.savefig(f'{B}/runs/takeover_scale_paths.png', dpi=90); print('ok')
