#!/usr/bin/env python3
"""Does MapAnything survive a resolution it was not shipped with?

The user's photos are 12 MP; MapAnything resizes every one to 518 x 392 before
inference, so its "per-pixel" cloud is per pixel of a 0.2 MP grid -- 45% of the
density CasDiffMVS produced at 768 x 576. Closing that gap means running the
network at ~770 long side, which is outside the fixed 518/512/504 mapping the
loader ships with, though the training configs mention variable resolution.

Probe, not a run: the same 8 views (spread across the sequence) inferred at 518
and at 770, the 770 depth resampled onto the 518 grid, and the per-pixel
relative difference after a single per-view scale alignment. Same batch both
times, so the only variable is resolution. A few percent means the model is
fine there; tens of percent means it is not, and higher resolution is closed.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from mapanything.models import MapAnything
from mapanything.utils.image import load_images

ap = argparse.ArgumentParser()
ap.add_argument("--image_folder", default="/root/imgs132_up")
ap.add_argument("--n", type=int, default=8)
ap.add_argument("--hi", type=int, default=770)
ap.add_argument("--out", required=True)
a = ap.parse_args()
paths = sorted(p for p in Path(a.image_folder).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
sel = [paths[i] for i in np.linspace(0, len(paths) - 1, a.n).round().astype(int)]
print("views:", [p.name for p in sel], flush=True)
model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda")


def run(views, tag):
    torch.cuda.reset_peak_memory_stats(); t0 = time.time()
    out = model.infer(views, memory_efficient_inference=True, minibatch_size=1, use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)
    torch.cuda.synchronize()
    d = torch.cat([o["depth_z"].detach().float().cpu() for o in out], 0)[..., 0]
    m = torch.cat([o["mask"].detach().cpu() for o in out], 0)[..., 0].bool()
    K = torch.cat([o["intrinsics"].detach().float().cpu() for o in out], 0)
    print(f"{tag}: depth {tuple(d.shape)}  focal p50 {float(K[:,0,0].median()):.1f}px  peak mem {torch.cuda.max_memory_allocated()/2**30:.2f} GiB  {time.time()-t0:.1f}s", flush=True)
    return d, m, K


v518 = load_images([str(p) for p in sel], resize_mode="fixed_mapping", resolution_set=518)
d0, m0, K0 = run(v518, "518")
vhi = load_images([str(p) for p in sel], resize_mode="longest_side", size=a.hi)
d1, m1, K1 = run(vhi, str(a.hi))

# resample the high-res depth onto the 518 grid and compare after per-view scale alignment
H0, W0 = d0.shape[1:]
d1s = F.interpolate(d1[:, None], size=(H0, W0), mode="nearest")[:, 0]
m1s = F.interpolate(m1[:, None].float(), size=(H0, W0), mode="nearest")[:, 0] > 0.5
rows = []
allrel = []
for i in range(a.n):
    ok = m0[i] & m1s[i] & (d0[i] > 0) & (d1s[i] > 0)
    s = float((d0[i][ok] / d1s[i][ok]).median())            # one scale per view (the two runs have independent global scale)
    rel = (d1s[i] * s - d0[i])[ok] / d0[i][ok]
    allrel.append(rel)
    rows.append({"view": sel[i].name, "scale_hi_to_518": s, "rel_abs_p50": float(rel.abs().median()),
                 "rel_abs_p90": float(rel.abs().quantile(0.9)), "focal_518": float(K0[i, 0, 0]), "focal_hi": float(K1[i, 0, 0]),
                 "focal_hi_scaled_to_518": float(K1[i, 0, 0] * W0 / d1.shape[2])})
    print(f"  {sel[i].name}: scale {s:.3f}  |rel| p50 {rows[-1]['rel_abs_p50']*100:.2f}%  p90 {rows[-1]['rel_abs_p90']*100:.2f}%  focal 518 {rows[-1]['focal_518']:.1f} vs hi->518 {rows[-1]['focal_hi_scaled_to_518']:.1f}", flush=True)
allrel = torch.cat(allrel)
summary = {"n": a.n, "hi": a.hi, "hi_shape": list(d1.shape[1:]),
           "rel_abs_p50_all": float(allrel.abs().median()), "rel_abs_p90_all": float(allrel.abs().quantile(0.9)),
           "signed_p50_all": float(allrel.median()), "rows": rows}
print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
Path(a.out).write_text(json.dumps(summary, indent=2) + "\n")
