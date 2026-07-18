#!/usr/bin/env python3.11
# E17 renders: same-gauge full(off) vs L2-on preview — top / elevation / cross-section.
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714")
DATA = ROOT / "data/pocketworld_captures"
OUT = ROOT / "experiments/rs_replication_exec_2026-07-19/E17_l2_preview_sim"

def load_ply(p):
    data = p.read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    n = int([l for l in data[:end].decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
    return np.frombuffer(data[end:end + n * 15], dtype=np.dtype([("xyz", "<f4", 3), ("rgb", "u1", 3)]))

for cap in ("cap50", "cap51"):
    d = DATA / cap / "device_full_pull_2026-07-17"
    rec = load_ply(d / "sfm_sparse.ply")
    hid = np.load(OUT / f"{cap}_hidden.npy")
    sd = np.load(OUT / f"{cap}_sd.npy") * 100.0  # cm
    xyz = rec["xyz"].astype(np.float64)
    rgb = rec["rgb"].astype(np.float64) / 255.0
    x, z = xyz[:, 0], xyz[:, 2]
    # robust extents (same gauge both panels)
    def lim(v, pad=0.05):
        lo, hi = np.percentile(v, [0.5, 99.5]); m = (hi - lo) * pad
        return lo - m, hi + m
    xl, zl = lim(x), lim(z)
    # cross-section slice: 10cm slab through densest z
    zc = np.median(z[np.abs(sd) < 1.5]) if (np.abs(sd) < 1.5).sum() else np.median(z)
    xsec = np.abs(z - zc) < 0.05

    views = [
        ("top (X-Z)", x, z, np.ones(len(x), bool), xl, zl, "x [m]", "z [m]"),
        ("elevation (X vs sd)", x, sd, np.ones(len(x), bool), xl, (-15, 25), "x [m]", "sd to plane [cm]"),
        (f"cross-section |z-{zc:.2f}m|<5cm", x, sd, xsec, xl, (-12, 15), "x [m]", "sd [cm]"),
    ]
    fig, axes = plt.subplots(3, 2, figsize=(15, 16), dpi=110)
    for row, (name, vx, vy, sel, vxl, vyl, lx, ly) in enumerate(views):
        for col, (label, mask) in enumerate([("full (L2 OFF)", np.ones(len(x), bool)), ("L2 ON preview", ~hid)]):
            ax = axes[row, col]
            m = sel & mask
            ax.scatter(vx[m], vy[m], s=0.4, c=rgb[m], linewidths=0)
            if row > 0:
                ax.axhline(0, color="lime", lw=0.6, alpha=0.7)
                ax.axhline(1.5, color="orange", lw=0.5, ls="--", alpha=0.6)
                ax.axhline(-1.5, color="orange", lw=0.5, ls="--", alpha=0.6)
            ax.set_xlim(vxl); ax.set_ylim(vyl)
            ax.set_facecolor("#101014")
            ax.set_title(f"{cap} {name} — {label} ({m.sum()} pts)", fontsize=10)
            ax.set_xlabel(lx); ax.set_ylabel(ly)
    fig.suptitle(f"E17 L2 render-gate SIMULATION — {cap} (display-only; delivered PLY stays full). hidden=band15&~rescued", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    out = OUT / f"{cap}_full_vs_l2on.png"
    fig.savefig(out, facecolor="white")
    plt.close(fig)
    print("wrote", out)
