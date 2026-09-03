#!/usr/bin/env python3
"""Root-cause test: did the second knife create depth SEAMS along the (blotchy)
CasDiffMVS anchor-mask boundary?

It averaged anchor-free pixels only and left anchored pixels untouched, so any
depth correction discontinuity must appear on adjacent pixel pairs that straddle
the mask boundary. Compare, for each candidate depth set:

  cross  : median |dz|/z over adjacent pairs where exactly one pixel is anchored
  inside : median |dz|/z over adjacent pairs where both are anchored
  free   : median |dz|/z over adjacent pairs where both are anchor-free
  ratio  : cross / max(inside, free)   -- >1 means a seam follows the mask

Also reports the same for the raw and anchored sets as controls, and the number
of boundary pixels (how much of the image the seam can touch)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image as PILImage

sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
from datasets.data_io import read_pfm  # noqa: E402


def med(x):
    return float(x.median()) if x.numel() else float("nan")


ap = argparse.ArgumentParser()
ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
ap.add_argument("--cas_out", default="/root/casdiffmvs_prior_20260903/out_blendmvg_prior_768x576_nv10")
ap.add_argument("--sets", nargs="+", required=True)
ap.add_argument("--views", type=int, default=16)
ap.add_argument("--out", required=True)
a = ap.parse_args()

saved = Path(a.saved)
mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
if nam.ndim == 4:
    nam = nam[..., 0]
V, H, W = mask.shape
s2f = json.load(open(a.mapping))
f2s = {int(f): s for s, f in enumerate(s2f)}

s_m = W / 1500.0
off_v = (2000.0 * s_m - H) / 2.0
vm, um = np.meshgrid(np.arange(H, dtype=np.float64), np.arange(W, dtype=np.float64), indexing="ij")
x15 = (um + 0.5) / s_m - 0.5
y15 = (vm + 0.5 + off_v) / s_m - 0.5
x768 = (y15 + 0.5) * (768.0 / 2000.0) - 0.5
y576 = ((1500.0 - 1.0 - x15) + 0.5) * (576.0 / 1500.0) - 0.5
gridN = torch.from_numpy(np.stack([2 * x768 / 767.0 - 1, 2 * y576 / 575.0 - 1], -1).astype(np.float32))[None]

probe = list(range(0, V, max(1, V // a.views)))[: a.views]
anchor = {}
for f in probe:
    s = f2s[f]
    fin = (np.asarray(PILImage.open(Path(a.cas_out) / "mask" / f"{s:08d}_final.png")) > 0).astype(np.float32)
    an = F.grid_sample(torch.from_numpy(fin)[None, None], gridN, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0].numpy() > 0.5
    anchor[f] = an & mask[f] & nam[f]

report = {}
for spec in a.sets:
    name, path = spec.split("=", 1)
    d = np.load(path).astype(np.float32)
    rows = []
    for f in probe:
        z = torch.from_numpy(d[f])
        v = torch.from_numpy(mask[f] & nam[f]) & (z > 0)
        am = torch.from_numpy(anchor[f])
        stats = {}
        for axis in (0, 1):
            if axis == 0:
                dz = (z[1:, :] - z[:-1, :]).abs() / z[:-1, :].clamp_min(1e-6)
                vv = v[1:, :] & v[:-1, :]
                a1, a2 = am[1:, :], am[:-1, :]
            else:
                dz = (z[:, 1:] - z[:, :-1]).abs() / z[:, :-1].clamp_min(1e-6)
                vv = v[:, 1:] & v[:, :-1]
                a1, a2 = am[:, 1:], am[:, :-1]
            cross = vv & (a1 != a2)
            inside = vv & a1 & a2
            free = vv & ~a1 & ~a2
            stats.setdefault("cross", []).append(dz[cross])
            stats.setdefault("inside", []).append(dz[inside])
            stats.setdefault("free", []).append(dz[free])
        r = {k: med(torch.cat(vs)) for k, vs in stats.items()}
        r["n_cross"] = int(sum(int(x.numel()) for x in stats["cross"]))
        r["frame"] = f
        rows.append(r)
    agg = {k: float(np.median([r[k] for r in rows])) for k in ("cross", "inside", "free")}
    agg["cross_over_max_inside_free"] = agg["cross"] / max(agg["inside"], agg["free"])
    agg["boundary_pairs_per_frame_p50"] = float(np.median([r["n_cross"] for r in rows]))
    report[name] = {"aggregate": agg, "per_frame": rows, "path": path}
    print(f"{name:22s} cross {agg['cross']:.5f}  inside {agg['inside']:.5f}  free {agg['free']:.5f}  ratio {agg['cross_over_max_inside_free']:.3f}  boundary pairs {agg['boundary_pairs_per_frame_p50']:.0f}", flush=True)

Path(a.out).write_text(json.dumps(report, indent=2) + "\n")
