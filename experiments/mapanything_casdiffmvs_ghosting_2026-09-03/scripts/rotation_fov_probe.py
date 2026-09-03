#!/usr/bin/env python3
"""Single-view predicted field-of-view vs rotation of the input image.
Truth from production COLMAP (fx=2862 px @4032x3024): long-side FOV 70.4 deg,
short-side FOV 55.7 deg, independent of orientation."""

import json
import math
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, os.getcwd())
from mapanything.models import MapAnything  # noqa: E402
from mapanything.utils.image import load_images  # noqa: E402

COMMON = dict(memory_efficient_inference=True, minibatch_size=1, use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)
TRUE_LONG = math.degrees(2 * math.atan(2016 / 2862.0))
TRUE_SHORT = math.degrees(2 * math.atan(1512 / 2862.0))

frames = [int(x) for x in sys.argv[1].split(",")]
model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda")
out = {"true_long_side_fov_deg": TRUE_LONG, "true_short_side_fov_deg": TRUE_SHORT, "rows": []}
with tempfile.TemporaryDirectory() as td, torch.no_grad():
    for f in frames:
        src = Image.open(f"/root/imgs132_up/frame_{f:06d}.jpg").convert("RGB")
        for rot in (0, 90, 180, 270):
            im = src.rotate(rot, expand=True)  # CCW degrees
            p = Path(td) / f"f{f}_r{rot}.jpg"
            im.save(p, quality=95)
            v = load_images([str(p)])
            o = model.infer(v, **COMMON)[0]
            K = o["intrinsics"][0].float().cpu().numpy()
            H, W = o["depth_z"].shape[1:3]
            fov_w = math.degrees(2 * math.atan((W / 2) / K[0, 0]))
            fov_h = math.degrees(2 * math.atan((H / 2) / K[1, 1]))
            long_fov, short_fov = (fov_h, fov_w) if H >= W else (fov_w, fov_h)
            out["rows"].append({"frame": f, "rot_ccw": rot, "model_WxH": [W, H], "pred_long_side_fov": round(long_fov, 2), "pred_short_side_fov": round(short_fov, 2), "long_fov_ratio_pred_over_true": round(long_fov / TRUE_LONG, 3)})
            print(out["rows"][-1], flush=True)
Path("/root/mapanything_rotation_fov_probe_20260903.json").write_text(json.dumps(out, indent=2) + "\n")
