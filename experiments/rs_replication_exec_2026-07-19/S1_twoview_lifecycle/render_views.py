#!/usr/bin/env python3.11
"""Same-gauge true-color side-by-side renders (baseline vs S1 caseA candidate) + diff maps.
Reads render_arrays.npz written by build_candidate.py. NO Sim3, NO realignment:
both clouds are in the identical production frame; identical axes/limits per view.
Views: top-down (X-Z) and elevation (X-Y, side view for thickness). Colors: production RGB.
Diff map: green = 2-view kept by unified rule, red = 2-view culled, gray = multiview/unrecovered.
Rescue map: blue = verified 2-view pairs passing rule but absent from production (NOT injected).
Usage: render_views.py cap50 cap51
"""
import numpy as np, sys, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))

def lims(a, pad=0.03):
    lo, hi = np.percentile(a, [0.5, 99.5])
    m = (hi-lo)*pad
    return lo-m, hi+m

def scatter(ax, x, y, c, s=0.35):
    ax.scatter(x, y, c=c, s=s, linewidths=0, rasterized=True)
    ax.set_facecolor("black")
    ax.set_aspect("equal")

def render_cap(cap):
    d = os.path.join(BASE, cap)
    z = np.load(os.path.join(d, "render_arrays.npz"))
    xyz, rgb = z["xyz"], z["rgb"].astype(float)/255.0
    keep = z["keep_mask"]; dif = z["dif_rgb"].astype(float)/255.0
    cull2 = z["cull2"]; keep2 = z["keep2"]; rescue = z["rescue"]
    y_floor = float(z["y_floor"])
    cand, cand_rgb = xyz[keep], rgb[keep]

    xl, zl, yl = lims(xyz[:,0]), lims(xyz[:,2]), lims(xyz[:,1])

    # ---- 1. true-color side-by-side, top-down (X-Z) and elevation (X-Y) ----
    fig, axes = plt.subplots(2, 2, figsize=(16, 14), facecolor="black")
    for ax, (P, C, title) in zip(axes[0], [(xyz, rgb, f"{cap} baseline (production) — top-down"),
                                           (cand, cand_rgb, f"{cap} S1 caseA candidate — top-down")]):
        scatter(ax, P[:,0], P[:,2], C)
        ax.set_xlim(xl); ax.set_ylim(zl)
        ax.set_title(title, color="white", fontsize=11)
    for ax, (P, C, title) in zip(axes[1], [(xyz, rgb, "baseline — elevation (X-Y, thickness view)"),
                                           (cand, cand_rgb, "candidate — elevation (X-Y, thickness view)")]):
        scatter(ax, P[:,0], P[:,1], C)
        ax.set_xlim(xl); ax.set_ylim(yl)
        ax.invert_yaxis()
        ax.axhline(y_floor, color="#00ffff", lw=0.4, alpha=0.5)
        ax.set_title(title, color="white", fontsize=11)
    for ax in axes.flat: ax.tick_params(colors="gray", labelsize=7)
    fig.suptitle(f"S1 2-view unified lifecycle — {cap} — SAME GAUGE (production poses, no Sim3); cyan line = detected floor",
                 color="white", fontsize=12)
    fig.tight_layout(rect=[0,0,1,0.97])
    p1 = os.path.join(d, f"compare_truecolor_{cap}.png")
    fig.savefig(p1, dpi=140, facecolor="black"); plt.close(fig)

    # ---- 2. diff map (verdict coloring) top-down + elevation, culled/kept drawn on top ----
    fig, axes = plt.subplots(1, 2, figsize=(16, 8), facecolor="black")
    order = np.concatenate([np.flatnonzero(~(keep2|cull2)), np.flatnonzero(keep2), np.flatnonzero(cull2)])
    for ax, (yy, ylim, name, inv) in zip(axes, [(xyz[:,2], zl, "top-down (X-Z)", False),
                                                (xyz[:,1], yl, "elevation (X-Y)", True)]):
        ax.scatter(xyz[order,0], yy[order], c=dif[order], s=np.where(cull2[order]|keep2[order], 1.6, 0.25),
                   linewidths=0, rasterized=True)
        ax.set_facecolor("black"); ax.set_aspect("equal")
        ax.set_xlim(xl); ax.set_ylim(ylim)
        if inv: ax.invert_yaxis(); ax.axhline(y_floor, color="#00ffff", lw=0.4, alpha=0.5)
        ax.set_title(f"{cap} verdict diff — {name}", color="white", fontsize=11)
        ax.tick_params(colors="gray", labelsize=7)
    fig.suptitle(f"green = 2-view KEPT by unified rule ({int(keep2.sum())})   red = 2-view CULLED ({int(cull2.sum())})   gray = multiview/unrecovered (kept)",
                 color="white", fontsize=12)
    fig.tight_layout(rect=[0,0,1,0.95])
    p2 = os.path.join(d, f"diff_verdict_{cap}.png")
    fig.savefig(p2, dpi=140, facecolor="black"); plt.close(fig)

    # ---- 3. rescue candidates overlay (top-down), NOT injected ----
    fig, ax = plt.subplots(figsize=(9, 8), facecolor="black")
    scatter(ax, xyz[:,0], xyz[:,2], "#555555", s=0.2)
    if len(rescue):
        ax.scatter(rescue[:,0], rescue[:,2], c="#00a0ff", s=1.2, linewidths=0, rasterized=True)
    ax.set_xlim(xl); ax.set_ylim(zl)
    ax.set_title(f"{cap} rescue candidates (blue, n={len(rescue)}): verified far/near 2-view pairs passing SAME rule,\nabsent from production cloud — reported only, NOT injected into candidate PLY",
                 color="white", fontsize=10)
    ax.tick_params(colors="gray", labelsize=7)
    fig.tight_layout()
    p3 = os.path.join(d, f"rescue_overlay_{cap}.png")
    fig.savefig(p3, dpi=140, facecolor="black"); plt.close(fig)

    # ---- 4. culled-points zoom: where did the 537/249 die? elevation crop around floor ----
    fig, ax = plt.subplots(figsize=(12, 6), facecolor="black")
    scatter(ax, xyz[:,0], xyz[:,1], "#444444", s=0.2)
    ax.scatter(xyz[keep2,0], xyz[keep2,1], c="#00dc00", s=2.0, linewidths=0)
    ax.scatter(xyz[cull2,0], xyz[cull2,1], c="#ff2828", s=3.0, linewidths=0)
    ax.set_xlim(xl); ax.set_ylim(y_floor+0.25, y_floor-0.25)
    ax.axhline(y_floor, color="#00ffff", lw=0.5, alpha=0.6)
    ax.set_title(f"{cap} floor band ±25cm elevation — red=culled 2-view, green=kept 2-view, cyan=floor", color="white", fontsize=11)
    ax.tick_params(colors="gray", labelsize=7)
    fig.tight_layout()
    p4 = os.path.join(d, f"floorband_culls_{cap}.png")
    fig.savefig(p4, dpi=140, facecolor="black"); plt.close(fig)

    print(cap, "->", p1, p2, p3, p4, sep="\n  ")

if __name__ == "__main__":
    for cap in (sys.argv[1:] or ["cap50", "cap51"]):
        render_cap(cap)
