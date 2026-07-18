#!/usr/bin/env python3.11
"""E16 analysis — M2 low-parallax birth ban vs banked E9 off x3 baselines.

Calibers:
  * shell metrics = e9_shell_metrics_fixed_v2 verbatim (fixed production plane
    normal + per-cloud shift-only dominant-floor re-anchor, E8 constants);
  * raw production-frame forensics = E12 main ruler (floor peak [-7.5,+12.5)mm,
    ghost [-45,-20), fat [-45,-10), above-junk [60,95), below <-100mm) + 5mm
    histogram bimodality contrast;
  * NEW per-face ledger (task order: floor/wall/objects losses must be split):
    fixed wall frame fit ONCE on the off representative cloud per cap, applied
    to every arm (fixed-ruler discipline); wall cover = 2cm cells on (w,fh)
    within |sd|<=6cm, fh>0.10; objects = rest (secondary walls included -
    documented crudeness, identical across arms);
  * diff coloring for the eyeball deliverable: OFF rep cloud, red = point with
    NO M2-arm neighbor within 2cm (the births the ban removed, plus run noise
    whose floor is measured by the off_r1-vs-off_r2 control), other points
    keep device-cloud NN true color; M2 clouds get the standard NN true-color
    (>10cm pure red) transfer.
Baselines are the banked E9 off runs (NOT rerun). Read-only outside E16 dir.
"""
import csv, json, os, re, struct
import numpy as np
from scipy.spatial import cKDTree

D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{D}/experiments/rs_replication_exec_2026-07-19"
E9_RUNS = f"{EXP}/E9_birth_alias/runs"
E16 = f"{EXP}/E16_m2_lowparallax"
E16_RUNS, OUT = f"{E16}/runs", f"{E16}/analysis"
os.makedirs(OUT, exist_ok=True)

FLOOR_SLAB, COVER_SLAB = 0.06, 0.03
CELL_THICK, CELL_COVER = 0.05, 0.02
BAND_BELOW = (-0.06, -0.015)
SHELL_ABOVE = (0.015, 0.06)
GHOST_BAND = (-0.045, -0.02)
BELOW_FLOOR = -0.10
WALL_MIN_FH, WALL_FIT_MIN_FH, WALL_SLAB = 0.10, 0.30, 0.06
NN_RED_M = 0.10
DIFF_ABSENT_M = 0.02  # OFF point with no arm neighbor within 2cm -> banned/absent

E16_ARMS = ["m2", "e16exe_envoff", "m2_r002", "m2_r005", "m2_r015"]

RUN_DIR = {}
for nm in ("cap50_off_r1", "cap50_off_r2", "cap50_off_r3",
           "cap51_off_r1", "cap51_off_r2", "cap51_off_r3"):
    RUN_DIR[nm] = f"{E9_RUNS}/{nm}"
for cap in ("cap50", "cap51"):
    for arm in E16_ARMS:
        nm = f"{cap}_{arm}"
        if os.path.isdir(f"{E16_RUNS}/{nm}"):
            RUN_DIR[nm] = f"{E16_RUNS}/{nm}"


def read_points3d_bin(p):
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        xyz = np.empty((n, 3), np.float64)
        for i in range(n):
            f.read(8)
            xyz[i] = np.frombuffer(f.read(24), dtype="<f8")
            f.read(3 + 8)
            (tl,) = struct.unpack("<Q", f.read(8))
            f.read(8 * tl)
    return xyz


def read_ply(path):
    with open(path, "rb") as f:
        h = b""
        while not h.endswith(b"end_header\n"):
            h += f.readline()
        n = int([l for l in h.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        d = np.fromfile(f, dtype=rec, count=n)
    return np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)


def write_ply(path, xyz, rgb):
    rec = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    d = np.empty(len(xyz), rec)
    d["x"], d["y"], d["z"] = xyz[:,0].astype(np.float32), xyz[:,1].astype(np.float32), xyz[:,2].astype(np.float32)
    d["r"], d["g"], d["b"] = rgb[:,0], rgb[:,1], rgb[:,2]
    with open(path, "wb") as f:
        f.write((f"ply\nformat binary_little_endian 1.0\nelement vertex {len(xyz)}\n"
                 "property float x\nproperty float y\nproperty float z\n"
                 "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
        d.tofile(f)


def device_cloud(cap):
    return read_ply(f"{D}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17/sfm_sparse.ply")


def export_arm_ply(cap, arm, dev_tree, dev_rgb):
    run = f"{cap}_{arm}"
    dst = f"{RUN_DIR[run]}/replay_finalize.ply"
    xyz = read_points3d_bin(f"{RUN_DIR[run]}/points3D.bin")
    dist, idx = dev_tree.query(xyz, k=1)
    rgb = dev_rgb[idx].copy()
    far = dist > NN_RED_M
    rgb[far] = (255, 0, 0)
    write_ply(dst, xyz, rgb)
    return {"n_points": int(len(xyz)), "nn_median_mm": round(float(np.median(dist))*1000, 2),
            "nn_p90_mm": round(float(np.percentile(dist, 90))*1000, 2),
            "red_gt10cm": int(far.sum()), "red_gt10cm_pct": round(100*float(far.mean()), 3)}


def diff_color_off(cap, off_run, arm, dev_tree, dev_rgb):
    """OFF cloud diff-colored against an arm cloud: absent-in-arm -> pure red."""
    off_xyz, _ = read_ply(f"{RUN_DIR[off_run]}/replay_finalize.ply")
    arm_xyz, _ = read_ply(f"{RUN_DIR[f'{cap}_{arm}']}/replay_finalize.ply")
    dist_arm, _ = cKDTree(arm_xyz).query(off_xyz, k=1)
    absent = dist_arm > DIFF_ABSENT_M
    dist_dev, idx = dev_tree.query(off_xyz, k=1)
    rgb = dev_rgb[idx].copy()
    rgb[dist_dev > NN_RED_M] = (128, 128, 128)  # geometry unknown to device cloud -> gray
    rgb[absent] = (255, 0, 0)                    # absent under the arm -> RED (banned+noise)
    dst = f"{OUT}/{cap}_{off_run.split('_',1)[1]}_diff_vs_{arm}.ply"
    write_ply(dst, off_xyz, rgb)
    return {"ply": os.path.relpath(dst, EXP), "n_off": int(len(off_xyz)),
            "absent_red": int(absent.sum()), "absent_red_pct": round(100*float(absent.mean()), 3)}


def control_noise(cap):
    """off_r1 vs off_r2 absent rate at the same radius = run-to-run noise floor."""
    a, _ = read_ply(f"{RUN_DIR[f'{cap}_off_r1']}/replay_finalize.ply")
    b, _ = read_ply(f"{RUN_DIR[f'{cap}_off_r2']}/replay_finalize.ply")
    d, _ = cKDTree(b).query(a, k=1)
    return round(100*float((d > DIFF_ABSENT_M).mean()), 3)


def anchor_floor(fh):
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


def cell_spreads(key, vals, min_pts=8):
    order = np.argsort(key)
    k, v = key[order], vals[order]
    bounds = np.flatnonzero(np.diff(k)) + 1
    return [float(np.percentile(g,90)-np.percentile(g,10)) for g in np.split(v, bounds) if len(g) >= min_pts]


def floor_metrics(xyz, fh):
    slab = np.abs(fh) <= FLOOR_SLAB
    P, f = xyz[slab], fh[slab]
    out = {"n_floor_slab": int(slab.sum()),
           "n_true_floor": int(((fh >= -0.015) & (fh <= FLOOR_SLAB)).sum())}
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


def fit_dominant_wall(xyz, fh, pn):
    P = xyz[fh > WALL_FIT_MIN_FH]
    if len(P) < 500: return None, None
    best = (None, None, -1)
    for ang in np.arange(0, 180, 1.0):
        t = np.radians(ang)
        d3 = np.array([np.cos(t), 0.0, np.sin(t)])
        d3 = d3 - (d3 @ pn)*pn
        nl = np.linalg.norm(d3)
        if nl < 1e-6: continue
        d3 /= nl
        pr = P @ d3
        hist, edges = np.histogram(pr, bins=np.arange(pr.min(), pr.max()+0.01, 0.01))
        k = int(np.argmax(hist))
        if hist[k] > best[2]: best = (d3, 0.5*(edges[k]+edges[k+1]), int(hist[k]))
    return best[0], best[1]


def face_ledger(xyz, fh, wall_d, wall_off, pn):
    """Per-face split with the FIXED wall frame: floor slab / dominant wall slab / rest."""
    floor_m = np.abs(fh) <= FLOOR_SLAB
    out = {"floor_n": int(floor_m.sum())}
    if wall_d is None:
        out.update(wall_n=None, wall_cover_cells_2cm=None, wall_thick_med_m=None, objects_n=None)
        return out
    sd = xyz @ wall_d - wall_off
    wall_m = (np.abs(sd) <= WALL_SLAB) & (fh > WALL_MIN_FH)
    out["wall_n"] = int(wall_m.sum())
    w_ax = np.cross(pn, wall_d); w_ax /= np.linalg.norm(w_ax)
    W = xyz[wall_m]
    if len(W):
        wu = W @ w_ax
        out["wall_cover_cells_2cm"] = len(set(zip(np.floor(wu/CELL_COVER).astype(np.int64),
                                                  np.floor(fh[wall_m]/CELL_COVER).astype(np.int64))))
        key = np.floor(wu/CELL_THICK).astype(np.int64)*1000003 + np.floor(fh[wall_m]/CELL_THICK).astype(np.int64)
        sp = cell_spreads(key, sd[wall_m])
        out["wall_thick_med_m"] = float(np.median(sp)) if sp else None
    else:
        out["wall_cover_cells_2cm"] = 0
        out["wall_thick_med_m"] = None
    out["objects_n"] = int((~floor_m & ~wall_m).sum())
    return out


def raw_forensics(fh_raw):
    """E12 main-ruler bands in the RAW production frame (no re-anchor)."""
    h, edges = np.histogram(fh_raw[np.abs(fh_raw) <= 0.15], bins=np.arange(-0.15, 0.1505, 0.005))
    centers = 0.5*(edges[:-1]+edges[1:])
    fp = (centers >= -0.010) & (centers < 0.015)
    gp = (centers >= -0.045) & (centers < -0.020)
    floor_peak_bin = int(h[fp].max()) if fp.any() else 0
    ghost_peak_bin = int(h[gp].max()) if gp.any() else 0
    return {
        "floor_peak": int(((fh_raw >= -0.0075) & (fh_raw < 0.0125)).sum()),
        "ghost_band": int(((fh_raw >= -0.045) & (fh_raw < -0.020)).sum()),
        "fat_layer": int(((fh_raw >= -0.045) & (fh_raw < -0.010)).sum()),
        "above_junk": int(((fh_raw >= 0.060) & (fh_raw < 0.095)).sum()),
        "below_floor": int((fh_raw < -0.10).sum()),
        "cover_cells_2cm_raw": None,  # filled by caller (needs xyz)
        "floor_peak_bin5mm": floor_peak_bin,
        "ghost_peak_bin5mm": ghost_peak_bin,
        "bimodal_contrast_ghost_over_floor": round(ghost_peak_bin/max(floor_peak_bin,1), 4),
    }


def parse_result(run_dir):
    txt = open(os.path.join(run_dir, "run.log"), errors="replace").read()
    m = re.search(r"^RESULT .*$", txt, re.M)
    if not m: return None
    res = {}
    for kv in m.group(0).split()[1:]:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try: res[k] = float(v) if "." in v else int(v)
            except ValueError: res[k] = v
    return res


def parse_m2_telemetry(run_dir):
    out = {}
    for fn in ("run.err", "run.log"):
        p = os.path.join(run_dir, fn)
        if not os.path.exists(p): continue
        txt = open(p, errors="replace").read()
        live = re.findall(r"m2-lowparallax frames=(\d+) ratio_min=([\d.]+) pairs_checked=(\d+) pairs_banned=(\d+) births_banned_live=(\d+) nodepth_allow=(\d+)", txt)
        td = re.findall(r"m2-lowparallax-td pairs_checked=(\d+) pairs_banned=(\d+) births_banned_td=(\d+) td_created=(\d+) td_grown=(\d+)", txt)
        if live:
            f, r, pc, pb, bb, nd = live[-1]
            out.update(ratio_min=float(r), live_pairs_checked=int(pc), live_pairs_banned=int(pb),
                       live_births_banned=int(bb), nodepth_allow=int(nd))
        if td:
            pc, pb, bb, cr, gr = td[-1]
            out.update(td_pairs_checked=int(pc), td_pairs_banned=int(pb), td_births_banned=int(bb),
                       td_created=int(cr), td_grown=int(gr))
    return out or None


def qmat(q):
    w,x,y,z = q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                     [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                     [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])


def camera_centers(run):
    d = {}
    with open(f"{RUN_DIR[run]}/solved_poses.csv") as f:
        rd = csv.reader(f); next(rd)
        for row in rd:
            if row[1] != "1": continue
            q = np.array([float(v) for v in row[2:6]]); t = np.array([float(v) for v in row[6:9]])
            R = qmat(q/np.linalg.norm(q))
            d[row[0]] = -R.T @ t
    return d


def pose_warp(cap, arm, ref="off_r2"):
    off, a = camera_centers(f"{cap}_{ref}"), camera_centers(f"{cap}_{arm}")
    common = sorted(set(off) & set(a))
    dl = np.array([a[k]-off[k] for k in common])
    med = np.median(dl, axis=0)
    res = np.percentile(np.linalg.norm(dl-med, axis=1), 90)
    return {"n_common": len(common),
            "median_dC_norm_mm": round(float(np.linalg.norm(med))*1000, 1),
            "p90_residual_mm": round(float(res)*1000,1)}


def xsec_panel(u_arr, fd_mm, colors, W=1500, H=420, umin=None, umax=None):
    c = np.full((H, W, 3), 20, np.uint8)
    FMIN, FMAX = -60.0, 60.0
    if umin is None: umin, umax = float(u_arr.min()), float(u_arr.max())
    def px(u, fd):
        x = ((u-umin)/max(umax-umin,1e-9)*(W-40)+20).astype(int)
        y = ((FMAX-fd)/(FMAX-FMIN)*(H-60)+30).astype(int)
        return x, y
    _, y1 = px(np.array([0.]), np.array([-15.])); _, y2 = px(np.array([0.]), np.array([-60.]))
    c[int(y1[0]):int(y2[0]), 20:W-20] = (45, 25, 25)
    _, y0 = px(np.array([0.]), np.array([0.]))
    c[int(y0[0])-1:int(y0[0])+1, 20:W-20] = (90, 90, 90)
    m = np.abs(fd_mm) <= 60
    x, y = px(u_arr[m], fd_mm[m])
    cols = colors[m]
    ok = (x>=1)&(x<W-1)&(y>=1)&(y<H-1)
    for xi, yi, ci in zip(x[ok], y[ok], cols[ok]):
        c[yi-1:yi+2, xi-1:xi+2] = ci
    return c, umin, umax


def annotate(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((28, 6), text, fill=(235,235,235))
    return np.asarray(im)


def main():
    from PIL import Image
    planes, dev = {}, {}
    for cap in ("cap50", "cap51"):
        gm = json.load(open(f"{D}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17/ghost_mask.json"))
        planes[cap] = (np.array(gm["plane_n"], float), float(gm["plane_d"]))
        dx, dr = device_cloud(cap)
        dev[cap] = (cKDTree(dx), dr)

    ply_export = {}
    for cap in ("cap50", "cap51"):
        for arm in E16_ARMS:
            nm = f"{cap}_{arm}"
            if nm in RUN_DIR and os.path.exists(f"{RUN_DIR[nm]}/points3D.bin"):
                ply_export[nm] = export_arm_ply(cap, arm, *dev[cap])
                print(f"[{nm}] NN true-color export: {ply_export[nm]}")

    # fixed wall frame per cap: fit ONCE on the off representative cloud
    wall_frame = {}
    for cap in ("cap50", "cap51"):
        pn, pd = planes[cap]
        rep = f"{cap}_off_r2"
        xyz, _ = read_ply(f"{RUN_DIR[rep]}/replay_finalize.ply")
        fh_raw = xyz @ pn + pd
        fh = fh_raw - anchor_floor(fh_raw)
        wd, wo = fit_dominant_wall(xyz, fh, pn)
        wall_frame[cap] = (wd, wo)
        print(f"[{cap}] fixed wall frame from {rep}: d={None if wd is None else np.round(wd,4).tolist()} off={wo}")

    caps, fhs = {}, {}
    for name in sorted(RUN_DIR):
        run_dir = RUN_DIR[name]
        ply = os.path.join(run_dir, "replay_finalize.ply")
        if not os.path.exists(ply): continue
        cap = name.split("_")[0]
        arm = name[len(cap)+1:]
        pn, pd = planes[cap]
        xyz, rgb = read_ply(ply)
        fh_raw = xyz @ pn + pd
        shift = anchor_floor(fh_raw)
        fh = fh_raw - shift
        fhs[name] = fh
        fl = floor_metrics(xyz, fh)
        faces = face_ledger(xyz, fh, *wall_frame[cap], pn)
        raw = raw_forensics(fh_raw)
        Q = xyz[np.abs(fh_raw) <= COVER_SLAB]
        raw["cover_cells_2cm_raw"] = len(set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64),
                                                 np.floor(Q[:,2]/CELL_COVER).astype(np.int64))))
        rec = {
            "run": name, "arm": arm, "n_points": int(len(xyz)),
            "gauge_shift_mm": round(shift*1000, 1),
            "band_below": int(((fh >= BAND_BELOW[0]) & (fh < BAND_BELOW[1])).sum()),
            "shell_above": int(((fh > SHELL_ABOVE[0]) & (fh <= SHELL_ABOVE[1])).sum()),
            "ghost_2045": int(((fh >= GHOST_BAND[0]) & (fh < GHOST_BAND[1])).sum()),
            "below_floor": int((fh < BELOW_FLOOR).sum()),
            "floor": fl, "faces": faces, "raw_frame": raw,
            "result": parse_result(run_dir),
            "m2": parse_m2_telemetry(run_dir),
        }
        if arm in E16_ARMS:
            rec["pose_warp_vs_off_r2"] = pose_warp(cap, arm)
        caps.setdefault(cap, {})[arm] = rec
        print(f"{name}: n={rec['n_points']} shift={rec['gauge_shift_mm']}mm band={rec['band_below']} "
              f"ghost2045={rec['ghost_2045']} floorpk={raw['floor_peak']} bimod={raw['bimodal_contrast_ghost_over_floor']} "
              f"floor_n={faces['floor_n']} wall_n={faces['wall_n']} wallcov={faces['wall_cover_cells_2cm']} obj_n={faces['objects_n']} "
              f"cover={fl['cover_cells_2cm']} m2={rec['m2']}")

    summary = {}
    for cap, arms in caps.items():
        offs = {a: r for a, r in arms.items() if a.startswith("off")}
        med = lambda f: float(np.median([f(r) for r in offs.values()]))
        off_med = {
            "n_points": med(lambda r: r["n_points"]),
            "band_below": med(lambda r: r["band_below"]),
            "ghost_2045": med(lambda r: r["ghost_2045"]),
            "raw_floor_peak": med(lambda r: r["raw_frame"]["floor_peak"]),
            "raw_ghost_band": med(lambda r: r["raw_frame"]["ghost_band"]),
            "raw_fat_layer": med(lambda r: r["raw_frame"]["fat_layer"]),
            "raw_below_floor": med(lambda r: r["raw_frame"]["below_floor"]),
            "raw_cover": med(lambda r: r["raw_frame"]["cover_cells_2cm_raw"]),
            "bimodal_contrast": med(lambda r: r["raw_frame"]["bimodal_contrast_ghost_over_floor"]),
            "true_floor": med(lambda r: r["floor"]["n_true_floor"]),
            "cover": med(lambda r: r["floor"]["cover_cells_2cm"]),
            "thick_med": med(lambda r: r["floor"]["thickness_med_cell_p90p10_m"]),
            "floor_n": med(lambda r: r["faces"]["floor_n"]),
            "wall_n": med(lambda r: r["faces"]["wall_n"]),
            "wall_cover": med(lambda r: r["faces"]["wall_cover_cells_2cm"]),
            "wall_thick_med": med(lambda r: r["faces"]["wall_thick_med_m"] or np.nan),
            "objects_n": med(lambda r: r["faces"]["objects_n"]),
            "n_reg": sorted({r["result"]["n_reg"] for r in offs.values()}),
            "reproj": med(lambda r: r["result"]["mean_reproj_px"]),
        }
        deltas = {}
        for a, r in arms.items():
            if a.startswith("off"): continue
            pct = lambda v, k: round(100*(v/max(off_med[k],1e-9)-1), 2)
            deltas[a] = {
                "n_points_delta_pct": pct(r["n_points"], "n_points"),
                "raw_floor_peak_delta_pct": pct(r["raw_frame"]["floor_peak"], "raw_floor_peak"),
                "raw_ghost_band_delta_pct": pct(r["raw_frame"]["ghost_band"], "raw_ghost_band"),
                "raw_fat_layer_delta_pct": pct(r["raw_frame"]["fat_layer"], "raw_fat_layer"),
                "bimodal_contrast": r["raw_frame"]["bimodal_contrast_ghost_over_floor"],
                "bimodal_contrast_off": off_med["bimodal_contrast"],
                "true_floor_delta_pct": pct(r["floor"]["n_true_floor"], "true_floor"),
                "cover_delta_pct": pct(r["floor"]["cover_cells_2cm"], "cover"),
                "floor_n_delta_pct": pct(r["faces"]["floor_n"], "floor_n"),
                "wall_n_delta_pct": pct(r["faces"]["wall_n"], "wall_n") if r["faces"]["wall_n"] is not None else None,
                "wall_cover_delta_pct": pct(r["faces"]["wall_cover_cells_2cm"], "wall_cover") if r["faces"]["wall_cover_cells_2cm"] is not None else None,
                "objects_n_delta_pct": pct(r["faces"]["objects_n"], "objects_n") if r["faces"]["objects_n"] is not None else None,
                "below_floor": r["below_floor"], "below_floor_off_med": med(lambda r2: r2["below_floor"]),
                "gauge_shift_mm": r["gauge_shift_mm"],
                "pose_warp": r.get("pose_warp_vs_off_r2"),
                "n_reg": r["result"].get("n_reg"), "reproj": r["result"].get("mean_reproj_px"),
                "m2_telemetry": r["m2"],
            }
        summary[cap] = {"off_median": off_med, "arm_deltas": deltas}

    # diff-colored OFF clouds (the eyeball deliverable) + noise control
    diffs = {"control_noise_pct(off_r1_vs_off_r2)": {cap: control_noise(cap) for cap in caps}}
    for cap in caps:
        for arm in ("m2", "m2_r002", "m2_r005", "m2_r015"):
            if arm in caps[cap]:
                diffs[f"{cap}_off_diff_vs_{arm}"] = diff_color_off(cap, f"{cap}_off_r2", arm, *dev[cap])
                print(f"[{cap}] diff-color vs {arm}: {diffs[f'{cap}_off_diff_vs_{arm}']}")

    # cross-sections: OFF vs m2 (+ the biting sensitivity arms on cap51)
    for cap in caps:
        pn, pd = planes[cap]
        u_ax = np.cross(pn, np.array([0.,0.,1.])); u_ax /= np.linalg.norm(u_ax)
        rows = [(f"{cap}_off_r2", f"{cap} OFF (off_r2)  band=[-60,-15)mm shaded, line=floor")]
        if "m2" in caps[cap]:
            rows.append((f"{cap}_m2", f"{cap} M2 ratio=0.01 (banned={((caps[cap]['m2']['m2'] or {}).get('live_pairs_banned'))})"))
        for arm, lab in (("m2_r005", "ratio=0.05"), ("m2_r015", "ratio=0.15")):
            if arm in caps[cap]:
                rows.append((f"{cap}_{arm}", f"{cap} M2 {lab} (banned={((caps[cap][arm]['m2'] or {}).get('live_pairs_banned'))})"))
        panels, ext = [], None
        for nm, lab in rows:
            xyz_i, rgb_i = read_ply(f"{RUN_DIR[nm]}/replay_finalize.ply")
            if rgb_i.sum() == 0: rgb_i = np.full_like(rgb_i, 200)
            fd = fhs[nm]*1000
            if ext is None:
                p, umin, umax = xsec_panel(xyz_i @ u_ax, fd, rgb_i); ext = (umin, umax)
            else:
                p, _, _ = xsec_panel(xyz_i @ u_ax, fd, rgb_i, umin=ext[0], umax=ext[1])
            panels.append(annotate(p, lab))
        gap = np.full((24, panels[0].shape[1], 3), 40, np.uint8)
        Image.fromarray(np.concatenate(sum([[p, gap] for p in panels[:-1]], []) + [panels[-1]], 0)).save(f"{OUT}/xsec_e16_{cap}.png")
        print(f"[{cap}] cross-section saved")

    out = {"caliber": "E8 constants; fixed production plane; shift-only re-anchor (v2) + RAW-frame forensics (E12 main ruler); fixed wall frame from off_r2; baselines = banked E9 off x3",
           "ply_export": ply_export, "diff_coloring": diffs, "runs": caps, "summary": summary}
    json.dump(out, open(f"{OUT}/e16_shell_metrics.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
