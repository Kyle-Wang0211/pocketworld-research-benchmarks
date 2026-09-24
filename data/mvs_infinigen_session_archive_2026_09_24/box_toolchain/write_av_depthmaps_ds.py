#!/usr/bin/env python3
"""CasDiffMVS official outputs (depth_est / mask/*_final.png / conf0-2 / cams at INFERENCE resolution) -> AliceVision
depth+sim EXRs, with AliceVision:downscale = DS relative to the SfMData image size (official DepthMap writes downscale 2).
Depth = Euclidean ray distance (AliceVision convention), invalid <= 0, sim = -min(conf) (lower is better).
Set MASK=0 to keep EVERY network depth (official-faithful): the Meshroom chain's only depth filter is
DepthMapFilter, so pre-applying CasDiffMVS's own geometric-consistency mask inserts a step the official pipeline
does not have -- and it deletes exactly the low-texture pixels the weakly-supported-surface vote needs evidence for.
  write_av_depthmaps_ds.py <out_native> <scene.sfm> <out_dir> <DS> [MASK=1]"""
import sys, json, glob, os, numpy as np, cv2, OpenEXR
SRC, SFM, OUT, DS = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
MASK = int(sys.argv[5]) if len(sys.argv) > 5 else 1
os.makedirs(OUT, exist_ok=True)
d = json.load(open(SFM)); vid_of_name = {v["path"].rsplit("/", 1)[-1]: v["viewId"] for v in d["views"]}
W0 = {v["viewId"]: (int(v["width"]), int(v["height"])) for v in d["views"]}
def read_pfm(p):
    with open(p, "rb") as f:
        f.readline(); w, h = map(int, f.readline().split()); s = float(f.readline())
        a = np.fromfile(f, "<f4" if s < 0 else ">f4").reshape(h, w)
    return np.flipud(a).astype(np.float32)
def read_cam(p):
    L = [l.rstrip() for l in open(p)]
    return np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3, 3)
n = 0
for p in sorted(glob.glob(f"{SRC}/cams/*_cam.txt")):
    i = int(os.path.basename(p)[:8]); vid = vid_of_name[f"{i:08d}.jpg"]; K = read_cam(p)
    Z = read_pfm(f"{SRC}/depth_est/{i:08d}.pfm"); h, w = Z.shape
    assert (w * DS, h * DS) == W0[vid], (w, h, DS, W0[vid])
    mask = (cv2.imread(f"{SRC}/mask/{i:08d}_final.png", cv2.IMREAD_GRAYSCALE) > 0) if MASK else np.ones(Z.shape, bool)
    c = np.minimum(np.minimum(read_pfm(f"{SRC}/conf0/{i:08d}.pfm"), read_pfm(f"{SRC}/conf1/{i:08d}.pfm")), read_pfm(f"{SRC}/conf2/{i:08d}.pfm"))
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    ray = np.sqrt(((u - K[0, 2]) / K[0, 0]) ** 2 + ((v - K[1, 2]) / K[1, 1]) ** 2 + 1.0)
    ok = mask & (Z > 0)
    depth = np.where(ok, Z * ray, -1.0).astype(np.float32); sim = np.where(ok, -c, 1.0).astype(np.float32)
    nv = int(ok.sum()); lo = float(depth[ok].min()) if nv else 0.0; hi = float(depth[ok].max()) if nv else 0.0
    if nv == 0: print("  WARNING view", i, "empty final mask", flush=True)
    OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "AliceVision:downscale": DS, "AliceVision:minDepth": lo,
                  "AliceVision:maxDepth": hi, "AliceVision:nbDepthValues": nv}, {"Y": depth}).write(f"{OUT}/{vid}_depthMap.exr")
    OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "AliceVision:downscale": DS}, {"Y": sim}).write(f"{OUT}/{vid}_simMap.exr")
    n += 1
print(f"wrote {n} depth/sim pairs ({w}x{h}, downscale {DS}, CasDiffMVS mask {'ON' if MASK else 'OFF'}) to {OUT}", flush=True)
