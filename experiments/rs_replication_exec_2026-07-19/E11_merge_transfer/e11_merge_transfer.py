#!/usr/bin/env python3.11
"""
E11 merge-and-transfer prototype (SYNTHESIS v2 spec P0+S1-S6, ORB-SLAM2 Fuse/Replace
SEMANTICS self-implemented -- zero GPLv3 code copied).

Core semantics (differs from E8 all-or-nothing merge):
  * same-site competing tracks (evidence edges: shared verified-track roots A +
    verified-pair bridges B, E8-identical construction incl. G1-excluded <2cm pairs);
  * support ratio decides WINNER ONLY, never life/death (S4);
  * loser is NOT deleted: each loser observation individually passes the gate chain
    (positive depth -> reproj <= 4px at winner position, chi2-style, our certified
    3-4px caliber -> viewing angle < 60 deg vs winner mean view dir, S3/S5);
    passing observations TRANSFER to the winner (dedup: one obs per frame, COLMAP
    track semantics); winner re-triangulated by multiview DLT over merged obs with
    E8 dive guards (all-obs 4px test + member bbox +-1cm envelope, else keep pos);
  * loser keeps failing observations; if remaining < 2 it dies NATURALLY (cannot be
    sustained as a 3D point) -- the only way a point leaves the cloud;
  * FROZEN production poses everywhere = zero BA warp by construction (E9-C 197mm
    lesson bypassed);
  * small-step N rounds: each round processes only the top-confidence ~15% of open
    competitions (confidence = support ratio, ties by proximity), winner positions
    re-triangulated between rounds, iterate to convergence (Metashape/PR#2145 mode).

Hard quality gates (constructive):
  * coverage zero loss: a death that would empty a 2cm cover cell not re-covered by
    the winner is VETOED atomically (loser lives, no transfer); final assert
    cover_after >= cover_before;
  * winner repositioning that would empty its sole cover cell is skipped (pos kept);
  * observation conservation fully accounted: before = kept + transferred + dropped
    (dropped only with a dying loser, counted).

Baseline = v1.1 candidate (user-approved E6 output), byte-identity asserted.
Reads ONLY frozen capture data + prior experiment products; writes ONLY into
E11_merge_transfer/. python3.11.
"""
import sqlite3, numpy as np, json, os, sys, time, hashlib, random
from collections import defaultdict
from scipy.spatial import cKDTree

MAX_IMAGE_ID = 2147483647
# ---- S1 constants (byte-identical to S1/E8) ----
REPROJ_GATE_PX = 3.0
THETA_GATE_DEG = 2.0
FLOOR_SLAB = 0.06
COVER_SLAB = 0.03
CELL_THICK = 0.05
CELL_COVER = 0.02
# ---- ghost rulers (E8/E9 byte-identical) ----
DBL_BAND = (-0.06, -0.015)
SHELL_ABOVE = (0.015, 0.06)
GHOST_2045 = (-0.045, -0.02)
BELOW_FLOOR = -0.10
CHAIR_NEARFLOOR_M = 0.05
WALL_MIN_FH = 0.10
WALL_FIT_MIN_FH = 0.30
WALL_SLAB = 0.06
# ---- E11 transfer constants ----
GATE_PX = 4.0            # our caliber 3-4px (COLMAP merge reproj gate; chi2 sigma=1 -> 16)
GATE_PX_SENS = (2.45, 3.0)  # sensitivity counters only (2.45px ~= chi2 5.99 @ sigma=1)
VIEW_COS_MIN = 0.5       # < 60 deg vs winner mean viewing direction (anti false-fuse, S3)
COMP_MAX_DIST_M = 0.05   # auxiliary distance VETO only (E8 DLT-dive lesson; never creates)
DLT_ENVELOPE_M = 0.01    # winner retriangulation envelope (E8 lesson)
ROOT_FANOUT_CAP = 20
ROUND_FRAC = 0.15        # small-step: top-confidence share per round
ROUND_MIN = 500
MAX_ROUNDS = 20
AUDIT_N = 36
AUDIT_SEED = 20260719

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
S1D = f"{EXP}/S1_twoview_lifecycle"
E3D = f"{EXP}/E3_birth_discipline"
E6D = f"{EXP}/E6_rescue_inject"
E8D = f"{EXP}/E8_shell_collapse"
E9D = f"{EXP}/E9_birth_alias"
TFD = f"{EXP}/TRAILS_forensics"
OUT_BASE = f"{EXP}/E11_merge_transfer"
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

# ---------------- rulers (S1/E8/E9 byte-identical constants) ----------------
def detect_floor_y(xyz):
    y = xyz[:,1]
    lo, hi = np.percentile(y, [0.5, 99.5])
    bins = np.arange(lo, hi + 0.005, 0.005)
    hcount, edges = np.histogram(y, bins=bins)
    peak = np.argmax(hcount)
    y0 = 0.5*(edges[peak]+edges[peak+1])
    sel = np.abs(y - y0) <= 0.015
    return float(np.median(y[sel]))

def cell_spreads(key, vals, min_pts=8):
    order = np.argsort(key)
    k, v = key[order], vals[order]
    bounds = np.flatnonzero(np.diff(k)) + 1
    return [float(np.percentile(g,90)-np.percentile(g,10)) for g in np.split(v, bounds) if len(g) >= min_pts]

def floor_metrics_y(xyz, y_floor):
    """E8 byte-identical certified ruler (y-based slab/cover). Used for the four
    rulers + hard gate + E6 anchor asserts, consistent with the y-based
    constructive coverage guard."""
    y = xyz[:,1]
    slab = np.abs(y - y_floor) <= FLOOR_SLAB
    P = xyz[slab]
    out = {"n_floor_slab": int(slab.sum())}
    if len(P) < 100:
        out.update({"thickness_med_cell_p90p10_m": None, "thickness_global_std_m": None, "cover_cells_2cm": 0})
        return out
    key = np.floor(P[:,0]/CELL_THICK).astype(np.int64)*1000003 + np.floor(P[:,2]/CELL_THICK).astype(np.int64)
    sp = cell_spreads(key, P[:,1])
    out["thickness_med_cell_p90p10_m"] = float(np.median(sp)) if sp else None
    out["thickness_p90_cell_m"] = float(np.percentile(sp,90)) if sp else None
    out["n_thickness_cells"] = len(sp)
    out["thickness_global_std_m"] = float(np.std(P[:,1]))
    tight = np.abs(P[:,1] - y_floor) <= COVER_SLAB
    Q = P[tight]
    cells = set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64), np.floor(Q[:,2]/CELL_COVER).astype(np.int64)))
    out["cover_cells_2cm"] = len(cells)
    out["cover_area_m2"] = round(len(cells) * CELL_COVER * CELL_COVER, 4)
    return out

def floor_metrics_fh(xyz, fh):
    """E9-C v2 caliber: metrics on plane-height fh (already re-anchored by caller)."""
    slab = np.abs(fh) <= FLOOR_SLAB
    P, f = xyz[slab], fh[slab]
    out = {"n_floor_slab": int(slab.sum())}
    if len(P) < 100:
        out.update(thickness_med_cell_p90p10_m=None, thickness_p90_cell_m=None, cover_cells_2cm=0)
        return out
    key = np.floor(P[:,0]/CELL_THICK).astype(np.int64)*1000003 + np.floor(P[:,2]/CELL_THICK).astype(np.int64)
    sp = cell_spreads(key, f)
    out["thickness_med_cell_p90p10_m"] = float(np.median(sp)) if sp else None
    out["thickness_p90_cell_m"] = float(np.percentile(sp,90)) if sp else None
    out["n_thickness_cells"] = len(sp)
    Q = P[np.abs(f) <= COVER_SLAB]
    out["cover_cells_2cm"] = len(set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64),
                                         np.floor(Q[:,2]/CELL_COVER).astype(np.int64))))
    out["cover_area_m2"] = round(out["cover_cells_2cm"]*CELL_COVER*CELL_COVER, 4)
    return out

def anchor_floor(fh):
    """E9-C v2 shift-only re-anchor (byte-identical logic)."""
    hist, edges = np.histogram(fh[np.abs(fh) <= 0.12], bins=np.arange(-0.12, 0.1205, 0.005))
    k = int(np.argmax(hist))
    thr = 0.35 * hist[k]
    lo = k
    while lo > 0 and hist[lo-1] >= thr: lo -= 1
    hi = k
    while hi < len(hist)-1 and hist[hi+1] >= thr: hi += 1
    centers = 0.5*(edges[lo:hi+1] + edges[lo+1:hi+2])
    w = hist[lo:hi+1].astype(float)
    return float((centers*w).sum()/w.sum())

def fit_dominant_wall(xyz, floor_h, pn):
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
    sd = xyz @ d - off
    m = (np.abs(sd) <= WALL_SLAB) & (floor_h > WALL_MIN_FH)
    P, s, fh = xyz[m], sd[m], floor_h[m]
    out = {"n_wall_slab": int(m.sum())}
    if len(P) < 100:
        out.update(thickness_med_cell_p90p10_m=None, thickness_p90_cell_m=None)
        return out
    w = np.cross(pn, d); w /= np.linalg.norm(w)
    key = np.floor((P @ w)/CELL_THICK).astype(np.int64)*1000003 + np.floor(fh/CELL_THICK).astype(np.int64)
    sp = cell_spreads(key, s)
    out["thickness_med_cell_p90p10_m"] = float(np.median(sp)) if sp else None
    out["thickness_p90_cell_m"] = float(np.percentile(sp,90)) if sp else None
    out["n_thickness_cells"] = len(sp)
    return out

def chair_roi_metrics(xyz, roi, y_floor):
    if roi is None: return None
    m = (xyz[:,0]>=roi["X"][0])&(xyz[:,0]<=roi["X"][1])&(xyz[:,2]>=roi["Z"][0])&(xyz[:,2]<=roi["Z"][1])
    P = xyz[m]
    if len(P)==0: return {"n_roi": 0}
    y = P[:,1]
    near_floor = np.abs(y - y_floor) <= CHAIR_NEARFLOOR_M
    return {"n_roi": int(len(P)), "n_roi_near_floor_5cm": int(near_floor.sum())}

# ---------------- renders (E8-identical style) ----------------
def xsec_panel(u_arr, fd_mm, colors, W=1500, H=520, umin=None, umax=None, band=True):
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
    order = np.argsort(-xyz[:, 1])
    for i in order:
        if ok[i]: c[y[i], x[i]] = rgb[i]
    return c

def annotate(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((28, 6), text, fill=(235,235,235))
    return np.asarray(im)

# ---------------- main ----------------
def run_cap(cap, cfg):
    d = cfg["dir"]
    out = os.path.join(OUT_BASE, cap); os.makedirs(out, exist_ok=True)
    DB, META, PLY = f"{d}/sfm_live.db", f"{d}/sfm_sparse_meta.json", f"{d}/sfm_sparse.ply"
    log(f"=== {cap} ===")
    wall = {}

    # ---- load db (S1/E8-identical) ----
    t0 = time.perf_counter()
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); c = db.cursor()
    img_ids = sorted(i for (i,) in c.execute("SELECT image_id FROM images"))
    kp_xy, kp_count = {}, {}
    for iid, r, cols_, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
        arr = np.frombuffer(data, dtype=np.float32).reshape(r, cols_)
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
    for pair_id, r, cols_, data in c.execute("SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0"):
        iid1, iid2 = pair_id // MAX_IMAGE_ID, pair_id % MAX_IMAGE_ID
        if iid1 not in offset or iid2 not in offset: continue
        m = np.frombuffer(data, dtype=np.uint32).reshape(r, cols_)
        n1, n2 = kp_count[iid1], kp_count[iid2]
        o1, o2 = offset[iid1], offset[iid2]
        for f1, f2 in m:
            if f1 >= n1 or f2 >= n2: continue
            ra, rb = find(o1+int(f1)), find(o2+int(f2))
            if ra != rb: parent[rb] = ra
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

    # ---- upstream product SHA consistency (E8-identical) ----
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

    # ---- re-extract rescue pairs WITH node ids; assert identity vs E6 (E8-identical) ----
    t0 = time.perf_counter()
    pair_members = defaultdict(list)
    for node in np.flatnonzero(counts[np.searchsorted(uniq, roots)] == 2):
        pair_members[int(roots[node])].append(int(node))
    off_list = np.array([offset[i] for i in img_ids] + [N], dtype=np.int64)
    iid_list = np.array(img_ids, dtype=np.int64)
    Rq_pos, Rq_f1, Rq_f2, Rq_n1, Rq_n2 = [], [], [], [], []
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
        Rq_n1.append(nds[0]); Rq_n2.append(nds[1])
    Rq_pos = np.array(Rq_pos)
    assert len(Rq_pos) == nPairs, f"pair re-extraction count {len(Rq_pos)} != {nPairs}"
    assert np.allclose(Rq_pos, P_pos, atol=1e-9)
    assert np.array_equal(np.array(Rq_f1), P_f1) and np.array_equal(np.array(Rq_f2), P_f2)
    P_n1 = np.array(Rq_n1); P_n2 = np.array(Rq_n2)
    wall["pair_reextract_s"] = round(time.perf_counter()-t0, 1)

    # ---- v1.1 BEFORE cloud (identity asserted, E8-identical) ----
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

    # ---- observation recovery (S1/E8-identical) + pair bridge reverse query ----
    t0 = time.perf_counter()
    obs = [[] for _ in range(nV)]
    for k, pi in enumerate(inj_idx):
        gi = nE3 + k
        obs[gi].append((int(P_f1[pi]), int(P_n1[pi]), float(P_xy1[pi,0]), float(P_xy1[pi,1])))
        obs[gi].append((int(P_f2[pi]), int(P_n2[pi]), float(P_xy2[pi,0]), float(P_xy2[pi,1])))
    pairs_by_f1 = defaultdict(list); pairs_by_f2 = defaultdict(list)
    for i in range(nPairs):
        pairs_by_f1[int(P_f1[i])].append(i)
        pairs_by_f2[int(P_f2[i])].append(i)
    bridgeP = np.full(nPairs, -1, np.int64)
    bridgeQ = np.full(nPairs, -1, np.int64)
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
        ptree_uv = cKDTree(uv[q_idx])
        for plist, xyarr, tgt in ((pairs_by_f1.get(fid, []), P_xy1, bridgeP),
                                  (pairs_by_f2.get(fid, []), P_xy2, bridgeQ)):
            if not plist: continue
            pl = np.array(plist)
            dd, kk = ptree_uv.query(xyarr[pl], k=1, distance_upper_bound=REPROJ_GATE_PX, workers=-1)
            hit = np.isfinite(dd)
            tgt[pl[hit]] = q_idx[kk[hit]]
    wall["obs_recovery_s"] = round(time.perf_counter()-t0, 1)
    n_obs0 = np.array([len(o) for o in obs])
    log(f"obs recovery: stock ge2={int((n_obs0[:nE3]>=2).sum())}/{nE3} 1={int((n_obs0[:nE3]==1).sum())} "
        f"0={int((n_obs0[:nE3]==0).sum())} ({wall['obs_recovery_s']}s)")

    # ---- evidence edges (E8-identical construction) ----
    t0 = time.perf_counter()
    root_pts = defaultdict(set)
    for gi in range(nV):
        for (fid, node, _, _) in obs[gi]:
            root_pts[int(roots[node])].add(gi)
    edgesA = set()
    n_root_skipped = 0
    for rt, s in root_pts.items():
        k = len(s)
        if k < 2: continue
        if k > ROOT_FANOUT_CAP:
            n_root_skipped += 1; continue
        s = sorted(s)
        for i in range(len(s)):
            for j in range(i+1, len(s)):
                edgesA.add((s[i], s[j]))
    edgesB = {}
    for i in range(nPairs):
        a, b = int(bridgeP[i]), int(bridgeQ[i])
        if a < 0 or b < 0 or a == b: continue
        e = (min(a,b), max(a,b))
        if e not in edgesB: edgesB[e] = i
    edges_all = sorted(edgesA | set(edgesB.keys()))
    wall["edges_s"] = round(time.perf_counter()-t0, 1)
    log(f"edges: A={len(edgesA)} B={len(edgesB)} union={len(edges_all)} rootskip={n_root_skipped}")

    # ================= E11 merge-and-transfer machinery =================
    t0 = time.perf_counter()
    y_floor = detect_floor_y(xyz_prod)
    alive = np.ones(nV, bool)
    heir = np.full(nV, -1, np.int64)          # dead loser -> winner it transferred into
    cur_pos = pts.copy()
    own_obs = [None]*nV                        # lazy dict (fid,node)->(x,y); own = not-yet-transferred
    got_obs = [None]*nV                        # winner's absorbed obs dict
    def own(i):
        if own_obs[i] is None:
            own_obs[i] = {(fid,node):(x,y) for (fid,node,x,y) in obs[i]}
        return own_obs[i]
    def full_obs(i):
        o = dict(own(i))
        if got_obs[i]: o.update(got_obs[i])
        return o
    n_own = n_obs0.copy()                      # current own obs count
    n_got = np.zeros(nV, np.int64)             # transferred-in count
    self_reproj = np.full(nV, -1.0)            # lazy mean self reproj (tie-break)
    def mean_reproj(i):
        if self_reproj[i] >= 0: return self_reproj[i]
        o = full_obs(i)
        if not o:
            self_reproj[i] = 1e9; return 1e9
        errs = []
        X = cur_pos[i]
        for (fid,_), (x,y) in o.items():
            Xc = pose_R[fid] @ X + pose_t[fid]
            if Xc[2] <= 0: errs.append(1e9); continue
            errs.append(np.hypot(f_*Xc[0]/Xc[2]+cx_-x, f_*Xc[1]/Xc[2]+cy_-y))
        self_reproj[i] = float(np.mean(errs))
        return self_reproj[i]
    # cover-cell bookkeeping (constructive zero-loss guard)
    def cov_cell(p):
        if abs(p[1] - y_floor) <= COVER_SLAB:
            return (int(np.floor(p[0]/CELL_COVER)), int(np.floor(p[2]/CELL_COVER)))
        return None
    cell_cnt = defaultdict(int)
    for gi in range(nV):
        cc = cov_cell(pts[gi])
        if cc is not None: cell_cnt[cc] += 1
    frame_dirs = {fid: None for fid in pose_R}
    def view_dir(fid, X):
        v = X - pose_C[fid]; n = np.linalg.norm(v)
        return v/n if n > 0 else v
    def mean_view_dir(i):
        o = full_obs(i)
        if not o: return None
        vs = np.array([view_dir(fid, cur_pos[i]) for (fid,_) in o.keys()])
        m = vs.mean(0); n = np.linalg.norm(m)
        return m/n if n > 0 else None
    def reproj_err(X, fid, x, y):
        Xc = pose_R[fid] @ X + pose_t[fid]
        if Xc[2] <= 0: return None
        return float(np.hypot(f_*Xc[0]/Xc[2]+cx_-x, f_*Xc[1]/Xc[2]+cy_-y))
    def dlt(obs_items):
        A = []
        for (fid, _), (x, y) in obs_items:
            Pm = K @ np.hstack([pose_R[fid], pose_t[fid].reshape(3,1)])
            A.append(x*Pm[2] - Pm[0]); A.append(y*Pm[2] - Pm[1])
        _,_,Vt = np.linalg.svd(np.array(A))
        Xh = Vt[-1]
        if abs(Xh[3]) < 1e-12: return None
        return Xh[:3]/Xh[3]

    S = defaultdict(int)                       # funnel counters
    transfer_errs = []                          # accepted transfer reproj errors (px)
    cross_layer_obs = [0, 0]                    # [attempted, passed] on cross-layer competitions
    comp_log = []                               # provenance rows
    rounds_hist = []
    edge_state = {}                             # edge -> 'open'|'done'
    def resolve(i):
        while heir[i] >= 0: i = heir[i]
        return i

    fh_cur = lambda i: cur_pos[i] @ pn + pd

    def try_competition(e, is_final_pass):
        a0, b0 = e
        a, b = resolve(a0), resolve(b0)
        if a == b: return "self"
        if not (alive[a] and alive[b]): return "self"
        S["attempted"] += 1
        dist = np.linalg.norm(cur_pos[a] - cur_pos[b])
        if dist > COMP_MAX_DIST_M:
            S["skip_dist_gt5cm"] += 1; return "dist"
        na, nb = n_own[a] + n_got[a], n_own[b] + n_got[b]
        if na == nb:
            w, l = (a, b) if mean_reproj(a) <= mean_reproj(b) else (b, a)
            S["tie_broken_by_reproj"] += 1
        else:
            w, l = (a, b) if na > nb else (b, a)
        lw = n_own[w] + n_got[w]; ll = n_own[l] + n_got[l]
        cross = abs(fh_cur(w) - fh_cur(l)) > 0.015
        # gate loser own observations individually at winner position
        Vw = mean_view_dir(w)
        wobs = full_obs(w)
        wframes = {fid for (fid,_) in wobs.keys()}
        Xw = cur_pos[w]
        passing, fail_keep = [], []
        cand_items = list(own(l).items())
        # bridge pair's own two observations also join the gate queue (verified
        # correspondence at the two pixel sites; S2 closure evidence)
        if e in edgesB:
            pi = edgesB[e]
            for fid, node, x, y in ((int(P_f1[pi]), int(P_n1[pi]), float(P_xy1[pi,0]), float(P_xy1[pi,1])),
                                    (int(P_f2[pi]), int(P_n2[pi]), float(P_xy2[pi,0]), float(P_xy2[pi,1]))):
                key = (fid, node)
                if key not in own(l) and key not in wobs:
                    cand_items.append((key, (x, y)))
        n_dup = 0
        new_frames = set()
        for key, (x, y) in cand_items:
            fid = key[0]
            is_own_l = key in own(l)
            if key in wobs or fid in wframes or fid in new_frames:
                n_dup += 1
                if is_own_l: fail_keep.append(key)     # frame already served: obs stays with loser
                continue
            err = reproj_err(Xw, fid, x, y)
            if cross: cross_layer_obs[0] += 1
            if err is None or err > GATE_PX:
                if is_own_l: fail_keep.append(key)
                S["obs_fail_reproj"] += 1
                continue
            if Vw is not None:
                if np.dot(view_dir(fid, Xw), Vw) < VIEW_COS_MIN:
                    if is_own_l: fail_keep.append(key)
                    S["obs_fail_viewangle"] += 1
                    continue
            passing.append((key, (x, y), err, is_own_l))
            new_frames.add(fid)
            if cross: cross_layer_obs[1] += 1
        if not passing:
            S["no_transfer"] += 1
            return "done" if is_final_pass else "open"
        n_l_transfer = sum(1 for p in passing if p[3])
        remaining = n_own[l] - n_l_transfer
        # death must be TRIGGERED by the loser's own support moving to the winner;
        # a point whose observations we could not recover (0-own-obs, bridge-only
        # evidence) is never killed -- unrecoverable != nonexistent (E8 honesty).
        will_die = (remaining < 2) and (n_l_transfer >= 1)
        # constructive coverage guard (atomic veto of the whole competition)
        if will_die:
            ccl = cov_cell(cur_pos[l]); ccw = cov_cell(Xw)
            if ccl is not None and cell_cnt[ccl] - 1 <= 0 and ccw != ccl:
                S["cov_guard_veto"] += 1
                return "done" if is_final_pass else "open"
        # commit transfers
        gd = got_obs[w] or {}
        for key, xy, err, is_own_l in passing:
            gd[key] = xy
            transfer_errs.append(err)
            if is_own_l:
                own(l).pop(key, None)
        got_obs[w] = gd
        n_got[w] += len(passing)
        n_own[l] = len(own(l))
        self_reproj[w] = -1.0
        # winner retriangulation (frozen poses; E8 dive guards)
        items = list(full_obs(w).items())
        moved = False
        if len(items) >= 2:
            Xn = dlt(items)
            if Xn is not None:
                lo_env = np.minimum(pts[w], cur_pos[l]) - DLT_ENVELOPE_M
                hi_env = np.maximum(pts[w], cur_pos[l]) + DLT_ENVELOPE_M
                ok = not (np.any(Xn < lo_env) or np.any(Xn > hi_env))
                if ok:
                    for (fid,_), (x, y) in items:
                        err = reproj_err(Xn, fid, x, y)
                        if err is None or err > GATE_PX: ok = False; break
                if ok:
                    ccw_old, ccw_new = cov_cell(cur_pos[w]), cov_cell(Xn)
                    if ccw_old is not None and ccw_old != ccw_new and cell_cnt[ccw_old] - 1 <= 0:
                        S["reposition_cov_skip"] += 1
                    else:
                        if ccw_old is not None: cell_cnt[ccw_old] -= 1
                        if ccw_new is not None: cell_cnt[ccw_new] += 1
                        cur_pos[w] = Xn; moved = True
                        S["winner_retriangulated"] += 1
                else:
                    S["retri_guard_keep_pos"] += 1
        # loser fate
        died = False
        if will_die:
            ccl = cov_cell(cur_pos[l])
            if ccl is not None: cell_cnt[ccl] -= 1
            alive[l] = False
            heir[l] = w
            died = True
            S["loser_died_natural"] += 1
            S["obs_dropped_with_death"] += len(own(l))
        else:
            S["loser_survived"] += 1
        S["obs_transferred"] += len(passing)
        comp_log.append((w, l, lw, ll, len(passing), n_l_transfer, n_dup,
                         int(died), int(cross), round(dist,5), int(moved)))
        return "acted"

    # ---- small-step rounds ----
    pool = list(edges_all)
    rnd = 0
    while rnd < MAX_ROUNDS:
        rnd += 1
        # confidence = support ratio (winner/loser), ties by proximity
        scored = []
        for e in pool:
            a, b = resolve(e[0]), resolve(e[1])
            if a == b or not (alive[a] and alive[b]): continue
            na, nb = n_own[a]+n_got[a], n_own[b]+n_got[b]
            hiN, loN = max(na, nb), min(na, nb)
            conf = (hiN + 1.0) / (loN + 1.0)
            d_ab = np.linalg.norm(cur_pos[a]-cur_pos[b])
            scored.append((conf, -d_ab, e))
        if not scored: break
        scored.sort(key=lambda t: (-t[0], -t[1]))
        take = max(ROUND_MIN, int(ROUND_FRAC*len(scored)))
        batch = [t[2] for t in scored[:take]]
        rest = [t[2] for t in scored[take:]]
        acted = died_before = S["loser_died_natural"]
        n_act = 0
        keep = []
        for e in batch:
            r = try_competition(e, is_final_pass=False)
            if r == "acted": n_act += 1
            elif r in ("open", "dist"): keep.append(e)
        pool = keep + rest
        died_this = S["loser_died_natural"] - died_before
        rounds_hist.append({"round": rnd, "candidates": len(scored), "processed": len(batch),
                            "acted": n_act, "died": died_this,
                            "obs_transferred_cum": int(S["obs_transferred"]),
                            "deaths_cum": int(S["loser_died_natural"])})
        log(f" round {rnd}: cands={len(scored)} proc={len(batch)} acted={n_act} died={died_this} "
            f"(cum transfer={S['obs_transferred']} deaths={S['loser_died_natural']})")
        if n_act == 0:
            # full convergence pass over the remaining pool
            n_act2 = 0
            keep = []
            for e in pool:
                r = try_competition(e, is_final_pass=True)
                if r == "acted": n_act2 += 1
                elif r in ("open", "dist"): keep.append(e)
            pool = keep
            rounds_hist.append({"round": f"{rnd}-final", "processed": len(pool), "acted": n_act2,
                                "deaths_cum": int(S["loser_died_natural"])})
            log(f" final pass: acted={n_act2}")
            if n_act2 == 0: break
    wall["transfer_s"] = round(time.perf_counter()-t0, 1)

    # ---- observation conservation accounting ----
    total_before = int(n_obs0.sum())
    kept_alive = int(sum(len(own(i)) for i in range(nV) if alive[i]))
    got_alive = int(sum(len(got_obs[i] or {}) for i in range(nV) if alive[i]))
    dropped = int(sum(len(own(i)) for i in range(nV) if not alive[i]))
    bridge_extra = got_alive + kept_alive + dropped - total_before  # bridge-pair obs added from outside point obs
    log(f"obs conservation: before={total_before} kept={kept_alive} transferred_in_alive={got_alive} "
        f"dropped_with_death={dropped} bridge_extra_injected={bridge_extra}")

    # ---- assemble AFTER cloud ----
    alive_idx = np.flatnonzero(alive)
    dead_idx = np.flatnonzero(~alive)
    # strengthened winner colors: obs-weighted mix with fully-absorbed dead losers
    after_rgb_full = cols.astype(float).copy()
    absorbed = defaultdict(list)
    for li in dead_idx:
        absorbed[resolve(li)].append(li)
    strengthened = np.zeros(nV, bool)
    for wi, ls in absorbed.items():
        if not alive[wi]: continue
        strengthened[wi] = True
        wgt = [max(n_obs0[wi], 1)]
        cc = [cols[wi].astype(float)]
        for li in ls:
            wgt.append(max(n_obs0[li], 1)); cc.append(cols[li].astype(float))
        wgt = np.array(wgt, float)[:, None]
        after_rgb_full[wi] = (np.array(cc)*wgt).sum(0)/wgt.sum()
    after_pts = cur_pos[alive_idx]
    after_rgb = np.clip(np.round(after_rgb_full[alive_idx]), 0, 255).astype(np.uint8)
    fh_after = after_pts @ pn + pd
    n_dead = len(dead_idx)
    n_strength = int(strengthened.sum())
    disp_winner = np.linalg.norm(cur_pos - pts, axis=1)
    log(f"after cloud: {len(after_pts)} pts (dead {n_dead}, strengthened winners {n_strength})")

    # ---- metrics: v1.1 raw caliber (anchor continuity) + E9-C v2 shift-only re-anchor ----
    t0 = time.perf_counter()
    band_before = int(((fh_before >= DBL_BAND[0]) & (fh_before < DBL_BAND[1])).sum())
    band_after = int(((fh_after >= DBL_BAND[0]) & (fh_after < DBL_BAND[1])).sum())
    assert band_before == cfg["anchor_band_before"], f"band anchor mismatch {band_before}"
    below_before = int((fh_before < BELOW_FLOOR).sum())
    below_after = int((fh_after < BELOW_FLOOR).sum())
    fl_before = floor_metrics_y(pts, y_floor)
    fl_after = floor_metrics_y(after_pts, y_floor)
    assert fl_after["cover_cells_2cm"] >= fl_before["cover_cells_2cm"], "HARD GATE: coverage dropped!"
    # E9-C v2: shift-only re-anchor per cloud (gauge frozen -> shifts should agree)
    sh_b, sh_a = anchor_floor(fh_before), anchor_floor(fh_after)
    fhb2, fha2 = fh_before - sh_b, fh_after - sh_a
    e9c = {}
    for tag, fh2, xyz2 in (("before", fhb2, pts), ("after", fha2, after_pts)):
        e9c[tag] = {
            "gauge_shift_mm": round((sh_b if tag=="before" else sh_a)*1000, 1),
            "band_below": int(((fh2 >= DBL_BAND[0]) & (fh2 < DBL_BAND[1])).sum()),
            "shell_above": int(((fh2 > SHELL_ABOVE[0]) & (fh2 <= SHELL_ABOVE[1])).sum()),
            "ghost_2045": int(((fh2 >= GHOST_2045[0]) & (fh2 < GHOST_2045[1])).sum()),
            "below_floor": int((fh2 < BELOW_FLOOR).sum()),
            "floor": floor_metrics_fh(xyz2, fh2),
        }
    dwall, woff = fit_dominant_wall(pts, fh_before, pn)
    wl_before = wall_metrics(pts, fh_before, dwall, woff, pn)
    wl_after = wall_metrics(after_pts, fh_after, dwall, woff, pn)
    roi_before = chair_roi_metrics(pts, cfg["chair_roi"], y_floor)
    roi_after = chair_roi_metrics(after_pts, cfg["chair_roi"], y_floor)
    # E6 anchors (before == E6 after)
    e6s = json.load(open(f"{E6D}/{cap}/stats.json"))
    a2 = e6s["check_1_four_rulers"]["ruler_2_floor_thickness"]["after"]
    assert abs(fl_before["thickness_med_cell_p90p10_m"] - a2["thickness_med_cell_p90p10_m"]) < 1e-6
    assert fl_before["cover_cells_2cm"] == a2["cover_cells_2cm"]
    # G1 true-surface retention: obs on true-floor points (|fh|<=0.015) must not drop
    true_floor = np.abs(fh_before) <= 0.015
    tf_obs_before = int(n_obs0[true_floor].sum())
    tf_alive = true_floor & alive
    tf_obs_after = int(sum(len(full_obs(i)) for i in np.flatnonzero(tf_alive)))
    tf_dead = int((true_floor & ~alive).sum())
    # component accounting for dying true-floor losers: transferred obs are RETAINED
    # (they live on the winner); only dropped obs are genuine losses; winner fh tells
    # whether the site stays on the true surface
    tf_drop = tf_xfer = 0
    tf_winner_in15 = tf_winner_total = 0
    for li in np.flatnonzero(true_floor & ~alive):
        tf_drop += len(own(li))
        tf_xfer += int(n_obs0[li] - len(own(li)))
        wi = resolve(li)
        tf_winner_total += 1
        if abs(cur_pos[wi] @ pn + pd) <= 0.015: tf_winner_in15 += 1
    # dead-point fh histogram (who dies?)
    dead_fh = fh_before[dead_idx]
    dead_hist = {
        "band_below_-60..-15mm": int(((dead_fh >= DBL_BAND[0]) & (dead_fh < DBL_BAND[1])).sum()),
        "true_floor_+-15mm": int((np.abs(dead_fh) <= 0.015).sum()),
        "shell_above_15..60mm": int(((dead_fh > SHELL_ABOVE[0]) & (dead_fh <= SHELL_ABOVE[1])).sum()),
        "above_60mm": int((dead_fh > 0.06).sum()),
        "below_-60mm": int((dead_fh < DBL_BAND[0]).sum()),
    }
    wall["metrics_s"] = round(time.perf_counter()-t0, 1)

    # ---- band evidence accounting ----
    in_band = (fh_before >= DBL_BAND[0]) & (fh_before < DBL_BAND[1])
    band_idx = np.flatnonzero(in_band)
    e_pts = set()
    for e in edges_all: e_pts.add(e[0]); e_pts.add(e[1])
    band_with_edge = int(sum(1 for i in band_idx if i in e_pts))
    band_dead = int((~alive[band_idx]).sum())
    band_ge2obs = int((n_obs0[band_idx] >= 2).sum())

    # ---- kill audit (>=30 dead losers, projected into real photos) ----
    t0 = time.perf_counter()
    audit = kill_audit(cap, d, out, dead_idx, heir, pts, cur_pos, fh_before, obs, n_obs0,
                       pose_R, pose_t, f_, cx_, cy_, resolve)
    wall["audit_s"] = round(time.perf_counter()-t0, 1)

    # ---- renders ----
    t0 = time.perf_counter()
    from PIL import Image
    a = np.array([1.0,0,0])
    if abs(pn @ a) > 0.9: a = np.array([0,0,1.0])
    u_ax = a - (a @ pn) * pn; u_ax /= np.linalg.norm(u_ax)
    ub = pts @ u_ax; ua = after_pts @ u_ax
    # true-color cross-sections (E9-C style, before vs after)
    pA, umin, umax = xsec_panel(ub, fh_before*1000, cols)
    pA = annotate(pA, f"{cap} BEFORE v1.1  (band [-60,-15)mm shaded, line=floor)  n={nV}")
    pB, _, _ = xsec_panel(ua, fh_after*1000, after_rgb, umin=umin, umax=umax)
    pB = annotate(pB, f"{cap} AFTER E11 merge-and-transfer  n={len(after_pts)}  deaths={n_dead}")
    gap = np.full((26, pA.shape[1], 3), 40, np.uint8)
    Image.fromarray(np.concatenate([pA, gap, pB], 0)).save(f"{out}/ghost_crosssection_floor_{cap}.png")
    # diff cross-section: gray=untouched, red=dead losers, green=strengthened winners
    colD = np.tile(np.array([120,120,120], np.uint8), (nV,1))
    colD[dead_idx] = (255, 40, 40)
    colD[strengthened] = (80, 230, 110)
    pD, _, _ = xsec_panel(ub, fh_before*1000, colD, umin=umin, umax=umax)
    pD = annotate(pD, f"{cap} DIFF  red=died-naturally losers (orig pos), green=strengthened winners")
    Image.fromarray(np.concatenate([pA, gap, pD], 0)).save(f"{out}/ghost_crosssection_diff_{cap}.png")
    # true-color side-by-side (top XZ + elevation XY)
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
    ply_cand = f"{out}/e11_candidate_{cap}.ply"
    write_ply_xyzrgb(ply_cand, after_pts, after_rgb,
                     f"E11 merge-and-transfer candidate {cap}: support decides winner only; "
                     f"loser obs individually gated (<= {GATE_PX}px at winner, view<60deg) and transferred; "
                     f"loser dies only when <2 obs remain; frozen production poses (zero BA warp)")
    diff_pts = np.vstack([pts[~strengthened & alive], pts[dead_idx], cur_pos[strengthened]])
    n_un = int((~strengthened & alive).sum())
    diff_rgb = np.vstack([np.tile(np.array([120,120,120], np.uint8), (n_un,1)),
                          np.tile(np.array([255,40,40], np.uint8), (n_dead,1)),
                          np.tile(np.array([0,220,0], np.uint8), (n_strength,1))])
    ply_diff = f"{out}/diff_transfer_{cap}.ply"
    write_ply_xyzrgb(ply_diff, diff_pts, diff_rgb,
                     f"E11 diff {cap}: red=naturally-died losers (orig pos), green=strengthened winners (new pos), gray=untouched")
    comp_arr = np.array(comp_log, dtype=np.float64) if comp_log else np.zeros((0,11))
    np.savez_compressed(f"{out}/transfer_provenance_{cap}.npz",
                        alive=alive, heir=heir, cur_pos=cur_pos, orig_pos=pts,
                        strengthened=strengthened, n_obs0=n_obs0,
                        n_own_final=np.array([len(own(i)) for i in range(nV)]),
                        n_got_final=np.array([len(got_obs[i] or {}) for i in range(nV)]),
                        comp_log=comp_arr,
                        comp_log_cols=np.array(["winner","loser","w_nobs","l_nobs","n_transfer",
                                                "n_from_loser","n_dup","died","cross_layer","dist_m","winner_moved"]),
                        is_inj=is_inj)

    def q(a_, pcts=(10,50,90)):
        a_ = np.asarray(a_, float); a_ = a_[np.isfinite(a_)]
        return {f"p{p}": round(float(np.percentile(a_,p)),5) for p in pcts} if len(a_) else {}

    te = np.array(transfer_errs)
    thin_pct = None
    if fl_before["thickness_med_cell_p90p10_m"] and fl_after["thickness_med_cell_p90p10_m"]:
        thin_pct = round(100.0*(fl_after["thickness_med_cell_p90p10_m"]/fl_before["thickness_med_cell_p90p10_m"]-1.0), 2)

    # ---- three-way reconciliation (E8 / E9 / E11) ----
    e8s = json.load(open(f"{E8D}/stats_all.json"))[cap]
    e9s = json.load(open(f"{E9D}/analysis/shell_metrics_fixed.json"))
    e9arm = e9s["summary"][cap]["arm_deltas"].get("conflict_mv", {})
    recon = {
        "E8_all_or_nothing": {
            "band_delta_pct": round(100*e8s["ghost_shell"]["double_floor_band"]["delta"]/band_before, 2),
            "cross_layer_rejected": "44-47% of attempts died at all-or-nothing reproj>4px",
            "fail_reproj": e8s["merge_funnel"].get("fail_reproj_gt4px"),
            "attempted": e8s["merge_funnel"].get("attempted"),
        },
        "E9_conflict_mv_blunt_knife": {
            "band_below_delta_pct": e9arm.get("band_below_delta_pct"),
            "cover_delta_pct": e9arm.get("cover_delta_pct"),
            "pose_warp": e9arm.get("pose_warp"),
            "verdict": ("cap51: band -96.3% but coverage -30.3% FAIL (collateral kill); "
                        "cap50: band +38.0% (pose-gauge warp made it WORSE) -- topology surgery + BA = E9-C lesson"),
        },
        "E11_this": {
            "band_delta": band_after - band_before,
            "band_delta_pct": round(100*(band_after-band_before)/band_before, 2),
            "cover_delta": fl_after["cover_cells_2cm"] - fl_before["cover_cells_2cm"],
            "cross_layer_obs_gate": {
                "attempted": cross_layer_obs[0], "passed": cross_layer_obs[1],
                "pass_rate_pct": round(100*cross_layer_obs[1]/max(cross_layer_obs[0],1), 2),
                "note": "per-observation transfer pass rate on cross-layer (|dfh|>1.5cm) competitions -- E8's death spot",
            },
        },
    }

    stats = {
        "cap": cap,
        "inputs": {"db": DB, "meta": META, "production_ply_sha256": ply_sha,
                   "baseline": "v1.1 candidate (user-approved E6 output)",
                   "v1_1_ply_sha256": v11_sha},
        "gauge": "production refined poses FROZEN throughout; no BA, no Sim3; zero pose warp by construction (E9-C lesson bypassed)",
        "semantics": {
            "winner": "support count (recovered obs) decides winner ONLY; ties by mean self-reproj",
            "loser": f"observations individually gated at winner position (pos depth -> reproj <= {GATE_PX}px "
                     f"(our 3-4px caliber; chi2 sigma=1 equiv 16) -> view angle < 60 deg); passing obs TRANSFER; "
                     "loser keeps failures; dies naturally only when < 2 own obs remain",
            "winner_retriangulation": f"multiview DLT over merged obs; accepted only if all obs <= {GATE_PX}px "
                                      f"AND inside member bbox +-{DLT_ENVELOPE_M}m (E8 dive lesson); else position kept",
            "small_steps": f"top-confidence {int(ROUND_FRAC*100)}% of open competitions per round (min {ROUND_MIN}), "
                           "positions retriangulated between rounds, iterate to convergence + final full pass",
            "aux_distance_veto_m": COMP_MAX_DIST_M,
            "coverage_guard": "constructive atomic veto: death emptying an uncovered 2cm cell vetoes the whole competition; "
                              "winner reposition emptying its sole cell is skipped",
            "license": "ORB-SLAM2 Fuse/Replace criteria SEMANTICS self-implemented; zero GPLv3 code copied",
        },
        "obs_recovery": {
            "stock_ge2_obs": int((n_obs0[:nE3]>=2).sum()), "stock_1_obs": int((n_obs0[:nE3]==1).sum()),
            "stock_0_obs": int((n_obs0[:nE3]==0).sum()), "n_stock": nE3, "n_injected": nV-nE3,
        },
        "evidence_graph": {"edges_A_shared_track": len(edgesA), "edges_B_pair_bridge": len(edgesB),
                           "edges_union": len(edges_all), "roots_skipped_fanout": n_root_skipped},
        "funnel": dict(S),
        "rounds": rounds_hist,
        "transfer_reproj_px": {"n": int(len(te)), **q(te),
                               "pass_at_2.45px_chi2_5.99": int((te <= GATE_PX_SENS[0]).sum()) if len(te) else 0,
                               "pass_at_3px": int((te <= GATE_PX_SENS[1]).sum()) if len(te) else 0},
        "obs_conservation": {
            "total_before": total_before, "kept_on_alive": kept_alive,
            "transferred_into_alive_winners": got_alive,
            "dropped_only_with_dying_loser": dropped,
            "bridge_pair_obs_injected": int(bridge_extra),
            "identity": "before + bridge_injected == kept + transferred + dropped",
            "holds": bool(total_before + bridge_extra == kept_alive + got_alive + dropped),
        },
        "ruler_1_points": {"before_v11": nV, "after_e11": int(len(after_pts)),
                           "delta": int(len(after_pts)-nV),
                           "deaths_natural": n_dead, "strengthened_winners": n_strength,
                           "note": "delta = losers whose remaining obs < 2 after gated transfer (natural death, not killed)"},
        "ruler_2_floor_thickness": {"y_floor": round(y_floor,4), "before": fl_before, "after": fl_after,
                                    "med_cell_change_pct": thin_pct},
        "ruler_2b_wall_thickness_proxy": {"before": wl_before, "after": wl_after},
        "ruler_3_coverage_hard_gate": {"before_cells_2cm": fl_before["cover_cells_2cm"],
                                       "after_cells_2cm": fl_after["cover_cells_2cm"],
                                       "delta": fl_after["cover_cells_2cm"] - fl_before["cover_cells_2cm"],
                                       "pass": fl_after["cover_cells_2cm"] >= fl_before["cover_cells_2cm"],
                                       "constructive_vetoes": int(S["cov_guard_veto"])},
        "ruler_4_wallclock_host_proxy_s": wall,
        "ghost_shell_v11_caliber": {
            "double_floor_band": {"band": list(DBL_BAND), "before": band_before, "after": band_after,
                                  "delta": band_after - band_before,
                                  "delta_pct": round(100*(band_after-band_before)/band_before, 2)},
            "below_floor": {"before": below_before, "after": below_after},
            "band_evidence_accounting": {"band_points_before": int(len(band_idx)),
                                         "band_points_with_ge2_obs": band_ge2obs,
                                         "band_points_touching_any_edge": band_with_edge,
                                         "band_points_died": band_dead},
        },
        "ghost_shell_e9c_fixed_frame_v2": e9c,
        "g1_true_surface_retention": {
            "true_floor_pts_before": int(true_floor.sum()),
            "true_floor_pts_died": tf_dead,
            "true_floor_obs_before": tf_obs_before,
            "true_floor_obs_after_incl_transfers": tf_obs_after,
            "retention_pct": round(100*tf_obs_after/max(tf_obs_before,1), 3),
            "dying_tf_losers_detail": {
                "obs_transferred_to_winner_retained": tf_xfer,
                "obs_dropped_genuine_loss": tf_drop,
                "winners_still_in_pm15mm": f"{tf_winner_in15}/{tf_winner_total}",
            },
            "zero_dropped": bool(tf_drop == 0),
            "e9_reference": "E9 conflict_mv collateral kill on true floor was -42%; this ruler is the same red line",
            "note": "obs on |fh|<=15mm points; transfers INTO true-floor winners count toward retention; "
                    "transferred-out obs live on the winner (retained), only dropped obs are losses",
        },
        "chair_roi": {"before": roi_before, "after": roi_after},
        "dead_fh_histogram": dead_hist,
        "winner_displacement_m": q(disp_winner[strengthened | (disp_winner > 0)]),
        "kill_audit": audit,
        "three_way_reconciliation": recon,
    }
    stats["outputs_sha256"] = {os.path.basename(p): sha256(p) for p in
                               [ply_cand, ply_diff,
                                f"{out}/transfer_provenance_{cap}.npz",
                                f"{out}/ghost_crosssection_floor_{cap}.png",
                                f"{out}/ghost_crosssection_diff_{cap}.png",
                                f"{out}/side_by_side_{cap}.png"] +
                               ([f"{out}/kill_audit_{cap}.png"] if os.path.exists(f"{out}/kill_audit_{cap}.png") else [])}
    json.dump(stats, open(f"{out}/stats.json", "w"), indent=2)
    log(json.dumps({k: stats[k] for k in ("funnel","ruler_1_points","ruler_2_floor_thickness",
                                          "ruler_3_coverage_hard_gate","ghost_shell_v11_caliber",
                                          "three_way_reconciliation")}, indent=1, default=str)[:3200])
    return stats


def kill_audit(cap, capdir, out, dead_idx, heir, pts, cur_pos, fh_before, obs, n_obs0,
               pose_R, pose_t, f_, cx_, cy_, resolve):
    """Sample >=30 naturally-died losers; verify each is a shell multiplet (twin of a
    surviving winner at the same pixel site), not real geometry. Project loser (red)
    and its heir winner (green) into the actual capture photo of one of the loser's
    observation frames; crop a patch around the site."""
    if len(dead_idx) == 0:
        return {"n_dead": 0, "note": "no deaths"}
    rng = random.Random(AUDIT_SEED)
    sample = sorted(rng.sample(list(map(int, dead_idx)), min(AUDIT_N, len(dead_idx))))
    # frame id -> photo path
    fid2jpg = {}
    jl = os.path.join(capdir, "sfm_fed_frames.jsonl")
    if os.path.exists(jl):
        for line in open(jl):
            try:
                r = json.loads(line)
                fid2jpg[int(r["frameId"])] = os.path.join(capdir, "photos_highres",
                                                          os.path.basename(r["jpegPath"]))
            except Exception:
                continue
    rows, crops = [], []
    from PIL import Image, ImageDraw
    PATCH = 140
    for li in sample:
        wi = resolve(li)
        d_lw = float(np.linalg.norm(pts[li] - cur_pos[wi]))
        row = {"loser": int(li), "winner": int(wi),
               "loser_fh_mm": round(float(fh_before[li])*1000, 1),
               "winner_fh_mm": round(float(fh_before[wi])*1000, 1),
               "dist_loser_winner_mm": round(d_lw*1000, 1),
               "loser_n_obs": int(n_obs0[li]), "winner_n_obs0": int(n_obs0[wi])}
        # classify
        fh = fh_before[li]
        if DBL_BAND[0] <= fh < DBL_BAND[1]: row["zone"] = "double_floor_band"
        elif abs(fh) <= 0.015: row["zone"] = "true_floor"
        elif SHELL_ABOVE[0] < fh <= SHELL_ABOVE[1]: row["zone"] = "shell_above"
        else: row["zone"] = "elsewhere"
        # photo projection
        crop_done = False
        for (fid, node, x, y) in obs[li]:
            jp = fid2jpg.get(fid)
            if not jp or not os.path.exists(jp): continue
            try:
                im = Image.open(jp)
            except Exception:
                continue
            def proj(X):
                Xc = pose_R[fid] @ X + pose_t[fid]
                if Xc[2] <= 0: return None
                return (f_*Xc[0]/Xc[2]+cx_, f_*Xc[1]/Xc[2]+cy_)
            pl, pw = proj(pts[li]), proj(cur_pos[wi])
            if pl is None: continue
            cx0, cy0 = int(x), int(y)
            box = (max(cx0-PATCH//2,0), max(cy0-PATCH//2,0),
                   min(cx0+PATCH//2, im.width), min(cy0+PATCH//2, im.height))
            patch = im.crop(box).convert("RGB")
            dr = ImageDraw.Draw(patch)
            def mark(p, color):
                if p is None: return
                px_, py_ = p[0]-box[0], p[1]-box[1]
                if -10 <= px_ <= patch.width+10 and -10 <= py_ <= patch.height+10:
                    dr.ellipse([px_-5, py_-5, px_+5, py_+5], outline=color, width=2)
            mark(pl, (255, 60, 60)); mark(pw, (60, 255, 90))
            dr.text((3, 2), f"L{li} fh{row['loser_fh_mm']} d{row['dist_loser_winner_mm']}mm", fill=(255,255,80))
            crops.append(np.asarray(patch.resize((PATCH, PATCH))))
            row["photo"] = os.path.basename(jp); row["frame"] = int(fid)
            row["reproj_sep_px"] = round(float(np.hypot(pl[0]-pw[0], pl[1]-pw[1])), 1) if pw else None
            crop_done = True
            break
        row["photo_checked"] = crop_done
        rows.append(row)
    # contact sheet
    if crops:
        ncol = 6
        nrow = (len(crops)+ncol-1)//ncol
        sheet = np.full((nrow*PATCH+ (nrow-1)*4, ncol*PATCH+(ncol-1)*4, 3), 30, np.uint8)
        for i, cimg in enumerate(crops):
            r_, c_ = divmod(i, ncol)
            y0, x0 = r_*(PATCH+4), c_*(PATCH+4)
            sheet[y0:y0+cimg.shape[0], x0:x0+cimg.shape[1]] = cimg
        Image.fromarray(sheet).save(f"{out}/kill_audit_{cap}.png")
    zones = defaultdict(int)
    for r in rows: zones[r["zone"]] += 1
    seps = [r["reproj_sep_px"] for r in rows if r.get("reproj_sep_px") is not None]
    summary = {
        "n_dead_total": int(len(dead_idx)),
        "n_sampled": len(rows),
        "zone_histogram": dict(zones),
        "dist_loser_winner_mm": {
            "p50": round(float(np.median([r["dist_loser_winner_mm"] for r in rows])), 1),
            "p90": round(float(np.percentile([r["dist_loser_winner_mm"] for r in rows], 90)), 1)},
        "reproj_sep_px_p50": round(float(np.median(seps)), 1) if seps else None,
        "true_floor_deaths_in_sample": zones.get("true_floor", 0),
        "rows": rows,
    }
    json.dump(summary, open(f"{out}/kill_audit_{cap}.json", "w"), indent=2)
    return {k: v for k, v in summary.items() if k != "rows"}


if __name__ == "__main__":
    caps = sys.argv[1:] or list(CAPS)
    os.makedirs(OUT_BASE, exist_ok=True)
    all_path = os.path.join(OUT_BASE, "stats_all.json")
    allstats = json.load(open(all_path)) if os.path.exists(all_path) else {}
    for cap in caps:
        allstats[cap] = run_cap(cap, CAPS[cap])
        json.dump(allstats, open(all_path, "w"), indent=2)
    log("ALL DONE")
