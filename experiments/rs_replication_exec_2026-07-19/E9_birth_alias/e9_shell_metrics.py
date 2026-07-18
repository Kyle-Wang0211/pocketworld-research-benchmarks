#!/usr/bin/env python3.11
"""E9-B shell metrics over replay arm clouds (replay_finalize.ply per run).

Ruler caliber = E8 (byte-identical constants): FLOOR_SLAB 0.06, COVER_SLAB 0.03,
CELL_THICK 0.05, CELL_COVER 0.02, DBL_BAND (-0.06,-0.015), BELOW_FLOOR -0.10.

Floor frame is SELF-COMPUTED per run (replay-baseline caliber; the v1.1 anchors
3,917/6,880 belong to the delivery pipeline and are NOT comparable):
  y-mode histogram (E8 detect_floor_y, S1-identical) -> LSQ plane on |y-y0|<=1.5cm
  slab -> one refit round on |fh|<=1.5cm inliers -> fh = xyz@pn + pd (pn oriented +y).
Same self-calibration applied to every arm => single-variable A/B within the replay
family; no Sim3, no realignment (poses share the device-fed gauge).

Writes stats_e9.json + per-cap/arm cross-section PNGs into E9_birth_alias/analysis/.
"""
import json, os, re, sys
import numpy as np

E9 = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E9_birth_alias"
RUNS = f"{E9}/runs"
OUT = f"{E9}/analysis"
os.makedirs(OUT, exist_ok=True)

FLOOR_SLAB = 0.06
COVER_SLAB = 0.03
CELL_THICK = 0.05
CELL_COVER = 0.02
DBL_BAND = (-0.06, -0.015)
BELOW_FLOOR = -0.10
WALL_MIN_FH = 0.10
WALL_FIT_MIN_FH = 0.30
WALL_SLAB = 0.06


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


def detect_floor_y(xyz):  # E8/S1-identical
    y = xyz[:,1]
    lo, hi = np.percentile(y, [0.5, 99.5])
    bins = np.arange(lo, hi + 0.005, 0.005)
    hcount, edges = np.histogram(y, bins=bins)
    peak = np.argmax(hcount)
    y0 = 0.5*(edges[peak]+edges[peak+1])
    sel = np.abs(y - y0) <= 0.015
    return float(np.median(y[sel]))


def fit_floor_plane(xyz):
    """Self-computed floor frame: LSQ plane through the dominant y-slab, one refit."""
    y0 = detect_floor_y(xyz)
    sel = np.abs(xyz[:,1] - y0) <= 0.015
    P = xyz[sel]
    for _ in range(2):
        # plane y = a*x + b*z + c  (floor is near-horizontal in device gauge)
        A = np.column_stack([P[:,0], P[:,2], np.ones(len(P))])
        coef, *_ = np.linalg.lstsq(A, P[:,1], rcond=None)
        a, b, c = coef
        n = np.array([-a, 1.0, -b]); n /= np.linalg.norm(n)
        d = -c * n[1]
        fh_all = xyz @ n + d
        P = xyz[np.abs(fh_all) <= 0.015]
        if len(P) < 200: break
    return n, float(d), y0


def floor_metrics_fh(xyz, fh):
    slab = np.abs(fh) <= FLOOR_SLAB
    P, f = xyz[slab], fh[slab]
    out = {"n_floor_slab": int(slab.sum())}
    if len(P) < 100:
        out.update({"thickness_med_cell_p90p10_m": None, "thickness_p90_cell_m": None, "cover_cells_2cm": 0})
        return out
    cx = np.floor(P[:,0]/CELL_THICK).astype(np.int64)
    cz = np.floor(P[:,2]/CELL_THICK).astype(np.int64)
    key = cx * 1000003 + cz
    order = np.argsort(key)
    key_s, f_s = key[order], f[order]
    bounds = np.flatnonzero(np.diff(key_s)) + 1
    groups = np.split(f_s, bounds)
    spreads = [float(np.percentile(g,90) - np.percentile(g,10)) for g in groups if len(g) >= 8]
    out["thickness_med_cell_p90p10_m"] = float(np.median(spreads)) if spreads else None
    out["thickness_p90_cell_m"] = float(np.percentile(spreads,90)) if spreads else None
    out["n_thickness_cells"] = len(spreads)
    tight = np.abs(f) <= COVER_SLAB
    Q = P[tight]
    cells = set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64), np.floor(Q[:,2]/CELL_COVER).astype(np.int64)))
    out["cover_cells_2cm"] = len(cells)
    out["cover_area_m2"] = round(len(cells) * CELL_COVER * CELL_COVER, 4)
    return out


def fit_dominant_wall(xyz, fh, pn):  # E8 port
    P = xyz[fh > WALL_FIT_MIN_FH]
    if len(P) < 500: return None, None
    best = (None, None, -1)
    for ang in np.arange(0, 180, 1.0):
        t = np.radians(ang)
        d3 = np.array([np.cos(t), 0.0, np.sin(t)])
        d3 = d3 - (d3 @ pn) * pn
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
        out.update({"thickness_med_cell_p90p10_m": None, "thickness_p90_cell_m": None})
        return out
    w = np.cross(pn, d); w /= np.linalg.norm(w)
    ca = np.floor((P @ w)/CELL_THICK).astype(np.int64)
    cb = np.floor(f/CELL_THICK).astype(np.int64)
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


def xsec_panel(u_arr, fd_mm, colors, W=1500, H=520, umin=None, umax=None, band=True, label=""):
    c = np.full((H, W, 3), 20, np.uint8)
    FMIN, FMAX = -60.0, 60.0
    if umin is None: umin, umax = float(u_arr.min()), float(u_arr.max())
    def px(u, fd):
        x = ((u - umin) / max(umax - umin, 1e-9) * (W - 40) + 20).astype(int)
        y = ((FMAX - fd) / (FMAX - FMIN) * (H - 60) + 30).astype(int)
        return x, y
    _, y0 = px(np.array([0.0]), np.array([0.0])); y0 = int(y0[0])
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


def parse_result(run_dir):
    log = os.path.join(run_dir, "run.log")
    if not os.path.exists(log): return None
    res = {}
    txt = open(log, errors="replace").read()
    m = re.search(r"^RESULT .*$", txt, re.M)
    if not m: return None
    for kv in m.group(0).split()[1:]:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try: res[k] = float(v) if "." in v else int(v)
            except ValueError: res[k] = v
    # arm mechanism stat lines (glog goes to stderr -> run.err; scan both)
    err = os.path.join(run_dir, "run.err")
    txt2 = txt + ("\n" + open(err, errors="replace").read() if os.path.exists(err) else "")
    mech = [l for l in txt2.splitlines()
            if re.search(r"conflict.multiview|exact.site|site_birth|geometric.winner|site.owner|SITE_", l)]
    res["_mech_lines"] = mech[-12:]
    return res


def main():
    from PIL import Image
    caps = {}
    for name in sorted(os.listdir(RUNS)):
        run_dir = os.path.join(RUNS, name)
        ply = os.path.join(run_dir, "replay_finalize.ply")
        if not os.path.isdir(run_dir) or not os.path.exists(ply):
            print(f"skip {name} (no replay_finalize.ply)"); continue
        cap = name.split("_")[0]
        arm = name[len(cap)+1:]
        xyz, rgb = read_ply_xyzrgb(ply)
        pn, pd, y0 = fit_floor_plane(xyz)
        fh = xyz @ pn + pd
        fl = floor_metrics_fh(xyz, fh)
        dwall, woff = fit_dominant_wall(xyz, fh, pn)
        wl = wall_metrics(xyz, fh, dwall, woff, pn)
        rec = {
            "run": name, "arm": arm,
            "n_points": int(len(xyz)),
            "floor_y_mode": round(y0, 5),
            "plane_n": [round(v,6) for v in pn], "plane_d": round(pd,6),
            "band_dblfloor": int(((fh >= DBL_BAND[0]) & (fh < DBL_BAND[1])).sum()),
            "below_floor": int((fh < BELOW_FLOOR).sum()),
            "floor": fl, "wall_proxy": wl,
            "result": parse_result(run_dir),
        }
        rec["band_frac_pct"] = round(100.0*rec["band_dblfloor"]/max(rec["n_points"],1), 3)
        caps.setdefault(cap, {})[arm] = rec
        # cache slab for renders
        np.savez_compressed(f"{OUT}/fh_{name}.npz", fh=fh.astype(np.float32))
        print(f"{name}: n={rec['n_points']} band={rec['band_dblfloor']} ({rec['band_frac_pct']}%) "
              f"below={rec['below_floor']} thick_med={fl.get('thickness_med_cell_p90p10_m')} "
              f"thick_p90={fl.get('thickness_p90_cell_m')} cover={fl.get('cover_cells_2cm')}")

    # medians over off runs + renders off-median vs each ON arm
    summary = {}
    for cap, arms in caps.items():
        offs = {a: r for a, r in arms.items() if a.startswith("off")}
        if not offs: continue
        med_band = float(np.median([r["band_dblfloor"] for r in offs.values()]))
        # pick representative off run = the one with band closest to median
        rep_off = min(offs.values(), key=lambda r: abs(r["band_dblfloor"] - med_band))
        off_med = {
            "band_dblfloor_median": med_band,
            "band_runs": {a: r["band_dblfloor"] for a, r in offs.items()},
            "n_points_median": float(np.median([r["n_points"] for r in offs.values()])),
            "thick_med_median": float(np.median([r["floor"]["thickness_med_cell_p90p10_m"] for r in offs.values()])),
            "thick_p90_median": float(np.median([r["floor"]["thickness_p90_cell_m"] for r in offs.values()])),
            "cover_median": float(np.median([r["floor"]["cover_cells_2cm"] for r in offs.values()])),
            "rep_off_run": rep_off["run"],
        }
        deltas = {}
        for a, r in arms.items():
            if a.startswith("off"): continue
            deltas[a] = {
                "band_delta_pct": round(100.0*(r["band_dblfloor"]/max(off_med["band_dblfloor_median"],1e-9)-1.0), 2),
                "points_delta_pct": round(100.0*(r["n_points"]/off_med["n_points_median"]-1.0), 2),
                "thick_med_delta_pct": round(100.0*(r["floor"]["thickness_med_cell_p90p10_m"]/off_med["thick_med_median"]-1.0), 2) if r["floor"]["thickness_med_cell_p90p10_m"] else None,
                "cover_delta_cells": int(r["floor"]["cover_cells_2cm"] - off_med["cover_median"]),
                "n_reg": r["result"].get("n_reg") if r["result"] else None,
            }
        summary[cap] = {"off_median": off_med, "arm_deltas": deltas}

        # renders: off representative vs each arm, floor cross-section
        rep_name = rep_off["run"]
        xyz_o, rgb_o = read_ply_xyzrgb(f"{RUNS}/{rep_name}/replay_finalize.ply")
        fh_o = np.load(f"{OUT}/fh_{rep_name}.npz")["fh"].astype(float)
        pn_o = np.array(rep_off["plane_n"]);
        u_ax = np.cross(pn_o, np.array([0.0,0.0,1.0])); u_ax /= np.linalg.norm(u_ax)
        gap = np.full((30, 1500, 3), 40, np.uint8)
        for a, r in arms.items():
            if a.startswith("off"): continue
            name = r["run"]
            xyz_a, rgb_a = read_ply_xyzrgb(f"{RUNS}/{name}/replay_finalize.ply")
            fh_a = np.load(f"{OUT}/fh_{name}.npz")["fh"].astype(float)
            pA, umin, umax = xsec_panel(xyz_o @ u_ax, fh_o*1000, rgb_o)
            pB, _, _ = xsec_panel(xyz_a @ u_ax, fh_a*1000, rgb_a, umin=umin, umax=umax)
            Image.fromarray(np.concatenate([pA, gap, pB], 0)).save(
                f"{OUT}/ghost_crosssection_floor_{cap}_{a}.png")
        print(f"[{cap}] renders done")

    json.dump({"runs": caps, "summary": summary}, open(f"{OUT}/stats_e9.json", "w"), indent=1)
    print(json.dumps(summary, indent=1))

if __name__ == "__main__":
    main()
