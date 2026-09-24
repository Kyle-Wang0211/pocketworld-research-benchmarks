#!/usr/bin/env python3
"""[PW-ENVELOPE] Task B data prep: per-pixel MATCHING ENVELOPE half-width, in SfM units.

Mechanism source (MicMac): DocMicMac/DocProg/MMCourse_day_4-5_matching.tex:219 -- ComputePx
creates a "matching envelope" constrained by aTEnvInf/aTEnvSup, a region in parallax space
exploited during matching; cASAMG.cpp:185-191 InterioriteEnvlop uses that quantity as the
"same surface" bandwidth. We do not invent a criterion: we take OUR matcher's own per-pixel
search interval and convert it to a metric half-width.

CasDiffMVS's own per-pixel search interval (verbatim, /root/diffmvs/models/module.py:263-268):
    radius       = ndepth // 2 * depth_inteval_pixel        # in NORMALIZED INVERSE DEPTH
    radius_min   = min_radius * radius
    radius_max   = max_radius * radius
    radius       = radius_min + (1 - confidence) * (radius_max - radius_min)
with (module.py:220-227 disp_to_depth) the normalized-inverse-depth -> metric Jacobian
    |d depth / d disp| = (1/depth_min - 1/depth_max) * depth^2

Inputs, all already on the box and all at EXACTLY the resolution/view set the meshing consumes:
  - conf : taken as -sim from <filt>/<viewId>_simMap.exr. /root/write_av_depthmaps_ds.py:29,35
           wrote sim = -min(conf0, conf1, conf2), so conf = -sim is exact, not a resample.
  - depth: <filt>/<viewId>_depthMap.exr. NOTE it is EUCLIDEAN RAY DISTANCE
           (write_av_depthmaps_ds.py:33 multiplies Z by the ray length), so we divide it back
           out to get the Z the network worked in.
  - depth_min/depth_max per view: last line of <testpath>/cams/<i>_cam.txt.
  - cascade constants: from the inference argv (numdepth=384, CostNum=[0,4,4],
    depth_interals_ratio=[4,2,1] default, min_radius=0.125, max_radius=8.0).

Output: <out>/<viewId>_envMap.exr, single channel "Y", float32, metric (SfM-unit) HALF-WIDTH
of the matcher's search interval at that pixel. <= 0 means "no envelope" (no depth there).
"""
import sys, os, json, glob
import numpy as np
import OpenEXR
import imageio.v2 as iio

FILT = sys.argv[1]          # /root/av_ep0_off/filt
SFM = sys.argv[2]           # /root/av_ep0_off/scene_dense.sfm
CAMS = sys.argv[3]          # /root/mvs_P16k/cams
OUT = sys.argv[4]           # /root/env_stage2
STAGE = int(sys.argv[5]) if len(sys.argv) > 5 else 2

# ---- cascade constants, from the inference argv (see /root/12mp.infer.log line 3) ----
NUMDEPTH = 384
COSTNUM = [0, 4, 4]
RATIO = [4, 2, 1]           # depth_interals_ratio default, /root/diffmvs/models/diffusion.py:15
MIN_RADIUS = 0.125
MAX_RADIUS = 8.0

os.makedirs(OUT, exist_ok=True)

d = json.load(open(SFM))
vid_of_name = {v["path"].rsplit("/", 1)[-1]: v["viewId"] for v in d["views"]}
W0 = {v["viewId"]: (int(v["width"]), int(v["height"])) for v in d["views"]}
I = d["intrinsics"][0]
IW, IH = int(I["width"]), int(I["height"])
F_FULL = float(I["focalLength"]) / float(I["sensorWidth"]) * IW
PP = [float(x) for x in I["principalPoint"]]


def cam_depth_range(p):
    L = [l.strip() for l in open(p) if l.strip()]
    vals = [float(x) for x in L[-1].split()]
    # input cams (colmap2mvsnet output) are written "<depth_min> ... <depth_max>";
    # datasets/mvs.py:87-88 reads [0] as min and [-1] as max.
    return vals[0], vals[-1]


base_disp = (COSTNUM[STAGE] // 2) * RATIO[STAGE] / float(NUMDEPTH)
print(f"[env] stage_idx={STAGE} ndepth={COSTNUM[STAGE]} ratio={RATIO[STAGE]} numdepth={NUMDEPTH}"
      f" -> base_disp={base_disp:.8f}; radius scale in [{MIN_RADIUS}, {MAX_RADIUS}]")

allq = []
n = 0
for camp in sorted(glob.glob(f"{CAMS}/*_cam.txt")):
    i = int(os.path.basename(camp)[:8])
    name = f"{i:08d}.jpg"
    if name not in vid_of_name:
        continue
    vid = vid_of_name[name]
    dpath = f"{FILT}/{vid}_depthMap.exr"
    spath = f"{FILT}/{vid}_simMap.exr"
    if not (os.path.exists(dpath) and os.path.exists(spath)):
        continue
    dmin, dmax = cam_depth_range(camp)

    depth_ray = np.asarray(iio.imread(dpath)).astype(np.float64)
    sim = np.asarray(iio.imread(spath)).astype(np.float64)
    h, w = depth_ray.shape
    assert sim.shape == depth_ray.shape

    # intrinsics rescaled from the SfM full-resolution intrinsic to this map's resolution
    s = w / float(IW)
    fx = F_FULL * s
    cx = (IW / 2.0 + PP[0]) * s
    cy = (IH / 2.0 + PP[1]) * s
    u, v = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    ray = np.sqrt(((u - cx) / fx) ** 2 + ((v - cy) / fx) ** 2 + 1.0)

    ok = depth_ray > 0
    Z = np.where(ok, depth_ray / ray, 0.0)          # back to the Z the network worked in
    conf = np.clip(-sim, 0.0, 1.0)                  # sim = -min(conf0,conf1,conf2)

    radius_disp = base_disp * (MIN_RADIUS + (1.0 - conf) * (MAX_RADIUS - MIN_RADIUS))
    jac = (1.0 / dmin - 1.0 / dmax) * (Z ** 2)      # |d depth / d disp|
    env = np.where(ok, radius_disp * jac, -1.0).astype(np.float32)

    OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION,
                  "AliceVision:downscale": 2,
                  "PW:envStage": STAGE},
                 {"Y": env}).write(f"{OUT}/{vid}_envMap.exr")
    if ok.any():
        allq.append(np.percentile(env[ok], [5, 25, 50, 75, 95]))
    n += 1
    if n % 40 == 0:
        print(f"  {n} views", flush=True)

q = np.mean(np.stack(allq), axis=0)
print(f"[env] wrote {n} envMaps to {OUT}")
print(f"[env] half-width (SfM units) mean-of-per-view percentiles "
      f"p5={q[0]:.6f} p25={q[1]:.6f} p50={q[2]:.6f} p75={q[3]:.6f} p95={q[4]:.6f}")
print(f"[env] same in mm at the 0.2664 SfM->m scale: "
      f"p5={q[0]*266.4:.2f} p25={q[1]*266.4:.2f} p50={q[2]*266.4:.2f} "
      f"p75={q[3]*266.4:.2f} p95={q[4]*266.4:.2f}")
