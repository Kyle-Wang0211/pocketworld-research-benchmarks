#!/usr/bin/env python3
"""True-color before/after viewers for the off-plane depth-competition diagnostic.

BEFORE = frozen union accepted points (every scored cell born).
AFTER  = cells whose floor depth uniquely wins depth competition (pinned rule,
         margin 0.02); cells that lose become HOLES (an off-plane structure sits
         there). Colors are read straight from the frozen production PLY colors
         carried in the jsonl rows (no re-colorize)."""
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

DIR = Path(__file__).resolve().parent
ROI = dict(X0=0.25, X1=1.05, Z0=-1.70, Z1=-0.55)
RULE = "survives_pinned_0.02"

rows = [json.loads(l) for l in (DIR / "depth_competition.jsonl").read_text().splitlines()]
roi = [r for r in rows if r["population"] == "roi"]
clean = [r for r in rows if r["population"] == "clean"]


def arr(rs):
    x = np.array([r["xyz_m"][0] for r in rs])
    z = np.array([r["xyz_m"][2] for r in rs])
    c = np.array([r["rgb_u8"] for r in rs]) / 255.0
    fp = np.array([r["is_false_positive_color"] for r in rs])
    surv = np.array([r[RULE] for r in rs])
    return x, z, c, fp, surv


rx, rz, rc, rfp, rsurv = arr(roi)


def draw_roi(ax):
    ax.add_patch(Rectangle((ROI["X0"], ROI["Z0"]), ROI["X1"] - ROI["X0"],
                           ROI["Z1"] - ROI["Z0"], fill=False, edgecolor="red",
                           lw=1.5, ls="--"))


# ---- Figure 1: ROI true-color BEFORE (all) vs AFTER (survivors) ----
fig, ax = plt.subplots(1, 2, figsize=(18, 12))
ax[0].scatter(rx, rz, c=rc, s=45)
ax[0].set_title(f"chair ROI BEFORE  union铺点  ({len(rx)} pts, "
                f"{int(rfp.sum())} chair-color FP)", fontsize=13)
ax[1].scatter(rx[rsurv], rz[rsurv], c=rc[rsurv], s=45)
ax[1].set_title(f"chair ROI AFTER depth-competition survivors "
                f"({int(rsurv.sum())} pts, {int((rfp & rsurv).sum())} chair-color FP; "
                f"{int((~rsurv).sum())} holes)", fontsize=13)
for a in ax:
    a.set_aspect("equal"); a.invert_yaxis(); a.set_xlabel("X"); a.set_ylabel("Z")
    a.set_xlim(ROI["X0"], ROI["X1"]); a.set_ylim(ROI["Z1"], ROI["Z0"])
plt.tight_layout()
plt.savefig(DIR / "viewer_roi_truecolor_before_after.png", dpi=95)
plt.close()

# ---- Figure 2: ROI FP highlight + hole map ----
fig, ax = plt.subplots(1, 2, figsize=(18, 12))
# BEFORE: wood vs chair-color FP
ax[0].scatter(rx[~rfp], rz[~rfp], c="0.6", s=45, label=f"wood floor ({(~rfp).sum()})")
ax[0].scatter(rx[rfp], rz[rfp], c="tab:red", s=55, label=f"chair-color FP ({rfp.sum()})")
ax[0].set_title("chair ROI BEFORE: chair-color FP highlight", fontsize=13)
# AFTER: survivors (grey) vs holes (X), FP survivors emphasised
ax[1].scatter(rx[rsurv], rz[rsurv], c="0.6", s=45, label=f"survived ({rsurv.sum()})")
ax[1].scatter(rx[~rsurv], rz[~rsurv], c="tab:blue", s=35, marker="x",
              label=f"hole ({(~rsurv).sum()})")
ax[1].scatter(rx[rfp & rsurv], rz[rfp & rsurv], c="tab:red", s=55,
              label=f"chair-color FP still born ({(rfp & rsurv).sum()})")
ax[1].set_title("chair ROI AFTER: survivors / holes / surviving FP", fontsize=13)
for a in ax:
    a.set_aspect("equal"); a.invert_yaxis(); a.set_xlabel("X"); a.set_ylabel("Z")
    a.set_xlim(ROI["X0"], ROI["X1"]); a.set_ylim(ROI["Z1"], ROI["Z0"]); a.legend(loc="upper right")
plt.tight_layout()
plt.savefig(DIR / "viewer_roi_falsepos_holes.png", dpi=95)
plt.close()

# ---- Figure 3: clean-floor retention (collateral damage) ----
cx, cz, cc, cfp, csurv = arr(clean)
fig, ax = plt.subplots(1, 2, figsize=(20, 11))
ax[0].scatter(cx, cz, c=cc, s=8)
ax[0].set_title(f"clean wood-floor subsample BEFORE ({len(cx)} pts)", fontsize=13)
ax[1].scatter(cx[csurv], cz[csurv], c="0.6", s=8, label=f"retained ({csurv.sum()})")
ax[1].scatter(cx[~csurv], cz[~csurv], c="tab:blue", s=14, marker="x",
              label=f"wrongly holed ({(~csurv).sum()})")
ax[1].set_title(f"clean floor AFTER: retention "
                f"{csurv.sum()/max(len(csurv),1)*100:.1f}%", fontsize=13)
for a in ax:
    a.set_aspect("equal"); a.invert_yaxis(); a.set_xlabel("X"); a.set_ylabel("Z")
    draw_roi(a)
ax[1].legend(loc="upper right")
plt.tight_layout()
plt.savefig(DIR / "viewer_clean_floor_retention.png", dpi=95)
plt.close()

print("saved viewer_roi_truecolor_before_after.png, viewer_roi_falsepos_holes.png, "
      "viewer_clean_floor_retention.png")
