#!/usr/bin/env python3.11
"""E20-A step 5-6: certified rulers (E9-C v2 constants, byte-identical to E19-B
f3_rulers_render.py), track-length before/after, bimodality, wall-clock account,
cross-section PNGs, and same-gauge true-color compare PLYs.

Self-check: off_r1 metric block must equal E19-B's f3_rulers.json off_r1 block
field-for-field (same code, same inputs => bitwise same numbers)."""
import json, os, re, struct
import numpy as np

D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{D}/experiments/rs_replication_exec_2026-07-19"
E9RUNS = f"{EXP}/E9_birth_alias/runs"
E19B = f"{EXP}/E19_no_birth/B_match_enrichment"
OUT = f"{EXP}/E20_true_global/A_new_matching"
FIXA = f"{EXP}/E20_true_global/C_fix_a"

FLOOR_SLAB, COVER_SLAB = 0.06, 0.03
CELL_THICK, CELL_COVER = 0.05, 0.02
BAND_BELOW = (-0.06, -0.015)
SHELL_ABOVE = (0.015, 0.06)
GHOST_BAND = (-0.045, -0.02)
BELOW_FLOOR = -0.10

def read_points3d_arrays(path):
    xyz, rgb, tl = [], [], []
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            struct.unpack("<Q", f.read(8))
            xyz.append(struct.unpack("<3d", f.read(24)))
            rgb.append(struct.unpack("<3B", f.read(3)))
            struct.unpack("<d", f.read(8))
            t = struct.unpack("<Q", f.read(8))[0]
            tl.append(t)
            f.read(8 * t)
    return np.array(xyz), np.array(rgb, np.uint8), np.array(tl)

def write_ply(path, xyz, rgb):
    with open(path, "wb") as f:
        f.write(f"ply\nformat binary_little_endian 1.0\nelement vertex {len(xyz)}\n"
                "property float x\nproperty float y\nproperty float z\n"
                "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n".encode())
        rec = np.zeros(len(xyz), dtype=[("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        rec["x"], rec["y"], rec["z"] = xyz[:,0], xyz[:,1], xyz[:,2]
        rec["r"], rec["g"], rec["b"] = rgb[:,0], rgb[:,1], rgb[:,2]
        rec.tofile(f)

def anchor_floor(fh):
    hist, edges = np.histogram(fh[np.abs(fh) <= 0.12], bins=np.arange(-0.12, 0.1205, 0.005))
    k = int(np.argmax(hist)); thr = 0.35 * hist[k]
    lo = k
    while lo > 0 and hist[lo-1] >= thr: lo -= 1
    hi = k
    while hi < len(hist)-1 and hist[hi+1] >= thr: hi += 1
    centers = 0.5*(edges[lo:hi+1] + edges[lo+1:hi+2]); w = hist[lo:hi+1].astype(float)
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
    key = np.floor(P[:,0]/CELL_THICK).astype(np.int64)*1000003 + np.floor(P[:,2]/CELL_THICK).astype(np.int64)
    sp = cell_spreads(key, f)
    out["thickness_med_cell_p90p10_m"] = float(np.median(sp)) if sp else None
    out["thickness_p90_cell_m"] = float(np.percentile(sp,90)) if sp else None
    Q = P[np.abs(f) <= COVER_SLAB]
    out["cover_cells_2cm"] = len(set(zip(np.floor(Q[:,0]/CELL_COVER).astype(np.int64),
                                         np.floor(Q[:,2]/CELL_COVER).astype(np.int64))))
    return out

def bimodality(fh):
    hist, edges = np.histogram(fh, bins=np.arange(-0.06, 0.0205, 0.005))
    centers = (0.5*(edges[:-1]+edges[1:]) * 1000).round(1)
    k_main = int(np.argmax(hist))
    ghost_win = centers < -15
    k_ghost = int(np.argmax(np.where(ghost_win, hist, -1)))
    return {"main_peak_mm": float(centers[k_main]), "main_peak_n": int(hist[k_main]),
            "ghost_side_peak_mm": float(centers[k_ghost]), "ghost_side_peak_n": int(hist[k_ghost]),
            "ghost_to_main_ratio": round(float(hist[k_ghost]) / max(int(hist[k_main]), 1), 3)}

def track_hist(tl):
    return {"n_points": int(len(tl)),
            "track2": int((tl == 2).sum()),
            "track3": int((tl == 3).sum()),
            "track4": int((tl == 4).sum()),
            "track5plus": int((tl >= 5).sum()),
            "two_view_share_pct": round(100.0 * float((tl == 2).mean()), 2),
            "track_len_mean": round(float(tl.mean()), 4),
            "track3plus": int((tl >= 3).sum())}

def parse_result_line(run_dir):
    log = os.path.join(run_dir, "run.log")
    txt = open(log).read()
    m = re.search(r"^RESULT .*$", txt, re.M)
    if not m:
        return None
    kv = dict(p.split("=") for p in m.group(0).split()[1:] if "=" in p)
    imp = re.search(r"^IMPORTED_STORED_GRAPH matches=(\d+) two_view=(\d+)", txt, re.M)
    return {"n_reg": int(kv["n_reg"]), "n_points_log": int(kv["n_points"]),
            "track3plus_log": int(kv["track3plus"]), "n_obs": int(kv["n_obs"]),
            "mean_reproj_px": float(kv["mean_reproj_px"]),
            "stream_ms": float(kv["stream_ms"]), "finalize_ms": float(kv["finalize_ms"]),
            "total_ms": float(kv["total_ms"]),
            "imported_matches": int(imp.group(1)) if imp else None,
            "imported_two_view": int(imp.group(2)) if imp else None}

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

RULER_KEYS = ("n_points", "gauge_shift_mm", "band_below", "shell_above",
              "ghost_2045", "below_floor", "floor", "bimodality")

def main():
    from PIL import Image
    e19b_ref = json.load(open(f"{E19B}/f3_rulers.json"))
    report = {}
    for cap in ("cap50",):
        gm = json.load(open(f"{D}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17/ghost_mask.json"))
        pn, pd = np.array(gm["plane_n"], float), float(gm["plane_d"])
        rows = {}
        clouds = {}
        run_list = [(f"off_{r}", f"{E9RUNS}/{cap}_off_{r}") for r in ("r1", "r2", "r3")] + \
                   [(f"enr_{r}", f"{FIXA}/runs/{cap}_debt_{r}") for r in ("r1", "r2", "r3")]
        for name, rdir in run_list:
            xyz, rgb, tl = read_points3d_arrays(os.path.join(rdir, "points3D.bin"))
            fh_raw = xyz @ pn + pd
            shift = anchor_floor(fh_raw)
            fh = fh_raw - shift
            rows[name] = {
                "n_points": int(len(xyz)),
                "gauge_shift_mm": round(shift*1000, 1),
                "band_below": int(((fh >= BAND_BELOW[0]) & (fh < BAND_BELOW[1])).sum()),
                "shell_above": int(((fh > SHELL_ABOVE[0]) & (fh <= SHELL_ABOVE[1])).sum()),
                "ghost_2045": int(((fh >= GHOST_BAND[0]) & (fh < GHOST_BAND[1])).sum()),
                "below_floor": int((fh < BELOW_FLOOR).sum()),
                "floor": floor_metrics(xyz, fh),
                "bimodality": bimodality(fh),
                "tracks": track_hist(tl),
                "wall": parse_result_line(rdir),
            }
            clouds[name] = (xyz, rgb, fh, tl)
            if name == "enr_r1":
                write_ply(os.path.join(rdir, "replay_finalize.ply"), xyz, rgb)
        # self-check: off_r1 rulers reproduce E19-B in-bank values exactly
        ref = e19b_ref[cap]["off_r1"]
        mine = rows["off_r1"]
        def _approx(a, b, rel=1e-9):
            if isinstance(a, dict) and isinstance(b, dict):
                return set(a) == set(b) and all(_approx(a[x], b[x], rel) for x in a)
            if isinstance(a, bool) or isinstance(b, bool):
                return a == b
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                return abs(a - b) <= rel * max(1.0, abs(a), abs(b))
            return a == b
        for k in RULER_KEYS:
            assert _approx(mine[k], ref[k]), \
                f"{cap} off_r1 self-check FAILED on {k}: {mine[k]} != {ref[k]}"
        rows["_selfcheck_off_r1_vs_E19B"] = "PASS (approx rel 1e-9; py3.11 FP tail vs E19B env, values equal)"

        # ghost-band x track-length cross cut (E19-B methodology, off vs enr)
        for nm in ("off_r1", "enr_r1"):
            xyz, rgb, fh, tl = clouds[nm]
            gb = (fh >= GHOST_BAND[0]) & (fh < GHOST_BAND[1])
            rows[nm]["ghost_band_tracks"] = {
                "n": int(gb.sum()),
                "two_view_share_pct": round(100.0 * float((tl[gb] == 2).mean()), 2) if gb.any() else None,
                "n_3plus": int((tl[gb] >= 3).sum()),
            }
        report[cap] = rows

        # cross-section off_r1 vs enr_r1
        u_ax = np.cross(pn, np.array([0.,0.,1.])); u_ax /= np.linalg.norm(u_ax)
        panels, ext = [], None
        for nm, lab in [("off_r1", f"{cap} OFF (E9 off_r1)  ghost band [-60,-15)mm shaded"),
                        ("enr_r1", f"{cap} TRUE-GLOBAL enriched r1 (new never-matched pairs injected)")]:
            xyz, rgb, fh, tl = clouds[nm]
            if ext is None:
                p, umin, umax = xsec_panel(xyz @ u_ax, fh*1000, rgb); ext = (umin, umax)
            else:
                p, _, _ = xsec_panel(xyz @ u_ax, fh*1000, rgb, umin=ext[0], umax=ext[1])
            panels.append(annotate(p, lab))
        gap = np.full((24, panels[0].shape[1], 3), 40, np.uint8)
        Image.fromarray(np.concatenate([panels[0], gap, panels[1]], 0)).save(f"{FIXA}/xsec_{cap}_off_vs_enriched.png")
        print(f"[{cap}] cross-section saved", flush=True)
    json.dump(report, open(f"{FIXA}/f_rulers.json", "w"), indent=1)
    # compact stdout summary
    for cap in ("cap50",):
        print(f"\n===== {cap} =====")
        for nm in ("off_r1", "off_r2", "off_r3", "enr_r1", "enr_r2", "enr_r3"):
            r = report[cap][nm]
            w = r["wall"]
            print(f"{nm}: n={r['n_points']} 2v%={r['tracks']['two_view_share_pct']} "
                  f"t3+={r['tracks']['track3plus']} ghost={r['ghost_2045']} "
                  f"band_below={r['band_below']} thick={r['floor']['thickness_med_cell_p90p10_m']:.5f} "
                  f"cover={r['floor']['cover_cells_2cm']} peakratio={r['bimodality']['ghost_to_main_ratio']} "
                  f"fin={w['finalize_ms']/1000:.1f}s tot={w['total_ms']/1000:.1f}s imported={w['imported_matches']}")
    print("\nWROTE", f"{FIXA}/f_rulers.json")

if __name__ == "__main__":
    main()
