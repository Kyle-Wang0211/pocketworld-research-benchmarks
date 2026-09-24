#!/usr/bin/env python3
"""expE renders: eyeball PRE (official, ghosted) vs POST-B (sparse-anchor
scaled) — window-colored projections + cross-section slab + full PLYs.

Reads the depth cache + s_B scales that expE_sparse_anchor_414.py wrote.
Window coloring: win25=red, win26=green, win28=blue. Ghosting shows as
separated color layers; a correct fix fuses them into one surface.
"""

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
OUT_DIR = Path("data/expE_sparse_anchor_414_2026_06_12")
DEPTH_CACHE = OUT_DIR / "window_depths.npz"
RESULTS = OUT_DIR / "expE_results.jsonl"
WINDOW_IDS = [25, 26, 28]
PLY_STRIDE = 2
CONF_PCT = 40.0


def log(m):
    print(f"[expE-render {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
z = np.load(DEPTH_CACHE)

s_B = {}
for line in RESULTS.read_text().splitlines():
    row = json.loads(line)
    if row.get("kind") == "fixB_scale":
        s_B[row["win"]] = row["s_B"]
log(f"s_B = {s_B}")
assert all(w in s_B for w in WINDOW_IDS), "missing fixB_scale rows"


def backproject(w, s, stride):
    depth, conf = z[f"depth_{w}"], z[f"conf_{w}"]
    Ks, w2cs = z[f"K_{w}"], z[f"w2c_{w}"]
    rows = man[w * 9: w * 9 + 18]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    pts, cols = [], []
    for i in range(n):
        zz_full = depth[i] * s
        m = (conf[i] >= floor) & (zz_full > 1e-3)
        vs, us = np.where(m)
        sel = (vs % stride == 0) & (us % stride == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs):
            continue
        img = cv2.imread(str(D / "capture_seq_k35_strict" / rows[i]["jpegPath"]))
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        K = Ks[i]
        zz = zz_full[vs, us]
        x = (us + 0.5 - K[0, 2]) / K[0, 0] * zz
        y = (vs + 0.5 - K[1, 2]) / K[1, 1] * zz
        cam = np.stack([x, y, zz, np.ones_like(zz)])
        c2w = np.linalg.inv(w2cs[i].astype(np.float64))
        pts.append((c2w @ cam)[:3].T.astype(np.float32))
        cols.append(img[vs, us][:, ::-1])  # BGR->RGB
    return np.concatenate(pts), np.concatenate(cols)


def write_ply(path, pts, cols):
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(pts)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "end_header\n")
    rec = np.empty(len(pts), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
    rec["xyz"], rec["rgb"] = pts, cols
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(rec.tobytes())


import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

WIN_RGB = {25: "#e6194b", 26: "#3cb44b", 28: "#4363d8"}

clouds = {}
for tag, scales in [("pre", {w: 1.0 for w in WINDOW_IDS}), ("postB", s_B)]:
    merged_p, merged_c = [], []
    for w in WINDOW_IDS:
        p, c = backproject(w, scales[w], PLY_STRIDE)
        clouds[(tag, w)] = p
        merged_p.append(p)
        merged_c.append(c)
        log(f"{tag} win{w}: {len(p):,} pts")
    write_ply(OUT_DIR / f"merged_{tag}.ply",
              np.concatenate(merged_p), np.concatenate(merged_c))
    log(f"wrote merged_{tag}.ply ({sum(len(p) for p in merged_p):,} pts)")

allpts = np.concatenate([clouds[("pre", w)] for w in WINDOW_IDS])
lo, hi = np.percentile(allpts, 2, axis=0), np.percentile(allpts, 98, axis=0)
x_mid = np.percentile(allpts[:, 0], 50)
slab_half = 0.025

fig, axes = plt.subplots(2, 3, figsize=(21, 12))
for row, tag in enumerate(["pre", "postB"]):
    for w in WINDOW_IDS:
        p = clouds[(tag, w)]
        sub = p[:: max(1, len(p) // 150_000)]
        axes[row][0].scatter(sub[:, 0], sub[:, 2], s=0.25, c=WIN_RGB[w],
                             alpha=0.22, linewidths=0, label=f"win{w}")
        axes[row][1].scatter(sub[:, 0], sub[:, 1], s=0.25, c=WIN_RGB[w],
                             alpha=0.22, linewidths=0)
        slab = p[np.abs(p[:, 0] - x_mid) < slab_half]
        axes[row][2].scatter(slab[:, 2], slab[:, 1], s=1.2, c=WIN_RGB[w],
                             alpha=0.5, linewidths=0)
    name = "PRE (official only — ghosted)" if tag == "pre" else "POST-B (sparse-anchor scaled)"
    axes[row][0].set_title(f"top-down XZ — {name}")
    axes[row][1].set_title(f"side XY — {name}")
    axes[row][2].set_title(f"cross-section slab |x-{x_mid:.2f}|<{slab_half*100:.0f}cm — {name}")
    axes[row][0].set_xlim(lo[0], hi[0]); axes[row][0].set_ylim(lo[2], hi[2])
    axes[row][1].set_xlim(lo[0], hi[0]); axes[row][1].set_ylim(lo[1], hi[1])
    axes[row][2].set_xlim(lo[2], hi[2]); axes[row][2].set_ylim(lo[1], hi[1])
    for ax in axes[row]:
        ax.set_aspect("equal")
    axes[row][0].legend(markerscale=30, loc="upper right")
fig.tight_layout()
fig.savefig(OUT_DIR / "render_pre_vs_postB.png", dpi=110)
log("wrote render_pre_vs_postB.png")
log("EXPE-RENDER-DONE")
