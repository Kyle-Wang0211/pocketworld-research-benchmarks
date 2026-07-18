#!/usr/bin/env python3.11
"""
S1 first knife prototype: unified 2-view point lifecycle (RS discipline, Q1=Case A adjudicated).

Rule (R2 Case A + #13 replacement, ONE ruler for ALL 2-view points, provenance-blind):
  1. structure-only refit: re-triangulate (DLT) the point from its two recovered
     observations + refined production poses (poses/intrinsics frozen).
  2. cull: negative depth (either view) OR post-refit reproj > 3.0 px (either view)
     OR parallax angle theta < 2.0 deg at refit position (production floater gate).
  3. provenance-blind: temporal-window vs spatial/far-time is NOT a criterion.
     Same ruler replaces #13 (kill-by-provenance): far-time 2-view points that pass
     geometry survive; near-time low-parallax points that fail geometry die.

Candidate cloud = production PLY; multi-view points untouched; 2-view points
keep/cull by the rule (survivors keep their production position+color — the rule
re-adjudicates life/death, it does not re-position); points whose observations
cannot be recovered from the db are kept + honestly reported.

OBSERVATION RECOVERY (key methodology, v2):
  Production PLY has no provenance/track labels. Position-NN matching against
  rebuilt-track DLT positions FAILED (probe_gauge.py: no gauge rotation, but
  ~1cm along-ray depth-ambiguity scatter => NN in 3D is not point identity).
  Instead we recover each production point's observations in OBSERVATION SPACE:
  project the point into every registered frame (refined poses, frozen K) and
  collect verified-matched keypoints (keypoints participating in >=1 inlier
  two_view_geometries match) within REPROJ gate of the projection.
    n_support_frames >= 3  -> multiview, keep untouched
    n_support_frames == 2  -> 2-view; if the two keypoints are transitively
                              matched (same union-find component => real
                              cross-frame correspondence, RS-1) -> apply rule;
                              else keep + report (evidence not reconstructible)
    n_support_frames <  2  -> keep + honestly report (obs not recoverable)

HONEST APPROXIMATION (declared): this rebuilds evidence from sfm_live.db, it is
NOT the byte-exact production finalize path. Support radius = 3px can absorb a
neighboring feature and misclassify a true 2-view point as multiview; that errs
toward KEEP (status quo), never toward extra culling.

Reads ONLY frozen capture data; writes ONLY into this experiment directory.
"""
import sqlite3, numpy as np, json, os, sys, time, hashlib
from collections import defaultdict
from scipy.spatial import cKDTree

MAX_IMAGE_ID = 2147483647
REPROJ_GATE_PX = 3.0          # RS-3 / production temporal-detail gate; also support radius
THETA_GATE_DEG = 2.0          # production floater/creation min angle (not invented)
FLOOR_SLAB = 0.06             # m, band around detected floor for thickness proxy
COVER_SLAB = 0.03             # m, band for coverage cells
CELL_THICK = 0.05             # m, XZ cell for per-cell thickness
CELL_COVER = 0.02             # m, XZ cell for coverage

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
CAPS = {
    "cap50": {
        "dir": f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17",
        "chair_roi": {"X": (0.25, 1.05), "Z": (-1.70, -0.55)},  # from 06_glomap_alias (frozen)
    },
    "cap51": {
        "dir": f"{ROOT}/data/pocketworld_captures/cap51/device_full_pull_2026-07-17",
        "chair_roi": None,
    },
}
OUT_BASE = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/S1_twoview_lifecycle"

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

def write_ply_xyzrgb(path, xyz, rgb, comment):
    n = len(xyz)
    with open(path, "wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"comment {comment}\n".encode())
        f.write(f"element vertex {n}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\n")
        f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        rec = np.empty(n, dtype=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")]))
        rec["x"], rec["y"], rec["z"] = xyz[:,0].astype("<f4"), xyz[:,1].astype("<f4"), xyz[:,2].astype("<f4")
        rec["r"], rec["g"], rec["b"] = rgb[:,0], rgb[:,1], rgb[:,2]
        rec.tofile(f)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.hexdigest()

# ---------------- floor / coverage metrics (same ruler both clouds) ----------------
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
        out.update({"thickness_med_cell_p90p10_m": None, "thickness_global_std_m": None, "cover_cells_2cm": 0})
        return out
    cx = np.floor(P[:,0]/CELL_THICK).astype(np.int64)
    cz = np.floor(P[:,2]/CELL_THICK).astype(np.int64)
    key = cx * 1000003 + cz
    order = np.argsort(key)
    key_s, y_s = key[order], P[order,1]
    bounds = np.flatnonzero(np.diff(key_s)) + 1
    groups = np.split(y_s, bounds)
    spreads = [float(np.percentile(g,90) - np.percentile(g,10)) for g in groups if len(g) >= 8]
    out["thickness_med_cell_p90p10_m"] = float(np.median(spreads)) if spreads else None
    out["thickness_p90_cell_m"] = float(np.percentile(spreads,90)) if spreads else None
    out["n_thickness_cells"] = len(spreads)
    out["thickness_global_std_m"] = float(np.std(P[:,1]))
    tight = np.abs(P[:,1] - y_floor) <= COVER_SLAB
    Q = P[tight]
    cells = set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64), np.floor(Q[:,2]/CELL_COVER).astype(np.int64)))
    out["cover_cells_2cm"] = len(cells)
    out["cover_area_m2"] = round(len(cells) * CELL_COVER * CELL_COVER, 4)
    return out

def chair_roi_metrics(xyz, roi, y_floor):
    if roi is None: return None
    m = (xyz[:,0]>=roi["X"][0])&(xyz[:,0]<=roi["X"][1])&(xyz[:,2]>=roi["Z"][0])&(xyz[:,2]<=roi["Z"][1])
    P = xyz[m]
    if len(P)==0: return {"n_roi": 0}
    y = P[:,1]
    near_floor = np.abs(y - y_floor) <= 0.05
    return {"n_roi": int(len(P)),
            "n_roi_near_floor_5cm": int(near_floor.sum()),
            "frac_roi_near_floor": round(float(near_floor.mean()),4),
            "roi_y_p10": float(np.percentile(y,10)), "roi_y_p50": float(np.percentile(y,50)),
            "roi_y_p90": float(np.percentile(y,90))}

# ---------------- main per-cap pipeline ----------------
def run_cap(cap, cfg):
    d = cfg["dir"]
    out = os.path.join(OUT_BASE, cap)
    os.makedirs(out, exist_ok=True)
    DB, META, PLY = f"{d}/sfm_live.db", f"{d}/sfm_sparse_meta.json", f"{d}/sfm_sparse.ply"

    log(f"=== {cap} ===")
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c = db.cursor()
    img_ids = sorted(i for (i,) in c.execute("SELECT image_id FROM images"))
    kp_xy, kp_count = {}, {}
    for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
        arr = np.frombuffer(data, dtype=np.float32).reshape(r, cols)
        kp_xy[iid] = np.ascontiguousarray(arr[:, :2].astype(np.float64)); kp_count[iid] = r
    cam = c.execute("SELECT model,params,width,height FROM cameras LIMIT 1").fetchone()
    params = np.frombuffer(cam[1], dtype=np.float64)
    assert len(params) == 3, f"expected SIMPLE_PINHOLE 3 params, got {len(params)}"
    f_, cx_, cy_ = params
    W, H = cam[2], cam[3]
    K = np.array([[f_,0,cx_],[0,f_,cy_],[0,0,1]])

    # union-find over verified inlier matches (verified-correspondence membership, RS-1)
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
    uniq, counts = np.unique(roots, return_counts=True)
    comp_size = dict(zip(uniq.tolist(), counts.tolist()))
    log(f"pairs={n_pairs} edges={n_edges} nodes={N}")

    # poses (refined, production gauge)
    meta = json.load(open(META))
    assert meta.get("refined") is True
    pose_R, pose_t, pose_C = {}, {}, {}
    for p in meta["poses"]:
        if not p.get("registered"): continue
        R = quat_to_R(np.array(p["quat_wxyz"], float)); t = np.array(p["t"], float)
        fid = p["frame_id"]; pose_R[fid], pose_t[fid] = R, t; pose_C[fid] = -R.T @ t

    xyz, rgb = read_ply_xyzrgb(PLY)
    nP = len(xyz)

    # ------- observation recovery in observation space -------
    # per-frame KDTree over MATCHED keypoints (component size >= 2)
    t0 = time.perf_counter()
    frame_trees, frame_nodes = {}, {}
    for iid in img_ids:
        fid = iid - 1
        if fid not in pose_R: continue
        base = offset[iid]
        nodes = np.arange(base, base + kp_count[iid])
        matched_mask = counts[np.searchsorted(uniq, roots[nodes])] >= 2
        nodes = nodes[matched_mask]
        if len(nodes) == 0: continue
        frame_trees[fid] = cKDTree(kp_xy[iid][nodes - base])
        frame_nodes[fid] = nodes

    # support accumulation: for each prod point, best keypoint node per frame within gate
    support_frames = [[] for _ in range(nP)]   # list of (fid, node, resid, u, v)
    for fid in sorted(frame_trees):
        R, t = pose_R[fid], pose_t[fid]
        Xc = xyz @ R.T + t
        infront = Xc[:,2] > 1e-6
        uv = np.full((nP,2), -1e9)
        z = Xc[infront,2]
        uv[infront,0] = f_*Xc[infront,0]/z + cx_
        uv[infront,1] = f_*Xc[infront,1]/z + cy_
        inimg = infront & (uv[:,0]>=-REPROJ_GATE_PX) & (uv[:,0]<=W+REPROJ_GATE_PX) & (uv[:,1]>=-REPROJ_GATE_PX) & (uv[:,1]<=H+REPROJ_GATE_PX)
        q_idx = np.flatnonzero(inimg)
        if len(q_idx)==0: continue
        dd, kk = frame_trees[fid].query(uv[q_idx], k=1, distance_upper_bound=REPROJ_GATE_PX, workers=-1)
        hit = np.isfinite(dd)
        for pi, dist_px, ki in zip(q_idx[hit], dd[hit], kk[hit]):
            node = int(frame_nodes[fid][ki])
            support_frames[pi].append((fid, node, float(dist_px)))
    t_support = time.perf_counter() - t0
    log(f"support recovery wall={t_support:.1f}s")

    n_support = np.array([len(s) for s in support_frames])

    # ------- adjudicate -------
    t1 = time.perf_counter()
    verdict = np.array(["keep_multiview"]*nP, dtype=object)
    theta_arr = np.full(nP, np.nan)
    refit_res = np.full(nP, np.nan)
    refit_disp = np.full(nP, np.nan)
    verdict[n_support <= 1] = "keep_unmatched_honest"
    two_idx = np.flatnonzero(n_support == 2)
    n_unverified_pair = 0
    for pi in two_idx:
        (f1, nd1, _), (f2, nd2, _) = support_frames[pi]
        if roots[nd1] != roots[nd2]:
            verdict[pi] = "keep_unverified_pair_honest"; n_unverified_pair += 1
            continue
        # structure-only refit: DLT from the two obs, frozen refined poses
        iid1, iid2 = f1+1, f2+1
        xy1 = kp_xy[iid1][nd1 - offset[iid1]]
        xy2 = kp_xy[iid2][nd2 - offset[iid2]]
        A = []
        for fid, xy in ((f1,xy1),(f2,xy2)):
            P = K @ np.hstack([pose_R[fid], pose_t[fid].reshape(3,1)])
            A.append(xy[0]*P[2] - P[0]); A.append(xy[1]*P[2] - P[1])
        _,_,Vt = np.linalg.svd(np.array(A))
        Xh = Vt[-1]
        if abs(Xh[3]) < 1e-12:
            verdict[pi] = "cull_neg_depth"; continue
        X = Xh[:3]/Xh[3]
        refit_disp[pi] = float(np.linalg.norm(X - xyz[pi]))
        ok, reason, maxres = True, None, 0.0
        for fid, xy in ((f1,xy1),(f2,xy2)):
            Xc = pose_R[fid] @ X + pose_t[fid]
            if Xc[2] <= 0: ok, reason = False, "neg_depth"; break
            u, v = f_*Xc[0]/Xc[2]+cx_, f_*Xc[1]/Xc[2]+cy_
            maxres = max(maxres, float(np.hypot(u-xy[0], v-xy[1])))
        refit_res[pi] = maxres
        if ok and maxres > REPROJ_GATE_PX: ok, reason = False, "reproj_gt3px"
        if ok:
            v1, v2 = X - pose_C[f1], X - pose_C[f2]
            cosang = np.dot(v1,v2)/(np.linalg.norm(v1)*np.linalg.norm(v2)+1e-15)
            th = float(np.degrees(np.arccos(np.clip(cosang,-1,1))))
            theta_arr[pi] = th
            if th < THETA_GATE_DEG: ok, reason = False, "theta_lt2deg"
        verdict[pi] = "keep_2view_pass" if ok else f"cull_{reason}"
    refit_wall_s = time.perf_counter() - t1
    log(f"2-view adjudication wall={refit_wall_s:.1f}s over {len(two_idx)} candidates")

    keep_mask = ~np.char.startswith(verdict.astype(str), "cull_")
    cand, cand_rgb = xyz[keep_mask], rgb[keep_mask]
    keep2 = verdict == "keep_2view_pass"
    cull2 = ~keep_mask

    ply_out = os.path.join(out, f"s1_caseA_{cap}.ply")
    write_ply_xyzrgb(ply_out, cand, cand_rgb, f"S1 caseA candidate {cap}: unified 2-view lifecycle (obs-recovered refit + 3px + 2deg, provenance-blind); positions/colors = production, culls only")

    dif_rgb = np.zeros((nP,3), np.uint8); dif_rgb[:] = (120,120,120)
    dif_rgb[keep2] = (0,220,0); dif_rgb[cull2] = (255,40,40)
    write_ply_xyzrgb(os.path.join(out, f"diff_{cap}.ply"), xyz, dif_rgb,
                     f"S1 diff {cap}: green=2view kept, red=2view culled, gray=multiview/unrecovered")

    # rescue analysis: verified 2-node components passing the same rule, absent from prod cloud
    t2 = time.perf_counter()
    rescue_pos = []
    pair_members = defaultdict(list)
    for node in np.flatnonzero(counts[np.searchsorted(uniq, roots)] == 2):
        pair_members[int(roots[node])].append(int(node))
    node_iid_of = lambda nd: img_ids[np.searchsorted(np.array([offset[i] for i in img_ids] + [N]), nd, side="right") - 1]
    off_list = np.array([offset[i] for i in img_ids] + [N], dtype=np.int64)
    iid_list = np.array(img_ids, dtype=np.int64)
    ptree = cKDTree(xyz)
    n_pair_pass = 0
    for rt, nds in pair_members.items():
        if len(nds) != 2: continue
        j1, j2 = (np.searchsorted(off_list, nd, side="right")-1 for nd in nds)
        iid1, iid2 = int(iid_list[j1]), int(iid_list[j2])
        if iid1 == iid2: continue
        f1, f2 = iid1-1, iid2-1
        if f1 not in pose_R or f2 not in pose_R: continue
        xy1 = kp_xy[iid1][nds[0]-offset[iid1]]; xy2 = kp_xy[iid2][nds[1]-offset[iid2]]
        A = []
        for fid, xy in ((f1,xy1),(f2,xy2)):
            P = K @ np.hstack([pose_R[fid], pose_t[fid].reshape(3,1)])
            A.append(xy[0]*P[2]-P[0]); A.append(xy[1]*P[2]-P[1])
        _,_,Vt = np.linalg.svd(np.array(A)); Xh = Vt[-1]
        if abs(Xh[3]) < 1e-12: continue
        X = Xh[:3]/Xh[3]
        ok = True; maxres = 0.0
        for fid, xy in ((f1,xy1),(f2,xy2)):
            Xc = pose_R[fid] @ X + pose_t[fid]
            if Xc[2] <= 0: ok = False; break
            u,v = f_*Xc[0]/Xc[2]+cx_, f_*Xc[1]/Xc[2]+cy_
            maxres = max(maxres, float(np.hypot(u-xy[0], v-xy[1])))
        if not ok or maxres > REPROJ_GATE_PX: continue
        v1, v2 = X-pose_C[f1], X-pose_C[f2]
        th = float(np.degrees(np.arccos(np.clip(np.dot(v1,v2)/(np.linalg.norm(v1)*np.linalg.norm(v2)+1e-15),-1,1))))
        if th < THETA_GATE_DEG: continue
        n_pair_pass += 1
        dd, _ = ptree.query(X, k=1)
        if dd > 0.02: rescue_pos.append(X)
    rescue_pos = np.array(rescue_pos) if rescue_pos else np.zeros((0,3))
    write_ply_xyzrgb(os.path.join(out, f"rescue_candidates_{cap}.ply"), rescue_pos,
                     np.tile(np.array([[0,160,255]],np.uint8), (len(rescue_pos),1)),
                     f"S1 {cap}: verified 2-view pairs passing unified rule, absent from production PLY (NOT injected)")
    log(f"rescue analysis wall={time.perf_counter()-t2:.1f}s")

    # ---- four rulers ----
    y_floor = detect_floor_y(xyz)
    base_fl = floor_metrics(xyz, y_floor)
    cand_fl = floor_metrics(cand, y_floor)
    base_roi = chair_roi_metrics(xyz, cfg["chair_roi"], y_floor)
    cand_roi = chair_roi_metrics(cand, cfg["chair_roi"], y_floor)

    def q(a, pcts=(10,50,90)):
        a = np.asarray(a, float); a = a[np.isfinite(a)]
        return {f"p{p}": round(float(np.percentile(a,p)),4) for p in pcts} if len(a) else {}

    vc = {v: int((verdict==v).sum()) for v in sorted(set(verdict.tolist()))}
    stats = {
        "cap": cap,
        "inputs": {"db": DB, "meta": META, "baseline_ply": PLY, "baseline_ply_sha256": sha256(PLY)},
        "gauge": "production refined poses/frame; PLY frame == meta pose frame (probe_gauge: rotation 0.11deg, residual unchanged => same gauge); NO Sim3, NO realignment",
        "rule": {"refit": "structure-only DLT from 2 recovered obs, poses+K frozen (refined production)",
                 "reproj_gate_px": REPROJ_GATE_PX, "theta_gate_deg": THETA_GATE_DEG,
                 "provenance_blind": True,
                 "replaces": ["R2#6 temporal-detail publish-without-BA", "R2#13 kill-by-provenance (frame-gap)"],
                 "survivor_position": "production position kept (rule re-adjudicates life/death only)"},
        "obs_recovery": {"method": "project prod point into all registered frames; verified-matched keypoint within 3px = support obs",
                         "n_pairs_db": n_pairs, "n_inlier_edges": n_edges,
                         "support_frames_hist": {str(k): int((n_support==k).sum()) for k in range(0, 8)},
                         "support_frames_ge8": int((n_support>=8).sum()),
                         "wall_s": round(t_support,1)},
        "verdicts": vc,
        "cull_total": int(cull2.sum()),
        "quality_of_adjudication": {
            "theta_deg_2view": q(theta_arr), "refit_maxres_px_2view": q(refit_res),
            "refit_disp_m_2view": q(refit_disp),
            "n_unverified_pair": n_unverified_pair},
        "rescue": {"n_verified_pairs_passing_rule": n_pair_pass,
                   "n_absent_from_prod_not_injected": int(len(rescue_pos))},
        "ruler_1_points": {"baseline": nP, "candidate": int(len(cand)),
                           "delta": int(len(cand)-nP), "delta_pct": round(100.0*(len(cand)-nP)/nP,2)},
        "ruler_2_floor_thickness": {"y_floor": round(y_floor,4), "baseline": base_fl, "candidate": cand_fl},
        "ruler_3_coverage": {"baseline_cells_2cm": base_fl.get("cover_cells_2cm"),
                             "candidate_cells_2cm": cand_fl.get("cover_cells_2cm"),
                             "baseline_area_m2": base_fl.get("cover_area_m2"),
                             "candidate_area_m2": cand_fl.get("cover_area_m2")},
        "ruler_4_wallclock": {"support_recovery_host_s": round(t_support,1),
                              "refit_rule_host_s": round(refit_wall_s,1),
                              "note": "host python proxy; NOT a device number; on-device structure-only refit must be measured before any ship claim (single wall clocks +-30% untrustworthy)"},
        "chair_roi": {"roi": cfg["chair_roi"], "baseline": base_roi, "candidate": cand_roi},
        "honesty": [
            "Prototype recovers evidence from sfm_live.db in observation space; NOT byte-exact production finalize replication.",
            "Support radius 3px can absorb a neighboring verified feature => a true 2-view point may be classified multiview and kept (errs toward status quo, never extra culling).",
            f"keep_unmatched_honest={vc.get('keep_unmatched_honest',0)} points had <2 recoverable obs; keep_unverified_pair_honest={vc.get('keep_unverified_pair_honest',0)} had 2 obs not transitively matched; all kept unchanged.",
            "Rescue candidates NOT injected into candidate PLY (colorize path + production identity not reproducible here); reported/visualized only.",
            "Wall clocks are host python proxies.",
        ],
    }
    stats["outputs"] = {os.path.basename(p): sha256(p) for p in
                        [ply_out, os.path.join(out,f"diff_{cap}.ply"), os.path.join(out,f"rescue_candidates_{cap}.ply")]}
    json.dump(stats, open(os.path.join(out, "stats.json"), "w"), indent=2)
    log(json.dumps({k: stats[k] for k in ("verdicts","ruler_1_points")}, indent=1))

    np.savez_compressed(os.path.join(out, "render_arrays.npz"),
                        xyz=xyz, rgb=rgb, keep_mask=keep_mask, dif_rgb=dif_rgb,
                        keep2=keep2, cull2=cull2, y_floor=y_floor,
                        rescue=rescue_pos)
    return stats

if __name__ == "__main__":
    caps = sys.argv[1:] or list(CAPS)
    all_path = os.path.join(OUT_BASE, "stats_all.json")
    allstats = json.load(open(all_path)) if os.path.exists(all_path) else {}
    for cap in caps:
        allstats[cap] = run_cap(cap, CAPS[cap])
    json.dump(allstats, open(all_path, "w"), indent=2)
    log("ALL DONE")
