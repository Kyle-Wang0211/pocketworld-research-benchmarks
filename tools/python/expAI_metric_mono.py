"""expAI: path B — pure DA3METRIC-LARGE monocular metric depth + ARKit
pose fusion, NO windows, NO umeyama, NO per-window scalar. First 100
spatial-order frames. Tests whether monocular-metric fusion ghosts
LESS than the windowed multi-view approach.

DA3METRIC: head output_dim=1 (depth only, NO conf), cat_token=False
(monocular). Metric conversion = focal(at process_res)/300 * canonical
(official `apply_metric_scaling`). No conf -> gate by depth-gradient
edges + valid range. Photo-colored output for ghosting eyeball.
"""
import json
import sys
import time
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, "/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
import torch
from da3base_official_streaming_oracle import install_mps_chunked_sdpa
install_mps_chunked_sdpa(torch, 256, 4.0)
from depth_anything_3.api import DepthAnything3

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
MODEL = "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3METRIC-LARGE"
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
N_FRAMES = 100
PROCESS_RES = 504
GRAD_REL_MAX = 0.04          # drop pixels where |depth step| / depth > this (edges)
STRIDE = 2


def log(m):
    print(f"[expAI {time.strftime('%H:%M:%S')}] {m}", flush=True)


man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
rows = man[:N_FRAMES]
log(f"frames: {len(rows)} (spatial-order first {N_FRAMES})")

log("loading DA3METRIC-LARGE …")
model = DepthAnything3.from_pretrained(MODEL).to(device=torch.device("mps"))
model.model.eval()
log("model ready")


def metric_depth_one(path, ixt):
    imgs_cpu, _, in_pre = model._preprocess_inputs(
        [path], None, ixt[None], PROCESS_RES, "upper_bound_resize")
    imgs, _, in_t = model._prepare_model_inputs(imgs_cpu, None, in_pre)
    raw = model._run_model_forward(imgs, None, in_t, [], False, False, "saddle_balanced")
    pred = model._convert_to_prediction(raw)
    depth = np.asarray(pred.depth, dtype=np.float32)[0]          # (H,W) canonical
    K = np.asarray(in_pre[0], dtype=np.float64)                  # scaled intrinsics
    focal = (K[0, 0] + K[1, 1]) / 2.0
    metric = depth * (focal / 300.0)                            # official formula
    img = np.asarray(imgs_cpu[0])
    if img.shape[0] == 3:
        img = np.transpose(img, (1, 2, 0))
    if img.dtype != np.uint8:
        img = np.clip(img * 255 if img.max() <= 1.5 else img, 0, 255).astype(np.uint8)
    return metric, K, img


def edge_mask(depth):
    gx = np.zeros_like(depth); gy = np.zeros_like(depth)
    gx[:, 1:-1] = np.abs(depth[:, 2:] - depth[:, :-2]) / 2
    gy[1:-1, :] = np.abs(depth[2:, :] - depth[:-2, :]) / 2
    rel = (gx + gy) / np.maximum(depth, 1e-3)
    return rel < GRAD_REL_MAX


def main():
    path_out = DELIVER / "metric_mono_first100.ply"
    fh = open(path_out, "wb")
    fh.write(("ply\nformat binary_little_endian 1.0\n"
              "element vertex 000000000000\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "end_header\n").encode())
    count = 0
    t0 = time.time()
    for i, r in enumerate(rows):
        fx, fy, cx, cy = r["cameraIntrinsicFxFyCxCy"]
        ixt = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], np.float32)
        w2c = np.asarray(r["cameraExtrinsic4x4"], np.float64).reshape(4, 4)
        path = str(D / "capture_seq_k35_strict" / r["jpegPath"])
        metric, K, img = metric_depth_one(path, ixt)
        H, W = metric.shape
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        m = edge_mask(metric) & (metric > 1e-3) & (metric < 20.0)
        vs, us = np.where(m)
        sel = (vs % STRIDE == 0) & (us % STRIDE == 0)
        vs, us = vs[sel], us[sel]
        if not len(vs):
            continue
        zz = metric[vs, us].astype(np.float64)
        x = (us + 0.5 - K[0, 2]) / K[0, 0] * zz
        y = (vs + 0.5 - K[1, 2]) / K[1, 1] * zz
        cam = np.stack([x, y, zz, np.ones_like(zz)])
        c2w = np.linalg.inv(w2c)
        pts = (c2w @ cam)[:3].T.astype(np.float32)
        cols = img[vs, us][:, ::-1]
        rec = np.empty(len(pts), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
        rec["xyz"], rec["rgb"] = pts, cols
        fh.write(rec.tobytes())
        count += len(pts)
        if i % 20 == 0:
            log(f"frame {i}/{N_FRAMES}, {count/1e6:.1f}M pts, {time.time()-t0:.0f}s")
    fh.close()
    with open(path_out, "r+b") as f2:
        data = f2.read(200)
        f2.seek(data.find(b"000000000000"))
        f2.write(f"{count:012d}".encode())
    log(f"metric_mono_first100.ply: {count:,} pts -> {path_out}")
    log("EXPAI-DONE")


if __name__ == "__main__":
    main()
