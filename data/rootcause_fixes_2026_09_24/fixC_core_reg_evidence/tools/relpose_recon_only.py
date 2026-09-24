#!/usr/bin/python3
"""relpose_recon_only.py <run_dir> <feed> <cap> [--untrusted=..] — adds 'relpose_recon_only' to metrics.json:
pairs (consecutive + skip-one registered) where the delivered relative pose disagrees with the verified image two-view
geometry (dir > 20 deg or rot > 5 deg) while the DEVICE relative pose agrees with it (dir <= 20 and rot <= 5) — i.e. the
reconstruction, not the image estimate, is the odd one out. Pairs where device AND recon both disagree with the image
estimate are counted separately as image-estimate-suspect. Pairs touching untrusted frames use recon vs image only."""
import json, os, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); import prep_inputs as P
rd, feedf, cap = sys.argv[1:4]
untrusted = set()
for a in sys.argv[4:]:
    if a.startswith('--untrusted='):
        for tok in a.split('=', 1)[1].split(','):
            if '-' in tok: lo, hi = map(int, tok.split('-')); untrusted |= set(range(lo, hi + 1))
            elif tok: untrusted.add(int(tok))
feed = [json.loads(l) for l in open(feedf) if l.strip()]
cache = json.load(open(W + f'/results/twoview_cache_{cap}.json'))
def to_colmap(q, t):
    w, x, y, z = q; n = (w*w+x*x+y*y+z*z) ** .5; w, x, y, z = w/n, x/n, y/n, z/n
    return [-x, w, -z, y], [t[0], -t[1], -t[2]]
dl = {}
for l in open(rd + '/delivered_poses.txt'):
    v = l.split()
    if int(v[2]) == 1: dl[int(v[0])] = (list(map(float, v[3:7])), list(map(float, v[7:10])))
def rel(a, b): Ra, ta = P.q2R(*a[0]), np.array(a[1]); Rb, tb = P.q2R(*b[0]), np.array(b[1]); R = Rb @ Ra.T; return R, tb - R @ ta
def dang(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float('nan') if na < 1e-12 or nb < 1e-12 else float(np.degrees(np.arccos(np.clip(a @ b / na / nb, -1, 1))))
ks = sorted(dl); prs = [(ks[i], ks[i + 1]) for i in range(len(ks) - 1)] + [(ks[i], ks[i + 2]) for i in range(len(ks) - 2)]
n_valid = 0; recon_only = []; suspect = []; untrusted_bad = []
for a, b in prs:
    c = cache.get('%d,%d' % (feed[a]['frameIndex'], feed[b]['frameIndex']))
    if not c or not c['ok']: continue
    n_valid += 1
    Rc, tc = np.array(c['R_c']), np.array(c['t_c'])
    Rr, tr = rel(dl[a], dl[b]); rr, dr = P.ang(Rr, Rc), dang(tr, tc)
    bad_r = dr > 20 or rr > 5
    if a in untrusted or b in untrusted:
        if bad_r: untrusted_bad.append([a, b, round(rr, 2), round(dr, 1)])
        continue
    Rd, td = rel(to_colmap(feed[a]['arkitCamFromWorldQwxyz'], feed[a]['arkitCamFromWorldTxyz']), to_colmap(feed[b]['arkitCamFromWorldQwxyz'], feed[b]['arkitCamFromWorldTxyz']))
    rd_, dd_ = P.ang(Rd, Rc), dang(td, tc)
    bad_d = dd_ > 20 or rd_ > 5
    if bad_r and not bad_d: recon_only.append([a, b, round(rr, 2), round(dr, 1), round(rd_, 2), round(dd_, 1)])
    elif bad_r and bad_d: suspect.append([a, b, round(rr, 2), round(dr, 1), round(rd_, 2), round(dd_, 1)])
m = json.load(open(rd + '/metrics.json'))
m['relpose_recon_only'] = {'n_valid_pairs': n_valid, 'n_recon_only': len(recon_only), 'recon_only': recon_only,
                           'n_image_suspect': len(suspect), 'image_suspect': suspect, 'untrusted_pairs_bad': untrusted_bad}
json.dump(m, open(rd + '/metrics.json', 'w'), indent=1, default=float)
print(os.path.basename(rd), 'valid', n_valid, 'recon_only', len(recon_only), recon_only[:8], 'suspect', len(suspect), 'untrusted_bad', untrusted_bad)
