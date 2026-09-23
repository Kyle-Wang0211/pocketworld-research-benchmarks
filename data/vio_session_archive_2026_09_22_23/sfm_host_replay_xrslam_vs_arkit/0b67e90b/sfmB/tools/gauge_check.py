#!/usr/bin/python3
# gauge_check.py <feed.jsonl> <run_dir> : live_end vs delivered — is image 1 held fixed, what happens
# to the image1->image2 baseline, and the global scale change (Sim3 live->final over all cameras).
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P, colmap_bin as CB
feed = [json.loads(l) for l in open(sys.argv[1])]; d = sys.argv[2]
L = CB.read_images_bin(d + '/live/live_end/images.bin'); F = CB.read_images_bin(d + '/images.bin')
def C(M, i): q, t, _ = M[i]; R = P.q2R(*q); return -R.T @ t
def prior(k): f = feed[k]; R = P.q2R(*f['arkitCamFromWorldQwxyz']); return -R.T @ np.array(f['arkitCamFromWorldTxyz'])
same1 = np.array_equal(L[1][0], F[1][0]) and np.array_equal(L[1][1], F[1][1])
ids = sorted(set(L) & set(F))
XL = np.array([C(L, i) for i in ids]).T; XF = np.array([C(F, i) for i in ids]).T
s, R, t = P.umeyama(XL, XF)
bL = np.linalg.norm(C(L, 2) - C(L, 1)); bF = np.linalg.norm(C(F, 2) - C(F, 1)); bP = np.linalg.norm(prior(1) - prior(0))
print(f'{os.path.basename(d)}: image1 pose bit-identical live->final: {same1}; global Sim3 scale final/live = {s:.4f}')
print(f'   |C2-C1| prior={bP*1000:.1f} mm  live={bL*1000:.1f}  final={bF*1000:.1f}  (final/live={bF/bL:.3f});  '
      f'final |C2-C1| in live-metric units = {bF/s*1000:.1f} mm')
