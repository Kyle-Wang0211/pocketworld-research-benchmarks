#!/usr/bin/env python3
"""cap50 LoFTR floor rescue: #12 quantize -> #14 MAGSAC + ARKit-F Sampson ->
union-find tracks -> multi-view DLT with ARKit poses -> gates (cheirality/reproj<3/tri>=2deg).
Outputs floor_rescue.ply (geometry, colorize later) + fr_rescue_stats.json.
Pure numpy + cv2. No production code touched."""
import os, json, numpy as np, cv2
from collections import defaultdict
import fr_common as fc

FR = fc.FR
NPZ_IN = os.environ.get("FR_NPZ", FR + "/fr_matches.npz")
OUT_PRE = os.environ.get("FR_OUT_PRE", FR + "/floor_rescue")   # -> _PRE.ply, _PRE_band.ply
STATS_OUT = os.environ.get("FR_STATS", FR + "/fr_rescue_stats.json")
M = np.load(NPZ_IN)
pairs = sorted({k[:-3] for k in M.files if k.endswith("_p0")},
               key=lambda s: tuple(map(int, s.split("_"))))

# --- keypoint resolution: matches were run at MATCH_W/H; scale to WORK (K frame) ---
allmax = max(float(M[f"{p}_p0"][:, 0].max()) for p in pairs if len(M[f"{p}_p0"])) if pairs else 0
if allmax <= fc.MATCH_W + 2:
    sx, sy = fc.WORK_W / fc.MATCH_W, fc.WORK_H / fc.MATCH_H
    scale_note = f"MATCH->WORK x{sx:.3f}"
else:
    sx = sy = 1.0
    scale_note = "already WORK res"
print(f"[scale] max_x={allmax:.1f} -> {scale_note}")

# --- MAGSAC availability ---
HAS_MAGSAC = hasattr(cv2, "USAC_MAGSAC")
RANSAC_METHOD = cv2.USAC_MAGSAC if HAS_MAGSAC else cv2.FM_RANSAC
print(f"[#14] {'USAC_MAGSAC' if HAS_MAGSAC else 'FM_RANSAC (MAGSAC unavailable)'}")

# --- union-find over (frame, gridcell) ---
parent = {}
def find(x):
    parent.setdefault(x, x)
    r = x
    while parent[r] != r: r = parent[r]
    while parent[x] != r: parent[x], x = r, parent[x]
    return r
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[rb] = ra

node_px = defaultdict(list)   # (frame, cx, cy) -> [(x,y),...] observed pixels (WORK res)
G = fc.GRID
kept_total = raw_total = 0
per_pair = []
for p in pairs:
    i, j = map(int, p.split("_"))
    p0 = M[f"{p}_p0"].astype(np.float64) * [sx, sy]
    p1 = M[f"{p}_p1"].astype(np.float64) * [sx, sy]
    raw_total += len(p0)
    if len(p0) < 8:
        per_pair.append((i, j, len(p0), 0)); continue
    # #14 MAGSAC F reject
    Fm, mask = cv2.findFundamentalMat(p0, p1, RANSAC_METHOD, fc.MAGSAC_T, 0.999, 200000)
    mask = np.ones(len(p0), bool) if mask is None else mask.ravel().astype(bool)
    # ARKit-F Sampson reject (independent of planar degeneracy)
    samp = fc.sampson(fc.F_arkit(i, j), p0, p1)
    keep = mask & (samp < fc.SAMPSON_T)
    kept_total += int(keep.sum())
    per_pair.append((i, j, len(p0), int(keep.sum())))
    for (x0, y0), (x1, y1) in zip(p0[keep], p1[keep]):
        c0 = (i, int(x0 // G), int(y0 // G)); c1 = (j, int(x1 // G), int(y1 // G))
        node_px[c0].append((x0, y0)); node_px[c1].append((x1, y1))
        union(c0, c1)
print(f"[match] {len(pairs)} pairs  raw={raw_total}  kept(MAGSAC&Sampson<{fc.SAMPSON_T})={kept_total}")

# --- tracks: root -> {frame: mean pixel} ---
tracks = defaultdict(lambda: defaultdict(list))
for cell, pxs in node_px.items():
    fid = cell[0]
    mx = np.mean([q[0] for q in pxs]); my = np.mean([q[1] for q in pxs])
    tracks[find(cell)][fid].append((mx, my))

# --- multi-view DLT + gates ---
def triangulate(views):
    A = []
    for fid, x, y in views:
        P = fc.projmat(fid)
        A.append(x * P[2] - P[0]); A.append(y * P[2] - P[1])
    _, _, Vt = np.linalg.svd(np.asarray(A))
    X = Vt[-1]; return X[:3] / X[3]

pts, meta = [], []
n_track = n_2plus = n_cheir = n_reproj = n_ang = 0
for root, byframe in tracks.items():
    n_track += 1
    views = [(fid, float(np.mean([q[0] for q in v])), float(np.mean([q[1] for q in v])))
             for fid, v in byframe.items()]
    if len(views) < 2: continue
    n_2plus += 1
    X = triangulate(views)
    reprojs, dirs, ok = [], [], True
    for fid, x, y in views:
        Xc = fc.R_of(fid) @ X + fc.t_of(fid); z = Xc[2]
        if not (fc.DEPTH_MIN < z < fc.DEPTH_MAX): ok = False; break
        uv = fc.K_of(fid) @ Xc; uv = uv[:2] / uv[2]
        reprojs.append(float(np.hypot(uv[0] - x, uv[1] - y)))
        d = X - fc.C_of(fid); dirs.append(d / (np.linalg.norm(d) + 1e-12))
    if not ok: n_cheir += 1; continue
    if max(reprojs) > fc.REPROJ_T: n_reproj += 1; continue
    ang = 0.0
    for a in range(len(dirs)):
        for b in range(a + 1, len(dirs)):
            ang = max(ang, np.degrees(np.arccos(np.clip(dirs[a] @ dirs[b], -1, 1))))
    if ang < fc.TRI_ANGLE_MIN: n_ang += 1; continue
    pts.append(X); meta.append((len(views), ang, max(reprojs), float(fc.floor_dist(X))))

pts = np.asarray(pts); meta = np.asarray(meta)
print(f"[tri] tracks={n_track} 2+view={n_2plus}  rej: cheir={n_cheir} reproj={n_reproj} ang={n_ang}"
      f"  -> RESCUE={len(pts)}")

# --- floor-band subset (headline: fills the SIFT floor hole?) ---
if len(pts):
    fd = meta[:, 3]
    floor_band = np.abs(fd) < fc.FLOOR_BAND
    fc.write_ply(OUT_PRE + ".ply", pts, rgb=None,
                 extra=meta, extra_names=["nview", "tri_angle_deg", "max_reproj_px", "floor_dist_m"])
    fc.write_ply(OUT_PRE + "_band.ply", pts[floor_band],
                 extra=meta[floor_band], extra_names=["nview", "tri_angle_deg", "max_reproj_px", "floor_dist_m"])
    stats = {
        "scale_note": scale_note, "magsac": HAS_MAGSAC,
        "pairs": len(pairs), "raw_matches": raw_total, "kept_after_F": kept_total,
        "tracks_total": n_track, "tracks_2plus_view": n_2plus,
        "rejected": {"cheirality": n_cheir, "reproj_gt3px": n_reproj, "tri_angle_lt2deg": n_ang},
        "rescue_points_total": int(len(pts)),
        "rescue_points_floor_band_20mm": int(floor_band.sum()),
        "nview_median": float(np.median(meta[:, 0])), "nview_max": int(meta[:, 0].max()),
        "tri_angle_deg_median": float(np.median(meta[:, 1])),
        "max_reproj_px_median": float(np.median(meta[:, 2])),
        "floor_band_tri_angle_median": float(np.median(meta[floor_band, 1])) if floor_band.sum() else None,
        "floor_band_reproj_median": float(np.median(meta[floor_band, 2])) if floor_band.sum() else None,
    }
    json.dump(stats, open(STATS_OUT, "w"), indent=1)
    print(f"[floor] rescue in floor band(+-20mm) = {int(floor_band.sum())}  "
          f"(production SIFT floor = see production_floor_stats)")
    print("DONE ->", FR + "/floor_rescue.ply  (+ _band.ply, fr_rescue_stats.json)")
else:
    print("[!] no rescue points survived gates")
