#!/usr/bin/env python3.11
"""
E2-B v2: RS default Max feature reprojection error = 2.0 px (VERIFIED) applied to
cap50 — track-space method (the verified one: rebuild tracks from sfm_live.db
two_view_geometries + refined production poses + multi-view DLT, median ~0.56px).

WHY v2: v1 (anchor on production PLY positions, recover obs by nearest keypoint)
was falsified — see _v1_deprecated_pointanchor/WHY_DEPRECATED.md.

METHOD:
  1. union-find over inlier two_view_geometries => tracks (verified correspondences).
  2. per track: multi-view DLT with refined production poses (poses+K frozen),
     per-OBSERVATION reprojection residual (neg depth => inf).
     VALIDATION: median per-obs residual must reproduce ~0.56px.
  3. RS-semantics gate g: delete obs with residual > g; track survives iff >=2
     surviving obs in >=2 distinct frames; RETRIANGULATE from survivors and
     iterate until stable (RS retriangulates after cull; max 5 iters).
     Sweep g in {1.5, 2.0(RS), 2.5, 3.0, 3.5, 4.0(our production BA-filter)}.
  4. Deliverables: rebuilt clouds at 2/3/4 px, true color via certified recipe
     (track obs -> full-res bilinear -> mean over surviving obs -> round),
     same production gauge (refined poses; NO Sim3, no realignment).
  5. Trail accounting on the 4px baseline cloud: Delta = survives@4px but killed
     by 2px. Signatures: SIG_ISO (d10 > 3x median = sparse trail proxy), DENSE
     (d10 < median = true-surface proxy), outside camera-XZ-hull envelope
     (mirror/glass trails extend beyond room envelope). Operating-point curve:
     trail kill rate vs dense false-kill rate per gate.

Reads ONLY frozen capture data; writes ONLY into this directory. No git ops.
"""
import sqlite3, numpy as np, json, os, time, hashlib, subprocess
from collections import defaultdict
from scipy.spatial import cKDTree, ConvexHull, Delaunay
from PIL import Image

MAX_IMAGE_ID = 2147483647
GATES = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
DELIVER = {2.0: "rs2px", 3.0: "mid3px", 4.0: "ours4px"}
BASE_GATE = 4.0
RS_GATE = 2.0
MAX_ITERS = 5
FLOOR_SLAB, COVER_SLAB, CELL_THICK, CELL_COVER = 0.06, 0.03, 0.05, 0.02

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
CAP_DIR = f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17"
OUT = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/TRAILS_rs2px_gate"
CHAIR_ROI = {"X": (0.25, 1.05), "Z": (-1.70, -0.55)}

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
    return (np.stack([data["x"],data["y"],data["z"]],1).astype(np.float64),
            np.stack([data["r"],data["g"],data["b"]],1))

def write_ply_xyzrgb(path, xyz, rgb, comment):
    n = len(xyz)
    with open(path, "wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"comment {comment}\n".encode())
        f.write(f"element vertex {n}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\n")
        f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        rec = np.empty(n, dtype=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")]))
        rec["x"],rec["y"],rec["z"] = xyz[:,0].astype("<f4"),xyz[:,1].astype("<f4"),xyz[:,2].astype("<f4")
        rec["r"],rec["g"],rec["b"] = rgb[:,0],rgb[:,1],rgb[:,2]
        rec.tofile(f)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

def detect_floor_y(xyz):
    y = xyz[:,1]
    lo, hi = np.percentile(y, [0.5, 99.5])
    bins = np.arange(lo, hi + 0.005, 0.005)
    hcount, edges = np.histogram(y, bins=bins)
    peak = np.argmax(hcount)
    y0 = 0.5*(edges[peak]+edges[peak+1])
    sel = np.abs(y - y0) <= 0.015
    return float(np.median(y[sel]))

def floor_metrics(xyz, y_floor):
    y = xyz[:,1]
    slab = np.abs(y - y_floor) <= FLOOR_SLAB
    P = xyz[slab]
    out = {"n_floor_slab": int(slab.sum())}
    if len(P) < 100:
        out.update({"thickness_med_cell_p90p10_m": None, "cover_cells_2cm": 0})
        return out
    cx = np.floor(P[:,0]/CELL_THICK).astype(np.int64)
    cz = np.floor(P[:,2]/CELL_THICK).astype(np.int64)
    key = cx*1000003 + cz
    order = np.argsort(key)
    key_s, y_s = key[order], P[order,1]
    bounds = np.flatnonzero(np.diff(key_s)) + 1
    groups = np.split(y_s, bounds)
    spreads = [float(np.percentile(g,90)-np.percentile(g,10)) for g in groups if len(g) >= 8]
    out["thickness_med_cell_p90p10_m"] = float(np.median(spreads)) if spreads else None
    out["thickness_p90_cell_m"] = float(np.percentile(spreads,90)) if spreads else None
    out["n_thickness_cells"] = len(spreads)
    tight = np.abs(P[:,1]-y_floor) <= COVER_SLAB
    Q = P[tight]
    cells = set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64), np.floor(Q[:,2]/CELL_COVER).astype(np.int64)))
    out["cover_cells_2cm"] = len(cells)
    out["cover_area_m2"] = round(len(cells)*CELL_COVER*CELL_COVER, 4)
    return out

def chair_roi_metrics(xyz, y_floor):
    m = (xyz[:,0]>=CHAIR_ROI["X"][0])&(xyz[:,0]<=CHAIR_ROI["X"][1])&(xyz[:,2]>=CHAIR_ROI["Z"][0])&(xyz[:,2]<=CHAIR_ROI["Z"][1])
    P = xyz[m]
    if len(P)==0: return {"n_roi": 0}
    y = P[:,1]
    return {"n_roi": int(len(P)), "n_roi_near_floor_5cm": int((np.abs(y-y_floor)<=0.05).sum()),
            "roi_y_p10": round(float(np.percentile(y,10)),4), "roi_y_p50": round(float(np.percentile(y,50)),4),
            "roi_y_p90": round(float(np.percentile(y,90)),4)}

def vmstat_free_gb():
    try:
        outp = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
        free = int([l for l in outp.splitlines() if l.startswith("Pages free")][0].split()[-1].rstrip("."))
        return round(free*16384/1e9, 2)
    except Exception:
        return None

def main():
    t_start = time.perf_counter()
    mem0 = vmstat_free_gb()
    DB, META, PLY = f"{CAP_DIR}/sfm_live.db", f"{CAP_DIR}/sfm_sparse_meta.json", f"{CAP_DIR}/sfm_sparse.ply"

    # ---------- db: keypoints + inlier matches -> union-find tracks ----------
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
    K = np.array([[f_,0,cx_],[0,f_,cy_],[0,0,1]])

    offset, acc = {}, 0
    for iid in img_ids: offset[iid] = acc; acc += kp_count.get(iid,0)
    N = acc
    parent = np.arange(N, dtype=np.int64)
    def find(x):
        root = x
        while parent[root] != root: root = parent[root]
        while parent[x] != root: parent[x], x = root, parent[x]
        return root
    n_pairs = n_edges = 0
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
            n_edges += 1
        n_pairs += 1
    db.close()
    for x in range(N): find(x)
    roots = parent
    log(f"db: pairs={n_pairs} inlier_edges={n_edges} kp_nodes={N}")

    meta = json.load(open(META))
    assert meta.get("refined") is True
    pose_R, pose_t, pose_C, Pmat = {}, {}, {}, {}
    for p in meta["poses"]:
        if not p.get("registered"): continue
        R = quat_to_R(np.array(p["quat_wxyz"], float)); t = np.array(p["t"], float)
        fid = p["frame_id"]
        pose_R[fid], pose_t[fid] = R, t
        pose_C[fid] = -R.T @ t
        Pmat[fid] = K @ np.hstack([R, t.reshape(3,1)])

    # node -> (fid, xy)
    iid_of_node = np.zeros(N, np.int64)
    for iid in img_ids:
        iid_of_node[offset[iid]:offset[iid]+kp_count[iid]] = iid

    comp = defaultdict(list)
    order = np.argsort(roots, kind="stable")
    rs = roots[order]
    bounds = np.flatnonzero(np.diff(rs)) + 1
    for grp in np.split(order, bounds):
        if len(grp) >= 2:
            comp[int(rs_val := roots[grp[0]])] = grp
    log(f"components(>=2 nodes)={len(comp)}")

    # ---------- build track obs ----------
    tracks = []  # list of (fids np.int32[], xy np.float64[n,2])
    for root, nodes in comp.items():
        fids, xys = [], []
        for nd in nodes:
            iid = int(iid_of_node[nd]); fid = iid - 1
            if fid not in pose_R: continue
            fids.append(fid); xys.append(kp_xy[iid][nd - offset[iid]])
        if len(set(fids)) < 2: continue
        tracks.append((np.array(fids, np.int32), np.array(xys)))
    nT = len(tracks)
    log(f"tracks with >=2 posed distinct frames: {nT}")

    # ---------- triangulate + iterate per gate ----------
    def dlt(fids, xys):
        A = np.empty((2*len(fids), 4))
        for i,(fid,xy) in enumerate(zip(fids,xys)):
            P = Pmat[fid]
            A[2*i]   = xy[0]*P[2] - P[0]
            A[2*i+1] = xy[1]*P[2] - P[1]
        _,_,Vt = np.linalg.svd(A, full_matrices=False)
        Xh = Vt[-1]
        if abs(Xh[3]) < 1e-12: return None
        return Xh[:3]/Xh[3]

    def residuals(X, fids, xys):
        res = np.empty(len(fids))
        for i,(fid,xy) in enumerate(zip(fids,xys)):
            Xc = pose_R[fid] @ X + pose_t[fid]
            if Xc[2] <= 0: res[i] = np.inf; continue
            u,v = f_*Xc[0]/Xc[2]+cx_, f_*Xc[1]/Xc[2]+cy_
            res[i] = np.hypot(u-xy[0], v-xy[1])
        return res

    t0 = time.perf_counter()
    init_X = np.full((nT,3), np.nan)
    init_res_list = []
    track_init = []   # (X, fids, xys, res)
    for fids, xys in tracks:
        X = dlt(fids, xys)
        if X is None:
            track_init.append(None); init_res_list.append(None); continue
        r = residuals(X, fids, xys)
        track_init.append((X, fids, xys, r))
        init_res_list.append(r)
    all_init_res = np.concatenate([r for r in init_res_list if r is not None])
    finite = all_init_res[np.isfinite(all_init_res)]
    med_res = float(np.median(finite))
    log(f"init DLT wall={time.perf_counter()-t0:.1f}s  per-obs residual median={med_res:.3f}px (validation target ~0.56px)  p90={np.percentile(finite,90):.2f}px  inf_frac={100*(~np.isfinite(all_init_res)).mean():.2f}%")

    def survive(gate):
        Xs = np.full((nT,3), np.nan)
        alive = np.zeros(nT, bool)
        n_obs_final = np.zeros(nT, np.int16)
        for ti, tr in enumerate(track_init):
            if tr is None: continue
            X, fids, xys, r = tr
            for _ in range(MAX_ITERS):
                keep = r <= gate
                if len(set(fids[keep].tolist())) < 2:
                    break
                if keep.all():
                    alive[ti] = True; Xs[ti] = X; n_obs_final[ti] = len(fids)
                    break
                fids2, xys2 = fids[keep], xys[keep]
                X2 = dlt(fids2, xys2)
                if X2 is None: break
                fids, xys = fids2, xys2
                X = X2
                r = residuals(X, fids, xys)
            else:
                keep = r <= gate
                if len(set(fids[keep].tolist())) >= 2 and keep.all():
                    alive[ti] = True; Xs[ti] = X; n_obs_final[ti] = len(fids)
        return alive, Xs, n_obs_final

    surv = {}
    for g in GATES:
        t1 = time.perf_counter()
        alive, Xs, nobs = survive(g)
        surv[g] = (alive, Xs, nobs)
        log(f"gate {g}px: tracks alive={int(alive.sum())}/{nT} ({100*alive.mean():.1f}%)  wall={time.perf_counter()-t1:.1f}s")

    # ---------- production reference / gauge ----------
    prod_xyz, prod_rgb = read_ply_xyzrgb(PLY)
    y_floor = detect_floor_y(prod_xyz)
    prod_fl = floor_metrics(prod_xyz, y_floor)
    prod_roi = chair_roi_metrics(prod_xyz, y_floor)

    aliveB, XB, _ = surv[BASE_GATE]
    alive2, X2_, _ = surv[RS_GATE]
    baseline_pts = XB[aliveB]
    delta_mask = aliveB & ~alive2          # killed by RS 2px, kept by our 4px
    delta_pts = XB[delta_mask]
    log(f"baseline(4px)={len(baseline_pts)}  RS(2px)={int(alive2.sum())}  Delta killed-by-2px={int(delta_mask.sum())}")

    # sanity: rebuilt 4px cloud vs production cloud NN
    ptree = cKDTree(prod_xyz)
    dd_prod, _ = ptree.query(baseline_pts, k=1, workers=-1)
    sanity = {"rebuilt4_n": int(len(baseline_pts)), "prod_n": int(len(prod_xyz)),
              "nn_to_prod_p50_mm": round(float(np.percentile(dd_prod,50))*1000,1),
              "nn_to_prod_p90_mm": round(float(np.percentile(dd_prod,90))*1000,1)}
    log("sanity", sanity)

    # ---------- trail signatures on baseline(4px) cloud ----------
    btree = cKDTree(baseline_pts)
    d10 = btree.query(baseline_pts, k=11, workers=-1)[0][:, 10]
    med_d10 = float(np.median(d10))
    SIG_ISO = d10 > 3.0*med_d10
    DENSE = d10 < med_d10
    cams = np.array([pose_C[f] for f in pose_C])
    cam_xz = cams[:, [0,2]]
    hull = ConvexHull(cam_xz)
    hull_xy = cam_xz[hull.vertices]
    dela = Delaunay(hull_xy)
    b_xz = baseline_pts[:, [0,2]]
    inside = dela.find_simplex(b_xz) >= 0
    seg_d = np.full(len(baseline_pts), np.inf)
    for i in range(len(hull_xy)):
        a, b = hull_xy[i], hull_xy[(i+1) % len(hull_xy)]
        ab = b - a
        tpar = np.clip(((b_xz - a) @ ab)/(ab @ ab), 0, 1)
        seg_d = np.minimum(seg_d, np.linalg.norm(b_xz - (a + tpar[:,None]*ab), axis=1))
    out_dist = np.where(inside, 0.0, seg_d)

    delta_in_base = delta_mask[aliveB]     # mask over baseline_pts rows
    # per-gate accounting relative to baseline cloud
    gate_stats = {}
    for g in GATES:
        aliveG = surv[g][0]
        killG = aliveB & ~aliveG
        kb = killG[aliveB]                 # over baseline_pts
        cand = surv[g][1][surv[g][0]]
        fl = floor_metrics(cand, y_floor)
        roi = chair_roi_metrics(cand, y_floor)
        gate_stats[str(g)] = {
            "alive_tracks": int(aliveG.sum()),
            "survival_vs_4px_pct": round(100.0*aliveG.sum()/max(1,aliveB.sum()), 2),
            "killed_vs_4px": int(kb.sum()),
            "trail_kill_rate_pct": round(100.0*(kb & SIG_ISO).sum()/max(1,SIG_ISO.sum()), 2),
            "dense_false_kill_pct": round(100.0*(kb & DENSE).sum()/max(1,DENSE.sum()), 3),
            "outside_hull_kill_pct": round(100.0*(kb & ~inside).sum()/max(1,(~inside).sum()), 2),
            "inside_hull_kill_pct": round(100.0*(kb & inside).sum()/max(1,inside.sum()), 2),
            "ruler_2_floor": fl, "ruler_3_roi": roi,
        }

    # cull-fraction curves at RS gate
    env_curve, iso_curve = [], []
    for lo, hi in zip([0.0,1e-9,0.1,0.25,0.5,1.0,2.0], [1e-9,0.1,0.25,0.5,1.0,2.0,100.0]):
        m = (out_dist >= lo) & (out_dist < hi)
        if m.sum() == 0: continue
        env_curve.append({"outside_m": f"[{lo:.2f},{hi:.2f})", "n": int(m.sum()),
                          "killed_by_2px_pct": round(100.0*(delta_in_base & m).sum()/m.sum(),2)})
    for lo, hi in zip([0,1,2,3,5,8], [1,2,3,5,8,10**9]):
        m = (d10 >= lo*med_d10) & (d10 < hi*med_d10)
        if m.sum() == 0: continue
        iso_curve.append({"d10_over_med": f"[{lo},{hi})", "n": int(m.sum()),
                          "killed_by_2px_pct": round(100.0*(delta_in_base & m).sum()/m.sum(),2)})

    # ---------- colorize (certified recipe: track obs, full-res bilinear, mean, round) ----------
    t2 = time.perf_counter()
    fed = {}
    with open(f"{CAP_DIR}/sfm_fed_frames.jsonl") as fh:
        for line in fh:
            j = json.loads(line)
            fed[j["frameId"]] = os.path.basename(j["jpegPath"])
    # gather sampling requests per frame for each deliverable gate
    deliver_alive = {g: surv[g][0] for g in DELIVER}
    # track surviving obs per gate: rerun survive bookkeeping cheaply — reuse final obs by re-deriving
    # (we stored only X; recompute surviving obs sets for deliverable gates)
    def surviving_obs(gate):
        outm = {}
        for ti, tr in enumerate(track_init):
            if tr is None or not surv[gate][0][ti]: continue
            X, fids, xys, r = tr
            for _ in range(MAX_ITERS):
                keep = r <= gate
                if keep.all(): break
                fids2, xys2 = fids[keep], xys[keep]
                X2 = dlt(fids2, xys2)
                if X2 is None: break
                fids, xys = fids2, xys2; X = X2
                r = residuals(X, fids, xys)
            outm[ti] = (fids, xys)
        return outm
    obs_by_gate = {g: surviving_obs(g) for g in DELIVER}
    req = defaultdict(list)   # fid -> list of (gate, ti, xy)
    for g, om in obs_by_gate.items():
        for ti, (fids, xys) in om.items():
            for fid, xy in zip(fids, xys):
                req[int(fid)].append((g, ti, xy))
    acc_rgb = {g: defaultdict(lambda: np.zeros(3)) for g in DELIVER}
    acc_n = {g: defaultdict(int) for g in DELIVER}
    n_missing_img = 0
    for fid in sorted(req):
        name = fed.get(fid)
        path = f"{CAP_DIR}/photos_highres/{name}" if name else None
        if not path or not os.path.exists(path):
            n_missing_img += 1; continue
        im = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
        h, w = im.shape[:2]
        sx, sy = w / W, h / H
        for g, ti, xy in req[fid]:
            x, y = xy[0]*sx, xy[1]*sy
            x0, y0 = int(np.floor(x)), int(np.floor(y))
            if x0 < 0 or y0 < 0 or x0+1 >= w or y0+1 >= h:
                x0 = min(max(x0,0), w-2); y0 = min(max(y0,0), h-2)
                x = min(max(x,0), w-1.0); y = min(max(y,0), h-1.0)
            fx, fy = x-x0, y-y0
            c = (im[y0,x0]*(1-fx)*(1-fy) + im[y0,x0+1]*fx*(1-fy)
                 + im[y0+1,x0]*(1-fx)*fy + im[y0+1,x0+1]*fx*fy)
            acc_rgb[g][ti] += c; acc_n[g][ti] += 1
    log(f"colorize wall={time.perf_counter()-t2:.1f}s missing_imgs={n_missing_img}")

    outputs = {}
    cloud_by_gate = {}
    for g, name in DELIVER.items():
        alive, Xs, _ = surv[g]
        idx = np.flatnonzero(alive)
        pts = Xs[idx]
        cols = np.zeros((len(idx),3), np.uint8)
        miss = 0
        for row, ti in enumerate(idx):
            n = acc_n[g].get(int(ti), 0)
            if n == 0:
                cols[row] = (128,128,128); miss += 1
            else:
                cols[row] = np.clip(np.round(acc_rgb[g][int(ti)]/n), 0, 255).astype(np.uint8)
        cloud_by_gate[g] = (pts, cols)
        p = os.path.join(OUT, f"{name}_cap50.ply")
        write_ply_xyzrgb(p, pts, cols,
            f"E2-B v2 cap50 gate={g}px RS-semantics (per-obs cull + retriangulate, >=2 obs survive); rebuilt tracks, refined production poses, same gauge, true color certified recipe")
        outputs[os.path.basename(p)] = sha256(p)
        log(f"wrote {name}: {len(pts)} pts (uncolored fallback {miss})")

    # diff cloud: baseline 4px points, gray=survives 2px, red=killed by 2px
    difc = np.full((len(baseline_pts),3), 110, np.uint8)
    difc[delta_in_base] = (255, 32, 32)
    p = os.path.join(OUT, "diff_killedby2px_cap50.ply")
    write_ply_xyzrgb(p, baseline_pts, difc, "E2-B v2 diff: baseline=rebuilt@4px; red=killed by RS 2.0px gate, gray=survives")
    outputs[os.path.basename(p)] = sha256(p)

    np.savez_compressed(os.path.join(OUT, "render_arrays_v2.npz"),
        prod_xyz=prod_xyz, prod_rgb=prod_rgb,
        base_pts=baseline_pts, base_rgb=cloud_by_gate[BASE_GATE][1],
        rs_pts=cloud_by_gate[RS_GATE][0], rs_rgb=cloud_by_gate[RS_GATE][1],
        delta_in_base=delta_in_base, d10=d10, out_dist=out_dist,
        SIG_ISO=SIG_ISO, DENSE=DENSE, cams=cams, hull_xy=hull_xy, y_floor=y_floor)

    stats = {
        "experiment": "E2-B v2: RS 2.0px reprojection gate (track-space, verified method) on cap50",
        "rs_key": "RS Max feature reprojection error = 2.0px (VERIFIED official default) vs ours 4px BA-post filter / 10px live create",
        "inputs": {"db": DB, "meta": META, "prod_ply": PLY, "prod_ply_sha256": sha256(PLY)},
        "gauge": "refined production poses, PLY frame == meta frame (S1 probe), NO Sim3/realignment; all clouds same gauge",
        "method": {
            "tracks": "union-find over inlier two_view_geometries; >=2 posed distinct frames",
            "triangulation": "multi-view DLT, poses+K frozen; per-obs residual; neg depth = inf",
            "gate_rule": "obs>gate deleted -> retriangulate from survivors -> iterate (max 5); survive iff >=2 obs in >=2 frames all within gate",
            "colors": "certified recipe: surviving track obs, full-res bilinear, mean, round",
        },
        "validation": {
            "per_obs_residual_median_px": round(med_res,3), "target": "~0.56px (previously verified method)",
            "per_obs_residual_p90_px": round(float(np.percentile(finite,90)),3),
            "n_tracks": nT, "n_obs_total": int(len(all_init_res)),
            "rebuilt4_vs_prod_nn": sanity,
        },
        "trail_signature": {
            "basis": "baseline = rebuilt@4px cloud",
            "SIG_ISO_def": f"d10 > 3x median ({3*med_d10*1000:.1f}mm)", "SIG_ISO_n": int(SIG_ISO.sum()),
            "DENSE_def": f"d10 < median ({med_d10*1000:.1f}mm)", "DENSE_n": int(DENSE.sum()),
            "outside_camera_hull_n": int((~inside).sum()),
            "note": "self-computed simple signature (E2-A trail set not yet available for reconciliation)",
        },
        "headline_delta_2px_vs_4px": {
            "baseline_4px_pts": int(aliveB.sum()), "rs_2px_pts": int(alive2.sum()),
            "killed_by_2px": int(delta_mask.sum()),
            "killed_pct_of_baseline": round(100.0*delta_mask.sum()/max(1,aliveB.sum()),2),
        },
        "production_reference": {"n_points": len(prod_xyz), "y_floor": round(y_floor,4),
                                 "floor": prod_fl, "chair_roi": prod_roi},
        "gate_sweep": gate_stats,
        "killed_by_2px_vs_outside_envelope": env_curve,
        "killed_by_2px_vs_isolation": iso_curve,
        "wallclock": {"total_host_s": round(time.perf_counter()-t_start,1), "note": "host python proxy, NOT device"},
        "mem_free_gb": {"start": mem0, "end": vmstat_free_gb()},
        "honesty": [
            "Track rebuild from sfm_live.db (union-find transitive merge) is NOT byte-exact production track identity; validated instead by per-obs residual median vs prior verified 0.56px and rebuilt@4px vs production-cloud NN distance.",
            "Gate rule is one variable only (reprojection); production creation also has tri-angle/floater gates — rebuilt@4px is the like-for-like control, production PLY is context, not the control.",
            "Positions are gate-specific retriangulations (RS retriangulates after cull); Delta analysis uses baseline(4px) positions.",
            "Trail signature is self-computed (isolation + camera-XZ-hull envelope); must be reconciled with E2-A trail set when it lands.",
            "Wall clocks host-only python proxies.",
        ],
        "outputs": outputs,
    }
    json.dump(stats, open(os.path.join(OUT, "stats_v2.json"), "w"), indent=2)
    log("DONE total wall=%.1fs" % (time.perf_counter()-t_start))

if __name__ == "__main__":
    main()
