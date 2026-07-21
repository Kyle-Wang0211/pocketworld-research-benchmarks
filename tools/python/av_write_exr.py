"""Rewrite the depth + sim EXRs for AliceVision with proper oiio-readable metadata
(AliceVision:downscale int attr) so the meshing's scale>0 assertion passes.
cv2 can't write typed attrs; modern OpenEXR(3.x) can. Reuses the export logic for
ray-distance depth + per-view K. Writes into the existing av_work/raw/depthMaps.
"""
import os, numpy as np, OpenEXR
from pathlib import Path
import pw_diffmvs_run as R

OUT = Path("av_work/raw/depthMaps")
CONF = 0.1
z = np.load(R.OUT / "p1cache_sfm_v8full.npz", allow_pickle=True)
frames = list(z["frames"])
depth = {n: z["depth"][i].astype(np.float32) for i, n in enumerate(frames)}
conf = {n: z["conf"][i].astype(np.float32) for i, n in enumerate(frames)}
man, _, _ = R._load_meta()
name2mi = {Path(f["jpegPath"]).name: i for i, f in enumerate(man)}


def build_kmap():
    _, wdef, _ = R._load_meta(); km = {}
    for win, wd in wdef.items():
        zz = np.load(R.EXPAC / "windows" / f"win_{win:02d}.npz")
        for j, mi in enumerate(wd["frame_idx"]):
            km.setdefault(mi, R.scaled_K(zz["K"][j]))
    return km


def parse_w2c(p):
    s = set(); L = [l for l in open(p) if not l.startswith("#") and l.strip()]
    for i in range(0, len(L), 2):
        t = L[i].split()
        if len(t) >= 10:
            s.add(t[9])
    return s


Kmap = build_kmap(); Kmed = np.median(np.stack(list(Kmap.values())), 0)
w2c = parse_w2c("sfm_cmp/sfm_v8/txt_glomap/images.txt")
names = [n for n in frames if n in w2c and n in name2mi]
H, W = 512, 896
for idx, n in enumerate(names):
    vid = 1000 + idx
    K = Kmap.get(name2mi[n], Kmed)
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    rayfac = np.sqrt(((uu - cx) / fx)**2 + ((vv - cy) / fy)**2 + 1.0).astype(np.float32)
    d = depth[n].copy(); d[conf[n] < CONF] = 0.0
    ray = (d * rayfac).astype(np.float32); ray[d <= 0] = 0.0
    nbval = int((ray > 0).sum())
    hdr = {"compression": OpenEXR.ZIP_COMPRESSION,
           "AliceVision:downscale": 1, "AliceVision:nbDepthValues": nbval}
    OpenEXR.File(hdr, {"Y": ray}).write(str(OUT / f"{vid}_depthMap.exr"))
    sim = (-conf[n]).astype(np.float32)
    OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "AliceVision:downscale": 1},
                 {"Y": sim}).write(str(OUT / f"{vid}_simMap.exr"))
    if idx % 100 == 0:
        print(f"  {idx}/{len(names)}", flush=True)
print(f"rewrote {len(names)} depth+sim EXRs with AliceVision:downscale=1 (int)")
