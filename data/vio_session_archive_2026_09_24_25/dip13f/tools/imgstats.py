#!/usr/bin/env python3
"""dip13f: per-frame image statistics straight from frames.bin (same box/3 as the replay).
Writes <out>.npz with per-frame arrays. Usage: imgstats.py <run-dir> <out.npz> [--every N]"""
import sys, json, numpy as np, cv2
run, out = sys.argv[1], sys.argv[2]
every = int(sys.argv[sys.argv.index('--every')+1]) if '--every' in sys.argv else 1
man = json.load(open(run+'/recording_manifest.json')); W, H = man['camera']['width'], man['camera']['height']
off = {}
for ln in open(run+'/frames.pwvi'):
    if ln.strip():
        d = json.loads(ln); off[d['frame']] = d['offset']
rows = [l.strip().split(',') for l in open(run+'/camera_index.csv').readlines()[1:] if l.strip()]
mm = np.memmap(run+'/frames.bin', dtype=np.uint8, mode='r')
clahe = cv2.createCLAHE(clipLimit=6.0, tileGridSize=(8, 8))
gftt = cv2.GFTTDetector_create(300, 1e-3, 20, 3, True)
R = {k: [] for k in ['t', 'frame', 'mean', 'p5', 'p95', 'sat', 'grad', 'lowtex', 'lap640', 'lapfull', 'ncorner', 'cx3', 'cy3', 'ten_ctr']}
for i, (ts, fr) in enumerate(rows):
    if i % every: continue
    fr = int(fr)
    if fr not in off: continue
    full = np.asarray(mm[off[fr]:off[fr]+W*H]).reshape(H, W)
    img = full.reshape(H//3, 3, W//3, 3).astype(np.float64).mean(axis=(1, 3))
    img = np.rint(img).astype(np.uint8)
    f = img.astype(np.float32)
    gx = cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3)
    g = np.sqrt(gx*gx+gy*gy)/8.0  # per-pixel intensity gradient (grey levels / px)
    blk = g[:480, :640].reshape(15, 32, 20, 32).mean(axis=(1, 3))
    lap = cv2.Laplacian(f, cv2.CV_32F, ksize=1)
    # full-res Laplacian variance on a centre crop 960x720 (blur at native resolution)
    c = full[360:1080, 480:1440].astype(np.float32)
    lapf = cv2.Laplacian(c, cv2.CV_32F, ksize=1)
    ce = clahe.apply(img)
    kps = gftt.detect(ce)
    xs = np.array([k.pt[0] for k in kps]); ys = np.array([k.pt[1] for k in kps])
    ok = (xs >= 20) & (ys >= 20) & (xs < 620) & (ys < 460)
    xs, ys = xs[ok], ys[ok]
    R['t'].append(int(ts)*1e-9); R['frame'].append(fr)
    R['mean'].append(img.mean()); R['p5'].append(np.percentile(img, 5)); R['p95'].append(np.percentile(img, 95))
    R['sat'].append((img >= 250).mean())
    R['grad'].append(g.mean()); R['lowtex'].append((blk < 2.0).mean())
    R['lap640'].append(lap.var()); R['lapfull'].append(lapf.var())
    R['ncorner'].append(len(xs))
    R['cx3'].append(np.histogram(xs, bins=[0, 213, 427, 640])[0])
    R['cy3'].append(np.histogram(ys, bins=[0, 160, 320, 480])[0])
    R['ten_ctr'].append(blk[4:11, 6:14].mean())
np.savez(out, **{k: np.array(v) for k, v in R.items()})
print('frames', len(R['t']))
