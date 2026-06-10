#!/usr/bin/env python3
"""Experiment F: off-ladder (H,W) shape probe around the 504x896 conf peak.

The official preprocess maps one process_res scalar to one (H,W); shapes like
490x910 / 518x882 are unreachable on that ladder. This probe feeds the model
hand-resized inputs at arbitrary 14-multiple shapes to test what the peak
actually keys on: the trained pair (504,896), H=504 alone, or W=896 alone.

Semantics mirror the official InputProcessor except the target size:
- single cv2.resize INTER_AREA from the original photo straight to (W,H)
  (official does longest-side then make-divisible, both INTER_AREA when
  downscaling; the 504x896 control row quantifies the path difference),
- torchvision ToTensor + ImageNet Normalize (same constants),
- intrinsics scaled per _resize_ixt (fx,cx by W ratio; fy,cy by H ratio),
- forward/postprocess copied from official_pytorch_k_sweep.run_attempt
  (prepare inputs, _normalize_extrinsics, saddle_balanced, umeyama,
  depth /= pose_scale), chunked SDPA installed for MPS.

NOT a production path: shipping an off-ladder shape would fork preprocess
away from official semantics — this is a mechanism probe first.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--official-src", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--k", type=int, default=18)
    parser.add_argument("--shapes", required=True, help="comma list like 504x882,490x910")
    parser.add_argument("--sdpa-query-chunk", type=int, default=256)
    parser.add_argument("--sdpa-min-gib", type=float, default=2.0)
    args = parser.parse_args()

    sys.path.insert(0, str(args.official_src))

    import cv2
    import torch
    import torchvision.transforms as T
    from depth_anything_3.api import DepthAnything3
    from depth_anything_3.utils.pose_align import align_poses_umeyama

    from da3base_official_streaming_oracle import install_mps_chunked_sdpa

    install_mps_chunked_sdpa(torch, args.sdpa_query_chunk, args.sdpa_min_gib)

    normalize = T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    manifest = json.loads(args.manifest.read_text())
    rows = manifest["frames"][: args.k]

    device = torch.device("mps")
    model = DepthAnything3.from_pretrained(str(args.model_path)).to(device=device)
    model.model.eval()

    results = []
    for shape in args.shapes.split(","):
        h, w = (int(v) for v in shape.lower().split("x"))
        assert h % 14 == 0 and w % 14 == 0, shape
        imgs, ixts, exts = [], [], []
        for row in rows:
            from PIL import Image

            pil = Image.open(args.frames_dir / row["jpegPath"]).convert("RGB")
            ow, oh = pil.size
            arr = cv2.resize(np.asarray(pil), (w, h), interpolation=cv2.INTER_AREA)
            imgs.append(normalize(T.ToTensor()(Image.fromarray(arr))))
            fx, fy, cx, cy = (float(v) for v in row["cameraIntrinsicFxFyCxCy"])
            k33 = np.asarray([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float32)
            k33[:1] *= w / float(ow)
            k33[1:2] *= h / float(oh)
            ixts.append(k33)
            exts.append(np.asarray(row["cameraExtrinsic4x4"], dtype=np.float32).reshape(4, 4))
        imgs_cpu = torch.stack(imgs)
        ex_pre = torch.from_numpy(np.stack(exts)).float()
        in_pre = torch.from_numpy(np.stack(ixts)).float()

        t0 = time.perf_counter()
        imgs_t, ex_t, in_t = model._prepare_model_inputs(imgs_cpu, ex_pre, in_pre)
        ex_t_norm = model._normalize_extrinsics(ex_t.clone())
        raw = model._run_model_forward(
            imgs_t,
            ex_t_norm,
            in_t,
            export_feat_layers=[],
            infer_gs=False,
            use_ray_pose=False,
            ref_view_strategy="saddle_balanced",
        )
        pred = model._convert_to_prediction(raw)
        _, _, pose_scale, _ = align_poses_umeyama(
            pred.extrinsics,
            ex_pre.numpy(),
            ransac=len(rows) >= 10,
            return_aligned=True,
            random_state=42,
        )
        depth = np.asarray(pred.depth, dtype=np.float32) / float(pose_scale)
        conf = np.asarray(pred.conf, dtype=np.float32)
        forward_s = time.perf_counter() - t0

        case = args.out_dir / f"k{args.k:02d}_{h}x{w}"
        case.mkdir(parents=True, exist_ok=True)
        np.save(case / "pytorch_depth.npy", depth)
        np.save(case / "pytorch_conf.npy", conf)
        np.save(case / "pytorch_intrinsics.npy", np.stack(ixts))
        np.save(case / "pytorch_extrinsics.npy", np.stack(exts)[:, :3, :])
        tok = ((h // 14) * (w // 14) + 1) * args.k
        row_out = {
            "shape": f"{h}x{w}",
            "tokens": tok,
            "conf_median": float(np.median(conf)),
            "conf_p95": float(np.percentile(conf, 95)),
            "umeyama_scale": float(pose_scale),
            "forward_s": round(forward_s, 1),
        }
        results.append(row_out)
        print(json.dumps(row_out), flush=True)
        del raw, pred
        import gc

        gc.collect()
        torch.mps.empty_cache()

    (args.out_dir / "expF_offgrid_report.json").write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
