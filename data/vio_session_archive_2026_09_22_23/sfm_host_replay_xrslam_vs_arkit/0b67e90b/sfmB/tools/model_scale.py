#!/usr/bin/python3
# model_scale.py <feed.jsonl> <model_dir>... : Sim3(model camera centres -> feed prior centres)
# per COLMAP model dir (images.bin). image name frame_%06d.jpg == feed row order (fid).
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import prep_inputs as P, colmap_bin as CB
feed = [json.loads(l) for l in open(sys.argv[1])]
def prior_C(f):
    R = P.q2R(*f['arkitCamFromWorldQwxyz']); return -R.T @ np.array(f['arkitCamFromWorldTxyz'])
def centres(d):
    im = CB.read_images_bin(d + '/images.bin'); out = {}
    for iid, (q, t, nm) in im.items():
        k = int(''.join(c for c in nm if c.isdigit())); R = P.q2R(*q); out[k] = -R.T @ t
    return out
if __name__ == '__main__':
    for d in sys.argv[2:]:
        C = centres(d); ks = sorted(k for k in C if k < len(feed))
        if len(ks) < 3: print(f'{d}: n={len(ks)} (<3)'); continue
        D = np.array([C[k] for k in ks]).T; Pc = np.array([prior_C(feed[k]) for k in ks]).T
        s, R, t = P.umeyama(D, Pc); e = np.linalg.norm(s * R @ D + t - Pc, axis=0)
        print(f'{os.path.relpath(d)}: n={len(ks)} model/prior scale={1/s:.4f} rmse_prior_m={np.sqrt((e**2).mean()):.4f}')
