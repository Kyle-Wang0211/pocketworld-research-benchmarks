#!/usr/bin/env python3
"""Which inference resolution puts MapAnything closest to CasDiffMVS?

Comparing 770 against 518 only says the two differ (4.4% median); it cannot
say which is better, because neither is ground truth. CasDiffMVS is the
reference the user judges geometrically right, so: the same 8 views inferred
at 518 / 770 / 1036, each resampled onto CasDiffMVS's 768x576 grid through the
same upright-crop mapping used everywhere in this campaign, one scale per view,
and the per-pixel relative deviation from CasDiffMVS where its final_mask holds.
Lower is closer. Also recorded: peak memory per resolution for 8 views, to
size the chunks of a full run, and the self-predicted focal, which the 770 probe
showed drifting further from COLMAP as resolution rises.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from mapanything.models import MapAnything
from mapanything.utils.image import load_images

sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
os.chdir("/root/casdiffmvs_official_20260903/diffmvs_upstream")
from datasets.data_io import read_pfm  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--image_folder", default="/root/imgs132_up")
ap.add_argument("--n", type=int, default=8)
ap.add_argument("--res", type=int, nargs="+", default=[518, 770, 1036])
ap.add_argument("--out", required=True)
a = ap.parse_args()
of = "/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10"
s2f = json.load(open("/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json"))
f2s = {int(f): s for s, f in enumerate(s2f)}
paths = sorted(p for p in Path(a.image_folder).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
sel = [paths[i] for i in np.linspace(0, len(paths) - 1, a.n).round().astype(int)]
frames = [int(p.stem.split("_")[-1]) for p in sel]
srcs = [f2s[f] for f in frames]
model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda")
x768, y576 = np.meshgrid(np.arange(768, dtype=np.float64), np.arange(576, dtype=np.float64))
x_l = (x768 + 0.5) * (2000.0 / 768.0) - 0.5; y_l = (y576 + 0.5) * (1500.0 / 576.0) - 0.5

cas = []
for s in srcs:
    d = read_pfm(os.path.join(of, f"depth_est/{s:08d}.pfm"))[0].astype(np.float32)
    m = cv2.imread(os.path.join(of, f"mask/{s:08d}_final.png"), 0) > 0
    cas.append((torch.from_numpy(d).cuda(), torch.from_numpy(m).cuda()))

res_out = {}
for R in a.res:
    if R == 518:
        views = load_images([str(p) for p in sel], resize_mode="fixed_mapping", resolution_set=518)
    else:
        views = load_images([str(p) for p in sel], resize_mode="longest_side", size=R)
    torch.cuda.reset_peak_memory_stats(); t0 = time.time()
    out = model.infer(views, memory_efficient_inference=True, minibatch_size=1, use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)
    torch.cuda.synchronize(); dt = time.time() - t0
    D = torch.cat([o["depth_z"].detach().float() for o in out], 0)[..., 0].cuda()
    M = torch.cat([o["mask"].detach() for o in out], 0)[..., 0].bool().cuda()
    K = torch.cat([o["intrinsics"].detach().float().cpu() for o in out], 0)
    Hm, Wm = D.shape[1:]; s_m = Wm / 1500.0; off_v = (2000.0 * s_m - Hm) / 2.0
    um = ((1500.0 - 1.0 - y_l) + 0.5) * s_m - 0.5; vm = (x_l + 0.5) * s_m - 0.5 - off_v
    grid = torch.from_numpy(np.stack([2 * um / (Wm - 1) - 1, 2 * vm / (Hm - 1) - 1], -1).astype(np.float32))[None].cuda()
    rows, allrel = [], []
    for i in range(a.n):
        dm = F.grid_sample(torch.where(M[i], D[i], torch.zeros_like(D[i]))[None, None], grid, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0]
        cd, cm = cas[i]
        ok = cm & (cd > 0) & (dm > 0)
        s = float((cd[ok] / dm[ok]).median())
        rel = (dm[ok] * s - cd[ok]) / cd[ok]
        allrel.append(rel)
        rows.append({"frame": frames[i], "src": srcs[i], "scale": s, "rel_abs_p50": float(rel.abs().median()), "rel_abs_p90": float(rel.abs().quantile(0.9)),
                     "focal_on_518_grid": float(K[i, 0, 0] * 392.0 / Wm)})
    allrel = torch.cat(allrel)
    res_out[R] = {"shape": [int(Hm), int(Wm)], "peak_gib_8views": torch.cuda.max_memory_allocated() / 2**30, "seconds": dt,
                  "vs_casdiff_rel_abs_p50": float(allrel.abs().median()), "vs_casdiff_rel_abs_p90": float(allrel.abs().quantile(0.9)),
                  "focal_on_518_grid_p50": float(np.median([r["focal_on_518_grid"] for r in rows])), "rows": rows}
    print(f"{R:5d}: {Hm}x{Wm}  vs CasDiffMVS |rel| p50 {res_out[R]['vs_casdiff_rel_abs_p50']*100:.2f}%  p90 {res_out[R]['vs_casdiff_rel_abs_p90']*100:.2f}%   "
          f"focal(518-grid) {res_out[R]['focal_on_518_grid_p50']:.1f}px   peak {res_out[R]['peak_gib_8views']:.2f} GiB  {dt:.1f}s", flush=True)
    del D, M, out; torch.cuda.empty_cache()
Path(a.out).write_text(json.dumps(res_out, indent=2) + "\n")
