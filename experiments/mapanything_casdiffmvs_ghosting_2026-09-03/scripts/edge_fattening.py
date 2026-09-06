#!/usr/bin/env python3
"""Is the white-wall "sticking" in CasDiffMVS edge fattening, and does the
official geometric gate let it through?

Hypothesis. CasDiffMVS regularises a cost volume with 2-D convolutions. At an
object silhouette against a textureless wall the background side of the cost is
flat, so the regulariser smears the foreground depth outward: pixels that are
really wall get depths between the object and the wall. A bridge of points then
appears to connect the luggage to the wall behind it. That is what the eye calls
sticking.

A bridging pixel is one whose neighbourhood (radius r) contains both a near
surface and a far surface separated by more than `jump`, while its own depth is
strictly between the two. Counted on the raw depth_est so the mechanism is seen
before the gate, then intersected with final_mask to see how many the official
photometric + geometric gate actually removes.

Also tested: MapAnything's own per-view mask (non_ambiguous & edge), mapped
onto the CasDiffMVS pixel grid, as a candidate edge prior -- if it marks the
same pixels, it can be borrowed directly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ap = argparse.ArgumentParser()
ap.add_argument("--repo", default="/root/casdiffmvs_official_20260903/diffmvs_upstream")
ap.add_argument("--out_folder", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10")
ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
ap.add_argument("--radius", type=int, default=6)
ap.add_argument("--jump", type=float, default=1.12, help="far/near ratio that counts as a discontinuity")
ap.add_argument("--margin", type=float, default=0.03, help="a bridging depth must be this far (relative) from both sides")
ap.add_argument("--out", required=True)
a = ap.parse_args()
sys.path.insert(0, a.repo)
os.chdir(a.repo)
from datasets.data_io import read_pfm  # noqa: E402

dev = "cuda"
of = a.out_folder
V = 132
import cv2

# MapAnything masks + the native->768x576 mapping (inverse of export_native_anchored's chain)
ma_mask = np.load(Path(a.saved) / "mask.npy")[..., 0].astype(bool)          # frame index, 518x392 upright
nam = np.load(Path(a.saved) / "non_ambiguous_mask.npy").astype(bool)
if nam.ndim == 4:
    nam = nam[..., 0]
ma_valid = ma_mask & nam
s2f = json.load(open(a.mapping))            # source index -> frame index
Hm, Wm = ma_mask.shape[1:]
s_m = Wm / 1500.0
off_v = (2000.0 * s_m - Hm) / 2.0


def ma_mask_on_cas_grid(src):
    """MapAnything's (non_ambiguous & edge) mask for source view `src`, resampled onto 768x576."""
    f = int(s2f[src])
    m = ma_valid[f].astype(np.float32)
    # 768x576 landscape pixel -> upright 1500x2000 (x_l,y_l) -> native (um,vm)
    x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
    x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5
    y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5
    # inverse of  x_l = y15 ; y_l = 1500-1-x15
    x15 = 1500.0 - 1.0 - y_l
    y15 = x_l
    um = (x15 + 0.5) * s_m - 0.5
    vm = (y15 + 0.5) * s_m - 0.5 - off_v
    gx = 2 * um / (Wm - 1) - 1
    gy = 2 * vm / (Hm - 1) - 1
    grid = torch.from_numpy(np.stack([gx, gy], -1).astype(np.float32))[None]
    out = F.grid_sample(torch.from_numpy(m)[None, None], grid, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0]
    return out.numpy() > 0.5


tot = {"pixels_in_final": 0, "bridging_raw": 0, "bridging_in_final": 0,
       "bridging_in_final_ma_says_edge": 0, "final_ma_says_edge": 0,
       "geo_support_bridging": [], "geo_support_all": []}
per_view = []
for v in range(V):
    d = torch.from_numpy(read_pfm(os.path.join(of, f"depth_est/{v:08d}.pfm"))[0].astype(np.float32)).to(dev)
    fin = cv2.imread(os.path.join(of, f"mask/{v:08d}_final.png"), cv2.IMREAD_GRAYSCALE) > 0
    fin_t = torch.from_numpy(fin).to(dev)
    H, W = d.shape
    valid = d > 0
    # neighbourhood min / max of depth over a (2r+1)^2 window, ignoring invalid
    big = torch.where(valid, d, torch.full_like(d, float("inf")))
    small = torch.where(valid, d, torch.full_like(d, -float("inf")))
    k = 2 * a.radius + 1
    nmin = -F.max_pool2d(-big[None, None], k, stride=1, padding=a.radius)[0, 0]
    nmax = F.max_pool2d(small[None, None], k, stride=1, padding=a.radius)[0, 0]
    disc = valid & torch.isfinite(nmin) & torch.isfinite(nmax) & (nmax / nmin.clamp_min(1e-6) > a.jump)
    between = (d > nmin * (1 + a.margin)) & (d < nmax * (1 - a.margin))
    bridging = disc & between
    ma_edge = ~torch.from_numpy(ma_mask_on_cas_grid(v)).to(dev)     # True where MapAnything drops the pixel
    b_fin = bridging & fin_t
    tot["pixels_in_final"] += int(fin_t.sum())
    tot["bridging_raw"] += int(bridging.sum())
    tot["bridging_in_final"] += int(b_fin.sum())
    tot["bridging_in_final_ma_says_edge"] += int((b_fin & ma_edge).sum())
    tot["final_ma_says_edge"] += int((fin_t & ma_edge).sum())
    per_view.append({"view": v, "final": int(fin_t.sum()), "bridging_raw": int(bridging.sum()),
                     "bridging_in_final": int(b_fin.sum())})
    if v % 20 == 0:
        print(f"  view {v}: final {int(fin_t.sum())}  bridging raw {int(bridging.sum())}  survive gate {int(b_fin.sum())}"
              f"  of which MapAnything flags {int((b_fin & ma_edge).sum())}", flush=True)

r = {k: v for k, v in tot.items() if not k.startswith("geo_support")}
r["frac_of_pc_that_is_bridging"] = tot["bridging_in_final"] / max(tot["pixels_in_final"], 1)
r["gate_removes_frac_of_bridging"] = 1 - tot["bridging_in_final"] / max(tot["bridging_raw"], 1)
r["mapanything_edge_recall_on_surviving_bridges"] = tot["bridging_in_final_ma_says_edge"] / max(tot["bridging_in_final"], 1)
r["mapanything_edge_frac_of_whole_pc"] = tot["final_ma_says_edge"] / max(tot["pixels_in_final"], 1)
r["params"] = {"radius": a.radius, "jump": a.jump, "margin": a.margin}
print(json.dumps(r, indent=2))
Path(a.out).write_text(json.dumps({"summary": r, "per_view": per_view}, indent=2) + "\n")
