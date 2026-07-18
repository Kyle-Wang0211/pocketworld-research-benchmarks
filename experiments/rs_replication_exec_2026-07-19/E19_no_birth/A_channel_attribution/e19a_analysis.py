#!/usr/bin/env python3.11
"""E19-A channel attribution — ghost-band composition: temporal_detail vs live/mapper.

Ruler = E13 step4 raw-frame caliber VERBATIM (fixed production plane from device
ghost_mask.json, NO re-anchor, no Sim3). Primary geometry source = points3D.bin
(float64, same as E13 step1 cache) so off_r2 numbers must reconcile bit-identical
with banked E13_dual_birth_inventory/analysis/step4_rulers.json before(off_r2).

Comparison frame: skip arm (AETHER_SKIP_TEMPORAL_DETAIL=1, one run per cap) vs
E9 off x3 MEDIAN per metric. envoff arms (same e19 exe, arm dormant) bound the
cross-binary drift vs the E9 baseline exe.

Attribution: ghost-band temporal_detail contribution = off_med - skip;
residual (live/mapper channels) = skip value. Detail cost = coverage/point deltas.
"""
import json
import os
import re
import sys

import numpy as np

D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{D}/experiments/rs_replication_exec_2026-07-19"
E19A = f"{EXP}/E19_no_birth/A_channel_attribution"
E9_RUNS = f"{EXP}/E9_birth_alias/runs"
sys.path.insert(0, f"{EXP}/E13_dual_birth_inventory/scripts")
from e13_lib import load_plane, read_points3d_bin_full, read_ply  # noqa: E402

TRUE_LO, TRUE_HI = -0.0075, 0.0125
GHOST_LO, GHOST_HI = -0.045, -0.020


def rulers(xyz, fh):
    """E13 step4_rulers_xsec.py rulers() verbatim."""
    cover_pts = xyz[np.abs(fh) <= 0.03]
    cover = len(set(zip(np.floor(cover_pts[:, 0] / 0.02).astype(np.int64),
                        np.floor(cover_pts[:, 2] / 0.02).astype(np.int64))))
    tf = xyz[(fh >= TRUE_LO) & (fh < TRUE_HI)]
    tf_cells = len(set(zip(np.floor(tf[:, 0] / 0.02).astype(np.int64),
                           np.floor(tf[:, 2] / 0.02).astype(np.int64))))
    gh = xyz[(fh >= GHOST_LO) & (fh < GHOST_HI)]
    gh_cells = len(set(zip(np.floor(gh[:, 0] / 0.02).astype(np.int64),
                           np.floor(gh[:, 2] / 0.02).astype(np.int64))))
    hist, edges = np.histogram(fh[np.abs(fh) <= 0.12] * 1000, bins=np.arange(-120, 120.5, 5))
    peak_true = int(hist[(edges[:-1] >= -5) & (edges[:-1] < 5)].max())
    peak_ghost = int(hist[(edges[:-1] >= -45) & (edges[:-1] < -15)].max())
    return {
        "n": int(len(xyz)),
        "true_floor_peak": int(((fh >= TRUE_LO) & (fh < TRUE_HI)).sum()),
        "ghost_band": int(((fh >= GHOST_LO) & (fh < GHOST_HI)).sum()),
        "mid_fat": int(((fh >= -0.045) & (fh < -0.010)).sum()),
        "above_6095": int(((fh >= 0.060) & (fh < 0.095)).sum()),
        "below_m10": int((fh < -0.100).sum()),
        "cover_raw_2cm": int(cover),
        "true_floor_cells_2cm": int(tf_cells),
        "ghost_band_cells_2cm": int(gh_cells),
        "hist_peak_true_per5mm": peak_true,
        "hist_peak_ghost_per5mm": peak_ghost,
        "bimodality_contrast(true/ghost)": round(peak_true / max(peak_ghost, 1), 3),
    }


def parse_result(run_dir):
    txt = open(os.path.join(run_dir, "run.log"), errors="replace").read()
    m = re.search(r"^RESULT .*$", txt, re.M)
    if not m:
        return None
    res = {}
    for kv in m.group(0).split()[1:]:
        if "=" in kv:
            k, v = kv.split("=", 1)
            try:
                res[k] = float(v) if "." in v else int(v)
            except ValueError:
                res[k] = v
    return res


def parse_err_telemetry(run_dir):
    txt = open(os.path.join(run_dir, "run.err"), errors="replace").read()
    out = {"skip_arm_log_hits": txt.count("e19-skip-temporal-detail")}
    m = re.findall(r"finalize worker: .*temporal=(\d+)ms", txt)
    if m:
        out["temporal_ms"] = int(m[-1])
    out["assert_red_line"] = bool(re.search(r"must not contain duplicate matches|THROW_CHECK_LE", txt))
    return out


def load_run(run_dir):
    _, xyz, _, _, _ = read_points3d_bin_full(os.path.join(run_dir, "points3D.bin"))
    return xyz


def xsec_panel(u_arr, fd_mm, colors, W=1500, H=420, umin=None, umax=None):
    c = np.full((H, W, 3), 20, np.uint8)
    FMIN, FMAX = -60.0, 60.0
    if umin is None:
        umin, umax = float(u_arr.min()), float(u_arr.max())

    def px(u, fd):
        x = ((u - umin) / max(umax - umin, 1e-9) * (W - 40) + 20).astype(int)
        y = ((FMAX - fd) / (FMAX - FMIN) * (H - 60) + 30).astype(int)
        return x, y

    _, y1 = px(np.array([0.]), np.array([-15.]))
    _, y2 = px(np.array([0.]), np.array([-60.]))
    c[int(y1[0]):int(y2[0]), 20:W - 20] = (45, 25, 25)
    _, y0 = px(np.array([0.]), np.array([0.]))
    c[int(y0[0]) - 1:int(y0[0]) + 1, 20:W - 20] = (90, 90, 90)
    m = np.abs(fd_mm) <= 60
    x, y = px(u_arr[m], fd_mm[m])
    cols = colors[m]
    ok = (x >= 1) & (x < W - 1) & (y >= 1) & (y < H - 1)
    for xi, yi, ci in zip(x[ok], y[ok], cols[ok]):
        c[yi - 1:yi + 2, xi - 1:xi + 2] = ci
    return c, umin, umax


def annotate(img, text):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((28, 6), text, fill=(235, 235, 235))
    return np.asarray(im)


def main():
    from PIL import Image
    banked = json.load(open(f"{EXP}/E13_dual_birth_inventory/analysis/step4_rulers.json"))
    out = {"caliber": "E13 step4 raw production frame verbatim (fixed plane, no re-anchor); "
                      "geometry = points3D.bin float64; skip arm 1-run vs E9 off x3 median"}
    for cap in ("cap51", "cap50"):
        pn, pd = load_plane(cap)
        rec = {"runs": {}}

        offs = {}
        for r in ("off_r1", "off_r2", "off_r3"):
            rd = f"{E9_RUNS}/{cap}_{r}"
            xyz = load_run(rd)
            fh = xyz @ pn + pd
            offs[r] = rulers(xyz, fh)
            offs[r]["result"] = parse_result(rd)
            rec["runs"][r] = offs[r]

        # reconciliation guard vs banked E13 off_r2 numbers
        b = banked[cap]["before(off_r2)"]
        mine = offs["off_r2"]
        mismatch = {k: (mine[k], b[k]) for k in b if k in mine and mine[k] != b[k]}
        rec["reconcile_off_r2_vs_E13_banked"] = "BIT-IDENTICAL" if not mismatch else {"MISMATCH": mismatch}

        arms = {}
        for arm in ("skip_td", "e19_envoff"):
            rd = f"{E19A}/runs/{cap}_{arm}"
            if not os.path.exists(os.path.join(rd, "points3D.bin")):
                arms[arm] = None
                continue
            xyz = load_run(rd)
            fh = xyz @ pn + pd
            a = rulers(xyz, fh)
            a["result"] = parse_result(rd)
            a["err_telemetry"] = parse_err_telemetry(rd)
            arms[arm] = a
            rec["runs"][arm] = a

        keys = ("n", "true_floor_peak", "ghost_band", "mid_fat", "above_6095", "below_m10",
                "cover_raw_2cm", "true_floor_cells_2cm", "ghost_band_cells_2cm",
                "hist_peak_true_per5mm", "hist_peak_ghost_per5mm")
        off_med = {k: float(np.median([offs[r][k] for r in offs])) for k in keys}
        off_med["bimodality_contrast(true/ghost)"] = round(
            off_med["hist_peak_true_per5mm"] / max(off_med["hist_peak_ghost_per5mm"], 1), 3)
        off_med["spread"] = {k: sorted(offs[r][k] for r in offs) for k in
                             ("n", "ghost_band", "cover_raw_2cm", "true_floor_peak")}
        rec["off_x3_median"] = off_med

        for arm, a in arms.items():
            if a is None:
                continue
            rec[f"{arm}_vs_off_med"] = {
                k: {"off_med": off_med[k], arm: a[k],
                    "delta": round(a[k] - off_med[k], 1),
                    "delta_pct": round(100 * (a[k] / max(off_med[k], 1e-9) - 1), 2)}
                for k in keys}
            rec[f"{arm}_vs_off_med"]["bimodality_contrast"] = {
                "off_med": off_med["bimodality_contrast(true/ghost)"],
                arm: a["bimodality_contrast(true/ghost)"]}

        if arms.get("skip_td"):
            s = arms["skip_td"]
            gb_off, gb_skip = off_med["ghost_band"], s["ghost_band"]
            rec["ATTRIBUTION"] = {
                "ghost_band_off_med": gb_off,
                "ghost_band_skip": gb_skip,
                "ghost_band_td_contribution": round(gb_off - gb_skip, 1),
                "ghost_band_td_contribution_pct_of_band": round(100 * (gb_off - gb_skip) / max(gb_off, 1e-9), 2),
                "ghost_band_residual_live_mapper": gb_skip,
                "ghost_cells_td_contribution": round(off_med["ghost_band_cells_2cm"] - s["ghost_band_cells_2cm"], 1),
                "detail_cost_points": round(off_med["n"] - s["n"], 1),
                "detail_cost_cover_cells_2cm": round(off_med["cover_raw_2cm"] - s["cover_raw_2cm"], 1),
                "detail_cost_true_floor_cells": round(off_med["true_floor_cells_2cm"] - s["true_floor_cells_2cm"], 1),
                "exchange_ratio_ghost_removed_per_cover_cell_lost":
                    round((gb_off - gb_skip) / max(off_med["cover_raw_2cm"] - s["cover_raw_2cm"], 1e-9), 2),
            }
        out[cap] = rec

        # cross-section: off_r2 vs skip_td (same u extent, same gauge, colors = each run's ply)
        if arms.get("skip_td"):
            panels, ext = [], None
            for nm, rd, lab in ((f"{cap}_off_r2", f"{E9_RUNS}/{cap}_off_r2",
                                 f"{cap} OFF (off_r2, raw production frame) band=[-60,-15)mm shaded"),
                                (f"{cap}_skip_td", f"{E19A}/runs/{cap}_skip_td",
                                 f"{cap} SKIP temporal_detail (E19-A arm)")):
                xyz_p, rgb_p = read_ply(os.path.join(rd, "replay_finalize.ply"))
                fh_p = xyz_p @ pn + pd
                u_ax = np.cross(pn, np.array([0., 0., 1.]))
                u_ax /= np.linalg.norm(u_ax)
                if ext is None:
                    p, umin, umax = xsec_panel(xyz_p @ u_ax, fh_p * 1000, rgb_p)
                    ext = (umin, umax)
                else:
                    p, _, _ = xsec_panel(xyz_p @ u_ax, fh_p * 1000, rgb_p, umin=ext[0], umax=ext[1])
                panels.append(annotate(p, lab))
            gap = np.full((24, panels[0].shape[1], 3), 40, np.uint8)
            Image.fromarray(np.concatenate([panels[0], gap, panels[1]], 0)).save(
                f"{E19A}/analysis/xsec_e19a_{cap}.png")
            print(f"[{cap}] cross-section saved")

    json.dump(out, open(f"{E19A}/analysis/e19a_metrics.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
