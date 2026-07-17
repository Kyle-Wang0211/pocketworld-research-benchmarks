#!/usr/bin/env python3
"""Before(union)/after(median) comparison + true-color top-down renders with a
zoomed chair/treadmill ROI. Colorize is read straight from the PLYs (already the
pinned cross-view-median / round production colors)."""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

OUT = ("/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/"
       "pocketworld-repro-contract-20260714/experiments/u3_merge_prototypes_2026-07-18/05_median_fusion/")

# Chair/treadmill flattened-false-positive ROI (top-down X-Z), lower-right object.
ROI = dict(X0=0.25, X1=1.05, Z0=-1.70, Z1=-0.55)


def load_ply(path):
    xs, ys, zs, r, g, b = [], [], [], [], [], []
    with open(path) as f:
        hdr = True
        for line in f:
            if hdr:
                if line.startswith("end_header"):
                    hdr = False
                continue
            t = line.split()
            xs.append(float(t[0])); ys.append(float(t[1])); zs.append(float(t[2]))
            r.append(int(t[3])); g.append(int(t[4])); b.append(int(t[5]))
    return (np.array(xs), np.array(ys), np.array(zs),
            np.column_stack([r, g, b]).astype(np.int64))


ux, uy, uz, urgb = load_ply(OUT + "union_baseline.ply")
fx, fy, fz, frgb = load_ply(OUT + "median_fusion.ply")


def in_roi(x, z):
    return (x >= ROI["X0"]) & (x <= ROI["X1"]) & (z >= ROI["Z0"]) & (z <= ROI["Z1"])


def is_false_positive(rgb):
    """Chair/treadmill = blue-grey / cool desaturated; wood floor = warm brown
    (red clearly dominant). Flag points that are NOT warm-brown: blue channel not
    much below red (b >= r - 8) -> greys and blues. This isolates the flattened
    object smear from the surrounding wood floor."""
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    return b >= (r - 8)


um = in_roi(ux, uz)
fm = in_roi(fx, fz)
u_fp = um & is_false_positive(urgb)
f_fp = fm & is_false_positive(frgb)

# "Good region" = floor outside ROI.
u_good = ~um
f_good = ~fm

stats = {
    "roi_box_xz": ROI,
    "union_total": int(len(ux)),
    "median_total": int(len(fx)),
    "total_reduction_frac": 1 - len(fx) / len(ux),
    "roi_union_points": int(um.sum()),
    "roi_median_points": int(fm.sum()),
    "roi_reduction_frac": 1 - fm.sum() / max(um.sum(), 1),
    "roi_falsepos_union": int(u_fp.sum()),
    "roi_falsepos_median": int(f_fp.sum()),
    "roi_falsepos_reduction_frac": 1 - f_fp.sum() / max(u_fp.sum(), 1),
    "good_region_union_points": int(u_good.sum()),
    "good_region_median_points": int(f_good.sum()),
    "good_region_retention_frac": f_good.sum() / max(u_good.sum(), 1),
    "roi_falsepos_share_union": u_fp.sum() / max(um.sum(), 1),
    "roi_falsepos_share_median": f_fp.sum() / max(fm.sum(), 1),
}
with open(OUT + "stats.json", "w") as f:
    json.dump(stats, f, indent=2, sort_keys=True)
print(json.dumps(stats, indent=2, sort_keys=True))


def draw_roi(ax):
    ax.add_patch(Rectangle((ROI["X0"], ROI["Z0"]), ROI["X1"]-ROI["X0"],
                           ROI["Z1"]-ROI["Z0"], fill=False, edgecolor="red",
                           lw=1.5, ls="--"))


# ---- Figure 1: full top-down before/after ----
fig, ax = plt.subplots(1, 2, figsize=(20, 11))
ax[0].scatter(ux, uz, c=urgb/255.0, s=5)
ax[0].set_title(f"BEFORE  union铺点  ({len(ux)} pts)", fontsize=14)
ax[1].scatter(fx, fz, c=frgb/255.0, s=5)
ax[1].set_title(f"AFTER  median fusion (>=5, single-pixel lock)  ({len(fx)} pts, -{stats['total_reduction_frac']*100:.1f}%)", fontsize=14)
for a in ax:
    a.set_aspect("equal"); a.invert_yaxis(); a.set_xlabel("X"); a.set_ylabel("Z")
    draw_roi(a)
plt.tight_layout()
plt.savefig(OUT + "viewer_topdown_before_after.png", dpi=95)
plt.close()
print("saved viewer_topdown_before_after.png")

# ---- Figure 2: ROI zoom before/after (chair/treadmill) ----
def roi_pts(x, z, rgb):
    m = in_roi(x, z)
    return x[m], z[m], rgb[m]/255.0

uxr, uzr, ucr = roi_pts(ux, uz, urgb)
fxr, fzr, fcr = roi_pts(fx, fz, frgb)
fig, ax = plt.subplots(1, 2, figsize=(18, 12))
ax[0].scatter(uxr, uzr, c=ucr, s=45)
ax[0].set_title(f"ROI chair/treadmill BEFORE ({len(uxr)} pts; {int(u_fp.sum())} non-wood FP)", fontsize=13)
ax[1].scatter(fxr, fzr, c=fcr, s=45)
ax[1].set_title(f"ROI chair/treadmill AFTER ({len(fxr)} pts; {int(f_fp.sum())} non-wood FP)", fontsize=13)
for a in ax:
    a.set_aspect("equal"); a.invert_yaxis(); a.set_xlabel("X"); a.set_ylabel("Z")
    a.set_xlim(ROI["X0"], ROI["X1"]); a.set_ylim(ROI["Z1"], ROI["Z0"])
plt.tight_layout()
plt.savefig(OUT + "viewer_roi_chair_before_after.png", dpi=95)
plt.close()
print("saved viewer_roi_chair_before_after.png")

# ---- Figure 3: ROI false-positive highlight before/after ----
fig, ax = plt.subplots(1, 2, figsize=(18, 12))
for a, (x, z, rgb, fp, title) in zip(
    ax,
    [(ux, uz, urgb, u_fp, "BEFORE"), (fx, fz, frgb, f_fp, "AFTER")]):
    m = in_roi(x, z)
    xm, zm, fpm = x[m], z[m], fp[m]
    a.scatter(xm[~fpm], zm[~fpm], c="0.6", s=40, label=f"wood/floor ({(~fpm).sum()})")
    a.scatter(xm[fpm], zm[fpm], c="red", s=55, label=f"non-wood FP ({fpm.sum()})")
    a.set_title(f"ROI FP highlight {title}", fontsize=13)
    a.set_aspect("equal"); a.invert_yaxis(); a.set_xlabel("X"); a.set_ylabel("Z")
    a.set_xlim(ROI["X0"], ROI["X1"]); a.set_ylim(ROI["Z1"], ROI["Z0"]); a.legend()
plt.tight_layout()
plt.savefig(OUT + "viewer_roi_falsepos_before_after.png", dpi=95)
plt.close()
print("saved viewer_roi_falsepos_before_after.png")
