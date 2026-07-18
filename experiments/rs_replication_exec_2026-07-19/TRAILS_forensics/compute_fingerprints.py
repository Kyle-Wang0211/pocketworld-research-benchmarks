#!/usr/bin/env python3.11
"""
E2-A trail forensics, stage 1: per-point fingerprint computation (cap50 / cap51).

Recovers observation evidence for every delivered point from sfm_live.db using the
S1-validated method (project point into every registered frame with refined
production poses + frozen K; verified-matched keypoint within 3px = support obs),
then computes per-point trail fingerprints:

  n_support        - number of support frames (track-length proxy, lower bound)
  mean/max_resid   - px residual of production position vs supporting keypoints
  tri_angle_deg    - max pairwise parallax angle over support cameras (n>=2)
  ray (unit)       - mean viewing direction (support cameras; else nearest camera => proxy flag)
  cam_depth        - distance to primary camera
  elong            - local PCA elongation sqrt(l1/l2) over <=16 NN within 8cm
  ray_align        - |cos(local PCA major axis, ray)|  (1 = trail smeared along sight line)
  floor_h          - signed height above production-arbitrated floor plane (ghost_mask.json plane)
  blocked_frac     - fraction of camera->point corridor samples passing through dense
                     existing structure (see-through test, suspects only)

HONESTY: evidence rebuilt from sfm_live.db is NOT the byte-exact production path;
ghost_mask.bin per-point bits are computed on the 93,360-pt pre-filter cloud while the
PLY has 92,849 pts => order alignment unsafe, so ONLY the global floor plane from
ghost_mask.json is consumed, never per-point bits. Points with <1 recoverable obs get
a nearest-camera ray proxy (flagged). Reads only frozen capture data; writes only here.
"""
import sqlite3, numpy as np, json, os, sys, time, hashlib
from scipy.spatial import cKDTree

MAX_IMAGE_ID = 2147483647
SUPPORT_GATE_PX = 3.0
KNN = 16
NN_RADIUS = 0.08          # m, local PCA neighborhood
CORRIDOR_R = 0.04         # m, see-through cylinder radius
CORRIDOR_STOP = 0.15      # m, stop before the point itself
CORRIDOR_MIN_NBR = 4      # neighbors at a sample => "blocked" sample

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
CAPS = {
    "cap50": f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17",
    "cap51": f"{ROOT}/data/pocketworld_captures/cap51/device_full_pull_2026-07-17",
    # E3 extension (2026-07-18): assembled input dirs (symlinks; ghost plane for
    # cap40/41 = E4 host-replay production-recipe plane, device pull lacks it)
    "cap40": f"{ROOT}/experiments/rs_replication_exec_2026-07-19/E3_birth_discipline/cap40_inputs",
    "cap41": f"{ROOT}/experiments/rs_replication_exec_2026-07-19/E3_birth_discipline/cap41_inputs",
    "cap50_fixA": f"{ROOT}/experiments/rs_replication_exec_2026-07-19/E20_true_global/C_fix_a/cap50_fixA_inputs",
}
OUT_BASE = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/TRAILS_forensics"

def log(*a): print(*a, flush=True)

def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z),   2*(x*z+w*y)],
        [2*(x*y+w*z),   1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y),   2*(y*z+w*x),   1-2*(x*x+y*y)]])

def read_ply_xyzrgb(path):
    with open(path, "rb") as f:
        header = b""
        while not header.endswith(b"end_header\n"):
            header += f.readline()
        n = int([l for l in header.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        data = np.fromfile(f, dtype=rec, count=n)
    xyz = np.stack([data["x"], data["y"], data["z"]], axis=1).astype(np.float64)
    rgb = np.stack([data["r"], data["g"], data["b"]], axis=1)
    return xyz, rgb

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

def run_cap(cap):
    d = CAPS[cap]
    out = os.path.join(OUT_BASE, cap); os.makedirs(out, exist_ok=True)
    DB, META, PLY = f"{d}/sfm_live.db", f"{d}/sfm_sparse_meta.json", f"{d}/sfm_sparse.ply"
    GHOST = f"{d}/ghost_mask.json"
    log(f"=== {cap} ===")

    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c = db.cursor()
    img_ids = sorted(i for (i,) in c.execute("SELECT image_id FROM images"))
    kp_xy, kp_count = {}, {}
    for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
        arr = np.frombuffer(data, dtype=np.float32).reshape(r, cols)
        kp_xy[iid] = np.ascontiguousarray(arr[:, :2].astype(np.float64)); kp_count[iid] = r
    cam = c.execute("SELECT model,params,width,height FROM cameras LIMIT 1").fetchone()
    params = np.frombuffer(cam[1], dtype=np.float64)
    assert len(params) == 3
    f_, cx_, cy_ = params
    W, H = cam[2], cam[3]

    # union-find over verified inlier matches
    offset, acc = {}, 0
    for iid in img_ids: offset[iid] = acc; acc += kp_count.get(iid, 0)
    N = acc
    parent = np.arange(N, dtype=np.int64)
    def find(x):
        root = x
        while parent[root] != root: root = parent[root]
        while parent[x] != root: parent[x], x = root, parent[x]
        return root
    n_pairs = 0
    for pair_id, r, cols, data in c.execute("SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0"):
        iid1, iid2 = pair_id // MAX_IMAGE_ID, pair_id % MAX_IMAGE_ID
        if iid1 not in offset or iid2 not in offset: continue
        m = np.frombuffer(data, dtype=np.uint32).reshape(r, cols)
        o1, o2 = offset[iid1], offset[iid2]
        n1, n2 = kp_count[iid1], kp_count[iid2]
        for f1, f2 in m:
            if f1 >= n1 or f2 >= n2: continue
            ra, rb = find(o1+int(f1)), find(o2+int(f2))
            if ra != rb: parent[rb] = ra
        n_pairs += 1
    db.close()
    for x in range(N): find(x)
    roots = parent
    uniq, counts = np.unique(roots, return_counts=True)

    meta = json.load(open(META)); assert meta.get("refined") is True
    pose_R, pose_t, pose_C = {}, {}, {}
    for p in meta["poses"]:
        if not p.get("registered"): continue
        R = quat_to_R(np.array(p["quat_wxyz"], float)); t = np.array(p["t"], float)
        fid = p["frame_id"]; pose_R[fid], pose_t[fid] = R, t; pose_C[fid] = -R.T @ t

    xyz, rgb = read_ply_xyzrgb(PLY)
    nP = len(xyz)
    log(f"points={nP} frames={len(pose_R)} pairs={n_pairs}")

    # ---- support recovery (S1-validated) ----
    t0 = time.perf_counter()
    frame_trees, frame_nodes = {}, {}
    for iid in img_ids:
        fid = iid - 1
        if fid not in pose_R: continue
        base = offset[iid]
        nodes = np.arange(base, base + kp_count[iid])
        matched = counts[np.searchsorted(uniq, roots[nodes])] >= 2
        nodes = nodes[matched]
        if len(nodes) == 0: continue
        frame_trees[fid] = cKDTree(kp_xy[iid][nodes - base])
        frame_nodes[fid] = nodes
    support = [[] for _ in range(nP)]  # (fid, resid_px)
    for fid in sorted(frame_trees):
        R, t = pose_R[fid], pose_t[fid]
        Xc = xyz @ R.T + t
        infront = Xc[:, 2] > 1e-6
        uv = np.full((nP, 2), -1e9)
        z = Xc[infront, 2]
        uv[infront, 0] = f_*Xc[infront, 0]/z + cx_
        uv[infront, 1] = f_*Xc[infront, 1]/z + cy_
        inimg = infront & (uv[:,0]>=-3) & (uv[:,0]<=W+3) & (uv[:,1]>=-3) & (uv[:,1]<=H+3)
        q_idx = np.flatnonzero(inimg)
        if len(q_idx) == 0: continue
        dd, kk = frame_trees[fid].query(uv[q_idx], k=1, distance_upper_bound=SUPPORT_GATE_PX, workers=-1)
        hit = np.isfinite(dd)
        for pi, dist_px in zip(q_idx[hit], dd[hit]):
            support[pi].append((fid, float(dist_px)))
    log(f"support recovery {time.perf_counter()-t0:.1f}s")

    # ---- per-point fingerprints ----
    n_support = np.array([len(s) for s in support], dtype=np.int32)
    mean_resid = np.full(nP, np.nan); max_resid = np.full(nP, np.nan)
    tri_angle = np.full(nP, np.nan)
    ray = np.zeros((nP, 3)); ray_proxy = np.zeros(nP, bool)
    prim_fid = np.full(nP, -1, dtype=np.int32)
    cam_depth = np.full(nP, np.nan)
    camC = np.array([pose_C[f] for f in sorted(pose_C)])
    cam_fids = np.array(sorted(pose_C))
    cam_tree = cKDTree(camC)
    for pi in range(nP):
        s = support[pi]
        X = xyz[pi]
        if s:
            res = [r for _, r in s]
            mean_resid[pi] = float(np.mean(res)); max_resid[pi] = float(np.max(res))
            fids = [f for f, _ in s]
            prim_fid[pi] = fids[int(np.argmin(res))]
            dirs = np.array([X - pose_C[f] for f in fids])
            nrm = np.linalg.norm(dirs, axis=1); nrm[nrm < 1e-12] = 1
            dirs = dirs / nrm[:, None]
            m = dirs.mean(axis=0); m /= (np.linalg.norm(m) + 1e-15)
            ray[pi] = m
            cam_depth[pi] = float(np.linalg.norm(X - pose_C[prim_fid[pi]]))
            if len(fids) >= 2:
                dsub = dirs[:8]
                cosm = np.clip(dsub @ dsub.T, -1, 1)
                tri_angle[pi] = float(np.degrees(np.arccos(cosm.min())))
        else:
            dd, ki = cam_tree.query(X)
            Cn = camC[ki]
            v = X - Cn; nv = np.linalg.norm(v)
            ray[pi] = v / (nv + 1e-15); ray_proxy[pi] = True
            prim_fid[pi] = int(cam_fids[ki]); cam_depth[pi] = float(nv)
    log("fingerprints (obs) done")

    # ---- local PCA elongation + ray alignment ----
    t1 = time.perf_counter()
    tree = cKDTree(xyz)
    dd, ii = tree.query(xyz, k=KNN, workers=-1)
    valid = dd <= NN_RADIUS
    nnb = valid.sum(axis=1)
    P = xyz[ii]                                # (nP,K,3)
    wp = np.where(valid[:, :, None], P, np.nan)
    mu = np.nanmean(wp, axis=1)
    Dv = np.where(valid[:, :, None], P - mu[:, None, :], 0.0)
    cov = np.einsum('nki,nkj->nij', Dv, Dv) / np.maximum(nnb, 1)[:, None, None]
    evals, evecs = np.linalg.eigh(cov)         # ascending
    l1, l2 = evals[:, 2], evals[:, 1]
    elong = np.sqrt(np.maximum(l1, 0) / np.maximum(l2, 1e-12))
    axis = evecs[:, :, 2]
    ray_align = np.abs(np.einsum('ni,ni->n', axis, ray))
    elong[nnb < 6] = np.nan; ray_align[nnb < 6] = np.nan
    log(f"local PCA {time.perf_counter()-t1:.1f}s")

    # ---- floor plane (global info only, from ghost_mask.json) ----
    gm = json.load(open(GHOST))
    pn = np.array(gm["plane_n"], float); pd = float(gm["plane_d"])
    floor_h = xyz @ pn + pd                    # camera side positive (verified: cameras ~ +1.3)
    ch = camC @ pn + pd
    if np.median(ch) < 0:                      # ensure "above floor = positive"
        pn, pd = -pn, -pd; floor_h = -floor_h
    log(f"floor plane: cam heights med={np.median(camC @ pn + pd):.3f}")

    # ---- see-through (blocked corridor) on suspects only ----
    t2 = time.perf_counter()
    prelim = ((elong >= 2.5) & (ray_align >= 0.85)) | (floor_h < -0.06)
    prelim &= cam_depth > 0.6
    sus = np.flatnonzero(prelim)
    blocked_frac = np.full(nP, np.nan)
    NSAMP = 12
    for pi in sus:
        C = pose_C[prim_fid[pi]] if prim_fid[pi] in pose_C else camC[cam_tree.query(xyz[pi])[1]]
        X = xyz[pi]; L = np.linalg.norm(X - C)
        if L <= CORRIDOR_STOP + 0.3: continue
        ts = np.linspace(0.3, (L - CORRIDOR_STOP) / L, NSAMP)
        samples = C[None, :] + ts[:, None] * (X - C)[None, :]
        cnt = tree.query_ball_point(samples, CORRIDOR_R, return_length=True)
        blocked_frac[pi] = float((cnt >= CORRIDOR_MIN_NBR).mean())
    log(f"see-through on {len(sus)} suspects {time.perf_counter()-t2:.1f}s")

    np.savez_compressed(os.path.join(out, "fingerprints.npz"),
        xyz=xyz, rgb=rgb, n_support=n_support, mean_resid=mean_resid, max_resid=max_resid,
        tri_angle=tri_angle, ray=ray, ray_proxy=ray_proxy, prim_fid=prim_fid,
        cam_depth=cam_depth, elong=elong, ray_align=ray_align, nnb=nnb,
        floor_h=floor_h, blocked_frac=blocked_frac, camC=camC, cam_fids=cam_fids,
        plane_n=pn, plane_d=pd)
    info = {
        "cap": cap, "inputs": {"db": DB, "meta": META, "ply": PLY, "ply_sha256": sha256(PLY),
                                "ghost_mask_json": GHOST},
        "gauge": "production refined poses; PLY frame == meta frame (S1 probe verified); NO Sim3",
        "n_points": nP,
        "support_hist": {str(k): int((n_support == k).sum()) for k in range(6)},
        "support_ge6": int((n_support >= 6).sum()),
        "ray_proxy_pts": int(ray_proxy.sum()),
        "honesty": [
            "evidence rebuilt from sfm_live.db; not byte-exact production finalize",
            "ghost_mask.bin per-point bits NOT used (93,360 pre-filter vs 92,849 delivered => order unsafe); only global floor plane consumed",
            f"{int(ray_proxy.sum())} pts have no recoverable obs; ray = nearest-camera proxy",
            "see-through corridor uses primary/nearest camera only",
        ],
    }
    json.dump(info, open(os.path.join(out, "fingerprints_info.json"), "w"), indent=2)
    log(json.dumps(info["support_hist"]))
    return info

if __name__ == "__main__":
    for cap in (sys.argv[1:] or list(CAPS)):
        run_cap(cap)
    log("DONE")
