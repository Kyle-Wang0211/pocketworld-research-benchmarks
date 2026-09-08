#!/usr/bin/env python3
"""MVSAnywhere cached depths -> the same per-view layout every other engine uses, then the SAME
official CasDiffMVS gate (>=3 views / 1px / 1%).

🔴 MVSAnywhere numbers frames by COLMAP image_id, NOT by filename: frame_id -> our image index is
an arbitrary permutation (4->6, 8->17, ...), not a shift. Two guesses (n, n-1) were both wrong; the
first export painted every point with another image's colour and compared each frame against
neighbours that were the wrong images. The table is now recovered by MATCHING POSES
(scripts/mvsa_match.py: best residual 0.022 vs 2nd-best 19.25, and a 132<->132 bijection) and is
re-verified per view here -- the run aborts if any view disagrees."""
import os, glob, pickle, sys
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from filter import check_geometric_consistency

SRC  = "/root/mvsa_out2/mvsanywhere/colmap/dense_offline/depths/scene0:0"
IMG  = "/root/community/dense/images"
POSE = "/root/regionmerge/sfm768/pose"          # our COLMAP world->cam per image index
OUT  = "/root/regionmerge/gated_mvsa"
for s in ("depth", "color", "cam"): os.makedirs(f"{OUT}/{s}", exist_ok=True)

FID2IDX = {int(a): int(b) for a, b in np.load("/root/regionmerge/mvsa_fid2idx.npy")}
raw = {}; ctl = []
for f in sorted(glob.glob(f"{SRC}/*.pickle")):
    d = pickle.load(open(f, "rb"))
    idx = FID2IDX[int(str(d["frame_id"]))]   # recovered by pose matching (mvsa_match.py), not guessed
    dep = d["depth_pred_s0_b1hw"].squeeze().float().cpu().numpy()
    msk = d["overall_mask_bhw"].squeeze().cpu().numpy().astype(np.uint8)
    if msk.shape != dep.shape:                              # cost-volume mask is at 1/4 resolution
        msk = cv2.resize(msk, (dep.shape[1], dep.shape[0]), interpolation=cv2.INTER_NEAREST)
    K = d["K_s0_b44"].squeeze().float().cpu().numpy()[:3, :3].astype(np.float64)
    E = d["cam_T_world_b44"].squeeze().float().cpu().numpy().astype(np.float64)
    # ---- positive control: does MVSAnywhere's pose for this frame equal OUR pose for image idx?
    Eo = np.loadtxt(f"{POSE}/{idx:08d}.txt").astype(np.float64)
    Rr = Eo[:3, :3].T @ E[:3, :3]
    ang = float(np.degrees(np.arccos(np.clip((np.trace(Rr) - 1) / 2, -1, 1))))
    dt = float(np.linalg.norm(Eo[:3, 3] - E[:3, 3]))
    ctl.append((idx, ang, dt))
    raw[idx] = (np.where(msk.astype(bool), dep, 0).astype(np.float32), K, E)

ang_max = max(c[1] for c in ctl); dt_max = max(c[2] for c in ctl)
print(f"POSITIVE CONTROL over {len(ctl)} views: max |dR| {ang_max:.6f} deg, max |dt| {dt_max:.6f} m", flush=True)
# 0.05 deg is float32 rounding on a rotation matrix stored in the pickle; the nearest
# WRONG frame sits at 19.25, so this gate still has a 385x margin.
assert ang_max < 0.05 and dt_max < 0.001, (
    f"frame_id -> image index mapping is WRONG (max dR {ang_max} deg, dt {dt_max} m). Aborting.")
print("mapping proven by pose match (see mvsa_match.py)", flush=True)
print("loaded", len(raw), "depths; shape", next(iter(raw.values()))[0].shape, flush=True)

lines = [l.strip() for l in open("/root/mvs_P16k/pair.txt") if l.strip()]
n = int(lines[0]); pairs = []; i = 1
for _ in range(n):
    ref = int(lines[i]); t = lines[i+1].split(); m = int(t[0])
    pairs.append((ref, [int(t[1+2*j]) for j in range(m)][:10])); i += 2

kept = []
for ref, srcs in pairs:
    if ref not in raw: continue
    dref, Kr, Er = raw[ref]
    gsum = 0; rsum = 0
    for s in srcs:
        if s not in raw: continue
        ds, Ks, Es = raw[s]
        gm, dr, _, _ = check_geometric_consistency(dref, Kr, Er, ds, Ks, Es, 30.0, 0.3, 1.0, 0.01)
        gsum = gsum + gm.astype(np.int32); rsum = rsum + dr
    davg = (rsum + dref) / (gsum + 1)
    keep = (gsum >= 3) & (dref > 0)
    kept.append(keep.mean())
    np.save(f"{OUT}/depth/{ref:08d}.npy", np.where(keep, davg, 0).astype(np.float32))
    img = cv2.imread(f"{IMG}/{ref:08d}.jpg")
    assert img is not None, f"missing image {ref:08d}.jpg"
    cv2.imwrite(f"{OUT}/color/{ref:08d}.png",
                cv2.resize(img, (dref.shape[1], dref.shape[0]), interpolation=cv2.INTER_AREA))
    np.savez(f"{OUT}/cam/{ref:08d}.npz", K=Kr, E=Er)
    if ref % 40 == 0: print(f"  ref {ref} keep {keep.mean():.3f}", flush=True)
print(f"DONE {len(kept)} views, keep mean {np.mean(kept):.3f}", flush=True)
