#!/usr/bin/env python3.11
"""E9-C fixed-framework shell metrics, v2 (final).

Frame design (forensics 2026-07-18, this session):
  * v0 (e9_shell_metrics.py): per-cloud self-fit plane -> CONFOUND (plane snaps to
    ghost layer / wrong slab; cap51 conflict_mv self-d drifted 42mm onto the ghost,
    cap50 exact_v2 drifted 270mm onto furniture).
  * v1 (e9_shell_metrics_fixed.py): single raw production plane -> valid for OFF
    (floor mode +2.5mm both caps) but ON arms warp the pose gauge (median camera
    shift up to 63mm, p90 residual up to 278mm) so their floors sit off-plane.
  * v2 (this): FIXED production plane NORMAL for every cloud + per-cloud shift-only
    re-anchor along that normal to the dominant floor cluster (contiguous bins
    >=35% of max, count-weighted center). No rotation, no scale, no Sim3.
    Anchor shift is itself reported as gauge_shift_mm; pose-gauge warp vs OFF is
    reported from solved_poses.csv (median dC + p90 residual).

Rulers (E8 byte-identical constants) on re-anchored fh':
  band_below   [-0.06,-0.015)   double-floor band under the (re-anchored) floor
  shell_above  (+0.015,+0.06]   upper second layer (cap50 pathology direction)
  ghost_2045   [-0.045,-0.020)  cap51 certified ghost peak band (device: -27..-33mm)
  floor thickness med/p90 cell p90-p10 in |fh'|<=0.06, cover 2cm cells in |fh'|<=0.03,
  dominant-wall proxy, below_floor fh' < -0.10.

Outputs: analysis/shell_metrics_fixed.json (v2 section replaces),
         analysis/xsec_fixed_v2_<cap>.png (off vs conflict_mv vs conflict_mv_owner).
"""
import csv, json, os, re
import numpy as np

D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
E9 = f"{D}/experiments/rs_replication_exec_2026-07-19/E9_birth_alias"
RUNS, OUT = f"{E9}/runs", f"{E9}/analysis"

FLOOR_SLAB, COVER_SLAB = 0.06, 0.03
CELL_THICK, CELL_COVER = 0.05, 0.02
BAND_BELOW = (-0.06, -0.015)
SHELL_ABOVE = (0.015, 0.06)
GHOST_BAND = (-0.045, -0.02)
BELOW_FLOOR = -0.10
WALL_MIN_FH, WALL_FIT_MIN_FH, WALL_SLAB = 0.10, 0.30, 0.06
ARMS_ON = ["conflict_mv", "conflict_mv_owner", "exact_v2", "geom_winner"]


def read_ply(path):
    with open(path, "rb") as f:
        h = b""
        while not h.endswith(b"end_header\n"):
            h += f.readline()
        n = int([l for l in h.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        d = np.fromfile(f, dtype=rec, count=n)
    return np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)


def anchor_floor(fh):
    """Dominant floor cluster center along fixed normal (shift-only re-anchor)."""
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


def wall_metrics(xyz, fh, d, off, pn):
    if d is None: return None
    sd = xyz @ d - off
    m = (np.abs(sd) <= WALL_SLAB) & (fh > WALL_MIN_FH)
    P, s, f = xyz[m], sd[m], fh[m]
    out = {"n_wall_slab": int(m.sum())}
    if len(P) < 100:
        out.update(thickness_med_cell_p90p10_m=None, thickness_p90_cell_m=None)
        return out
    w = np.cross(pn, d); w /= np.linalg.norm(w)
    key = np.floor((P @ w)/CELL_THICK).astype(np.int64)*1000003 + np.floor(f/CELL_THICK).astype(np.int64)
    sp = cell_spreads(key, s)
    out["thickness_med_cell_p90p10_m"] = float(np.median(sp)) if sp else None
    out["thickness_p90_cell_m"] = float(np.percentile(sp,90)) if sp else None
    out["n_thickness_cells"] = len(sp)
    return out


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


def qmat(q):
    w,x,y,z = q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                     [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                     [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])


def camera_centers(run):
    d = {}
    with open(f"{RUNS}/{run}/solved_poses.csv") as f:
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
            "median_dC_mm": [round(v*1000,1) for v in med],
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
    planes = {}
    for cap in ("cap50", "cap51"):
        gm = json.load(open(f"{D}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17/ghost_mask.json"))
        planes[cap] = (np.array(gm["plane_n"], float), float(gm["plane_d"]))

    caps, fhs = {}, {}
    for name in sorted(os.listdir(RUNS)):
        run_dir = os.path.join(RUNS, name)
        ply = os.path.join(run_dir, "replay_finalize.ply")
        if not os.path.isdir(run_dir) or not os.path.exists(ply): continue
        cap = name.split("_")[0]
        arm = name[len(cap)+1:]
        pn, pd = planes[cap]
        xyz, rgb = read_ply(ply)
        fh_raw = xyz @ pn + pd
        shift = anchor_floor(fh_raw)
        fh = fh_raw - shift
        fhs[name] = fh
        fl = floor_metrics(xyz, fh)
        dwall, woff = fit_dominant_wall(xyz, fh, pn)
        wl = wall_metrics(xyz, fh, dwall, woff, pn)
        rec = {
            "run": name, "arm": arm, "n_points": int(len(xyz)),
            "gauge_shift_mm": round(shift*1000, 1),
            "band_below": int(((fh >= BAND_BELOW[0]) & (fh < BAND_BELOW[1])).sum()),
            "shell_above": int(((fh > SHELL_ABOVE[0]) & (fh <= SHELL_ABOVE[1])).sum()),
            "ghost_2045": int(((fh >= GHOST_BAND[0]) & (fh < GHOST_BAND[1])).sum()),
            "below_floor": int((fh < BELOW_FLOOR).sum()),
            "floor": fl, "wall_proxy": wl,
            "result": parse_result(run_dir),
        }
        if arm in ARMS_ON:
            rec["pose_warp_vs_off_r2"] = pose_warp(cap, arm)
        rec["band_frac_pct"] = round(100*rec["band_below"]/max(rec["n_points"],1), 3)
        caps.setdefault(cap, {})[arm] = rec
        print(f"{name}: n={rec['n_points']} shift={rec['gauge_shift_mm']}mm "
              f"band_below={rec['band_below']} shell_above={rec['shell_above']} "
              f"ghost2045={rec['ghost_2045']} below={rec['below_floor']} "
              f"thick_med={fl.get('thickness_med_cell_p90p10_m')} cover={fl.get('cover_cells_2cm')}")

    summary = {}
    for cap, arms in caps.items():
        offs = {a: r for a, r in arms.items() if a.startswith("off")}
        med = lambda f: float(np.median([f(r) for r in offs.values()]))
        off_med = {
            "band_below_median": med(lambda r: r["band_below"]),
            "band_runs": {a: r["band_below"] for a, r in offs.items()},
            "shell_above_median": med(lambda r: r["shell_above"]),
            "ghost_2045_median": med(lambda r: r["ghost_2045"]),
            "n_points_median": med(lambda r: r["n_points"]),
            "thick_med_median": med(lambda r: r["floor"]["thickness_med_cell_p90p10_m"]),
            "thick_p90_median": med(lambda r: r["floor"]["thickness_p90_cell_m"]),
            "cover_median": med(lambda r: r["floor"]["cover_cells_2cm"]),
            "wall_thick_med_median": med(lambda r: (r["wall_proxy"] or {}).get("thickness_med_cell_p90p10_m") or np.nan),
            "below_floor_median": med(lambda r: r["below_floor"]),
            "reproj_median": med(lambda r: r["result"]["mean_reproj_px"]),
            "gauge_shift_mm": {a: r["gauge_shift_mm"] for a, r in offs.items()},
            "n_reg": sorted({r["result"]["n_reg"] for r in offs.values()}),
        }
        mb = off_med["band_below_median"]
        off_med["rep_off_run"] = min(offs.values(), key=lambda r: abs(r["band_below"]-mb))["run"]
        deltas = {}
        for a, r in arms.items():
            if a.startswith("off"): continue
            w = (r["wall_proxy"] or {}).get("thickness_med_cell_p90p10_m")
            deltas[a] = {
                "band_below_delta_pct": round(100*(r["band_below"]/max(mb,1e-9)-1), 2),
                "ghost2045_delta_pct": round(100*(r["ghost_2045"]/max(off_med["ghost_2045_median"],1e-9)-1), 2),
                "shell_above_delta_pct": round(100*(r["shell_above"]/max(off_med["shell_above_median"],1e-9)-1), 2),
                "points_delta_pct": round(100*(r["n_points"]/off_med["n_points_median"]-1), 2),
                "thick_med_delta_pct": round(100*(r["floor"]["thickness_med_cell_p90p10_m"]/off_med["thick_med_median"]-1), 2) if r["floor"]["thickness_med_cell_p90p10_m"] else None,
                "cover_delta_pct": round(100*(r["floor"]["cover_cells_2cm"]/off_med["cover_median"]-1), 2),
                "wall_thick_delta_pct": round(100*(w/off_med["wall_thick_med_median"]-1), 2) if w and off_med["wall_thick_med_median"]==off_med["wall_thick_med_median"] else None,
                "below_floor": r["below_floor"],
                "gauge_shift_mm": r["gauge_shift_mm"],
                "pose_warp": r.get("pose_warp_vs_off_r2"),
                "n_reg": r["result"].get("n_reg"), "reproj": r["result"].get("mean_reproj_px"),
            }
        summary[cap] = {"frame": "fixed production normal + per-cloud dominant-floor re-anchor (shift-only)",
                        "off_median": off_med, "arm_deltas": deltas}

        pn, pd = planes[cap]
        u_ax = np.cross(pn, np.array([0.,0.,1.])); u_ax /= np.linalg.norm(u_ax)
        rep = off_med["rep_off_run"]
        panels, ext = [], None
        for nm, lab in [(rep, f"{cap} OFF ({rep})  band=[-60,-15)mm shaded, line=floor"),
                        (f"{cap}_conflict_mv", f"{cap} conflict_mv  (shift {arms['conflict_mv']['gauge_shift_mm']}mm)"),
                        (f"{cap}_conflict_mv_owner", f"{cap} conflict_mv_owner  (shift {arms['conflict_mv_owner']['gauge_shift_mm']}mm)")]:
            xyz_i, rgb_i = read_ply(f"{RUNS}/{nm}/replay_finalize.ply")
            fd = fhs[nm]*1000
            if ext is None:
                p, umin, umax = xsec_panel(xyz_i @ u_ax, fd, rgb_i); ext = (umin, umax)
            else:
                p, _, _ = xsec_panel(xyz_i @ u_ax, fd, rgb_i, umin=ext[0], umax=ext[1])
            panels.append(annotate(p, lab))
        gap = np.full((24, panels[0].shape[1], 3), 40, np.uint8)
        Image.fromarray(np.concatenate([panels[0], gap, panels[1], gap, panels[2]], 0)).save(f"{OUT}/xsec_fixed_v2_{cap}.png")
        print(f"[{cap}] v2 cross-section saved")

    out = {"caliber": "E8 constants; fixed production plane normal; per-cloud shift-only floor re-anchor",
           "frame_forensics": {
               "v0_self_plane_confound": "cap51 conflict_mv self-d drifted 42mm onto ghost; cap50 exact_v2 270mm onto furniture; cap50 off self-planes 20mm above production floor",
               "v1_raw_fixed_plane": "valid for OFF (floor mode +2.5mm both caps) but ON arms warp pose gauge (see pose_warp)",
               "device_reference_hist": {
                   "cap50": "broad multi-layer floor: ghost -22/-27mm + main -7..+32mm (mode +12.5mm) + deep -67/-72mm",
                   "cap51": "clean bimodal: main +2.5/+7.5mm (~5100/bin), ghost -27/-32mm (~1700-1900/bin)"}},
           "runs": caps, "summary": summary}
    json.dump(out, open(f"{OUT}/shell_metrics_fixed.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
