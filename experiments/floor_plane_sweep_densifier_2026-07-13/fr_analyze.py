#!/usr/bin/env python3
"""Diagnose the reproj>3px (8555) and tri_angle<2deg (708) rejects.
For each failed track: how many views, and is there a consistent SUBSET
(drop worst view) that would pass all gates? Also quantify within-frame
cell pixel spread (cross-object merge signature). No production code touched."""
import numpy as np, cv2
from collections import defaultdict
import fr_common as fc

FR = fc.FR
M = np.load(FR + "/fr_matches.npz")
pairs = sorted({k[:-3] for k in M.files if k.endswith("_p0")},
               key=lambda s: tuple(map(int, s.split("_"))))
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

G = fc.GRID
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

# tracks: root -> {frame: [pixel obs]}
tracks = defaultdict(lambda: defaultdict(list))
for cell, pxs in node_px.items():
    tracks[find(cell)][cell[0]].append(pxs)  # keep raw pixel lists per frame

def tri(views):
    A = []
    for fid, x, y in views:
        P = fc.projmat(fid); A.append(x*P[2]-P[0]); A.append(y*P[2]-P[1])
    _,_,Vt = np.linalg.svd(np.asarray(A)); X = Vt[-1]; return X[:3]/X[3]

def eval_views(views):
    """return (ok_cheir, max_reproj, max_angle, X, reprojs)"""
    X = tri(views); reprojs=[]; dirs=[]
    for fid,x,y in views:
        Xc = fc.R_of(fid)@X + fc.t_of(fid); z=Xc[2]
        if not (fc.DEPTH_MIN < z < fc.DEPTH_MAX): return (False,None,None,X,None)
        uv = fc.K_of(fid)@Xc; uv=uv[:2]/uv[2]
        reprojs.append(float(np.hypot(uv[0]-x, uv[1]-y)))
        d=X-fc.C_of(fid); dirs.append(d/(np.linalg.norm(d)+1e-12))
    ang=0.0
    for a in range(len(dirs)):
        for b in range(a+1,len(dirs)):
            ang=max(ang, np.degrees(np.arccos(np.clip(dirs[a]@dirs[b],-1,1))))
    return (True, max(reprojs), ang, X, reprojs)

# Reproduce baseline classification + probe subset rescue
n_reproj_fail=0; n_ang_fail=0; n_pass=0
reproj_rescuable=0; reproj_rescuable_floor=0
ang_fail_floor=0
withinframe_spread=[]  # for reproj-fail multiview: max within-frame obs spread
for root, byframe in tracks.items():
    views=[]
    frame_spread=0.0
    for fid, obslists in byframe.items():
        allpx=[q for lst in obslists for q in lst]
        mx=np.mean([q[0] for q in allpx]); my=np.mean([q[1] for q in allpx])
        if len(allpx)>1:
            sx=max(q[0] for q in allpx)-min(q[0] for q in allpx)
            sy=max(q[1] for q in allpx)-min(q[1] for q in allpx)
            frame_spread=max(frame_spread, np.hypot(sx,sy))
        views.append((fid,mx,my))
    if len(views)<2: continue
    ok,mr,ang,X,reprojs = eval_views(views)
    if not ok: continue
    if mr>fc.REPROJ_T:
        n_reproj_fail+=1
        withinframe_spread.append(frame_spread)
        # subset rescue: iteratively drop worst-reproj view
        vv=list(views); rr=list(reprojs)
        rescued=False
        while len(vv)>2:
            wi=int(np.argmax(rr)); vv.pop(wi)
            ok2,mr2,ang2,X2,rr2 = eval_views(vv)
            if not ok2: break
            rr=rr2
            if mr2<=fc.REPROJ_T and ang2>=fc.TRI_ANGLE_MIN:
                rescued=True; Xf=X2; break
        if rescued:
            reproj_rescuable+=1
            if abs(fc.floor_dist(Xf))<fc.FLOOR_BAND: reproj_rescuable_floor+=1
    elif ang<fc.TRI_ANGLE_MIN:
        n_ang_fail+=1
        if abs(fc.floor_dist(X))<fc.FLOOR_BAND: ang_fail_floor+=1
    else:
        n_pass+=1

sp=np.array(withinframe_spread)
print(f"reproj_fail(multiview)={n_reproj_fail}  ang_fail={n_ang_fail}  pass={n_pass}")
print(f"[reproj-fail] within-frame obs spread: median={np.median(sp):.2f}px  "
      f">8px(cross-cell merge)={int((sp>8).sum())} ({(sp>8).mean()*100:.0f}%)")
print(f"[SUBSET RESCUE] reproj-fail tracks rescuable by dropping outlier view: "
      f"{reproj_rescuable}  (floor-band: {reproj_rescuable_floor})")
print(f"[ang-fail] in floor band = {ang_fail_floor} / {n_ang_fail}")
