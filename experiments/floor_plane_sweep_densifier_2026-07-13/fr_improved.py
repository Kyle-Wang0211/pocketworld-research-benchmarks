#!/usr/bin/env python3
"""Lever C improved recovery. Same matches (fr_matches.npz), same geometry gates
(cheirality + reproj<3 + tri>=2deg + MAGSAC/Sampson<3). Two additions:
  (B) ROBUST TRACK CLEANING: a union-find track polluted by cross-object merge
      (reproj>3px) is SPLIT into maximal geometrically-consistent view subsets;
      each subset >=2 views that passes ALL gates becomes a point. No gate relaxed.
  (C) finer grid option to reduce cross-object merge at the source.
Reports: floor good points, 5cm coverage cells, quality (tri/reproj/valid),
and NEW 5cm cells that SIFT production floor does NOT already cover.
Env: FR_GRID (default 8), FR_ROBUST (1 on/0 off), FR_SPLIT (1 recover 2nd subset).
"""
import os, json, struct, numpy as np, cv2
from collections import defaultdict
import fr_common as fc

FR = fc.FR
GRID = int(os.environ.get("FR_GRID", str(fc.GRID)))
ROBUST = os.environ.get("FR_ROBUST", "1") == "1"
SPLIT = os.environ.get("FR_SPLIT", "1") == "1"
fc.REPROJ_T = float(os.environ.get("FR_REPROJ", str(fc.REPROJ_T)))  # allow tightening only
CELL = 0.05  # 5cm coverage cell (matches production_floor_stats coverage metric)

# ---------- binary/ascii PLY reader (xyz only) ----------
def read_ply_xyz(path):
    with open(path, "rb") as f:
        line = f.readline().decode().strip()
        assert line == "ply"
        fmt = None; n = 0; props = []
        while True:
            line = f.readline().decode().strip()
            if line.startswith("format"): fmt = line.split()[1]
            elif line.startswith("element vertex"): n = int(line.split()[-1])
            elif line.startswith("property"): props.append(line.split()[1:])
            elif line == "end_header": break
        if fmt == "ascii":
            xyz = np.array([[float(v) for v in f.readline().split()[:3]] for _ in range(n)])
            return xyz
        # binary_little_endian: build struct per vertex
        tmap = {"float":"f","float32":"f","double":"d","uchar":"B","uint8":"B",
                "char":"b","int":"i","uint":"I","short":"h","ushort":"H"}
        fchar = {"float":4,"float32":4,"double":8,"uchar":1,"uint8":1,"char":1,
                 "int":4,"uint":4,"short":2,"ushort":2}
        rec = "<" + "".join(tmap[p[0]] for p in props)
        sz = sum(fchar[p[0]] for p in props)
        buf = f.read(sz * n)
        out = np.zeros((n,3))
        vals = list(struct.iter_unpack(rec, buf))
        for k in range(n):
            out[k,0]=vals[k][0]; out[k,1]=vals[k][1]; out[k,2]=vals[k][2]
        return out

sift = read_ply_xyz(FR + "/production_floor.ply")

# ---------- in-plane 2D basis for 5cm rasterization ----------
n = fc.PLANE_N
a = np.array([1,0,0.]) if abs(n[0]) < 0.9 else np.array([0,1,0.])
u = a - (a @ n) * n; u /= np.linalg.norm(u)
v = np.cross(n, u)
def cells_of(pts):
    if len(pts) == 0: return set()
    uu = pts @ u; vv = pts @ v
    return set(zip(np.floor(uu/CELL).astype(int), np.floor(vv/CELL).astype(int)))
sift_cells = cells_of(sift)  # SIFT floor 5cm cells (all sift floor, not just band)

# ---------- matches -> union-find tracks ----------
M = np.load(FR + "/fr_matches.npz")
pairs = sorted({k[:-3] for k in M.files if k.endswith("_p0")},
               key=lambda s: tuple(map(int, s.split("_"))))
RANSAC = cv2.USAC_MAGSAC if hasattr(cv2, "USAC_MAGSAC") else cv2.FM_RANSAC
parent = {}
def find(x):
    parent.setdefault(x, x); r = x
    while parent[r] != r: r = parent[r]
    while parent[x] != r: parent[x], x = r, parent[x]
    return r
def union(a_, b_):
    ra, rb = find(a_), find(b_)
    if ra != rb: parent[rb] = ra
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
        c0 = (i, int(x0//GRID), int(y0//GRID)); c1 = (j, int(x1//GRID), int(y1//GRID))
        node_px[c0].append((x0, y0)); node_px[c1].append((x1, y1))
        union(c0, c1)

tracks = defaultdict(lambda: defaultdict(list))
for cell, pxs in node_px.items():
    fid = cell[0]
    mx = np.mean([q[0] for q in pxs]); my = np.mean([q[1] for q in pxs])
    tracks[find(cell)][fid].append((mx, my))

# ---------- triangulation + gate helpers ----------
def tri(views):
    A = []
    for fid, x, y in views:
        P = fc.projmat(fid); A.append(x*P[2]-P[0]); A.append(y*P[2]-P[1])
    _,_,Vt = np.linalg.svd(np.asarray(A)); X = Vt[-1]; return X[:3]/X[3]

def evalv(views):
    """-> (ok, maxreproj, maxang, X, reprojs) ; ok=False on cheirality fail"""
    X = tri(views); reprojs=[]; dirs=[]
    for fid,x,y in views:
        Xc = fc.R_of(fid)@X + fc.t_of(fid); z=Xc[2]
        if not (fc.DEPTH_MIN < z < fc.DEPTH_MAX): return (False,None,None,X,None)
        uv = fc.K_of(fid)@Xc; uv=uv[:2]/uv[2]
        reprojs.append(float(np.hypot(uv[0]-x, uv[1]-y)))
        d=X-fc.C_of(fid); dirs.append(d/(np.linalg.norm(d)+1e-12))
    ang=0.0
    for a_ in range(len(dirs)):
        for b_ in range(a_+1,len(dirs)):
            ang=max(ang, np.degrees(np.arccos(np.clip(dirs[a_]@dirs[b_],-1,1))))
    return (True, max(reprojs), ang, X, reprojs)

def passes(views):
    ok,mr,ang,X,rr = evalv(views)
    if not ok or mr>fc.REPROJ_T or ang<fc.TRI_ANGLE_MIN: return None
    return (X, len(views), ang, mr)

def recover(views):
    """Return list of accepted (X,nview,ang,reproj) from a (possibly polluted) track.
    Clean path: whole track passes -> 1 pt. Else robust: greedily peel the
    max-reproj view to find a consistent subset; optionally recover a 2nd subset
    from the peeled-off views (true cross-object split)."""
    r = passes(views)
    if r is not None: return [r]
    if not ROBUST or len(views) < 3: return []
    out = []
    vv = list(views); peeled = []
    while len(vv) >= 2:
        r = passes(vv)
        if r is not None: out.append(r); break
        ok,mr,ang,X,rr = evalv(vv)
        wi = int(np.argmax(rr)) if rr is not None else 0
        peeled.append(vv.pop(wi))
    if SPLIT and len(peeled) >= 2:
        out += recover(peeled)  # recurse on the discarded observations
    return out

# ---------- run ----------
pts=[]; meta=[]
for root, byframe in tracks.items():
    views = [(fid, float(np.mean([q[0] for q in v])), float(np.mean([q[1] for q in v])))
             for fid, v in byframe.items()]
    if len(views) < 2: continue
    for X, nv, ang, mr in recover(views):
        pts.append(X); meta.append((nv, ang, mr, float(fc.floor_dist(X))))
pts = np.asarray(pts); meta = np.asarray(meta)

# ---------- dedup at 1cm (avoid split producing near-duplicate points) ----------
def dedup(P, MT, vox=0.01):
    if len(P)==0: return P, MT
    keys = np.floor(P/vox).astype(np.int64)
    seen={}; keep=[]
    order = np.argsort(-MT[:,0])  # prefer higher n-view
    for idx in order:
        k = tuple(keys[idx])
        if k in seen: continue
        seen[k]=1; keep.append(idx)
    keep=np.array(sorted(keep))
    return P[keep], MT[keep]
pts, meta = dedup(pts, meta)

fd = meta[:,3]; band = np.abs(fd) < fc.FLOOR_BAND
band_pts = pts[band]; band_meta = meta[band]
rescue_cells = cells_of(band_pts)
new_cells = rescue_cells - sift_cells

def med(a): return float(np.median(a)) if len(a) else None
res = {
  "grid": GRID, "robust": ROBUST, "split": SPLIT,
  "rescue_points_total": int(len(pts)),
  "floor_band_20mm_points": int(band.sum()),
  "floor_band_5cm_cells": len(rescue_cells),
  "floor_band_5cm_cells_NEW_vs_sift": len(new_cells),
  "sift_floor_5cm_cells": len(sift_cells),
  "quality_floorband": {
     "tri_angle_deg_median": med(band_meta[:,1]),
     "reproj_px_median": med(band_meta[:,2]),
     "nview_median": med(band_meta[:,0]),
     "nview_ge3_frac": float((band_meta[:,0]>=3).mean()) if band.sum() else None,
     "tri_angle_deg_p10": float(np.percentile(band_meta[:,1],10)) if band.sum() else None,
     "reproj_px_p90": float(np.percentile(band_meta[:,2],90)) if band.sum() else None,
  },
}
tag = f"g{GRID}_R{int(ROBUST)}_S{int(SPLIT)}"
json.dump(res, open(FR + f"/fr_improved_{tag}.json", "w"), indent=1)
# save band ply for the headline config only
if os.environ.get("FR_WRITE","0")=="1":
    fc.write_ply(FR + "/floor_rescue_band_improved.ply", band_pts,
                 extra=band_meta, extra_names=["nview","tri_angle_deg","max_reproj_px","floor_dist_m"])
print(json.dumps(res, indent=1))
