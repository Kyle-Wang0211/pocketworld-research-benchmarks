#!/usr/bin/env python3
"""Sweep official DA3 PyTorch inference over K and process_res values."""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import resource
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--official-src", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--device", default="mps", choices=["auto", "cpu", "mps", "cuda"])
    parser.add_argument("--process-res", type=int, nargs="+", default=[476, 742])
    parser.add_argument("--k-values", type=int, nargs="+", default=[1, 2, 3, 5, 10, 35])
    parser.add_argument("--process-res-method", default="upper_bound_resize")
    parser.add_argument("--ref-view-strategy", default="saddle_balanced")
    parser.add_argument("--save-arrays", action="store_true")
    parser.add_argument("--stop-after-first-failure", action="store_true")
    args = parser.parse_args()

    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.official_src))
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    import torch
    from depth_anything_3.api import DepthAnything3
    from depth_anything_3.utils.pose_align import align_poses_umeyama

    manifest = read_json(args.manifest)
    rows_all = list(manifest.get("frames") or [])
    if not rows_all:
        raise ValueError(f"No frames in {args.manifest}")

    device = choose_device(torch, args.device)
    load_t0 = time.perf_counter()
    model = DepthAnything3.from_pretrained(str(args.model_path))
    model = model.to(device=device)
    model.model.eval()
    load_ms = (time.perf_counter() - load_t0) * 1000.0

    report: dict[str, Any] = {
        "schema_version": "pocketworld_official_pytorch_k_sweep_v1",
        "inputs": {
            "frames_dir": str(args.frames_dir),
            "manifest": str(args.manifest),
            "model_path": str(args.model_path),
            "official_src": str(args.official_src),
        },
        "parameters": {
            "device": str(device),
            "process_res": args.process_res,
            "k_values": args.k_values,
            "process_res_method": args.process_res_method,
            "ref_view_strategy": args.ref_view_strategy,
            "save_arrays": args.save_arrays,
        },
        "runtime": {
            "python": sys.version.replace("\n", " "),
            "platform": platform.platform(),
            "torch": torch.__version__,
            "load_ms": load_ms,
        },
        "attempts": [],
    }

    for process_res in args.process_res:
        for k_value in args.k_values:
            if k_value > len(rows_all):
                continue
            attempt = run_attempt(
                rows=rows_all[:k_value],
                frames_dir=args.frames_dir,
                out_dir=args.out_dir / f"k{k_value:02d}_res{process_res}_{device.type}",
                model=model,
                torch=torch,
                align_poses_umeyama=align_poses_umeyama,
                device=device,
                process_res=process_res,
                process_res_method=args.process_res_method,
                ref_view_strategy=args.ref_view_strategy,
                save_arrays=args.save_arrays,
            )
            report["attempts"].append(attempt)
            write_json(args.out_dir / "official_pytorch_k_sweep_report.json", report)
            write_markdown(args.out_dir / "official_pytorch_k_sweep_report_zh.md", report)
            print(json.dumps(compact_attempt(attempt), ensure_ascii=False, indent=2), flush=True)
            cleanup(torch, device)
            if attempt["status"] != "success" and args.stop_after_first_failure:
                break

    report["elapsed_s"] = round(time.perf_counter() - started, 3)
    write_json(args.out_dir / "official_pytorch_k_sweep_report.json", report)
    write_markdown(args.out_dir / "official_pytorch_k_sweep_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def run_attempt(
    *,
    rows: list[dict[str, Any]],
    frames_dir: Path,
    out_dir: Path,
    model: Any,
    torch: Any,
    align_poses_umeyama: Any,
    device: Any,
    process_res: int,
    process_res_method: str,
    ref_view_strategy: str,
    save_arrays: bool,
) -> dict[str, Any]:
    k_value = len(rows)
    attempt: dict[str, Any] = {
        "k": k_value,
        "process_res": process_res,
        "device": str(device),
        "status": "started",
        "out_dir": str(out_dir),
        "rss_before_mb": rss_mb(),
    }
    t0 = time.perf_counter()
    try:
        image_paths = [str(resolve_image(frames_dir, row["jpegPath"])) for row in rows]
        extrinsics = np.stack(
            [np.asarray(row["cameraExtrinsic4x4"], dtype=np.float32).reshape(4, 4) for row in rows]
        )
        intrinsics = np.stack([intrinsics_matrix(row["cameraIntrinsicFxFyCxCy"]) for row in rows])

        pre_t0 = time.perf_counter()
        imgs_cpu, ex_pre, in_pre = model._preprocess_inputs(
            image_paths,
            extrinsics,
            intrinsics,
            process_res,
            process_res_method,
        )
        pre_ms = (time.perf_counter() - pre_t0) * 1000.0
        imgs, ex_t, in_t = model._prepare_model_inputs(imgs_cpu, ex_pre, in_pre)
        ex_t_norm = model._normalize_extrinsics(ex_t.clone())

        fw_t0 = time.perf_counter()
        raw_output = model._run_model_forward(
            imgs,
            ex_t_norm,
            in_t,
            export_feat_layers=[],
            infer_gs=False,
            use_ray_pose=False,
            ref_view_strategy=ref_view_strategy,
        )
        forward_ms = (time.perf_counter() - fw_t0) * 1000.0

        prediction = model._convert_to_prediction(raw_output)
        _, _, pose_scale, aligned_extrinsics = align_poses_umeyama(
            prediction.extrinsics,
            tensor_to_numpy(ex_pre),
            ransac=len(rows) >= 10,
            return_aligned=True,
            random_state=42,
        )
        prediction.intrinsics = tensor_to_numpy(in_pre)
        prediction.extrinsics = tensor_to_numpy(ex_pre)[..., :3, :]
        prediction.depth = np.asarray(prediction.depth, dtype=np.float32) / float(pose_scale)
        prediction = model._add_processed_images(prediction, imgs_cpu)

        depth = np.asarray(prediction.depth, dtype=np.float32)
        conf = np.asarray(prediction.conf, dtype=np.float32)
        pred_intrinsics = np.asarray(prediction.intrinsics, dtype=np.float32)
        pred_extrinsics = np.asarray(prediction.extrinsics, dtype=np.float32)
        processed_images = processed_images_to_uint8(np.asarray(prediction.processed_images))

        outputs = {}
        if save_arrays:
            out_dir.mkdir(parents=True, exist_ok=True)
            outputs = {
                "depth_npy": str(out_dir / "pytorch_depth.npy"),
                "conf_npy": str(out_dir / "pytorch_conf.npy"),
                "intrinsics_npy": str(out_dir / "pytorch_intrinsics.npy"),
                "extrinsics_npy": str(out_dir / "pytorch_extrinsics.npy"),
                "processed_images_npy": str(out_dir / "pytorch_processed_images.npy"),
            }
            np.save(out_dir / "pytorch_depth.npy", depth)
            np.save(out_dir / "pytorch_conf.npy", conf)
            np.save(out_dir / "pytorch_intrinsics.npy", pred_intrinsics)
            np.save(out_dir / "pytorch_extrinsics.npy", pred_extrinsics)
            np.save(out_dir / "pytorch_processed_images.npy", processed_images)

        attempt.update(
            {
                "status": "success",
                "preprocess_ms": pre_ms,
                "forward_ms": forward_ms,
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
                "rss_after_mb": rss_mb(),
                "processed_shape_nchw": list(imgs_cpu.shape),
                "output_shapes": {
                    "depth": list(depth.shape),
                    "conf": list(conf.shape),
                    "intrinsics": list(pred_intrinsics.shape),
                    "extrinsics": list(pred_extrinsics.shape),
                    "processed_images": list(processed_images.shape),
                    "aligned_extrinsics": list(np.asarray(aligned_extrinsics).shape),
                },
                "official_alignment": {
                    "umeyama_scale": float(pose_scale),
                    "ransac": len(rows) >= 10,
                },
                "depth": summarize_array(depth.reshape(-1)),
                "confidence": summarize_array(conf.reshape(-1)),
                "pred_intrinsics": {
                    "fx": summarize_array(pred_intrinsics[:, 0, 0]),
                    "fy": summarize_array(pred_intrinsics[:, 1, 1]),
                },
                "outputs": outputs,
            }
        )
    except Exception as exc:
        attempt.update(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback_tail": traceback.format_exc().splitlines()[-12:],
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0,
                "rss_after_mb": rss_mb(),
            }
        )
    return attempt


def choose_device(torch: Any, requested: str) -> Any:
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(requested)


def cleanup(torch: Any, device: Any) -> None:
    gc.collect()
    if device.type == "cuda" and torch.cuda.is_available():
        torch.cuda.empty_cache()
    if device.type == "mps" and hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
        torch.mps.empty_cache()


def tensor_to_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def resolve_image(frames_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else frames_dir / path


def intrinsics_matrix(values: list[float]) -> np.ndarray:
    if len(values) == 4:
        fx, fy, cx, cy = [float(value) for value in values]
        return np.asarray([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float32)
    arr = np.asarray(values, dtype=np.float32)
    if arr.size != 9:
        raise ValueError(f"Expected 4 or 9 intrinsics values, got {arr.size}")
    return arr.reshape(3, 3)


def processed_images_to_uint8(images: np.ndarray) -> np.ndarray:
    arr = np.asarray(images)
    if arr.ndim != 4:
        raise ValueError(f"Expected NHWC image batch, got {arr.shape}")
    if arr.shape[1] == 3 and arr.shape[-1] != 3:
        arr = np.transpose(arr, (0, 2, 3, 1))
    if np.issubdtype(arr.dtype, np.floating):
        if float(np.nanmax(arr)) <= 1.5:
            arr = arr * 255.0
        arr = np.clip(arr, 0, 255)
    return arr.astype(np.uint8)


def summarize_array(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"count": 0}
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p05": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
    }


def compact_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    keys = ["k", "process_res", "device", "status", "processed_shape_nchw", "output_shapes", "error_type", "error"]
    return {key: attempt[key] for key in keys if key in attempt}


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "out_dir": Path(report["attempts"][0]["out_dir"]).parents[0].as_posix() if report["attempts"] else None,
        "successes": [
            {"k": row["k"], "process_res": row["process_res"], "shape": row.get("processed_shape_nchw")}
            for row in report["attempts"]
            if row["status"] == "success"
        ],
        "failures": [
            {"k": row["k"], "process_res": row["process_res"], "error": row.get("error")}
            for row in report["attempts"]
            if row["status"] != "success"
        ],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official PyTorch K Sweep",
        "",
        "## Parameters",
        "",
        f"- device: `{report['parameters']['device']}`",
        f"- process_res: `{report['parameters']['process_res']}`",
        f"- k_values: `{report['parameters']['k_values']}`",
        f"- save_arrays: `{report['parameters']['save_arrays']}`",
        "",
        "## Attempts",
        "",
        "| K | process_res | status | shape | forward ms | error |",
        "|---:|---:|---|---|---:|---|",
    ]
    for row in report["attempts"]:
        shape = row.get("processed_shape_nchw")
        lines.append(
            "| {k} | {res} | {status} | {shape} | {forward} | {error} |".format(
                k=row["k"],
                res=row["process_res"],
                status=row["status"],
                shape="-" if shape is None else "x".join(str(v) for v in shape),
                forward="-" if row.get("forward_ms") is None else f"{row['forward_ms']:.1f}",
                error=(row.get("error") or "-").replace("\n", " "),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return usage / (1024.0 * 1024.0)
    return usage / 1024.0


if __name__ == "__main__":
    raise SystemExit(main())
