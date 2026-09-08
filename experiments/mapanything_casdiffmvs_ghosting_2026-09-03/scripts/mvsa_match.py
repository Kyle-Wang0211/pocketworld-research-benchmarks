#!/usr/bin/env python3
"""Recover the frame_id -> our image index mapping by MATCHING POSES, not by guessing the naming."""
import glob, os, pickle, numpy as np
SRC  = "/root/mvsa_out2/mvsanywhere/colmap/dense_offline/depths/scene0:0"
POSE = "/root/regionmerge/sfm768/pose"

ours = {}
for f in sorted(glob.glob(f"{POSE}/*.txt")):
    ours[int(os.path.basename(f)[:8])] = np.loadtxt(f).astype(np.float64)
idxs = sorted(ours)
print("our poses:", len(idxs))

def dist(A, B):
    Rr = A[:3, :3].T @ B[:3, :3]
    ang = np.degrees(np.arccos(np.clip((np.trace(Rr) - 1) / 2, -1, 1)))
    return float(ang) + 100.0 * float(np.linalg.norm(A[:3, 3] - B[:3, 3]))

rows = []
for f in sorted(glob.glob(f"{SRC}/*.pickle")):
    d = pickle.load(open(f, "rb"))
    fid = int(str(d["frame_id"]))
    E = d["cam_T_world_b44"].squeeze().float().cpu().numpy().astype(np.float64)
    ds = [(dist(ours[i], E), i) for i in idxs]
    ds.sort()
    rows.append((fid, ds[0][1], ds[0][0], ds[1][0]))

rows.sort()
best = np.array([r[2] for r in rows]); second = np.array([r[3] for r in rows])
tgt = [r[1] for r in rows]
print(f"best-match residual: max {best.max():.6f}  (2nd-best min {second.min():.4f})")
print(f"bijection: {len(set(tgt))} distinct targets for {len(tgt)} frames")
offs = sorted({r[0] - r[1] for r in rows})
print("frame_id - image_index offsets present:", offs[:8], "..." if len(offs) > 8 else "")
print("first 10 (frame_id -> image):", [(r[0], r[1]) for r in rows[:10]])
np.save("/root/regionmerge/mvsa_fid2idx.npy", np.array([[r[0], r[1]] for r in rows], dtype=np.int64))
print("saved /root/regionmerge/mvsa_fid2idx.npy")
