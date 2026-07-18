#!/usr/bin/env python3.11
"""
E6-A rescue injection = v1.1 candidate (cap50 main, cap51 val).

PRINCIPLE (RS discipline): a tie point that passes THE ruler should be published;
the rescue side passed the SAME S1 ruler as the delivered cloud — not publishing
it is a leak. BUT the injection side must be STRICTER than the incumbent side,
never looser. So a rescue pair must survive the FULL v1 gate stack:

  G0  S1 unified rule (byte-identical constants): verified 2-node component,
      structure-only DLT refit with frozen refined production poses/K,
      cull neg-depth / reproj>3px / theta<2deg.               (= rescue definition)
  G1  dedup: >2cm from ANY production point (S1 rescue definition; a point
      already represented is not a hole).
  G2  resurrection guard (STRICTER than stock): >=5cm away from every point the
      user-approved E3 knife culled — injection must not re-populate cleaned zones.
  G3  floor guard (STRICTER than stock E3 -0.10): floor_h >= -0.015 m
      (production-arbitrated plane). Constructively zero new double-floor-band
      (band := floor_h in [-0.06,-0.015]) and zero new below-floor points.
  G4  chair-ROI guard (cap50, STRICTER): no injected point inside chair ROI
      within 5cm of floor (ghost-layer metric must not increase).
  G5  corridor vote bh=8, BOTH observation cameras (STRICTER than stock E3
      net>=0 with possible proxy votes): march E2-A constants (5cm voxel >=6pts
      solid from the E3 candidate cloud, step 4cm, start 25cm, stop 20cm short);
      EITHER corridor with >=8 solid crossings => cull. No proxy votes (both
      corridors are real observation corridors). Too-short corridor (<~55cm)
      has no march evidence => treated clear (declared).
  G6  after-context signature scan (STRICTER than stock: E3 lets flagged points
      earn existence, injected points may NOT be flagged at all): compute the
      E2-A four signatures (S_behind|S_below|S_streak|S_out, byte-identical
      constants) on the combined cloud (E3 candidate + injected); any flagged
      injected point is dropped; iterate to fixed point.

Survivors are colorized by the CERTIFIED production recipe
(lib/capture/colorize_pipeline.dart + representative_color.dart):
  bilinear at (obs_xy - 0.5) on the full-res photo (keypoint space == photo
  space 3840x2160, scale=1), out-of-bounds skipped; representative sample =
  the REAL sample whose luma (.299/.587/.114) hits the lower-median (2 samples
  => the darker one); round+clamp. Missing photo => remaining sample; if no
  sample at all => nearest-production-point color (NN fallback, declared).

CHECKS
  (1) four rulers before(E3 candidate)/after(v1.1)
  (2) ghost-layer recheck, per-item before/after: double-floor band density,
      below-floor count, trail-signature counts (identical detector on both
      clouds), chair ROI near-floor — injection must ADD NOTHING.
  (3) spatial distribution of injected points: hole-filling vs already-dense,
      layered floor/object/high + new 2cm floor coverage cells.

Products ONLY in this directory. No production code touched, no git commits.
Reads only frozen capture data + S1/E3/E2-A research products (SHA-checked).
"""
import sqlite3, numpy as np, json, os, sys, time, hashlib
from collections import defaultdict
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

MAX_IMAGE_ID = 2147483647
# ---- S1 constants (byte-identical) ----
REPROJ_GATE_PX = 3.0
THETA_GATE_DEG = 2.0
FLOOR_SLAB = 0.06
COVER_SLAB = 0.03
CELL_THICK = 0.05
CELL_COVER = 0.02
# ---- E2-A march / signature constants (byte-identical) ----
VOX = 0.05
VOX_SOLID = 6
MARCH_STEP = 0.04
MARCH_START = 0.25
MARCH_STOP = 0.20
BLOCK_MIN_HITS = 3          # E2-A S_behind flag level
DENS_R = 0.10
WISP_MAX_CNT = 10
STREAK_LINK = 0.15
STREAK_MIN = 4
STREAK_ELONG = 3.0
STREAK_ALIGN = 0.80
BELOW_FLOOR = -0.10
CORE_CNT = 40
OUT_DIST = 0.25
OUT_MAX_CNT = 10
# ---- E3 vote constant (user-approved operating point) ----
VOTE_BLOCK_HITS = 8
# ---- E6 injection-side strictness (declared, stricter-not-looser) ----
DEDUP_PROD_M = 0.02         # S1 rescue definition
RESURRECT_GUARD_M = 0.05    # min dist to any E3-culled point
FLOOR_GUARD_M = -0.015      # injected floor_h must be >= this
DBL_BAND = (-0.06, -0.015)  # double-floor band metric
CHAIR_NEARFLOOR_M = 0.05

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
S1D = f"{EXP}/S1_twoview_lifecycle"
E3D = f"{EXP}/E3_birth_discipline"
TFD = f"{EXP}/TRAILS_forensics"
OUT_BASE = f"{EXP}/E6_rescue_inject"
CAPS = {
    "cap50": {
        "dir": f"{ROOT}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17",
        "chair_roi": {"X": (0.25, 1.05), "Z": (-1.70, -0.55)},
        "expect_pairs_pass": 48226, "expect_absent": 15694,
    },
    "cap51": {
        "dir": f"{ROOT}/data/pocketworld_captures/cap51/device_full_pull_2026-07-17",
        "chair_roi": None,
        "expect_pairs_pass": 28224, "expect_absent": 8538,
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

# ---------------- S1-identical rulers ----------------
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

def cover_cells_set(xyz, y_floor):
    y = xyz[:,1]
    m = np.abs(y - y_floor) <= COVER_SLAB
    Q = xyz[m]
    return set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64), np.floor(Q[:,2]/CELL_COVER).astype(np.int64)))

def chair_roi_metrics(xyz, roi, y_floor):
    if roi is None: return None
    m = (xyz[:,0]>=roi["X"][0])&(xyz[:,0]<=roi["X"][1])&(xyz[:,2]>=roi["Z"][0])&(xyz[:,2]<=roi["Z"][1])
    P = xyz[m]
    if len(P)==0: return {"n_roi": 0}
    y = P[:,1]
    near_floor = np.abs(y - y_floor) <= CHAIR_NEARFLOOR_M
    return {"n_roi": int(len(P)), "n_roi_near_floor_5cm": int(near_floor.sum()),
            "frac_roi_near_floor": round(float(near_floor.mean()),4)}

# ---------------- E2-A-identical signature detector ----------------
def detect_signatures(xyz, ray, primC, floor_h, own_key=None, solid=None, cnt10=None, tree=None):
    """Four-signature scan, byte-identical E2-A constants.
    ray: (n,3) unit mean viewing dir per point; primC: (n,3) primary camera per point.
    Returns dict of masks + aux. Caller may pass precomputed voxel solid set."""
    nP = len(xyz)
    if tree is None: tree = cKDTree(xyz)
    if cnt10 is None:
        cnt10 = np.asarray(tree.query_ball_point(xyz, DENS_R, return_length=True, workers=-1))
    key = np.floor(xyz / VOX).astype(np.int64)
    if solid is None:
        vox = defaultdict(int)
        for k in map(tuple, key): vox[k] += 1
        solid = {k for k, v in vox.items() if v >= VOX_SOLID}
    own_vox = [tuple(k) for k in key]
    cam_depth = np.linalg.norm(xyz - primC, axis=1)

    # S_behind
    suspects = np.flatnonzero((cnt10 <= 40) & (cam_depth > 0.8))
    behind_hits = np.zeros(nP, np.int16)
    for pi in suspects:
        C = primC[pi]; X = xyz[pi]
        v = X - C; L = np.linalg.norm(v)
        if L <= MARCH_START + MARCH_STOP + 0.1: continue
        u = v / L
        ts = np.arange(MARCH_START, L - MARCH_STOP, MARCH_STEP)
        sk = np.floor((C[None,:] + ts[:,None]*u[None,:]) / VOX).astype(np.int64)
        hits = 0; prev = None
        for k in map(tuple, sk):
            if k == prev: continue
            prev = k
            if k in solid and k != own_vox[pi]: hits += 1
        behind_hits[pi] = hits
    S_behind = behind_hits >= BLOCK_MIN_HITS

    # S_below
    S_below = floor_h < BELOW_FLOOR

    # S_streak
    wisp = np.flatnonzero(cnt10 <= WISP_MAX_CNT)
    S_streak = np.zeros(nP, bool)
    if len(wisp):
        lab = connected_components(xyz[wisp], STREAK_LINK)
        for lb in np.unique(lab):
            mem = wisp[lab == lb]
            if len(mem) < STREAK_MIN: continue
            P = xyz[mem]; mu = P.mean(0)
            ev, evec = np.linalg.eigh(np.cov((P - mu).T))
            elong_c = float(np.sqrt(max(ev[2], 0) / max(ev[1], 1e-12)))
            axis = evec[:, 2]
            mray = ray[mem].mean(0); mray /= (np.linalg.norm(mray) + 1e-15)
            if elong_c >= STREAK_ELONG and float(abs(axis @ mray)) >= STREAK_ALIGN:
                S_streak[mem] = True

    # S_out
    core = cnt10 >= CORE_CNT
    if core.any():
        ct = cKDTree(xyz[core])
        dist_core, _ = ct.query(xyz, workers=-1)
    else:
        dist_core = np.full(nP, np.inf)
    S_out = (dist_core > OUT_DIST) & (cnt10 <= OUT_MAX_CNT)

    union = S_behind | S_below | S_streak | S_out
    return {"S_behind": S_behind, "S_below": S_below, "S_streak": S_streak,
            "S_out": S_out, "union": union, "cnt10": cnt10, "behind_hits": behind_hits,
            "solid": solid}

def corridor_hits_march(C, X, own_k, solid):
    v = X - C; L = np.linalg.norm(v)
    if L <= MARCH_START + MARCH_STOP + 0.1: return None
    u = v / L
    ts = np.arange(MARCH_START, L - MARCH_STOP, MARCH_STEP)
    sk = np.floor((C[None,:] + ts[:,None]*u[None,:]) / VOX).astype(np.int64)
    hits = 0; prev = None
    for k in map(tuple, sk):
        if k == prev: continue
        prev = k
        if k in solid and k != own_k: hits += 1
    return hits

# ---------------- certified colorize ----------------
def bilinear_sample(img, x, y):
    """COLMAP convention: sample at (x-0.5, y-0.5), bilinear, None if out of bounds.
    img: HxWx3 float32."""
    fx, fy = x - 0.5, y - 0.5
    x0, y0 = int(np.floor(fx)), int(np.floor(fy))
    x1, y1 = x0 + 1, y0 + 1
    h, w = img.shape[:2]
    if x0 < 0 or y0 < 0 or x1 >= w or y1 >= h: return None
    dx, dy = fx - x0, fy - y0
    return ((1-dx)*(1-dy)*img[y0,x0] + dx*(1-dy)*img[y0,x1]
            + (1-dx)*dy*img[y1,x0] + dx*dy*img[y1,x1])

def representative_rgb(samples):
    """production representative_color.dart: lower-median luma REAL sample; round+clamp."""
    if len(samples) == 1:
        s = samples[0]
    else:
        lum = [0.299*s[0] + 0.587*s[1] + 0.114*s[2] for s in samples]
        med = sorted(lum)[(len(lum)-1) >> 1]
        best, bestd = 0, float("inf")
        for k, l in enumerate(lum):
            d = abs(l - med)
            if d < bestd or (d == bestd and l < lum[best]):
                best, bestd = k, d
        s = samples[best]
    return np.clip(np.round(np.asarray(s)), 0, 255).astype(np.uint8)

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

    # ---- S1 / E3 / E2-A products, SHA-consistency ----
    s1_stats = json.load(open(f"{S1D}/{cap}/stats.json"))
    assert s1_stats["inputs"]["baseline_ply_sha256"] == ply_sha, "S1 ran on a different PLY!"
    fpi = json.load(open(f"{TFD}/{cap}/fingerprints_info.json"))
    assert fpi["inputs"]["ply_sha256"] == ply_sha, "E2-A fingerprints on a different PLY!"
    fpz = np.load(f"{TFD}/{cap}/fingerprints.npz")
    assert len(fpz["xyz"]) == nP and np.allclose(fpz["xyz"], xyz)
    ray_prod = fpz["ray"]; prim_fid_prod = fpz["prim_fid"]
    pn, pd = fpz["plane_n"], float(fpz["plane_d"])
    camC_all = fpz["camC"]; cam_fids = fpz["cam_fids"]
    fid2C = {int(f): camC_all[i] for i, f in enumerate(cam_fids)}
    cam_tree = cKDTree(camC_all)

    e3a = np.load(f"{E3D}/{cap}/e3_arrays.npz", allow_pickle=True)
    cull_e3 = e3a["cull"]
    keep_e3 = ~cull_e3
    xyz_e3_ply, rgb_e3_ply = read_ply_xyzrgb(f"{E3D}/{cap}/e3_candidate_{cap}.ply")
    assert len(xyz_e3_ply) == int(keep_e3.sum())
    assert np.allclose(xyz_e3_ply, xyz[keep_e3].astype(np.float32).astype(np.float64))
    xyz_e3, rgb_e3 = xyz[keep_e3], rgb[keep_e3]
    e3_sha = sha256(f"{E3D}/{cap}/e3_candidate_{cap}.ply")
    log(f"prod={nP} e3_candidate={len(xyz_e3)} (E3 culled {int(cull_e3.sum())})")

    # ---- rescue extraction with provenance (S1 rescue code + provenance kept) ----
    t0 = time.perf_counter()
    pair_members = defaultdict(list)
    for node in np.flatnonzero(counts[np.searchsorted(uniq, roots)] == 2):
        pair_members[int(roots[node])].append(int(node))
    off_list = np.array([offset[i] for i in img_ids] + [N], dtype=np.int64)
    iid_list = np.array(img_ids, dtype=np.int64)
    ptree = cKDTree(xyz)
    R_pos, R_f1, R_f2, R_xy1, R_xy2, R_res, R_th, R_dprod = [], [], [], [], [], [], [], []
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
        R_pos.append(X); R_f1.append(f1); R_f2.append(f2)
        R_xy1.append(xy1); R_xy2.append(xy2)
        R_res.append(maxres); R_th.append(th); R_dprod.append(float(dd))
    wall["rescue_extract_s"] = round(time.perf_counter()-t0, 1)
    R_pos = np.array(R_pos); R_f1 = np.array(R_f1); R_f2 = np.array(R_f2)
    R_xy1 = np.array(R_xy1); R_xy2 = np.array(R_xy2)
    R_res = np.array(R_res); R_th = np.array(R_th); R_dprod = np.array(R_dprod)
    assert n_pair_pass == cfg["expect_pairs_pass"], f"pair-pass regression: {n_pair_pass} != {cfg['expect_pairs_pass']}"
    n_absent = int((R_dprod > DEDUP_PROD_M).sum())
    assert n_absent == cfg["expect_absent"], f"absent regression: {n_absent} != {cfg['expect_absent']}"
    log(f"rescue pairs passing S1 rule={n_pair_pass}, absent>2cm={n_absent} ({wall['rescue_extract_s']}s)")

    funnel = {"G0_s1_pass_pairs": int(n_pair_pass)}

    # ---- G1 dedup ----
    alive = R_dprod > DEDUP_PROD_M
    funnel["G1_dedup_gt2cm"] = int(alive.sum())

    # ---- G2 resurrection guard ----
    if cull_e3.any():
        killed_tree = cKDTree(xyz[cull_e3])
        d_kill, _ = killed_tree.query(R_pos, k=1)
    else:
        d_kill = np.full(len(R_pos), np.inf)
    g2_cut = alive & (d_kill < RESURRECT_GUARD_M)
    alive &= d_kill >= RESURRECT_GUARD_M
    funnel["G2_resurrection_guard"] = int(alive.sum())
    funnel["G2_cut"] = int(g2_cut.sum())

    # ---- G3 floor guard (arbitrated plane) ----
    floor_h_R = R_pos @ pn + pd
    g3_cut = alive & (floor_h_R < FLOOR_GUARD_M)
    alive &= floor_h_R >= FLOOR_GUARD_M
    funnel["G3_floor_guard"] = int(alive.sum())
    funnel["G3_cut"] = int(g3_cut.sum())

    # ---- G4 chair ROI guard ----
    y_floor = detect_floor_y(xyz)      # production baseline, same ruler as S1/E3
    roi = cfg["chair_roi"]
    if roi is not None:
        in_roi = ((R_pos[:,0]>=roi["X"][0])&(R_pos[:,0]<=roi["X"][1])
                  &(R_pos[:,2]>=roi["Z"][0])&(R_pos[:,2]<=roi["Z"][1]))
        near_fl = np.abs(R_pos[:,1] - y_floor) <= CHAIR_NEARFLOOR_M
        g4_cut = alive & in_roi & near_fl
        alive &= ~(in_roi & near_fl)
        funnel["G4_chair_roi_guard"] = int(alive.sum())
        funnel["G4_cut"] = int(g4_cut.sum())
    else:
        funnel["G4_chair_roi_guard"] = int(alive.sum())
        funnel["G4_cut"] = 0

    # ---- G7 floor-thickening guard (STRICTER): floor-slab injections must be pure
    # hole-filling. First cap50 run showed floor med-cell thickness 0.0484->0.0517
    # (+3.3mm) because most floor injections land in already-covered cells: they
    # thicken the floor (2-view depth-noise shell pathology) without adding coverage.
    # Rule: injected with |y - y_floor| <= FLOOR_SLAB is kept ONLY if
    #   (a) |y - y_floor| <= COVER_SLAB (contributes coverage), AND
    #   (b) its 2cm cover cell is NOT already covered by the E3 cloud, AND
    #   (c) its 5cm thickness cell has < 8 E3 slab points (not a measured cell).
    cells_before = cover_cells_set(xyz_e3, y_floor)
    slab_e3 = np.abs(xyz_e3[:,1] - y_floor) <= FLOOR_SLAB
    cell_cnt_e3 = defaultdict(int)
    for cxz in zip(np.floor(xyz_e3[slab_e3,0]/CELL_THICK).astype(np.int64),
                   np.floor(xyz_e3[slab_e3,2]/CELL_THICK).astype(np.int64)):
        cell_cnt_e3[cxz] += 1
    dy = np.abs(R_pos[:,1] - y_floor)
    in_slab = dy <= FLOOR_SLAB
    cov_cell = list(zip(np.floor(R_pos[:,0]/CELL_COVER).astype(np.int64),
                        np.floor(R_pos[:,2]/CELL_COVER).astype(np.int64)))
    th_cell = list(zip(np.floor(R_pos[:,0]/CELL_THICK).astype(np.int64),
                       np.floor(R_pos[:,2]/CELL_THICK).astype(np.int64)))
    g7_ok = np.ones(len(R_pos), bool)
    for i in np.flatnonzero(alive & in_slab):
        g7_ok[i] = (dy[i] <= COVER_SLAB and cov_cell[i] not in cells_before
                    and cell_cnt_e3.get(th_cell[i], 0) < 8)
    g7_cut = alive & ~g7_ok
    alive &= g7_ok
    funnel["G7_floor_holefill_only"] = int(alive.sum())
    funnel["G7_cut"] = int(g7_cut.sum())

    # ---- G5 corridor vote bh=8 from BOTH obs cameras (solid = E3 candidate cloud) ----
    t0 = time.perf_counter()
    key_e3 = np.floor(xyz_e3 / VOX).astype(np.int64)
    vox = defaultdict(int)
    for k in map(tuple, key_e3): vox[k] += 1
    solid_e3 = {k for k, v in vox.items() if v >= VOX_SOLID}
    idx_alive = np.flatnonzero(alive)
    g5_blocked = np.zeros(len(R_pos), bool)
    corridor_max_hits = np.full(len(R_pos), -1, np.int16)
    n_short = 0
    for pi in idx_alive:
        own_k = tuple(np.floor(R_pos[pi] / VOX).astype(np.int64))
        mh = -1; short_both = True
        for fid in (R_f1[pi], R_f2[pi]):
            h = corridor_hits_march(pose_C[fid], R_pos[pi], own_k, solid_e3)
            if h is None: continue
            short_both = False
            mh = max(mh, h)
        corridor_max_hits[pi] = mh
        if short_both: n_short += 1          # no march evidence => clear (declared)
        elif mh >= VOTE_BLOCK_HITS: g5_blocked[pi] = True
    alive &= ~g5_blocked
    funnel["G5_corridor_bh8_both_cams"] = int(alive.sum())
    funnel["G5_cut"] = int(g5_blocked.sum())
    funnel["G5_short_corridor_clear"] = int(n_short)
    wall["corridor_vote_s"] = round(time.perf_counter()-t0, 1)
    log(f"funnel after G5: {funnel} ({wall['corridor_vote_s']}s)")

    # ---- per-point rays / primary cams for detector ----
    dir1 = R_pos - camC_all[np.searchsorted(cam_fids, R_f1)]
    dir2 = R_pos - camC_all[np.searchsorted(cam_fids, R_f2)]
    dir1 /= (np.linalg.norm(dir1, axis=1, keepdims=True) + 1e-15)
    dir2 /= (np.linalg.norm(dir2, axis=1, keepdims=True) + 1e-15)
    ray_R = dir1 + dir2
    ray_R /= (np.linalg.norm(ray_R, axis=1, keepdims=True) + 1e-15)
    primC_R = np.array([pose_C[R_f1[i]] for i in range(len(R_pos))])

    ray_e3 = ray_prod[keep_e3]
    primC_e3 = np.empty_like(xyz_e3)
    pf = prim_fid_prod[keep_e3]
    for i in range(len(xyz_e3)):
        fp = int(pf[i])
        primC_e3[i] = fid2C[fp] if fp in fid2C else camC_all[cam_tree.query(xyz_e3[i])[1]]
    floor_h_e3 = fpz["floor_h"][keep_e3]

    # ---- G6 after-context four-signature scan, iterate to fixed point ----
    t0 = time.perf_counter()
    g6_dropped = np.zeros(len(R_pos), bool)
    it = 0
    while True:
        it += 1
        idx = np.flatnonzero(alive)
        comb_xyz = np.vstack([xyz_e3, R_pos[idx]])
        comb_ray = np.vstack([ray_e3, ray_R[idx]])
        comb_primC = np.vstack([primC_e3, primC_R[idx]])
        comb_fh = np.concatenate([floor_h_e3, floor_h_R[idx]])
        det = detect_signatures(comb_xyz, comb_ray, comb_primC, comb_fh)
        inj_flag = det["union"][len(xyz_e3):]
        n_flag = int(inj_flag.sum())
        log(f" G6 iter{it}: injected flagged={n_flag} "
            f"(behind={int(det['S_behind'][len(xyz_e3):].sum())} below={int(det['S_below'][len(xyz_e3):].sum())} "
            f"streak={int(det['S_streak'][len(xyz_e3):].sum())} out={int(det['S_out'][len(xyz_e3):].sum())})")
        if n_flag == 0:
            det_after = det
            break
        g6_dropped[idx[inj_flag]] = True
        alive[idx[inj_flag]] = False
        if it >= 25:
            log(" G6 WARNING: iteration cap hit; residual flags dropped, final det recomputed next pass")
    funnel["G6_signature_clean"] = int(alive.sum())
    funnel["G6_cut"] = int(g6_dropped.sum())
    funnel["G6_iters"] = it
    wall["signature_scan_s"] = round(time.perf_counter()-t0, 1)
    log(f"G6 done: inject {int(alive.sum())} ({wall['signature_scan_s']}s)")

    # ---- before-detector on E3 candidate alone (ghost recheck baseline) ----
    t0 = time.perf_counter()
    det_before = detect_signatures(xyz_e3, ray_e3, primC_e3, floor_h_e3)
    wall["before_detector_s"] = round(time.perf_counter()-t0, 1)

    # ---- certified colorize ----
    t0 = time.perf_counter()
    fid2jpg = {}
    for line in open(f"{d}/sfm_fed_frames.jsonl"):
        j = json.loads(line)
        p = os.path.join(d, "photos_highres", os.path.basename(j["jpegPath"]))
        fid2jpg[j["frameId"]] = p if os.path.exists(p) else None
    n_missing_jpg = sum(1 for v in fid2jpg.values() if v is None)
    inj_idx = np.flatnonzero(alive)
    # group obs by frame
    by_frame = defaultdict(list)     # fid -> list of (inj_row, xy)
    for row, pi in enumerate(inj_idx):
        by_frame[int(R_f1[pi])].append((row, R_xy1[pi]))
        by_frame[int(R_f2[pi])].append((row, R_xy2[pi]))
    samples = defaultdict(list)      # inj_row -> list of rgb float triples
    n_oob = 0
    for fid in sorted(by_frame):
        jp = fid2jpg.get(fid)
        if jp is None: continue
        img = np.asarray(Image.open(jp).convert("RGB"), dtype=np.float32)
        assert img.shape[1] == W and img.shape[0] == H, f"photo dims {img.shape} != camera {W}x{H}"
        for row, xy in by_frame[fid]:
            s = bilinear_sample(img, xy[0], xy[1])
            if s is None: n_oob += 1
            else: samples[row].append(s)
        del img
    inj_rgb = np.zeros((len(inj_idx), 3), np.uint8)
    n_nn_fallback = 0
    for row in range(len(inj_idx)):
        ss = samples.get(row)
        if ss:
            inj_rgb[row] = representative_rgb(ss)
        else:
            n_nn_fallback += 1
            _, k = ptree.query(R_pos[inj_idx[row]], k=1)
            inj_rgb[row] = rgb[k]
    wall["colorize_s"] = round(time.perf_counter()-t0, 1)
    log(f"colorize: {len(inj_idx)} pts, missing jpg frames={n_missing_jpg}, oob_samples={n_oob}, NN fallback pts={n_nn_fallback} ({wall['colorize_s']}s)")

    # ---- v1.1 candidate ----
    inj_xyz = R_pos[inj_idx]
    v11_xyz = np.vstack([xyz_e3, inj_xyz])
    v11_rgb = np.vstack([rgb_e3, inj_rgb])
    p_v11 = os.path.join(out, f"v1_1_candidate_{cap}.ply")
    write_ply_xyzrgb(p_v11, v11_xyz, v11_rgb,
        f"E6-A v1.1 candidate {cap}: E3 candidate + {len(inj_idx)} rescued verified 2-view points (S1 rule + full E3 risk gates stricter-side + certified colorize); production gauge, no Sim3")
    dif_rgb = np.zeros((len(v11_xyz),3), np.uint8); dif_rgb[:] = (120,120,120)
    dif_rgb[len(xyz_e3):] = (0,160,255)
    p_diff = os.path.join(out, f"diff_inject_{cap}.ply")
    write_ply_xyzrgb(p_diff, v11_xyz, dif_rgb,
        f"E6-A diff {cap}: blue=injected rescue points, gray=E3 candidate (user-approved)")

    # ---- checks: four rulers before(E3)/after(v1.1) ----
    base_fl = floor_metrics(xyz_e3, y_floor)
    cand_fl = floor_metrics(v11_xyz, y_floor)
    rulers = {
        "ruler_1_points": {"before_e3": len(xyz_e3), "after_v11": len(v11_xyz),
                           "injected": int(len(inj_idx)),
                           "delta_pct": round(100.0*len(inj_idx)/len(xyz_e3), 2),
                           "vs_production_baseline": {"baseline": nP, "after_v11": len(v11_xyz),
                                                      "delta_pct": round(100.0*(len(v11_xyz)-nP)/nP, 2)}},
        "ruler_2_floor_thickness": {"y_floor": round(y_floor,4), "before": base_fl, "after": cand_fl},
        "ruler_3_coverage": {"before_cells_2cm": base_fl.get("cover_cells_2cm"),
                             "after_cells_2cm": cand_fl.get("cover_cells_2cm"),
                             "new_cells_from_injection": None},  # filled below
        "ruler_4_wallclock_host_proxy_s": wall,
    }
    cells_before = cover_cells_set(xyz_e3, y_floor)
    cells_after = cover_cells_set(v11_xyz, y_floor)
    rulers["ruler_3_coverage"]["new_cells_from_injection"] = len(cells_after - cells_before)

    # ---- ghost-layer recheck (before/after, per item; injection must add nothing) ----
    fh_before = floor_h_e3
    fh_after = np.concatenate([floor_h_e3, floor_h_R[inj_idx]])
    def band_cnt(fh): return int(((fh >= DBL_BAND[0]) & (fh < DBL_BAND[1])).sum())
    def below_cnt(fh): return int((fh < BELOW_FLOOR).sum())
    nE3 = len(xyz_e3)
    ghost = {
        "double_floor_band_density": {"band_floor_h_m": list(DBL_BAND),
            "before": band_cnt(fh_before), "after": band_cnt(fh_after),
            "added_by_injection": band_cnt(fh_after) - band_cnt(fh_before)},
        "below_floor_points": {"gate_m": BELOW_FLOOR,
            "before": below_cnt(fh_before), "after": below_cnt(fh_after),
            "added_by_injection": below_cnt(fh_after) - below_cnt(fh_before)},
        "trail_signature_points": {
            "before_e3_cloud": {k: int(det_before[k].sum()) for k in ("S_behind","S_below","S_streak","S_out","union")},
            "after_v11_cloud": {k: int(det_after[k].sum()) for k in ("S_behind","S_below","S_streak","S_out","union")},
            "after_flag_on_injected": int(det_after["union"][nE3:].sum()),
            "after_flag_on_e3_points": int(det_after["union"][:nE3].sum()),
            "e3_points_newly_flagged_by_injection_context": int((det_after["union"][:nE3] & ~det_before["union"]).sum()),
            "e3_points_unflagged_by_injection_context": int((det_before["union"] & ~det_after["union"][:nE3]).sum()),
            "note": "gate is count-level (union must not increase). Context shift detail: injected occupancy ADDS evidence - an e3 point newly flagged S_behind now provably looks through a (newly densified) surface; its own position/status is unchanged, it becomes a candidate for a FUTURE knife, not a new ghost. Unflagged count = injected density legitimately de-wisps sparse real geometry.",
        },
        "chair_roi": {"roi": roi,
            "before": chair_roi_metrics(xyz_e3, roi, y_floor),
            "after": chair_roi_metrics(v11_xyz, roi, y_floor)},
    }
    ghost_pass = (ghost["double_floor_band_density"]["added_by_injection"] <= 0
                  and ghost["below_floor_points"]["added_by_injection"] <= 0
                  and ghost["trail_signature_points"]["after_flag_on_injected"] == 0
                  and ghost["trail_signature_points"]["after_v11_cloud"]["union"]
                      <= ghost["trail_signature_points"]["before_e3_cloud"]["union"])
    if roi is not None:
        ghost_pass = ghost_pass and (ghost["chair_roi"]["after"]["n_roi_near_floor_5cm"]
                                     <= ghost["chair_roi"]["before"]["n_roi_near_floor_5cm"])
    ghost["pass"] = bool(ghost_pass)

    # ---- spatial distribution of injected points ----
    d_prod_inj = R_dprod[inj_idx]
    e3_tree = cKDTree(xyz_e3)
    cnt10_prod_inj = np.asarray(e3_tree.query_ball_point(inj_xyz, DENS_R, return_length=True, workers=-1))
    fh_inj = floor_h_R[inj_idx]
    layer = np.where(np.abs(fh_inj) <= FLOOR_SLAB, "floor",
             np.where(fh_inj <= 1.0, "object_low", "wall_high"))
    def hist(a, edges):
        h, _ = np.histogram(a, bins=edges)
        return {f"[{edges[i]},{edges[i+1]})": int(h[i]) for i in range(len(h))}
    hole = cnt10_prod_inj <= WISP_MAX_CNT
    dense = cnt10_prod_inj >= CORE_CNT
    spatial = {
        "dist_to_nearest_production_point_m": hist(d_prod_inj, [0.02, 0.05, 0.10, 0.25, 10.0]),
        "local_e3_density_cnt10": {"hole_cnt10_le10": int(hole.sum()),
                                   "mid": int((~hole & ~dense).sum()),
                                   "already_dense_cnt10_ge40": int(dense.sum()),
                                   "frac_already_dense": round(float(dense.mean()), 3) if len(inj_idx) else None,
                                   "frac_hole_or_mid": round(float((~dense).mean()), 3) if len(inj_idx) else None},
        "layer_counts": {l: int((layer == l).sum()) for l in ("floor","object_low","wall_high")},
        "layer_x_density": {l: {"hole": int((hole & (layer==l)).sum()),
                                 "mid": int((~hole & ~dense & (layer==l)).sum()),
                                 "dense": int((dense & (layer==l)).sum())}
                            for l in ("floor","object_low","wall_high")},
        "new_floor_cover_cells_2cm": len(cells_after - cells_before),
        "note": "layering by height above arbitrated floor plane: floor=|fh|<=0.06, object_low=fh<=1.0, wall_high=fh>1.0 (proxy layering, declared)",
    }

    # ---- renders ----
    t0 = time.perf_counter()
    fig, axes = plt.subplots(2, 2, figsize=(20, 20))
    for axrow, (a, b, la, lb_, inv) in zip(axes, [(0,2,"X","Z",False),(2,1,"Z","Y",True)]):
        for ax, (P, Cl, ttl) in zip(axrow, [(xyz_e3, rgb_e3, f"E3 candidate {len(xyz_e3)} (user-approved)"),
                                            (v11_xyz, v11_rgb, f"v1.1 = E3 + {len(inj_idx)} rescued")]):
            ax.scatter(P[:,a], P[:,b], s=0.25, c=Cl/255.0, linewidths=0)
            ax.scatter(camC_all[:,a], camC_all[:,b], s=14, c="magenta", marker="^")
            ax.set_aspect("equal"); ax.set_facecolor("#181818")
            ax.set_xlabel(la); ax.set_ylabel(lb_)
            if inv: ax.invert_yaxis()
            ax.set_title(f"{cap} {ttl} ({'topview' if not inv else 'elevation'}) - same gauge, no Sim3")
    plt.tight_layout()
    p_sbs = os.path.join(out, f"side_by_side_{cap}.png")
    plt.savefig(p_sbs, dpi=110); plt.close()

    fig, axes = plt.subplots(1, 2, figsize=(20, 10))
    for ax, (a, b, la, lb_, inv) in zip(axes, [(0,2,"X","Z",False),(2,1,"Z","Y",True)]):
        ax.scatter(xyz_e3[:,a], xyz_e3[:,b], s=0.2, c=rgb_e3/255.0, linewidths=0)
        ax.scatter(inj_xyz[:,a], inj_xyz[:,b], s=2.5, c="#00a0ff", linewidths=0)
        ax.scatter(camC_all[:,a], camC_all[:,b], s=16, c="magenta", marker="^")
        ax.set_aspect("equal"); ax.set_facecolor("#181818")
        ax.set_xlabel(la); ax.set_ylabel(lb_)
        if inv: ax.invert_yaxis()
        ax.set_title(f"{cap} injected {len(inj_idx)} pts (blue) over E3 true color ({'topview' if not inv else 'elevation'})")
    plt.tight_layout()
    p_ov = os.path.join(out, f"inject_overlay_{cap}.png")
    plt.savefig(p_ov, dpi=110); plt.close()

    fig, axes = plt.subplots(1, 3, figsize=(18, 4.5))
    axes[0].hist(d_prod_inj, bins=40, range=(0.02, 0.5), color="#2277cc")
    axes[0].set_title("injected: dist to nearest production pt (m)")
    axes[1].hist(cnt10_prod_inj, bins=40, range=(0, 120), color="#2277cc")
    axes[1].axvline(WISP_MAX_CNT, color="orange", ls="--", label="hole<=10")
    axes[1].axvline(CORE_CNT, color="red", ls="--", label="dense>=40")
    axes[1].legend(); axes[1].set_title("injected: local E3-cloud density cnt10")
    ls = [int((layer==l).sum()) for l in ("floor","object_low","wall_high")]
    axes[2].bar(["floor","object_low","wall_high"], ls, color=["#44aa77","#7766cc","#cc7744"])
    axes[2].set_title("injected: layer counts")
    plt.suptitle(f"{cap} injected point spatial distribution")
    plt.tight_layout()
    p_sp = os.path.join(out, f"spatial_dist_{cap}.png")
    plt.savefig(p_sp, dpi=110); plt.close()
    wall["renders_s"] = round(time.perf_counter()-t0, 1)

    # ---- provenance npz ----
    p_npz = os.path.join(out, f"rescue_provenance_{cap}.npz")
    np.savez_compressed(p_npz,
        pos=R_pos, f1=R_f1, f2=R_f2, xy1=R_xy1, xy2=R_xy2, maxres=R_res, theta=R_th,
        dist_prod=R_dprod, floor_h=floor_h_R, corridor_max_hits=corridor_max_hits,
        injected_mask=alive, g5_blocked=g5_blocked, g6_dropped=g6_dropped,
        inj_rgb=inj_rgb, inj_idx=inj_idx)

    stats = {
        "cap": cap,
        "inputs": {"db": DB, "meta": META, "baseline_ply": PLY, "baseline_ply_sha256": ply_sha,
                   "e3_candidate_ply": f"{E3D}/{cap}/e3_candidate_{cap}.ply", "e3_candidate_sha256": e3_sha,
                   "e3_arrays": f"{E3D}/{cap}/e3_arrays.npz",
                   "e2a_fingerprints": f"{TFD}/{cap}/fingerprints.npz",
                   "sha_checks": "S1 stats + E2-A fingerprints ply_sha256 == baseline sha (asserted); e3_candidate == prod[~cull] (asserted)"},
        "gauge": "production refined poses; injected refit points triangulated in the SAME frame (frozen poses/K); NO Sim3, no realignment",
        "rule": {
            "principle": "RS discipline: tie points passing THE unified ruler get published; injection side runs STRICTER gates than incumbent side",
            "G0": "S1 unified 2-view rule (verified pair + DLT refit + reproj<=3px + theta>=2deg), byte-identical constants",
            "G1": f"dedup: > {DEDUP_PROD_M} m from any production point",
            "G2": f"resurrection guard: >= {RESURRECT_GUARD_M} m from every E3-culled point (stricter, injected must not repopulate cleaned zones)",
            "G3": f"floor guard: floor_h >= {FLOOR_GUARD_M} m on arbitrated plane (stricter than stock E3 {BELOW_FLOOR}; constructively zero double-floor-band adds)",
            "G4": f"chair-ROI guard (cap50): no injected point in ROI within {CHAIR_NEARFLOOR_M} m of floor",
            "G5": f"corridor vote: BOTH observation corridors marched (E2-A constants) against E3-candidate solid voxels; either >= {VOTE_BLOCK_HITS} solid crossings => cull; no proxy votes (stricter than stock net>=0); too-short corridor = clear (declared)",
            "G7": "floor-thickening guard: floor-slab (|y-y_floor|<=0.06) injections kept ONLY as pure hole-fill (tight slab <=0.03 AND new 2cm cover cell AND thickness cell with <8 E3 slab pts) - protects the floor thickness ruler from 2-view depth-noise shell",
            "G6": "after-context E2-A four-signature scan on combined cloud; ANY flagged injected point dropped, iterated to fixed point (stricter than stock earn-existence)",
            "colorize": "certified recipe: bilinear at obs_xy-0.5 full-res (COLMAP convention), OOB skipped, representative sample = lower-median-luma real sample (2 obs => darker), round+clamp; missing photo => remaining obs; none => NN production color (declared)",
        },
        "funnel": funnel,
        "colorize": {"n_frames_missing_jpg": n_missing_jpg, "n_oob_samples": int(n_oob),
                     "n_nn_fallback_points": int(n_nn_fallback),
                     "n_from_two_obs": int(sum(1 for r in range(len(inj_idx)) if len(samples.get(r, [])) == 2)),
                     "n_from_one_obs": int(sum(1 for r in range(len(inj_idx)) if len(samples.get(r, [])) == 1))},
        "check_1_four_rulers": rulers,
        "check_2_ghost_recheck": ghost,
        "check_3_spatial_distribution": spatial,
        "quality_of_injected": {
            "theta_deg": {f"p{p}": round(float(np.percentile(R_th[inj_idx], p)), 3) for p in (10,50,90)} if len(inj_idx) else {},
            "refit_maxres_px": {f"p{p}": round(float(np.percentile(R_res[inj_idx], p)), 3) for p in (10,50,90)} if len(inj_idx) else {},
        },
        "honesty": [
            "evidence rebuilt from sfm_live.db in observation space; NOT byte-exact production finalize replication",
            "injected positions are host DLT refit results with frozen refined poses (structure-only); production would re-triangulate + BA these tracks - positions may differ at mm scale",
            f"colorize: {n_missing_jpg} registered frames have no photo on disk ({cap}); points with zero recoverable samples fall back to nearest-production-point color ({n_nn_fallback} pts, declared)",
            "representative color with 2 samples = the darker sample (production lower-median rule), not an average",
            "G3/G4/G5-unanimity/G6-zero-flag/G7 are injection-side strictness choices (stricter than user-approved E3 stock rule), chosen so the ghost recheck passes constructively; the cost is conservatism: some real rescue points near cleaned zones/floor band/covered floor cells are left out (counted in funnel)",
            "first-run lesson (disclosed): without G7 the cap50 floor med-cell thickness regressed 0.04844->0.05172 m (+3.3mm) - floor injections into already-covered cells thicken instead of fill; G7 was added in response and the run repeated (this is a rule change made BEFORE any user approval of E6 products, not after)",
            "wallclock = host python proxy, not device numbers; nothing here ships without sign-off",
        ],
    }
    outputs = {}
    for p in [p_v11, p_diff, p_sbs, p_ov, p_sp, p_npz]:
        outputs[os.path.basename(p)] = sha256(p)
    stats["outputs_sha256"] = outputs
    json.dump(stats, open(os.path.join(out, "stats.json"), "w"), indent=2)
    log(json.dumps({"funnel": funnel, "ghost_pass": ghost["pass"]}, indent=1))
    return stats

if __name__ == "__main__":
    caps = sys.argv[1:] or list(CAPS)
    all_path = os.path.join(OUT_BASE, "stats_all.json")
    allstats = json.load(open(all_path)) if os.path.exists(all_path) else {}
    for cap in caps:
        allstats[cap] = run_cap(cap, CAPS[cap])
    json.dump(allstats, open(all_path, "w"), indent=2)
    log("E6 DONE")
