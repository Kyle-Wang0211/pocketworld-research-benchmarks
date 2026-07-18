#!/usr/bin/env python3.11
"""
E2-B: RS default Max feature reprojection error = 2.0px (VERIFIED, official key table)
applied to our production cap50 cloud — tests the #1 RS-faithful hypothesis for
"why RS has no specular/mirror trails".

RULE (RS / RC tie-point semantics, per orchestrator spec):
  per-OBSERVATION residual vs production point position (poses+K frozen, refined
  production gauge); observation with residual > gate is deleted; a point survives
  iff >= 2 surviving observations (in distinct frames). Sweep gates:
  1.5 / 2.0(RS) / 2.5 / 3.0(mid) / 3.5 / 4.0(our production BA-filter, control).
  Survivors keep production position+color (life/death only, no repositioning).

OBSERVATION RECOVERY (extends S1 verified method, honest approximation declared):
  Production PLY has no track labels. Recover observations in observation space:
  project each point into all 139 registered frames (refined poses, frozen K),
  take best verified-matched keypoint (participating in >=1 inlier
  two_view_geometries edge) within SUPPORT_R=6.0px per frame, then keep only hits
  in the point's MAJORITY union-find component (track identity guard against
  absorbing neighbor features). Points with <2 recovered in-component obs are
  kept unchanged in every candidate + honestly counted (cannot be adjudicated).
  Since production itself filters obs at 4px, the 4px control doubles as a
  methodology validation (should cull ~nothing).

TRAIL SIGNATURE (self-computed simple version; E2-A parallel not yet delivered):
  SIG_ISO  : isolation — dist to 10th NN > 3x median (sparse streaks/trails)
  DENSE    : dist to 10th NN < median (dense-surface core = true-point proxy)
  ENVELOPE : XZ distance outside convex hull of camera centers (trails from
             mirrors/glass extend beyond the room envelope; binned cull-fraction
             curve reported, no cherry-picked threshold)

Reads ONLY frozen capture data; writes ONLY into this directory. No git ops.
"""
import sqlite3, numpy as np, json, os, sys, time, hashlib, subprocess
from collections import defaultdict, Counter
from scipy.spatial import cKDTree, ConvexHull, Delaunay

MAX_IMAGE_ID = 2147483647
SUPPORT_R = 6.0
GATES = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
DELIVER = {2.0: "rs2px", 3.0: "mid3px", 4.0: "prod4px"}
FLOOR_SLAB, COVER_SLAB, CELL_THICK, CELL_COVER = 0.06, 0.03, 0.05, 0.02

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
CAP_DIR = f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17"
OUT = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/TRAILS_rs2px_gate"
CHAIR_ROI = {"X": (0.25, 1.05), "Z": (-1.70, -0.55)}  # frozen, from 06_glomap_alias

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
    key = cx * 1000003 + cz
    order = np.argsort(key)
    key_s, y_s = key[order], P[order,1]
    bounds = np.flatnonzero(np.diff(key_s)) + 1
    groups = np.split(y_s, bounds)
    spreads = [float(np.percentile(g,90) - np.percentile(g,10)) for g in groups if len(g) >= 8]
    out["thickness_med_cell_p90p10_m"] = float(np.median(spreads)) if spreads else None
    out["thickness_p90_cell_m"] = float(np.percentile(spreads,90)) if spreads else None
    out["n_thickness_cells"] = len(spreads)
    tight = np.abs(P[:,1] - y_floor) <= COVER_SLAB
    Q = P[tight]
    cells = set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64), np.floor(Q[:,2]/CELL_COVER).astype(np.int64)))
    out["cover_cells_2cm"] = len(cells)
    out["cover_area_m2"] = round(len(cells) * CELL_COVER * CELL_COVER, 4)
    return out

def chair_roi_metrics(xyz, y_floor):
    roi = CHAIR_ROI
    m = (xyz[:,0]>=roi["X"][0])&(xyz[:,0]<=roi["X"][1])&(xyz[:,2]>=roi["Z"][0])&(xyz[:,2]<=roi["Z"][1])
    P = xyz[m]
    if len(P)==0: return {"n_roi": 0}
    y = P[:,1]
    near_floor = np.abs(y - y_floor) <= 0.05
    return {"n_roi": int(len(P)), "n_roi_near_floor_5cm": int(near_floor.sum()),
            "roi_y_p10": float(np.percentile(y,10)), "roi_y_p50": float(np.percentile(y,50)),
            "roi_y_p90": float(np.percentile(y,90))}

def vmstat_free_gb():
    try:
        outp = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
        free = int([l for l in outp.splitlines() if l.startswith("Pages free")][0].split()[-1].rstrip("."))
        return round(free * 16384 / 1e9, 2)
    except Exception:
        return None

def main():
    t_start = time.perf_counter()
    mem0 = vmstat_free_gb()
    DB, META, PLY = f"{CAP_DIR}/sfm_live.db", f"{CAP_DIR}/sfm_sparse_meta.json", f"{CAP_DIR}/sfm_sparse.ply"

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

    offset, acc = {}, 0
    for iid in img_ids: offset[iid] = acc; acc += kp_count.get(iid, 0)
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
    log(f"db: pairs={n_pairs} inlier_edges={n_edges} kp_nodes={N}")

    meta = json.load(open(META))
    assert meta.get("refined") is True
    pose_R, pose_t = {}, {}
    for p in meta["poses"]:
        if not p.get("registered"): continue
        R = quat_to_R(np.array(p["quat_wxyz"], float)); t = np.array(p["t"], float)
        pose_R[p["frame_id"]], pose_t[p["frame_id"]] = R, t

    xyz, rgb = read_ply_xyzrgb(PLY)
    nP = len(xyz)
    log(f"prod cloud: {nP} pts, {len(pose_R)} registered frames")

    # ---------- observation recovery (SUPPORT_R, verified keypoints only) ----------
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

    support = [[] for _ in range(nP)]   # (fid, node, resid_px)
    for fid in sorted(frame_trees):
        R, t = pose_R[fid], pose_t[fid]
        Xc = xyz @ R.T + t
        infront = Xc[:,2] > 1e-6
        uv = np.full((nP,2), -1e9)
        z = Xc[infront,2]
        uv[infront,0] = f_*Xc[infront,0]/z + cx_
        uv[infront,1] = f_*Xc[infront,1]/z + cy_
        inimg = infront & (uv[:,0]>=-SUPPORT_R) & (uv[:,0]<=W+SUPPORT_R) & (uv[:,1]>=-SUPPORT_R) & (uv[:,1]<=H+SUPPORT_R)
        q_idx = np.flatnonzero(inimg)
        if len(q_idx)==0: continue
        dd, kk = frame_trees[fid].query(uv[q_idx], k=1, distance_upper_bound=SUPPORT_R, workers=-1)
        hit = np.isfinite(dd)
        for pi, dist_px, ki in zip(q_idx[hit], dd[hit], kk[hit]):
            support[pi].append((fid, int(frame_nodes[fid][ki]), float(dist_px)))
    t_support = time.perf_counter() - t0
    log(f"support recovery wall={t_support:.1f}s")

    # ---------- track-identity guard: majority union-find component ----------
    t1 = time.perf_counter()
    obs_res = [None]*nP        # np.array of in-component obs residuals per point
    n_raw = np.zeros(nP, np.int32)
    n_incomp = np.zeros(nP, np.int32)
    for pi in range(nP):
        s = support[pi]
        n_raw[pi] = len(s)
        if len(s) < 2: continue
        comp = Counter(int(roots[nd]) for _, nd, _ in s)
        best_c, best_n = comp.most_common(1)[0]
        if best_n < 2: continue                      # no track with >=2 obs
        res = np.array([r for _, nd, r in s if int(roots[nd]) == best_c])
        obs_res[pi] = res
        n_incomp[pi] = len(res)
    adjudicable = n_incomp >= 2
    log(f"identity guard wall={time.perf_counter()-t1:.1f}s; adjudicable={int(adjudicable.sum())}/{nP}")

    all_res = np.concatenate([r for r in obs_res if r is not None])
    res_hist_edges = [0,0.5,1,1.5,2,2.5,3,3.5,4,5,6]
    res_hist = np.histogram(all_res, bins=res_hist_edges)[0]

    # ---------- trail signatures ----------
    t2 = time.perf_counter()
    tree3d = cKDTree(xyz)
    d10 = tree3d.query(xyz, k=11, workers=-1)[0][:, 10]
    med_d10 = float(np.median(d10))
    SIG_ISO = d10 > 3.0 * med_d10
    DENSE = d10 < med_d10
    cams = np.array([-pose_R[f].T @ pose_t[f] for f in pose_R])
    cam_xz = cams[:, [0,2]]
    hull = ConvexHull(cam_xz)
    dela = Delaunay(cam_xz[hull.vertices])
    p_xz = xyz[:, [0,2]]
    inside = dela.find_simplex(p_xz) >= 0
    # distance outside camera hull (0 if inside)
    hull_pts = cam_xz[hull.vertices]
    seg_d = np.full(nP, np.inf)
    for i in range(len(hull_pts)):
        a, b = hull_pts[i], hull_pts[(i+1) % len(hull_pts)]
        ab = b - a
        tpar = np.clip(((p_xz - a) @ ab) / (ab @ ab), 0, 1)
        proj = a + tpar[:,None]*ab
        seg_d = np.minimum(seg_d, np.linalg.norm(p_xz - proj, axis=1))
    out_dist = np.where(inside, 0.0, seg_d)
    log(f"signatures wall={time.perf_counter()-t2:.1f}s  med_d10={med_d10*1000:.1f}mm  SIG_ISO={int(SIG_ISO.sum())} DENSE={int(DENSE.sum())} outside_hull={int((~inside).sum())}")

    # ---------- gate sweep ----------
    y_floor = detect_floor_y(xyz)
    base_fl = floor_metrics(xyz, y_floor)
    base_roi = chair_roi_metrics(xyz, y_floor)
    floor_band = np.abs(xyz[:,1] - y_floor) <= COVER_SLAB

    sweep = {}
    cull_mask_by_gate = {}
    for g in GATES:
        surv_obs = np.array([int((r <= g).sum()) if r is not None else -1 for r in obs_res])
        cull = adjudicable & (surv_obs < 2) & (surv_obs >= 0)
        keep = ~cull
        cull_mask_by_gate[g] = cull
        cand = xyz[keep]
        fl = floor_metrics(cand, y_floor)
        roi = chair_roi_metrics(cand, y_floor)
        nc = int(cull.sum())
        sweep[str(g)] = {
            "culled": nc, "survival_pct": round(100.0*keep.sum()/nP, 2),
            "cull_in_SIG_ISO": int((cull & SIG_ISO).sum()),
            "cull_in_DENSE": int((cull & DENSE).sum()),
            "trail_kill_rate_pct": round(100.0*(cull & SIG_ISO).sum()/max(1,SIG_ISO.sum()), 2),
            "dense_false_kill_pct": round(100.0*(cull & DENSE).sum()/max(1,DENSE.sum()), 3),
            "cull_outside_hull": int((cull & ~inside).sum()),
            "outside_hull_kill_pct": round(100.0*(cull & ~inside).sum()/max(1,(~inside).sum()), 2),
            "cull_in_floorband3cm": int((cull & floor_band).sum()),
            "cull_median_d10_mm": round(float(np.median(d10[cull]))*1000,1) if nc else None,
            "keep_median_d10_mm": round(float(np.median(d10[keep]))*1000,1),
            "ruler_1_points": {"candidate": int(keep.sum()), "delta_pct": round(-100.0*nc/nP,2)},
            "ruler_2_floor": fl, "ruler_3_roi": roi,
        }
        log(f"gate {g}px: cull={nc} ({100.0*nc/nP:.2f}%)  trail_kill={sweep[str(g)]['trail_kill_rate_pct']}%  dense_false_kill={sweep[str(g)]['dense_false_kill_pct']}%")

    # cull-fraction vs outside-envelope distance bins (2px gate)
    cull2 = cull_mask_by_gate[2.0]
    bins_m = [0.0, 1e-9, 0.1, 0.25, 0.5, 1.0, 2.0, 100.0]
    env_curve = []
    for lo, hi in zip(bins_m[:-1], bins_m[1:]):
        m = (out_dist >= lo) & (out_dist < hi)
        if m.sum() == 0: continue
        env_curve.append({"outside_m": f"[{lo:.2f},{hi:.2f})", "n": int(m.sum()),
                          "cull_frac_pct_at_2px": round(100.0*(cull2 & m).sum()/m.sum(), 2)})
    iso_curve = []
    iso_bins = [0, 1, 2, 3, 5, 8, 1e9]
    for lo, hi in zip(iso_bins[:-1], iso_bins[1:]):
        m = (d10 >= lo*med_d10) & (d10 < hi*med_d10)
        if m.sum() == 0: continue
        iso_curve.append({"d10_over_med": f"[{lo},{hi})", "n": int(m.sum()),
                          "cull_frac_pct_at_2px": round(100.0*(cull2 & m).sum()/m.sum(), 2)})

    # ---------- deliverable PLYs ----------
    outputs = {}
    for g, name in DELIVER.items():
        keep = ~cull_mask_by_gate[g]
        p = os.path.join(OUT, f"{name}_cap50.ply")
        write_ply_xyzrgb(p, xyz[keep], rgb[keep],
            f"E2-B cap50 gate={g}px RS-semantics per-obs cull, point needs >=2 surviving obs; positions/colors=production; unadjudicable kept honestly")
        outputs[os.path.basename(p)] = sha256(p)

    # tiered diff PLY: white->kept everywhere; yellow=culled@2 only; orange=also@3; red=also@4
    dif = np.full((nP,3), 90, np.uint8)
    c2, c3, c4 = cull_mask_by_gate[2.0], cull_mask_by_gate[3.0], cull_mask_by_gate[4.0]
    dif[c2 & ~c3] = (255, 230, 40)
    dif[c3 & ~c4] = (255, 140, 0)
    dif[c4] = (255, 30, 30)
    p = os.path.join(OUT, "diff_tiers_cap50.ply")
    write_ply_xyzrgb(p, xyz, dif, "E2-B diff tiers: gray=kept@2px, yellow=culled only by 2px, orange=culled by 3px too, red=culled even at 4px(prod control)")
    outputs[os.path.basename(p)] = sha256(p)

    np.savez_compressed(os.path.join(OUT, "render_arrays.npz"),
        xyz=xyz, rgb=rgb, cull2=c2, cull3=c3, cull4=c4, d10=d10,
        SIG_ISO=SIG_ISO, DENSE=DENSE, out_dist=out_dist, cams=cams,
        y_floor=y_floor, dif=dif)

    stats = {
        "experiment": "E2-B RS 2.0px reprojection gate on cap50 production cloud",
        "rs_key": "Max feature reprojection error = 2.0 px (VERIFIED official default) vs ours 4px BA-post filter / 10px live create",
        "inputs": {"db": DB, "meta": META, "baseline_ply": PLY, "baseline_ply_sha256": sha256(PLY)},
        "gauge": "production refined poses; PLY frame == meta pose frame (S1 probe_gauge: rotation-only 0.11deg); NO Sim3, NO realignment",
        "method": {
            "obs_recovery": f"project into all {len(pose_R)} registered frames, best verified-matched keypoint within {SUPPORT_R}px/frame, majority union-find component identity guard",
            "rule": "obs residual > gate => obs deleted; point survives iff >=2 surviving obs (distinct frames); survivors keep production position+color",
            "residual_reference": "production BA point position, poses+K frozen (structure not refit; declared)",
        },
        "obs_recovery_stats": {
            "n_pairs_db": n_pairs, "n_inlier_edges": n_edges,
            "adjudicable_pts": int(adjudicable.sum()), "unadjudicable_kept_honest": int((~adjudicable).sum()),
            "obs_residual_median_px": round(float(np.median(all_res)), 3),
            "obs_residual_hist_edges_px": res_hist_edges,
            "obs_residual_hist": res_hist.tolist(),
            "wall_s": round(t_support, 1),
        },
        "trail_signature": {
            "SIG_ISO": f"d10 > 3x median ({med_d10*3000:.1f}mm): {int(SIG_ISO.sum())} pts",
            "DENSE": f"d10 < median ({med_d10*1000:.1f}mm): {int(DENSE.sum())} pts",
            "outside_camera_hull_pts": int((~inside).sum()),
            "note": "self-computed simple signature (E2-A parallel not consumed); SIG_ISO=trail proxy, DENSE=true-surface proxy",
        },
        "baseline": {"n_points": nP, "y_floor": round(y_floor,4), "floor": base_fl, "chair_roi": base_roi},
        "gate_sweep": sweep,
        "cull_frac_vs_outside_envelope_at_2px": env_curve,
        "cull_frac_vs_isolation_at_2px": iso_curve,
        "wallclock": {"total_host_s": round(time.perf_counter()-t_start,1),
                      "note": "host python proxy, NOT a device number"},
        "mem_free_gb": {"start": mem0, "end": vmstat_free_gb()},
        "honesty": [
            "Residuals measured against production BA positions (structure frozen); RS re-triangulates after obs deletion — our one-pass rule is the conservative approximation (no rescue-by-refit), may over-cull points a refit would save.",
            f"{int((~adjudicable).sum())} points had <2 recoverable in-component obs; kept unchanged in ALL candidates (never culled) — cull rates are lower bounds.",
            "Support radius 6px + majority-component guard is evidence reconstruction from sfm_live.db, NOT byte-exact production finalize track identity.",
            "4px control doubles as methodology validation: production already filters at 4px, so its cull count measures our recovery error floor.",
            "Trail signature is self-computed (isolation + camera-hull envelope), pending reconciliation with E2-A trail set.",
            "Wall clocks host-only.",
        ],
        "outputs": outputs,
    }
    json.dump(stats, open(os.path.join(OUT, "stats.json"), "w"), indent=2)
    log(json.dumps({k: stats[k] for k in ("obs_recovery_stats","gate_sweep")}, indent=1)[:2000])
    log("DONE")

if __name__ == "__main__":
    main()
