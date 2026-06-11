#!/usr/bin/env python3
"""Experiment G: full-capture multi-window K=18 pose-conditioned R1 runner.

Runs the production window plan (K=18, stride=K/2, official preprocess at the
chosen process_res, ARKit extrinsics/intrinsics, saddle_balanced, umeyama
pose_scale per window) over an entire capture manifest with the model loaded
once. Per-window forward/postprocess mirrors official_pytorch_k_sweep
.run_attempt; chunked SDPA installed for MPS. Resumable: windows whose output
dir already holds pytorch_depth.npy are skipped.

Outputs per window_NNN/: pytorch_depth.npy (metric, /pose_scale), pytorch_conf
.npy (raw 1+exp), pytorch_intrinsics.npy (processed scale), pytorch_extrinsics
.npy (ARKit w2c 3x4), processed_images_uint8.npy, plus expG_run_report.json.
"""

from __future__ import annotations

import argparse
import gc
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
    parser.add_argument("--stride", type=int, default=9)
    parser.add_argument("--process-res", type=int, default=896)
    parser.add_argument("--sdpa-query-chunk", type=int, default=256)
    parser.add_argument("--sdpa-min-gib", type=float, default=2.0)
    args = parser.parse_args()

    sys.path.insert(0, str(args.official_src))

    import torch
    from depth_anything_3.api import DepthAnything3
    from depth_anything_3.utils.pose_align import align_poses_umeyama

    from da3base_official_streaming_oracle import install_mps_chunked_sdpa

    install_mps_chunked_sdpa(torch, args.sdpa_query_chunk, args.sdpa_min_gib)

    manifest = json.loads(args.manifest.read_text())
    rows_all = manifest["frames"]
    n = len(rows_all)
    starts = list(range(0, n - args.k + 1, args.stride))
    if starts[-1] != n - args.k:
        starts.append(n - args.k)
    print(f"frames={n} windows={len(starts)} k={args.k} stride={args.stride} res={args.process_res}", flush=True)

    device = torch.device("mps")
    model = DepthAnything3.from_pretrained(str(args.model_path)).to(device=device)
    model.model.eval()

    report_path = args.out_dir / "expG_run_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {"windows": {}}

    for wi, start in enumerate(starts):
        wdir = args.out_dir / f"window_{wi:03d}"
        if (wdir / "pytorch_depth.npy").exists():
            print(f"window {wi:03d} exists, skip", flush=True)
            continue
        rows = rows_all[start : start + args.k]
        t0 = time.perf_counter()
        image_paths = [str(args.frames_dir / r["jpegPath"]) for r in rows]
        extrinsics = np.stack(
            [np.asarray(r["cameraExtrinsic4x4"], dtype=np.float32).reshape(4, 4) for r in rows]
        )
        intrinsics = np.stack(
            [
                np.asarray(
                    [[r["cameraIntrinsicFxFyCxCy"][0], 0, r["cameraIntrinsicFxFyCxCy"][2]],
                     [0, r["cameraIntrinsicFxFyCxCy"][1], r["cameraIntrinsicFxFyCxCy"][3]],
                     [0, 0, 1]],
                    dtype=np.float32,
                )
                for r in rows
            ]
        )
        imgs_cpu, ex_pre, in_pre = model._preprocess_inputs(
            image_paths, extrinsics, intrinsics, args.process_res, "upper_bound_resize"
        )
        imgs, ex_t, in_t = model._prepare_model_inputs(imgs_cpu, ex_pre, in_pre)
        ex_t_norm = model._normalize_extrinsics(ex_t.clone())
        raw = model._run_model_forward(
            imgs,
            ex_t_norm,
            in_t,
            export_feat_layers=[],
            infer_gs=False,
            use_ray_pose=False,
            ref_view_strategy="saddle_balanced",
        )
        pred = model._convert_to_prediction(raw)
        ex_pre_np = ex_pre.detach().cpu().numpy() if hasattr(ex_pre, "detach") else np.asarray(ex_pre)
        in_pre_np = in_pre.detach().cpu().numpy() if hasattr(in_pre, "detach") else np.asarray(in_pre)
        _, _, pose_scale, _ = align_poses_umeyama(
            pred.extrinsics,
            ex_pre_np,
            ransac=len(rows) >= 10,
            return_aligned=True,
            random_state=42,
        )
        depth = (np.asarray(pred.depth, dtype=np.float32) / float(pose_scale))
        conf = np.asarray(pred.conf, dtype=np.float32)

        imgs_np = imgs_cpu.detach().cpu().numpy() if hasattr(imgs_cpu, "detach") else np.asarray(imgs_cpu)
        if imgs_np.ndim == 5:
            imgs_np = imgs_np[0]
        mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)[None, :, None, None]
        std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)[None, :, None, None]
        rgb = np.clip((imgs_np * std + mean) * 255.0, 0, 255).astype(np.uint8).transpose(0, 2, 3, 1)

        wdir.mkdir(parents=True, exist_ok=True)
        np.save(wdir / "pytorch_depth.npy", depth)
        np.save(wdir / "pytorch_conf.npy", conf)
        np.save(wdir / "pytorch_intrinsics.npy", in_pre_np)
        np.save(wdir / "pytorch_extrinsics.npy", ex_pre_np[:, :3, :])
        np.save(wdir / "processed_images_uint8.npy", rgb)

        row = {
            "start": start,
            "frame_ids": [r["frameID"] for r in rows[:1]] + ["..."] + [rows[-1]["frameID"]],
            "umeyama_scale": float(pose_scale),
            "conf_median": float(np.median(conf)),
            "elapsed_s": round(time.perf_counter() - t0, 1),
        }
        report["windows"][f"{wi:03d}"] = row
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2))
        print(f"window {wi:03d} start={start} conf_med={row['conf_median']:.2f} "
              f"scale={row['umeyama_scale']:.4f} {row['elapsed_s']}s", flush=True)

        del raw, pred, imgs, ex_t, in_t, imgs_cpu
        gc.collect()
        torch.mps.empty_cache()

    print("EXPG-ALL-DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
