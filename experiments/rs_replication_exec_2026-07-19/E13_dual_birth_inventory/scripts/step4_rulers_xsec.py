#!/usr/bin/env python3.11
"""E13 step4 — production raw-frame rulers before/after + cross sections + PLYs.

Ruler = E12 raw_frame_forensics caliber verbatim (production plane from device
ghost_mask.json, NO re-anchor; verified bit-identical vs banked numbers in
step0). Also: per-band 2cm cell coverage (true-floor band separately),
histogram peak heights (bimodality contrast), diff/after PLY exports (colors
row-inherited from E9 replay_finalize_truecolor.ply, same gauge, no Sim3).
"""
import json
import sys

import numpy as np

sys.path.insert(0, "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E13_dual_birth_inventory/scripts")
from e13_lib import DEVICE_PLY, E13, E9_RUNS, OFF_RUN, load_plane, read_ply, write_ply

TRUE_LO, TRUE_HI = -0.0075, 0.0125
GHOST_LO, GHOST_HI = -0.045, -0.020


def rulers(xyz, fh):
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
    peak_true = int(hist[(edges[:-1] >= -5) & (edges[:-1] < 5)].max())  # bins [-5,0) [0,5)
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
    out = {}
    for cap in ("cap51", "cap50"):
        z = np.load(f"{E13}/analysis/step1_cache_{cap}.npz")
        xyz, fh = z["xyz"], z["fh"]
        s = np.load(f"{E13}/analysis/settlement_{cap}_main.npz")
        alive = s["alive"]
        pn, pd = load_plane(cap)

        # colors: row-inherited from E9 truecolor export (same row order as points3D.bin)
        txyz, trgb = read_ply(f"{OFF_RUN[cap]}/replay_finalize_truecolor.ply")
        assert len(txyz) == len(xyz), "truecolor row mismatch"
        assert np.abs(txyz - xyz).max() < 1e-5, "truecolor xyz mismatch"

        rec = {"off_x3_median_banked": "see E12 raw_frame_forensics.json"}
        rec["before(off_r2)"] = rulers(xyz, fh)
        rec["after(settled)"] = rulers(xyz[alive], fh[alive])
        # device production cloud reference
        dxyz, _ = read_ply(DEVICE_PLY[cap])
        dfh = dxyz @ pn + pd
        rec["DEVICE"] = rulers(dxyz, dfh)
        b, a = rec["before(off_r2)"], rec["after(settled)"]
        rec["delta_pct"] = {k: round(100 * (a[k] / max(b[k], 1e-9) - 1), 2)
                           for k in ("n", "true_floor_peak", "ghost_band", "mid_fat",
                                     "cover_raw_2cm", "true_floor_cells_2cm", "ghost_band_cells_2cm")}
        out[cap] = rec

        # after ply (truecolor) + diff ply
        write_ply(f"{E13}/analysis/e13_after_{cap}.ply", xyz[alive], trgb[alive])
        diff_rgb = np.full((len(xyz), 3), 120, np.uint8)
        diff_rgb[~alive] = (255, 40, 40)
        winners = np.unique(s["kills_winner"])
        diff_rgb[winners] = (40, 255, 60)
        write_ply(f"{E13}/analysis/e13_diff_{cap}.ply", xyz, diff_rgb)

        # cross-section off vs after (same u extent, same gauge)
        u_ax = np.cross(pn, np.array([0., 0., 1.]))
        u_ax /= np.linalg.norm(u_ax)
        p1, umin, umax = xsec_panel(xyz @ u_ax, fh * 1000, trgb)
        p1 = annotate(p1, f"{cap} OFF (off_r2, production raw frame)  band=[-60,-15)mm shaded")
        p2, _, _ = xsec_panel(xyz[alive] @ u_ax, fh[alive] * 1000, trgb[alive], umin=umin, umax=umax)
        p2 = annotate(p2, f"{cap} E13 settled (kills={int((~alive).sum())}, poses+positions frozen)")
        kills_only = ~alive
        p3, _, _ = xsec_panel(xyz[kills_only] @ u_ax, fh[kills_only] * 1000,
                              np.tile(np.array([255, 40, 40], np.uint8), (int(kills_only.sum()), 1)),
                              umin=umin, umax=umax)
        p3 = annotate(p3, f"{cap} killed losers only (red)")
        gap = np.full((24, p1.shape[1], 3), 40, np.uint8)
        Image.fromarray(np.concatenate([p1, gap, p2, gap, p3], 0)).save(f"{E13}/analysis/xsec_e13_{cap}.png")
        print(f"[{cap}] rulers+xsec+ply done")
    json.dump(out, open(f"{E13}/analysis/step4_rulers.json", "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
