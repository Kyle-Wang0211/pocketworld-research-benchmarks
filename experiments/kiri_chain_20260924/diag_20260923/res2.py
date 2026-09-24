"""Depth maps actually fed to TSDF: size, K, median depth, pixel footprint; and what floor-vs-round pixel lookup changes."""
import numpy as np, json, glob
from replay_lib import *
L = np.load("labels4.npz")["labels"]
Ks = []; shapes = set(); zs = []; zreg = {c: [] for c in (1, 2, 3, 4)}; jump = {c: [0, 0] for c in (0, 1, 2, 3, 4)}
for rv, sv in PAIR_DATA:
    o = replay(rv, sv); K = o["K"]; Ks.append([K[0, 0], K[1, 1], K[0, 2], K[1, 2]]); shapes.add(o["d"].shape)
    f = o["final"]; d = np.where(f, o["davg"], 0.0); zs.append(d[f][::7])
    for c in zreg: zreg[c].append(d[f & (L[rv] == c)][::7])
    # floor(u) vs round(u): for u in [i+0.5, i+1) the kernel reads pixel i, round would read i+1 -> depth difference to the right/down neighbour
    dx = np.abs(d[:, 1:] - d[:, :-1]); vx = f[:, 1:] & f[:, :-1]; dy = np.abs(d[1:, :] - d[:-1, :]); vy = f[1:, :] & f[:-1, :]
    for c in jump:
        mx = vx & ((L[rv][:, 1:] == c) if c else True); my = vy & ((L[rv][1:, :] == c) if c else True)
        jump[c][0] += int(mx.sum() + my.sum()); jump[c][1] += int(((dx > 0.003) & mx).sum() + ((dy > 0.003) & my).sum())
Ks = np.array(Ks); z = np.concatenate(zs)
out = dict(depth_shape=sorted(shapes), fx=[float(Ks[:, 0].min()), float(Ks[:, 0].max())], fy=[float(Ks[:, 1].min()), float(Ks[:, 1].max())],
           cx=[float(Ks[:, 2].min()), float(Ks[:, 2].max())], cy=[float(Ks[:, 3].min()), float(Ks[:, 3].max())],
           median_depth_CD=float(np.median(z)), depth_p10_p90_CD=np.percentile(z, [10, 90]).tolist())
fx = float(np.median(Ks[:, 0])); s = 0.2664
out["footprint_at_median_CD_mm"] = 1000 * out["median_depth_CD"] / fx; out["footprint_at_median_AV_mm"] = out["footprint_at_median_CD_mm"] * s
out["median_depth_AV"] = out["median_depth_CD"] * s
names = {1: "fabric_wall", 2: "floor", 3: "suitcase", 4: "white_wall"}
for c, n in names.items():
    zz = np.concatenate(zreg[c]); out[f"{n}_median_depth_CD"] = float(np.median(zz)); out[f"{n}_footprint_CD_mm"] = 1000 * float(np.median(zz)) / fx
for c in jump: out[f"neighbour_depth_diff_gt_1voxel(3mmCD)_frac_{names.get(c, 'all')}"] = jump[c][1] / max(jump[c][0], 1)
# original image and K for comparison
Kf, _, _, _ = read_camera_parameters("/root/mvs_P16k/cams/00000000_cam.txt"); out["orig_K_view0"] = [float(Kf[0, 0]), float(Kf[1, 1]), float(Kf[0, 2]), float(Kf[1, 2])]
print(json.dumps(out, indent=1)); json.dump(out, open("res2.json", "w"), indent=1)
