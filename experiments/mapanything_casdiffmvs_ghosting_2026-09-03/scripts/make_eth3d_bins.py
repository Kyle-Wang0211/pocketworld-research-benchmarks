#!/usr/bin/env python3.11
"""ETH3D office positive control: official CasDiffMVS clouds (08-24 chain) + laser GT, same bin convention as ply2bin.py
(x,-y,-z baked; meta n/center(1-99%)/ext/med/radius=p95 dist to med)."""
import json, re, sys, numpy as np
from plyfile import PlyData
from pathlib import Path
E = Path.home()/"Developer/ethd3d_a_line"
OUT = Path("/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/pose_ablation_20260818/verdict_page/eth3d_office_20260907/bin")
OUT.mkdir(parents=True, exist_ok=True)
meta = {}
def emit(tag, pos, col):
    pos = pos.astype("<f4"); pos[:,1] *= -1; pos[:,2] *= -1
    pos = np.ascontiguousarray(pos); col = np.ascontiguousarray(col.astype(np.uint8))
    pos.tofile(OUT/f"{tag}.pos"); col.tofile(OUT/f"{tag}.col")
    lo, hi = np.percentile(pos, 1, 0), np.percentile(pos, 99, 0); med = np.median(pos, 0)
    rad = float(np.percentile(np.linalg.norm(pos - med, axis=1), 95))
    meta[tag] = {"n": int(len(pos)), "center": ((lo+hi)/2).tolist(), "ext": (hi-lo).tolist(), "med": med.astype(float).tolist(), "radius": rad}
    print(tag, len(pos), "med", np.round(med,3).tolist(), "radius", round(rad,3), flush=True)
    return pos
def load_xyz_rgb(p):
    v = PlyData.read(str(p))["vertex"].data
    xyz = np.stack([v["x"], v["y"], v["z"]], 1).astype(np.float64)
    rgb = np.stack([v["red"], v["green"], v["blue"]], 1) if "red" in v.dtype.names else None
    return xyz, rgb
# 1. dense clouds
d_blend, c_blend = load_xyz_rgb(E/"run_20260824/dense_blendmvg.ply"); P_blend = emit("cas_blendmvg", d_blend, c_blend)
d_new, c_new = load_xyz_rgb(E/"run_20260824/dense_new.ply"); emit("cas_mvgzerodtu", d_new, c_new)
# 2. GT scans with MeshLab alignment matrices
mlp = (E/"data/office/dslr_scan_eval/scan_alignment.mlp").read_text()
mats = {}
for m in re.finditer(r'filename="(scan\d\.ply)">\s*<MLMatrix44>\s*([^<]+)</MLMatrix44>', mlp):
    mats[m.group(1)] = np.array([float(x) for x in m.group(2).split()]).reshape(4,4)
gts = []
for name, M in mats.items():
    xyz, _ = load_xyz_rgb(E/"data/office/dslr_scan_eval"/name)
    xyz = xyz @ M[:3,:3].T + M[:3,3]
    gts.append(xyz); print(name, len(xyz), "M diag", np.round(np.diag(M),3).tolist(), flush=True)
G = np.concatenate(gts, 0)
# alignment sanity: NN distance from dense sample to GT (KD-tree on a GT subsample)
from scipy.spatial import cKDTree
rng = np.random.default_rng(0)
gsub = G[rng.choice(len(G), 3_000_000, replace=False)]
tree = cKDTree(gsub)
dsub = d_blend[rng.choice(len(d_blend), 100_000, replace=False)]
dist, _ = tree.query(dsub, k=1)
print("alignment check: dense->GT(3M subsample) NN dist median %.4f m  p90 %.4f m  (transform applied)" % (np.median(dist), np.percentile(dist, 90)), flush=True)
# untransformed control
gsub0 = np.concatenate([load_xyz_rgb(E/"data/office/dslr_scan_eval"/n)[0] for n in mats])[::12]
dist0, _ = cKDTree(gsub0).query(dsub, k=1)
print("control without transform: median %.4f m" % np.median(dist0), flush=True)
# colour GT by height (viewer y = -y): light grey gradient so walls/objects read as surfaces
h = -G[:,1]; lo, hi = np.percentile(h, 2), np.percentile(h, 98); t = np.clip((h-lo)/(hi-lo+1e-9), 0, 1)
col = np.stack([120+100*t, 130+100*t, 150+90*t], 1)
emit("gt_scan", G, col)
json.dump(meta, open(OUT/"meta.json", "w"), indent=1)
print("meta written")
