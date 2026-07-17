#!/usr/bin/env python3.11
"""
#6 GLOMAP same-image multi-feature alias detector (prototype) for cap50.

Mechanism (mirrors GLOMAP track_establishment.cc union-find):
  - Nodes = (image_id, feature_idx).
  - Union over two_view_geometries INLIER matches (COLMAP's geometrically
    verified correspondences = what GLOMAP consumes for track establishment).
  - A track = connected component.
  - ALIAS = a track that collects >= 2 distinct features from the SAME image.
    In stock GLOMAP such a track is dropped whole ("thres_inconsistency" /
    duplicate-image rejection). U3 upgrade: DO NOT drop; MARK as an
    observation-site candidate for pre-birth arbitration.

Outputs (no self-approval; numbers + manifest only):
  tracks_summary.json          global track / alias statistics
  alias_tracks.jsonl           one row per alias track (members + which images collide)
  alias_points.ply             3D triangulated alias-track centroids (source-colored)
  alias_points.csv             per-alias-track 3D pos + spread + ROI flags
This script only READS the DB and WRITES into 06_glomap_alias/. No prod code touched.
"""
import sqlite3, numpy as np, json, os, sys, struct

DB = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_live.db"
META = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse_meta.json"
OUT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/06_glomap_alias"
MAX_IMAGE_ID = 2147483647  # COLMAP pair_id base

# chair "squash" ROI (top-down bottom-right), from task
CHAIR_X = (0.25, 1.05)
CHAIR_Z = (-1.70, -0.55)

def log(*a): print(*a, flush=True)

# ---------- load DB ----------
db = sqlite3.connect(DB); c = db.cursor()
img_name = {}
for iid, name in c.execute("SELECT image_id,name FROM images"):
    img_name[iid] = name
n_images = len(img_name)
max_iid = max(img_name)

# per-image keypoint counts + xy
kp_count = {}
kp_xy = {}   # image_id -> (n,2) float32
for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
    arr = np.frombuffer(data, dtype=np.float32).reshape(r, cols)
    kp_count[iid] = r
    kp_xy[iid] = np.ascontiguousarray(arr[:, :2])
log(f"images={n_images} max_iid={max_iid} total_kp={sum(kp_count.values())}")

# global node offsets
offset = {}
acc = 0
for iid in sorted(img_name):
    offset[iid] = acc
    acc += kp_count.get(iid, 0)
N = acc
log(f"total feature nodes N={N}")

# ---------- union-find ----------
parent = np.arange(N, dtype=np.int64)
rank = np.zeros(N, dtype=np.int8)
def find(x):
    root = x
    while parent[root] != root:
        root = parent[root]
    while parent[x] != root:
        parent[x], x = root, parent[x]
    return root
def union(a, b):
    ra, rb = find(a), find(b)
    if ra == rb: return
    if rank[ra] < rank[rb]: ra, rb = rb, ra
    parent[rb] = ra
    if rank[ra] == rank[rb]: rank[ra] += 1

n_pairs = 0
n_edges = 0
for pair_id, r, cols, data in c.execute("SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0"):
    iid2 = pair_id % MAX_IMAGE_ID
    iid1 = pair_id // MAX_IMAGE_ID
    if iid1 not in offset or iid2 not in offset:
        continue
    m = np.frombuffer(data, dtype=np.uint32).reshape(r, cols)  # cols=2 feature idx
    o1, o2 = offset[iid1], offset[iid2]
    n1, n2 = kp_count[iid1], kp_count[iid2]
    for f1, f2 in m:
        if f1 >= n1 or f2 >= n2:
            continue
        union(o1 + int(f1), o2 + int(f2))
        n_edges += 1
    n_pairs += 1
log(f"union pairs={n_pairs} edges={n_edges}")
db.close()

# ---------- gather tracks ----------
# node -> (image_id, feat_idx) reverse lookup via offsets
img_ids_sorted = sorted(img_name)
off_arr = np.array([offset[i] for i in img_ids_sorted] + [N], dtype=np.int64)
iid_arr = np.array(img_ids_sorted, dtype=np.int64)
def node_to_img(node):
    j = np.searchsorted(off_arr, node, side='right') - 1
    return int(iid_arr[j]), int(node - off_arr[j])

# flatten roots
roots = np.empty(N, dtype=np.int64)
for x in range(N):
    roots[x] = find(x)

from collections import defaultdict
track_nodes = defaultdict(list)
for node in range(N):
    track_nodes[int(roots[node])].append(node)

# track statistics: only tracks with >=2 nodes are real tracks
tracks = {rt: nodes for rt, nodes in track_nodes.items() if len(nodes) >= 2}
singletons = sum(1 for nodes in track_nodes.values() if len(nodes) == 1)
log(f"tracks(>=2 nodes)={len(tracks)} singletons={singletons}")

# ---------- alias detection ----------
alias_rows = []
track_len_hist = defaultdict(int)
n_alias = 0
alias_collision_images = defaultdict(int)  # image_id -> #alias tracks it participates with a duplicate
alias_track_recs = []
for rt, nodes in tracks.items():
    img_of = {}
    per_img = defaultdict(list)
    for node in nodes:
        iid, fidx = node_to_img(node)
        per_img[iid].append((fidx, node))
    n_obs = len(nodes)
    n_distinct_img = len(per_img)
    track_len_hist[n_obs] += 1
    dup_imgs = {iid: v for iid, v in per_img.items() if len(v) >= 2}
    if dup_imgs:
        n_alias += 1
        for iid in dup_imgs:
            alias_collision_images[iid] += 1
        alias_track_recs.append((rt, per_img, dup_imgs, n_obs, n_distinct_img))

log(f"ALIAS tracks (>=1 image contributes >=2 features) = {n_alias}")

# ---------- 3D triangulation of alias tracks ----------
meta = json.load(open(META))
pose_by_frame = {}
for p in meta['poses']:
    if p.get('registered'):
        pose_by_frame[p['frame_id']] = (np.array(p['quat_wxyz'], float), np.array(p['t'], float))
# intrinsics SIMPLE_PINHOLE f,cx,cy
db = sqlite3.connect(DB); c = db.cursor()
_, model, W, H, params, _ = c.execute("SELECT * FROM cameras LIMIT 1").fetchone()
f, cx, cy = np.frombuffer(params, dtype=np.float64)
db.close()
K = np.array([[f,0,cx],[0,f,cy],[0,0,1]])

def quat_to_R(q):
    w,x,y,z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z),   2*(x*z+w*y)],
        [2*(x*y+w*z),   1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y),   2*(y*z+w*x),   1-2*(x*x+y*y)]])

def image_to_frame(iid):
    return iid - 1  # image_id = frame_id+1

def triangulate(obs):
    # obs: list of (image_id, u, v). DLT.
    A = []
    for iid, u, v in obs:
        fr = image_to_frame(iid)
        if fr not in pose_by_frame: continue
        q, t = pose_by_frame[fr]
        R = quat_to_R(q)
        P = K @ np.hstack([R, t.reshape(3,1)])
        A.append(u*P[2] - P[0])
        A.append(v*P[2] - P[1])
    if len(A) < 4: return None, 0
    A = np.array(A)
    _,_,Vt = np.linalg.svd(A)
    X = Vt[-1]; X = X[:3]/X[3]
    return X, len(A)//2

# For alias tracks compute per-image "best" (all features') 3D and spread.
alias_pts = []
csv_lines = ["track_root,n_obs,n_images,n_dup_images,X,Y,Z,spread_m,in_chair_roi"]
for rt, per_img, dup_imgs, n_obs, n_distinct_img in alias_track_recs:
    # build obs using ALL features (alias => multiple per dup image)
    obs = []
    for iid, feats in per_img.items():
        for fidx, node in feats:
            xy = kp_xy[iid][fidx]
            obs.append((iid, float(xy[0]), float(xy[1])))
    X, nviews = triangulate(obs)
    if X is None:
        continue
    # spread: reprojection-free proxy = per-observation single-ray midpoint scatter
    # compute per-image individual triangulation not possible w/1 ray; use residual of DLT sol
    # spread proxy: std of pairwise triangulations among distinct-image subsets
    subpts = []
    imgs = list(per_img.keys())
    # sample: triangulate using each pair of distinct images (one feat each) -> scatter of the alias
    for i in range(len(imgs)):
        for j in range(i+1, len(imgs)):
            a, b = imgs[i], imgs[j]
            fa = per_img[a][0]; fb = per_img[b][0]
            xa = kp_xy[a][fa[0]]; xb = kp_xy[b][fb[0]]
            Xp, nv = triangulate([(a,float(xa[0]),float(xa[1])),(b,float(xb[0]),float(xb[1]))])
            if Xp is not None and np.all(np.isfinite(Xp)):
                subpts.append(Xp)
    spread = float(np.linalg.norm(np.std(np.array(subpts),axis=0))) if len(subpts)>=2 else 0.0
    in_roi = (CHAIR_X[0] <= X[0] <= CHAIR_X[1]) and (CHAIR_Z[0] <= X[2] <= CHAIR_Z[1])
    alias_pts.append((X, n_obs, len(dup_imgs), in_roi))
    csv_lines.append(f"{rt},{n_obs},{n_distinct_img},{len(dup_imgs)},{X[0]:.4f},{X[1]:.4f},{X[2]:.4f},{spread:.4f},{int(in_roi)}")

# ---------- write outputs ----------
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT,"alias_points.csv"),"w") as fcsv:
    fcsv.write("\n".join(csv_lines)+"\n")

# PLY: alias centroids colored by dup severity (red=alias in ROI, orange=alias elsewhere)
valid = [(X,in_roi) for (X,no,nd,in_roi) in alias_pts if np.all(np.isfinite(X))]
with open(os.path.join(OUT,"alias_points.ply"),"w") as fp:
    fp.write("ply\nformat ascii 1.0\n")
    fp.write(f"element vertex {len(valid)}\n")
    fp.write("property float x\nproperty float y\nproperty float z\n")
    fp.write("property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    for X,in_roi in valid:
        r,g,b = (255,0,0) if in_roi else (255,140,0)
        fp.write(f"{X[0]:.5f} {X[1]:.5f} {X[2]:.5f} {r} {g} {b}\n")

n_roi = sum(1 for (_,_,_,in_roi) in alias_pts if in_roi)
summary = {
  "capture": "cap50",
  "input_db": DB,
  "n_images": n_images,
  "n_registered_poses": len(pose_by_frame),
  "n_verified_pairs_used": n_pairs,
  "n_inlier_edges": n_edges,
  "n_feature_nodes": N,
  "n_tracks_ge2": len(tracks),
  "n_singletons": singletons,
  "n_alias_tracks": n_alias,
  "alias_fraction_of_tracks": round(n_alias/max(1,len(tracks)),5),
  "n_alias_triangulated": len(alias_pts),
  "n_alias_in_chair_roi": n_roi,
  "track_len_hist_top10": dict(sorted(track_len_hist.items())[:10]),
  "top_collision_images": sorted(alias_collision_images.items(), key=lambda kv:-kv[1])[:15],
  "chair_roi": {"X": CHAIR_X, "Z": CHAIR_Z},
  "note": "alias = same image contributes >=2 features to one union-find track (GLOMAP duplicate-image inconsistency). Marked as observation-site candidates, NOT dropped."
}
json.dump(summary, open(os.path.join(OUT,"tracks_summary.json"),"w"), indent=2)

# alias_tracks.jsonl
with open(os.path.join(OUT,"alias_tracks.jsonl"),"w") as fj:
    for rt, per_img, dup_imgs, n_obs, n_distinct_img in alias_track_recs:
        rec = {"track_root": rt, "n_obs": n_obs, "n_images": n_distinct_img,
               "dup_images": {str(iid): [f[0] for f in per_img[iid]] for iid in dup_imgs},
               "images": {str(iid): [f[0] for f in per_img[iid]] for iid in per_img}}
        fj.write(json.dumps(rec)+"\n")

log(json.dumps(summary, indent=2))
log("DONE")
