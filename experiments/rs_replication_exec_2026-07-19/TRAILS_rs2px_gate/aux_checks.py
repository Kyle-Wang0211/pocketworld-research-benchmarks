#!/usr/bin/env python3.11
"""E2-B v2 auxiliary checks:
A) residual-median decomposition (2-view vs multi-view tracks) — reconcile with prior 0.56px claim
B) far-trail region (>1m outside camera XZ hull) absolute kill/remain per gate
C) floor-band coverage on RS candidate vs baseline (already in stats; recomputed for far region)
Writes aux_checks.json only."""
import sqlite3, numpy as np, json, os
from collections import defaultdict
from scipy.spatial import cKDTree

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
CAP_DIR = f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17"
OUT = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/TRAILS_rs2px_gate"
MAX_IMAGE_ID = 2147483647

def quat_to_R(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                     [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                     [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])

db = sqlite3.connect(f"file:{CAP_DIR}/sfm_live.db?mode=ro", uri=True); c = db.cursor()
img_ids = sorted(i for (i,) in c.execute("SELECT image_id FROM images"))
kp_xy, kp_count = {}, {}
for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
    arr = np.frombuffer(data, dtype=np.float32).reshape(r, cols)
    kp_xy[iid] = arr[:, :2].astype(np.float64); kp_count[iid] = r
params = np.frombuffer(c.execute("SELECT params FROM cameras").fetchone()[0], dtype=np.float64)
f_, cx_, cy_ = params
offset, acc = {}, 0
for iid in img_ids: offset[iid] = acc; acc += kp_count.get(iid,0)
N = acc
parent = np.arange(N, dtype=np.int64)
def find(x):
    root = x
    while parent[root] != root: root = parent[root]
    while parent[x] != root: parent[x], x = root, parent[x]
    return root
for pair_id, r, cols, data in c.execute("SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0"):
    iid1, iid2 = pair_id // MAX_IMAGE_ID, pair_id % MAX_IMAGE_ID
    if iid1 not in offset or iid2 not in offset: continue
    m = np.frombuffer(data, dtype=np.uint32).reshape(r, cols)
    for f1, f2 in m:
        if f1 >= kp_count[iid1] or f2 >= kp_count[iid2]: continue
        ra, rb = find(offset[iid1]+int(f1)), find(offset[iid2]+int(f2))
        if ra != rb: parent[rb] = ra
db.close()
for x in range(N): find(x)
roots = parent
iid_of_node = np.zeros(N, np.int64)
for iid in img_ids:
    iid_of_node[offset[iid]:offset[iid]+kp_count[iid]] = iid

meta = json.load(open(f"{CAP_DIR}/sfm_sparse_meta.json"))
pose_R, pose_t = {}, {}
K = np.array([[f_,0,cx_],[0,f_,cy_],[0,0,1]])
Pmat = {}
for p in meta["poses"]:
    if not p.get("registered"): continue
    R = quat_to_R(np.array(p["quat_wxyz"],float)); t = np.array(p["t"],float)
    pose_R[p["frame_id"]], pose_t[p["frame_id"]] = R, t
    Pmat[p["frame_id"]] = K @ np.hstack([R, t.reshape(3,1)])

order = np.argsort(roots, kind="stable")
rs = roots[order]
bounds = np.flatnonzero(np.diff(rs)) + 1
groups = [g for g in np.split(order, bounds) if len(g) >= 2]

res_by_size = {"2": [], "3-4": [], "5-9": [], "10+": []}
tracksize_hist = defaultdict(int)
for grp in groups:
    fids, xys = [], []
    for nd in grp:
        iid = int(iid_of_node[nd]); fid = iid-1
        if fid not in pose_R: continue
        fids.append(fid); xys.append(kp_xy[iid][nd-offset[iid]])
    nf = len(set(fids))
    if nf < 2: continue
    tracksize_hist[min(len(fids), 15)] += 1
    A = np.empty((2*len(fids),4))
    for i,(fid,xy) in enumerate(zip(fids,xys)):
        P = Pmat[fid]
        A[2*i] = xy[0]*P[2]-P[0]; A[2*i+1] = xy[1]*P[2]-P[1]
    _,_,Vt = np.linalg.svd(A, full_matrices=False)
    Xh = Vt[-1]
    if abs(Xh[3]) < 1e-12: continue
    X = Xh[:3]/Xh[3]
    rr = []
    for fid,xy in zip(fids,xys):
        Xc = pose_R[fid]@X + pose_t[fid]
        if Xc[2] <= 0: rr.append(np.inf); continue
        rr.append(float(np.hypot(f_*Xc[0]/Xc[2]+cx_-xy[0], f_*Xc[1]/Xc[2]+cy_-xy[1])))
    n = len(fids)
    key = "2" if n==2 else "3-4" if n<=4 else "5-9" if n<=9 else "10+"
    res_by_size[key].extend(rr)

decomp = {}
for k, v in res_by_size.items():
    a = np.array(v); fin = a[np.isfinite(a)]
    decomp[k] = {"n_obs": len(a), "median_px": round(float(np.median(fin)),3) if len(fin) else None,
                 "p90_px": round(float(np.percentile(fin,90)),3) if len(fin) else None}

# B) far-trail region per gate using delivered clouds + hull from npz
z = np.load(f"{OUT}/render_arrays_v2.npz")
hull_xy, cams = z["hull_xy"], z["cams"]
def outside_dist(pts):
    p_xz = pts[:, [0,2]]
    seg_d = np.full(len(pts), np.inf)
    for i in range(len(hull_xy)):
        a, b = hull_xy[i], hull_xy[(i+1)%len(hull_xy)]
        ab = b-a
        t = np.clip(((p_xz-a)@ab)/(ab@ab), 0, 1)
        seg_d = np.minimum(seg_d, np.linalg.norm(p_xz-(a+t[:,None]*ab), axis=1))
    from scipy.spatial import Delaunay
    inside = Delaunay(hull_xy).find_simplex(p_xz) >= 0
    return np.where(inside, 0.0, seg_d)

def read_ply(path):
    with open(path,"rb") as f:
        h=b""
        while not h.endswith(b"end_header\n"): h += f.readline()
        n=int([l for l in h.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        d=np.fromfile(f,dtype=rec,count=n)
    return np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64)

far = {}
prod = read_ply(f"{CAP_DIR}/sfm_sparse.ply")
for name, path in [("production", None), ("ours4px", f"{OUT}/ours4px_cap50.ply"),
                   ("mid3px", f"{OUT}/mid3px_cap50.ply"), ("rs2px", f"{OUT}/rs2px_cap50.ply")]:
    pts = prod if path is None else read_ply(path)
    od = outside_dist(pts)
    far[name] = {"n_total": len(pts),
                 "n_outside_0.5-1m": int(((od>=0.5)&(od<1.0)).sum()),
                 "n_outside_1-2m": int(((od>=1.0)&(od<2.0)).sum()),
                 "n_outside_gt2m": int((od>=2.0).sum())}

out = {"A_residual_decomposition_by_track_size": decomp,
       "A_note": "prior 0.56px claim likely measured 2-view-dominant or per-pair triangulations; multi-view merged tracks carry larger per-obs residuals",
       "A_tracksize_hist(capped15)": {str(k): v for k,v in sorted(tracksize_hist.items())},
       "B_far_trail_absolute": far}
json.dump(out, open(f"{OUT}/aux_checks.json","w"), indent=2)
print(json.dumps(out, indent=1))
