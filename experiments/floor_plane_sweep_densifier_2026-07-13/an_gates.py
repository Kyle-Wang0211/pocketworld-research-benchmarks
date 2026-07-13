#!/usr/bin/env python3
"""Analysis-only: instrument the exact triangulation to measure WHERE good floor points
are lost. No production code, no re-matching. Reuses fr_matches.npz + fr_common gates."""
import json, numpy as np, cv2
from collections import defaultdict
import fr_common as fc

FR = fc.FR
M = np.load(FR + "/fr_matches.npz")
pairs = sorted({k[:-3] for k in M.files if k.endswith("_p0")},
               key=lambda s: tuple(map(int, s.split("_"))))
G = fc.GRID
HAS_MAGSAC = hasattr(cv2, "USAC_MAGSAC")
RANSAC = cv2.USAC_MAGSAC if HAS_MAGSAC else cv2.FM_RANSAC

parent = {}
def find(x):
    parent.setdefault(x, x); r = x
    while parent[r] != r: r = parent[r]
    while parent[x] != r: parent[x], x = r, parent[x]
    return r
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[rb] = ra

# node_px: (frame,cx,cy) -> list of observed pixels merged into this cell
node_px = defaultdict(list)
for p in pairs:
    i, j = map(int, p.split("_"))
    p0 = M[f"{p}_p0"].astype(np.float64); p1 = M[f"{p}_p1"].astype(np.float64)
    if len(p0) < 8: continue
    Fm, mask = cv2.findFundamentalMat(p0, p1, RANSAC, fc.MAGSAC_T, 0.999, 200000)
    mask = np.ones(len(p0), bool) if mask is None else mask.ravel().astype(bool)
    samp = fc.sampson(fc.F_arkit(i, j), p0, p1)
    keep = mask & (samp < fc.SAMPSON_T)
    for (x0, y0), (x1, y1) in zip(p0[keep], p1[keep]):
        c0 = (i, int(x0 // G), int(y0 // G)); c1 = (j, int(x1 // G), int(y1 // G))
        node_px[c0].append((x0, y0)); node_px[c1].append((x1, y1))
        union(c0, c1)

# within-cell merge spread: how far apart are pixels averaged into one cell?
cell_spread = {}
for cell, pxs in node_px.items():
    a = np.asarray(pxs)
    cell_spread[cell] = 0.0 if len(a) < 2 else float(np.max(np.hypot(a[:,0]-a[:,0].mean(), a[:,1]-a[:,1].mean())))

tracks = defaultdict(lambda: defaultdict(list))
track_cellspread = defaultdict(float)
for cell, pxs in node_px.items():
    fid = cell[0]; a = np.asarray(pxs)
    tracks[find(cell)][fid].append((a[:,0].mean(), a[:,1].mean()))
    track_cellspread[find(cell)] = max(track_cellspread[find(cell)], cell_spread[cell])

def triangulate(views):
    A = []
    for fid, x, y in views:
        P = fc.projmat(fid); A.append(x*P[2]-P[0]); A.append(y*P[2]-P[1])
    _, _, Vt = np.linalg.svd(np.asarray(A)); X = Vt[-1]; return X[:3]/X[3]

def eval_track(views):
    X = triangulate(views); reprojs = []; dirs = []
    for fid, x, y in views:
        Xc = fc.R_of(fid) @ X + fc.t_of(fid); z = Xc[2]
        if not (fc.DEPTH_MIN < z < fc.DEPTH_MAX): return None
        uv = fc.K_of(fid) @ Xc; uv = uv[:2]/uv[2]
        reprojs.append(np.hypot(uv[0]-x, uv[1]-y)); d = X - fc.C_of(fid); dirs.append(d/(np.linalg.norm(d)+1e-12))
    ang = 0.0
    for a in range(len(dirs)):
        for b in range(a+1, len(dirs)):
            ang = max(ang, np.degrees(np.arccos(np.clip(dirs[a]@dirs[b],-1,1))))
    return X, np.array(reprojs), ang

FB = fc.FLOOR_BAND  # 0.020
NEAR = 0.030        # near-floor test band for reject characterization

# categorize every 2+ track
rej_reproj = []   # (floor_dist, max_reproj, nview, cellspread, robust_recoverable)
rej_ang = []      # (floor_dist, ang, nview, cellspread)
accepted_floor_conf_note = 0
for root, byframe in tracks.items():
    views = [(fid, float(np.mean([q[0] for q in v])), float(np.mean([q[1] for q in v])))
             for fid, v in byframe.items()]
    if len(views) < 2: continue
    res = eval_track(views)
    if res is None: continue  # cheirality
    X, reprojs, ang = res
    fd = float(fc.floor_dist(X)); nv = len(views); cs = track_cellspread[root]
    if reprojs.max() > fc.REPROJ_T:
        # robust recovery: drop worst view, re-triangulate if 3+ views
        recov = False; fd2 = fd; ang2 = ang
        if nv >= 3:
            worst = int(np.argmax(reprojs)); vv = [v for k,v in enumerate(views) if k != worst]
            r2 = eval_track(vv)
            if r2 is not None:
                X2, rp2, ang2 = r2
                if rp2.max() <= fc.REPROJ_T and ang2 >= fc.TRI_ANGLE_MIN:
                    recov = True; fd2 = float(fc.floor_dist(X2))
        rej_reproj.append((fd, float(reprojs.max()), nv, cs, recov, fd2))
    elif ang < fc.TRI_ANGLE_MIN:
        rej_ang.append((fd, ang, nv, cs))

rej_reproj = np.array(rej_reproj, float) if rej_reproj else np.zeros((0,6))
rej_ang = np.array(rej_ang, float) if rej_ang else np.zeros((0,4))

print("=== REPROJ>3px rejects: total", len(rej_reproj))
if len(rej_reproj):
    fd = rej_reproj[:,0]; mr = rej_reproj[:,1]; nv = rej_reproj[:,2]; cs = rej_reproj[:,3]; recov = rej_reproj[:,4].astype(bool); fd2 = rej_reproj[:,5]
    print("  near floor(|fd|<30mm):", (np.abs(fd)<NEAR).sum(), " in-band(<20mm):", (np.abs(fd)<FB).sum())
    print("  reproj bucket among near-floor(<30mm):")
    nf = np.abs(fd)<NEAR
    for lo,hi in [(3,4),(4,6),(6,10),(10,1e9)]:
        m = nf & (mr>=lo)&(mr<hi); print("    [%g,%g)px: %d"%(lo,hi,m.sum()))
    print("  high cell-merge-spread (>4px, likely #12 quant merge damage): all=%d near-floor=%d"%((cs>4).sum(),(nf&(cs>4)).sum()))
    print("  robust-recoverable (drop worst view -> passes): all=%d  near-floor=%d  ->in-band after: %d"%(
        recov.sum(), (nf&recov).sum(), (recov & (np.abs(fd2)<FB)).sum()))

print("=== tri_angle<2deg rejects: total", len(rej_ang))
if len(rej_ang):
    fd = rej_ang[:,0]; ang = rej_ang[:,1]; nv = rej_ang[:,2]
    nf = np.abs(fd)<NEAR
    print("  near floor(<30mm):", nf.sum(), " in-band(<20mm):", (np.abs(fd)<FB).sum())
    print("  angle among near-floor:", "median=%.2f"%(np.median(ang[nf]) if nf.sum() else -1))
    for lo,hi in [(0,0.5),(0.5,1),(1,1.5),(1.5,2)]:
        m = nf&(ang>=lo)&(ang<hi); print("    [%g,%g)deg: %d"%(lo,hi,m.sum()))
    print("  nview>=3 among near-floor tri<2 rejects:", (nf&(nv>=3)).sum())

# conf of accepted floor-band good points: recompute which matches feed floor points
print("=== DONE")
