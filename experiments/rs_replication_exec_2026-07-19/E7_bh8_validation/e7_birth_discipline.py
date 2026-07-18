#!/usr/bin/env python3.11
"""
E7: INDEPENDENT VALIDATION of the E3 birth-discipline knife at its FROZEN operating
point bh=8 on cap40/cap41 (bedroom - a scene E3 was never calibrated on).

THIS IS A VALIDATION, NOT A CALIBRATION: every rule constant below is byte-identical
to E3_birth_discipline/e3_birth_discipline.py. DIFF (full disclosure):
  1. CAPS -> cap40/41 E4-B host-replay triple; protected_ranks EMPTY (no pre-audited
     clusters exist for this scene - the independent photo audit e7_audit.py plays
     that role AFTER the run, never feeding back into it); zone_ranks empty;
     chair_roi/window_z_max None (cap50-scene-specific accounting labels only).
  2. TF/OUT_BASE -> E7_bh8_validation (E7's own verbatim E2-A products).
  3. VOTE_BLOCK_HITS_SWEEP extended to 3..12 (pure scan for the curve-shape drift
     comparison demanded by the task; MAIN stays 8, untouched).

LAYERED rule (E2-B lesson: global knives always over-kill; so risk-layered gates):

  BASELINE (all points)  = S1 unified 2-view lifecycle, byte-identical constants:
    multiview (>=3 recovered obs) keep; 2-view verified pair -> structure-only DLT
    refit with frozen refined poses, cull on neg-depth / reproj>3px / theta<2deg;
    unrecoverable obs kept + honestly counted. Provenance-blind.

  RISK LAYER (E2-A four-signature union, EXACT reuse of TRAILS_forensics
  trail_detect.npz: S_behind | S_below | S_streak | S_out):
    a risk-flagged point that survives S1 must additionally EARN existence:
      path 1: n_support >= 3 recovered obs (multi-view support), OR
      path 2: net-visibility vote  (support - oppose >= 0):
        each recovered support frame votes by ITS OWN sight corridor:
          clear   (< VOTE_BLOCK_HITS solid-voxel crossings, march identical to
                   E2-A constants: 5cm voxel >=6pts solid, step 4cm, start 25cm,
                   stop 20cm short)                                   -> +1
          blocked (>= VOTE_BLOCK_HITS solid crossings)                -> -1
        points with 0 recoverable obs get ONE nearest-camera proxy vote (flagged);
        crossing the production floor plane counts as an oppose occluder: any
        point with floor_h < -0.10 m (below the known 2-3.5cm double-floor band)
        has every corridor crossing the solid floor => all its votes oppose.
    Non-risk points: S1 verdict stands UNCHANGED (no global tightening).

  Rationale: a mirror ghost is observed only through reflections => its own
  support corridors pierce the real surface (oppose); real sparse geometry seen
  through a real opening (door shelves Z~-9.1) has clear corridors (support).

HARD CHECKS
  (a) audited TRUE-geometry clusters (cap50 r05 ceiling / r09 backpack /
      r12 door-opening shelves, audit_verdicts.json) must survive; killing them
      means the rule is wrong -> FAIL honestly.
  (b) four rulers (points / floor thickness / correct coverage / wallclock proxy)
      on cap50+cap51; floor coverage loss > 1% = FAIL.
  (c) trail-kill accounting vs the E2-A candidates (protected clusters excluded),
      per hot zone (window-glass reflections / below-floor reflection layer /
      piano lacquer / satin quilt).

Also produces a VOTE_BLOCK_HITS sweep curve (3/4/5/6/8) = the layered-threshold
scan demanded if signature FPs over-kill; honesty over polish.

Products only in this directory. No production code touched, no git commits.
Reads only frozen capture data + E2-A/S1 research products (SHA-checked).
"""
import sqlite3, numpy as np, json, os, sys, time, hashlib
from collections import defaultdict
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MAX_IMAGE_ID = 2147483647
# ---- S1 baseline constants (byte-identical to S1_twoview_lifecycle/build_candidate.py) ----
REPROJ_GATE_PX = 3.0
THETA_GATE_DEG = 2.0
FLOOR_SLAB = 0.06
COVER_SLAB = 0.03
CELL_THICK = 0.05
CELL_COVER = 0.02
# ---- E2-A march constants (byte-identical to TRAILS_forensics/detect_trails.py) ----
VOX = 0.05
VOX_SOLID = 6
MARCH_STEP = 0.04
MARCH_START = 0.25
MARCH_STOP = 0.20
# ---- E3 vote constants ----
# MAIN = 8, NOT the E2-A searchlight value (3). Provenance (honest): the sweep on
# cap50 shows the oppose threshold must be >= 8 for ALL audited true-geometry
# clusters to survive (check a red line: backpack r09 dies 17/19 at 3). This is
# CALIBRATED ON the protected audit set => it cannot also validate on it; the
# spec-faithful bh=3 run + full sweep are reported unredacted in stats/README.
VOTE_BLOCK_HITS_MAIN = 8
VOTE_BLOCK_HITS_SWEEP = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
MULTIVIEW_EARN = 3                # path-1 earn threshold (>=3 recovered obs)
BELOW_FLOOR = -0.10               # E2-A S_below gate; floor plane = standing occluder
CLUSTER_LINK = 0.20               # E2-A candidate clustering radius (reproduction)

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
TF = f"{EXP}/E7_bh8_validation"            # E7's own verbatim E2-A products (cap40/41)
OUT_BASE = f"{EXP}/E7_bh8_validation"
E4B = f"{EXP}/E4_cap4041_host_replay/S1_rerun"
CAPS = {
    "cap40": {
        "dir": f"{E4B}/inputs/cap40",   # E4-B host-replay self-consistent triple
        "chair_roi": None,               # cap50-scene accounting label - n/a here
        "protected_ranks": {},           # VALIDATION: no pre-audited clusters may exist;
                                         # the independent photo audit runs AFTER, never feeds back
        "zone_ranks": {},                # no scene-tuned zone labels (accounting only anyway)
        "window_z_max": None,
    },
    "cap41": {
        "dir": f"{E4B}/inputs/cap41",
        "chair_roi": None,
        "protected_ranks": {},
        "zone_ranks": {},
        "window_z_max": None,
    },
}

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

def connected_components(pts, radius):
    if len(pts) == 0: return np.zeros(0, int)
    tree = cKDTree(pts)
    pairs = tree.query_pairs(radius, output_type="ndarray")
    parent = np.arange(len(pts))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra
    return np.array([find(i) for i in range(len(pts))])

# ---------------- floor / coverage rulers (S1-identical) ----------------
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
    return {"n_roi": int(len(P)), "n_roi_near_floor_5cm": int(near_floor.sum()),
            "frac_roi_near_floor": round(float(near_floor.mean()),4),
            "roi_y_p10": float(np.percentile(y,10)), "roi_y_p50": float(np.percentile(y,50)),
            "roi_y_p90": float(np.percentile(y,90))}

# ---------------- main ----------------
def run_cap(cap, cfg):
    d = cfg["dir"]
    out = os.path.join(OUT_BASE, cap); os.makedirs(out, exist_ok=True)
    DB, META, PLY = f"{d}/sfm_live.db", f"{d}/sfm_sparse_meta.json", f"{d}/sfm_sparse.ply"
    log(f"=== {cap} ===")
    wall = {}

    # ---- load db (S1-identical) ----
    t0 = time.perf_counter()
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c = db.cursor()
    img_ids = sorted(i for (i,) in c.execute("SELECT image_id FROM images"))
    kp_xy, kp_count = {}, {}
    for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
        arr = np.frombuffer(data, dtype=np.float32).reshape(r, cols)
        kp_xy[iid] = np.ascontiguousarray(arr[:, :2].astype(np.float64)); kp_count[iid] = r
    cam = c.execute("SELECT model,params,width,height FROM cameras LIMIT 1").fetchone()
    params = np.frombuffer(cam[1], dtype=np.float64)
    assert len(params) == 3, "expected SIMPLE_PINHOLE"
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
    n_pairs = 0
    for pair_id, r, cols, data in c.execute("SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0"):
        iid1, iid2 = pair_id // MAX_IMAGE_ID, pair_id % MAX_IMAGE_ID
        if iid1 not in offset or iid2 not in offset: continue
        m = np.frombuffer(data, dtype=np.uint32).reshape(r, cols)
        n1, n2 = kp_count[iid1], kp_count[iid2]
        o1, o2 = offset[iid1], offset[iid2]
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
    ply_sha = sha256(PLY)
    wall["load_s"] = round(time.perf_counter()-t0, 1)

    # ---- E2-A products, SHA-checked same cloud ----
    fpi = json.load(open(f"{TF}/{cap}/fingerprints_info.json"))
    assert fpi["inputs"]["ply_sha256"] == ply_sha, "E2-A fingerprints computed on a different PLY!"
    fpz = np.load(f"{TF}/{cap}/fingerprints.npz")
    tdz = np.load(f"{TF}/{cap}/trail_detect.npz")
    assert len(fpz["xyz"]) == nP and np.allclose(fpz["xyz"], xyz)
    risk = tdz["cand"].copy()
    S_below_mask = tdz["S_below"].copy()
    floor_h = fpz["floor_h"]
    nRisk = int(risk.sum())
    log(f"points={nP} risk(E2-A union)={nRisk}")

    # ---- support recovery (S1-identical) ----
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
    support_frames = [[] for _ in range(nP)]
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
            support_frames[pi].append((fid, int(frame_nodes[fid][ki]), float(dist_px)))
    n_support = np.array([len(s) for s in support_frames])
    wall["support_recovery_s"] = round(time.perf_counter()-t0, 1)
    log(f"support recovery {wall['support_recovery_s']}s")

    # ---- S1 baseline adjudication (identical) ----
    t0 = time.perf_counter()
    verdict = np.array(["keep_multiview"]*nP, dtype=object)
    verdict[n_support <= 1] = "keep_unmatched_honest"
    two_idx = np.flatnonzero(n_support == 2)
    for pi in two_idx:
        (f1, nd1, _), (f2, nd2, _) = support_frames[pi]
        if roots[nd1] != roots[nd2]:
            verdict[pi] = "keep_unverified_pair_honest"; continue
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
            verdict[pi] = "cull_s1_neg_depth"; continue
        X = Xh[:3]/Xh[3]
        ok, reason, maxres = True, None, 0.0
        for fid, xy in ((f1,xy1),(f2,xy2)):
            Xc = pose_R[fid] @ X + pose_t[fid]
            if Xc[2] <= 0: ok, reason = False, "neg_depth"; break
            u, v = f_*Xc[0]/Xc[2]+cx_, f_*Xc[1]/Xc[2]+cy_
            maxres = max(maxres, float(np.hypot(u-xy[0], v-xy[1])))
        if ok and maxres > REPROJ_GATE_PX: ok, reason = False, "reproj_gt3px"
        if ok:
            v1, v2 = X - pose_C[f1], X - pose_C[f2]
            cosang = np.dot(v1,v2)/(np.linalg.norm(v1)*np.linalg.norm(v2)+1e-15)
            th = float(np.degrees(np.arccos(np.clip(cosang,-1,1))))
            if th < THETA_GATE_DEG: ok, reason = False, "theta_lt2deg"
        verdict[pi] = "keep_2view_pass" if ok else f"cull_s1_{reason}"
    wall["s1_rule_s"] = round(time.perf_counter()-t0, 1)
    s1_cull = np.char.startswith(verdict.astype(str), "cull_s1_")
    log(f"S1 baseline culls={int(s1_cull.sum())}")

    # ---- voxel occupancy + corridor votes for risk points ----
    t0 = time.perf_counter()
    key = np.floor(xyz / VOX).astype(np.int64)
    vox = defaultdict(int)
    for k in map(tuple, key): vox[k] += 1
    solid = {k for k, v in vox.items() if v >= VOX_SOLID}
    camC_all = np.array([pose_C[f] for f in sorted(pose_C)])
    cam_fids = np.array(sorted(pose_C))
    cam_tree = cKDTree(camC_all)
    own_vox = [tuple(k) for k in key]

    def corridor_hits(C, pi):
        """distinct solid voxels crossed on [MARCH_START, L-MARCH_STOP]; None=too short."""
        X = xyz[pi]; v = X - C; L = np.linalg.norm(v)
        if L <= MARCH_START + MARCH_STOP + 0.1: return None
        u = v / L
        ts = np.arange(MARCH_START, L - MARCH_STOP, MARCH_STEP)
        sk = np.floor((C[None,:] + ts[:,None]*u[None,:]) / VOX).astype(np.int64)
        hits = 0; prev = None
        for k in map(tuple, sk):
            if k == prev: continue
            prev = k
            if k in solid and k != own_vox[pi]: hits += 1
        return hits

    risk_idx = np.flatnonzero(risk & ~s1_cull)
    vote_hits = {}          # pi -> list of per-view corridor hit counts (None dropped)
    vote_proxy = np.zeros(nP, bool)
    for pi in risk_idx:
        hs = []
        if n_support[pi] >= 1:
            for fid, _, _ in support_frames[pi]:
                h = corridor_hits(pose_C[fid], pi)
                if h is not None: hs.append(h)
        if not hs:  # 0-obs or all-too-short => nearest-camera proxy single vote
            ki = cam_tree.query(xyz[pi])[1]
            h = corridor_hits(camC_all[ki], pi)
            hs = [h if h is not None else 0]
            vote_proxy[pi] = True
        vote_hits[pi] = hs
    wall["corridor_votes_s"] = round(time.perf_counter()-t0, 1)
    log(f"corridor votes for {len(risk_idx)} risk pts {wall['corridor_votes_s']}s")

    # ---- adjudicate risk layer for a given oppose threshold ----
    def risk_overlay(block_hits):
        v = verdict.copy()
        net_arr = np.full(nP, np.nan)
        for pi in risk_idx:
            if n_support[pi] >= MULTIVIEW_EARN:
                v[pi] = "keep_risk_multiview"; continue
            below = floor_h[pi] < BELOW_FLOOR
            votes = [(-1 if (below or h >= block_hits) else +1) for h in vote_hits[pi]]
            net = sum(votes)
            net_arr[pi] = net
            if net >= 0:
                v[pi] = "keep_risk_netvisible"
            else:
                v[pi] = "cull_risk_belowfloor" if below else "cull_risk_occluded"
        return v, net_arr

    # ---- clustering reproduction (E2-A identical) for zones + protected check ----
    ci = np.flatnonzero(risk)
    lab = connected_components(xyz[ci], CLUSTER_LINK)
    clus = []
    for lb in np.unique(lab):
        mem = ci[lab == lb]
        clus.append((len(mem), mem))
    clus.sort(key=lambda c: -c[0])
    rank_members = {rank: mem for rank, (n, mem) in enumerate(clus)}
    ref = json.load(open(f"{TF}/{cap}/trail_stats.json"))["clusters_ge3"]
    for r in ref[:15]:
        rk = r["rank"]
        assert rk in rank_members and len(rank_members[rk]) == r["n"], f"cluster reproduction mismatch rank {rk}"

    protected_mask = np.zeros(nP, bool)
    for rk in cfg["protected_ranks"]:
        protected_mask[rank_members[rk]] = True

    # hot zones (priority: named clusters > protected(excluded) > below-floor > window > other)
    zone = np.array(["nonrisk"]*nP, dtype=object)
    zone[risk] = "other"
    if cfg["window_z_max"] is not None:
        zw = risk & (xyz[:,2] < cfg["window_z_max"])
        zone[zw] = "window_glass"
    zone[risk & S_below_mask] = "below_floor"
    for rk, zname in cfg["zone_ranks"].items():
        zone[rank_members[rk]] = zname
    zone[protected_mask] = "protected_true_geom"

    # ---- sweep ----
    sweep = []
    for bh in VOTE_BLOCK_HITS_SWEEP:
        v, _ = risk_overlay(bh)
        cull = np.char.startswith(v.astype(str), "cull_")
        prot_killed = int((cull & protected_mask).sum())
        acct = risk & ~protected_mask
        sweep.append({
            "vote_block_hits": bh,
            "risk_killed_excl_protected": int((cull & acct).sum()),
            "risk_total_excl_protected": int(acct.sum()),
            "protected_killed": prot_killed, "protected_total": int(protected_mask.sum()),
            "total_cull": int(cull.sum()),
            "zone_kill": {zn: [int((cull & (zone==zn)).sum()), int((zone==zn).sum())]
                          for zn in sorted(set(zone[risk].tolist()))},
        })
        log(f" sweep bh={bh}: cull={int(cull.sum())} protected_killed={prot_killed}")

    # ---- main verdict ----
    t0 = time.perf_counter()
    verdict_main, net_arr = risk_overlay(VOTE_BLOCK_HITS_MAIN)
    wall["risk_rule_s"] = round(time.perf_counter()-t0, 3)
    cull = np.char.startswith(verdict_main.astype(str), "cull_")
    keep_mask = ~cull
    cand, cand_rgb = xyz[keep_mask], rgb[keep_mask]
    vc = {v: int((verdict_main==v).sum()) for v in sorted(set(verdict_main.tolist()))}
    log(json.dumps(vc, indent=1))

    # ---- check (a): protected clusters ----
    check_a = {"applicable": bool(cfg["protected_ranks"])}
    if cfg["protected_ranks"]:
        rows = {}
        worst_frac = 0.0
        for rk, name in cfg["protected_ranks"].items():
            mem = rank_members[rk]
            k = int(cull[mem].sum())
            rows[f"r{rk:02d}_{name}"] = {"n": int(len(mem)), "killed": k,
                                         "survive_frac": round(1 - k/len(mem), 3)}
            worst_frac = max(worst_frac, k/len(mem))
        check_a["clusters"] = rows
        check_a["pass"] = bool(worst_frac == 0.0)
        check_a["note"] = "PASS requires every audited true-geometry cluster fully alive (they are real multi-view geometry; any kill = rule error)"
    else:
        check_a["pass"] = None
        check_a["note"] = "no audited-FP true-geometry clusters on this cap (E2-A audited clusters here are TRUE/AMB mirror trails)"

    # ---- check (b): four rulers ----
    # E7 measurement note: the S1 detect_floor_y (global y-hist max) lands on the BED TOP
    # in this bedroom scene; the real floor is the fingerprints' reconstructed lowest
    # dominant y-slab plane. Use that plane (same one the rule's floor_h consumes) for
    # the floor rulers. Bed-top y kept for disclosure.
    y_floor = float(-fpz["plane_d"])
    y_hist_max = detect_floor_y(xyz)          # bed top - disclosure only
    base_fl = floor_metrics(xyz, y_floor)
    cand_fl = floor_metrics(cand, y_floor)
    # increment view demanded by the task: baseline = E4-B S1 candidate (S1 culls only),
    # so the delta isolates what the E3 risk layer ADDS on this scene.
    s1_keep = ~s1_cull
    s1_fl = floor_metrics(xyz[s1_keep], y_floor)
    e3_added_cull = cull & s1_keep
    # cross-check our internal S1 against the E4-B S1 rerun verdicts (same inputs+constants)
    e4b_stats = json.load(open(f"{E4B}/{cap}/stats.json"))
    e4b_culls = {k: v for k, v in e4b_stats["verdicts"].items() if k.startswith("cull_")}
    our_culls = {k.replace("cull_s1_", "cull_"): v for k, v in vc.items() if k.startswith("cull_s1_")}
    s1_crosscheck = {"e4b": e4b_culls, "e7_internal": our_culls,
                     "match": sum(e4b_culls.values()) == int(s1_cull.sum())}
    cover_loss_pct = 100.0*(base_fl["cover_cells_2cm"]-cand_fl["cover_cells_2cm"])/max(base_fl["cover_cells_2cm"],1)
    cover_loss_vs_s1_pct = 100.0*(s1_fl["cover_cells_2cm"]-cand_fl["cover_cells_2cm"])/max(s1_fl["cover_cells_2cm"],1)
    check_b = {
        "floor_plane_note": {"y_floor_used": round(y_floor,4), "source": "fingerprints reconstructed lowest dominant y-slab (same plane the rule's floor_h uses)",
                             "y_hist_global_max": round(y_hist_max,4), "why_not_hist_max": "global y-hist max is the BED TOP in this bedroom scene"},
        "ruler_1_points": {"baseline": nP, "candidate": int(len(cand)),
                           "delta": int(len(cand)-nP), "delta_pct": round(100.0*(len(cand)-nP)/nP,2),
                           "s1_only_candidate": int(s1_keep.sum()),
                           "e3_risk_layer_added_culls": int(e3_added_cull.sum())},
        "ruler_2_floor_thickness": {"y_floor": round(y_floor,4), "baseline": base_fl,
                                    "s1_only": s1_fl, "candidate": cand_fl},
        "ruler_3_coverage": {"baseline_cells_2cm": base_fl["cover_cells_2cm"],
                             "s1_only_cells_2cm": s1_fl["cover_cells_2cm"],
                             "candidate_cells_2cm": cand_fl["cover_cells_2cm"],
                             "floor_cover_loss_pct": round(cover_loss_pct, 3),
                             "floor_cover_loss_vs_s1_baseline_pct": round(cover_loss_vs_s1_pct, 3),
                             "gate": "loss > 1% = FAIL"},
        "ruler_4_wallclock_host_proxy_s": wall,
        "s1_crosscheck_vs_e4b": s1_crosscheck,
        "chair_roi": {"roi": cfg["chair_roi"],
                      "baseline": chair_roi_metrics(xyz, cfg["chair_roi"], y_floor),
                      "candidate": chair_roi_metrics(cand, cfg["chair_roi"], y_floor)},
        "pass": bool(cover_loss_pct <= 1.0),
    }

    # ---- check (c): kill accounting per hot zone (protected excluded) ----
    acct = risk & ~protected_mask
    zones = {}
    for zn in sorted(set(zone[acct].tolist())):
        zm = acct & (zone == zn)
        zones[zn] = {"n": int(zm.sum()), "killed": int((cull & zm).sum()),
                     "kill_frac": round(float((cull & zm).sum())/max(int(zm.sum()),1), 3)}
    check_c = {"risk_candidates_excl_protected": int(acct.sum()),
               "killed_excl_protected": int((cull & acct).sum()),
               "kill_frac": round(float((cull & acct).sum())/max(int(acct.sum()),1), 3),
               "zones": zones}

    # ---- products ----
    p_cand = os.path.join(out, f"e7_candidate_{cap}.ply")
    write_ply_xyzrgb(p_cand, cand, cand_rgb,
        f"E7 frozen-bh8 validation candidate {cap}: S1 baseline + risk-layer earn-existence (E2-A 4-signature risk, >= {MULTIVIEW_EARN} obs OR net-visibility vote, oppose=corridor >= {VOTE_BLOCK_HITS_MAIN} solid crossings or below-floor plane); production gauge, positions/colors untouched")
    dif_rgb = np.zeros((nP,3), np.uint8); dif_rgb[:] = (120,120,120)
    dif_rgb[risk & keep_mask] = (0,220,0)
    dif_rgb[cull] = (255,40,40)
    p_diff = os.path.join(out, f"diff_{cap}.ply")
    write_ply_xyzrgb(p_diff, xyz, dif_rgb,
        f"E7 diff {cap}: red=killed, green=risk point that EARNED existence, gray=non-risk kept")

    # renders: true-color side-by-side + trail before/after
    def scatter(ax, P, Cl, s=0.25):
        ax.scatter(P[:,0], P[:,2], s=s, c=Cl, linewidths=0)
    fig, axes = plt.subplots(2, 2, figsize=(20, 20))
    for axrow, (a, b, la, lb_, inv) in zip(axes, [(0,2,"X","Z",False),(2,1,"Z","Y",True)]):
        for ax, (P, Cl, ttl) in zip(axrow, [(xyz, rgb, f"baseline {nP}"), (cand, cand_rgb, f"E7 candidate {len(cand)}")]):
            ax.scatter(P[:,a], P[:,b], s=0.25, c=Cl/255.0, linewidths=0)
            ax.scatter(camC_all[:,a], camC_all[:,b], s=14, c="magenta", marker="^")
            ax.set_aspect("equal"); ax.set_facecolor("#181818")
            ax.set_xlabel(la); ax.set_ylabel(lb_)
            if inv: ax.invert_yaxis()
            ax.set_title(f"{cap} {ttl} ({'topview' if not inv else 'elevation'}) - same gauge, no Sim3")
    plt.tight_layout()
    p_sbs = os.path.join(out, f"side_by_side_{cap}.png")
    plt.savefig(p_sbs, dpi=110); plt.close()

    fig, axes = plt.subplots(2, 2, figsize=(20, 20))
    after_trail = risk & keep_mask
    panels = [(xyz, risk, f"BEFORE: E2-A trail candidates {nRisk}"),
              (None, None, f"AFTER: surviving trail candidates {int(after_trail.sum())} (killed {int((risk & cull).sum())})")]
    for axrow, (a, b, la, lb_, inv) in zip(axes, [(0,2,"X","Z",False),(2,1,"Z","Y",True)]):
        # before
        ax = axrow[0]
        ax.scatter(xyz[~risk][:,a], xyz[~risk][:,b], s=0.2, c=rgb[~risk]/255.0, linewidths=0)
        ax.scatter(xyz[risk][:,a], xyz[risk][:,b], s=3.0, c="red", linewidths=0)
        ax.set_title(f"{cap} {panels[0][2]}")
        # after
        ax2 = axrow[1]
        km = keep_mask & ~risk
        ax2.scatter(xyz[km][:,a], xyz[km][:,b], s=0.2, c=rgb[km]/255.0, linewidths=0)
        ax2.scatter(xyz[after_trail][:,a], xyz[after_trail][:,b], s=3.0, c="red", linewidths=0)
        ax2.set_title(f"{cap} {panels[1][2]}")
        for ax_ in (ax, ax2):
            ax_.scatter(camC_all[:,a], camC_all[:,b], s=14, c="magenta", marker="^")
            ax_.set_aspect("equal"); ax_.set_facecolor("#181818")
            ax_.set_xlabel(la); ax_.set_ylabel(lb_)
            if inv: ax_.invert_yaxis()
    plt.tight_layout()
    p_ba = os.path.join(out, f"trail_before_after_{cap}.png")
    plt.savefig(p_ba, dpi=110); plt.close()

    # sweep curve
    fig, ax = plt.subplots(figsize=(8,5))
    xs = [s["vote_block_hits"] for s in sweep]
    ax.plot(xs, [100*s["risk_killed_excl_protected"]/max(s["risk_total_excl_protected"],1) for s in sweep],
            "o-", label="risk killed % (excl protected)")
    if cfg["protected_ranks"]:
        ax.plot(xs, [100*s["protected_killed"]/max(s["protected_total"],1) for s in sweep],
                "s--", color="red", label="protected TRUE-geom killed % (must be 0)")
    ax.axvline(VOTE_BLOCK_HITS_MAIN, color="gray", ls=":", label=f"main={VOTE_BLOCK_HITS_MAIN}")
    ax.set_xlabel("oppose-vote threshold (solid voxel crossings)"); ax.set_ylabel("%")
    ax.set_title(f"{cap} layered-threshold sweep (net-visibility vote)")
    ax.legend(); ax.grid(alpha=0.3)
    p_sw = os.path.join(out, f"sweep_curve_{cap}.png")
    plt.savefig(p_sw, dpi=110); plt.close()

    stats = {
        "cap": cap,
        "experiment": "E7 independent validation of E3 knife at FROZEN bh=8 (no scene retuning)",
        "inputs": {"db": DB, "meta": META, "baseline_ply": PLY, "baseline_ply_sha256": ply_sha,
                   "e2a_fingerprints": f"{TF}/{cap}/fingerprints.npz",
                   "e2a_trail_detect": f"{TF}/{cap}/trail_detect.npz",
                   "e2a_sha_check": "fingerprints_info ply_sha256 == baseline sha (asserted)"},
        "gauge": "production refined poses; PLY frame == meta frame (S1 probe verified); NO Sim3",
        "rule": {
            "baseline": "S1 unified 2-view lifecycle, byte-identical constants (3px reproj, 2deg theta, provenance-blind)",
            "risk_signature": "E2-A four-signature union reused verbatim (S_behind|S_below|S_streak|S_out)",
            "earn_existence": {
                "path1_multiview_obs": MULTIVIEW_EARN,
                "path2_net_visibility": f"per-support-frame corridor votes, clear(+1)/blocked(-1), blocked = >= {VOTE_BLOCK_HITS_MAIN} solid {VOX}m-voxel crossings (E2-A march constants); floor plane = standing occluder for floor_h < {BELOW_FLOOR}; 0-obs points: 1 nearest-camera proxy vote (flagged); survive iff net >= 0",
            },
            "layering": "non-risk points keep their S1 verdict unchanged (no global tightening; E2-B lesson)",
            "operating_point_provenance": f"vote_block_hits={VOTE_BLOCK_HITS_MAIN} selected FROM the sweep as the smallest threshold with zero audited true-geometry kills on cap50; calibrated on the protected set (disclosed overfit risk); spec-faithful bh=3 result kept in sweep",
        },
        "verdicts": vc,
        "n_risk": nRisk,
        "n_risk_proxy_vote": int(vote_proxy[risk_idx].sum()) if len(risk_idx) else 0,
        "check_a_protected_true_geometry": check_a,
        "check_b_four_rulers": check_b,
        "check_c_trail_kill_accounting": check_c,
        "sweep_vote_block_hits": sweep,
        "honesty": [
            "evidence rebuilt from sfm_live.db in observation space; NOT byte-exact production finalize; 3px support radius errs toward keep",
            f"{int((n_support<=1).sum())} pts have <2 recoverable obs (S1 known floor ~65%); risk-flagged ones among them get a single nearest-camera proxy corridor vote - direction may be wrong for moved objects (cluster09-type)",
            "E2-A signature FP rate 15-35% point-level (single-rater audit); the layered gate + net-visibility vote is the mitigation, sweep curve provided",
            "march/voxel thresholds are E2-A forensic constants, not certified production config; nothing here ships without sign-off",
            "wallclock = host python proxy, not device numbers",
        ],
    }
    outputs = {}
    for p in [p_cand, p_diff, p_sbs, p_ba, p_sw]:
        outputs[os.path.basename(p)] = sha256(p)
    stats["outputs_sha256"] = outputs
    json.dump(stats, open(os.path.join(out, "stats.json"), "w"), indent=2)
    np.savez_compressed(os.path.join(out, "e7_arrays.npz"),
                        verdict=verdict_main.astype(str), risk=risk, cull=cull,
                        n_support=n_support, net=net_arr, zone=zone.astype(str),
                        protected_mask=protected_mask, vote_proxy=vote_proxy)
    return stats

if __name__ == "__main__":
    caps = sys.argv[1:] or list(CAPS)
    all_path = os.path.join(OUT_BASE, "stats_all.json")
    allstats = json.load(open(all_path)) if os.path.exists(all_path) else {}
    for cap in caps:
        allstats[cap] = run_cap(cap, CAPS[cap])
    json.dump(allstats, open(all_path, "w"), indent=2)
    log("E7 DONE")
