# -*- coding: utf-8 -*-
"""Resolution census over /root/monotrain. Read-only."""
import os, re, sys, random, struct, json
import numpy as np
from PIL import Image

ROOT = "/root/monotrain"
HEX24 = re.compile(r"^[0-9a-f]{24}$")
RULES = [("sp_", "sp_SimpleProc"), ("ta_", "ta_TartanAir"), ("tg_", "tg_TartanGround"),
         ("gso_", "gso_GSO"), ("ak_", "ak_ARKitScenes")]

def dom(s):
    for p, n in RULES:
        if s.startswith(p):
            return n
    if HEX24.match(s):
        return "hex_BlendedMVG"
    return None

def pfm_header(path):
    with open(path, "rb") as f:
        t = f.readline().rstrip()
        dims = f.readline()
        while dims.strip().startswith(b"#"):
            dims = f.readline()
        w, h = map(int, dims.split())
        return w, h, t

def read_pfm(path):
    with open(path, "rb") as f:
        t = f.readline().rstrip()
        color = (t == b"PF")
        dims = f.readline()
        while dims.strip().startswith(b"#"):
            dims = f.readline()
        w, h = map(int, dims.split())
        scale = float(f.readline().rstrip())
        end = "<" if scale < 0 else ">"
        data = np.frombuffer(f.read(w*h*(3 if color else 1)*4), dtype=end+"f")
        data = data.reshape((h, w, 3) if color else (h, w))
        return np.flipud(data).copy()

def block_const_k(a):
    """largest k>1 dividing H and W such that every kxk block is exactly constant"""
    H, W = a.shape
    best = 1
    for k in range(2, 33):
        if H % k or W % k:
            continue
        b = a.reshape(H//k, k, W//k, k)
        mn = b.min(axis=(1,3)); mx = b.max(axis=(1,3))
        if np.array_equal(mn, mx):
            best = k
    return best

def dup_frac(a):
    H, W = a.shape
    col = float(np.mean(a[:, 1:] == a[:, :-1]))
    row = float(np.mean(a[1:, :] == a[:-1, :]))
    return col, row

scans = sorted(os.listdir(ROOT))
buckets = {}
for s in scans:
    d = dom(s)
    if d is None:
        buckets.setdefault("UNKNOWN", []).append(s)
    else:
        buckets.setdefault(d, []).append(s)

rng = random.Random(0)
N_HDR = int(sys.argv[1]) if len(sys.argv) > 1 else 60
N_FULL = int(sys.argv[2]) if len(sys.argv) > 2 else 12
out = {}
for d in sorted(buckets):
    ss = buckets[d]
    if d == "UNKNOWN":
        out[d] = {"n_scenes": len(ss), "examples": ss[:10]}
        continue
    samp = rng.sample(ss, min(N_HDR, len(ss)))
    imgdims, depdims, nviews = {}, {}, []
    bad = []
    for s in samp:
        idir = os.path.join(ROOT, s, "blended_images")
        ddir = os.path.join(ROOT, s, "rendered_depth_maps")
        try:
            ims = sorted(os.listdir(idir))
        except Exception as e:
            bad.append((s, str(e))); continue
        nviews.append(len(ims))
        pick = ims if len(ims) <= 3 else [ims[0], ims[len(ims)//2], ims[-1]]
        for f in pick:
            try:
                with Image.open(os.path.join(idir, f)) as im:
                    imgdims[im.size] = imgdims.get(im.size, 0) + 1
            except Exception as e:
                bad.append((s+"/"+f, str(e)))
            p = os.path.join(ddir, f.replace(".jpg", ".pfm"))
            try:
                w, h, t = pfm_header(p)
                depdims[(w, h, t.decode())] = depdims.get((w, h, t.decode()), 0) + 1
            except Exception as e:
                bad.append((s+"/"+f+".pfm", str(e)))
    # full-read NN test
    nn = []
    for s in rng.sample(ss, min(N_FULL, len(ss))):
        ddir = os.path.join(ROOT, s, "rendered_depth_maps")
        try:
            ds = sorted(os.listdir(ddir))
        except Exception:
            continue
        for f in (ds[:1] + ds[len(ds)//2:len(ds)//2+1]):
            try:
                a = read_pfm(os.path.join(ddir, f))
            except Exception as e:
                bad.append((s+"/"+f, str(e))); continue
            if a.ndim != 2:
                continue
            k = block_const_k(a)
            c, r = dup_frac(a)
            nn.append({"scan": s, "view": f, "shape": list(a.shape), "block_k": k,
                       "dup_col": round(c,4), "dup_row": round(r,4),
                       "n_unique": int(np.unique(a).size),
                       "min": float(np.nanmin(a)), "max": float(np.nanmax(a)),
                       "n_zero": int((a==0).sum()), "n_nan": int(np.isnan(a).sum())})
    out[d] = {"n_scenes": len(ss), "sampled_scenes": len(samp),
              "img_dims": {str(k): v for k, v in imgdims.items()},
              "depth_dims": {str(k): v for k, v in depdims.items()},
              "views_per_scene_min_max": [min(nviews), max(nviews)] if nviews else None,
              "views_per_scene_mean": round(float(np.mean(nviews)),1) if nviews else None,
              "nn_test": nn, "errors": bad[:10]}
print(json.dumps(out, indent=1))
