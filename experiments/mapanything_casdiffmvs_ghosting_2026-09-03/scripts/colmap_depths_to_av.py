#!/usr/bin/env python3
"""COLMAP PatchMatch geometric depth maps -> AliceVision native depth maps, so the classical depths can go through
the same fuseCut meshing that the CasDiffMVS depths went through. AliceVision depth = distance along the ray;
COLMAP stores planar Z."""
import sys, json, glob, os, numpy as np, OpenEXR
WS, SRC, SFM, OUT = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)
d = json.load(open(SFM)); vid_of = {v["path"].rsplit("/",1)[-1]: v["viewId"] for v in d["views"]}
def read_colmap_map(p):
    b = open(p, "rb").read(); i = 0; h = []
    for _ in range(3):
        j = b.index(b"&", i); h.append(int(b[i:j])); i = j + 1
    w, hh, c = h
    return np.frombuffer(b[i:], "<f4").reshape(c, hh, w)[0].astype(np.float32)
def read_cam(i):
    L = [l.rstrip() for l in open(f"{SRC}/cams/{i:08d}_cam.txt")]
    return np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3, 3)
n = 0
for f in sorted(glob.glob(f"{WS}/stereo/depth_maps/*.geometric.bin")):
    i = int(os.path.basename(f)[:8]); Z = read_colmap_map(f); h, w = Z.shape
    K = read_cam(i)
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    ray = np.sqrt(((u - K[0,2]) / K[0,0])**2 + ((v - K[1,2]) / K[1,1])**2 + 1.0)
    ok = Z > 0
    dist = np.where(ok, Z * ray, -1.0).astype(np.float32)
    nv = int(ok.sum()); lo = float(dist[ok].min()) if nv else 0.0; hi = float(dist[ok].max()) if nv else 0.0
    vid = vid_of[f"{i:08d}.jpg"]
    OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "AliceVision:downscale": 1,
                  "AliceVision:minDepth": lo, "AliceVision:maxDepth": hi, "AliceVision:nbDepthValues": nv},
                 {"Y": dist}).write(f"{OUT}/{vid}_depthMap.exr")
    OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "AliceVision:downscale": 1},
                 {"Y": np.where(ok, -1.0, 1.0).astype(np.float32)}).write(f"{OUT}/{vid}_simMap.exr")
    n += 1
print("wrote", n, "AliceVision map pairs from COLMAP PatchMatch depths", flush=True)
