#!/usr/bin/env python3
"""CasDiffMVS depths -> AliceVision depth-map folder (the native fuseCut input, what Meshroom/RealityScan use).

Two conversions that are easy to get wrong and are done explicitly here:
  * AliceVision depth = EUCLIDEAN distance from the camera centre along the ray (its own code reconstructs
    p = C + normalize(iCam * pix) * depth), while CasDiffMVS/MVSNet store planar Z. dist = Z * |K^-1 [u,v,1]|.
  * invalid pixels must be <= 0 (AliceVision treats non-positive depth as no data). We zero everything outside the
    OFFICIAL final mask, so fuseCut is fed exactly the gated depths the user has been looking at.
simMap carries the photometric score; AliceVision's convention is "lower is better" in [-1, 1], so sim = -conf.

  write_av_depthmaps.py <out_official> <sfm_poses.sfm> <out_dir>
"""
import sys, json, glob, os, numpy as np, cv2, OpenEXR
SRC, SFM, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
d = json.load(open(SFM))
vid_of_name = {v["path"].rsplit("/", 1)[-1]: v["viewId"] for v in d["views"]}
def read_pfm(p):
    with open(p, "rb") as f:
        f.readline(); w, h = map(int, f.readline().split()); s = float(f.readline())
        a = np.fromfile(f, "<f4" if s < 0 else ">f4").reshape(h, w)
    return np.flipud(a).astype(np.float32)
def read_cam(p):
    L = [l.rstrip() for l in open(p)]
    return (np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4, 4),
            np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3, 3))
n = 0
for p in sorted(glob.glob(f"{SRC}/cams/*_cam.txt")):
    i = int(os.path.basename(p)[:8]); vid = vid_of_name[f"{i:08d}.jpg"]
    E, K = read_cam(p)
    Z = read_pfm(f"{SRC}/depth_est/{i:08d}.pfm")
    mask = cv2.imread(f"{SRC}/mask/{i:08d}_final.png", cv2.IMREAD_GRAYSCALE) > 0
    c0 = read_pfm(f"{SRC}/conf0/{i:08d}.pfm"); c1 = read_pfm(f"{SRC}/conf1/{i:08d}.pfm"); c2 = read_pfm(f"{SRC}/conf2/{i:08d}.pfm")
    h, w = Z.shape
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    ray = np.sqrt(((u - K[0, 2]) / K[0, 0]) ** 2 + ((v - K[1, 2]) / K[1, 1]) ** 2 + 1.0)   # |K^-1 [u,v,1]|
    depth = np.where(mask & (Z > 0), Z * ray, -1.0).astype(np.float32)
    sim = np.where(mask & (Z > 0), -(np.minimum(np.minimum(c0, c1), c2)), 1.0).astype(np.float32)
    valid = depth > 0
    hdr = {"compression": OpenEXR.ZIP_COMPRESSION, "AliceVision:downscale": 1,
           "AliceVision:minDepth": float(depth[valid].min()), "AliceVision:maxDepth": float(depth[valid].max()),
           "AliceVision:nbDepthValues": int(valid.sum())}
    OpenEXR.File({"Y": depth}, hdr).write(f"{OUT}/{vid}_depthMap.exr")
    OpenEXR.File({"Y": sim}, {"compression": OpenEXR.ZIP_COMPRESSION, "AliceVision:downscale": 1}).write(f"{OUT}/{vid}_simMap.exr")
    n += 1
    if n % 40 == 0: print(" ", n, flush=True)
print("wrote", n, "depth/sim map pairs to", OUT, flush=True)
