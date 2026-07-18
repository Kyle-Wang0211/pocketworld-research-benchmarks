#!/usr/bin/env python3.11
"""E9-C FIXED-FRAME shell metrics — one production-certified floor plane per cap,
identical for every arm (kills the per-cloud self-plane confound of e9_shell_metrics.py).

Fixed frame source: data/pocketworld_captures/<cap>/device_full_pull_2026-07-17/ghost_mask.json
(plane_n, plane_d — production delivery-cloud certified plane).
Gauge validation (2026-07-18, this session): OFF replay clouds' floor mode sits at +2.5 mm
under the production plane for BOTH caps => shared gauge, no Sim3, plane directly applicable.

Ruler caliber = E8 byte-identical constants. Outputs:
  analysis/shell_metrics_fixed.json
  analysis/xsec_fixed_<cap>.png  (off vs conflict_mv vs conflict_mv_owner, +/-60mm, fixed frame)
"""
import json, os, re
import numpy as np

D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
E9 = f"{D}/experiments/rs_replication_exec_2026-07-19/E9_birth_alias"
RUNS, OUT = f"{E9}/runs", f"{E9}/analysis"

FLOOR_SLAB = 0.06
COVER_SLAB = 0.03
CELL_THICK = 0.05
CELL_COVER = 0.02
DBL_BAND = (-0.06, -0.015)
GHOST_BAND = (-0.045, -0.02)   # diagnostic: cap51 ghost peak sits at -32.5..-37.5mm
BELOW_FLOOR = -0.10
WALL_MIN_FH = 0.10
WALL_FIT_MIN_FH = 0.30
WALL_SLAB = 0.06


def read_ply(path):
    with open(path, "rb") as f:
        h = b""
        while not h.endswith(b"end_header\n"):
            h += f.readline()
        n = int([l for l in h.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        d = np.fromfile(f, dtype=rec, count=n)
    xyz = np.stack([d["x"], d["y"], d["z"]], 1).astype(np.float64)
    rgb = np.stack([d["r"], d["g"], d["b"]], 1)
    return xyz, rgb


def cell_spreads(vals_key, vals, min_pts=8):
    order = np.argsort(vals_key)
    k, v = vals_key[order], vals[order]
    bounds = np.flatnonzero(np.diff(k)) + 1
    return [float(np.percentile(g, 90) - np.percentile(g, 10))
            for g in np.split(v, bounds) if len(g) >= min_pts]


def floor_metrics(xyz, fh):
    slab = np.abs(fh) <= FLOOR_SLAB
    P, f = xyz[slab], fh[slab]
    out = {"n_floor_slab": int(slab.sum())}
    if len(P) < 100:
        out.update(thickness_med_cell_p90p10_m=None, thickness_p90_cell_m=None, cover_cells_2cm=0)
        return out
    key = np.floor(P[:,0]/CELL_THICK).astype(np.int64)*1000003 + np.floor(P[:,2]/CELL_THICK).astype(np.int64)
    spreads = cell_spreads(key, f)
    out["thickness_med_cell_p90p10_m"] = float(np.median(spreads)) if spreads else None
    out["thickness_p90_cell_m"] = float(np.percentile(spreads, 90)) if spreads else None
    out["n_thickness_cells"] = len(spreads)
    Q = P[np.abs(f) <= COVER_SLAB]
    cells = set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64), np.floor(Q[:,2]/CELL_COVER).astype(np.int64)))
    out["cover_cells_2cm"] = len(cells)
    out["cover_area_m2"] = round(len(cells)*CELL_COVER*CELL_COVER, 4)
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
        if hist[k] > best[2]:
            best = (d3, 0.5*(edges[k]+edges[k+1]), int(hist[k]))
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
    spreads = cell_spreads(key, s)
    out["thickness_med_cell_p90p10_m"] = float(np.median(spreads)) if spreads else None
    out["thickness_p90_cell_m"] = float(np.percentile(spreads, 90)) if spreads else None
    out["n_thickness_cells"] = len(spreads)
    return out


def parse_result(run_dir):
    log = os.path.join(run_dir, "run.log")
    if not os.path.exists(log): return None
    txt = open(log, errors="replace").read()
    m = re.search(r"^RESULT .*$", txt, re.M)
    if not m: return None
    res = {}
    for kv in m.group(0).split()[1:]:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try: res[k] = float(v) if "." in v else int(v)
            except ValueError: res[k] = v
    return res


def xsec_panel(u_arr, fd_mm, colors, W=1500, H=420, umin=None, umax=None, label=""):
    c = np.full((H, W, 3), 20, np.uint8)
    FMIN, FMAX = -60.0, 60.0
    if umin is None: umin, umax = float(u_arr.min()), float(u_arr.max())
    def px(u, fd):
        x = ((u - umin)/max(umax-umin, 1e-9)*(W-40)+20).astype(int)
        y = ((FMAX - fd)/(FMAX-FMIN)*(H-60)+30).astype(int)
        return x, y
    _, y1 = px(np.array([0.]), np.array([-15.])); _, y2 = px(np.array([0.]), np.array([-60.]))
    c[int(y1[0]):int(y2[0]), 20:W-20] = (45, 25, 25)          # double-floor band shading
    _, y0 = px(np.array([0.]), np.array([0.]))
    c[int(y0[0])-1:int(y0[0])+1, 20:W-20] = (90, 90, 90)      # production floor plane
    m = np.abs(fd_mm) <= 60
    x, y = px(u_arr[m], fd_mm[m])
    cols = colors[m]
    ok = (x >= 1) & (x < W-1) & (y >= 1) & (y < H-1)
    for xi, yi, ci in zip(x[ok], y[ok], cols[ok]):
        c[yi-1:yi+2, xi-1:xi+2] = ci
    return c, umin, umax


def annotate(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((28, 6), text, fill=(230, 230, 230))
    return np.asarray(im)


def main():
    from PIL import Image
    planes = {}
    for cap in ("cap50", "cap51"):
        gm = json.load(open(f"{D}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17/ghost_mask.json"))
        planes[cap] = (np.array(gm["plane_n"], float), float(gm["plane_d"]))

    caps = {}
    for name in sorted(os.listdir(RUNS)):
        run_dir = os.path.join(RUNS, name)
        ply = os.path.join(run_dir, "replay_finalize.ply")
        if not os.path.isdir(run_dir) or not os.path.exists(ply): continue
        cap = name.split("_")[0]
        arm = name[len(cap)+1:]
        pn, pd = planes[cap]
        xyz, rgb = read_ply(ply)
        fh = xyz @ pn + pd
        fl = floor_metrics(xyz, fh)
        dwall, woff = fit_dominant_wall(xyz, fh, pn)
        wl = wall_metrics(xyz, fh, dwall, woff, pn)
        # floor-mode sanity under the fixed plane
        near = fh[np.abs(fh) <= 0.10]
        hist, edges = np.histogram(near, bins=np.arange(-0.10, 0.1005, 0.005))
        mode_mm = round(1000*0.5*(edges[int(np.argmax(hist))]+edges[int(np.argmax(hist))+1]), 1)
        rec = {
            "run": name, "arm": arm, "n_points": int(len(xyz)),
            "fixed_plane": {"n": [round(v, 6) for v in pn], "d": round(pd, 6)},
            "floor_mode_mm_fixed": mode_mm,
            "band_dblfloor": int(((fh >= DBL_BAND[0]) & (fh < DBL_BAND[1])).sum()),
            "band_ghost_2045": int(((fh >= GHOST_BAND[0]) & (fh < GHOST_BAND[1])).sum()),
            "below_floor": int((fh < BELOW_FLOOR).sum()),
            "floor": fl, "wall_proxy": wl,
            "result": parse_result(run_dir),
        }
        rec["band_frac_pct"] = round(100.0*rec["band_dblfloor"]/max(rec["n_points"], 1), 3)
        caps.setdefault(cap, {})[arm] = rec
        print(f"{name}: n={rec['n_points']} mode={mode_mm}mm band={rec['band_dblfloor']} "
              f"({rec['band_frac_pct']}%) ghost2045={rec['band_ghost_2045']} below={rec['below_floor']} "
              f"thick_med={fl.get('thickness_med_cell_p90p10_m')} cover={fl.get('cover_cells_2cm')}")

    summary = {}
    for cap, arms in caps.items():
        offs = {a: r for a, r in arms.items() if a.startswith("off")}
        med = lambda f: float(np.median([f(r) for r in offs.values()]))
        off_med = {
            "band_dblfloor_median": med(lambda r: r["band_dblfloor"]),
            "band_runs": {a: r["band_dblfloor"] for a, r in offs.items()},
            "band_ghost_2045_median": med(lambda r: r["band_ghost_2045"]),
            "ghost_runs": {a: r["band_ghost_2045"] for a, r in offs.items()},
            "n_points_median": med(lambda r: r["n_points"]),
            "thick_med_median": med(lambda r: r["floor"]["thickness_med_cell_p90p10_m"]),
            "thick_p90_median": med(lambda r: r["floor"]["thickness_p90_cell_m"]),
            "cover_median": med(lambda r: r["floor"]["cover_cells_2cm"]),
            "wall_thick_med_median": med(lambda r: (r["wall_proxy"] or {}).get("thickness_med_cell_p90p10_m") or np.nan),
            "below_floor_median": med(lambda r: r["below_floor"]),
            "reproj_median": med(lambda r: r["result"]["mean_reproj_px"]),
            "n_reg": sorted({r["result"]["n_reg"] for r in offs.values()}),
        }
        med_band = off_med["band_dblfloor_median"]
        off_med["rep_off_run"] = min(offs.values(), key=lambda r: abs(r["band_dblfloor"]-med_band))["run"]
        deltas = {}
        for a, r in arms.items():
            if a.startswith("off"): continue
            w = (r["wall_proxy"] or {}).get("thickness_med_cell_p90p10_m")
            deltas[a] = {
                "band_delta_pct": round(100*(r["band_dblfloor"]/max(med_band, 1e-9)-1), 2),
                "ghost2045_delta_pct": round(100*(r["band_ghost_2045"]/max(off_med["band_ghost_2045_median"], 1e-9)-1), 2),
                "points_delta_pct": round(100*(r["n_points"]/off_med["n_points_median"]-1), 2),
                "thick_med_delta_pct": round(100*(r["floor"]["thickness_med_cell_p90p10_m"]/off_med["thick_med_median"]-1), 2) if r["floor"]["thickness_med_cell_p90p10_m"] else None,
                "cover_delta_cells": int(r["floor"]["cover_cells_2cm"]-off_med["cover_median"]),
                "cover_delta_pct": round(100*(r["floor"]["cover_cells_2cm"]/off_med["cover_median"]-1), 2),
                "wall_thick_delta_pct": round(100*(w/off_med["wall_thick_med_median"]-1), 2) if w and off_med["wall_thick_med_median"] == off_med["wall_thick_med_median"] else None,
                "below_floor": r["below_floor"],
                "n_reg": r["result"].get("n_reg"), "reproj": r["result"].get("mean_reproj_px"),
            }
        summary[cap] = {"fixed_plane_src": "device_full_pull_2026-07-17/ghost_mask.json",
                        "off_median": off_med, "arm_deltas": deltas}

        # 3-panel fixed-frame cross-section: off vs conflict_mv vs conflict_mv_owner
        pn, pd = planes[cap]
        u_ax = np.cross(pn, np.array([0., 0., 1.])); u_ax /= np.linalg.norm(u_ax)
        rep = off_med["rep_off_run"]
        panels, extents = [], None
        for nm, lab in [(rep, f"{cap} OFF ({rep}) — fixed production plane"),
                        (f"{cap}_conflict_mv", f"{cap} conflict_mv"),
                        (f"{cap}_conflict_mv_owner", f"{cap} conflict_mv_owner")]:
            xyz_i, rgb_i = read_ply(f"{RUNS}/{nm}/replay_finalize.ply")
            fh_i = (xyz_i @ pn + pd)*1000
            if extents is None:
                p, umin, umax = xsec_panel(xyz_i @ u_ax, fh_i, rgb_i)
                extents = (umin, umax)
            else:
                p, _, _ = xsec_panel(xyz_i @ u_ax, fh_i, rgb_i, umin=extents[0], umax=extents[1])
            panels.append(annotate(p, lab))
        gap = np.full((24, panels[0].shape[1], 3), 40, np.uint8)
        stacked = np.concatenate([panels[0], gap, panels[1], gap, panels[2]], 0)
        Image.fromarray(stacked).save(f"{OUT}/xsec_fixed_{cap}.png")
        print(f"[{cap}] fixed-frame cross-section saved")

    json.dump({"caliber": "E8 constants, FIXED production plane per cap",
               "runs": caps, "summary": summary},
              open(f"{OUT}/shell_metrics_fixed.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
