#!/usr/bin/env python3
"""Render top-down viewer panels for the Merrell net-vote prototype.

Reads only netvote_candidates.ply (produced by merrell_netvote_prototype.py) --
each vertex carries support / freespace_opposition / occlusion / netvote / in_roi.
No 4K pixels, no production code.
"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
ROI = {"X0": 0.25, "X1": 1.05, "Z0": -1.70, "Z1": -0.55}


def load(path):
    lines = path.read_text().splitlines()
    props = [ln.split()[-1] for ln in lines if ln.startswith("property")]
    i = lines.index("end_header") + 1
    a = np.asarray([ln.split() for ln in lines[i:] if ln.strip()], dtype=float)
    return {p: a[:, k] for k, p in enumerate(props)}


def roi_rect(ax):
    ax.add_patch(plt.Rectangle((ROI["X0"], ROI["Z0"]),
                               ROI["X1"] - ROI["X0"], ROI["Z1"] - ROI["Z0"],
                               fill=False, ec="crimson", lw=1.4, ls="--", zorder=5))


def main():
    d = load(OUT / "netvote_candidates.ply")
    x, z = d["x"], d["z"]
    rgb = np.stack([d["red"], d["green"], d["blue"]], 1) / 255.0
    support = d["support"]
    opp = d["freespace_opposition"]
    netvote = d["netvote"]
    in_roi = d["in_roi"] > 0.5

    single_kill = opp >= 1                 # single-vote-conviction gate
    net_kill = netvote < 0                 # Merrell net-vote gate
    net_survive = ~net_kill
    true_floor = (~in_roi) & (support >= 5)
    falsekill = true_floor & single_kill   # killed by single-vote, true floor
    rescued = falsekill & net_survive      # net-vote saves them

    fig, axs = plt.subplots(2, 2, figsize=(15, 12))

    # (0,0) global top-down true color
    ax = axs[0, 0]
    ax.scatter(x, z, s=2, c=rgb, linewidths=0)
    roi_rect(ax)
    ax.set_title(f"A. cap50 plane-sweep candidates (top-down true color)\n"
                 f"{len(x)} pts; ROI = chair/treadmill flatten box", fontsize=11)

    # (0,1) net-vote gate on the chair ROI: before vs after are IDENTICAL
    ax = axs[0, 1]
    roi = in_roi
    ax.scatter(x[roi], z[roi], s=6, c="lightgray", label=f"ROI all ({int(roi.sum())})")
    surv = roi & net_survive
    ax.scatter(x[surv], z[surv], s=6, c="seagreen",
               label=f"survive net-vote ({int(surv.sum())})")
    killed = roi & net_kill
    ax.scatter(x[killed], z[killed], s=14, c="red", marker="x",
               label=f"killed by net-vote ({int(killed.sum())})")
    roi_rect(ax)
    ax.set_xlim(ROI["X0"] - 0.1, ROI["X1"] + 0.1)
    ax.set_ylim(ROI["Z0"] - 0.1, ROI["Z1"] + 0.1)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title("B. HONEST TEST -- chair ROI under Merrell net-vote\n"
                 "net-vote kills 0: the flattened chair survives intact",
                 fontsize=11)

    # (1,0) same ROI under single-vote-conviction (the wrong gate): kills some
    ax = axs[1, 0]
    ax.scatter(x[roi & ~single_kill], z[roi & ~single_kill], s=6, c="lightgray",
               label=f"survive ({int((roi & ~single_kill).sum())})")
    ax.scatter(x[roi & single_kill], z[roi & single_kill], s=10, c="red",
               label=f"killed by 1-vote ({int((roi & single_kill).sum())})")
    roi_rect(ax)
    ax.set_xlim(ROI["X0"] - 0.1, ROI["X1"] + 0.1)
    ax.set_ylim(ROI["Z0"] - 0.1, ROI["Z1"] + 0.1)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title("C. same ROI under single-vote-conviction\n"
                 "1-vote gate removes some chair pts -- but see panel D why it is wrong",
                 fontsize=11)

    # (1,1) demonstration A: false-kill rescue on true floor (outside ROI)
    ax = axs[1, 1]
    base = (~in_roi)
    ax.scatter(x[base], z[base], s=1.2, c="0.82", linewidths=0)
    ax.scatter(x[rescued], z[rescued], s=9, c="seagreen",
               label=f"true floor rescued by net-vote ({int(rescued.sum())})")
    # any true-floor point still net-killed (should be ~0)
    stillkill = true_floor & net_kill
    ax.scatter(x[stillkill], z[stillkill], s=12, c="red", marker="x",
               label=f"true floor net-killed ({int(stillkill.sum())})")
    roi_rect(ax)
    ax.set_title("D. DEMO -- cure of false kills (outside ROI, support>=5)\n"
                 "1-vote gate would kill these true floor pts; net-vote keeps all",
                 fontsize=11)

    for ax in axs.flat:
        ax.set_xlabel("X (m)")
        ax.set_ylabel("Z (m)")
        ax.set_aspect("equal", adjustable="box")
        ax.invert_yaxis()

    fig.suptitle("U3 #4 Merrell signed net-vote (stability = support - free-space "
                 "opposition) on cap50 -- net-vote cures false kills but CANNOT "
                 "kill the plane-sweep chair", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out = OUT / "viewer_netvote_panels.png"
    fig.savefig(out, dpi=115)
    print("wrote", out)


if __name__ == "__main__":
    main()
