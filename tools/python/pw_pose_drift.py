"""Pose-drift probe: per-frame SfM-anchor reprojection error vs capture order and
distance. If late/far frames have systematically higher error -> ARKit global drift
is real -> light BA is the fix. If error is uniformly small -> drift is NOT the
culprit (residual dirt is glare/specular -> conf mask instead).
"""
import json
import numpy as np
import pw_diffmvs_run as R

man, wdef, _ = R._load_meta()
A = np.load(R.ANCH)
pts, obsf, obsuv, obsa = A["pts"], A["obs_frame"], A["obs_uv"], A["obs_aidx"]

# global frame -> (K@896x504, w2c) from windows
Kmap, wmap = {}, {}
for win, wd in wdef.items():
    z = np.load(R.EXPAC / "windows" / f"win_{win:02d}.npz")
    for j, mi in enumerate(wd["frame_idx"]):
        if mi not in Kmap:
            Kmap[mi] = z["K"][j].astype(np.float64); wmap[mi] = z["w2c"][j].astype(np.float64)
frames = sorted(Kmap)

# fit obs_uv native->896x504 scale from all observations (K is at 896x504)
us, vs = [], []
for mi in frames[:60]:
    sel = obsf == mi
    if sel.sum() < 8:
        continue
    aw = pts[obsa[sel]]; w2c = wmap[mi]; K = Kmap[mi]
    P = (w2c[:3, :3] @ aw.T + w2c[:3, 3:4]).T
    uvp = (K @ P.T).T; uvp = uvp[:, :2] / uvp[:, 2:3]
    us.append(uvp[:, 0] / obsuv[sel][:, 0]); vs.append(uvp[:, 1] / obsuv[sel][:, 1])
sx = float(np.median(np.concatenate(us))); sy = float(np.median(np.concatenate(vs)))
scale = np.array([sx, sy])
print(f"obs_uv->896x504 scale = [{sx:.4f},{sy:.4f}]", flush=True)

rows = []
for mi in frames:
    sel = obsf == mi
    if sel.sum() < 8:
        continue
    aw = pts[obsa[sel]]; w2c = wmap[mi]; K = Kmap[mi]
    P = (w2c[:3, :3] @ aw.T + w2c[:3, 3:4]).T
    z = P[:, 2]
    uvp = (K @ P.T).T; uvp = uvp[:, :2] / uvp[:, 2:3]
    err = np.linalg.norm(uvp - obsuv[sel] * scale, axis=1)
    good = z > 0.05
    med = float(np.median(err[good]))
    cap = int(man[mi]["frameID"].split("-")[-1])      # capture order
    center = -w2c[:3, :3].T @ w2c[:3, 3]
    rows.append((mi, cap, med, int(sel.sum()), center))

rows.sort(key=lambda r: r[1])                          # by capture order
caps = np.array([r[1] for r in rows]); errs = np.array([r[2] for r in rows])
centers = np.array([r[4] for r in rows])
scene_c = centers.mean(0); dist = np.linalg.norm(centers - scene_c, axis=1)

print(f"\nframes with poses+anchors: {len(rows)}")
print(f"per-frame median reproj err (px@896): overall median={np.median(errs):.2f}  "
      f"p90={np.percentile(errs,90):.2f}  max={errs.max():.2f}")
print(f"  frames >2px: {(errs>2).sum()}  >5px: {(errs>5).sum()}  >10px: {(errs>10).sum()}")

# capture-order thirds
n = len(rows); t = n // 3
early, mid, late = errs[:t], errs[t:2*t], errs[2*t:]
print(f"\nby CAPTURE ORDER (early/mid/late thirds): median err = "
      f"{np.median(early):.2f} / {np.median(mid):.2f} / {np.median(late):.2f} px")
print(f"  Pearson r(capture_order, err) = {np.corrcoef(caps, errs)[0,1]:+.3f}")

# distance bins
order = np.argsort(dist); de = errs[order]
near, far = de[:t], de[-t:]
print(f"by DISTANCE from scene center (near/far thirds): median err = "
      f"{np.median(near):.2f} / {np.median(far):.2f} px")
print(f"  Pearson r(distance, err) = {np.corrcoef(dist, errs)[0,1]:+.3f}")

worst = sorted(rows, key=lambda r: -r[2])[:8]
print("\nworst-8 frames (mi, cap#, medErr px, nObs):")
for mi, cap, med, no, _ in worst:
    print(f"  mi={mi:3d} cap={cap:3d} err={med:5.2f}px nObs={no}")
