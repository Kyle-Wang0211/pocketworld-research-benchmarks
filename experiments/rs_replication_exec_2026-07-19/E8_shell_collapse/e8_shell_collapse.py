#!/usr/bin/env python3.11
"""
E8 shell collapse: merge-not-delete. Fragmented same-surface twins (double floor /
double wall 2-3.5cm second layer) are MERGED into one consensus point via
observation-connectivity evidence + COLMAP all-or-nothing merge test.

Diagnosis (this campaign): shell root cause = same physical surface point born
repeatedly (fragmented tracks each 2-view DLT'd; depth spread = sigma_depth).
Per-point gates cannot kill it (E2-B/E7: shell points are individually good).
Solution = MERGE observations, never delete them.

Evidence graph (observation connectivity, NO pure-distance merging - cap47 lesson):
  source A (shared track): recovered support observations (S1 method, byte-identical
     3px nearest matched keypoint per frame) whose keypoint union-find components
     overlap => the two cloud points touch the same verified correspondence track.
  source B (pair bridge): each of the S1-rule-passing verified pairs (ALL of them,
     including the ones G1 excluded as <2cm duplicates - those ARE the fragment
     connection evidence) is reverse-queried: the v1.1 point projecting nearest
     (<=3px) to kp1 in frame f1, and nearest to kp2 in f2. Different points on the
     two sides => bridge edge (the pair is a verified cross-frame correspondence
     between the two fragments' pixel sites).

Merge rule (COLMAP source-verifiable criterion, all-or-nothing):
  trial position = track-length weighted average of the two points.
  accept ONLY if EVERY observation of BOTH tracks (plus, for source-B edges, the
  bridging pair's own two observations) reprojects <= 4px with positive depth at
  the trial position. On accept: consensus position = multi-view DLT over the
  merged observation set (falls back to the weighted average if the DLT position
  itself fails the same all-obs test - counted). Recursive: passes over the edge
  list until fixed point (merged tracks re-tested against neighbours).

Hard quality gates:
  - coverage may not drop: constructive rep-level 2cm-cover-cell guard - a merge
    that would empty a covered cell without re-covering it is vetoed (counted).
  - merge = union of observations; nothing is deleted; full member->consensus
    provenance saved.

Baseline = v1.1 candidate (user-approved, E6 output = E3 stock + injected rescue
points). Regression anchors asserted against E6 stats.json.

Reads ONLY frozen capture data + prior experiment products; writes ONLY into
E8_shell_collapse/. python3.11.
"""
import sqlite3, numpy as np, json, os, sys, time, hashlib
from collections import defaultdict
from scipy.spatial import cKDTree

MAX_IMAGE_ID = 2147483647
# ---- S1 constants (byte-identical) ----
REPROJ_GATE_PX = 3.0        # support recovery + bridge query radius (S1 ruler)
THETA_GATE_DEG = 2.0
FLOOR_SLAB = 0.06
COVER_SLAB = 0.03
CELL_THICK = 0.05
CELL_COVER = 0.02
# ---- E6 ghost metrics (byte-identical) ----
DBL_BAND = (-0.06, -0.015)
BELOW_FLOOR = -0.10
CHAIR_NEARFLOOR_M = 0.05
# ---- E8 merge constants ----
MERGE_MAX_REPROJ_PX = 4.0   # COLMAP merge criterion (task-fixed, source-verifiable)
MERGE_MAX_DIST_M = 0.05     # AUXILIARY distance cap (evidence prerequisite unchanged):
                            # shell = 2-3.5cm second layer; without this cap, low-parallax
                            # obs unions pass 4px while being depth-ambiguity smears up to
                            # ~0.4m long (first cap50 run: member displacement p90=0.39m,
                            # 490 new below-floor points). Distance only VETOES, never merges.
DLT_ENVELOPE_M = 0.01       # consensus DLT accepted only inside member bbox +- this margin;
                            # else fall back to track-length weighted average (COLMAP's own
                            # merge position). Guards the same depth-ambiguity dive.
ROOT_FANOUT_CAP = 20        # a track root touched by >20 cloud points is skipped (logged)
WALL_MIN_FH = 0.10          # wall-ruler slab excludes floor points
WALL_FIT_MIN_FH = 0.30      # dominant-wall plane fit uses points well above floor
WALL_SLAB = 0.06            # +-6cm slab around dominant wall plane (mirror of FLOOR_SLAB)

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
S1D = f"{EXP}/S1_twoview_lifecycle"
E3D = f"{EXP}/E3_birth_discipline"
E6D = f"{EXP}/E6_rescue_inject"
TFD = f"{EXP}/TRAILS_forensics"
OUT_BASE = f"{EXP}/E8_shell_collapse"
CAPS = {
    "cap50": {
        "dir": f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17",
        "chair_roi": {"X": (0.25, 1.05), "Z": (-1.70, -0.55)},
        "expect_pairs_pass": 48226,
        "anchor_band_before": 3917,
    },
    "cap51": {
        "dir": f"{ROOT}/data/pocketworld_captures/cap51/device_full_pull_2026-07-17",
        "chair_roi": None,
        "expect_pairs_pass": 28224,
        "anchor_band_before": 6880,
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

# ---------------- S1-identical floor rulers ----------------
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
    near_floor = np.abs(y - y_floor) <= CHAIR_NEARFLOOR_M
    return {"n_roi": int(len(P)), "n_roi_near_floor_5cm": int(near_floor.sum())}

# ---------------- E8 wall ruler (declared proxy, frozen on BEFORE cloud) ----------------
def fit_dominant_wall(xyz, floor_h, pn):
    """Deterministic dominant vertical plane: scan 180 horizontal directions,
    1cm offset histogram over points with floor_h > WALL_FIT_MIN_FH; max bin wins.
    Returns (d, off): plane = {p : p.d == off}."""
    a = np.array([1.0, 0, 0])
    if abs(pn @ a) > 0.9: a = np.array([0, 0, 1.0])
    u = a - (a @ pn) * pn; u /= np.linalg.norm(u)
    v = np.cross(pn, u)
    P = xyz[floor_h > WALL_FIT_MIN_FH]
    best = (None, None, -1)
    for i in range(180):
        th = np.deg2rad(i)
        d = np.cos(th)*u + np.sin(th)*v
        pr = P @ d
        lo, hi = pr.min(), pr.max()
        cnt, edges = np.histogram(pr, bins=np.arange(lo, hi + 0.01, 0.01))
        j = int(np.argmax(cnt))
        if cnt[j] > best[2]:
            best = (d, 0.5*(edges[j]+edges[j+1]), int(cnt[j]))
    d, c0, _ = best
    pr = xyz[floor_h > WALL_FIT_MIN_FH] @ d
    off = float(np.median(pr[np.abs(pr - c0) <= 0.03]))
    return d, off

def wall_metrics(xyz, floor_h, d, off, pn):
    """Mirror of floor ruler on the dominant wall: slab +-6cm along wall normal,
    5cm cells on (in-wall horizontal axis, height), per-cell p90-p10 of normal dist."""
    sd = xyz @ d - off
    m = (np.abs(sd) <= WALL_SLAB) & (floor_h > WALL_MIN_FH)
    P, s, fh = xyz[m], sd[m], floor_h[m]
    out = {"n_wall_slab": int(m.sum())}
    if len(P) < 100:
        out.update({"thickness_med_cell_p90p10_m": None, "thickness_p90_cell_m": None})
        return out
    w = np.cross(pn, d); w /= np.linalg.norm(w)
    ca = np.floor((P @ w)/CELL_THICK).astype(np.int64)
    cb = np.floor(fh/CELL_THICK).astype(np.int64)
    key = ca * 1000003 + cb
    order = np.argsort(key)
    key_s, s_s = key[order], s[order]
    bounds = np.flatnonzero(np.diff(key_s)) + 1
    groups = np.split(s_s, bounds)
    spreads = [float(np.percentile(g,90) - np.percentile(g,10)) for g in groups if len(g) >= 8]
    out["thickness_med_cell_p90p10_m"] = float(np.median(spreads)) if spreads else None
    out["thickness_p90_cell_m"] = float(np.percentile(spreads,90)) if spreads else None
    out["n_thickness_cells"] = len(spreads)
    return out

# ---------------- renders ----------------
def xsec_panel(u_arr, fd_mm, colors, W=1500, H=520, umin=None, umax=None, band=True):
    """ghost_crosssection-style side view: horizontal in-plane coord vs signed mm
    distance in [-60,+60]; dark bg, 0-line gray, ghost band shaded."""
    c = np.full((H, W, 3), 20, np.uint8)
    FMIN, FMAX = -60.0, 60.0
    if umin is None: umin, umax = float(u_arr.min()), float(u_arr.max())
    def px(u, fd):
        x = ((u - umin) / max(umax - umin, 1e-9) * (W - 40) + 20).astype(int)
        y = ((FMAX - fd) / (FMAX - FMIN) * (H - 60) + 30).astype(int)
        return x, y
    _, y0 = px(np.array([0.0]), np.array([0.0])); y0 = int(y0[0])
    c[y0-1:y0+1, 20:W-20] = (70, 70, 70)
    if band:
        _, y1 = px(np.array([0.0]), np.array([-15.0]))
        _, y2 = px(np.array([0.0]), np.array([-60.0]))
        c[int(y1[0]):int(y2[0]), 20:W-20] = (45, 25, 25)
        c[y0-1:y0+1, 20:W-20] = (70, 70, 70)
    m = (np.abs(fd_mm) <= 60)
    x, y = px(u_arr[m], fd_mm[m])
    cols = colors[m] if colors.ndim > 1 else np.tile(colors, (int(m.sum()), 1))
    ok = (x >= 1) & (x < W-1) & (y >= 1) & (y < H-1)
    for xi, yi, ci in zip(x[ok], y[ok], cols[ok]):
        c[yi-1:yi+2, xi-1:xi+2] = ci
    return c, umin, umax

def ortho_panel(xyz, rgb, ax0, ax1, W, H, lims, flip1=False):
    c = np.full((H, W, 3), 15, np.uint8)
    (a0, a1), (b0, b1) = lims
    x = ((xyz[:, ax0] - a0) / max(a1 - a0, 1e-9) * (W - 20) + 10).astype(int)
    t = xyz[:, ax1]
    if flip1: t = -t
    tb0, tb1 = (-b1, -b0) if flip1 else (b0, b1)
    y = ((tb1 - t) / max(tb1 - tb0, 1e-9) * (H - 20) + 10).astype(int)
    ok = (x >= 0) & (x < W) & (y >= 0) & (y < H)
    order = np.argsort(-xyz[:, 1])   # paint low last for top view stability
    for i in order:
        if ok[i]: c[y[i], x[i]] = rgb[i]
    return c

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
    W_img, H_img = cam[2], cam[3]
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

    xyz_prod, rgb_prod = read_ply_xyzrgb(PLY)
    nProd = len(xyz_prod)
    ply_sha = sha256(PLY)
    wall["load_s"] = round(time.perf_counter()-t0, 1)

    # ---- upstream product SHA consistency ----
    s1_stats = json.load(open(f"{S1D}/{cap}/stats.json"))
    assert s1_stats["inputs"]["baseline_ply_sha256"] == ply_sha, "S1 ran on a different PLY!"
    fpi = json.load(open(f"{TFD}/{cap}/fingerprints_info.json"))
    assert fpi["inputs"]["ply_sha256"] == ply_sha, "E2-A fingerprints on a different PLY!"
    fpz = np.load(f"{TFD}/{cap}/fingerprints.npz")
    assert len(fpz["xyz"]) == nProd and np.allclose(fpz["xyz"], xyz_prod)
    pn, pd = fpz["plane_n"].astype(float), float(fpz["plane_d"])
    floor_h_prod = fpz["floor_h"].astype(float)

    e3a = np.load(f"{E3D}/{cap}/e3_arrays.npz", allow_pickle=True)
    keep_e3 = ~e3a["cull"]
    xyz_e3, rgb_e3 = xyz_prod[keep_e3], rgb_prod[keep_e3]
    floor_h_e3 = floor_h_prod[keep_e3]
    nE3 = len(xyz_e3)

    prov = np.load(f"{E6D}/{cap}/rescue_provenance_{cap}.npz")
    P_pos = prov["pos"].astype(float); P_f1 = prov["f1"]; P_f2 = prov["f2"]
    P_xy1 = prov["xy1"].astype(float); P_xy2 = prov["xy2"].astype(float)
    P_dprod = prov["dist_prod"].astype(float)
    inj_idx = prov["inj_idx"]; inj_rgb = prov["inj_rgb"]
    nPairs = len(P_pos)
    assert nPairs == cfg["expect_pairs_pass"]
    P_fh = P_pos @ pn + pd

    # ---- re-extract rescue pairs WITH node ids; assert identity vs E6 provenance ----
    t0 = time.perf_counter()
    pair_members = defaultdict(list)
    for node in np.flatnonzero(counts[np.searchsorted(uniq, roots)] == 2):
        pair_members[int(roots[node])].append(int(node))
    off_list = np.array([offset[i] for i in img_ids] + [N], dtype=np.int64)
    iid_list = np.array(img_ids, dtype=np.int64)
    Rq_pos, Rq_f1, Rq_f2, Rq_n1, Rq_n2, Rq_root = [], [], [], [], [], []
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
            Pm = K @ np.hstack([pose_R[fid], pose_t[fid].reshape(3,1)])
            A.append(xy[0]*Pm[2]-Pm[0]); A.append(xy[1]*Pm[2]-Pm[1])
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
        Rq_pos.append(X); Rq_f1.append(f1); Rq_f2.append(f2)
        Rq_n1.append(nds[0]); Rq_n2.append(nds[1]); Rq_root.append(rt)
    Rq_pos = np.array(Rq_pos)
    assert len(Rq_pos) == nPairs, f"pair re-extraction count {len(Rq_pos)} != {nPairs}"
    assert np.allclose(Rq_pos, P_pos, atol=1e-9)
    assert np.array_equal(np.array(Rq_f1), P_f1) and np.array_equal(np.array(Rq_f2), P_f2)
    P_n1 = np.array(Rq_n1); P_n2 = np.array(Rq_n2); P_root = np.array(Rq_root)
    wall["pair_reextract_s"] = round(time.perf_counter()-t0, 1)
    log(f"pairs re-extracted with node ids: {nPairs} (identity vs E6 provenance asserted)")

    # ---- v1.1 BEFORE cloud (stock float64 from prod + injected float64 from provenance) ----
    pts = np.vstack([xyz_e3, P_pos[inj_idx]])
    cols = np.vstack([rgb_e3, inj_rgb]).astype(np.uint8)
    fh_before = np.concatenate([floor_h_e3, P_fh[inj_idx]])
    nV = len(pts)
    v11_xyz_ply, v11_rgb_ply = read_ply_xyzrgb(f"{E6D}/{cap}/v1_1_candidate_{cap}.ply")
    assert len(v11_xyz_ply) == nV
    assert np.allclose(v11_xyz_ply, pts.astype(np.float32).astype(np.float64))
    assert np.array_equal(v11_rgb_ply, cols)
    v11_sha = sha256(f"{E6D}/{cap}/v1_1_candidate_{cap}.ply")
    is_inj = np.zeros(nV, bool); is_inj[nE3:] = True
    log(f"v1.1 baseline reconstructed: {nV} pts ({nE3} stock + {nV-nE3} injected), PLY identity asserted")

    # ---- observation recovery for stock points (S1-identical) + per-frame projections ----
    t0 = time.perf_counter()
    obs = [[] for _ in range(nV)]           # (fid, node, x, y)
    # injected points: their two birth observations (known exactly)
    for k, pi in enumerate(inj_idx):
        gi = nE3 + k
        iid1, iid2 = int(P_f1[pi])+1, int(P_f2[pi])+1
        obs[gi].append((int(P_f1[pi]), int(P_n1[pi]), float(P_xy1[pi,0]), float(P_xy1[pi,1])))
        obs[gi].append((int(P_f2[pi]), int(P_n2[pi]), float(P_xy2[pi,0]), float(P_xy2[pi,1])))
    # pair->frame lookup for bridge queries
    pairs_by_f1 = defaultdict(list); pairs_by_f2 = defaultdict(list)
    for i in range(nPairs):
        pairs_by_f1[int(P_f1[i])].append(i)
        pairs_by_f2[int(P_f2[i])].append(i)
    bridgeP = np.full(nPairs, -1, np.int64)   # nearest v1.1 point to kp1 in f1
    bridgeQ = np.full(nPairs, -1, np.int64)   # nearest v1.1 point to kp2 in f2
    node_count_ge2 = counts[np.searchsorted(uniq, roots)] >= 2
    for fid in sorted(pose_R):
        iid = fid + 1
        if iid not in offset: continue
        R, t = pose_R[fid], pose_t[fid]
        Xc = pts @ R.T + t
        infront = Xc[:,2] > 1e-6
        uv = np.full((nV,2), -1e9)
        z = Xc[infront,2]
        uv[infront,0] = f_*Xc[infront,0]/z + cx_
        uv[infront,1] = f_*Xc[infront,1]/z + cy_
        inimg = infront & (uv[:,0]>=-REPROJ_GATE_PX) & (uv[:,0]<=W_img+REPROJ_GATE_PX) \
                        & (uv[:,1]>=-REPROJ_GATE_PX) & (uv[:,1]<=H_img+REPROJ_GATE_PX)
        q_idx = np.flatnonzero(inimg)
        if len(q_idx) == 0: continue
        # (a) stock support: nearest matched keypoint within 3px (S1-identical, stock only)
        base = offset[iid]
        nodes = np.arange(base, base + kp_count[iid])
        nodes = nodes[node_count_ge2[nodes]]
        if len(nodes):
            ktree = cKDTree(kp_xy[iid][nodes - base])
            stock_q = q_idx[q_idx < nE3]
            if len(stock_q):
                dd, kk = ktree.query(uv[stock_q], k=1, distance_upper_bound=REPROJ_GATE_PX, workers=-1)
                hit = np.isfinite(dd)
                for gi, ki in zip(stock_q[hit], kk[hit]):
                    node = int(nodes[ki])
                    xyk = kp_xy[iid][node - base]
                    obs[gi].append((fid, node, float(xyk[0]), float(xyk[1])))
        # (b) pair bridge reverse query: nearest projecting v1.1 point within 3px
        ptree_uv = cKDTree(uv[q_idx])
        for side, plist, xyarr, tgt in (("1", pairs_by_f1.get(fid, []), P_xy1, bridgeP),
                                         ("2", pairs_by_f2.get(fid, []), P_xy2, bridgeQ)):
            if not plist: continue
            pl = np.array(plist)
            dd, kk = ptree_uv.query(xyarr[pl], k=1, distance_upper_bound=REPROJ_GATE_PX, workers=-1)
            hit = np.isfinite(dd)
            tgt[pl[hit]] = q_idx[kk[hit]]
    wall["obs_recovery_s"] = round(time.perf_counter()-t0, 1)
    n_obs = np.array([len(o) for o in obs])
    log(f"obs recovery: stock ge2-obs={int((n_obs[:nE3]>=2).sum())}/{nE3}, "
        f"1-obs={int((n_obs[:nE3]==1).sum())}, 0-obs={int((n_obs[:nE3]==0).sum())} "
        f"({wall['obs_recovery_s']}s)")

    # ---- evidence edges ----
    t0 = time.perf_counter()
    root_pts = defaultdict(set)
    for gi in range(nV):
        for (fid, node, _, _) in obs[gi]:
            root_pts[int(roots[node])].add(gi)
    edgesA = set()
    n_root_skipped = 0
    root_fanout_hist = defaultdict(int)
    for rt, s in root_pts.items():
        k = len(s)
        root_fanout_hist[k] += 1
        if k < 2: continue
        if k > ROOT_FANOUT_CAP:
            n_root_skipped += 1; continue
        s = sorted(s)
        for i in range(len(s)):
            for j in range(i+1, len(s)):
                edgesA.add((s[i], s[j]))
    edgesB = {}
    n_bridge_both = n_bridge_cross = 0
    for i in range(nPairs):
        a, b = int(bridgeP[i]), int(bridgeQ[i])
        if a < 0 or b < 0: continue
        n_bridge_both += 1
        if a == b: continue
        n_bridge_cross += 1
        e = (min(a,b), max(a,b))
        if e not in edgesB: edgesB[e] = i          # remember bridging pair (its obs join the test)
    edges_all = sorted(edgesA | set(edgesB.keys()))
    n_g1_excluded_bridges = sum(1 for e, i in edgesB.items() if P_dprod[i] <= 0.02)
    wall["edges_s"] = round(time.perf_counter()-t0, 1)
    log(f"edges: A(shared-track)={len(edgesA)} B(pair-bridge)={len(edgesB)} "
        f"(cross-point bridges {n_bridge_cross}/{n_bridge_both} both-side hits; "
        f"G1-excluded-pair bridges {n_g1_excluded_bridges}) union={len(edges_all)} "
        f"roots skipped fanout>{ROOT_FANOUT_CAP}: {n_root_skipped}")

    # ---- merge machinery (COLMAP all-or-nothing at weighted trial position) ----
    t0 = time.perf_counter()
    y_floor = detect_floor_y(xyz_prod)   # production ruler anchor (S1/E6-identical)
    pparent = np.arange(nV, dtype=np.int64)
    def pfind(x):
        r = x
        while pparent[r] != r: r = pparent[r]
        while pparent[x] != r: pparent[x], x = r, pparent[x]
        return r
    rep_pos = pts.copy()
    rep_len = np.maximum(n_obs, 1).astype(np.int64)
    rep_obs = {}     # rep -> dict {(fid,node): (x,y)}  (lazy; virgin points read from obs[])
    def get_obs_dict(r):
        if r in rep_obs: return rep_obs[r]
        return {(fid, node): (x, y) for (fid, node, x, y) in obs[r]}
    # rep-level 2cm cover-cell bookkeeping (constructive coverage guard)
    def cov_cell(p):
        if abs(p[1] - y_floor) <= COVER_SLAB:
            return (int(np.floor(p[0]/CELL_COVER)), int(np.floor(p[2]/CELL_COVER)))
        return None
    cell_cnt = defaultdict(int)
    for gi in range(nV):
        cc = cov_cell(pts[gi])
        if cc is not None: cell_cnt[cc] += 1
    def reproj_ok(X, obs_items):
        for (fid, node), (x, y) in obs_items:
            R, t = pose_R[fid], pose_t[fid]
            Xc = R @ X + t
            if Xc[2] <= 0: return False, "neg_depth"
            u = f_*Xc[0]/Xc[2] + cx_
            v = f_*Xc[1]/Xc[2] + cy_
            if np.hypot(u - x, v - y) > MERGE_MAX_REPROJ_PX: return False, "reproj_gt4px"
        return True, None
    def dlt(obs_items):
        A = []
        for (fid, node), (x, y) in obs_items:
            Pm = K @ np.hstack([pose_R[fid], pose_t[fid].reshape(3,1)])
            A.append(x*Pm[2] - Pm[0]); A.append(y*Pm[2] - Pm[1])
        _,_,Vt = np.linalg.svd(np.array(A))
        Xh = Vt[-1]
        if abs(Xh[3]) < 1e-12: return None
        return Xh[:3]/Xh[3]
    stats_m = defaultdict(int)
    n_pass_total = 0
    passes = 0
    while True:
        passes += 1
        n_merged_this_pass = 0
        for e in edges_all:
            ra, rb = pfind(e[0]), pfind(e[1])
            if ra == rb: continue
            stats_m["attempted"] += 1
            if np.linalg.norm(rep_pos[ra] - rep_pos[rb]) > MERGE_MAX_DIST_M:
                stats_m["skip_dist_gt5cm"] += 1; continue
            oa, ob = get_obs_dict(ra), get_obs_dict(rb)
            merged = dict(oa); merged.update(ob)
            if e in edgesB:                      # bridging pair's own obs join the track+test
                pi = edgesB[e]
                merged[(int(P_f1[pi]), int(P_n1[pi]))] = (float(P_xy1[pi,0]), float(P_xy1[pi,1]))
                merged[(int(P_f2[pi]), int(P_n2[pi]))] = (float(P_xy2[pi,0]), float(P_xy2[pi,1]))
            la, lb = rep_len[ra], rep_len[rb]
            Xtrial = (la*rep_pos[ra] + lb*rep_pos[rb]) / (la + lb)
            items = list(merged.items())
            ok, why = reproj_ok(Xtrial, items)
            if not ok:
                stats_m[f"fail_{why}"] += 1; continue
            Xfin = dlt(items)
            if Xfin is not None:
                lo_env = np.minimum(rep_pos[ra], rep_pos[rb]) - DLT_ENVELOPE_M
                hi_env = np.maximum(rep_pos[ra], rep_pos[rb]) + DLT_ENVELOPE_M
                ok2, _ = reproj_ok(Xfin, items)
                if (not ok2) or np.any(Xfin < lo_env) or np.any(Xfin > hi_env):
                    Xfin = Xtrial; stats_m["dlt_fallback_trial"] += 1
                else:
                    stats_m["dlt_used"] += 1
            else:
                Xfin = Xtrial; stats_m["dlt_fallback_trial"] += 1
            # constructive coverage guard (rep-level)
            cca, ccb, ccn = cov_cell(rep_pos[ra]), cov_cell(rep_pos[rb]), cov_cell(Xfin)
            veto = False
            for cc in (cca, ccb):
                if cc is None: continue
                rem = (1 if cc == cca else 0) + (1 if cc == ccb else 0)
                if cell_cnt[cc] - rem <= 0 and ccn != cc:
                    veto = True; break
            if veto:
                stats_m["cov_guard_veto"] += 1; continue
            # commit
            if cca is not None: cell_cnt[cca] -= 1
            if ccb is not None: cell_cnt[ccb] -= 1
            if ccn is not None: cell_cnt[ccn] += 1
            pparent[rb] = ra
            rep_obs[ra] = merged
            rep_obs.pop(rb, None)
            rep_pos[ra] = Xfin
            rep_len[ra] = la + lb
            n_merged_this_pass += 1
            n_pass_total += 1
        log(f" merge pass {passes}: merged {n_merged_this_pass} (total {n_pass_total})")
        if n_merged_this_pass == 0: break
        if passes >= 10:
            log(" WARNING: pass cap hit"); break
    wall["merge_s"] = round(time.perf_counter()-t0, 1)

    # ---- assemble AFTER cloud ----
    rep_of = np.array([pfind(i) for i in range(nV)])
    rep_ids, rep_sizes = np.unique(rep_of, return_counts=True)
    merged_reps = rep_ids[rep_sizes >= 2]
    merged_rep_set = set(merged_reps.tolist())
    untouched = np.array([rep_of[i] == i and i not in merged_rep_set for i in range(nV)])
    members_mask = ~untouched
    group_of = np.full(nV, -1, np.int64)
    for g, r in enumerate(merged_reps):
        group_of[rep_of == r] = g
    # consensus color = obs-count weighted mean of member colors
    cons_pos = np.zeros((len(merged_reps), 3))
    cons_rgb = np.zeros((len(merged_reps), 3), np.uint8)
    cons_nobs = np.zeros(len(merged_reps), np.int64)
    cons_nmem = np.zeros(len(merged_reps), np.int64)
    for g, r in enumerate(merged_reps):
        mem = np.flatnonzero(rep_of == r)
        wgt = np.maximum(n_obs[mem], 1).astype(float)
        cons_pos[g] = rep_pos[r]
        cons_rgb[g] = np.clip(np.round((cols[mem].astype(float) * wgt[:,None]).sum(0) / wgt.sum()), 0, 255).astype(np.uint8)
        cons_nobs[g] = len(rep_obs.get(r, {})) if r in rep_obs else n_obs[r]
        cons_nmem[g] = len(mem)
    after_pts = np.vstack([pts[untouched], cons_pos]) if len(merged_reps) else pts[untouched]
    after_rgb = np.vstack([cols[untouched], cons_rgb]) if len(merged_reps) else cols[untouched]
    fh_after = np.concatenate([fh_before[untouched], cons_pos @ pn + pd]) if len(merged_reps) else fh_before[untouched]
    n_members = int(members_mask.sum())
    log(f"merged groups={len(merged_reps)} members={n_members} -> after cloud {len(after_pts)} pts "
        f"(delta {len(after_pts)-nV})")

    # displacement of members to consensus
    disp = np.linalg.norm(pts[members_mask] - cons_pos[group_of[members_mask]], axis=1) if n_members else np.zeros(0)

    # ---- metrics before/after ----
    t0 = time.perf_counter()
    fl_before = floor_metrics(pts, y_floor)
    fl_after = floor_metrics(after_pts, y_floor)
    dwall, woff = fit_dominant_wall(pts, fh_before, pn)
    wl_before = wall_metrics(pts, fh_before, dwall, woff, pn)
    wl_after = wall_metrics(after_pts, fh_after, dwall, woff, pn)
    band_before = int(((fh_before >= DBL_BAND[0]) & (fh_before < DBL_BAND[1])).sum())
    band_after = int(((fh_after >= DBL_BAND[0]) & (fh_after < DBL_BAND[1])).sum())
    below_before = int((fh_before < BELOW_FLOOR).sum())
    below_after = int((fh_after < BELOW_FLOOR).sum())
    assert band_before == cfg["anchor_band_before"], f"band anchor mismatch {band_before}"
    roi_before = chair_roi_metrics(pts, cfg["chair_roi"], y_floor)
    roi_after = chair_roi_metrics(after_pts, cfg["chair_roi"], y_floor)
    wall["metrics_s"] = round(time.perf_counter()-t0, 1)

    # E6 regression anchors (before == E6 'after')
    e6s = json.load(open(f"{E6D}/{cap}/stats.json"))
    a2 = e6s["check_1_four_rulers"]["ruler_2_floor_thickness"]["after"]
    assert abs(fl_before["thickness_med_cell_p90p10_m"] - a2["thickness_med_cell_p90p10_m"]) < 1e-6
    assert fl_before["cover_cells_2cm"] == a2["cover_cells_2cm"]

    # ---- double-floor band evidence accounting (does connectivity reach the shell?) ----
    in_band = (fh_before >= DBL_BAND[0]) & (fh_before < DBL_BAND[1])
    band_idx = np.flatnonzero(in_band)
    e_pts = set()
    for e in edges_all: e_pts.add(e[0]); e_pts.add(e[1])
    band_with_edge = int(sum(1 for i in band_idx if i in e_pts))
    band_ge2obs = int((n_obs[band_idx] >= 2).sum())
    band_merged = int(members_mask[band_idx].sum())
    comp_sizes = rep_sizes[rep_sizes >= 2]

    # ---- renders ----
    t0 = time.perf_counter()
    from PIL import Image
    a = np.array([1.0,0,0])
    if abs(pn @ a) > 0.9: a = np.array([0,0,1.0])
    u_ax = a - (a @ pn) * pn; u_ax /= np.linalg.norm(u_ax)
    # floor cross-section: before all light-gray; after untouched gray, consensus green
    ub = pts @ u_ax; ua = after_pts @ u_ax
    colb = np.tile(np.array([185,180,175], np.uint8), (nV,1))
    cola = np.vstack([np.tile(np.array([185,180,175], np.uint8), (int(untouched.sum()),1)),
                      np.tile(np.array([80,230,110], np.uint8), (len(merged_reps),1))])
    pA, umin, umax = xsec_panel(ub, fh_before*1000, colb)
    pB, _, _ = xsec_panel(ua, fh_after*1000, cola, umin=umin, umax=umax)
    gap = np.full((26, pA.shape[1], 3), 40, np.uint8)
    Image.fromarray(np.concatenate([pA, gap, pB], 0)).save(f"{out}/ghost_crosssection_floor_{cap}.png")
    # wall cross-section
    w_ax = np.cross(pn, dwall); w_ax /= np.linalg.norm(w_ax)
    wb_m = fh_before > WALL_MIN_FH; wa_m = fh_after > WALL_MIN_FH
    pA2, um2, ux2 = xsec_panel((pts[wb_m]) @ w_ax, (pts[wb_m] @ dwall - woff)*1000, colb[wb_m], band=False)
    pB2, _, _ = xsec_panel((after_pts[wa_m]) @ w_ax, (after_pts[wa_m] @ dwall - woff)*1000, cola[wa_m],
                           umin=um2, umax=ux2, band=False)
    Image.fromarray(np.concatenate([pA2, gap, pB2], 0)).save(f"{out}/ghost_crosssection_wall_{cap}.png")
    # true-color side-by-side (top XZ + elevation XY), same limits
    lo = np.percentile(pts, 1, axis=0); hi = np.percentile(pts, 99, axis=0)
    limsT = ((lo[0], hi[0]), (lo[2], hi[2])); limsE = ((lo[0], hi[0]), (lo[1], hi[1]))
    PW, PH = 850, 700
    tb = ortho_panel(pts, cols, 0, 2, PW, PH, limsT)
    ta = ortho_panel(after_pts, after_rgb, 0, 2, PW, PH, limsT)
    eb = ortho_panel(pts, cols, 0, 1, PW, PH, limsE, flip1=True)
    ea = ortho_panel(after_pts, after_rgb, 0, 1, PW, PH, limsE, flip1=True)
    gv = np.full((PH, 20, 3), 40, np.uint8)
    row1 = np.concatenate([tb, gv, ta], 1); row2 = np.concatenate([eb, gv, ea], 1)
    gh = np.full((20, row1.shape[1], 3), 40, np.uint8)
    Image.fromarray(np.concatenate([row1, gh, row2], 0)).save(f"{out}/side_by_side_{cap}.png")
    wall["renders_s"] = round(time.perf_counter()-t0, 1)

    # ---- output clouds ----
    ply_cand = f"{out}/e8_candidate_{cap}.ply"
    write_ply_xyzrgb(ply_cand, after_pts, after_rgb,
                     f"E8 shell-collapse candidate {cap}: v1.1 + observation-connectivity COLMAP merge "
                     f"(all-or-nothing 4px, consensus=multiview DLT); merge-not-delete")
    diff_pts = np.vstack([pts[untouched], pts[members_mask], cons_pos]) if len(merged_reps) else pts[untouched]
    diff_rgb = np.vstack([np.tile(np.array([120,120,120], np.uint8), (int(untouched.sum()),1)),
                          np.tile(np.array([255,40,40], np.uint8), (n_members,1)),
                          np.tile(np.array([0,220,0], np.uint8), (len(merged_reps),1))]) \
               if len(merged_reps) else np.tile(np.array([120,120,120], np.uint8), (int(untouched.sum()),1))
    ply_diff = f"{out}/diff_collapse_{cap}.ply"
    write_ply_xyzrgb(ply_diff, diff_pts, diff_rgb,
                     f"E8 diff {cap}: red=merged twin members (original positions), green=consensus points, gray=untouched")
    np.savez_compressed(f"{out}/collapse_provenance_{cap}.npz",
                        rep_of=rep_of, group_of=group_of, untouched=untouched,
                        cons_pos=cons_pos, cons_rgb=cons_rgb, cons_nobs=cons_nobs, cons_nmem=cons_nmem,
                        n_obs=n_obs, is_inj=is_inj, member_disp=disp,
                        bridgeP=bridgeP, bridgeQ=bridgeQ)

    def q(a, pcts=(10,50,90)):
        a = np.asarray(a, float); a = a[np.isfinite(a)]
        return {f"p{p}": round(float(np.percentile(a,p)),5) for p in pcts} if len(a) else {}

    thin_pct = None
    if fl_before["thickness_med_cell_p90p10_m"] and fl_after["thickness_med_cell_p90p10_m"]:
        thin_pct = round(100.0*(fl_after["thickness_med_cell_p90p10_m"]/fl_before["thickness_med_cell_p90p10_m"]-1.0), 2)
    wall_thin_pct = None
    if wl_before.get("thickness_med_cell_p90p10_m") and wl_after.get("thickness_med_cell_p90p10_m"):
        wall_thin_pct = round(100.0*(wl_after["thickness_med_cell_p90p10_m"]/wl_before["thickness_med_cell_p90p10_m"]-1.0), 2)

    fan_hist = {str(k): v for k, v in sorted(root_fanout_hist.items()) if k >= 2}
    stats = {
        "cap": cap,
        "inputs": {"db": DB, "meta": META, "production_ply_sha256": ply_sha,
                   "baseline": "v1.1 candidate (user-approved E6 output; E8 is the next layer on top of it)",
                   "v1_1_ply_sha256": v11_sha},
        "gauge": "production refined poses; NO Sim3, NO realignment; consensus positions from frozen-pose multiview DLT",
        "rule": {
            "evidence": "observation connectivity ONLY (shared verified-track roots + verified-pair bridges incl. G1-excluded <2cm pairs); NO pure-distance merging (cap47 lesson)",
            "merge_test": f"COLMAP all-or-nothing: trial=track-length weighted average; EVERY obs of both tracks (+bridging pair obs) must reproject <= {MERGE_MAX_REPROJ_PX}px with positive depth",
            "aux_distance_cap_m": MERGE_MAX_DIST_M,
            "aux_distance_note": "distance only VETOES (never creates a merge); added after first run showed 4px all-or-nothing cannot constrain depth on low-parallax obs unions (displacement p90=0.39m, 490 new below-floor)",
            "consensus_position": f"multiview DLT over merged obs, accepted only if it passes the same all-obs test AND stays inside member bbox +-{DLT_ENVELOPE_M}m; else track-length weighted average (COLMAP's own merge position); counted",
            "recursive": "passes over edge list to fixed point",
            "coverage_guard": "constructive: merge vetoed if it would empty a 2cm cover cell without re-covering it",
        },
        "obs_recovery": {
            "stock_ge2_obs": int((n_obs[:nE3]>=2).sum()), "stock_1_obs": int((n_obs[:nE3]==1).sum()),
            "stock_0_obs": int((n_obs[:nE3]==0).sum()), "n_stock": nE3, "n_injected": nV-nE3,
            "note": "S1-identical recovery (3px nearest verified-matched keypoint per frame); injected points carry their two birth obs exactly",
        },
        "evidence_graph": {
            "edges_shared_track_A": len(edgesA),
            "edges_pair_bridge_B": len(edgesB),
            "bridges_from_G1_excluded_pairs": n_g1_excluded_bridges,
            "pairs_with_both_side_hits": n_bridge_both,
            "pairs_bridging_two_different_points": n_bridge_cross,
            "edges_union": len(edges_all),
            "root_fanout_hist_ge2": fan_hist,
            "roots_skipped_fanout_gt_cap": n_root_skipped,
        },
        "merge_funnel": dict(stats_m) | {"merged_total": n_pass_total, "passes": passes},
        "groups": {
            "n_groups": int(len(merged_reps)), "n_member_points": n_members,
            "group_size_hist": {str(k): int(v) for k, v in
                                zip(*np.unique(comp_sizes, return_counts=True))} if len(comp_sizes) else {},
            "member_displacement_m": q(disp),
            "consensus_nobs": q(cons_nobs) if len(merged_reps) else {},
        },
        "ruler_1_points": {"before_v11": nV, "after_e8": int(len(after_pts)),
                           "delta": int(len(after_pts)-nV),
                           "note": "delta = merged twins collapsing into consensus; observations all retained (union), nothing deleted"},
        "ruler_2_floor_thickness": {"y_floor": round(y_floor,4), "before": fl_before, "after": fl_after,
                                    "med_cell_change_pct": thin_pct},
        "ruler_2b_wall_thickness_proxy": {"wall_normal": [round(float(x),5) for x in dwall],
                                          "wall_offset_m": round(woff,4),
                                          "before": wl_before, "after": wl_after,
                                          "med_cell_change_pct": wall_thin_pct,
                                          "note": "E8-declared proxy ruler (dominant vertical plane frozen on BEFORE cloud, +-6cm slab, 5cm cells, p90-p10 along wall normal); not a certified metric"},
        "ruler_3_coverage_hard_gate": {"before_cells_2cm": fl_before["cover_cells_2cm"],
                                       "after_cells_2cm": fl_after["cover_cells_2cm"],
                                       "delta": fl_after["cover_cells_2cm"] - fl_before["cover_cells_2cm"],
                                       "pass": fl_after["cover_cells_2cm"] >= fl_before["cover_cells_2cm"],
                                       "constructive_vetoes": int(stats_m["cov_guard_veto"])},
        "ruler_4_wallclock_host_proxy_s": wall,
        "ghost_shell": {
            "double_floor_band": {"band_floor_h_m": list(DBL_BAND), "before": band_before, "after": band_after,
                                  "delta": band_after - band_before},
            "below_floor": {"before": below_before, "after": below_after},
            "band_evidence_accounting": {
                "band_points_before": int(len(band_idx)),
                "band_points_with_ge2_obs": band_ge2obs,
                "band_points_touching_any_edge": band_with_edge,
                "band_points_merged": band_merged,
                "note": "answers: does connectivity evidence actually reach the shell?"},
        },
        "chair_roi": {"before": roi_before, "after": roi_after},
        "cap47_reconciliation": {
            "cap47_pure_spatial_FRAG_MERGE": "-3% thickness, condemned (no observation evidence)",
            "e8_floor_med_cell_change_pct": thin_pct,
            "e8_wall_med_cell_change_pct": wall_thin_pct,
            "e8_double_floor_band_change": band_after - band_before,
        },
    }
    stats["outputs_sha256"] = {os.path.basename(p): sha256(p) for p in
                               [ply_cand, ply_diff,
                                f"{out}/collapse_provenance_{cap}.npz",
                                f"{out}/ghost_crosssection_floor_{cap}.png",
                                f"{out}/ghost_crosssection_wall_{cap}.png",
                                f"{out}/side_by_side_{cap}.png"]}
    json.dump(stats, open(f"{out}/stats.json", "w"), indent=2)
    log(json.dumps({k: stats[k] for k in ("merge_funnel","groups","ruler_2_floor_thickness",
                                           "ruler_3_coverage_hard_gate","ghost_shell")}, indent=1, default=str)[:3000])
    return stats

if __name__ == "__main__":
    caps = sys.argv[1:] or list(CAPS)
    all_path = os.path.join(OUT_BASE, "stats_all.json")
    allstats = json.load(open(all_path)) if os.path.exists(all_path) else {}
    for cap in caps:
        allstats[cap] = run_cap(cap, CAPS[cap])
        json.dump(allstats, open(all_path, "w"), indent=2)
    log("ALL DONE")
