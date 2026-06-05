#!/usr/bin/env python3
"""Export one official Depth Anything 3 PyTorch window for diagnostics."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import resource
import struct
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--official-src", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--device", default="mps", choices=["auto", "cpu", "mps", "cuda"])
    parser.add_argument("--process-res", type=int, default=252)
    parser.add_argument("--process-res-method", default="upper_bound_resize")
    parser.add_argument("--sample-ratio", type=float, default=0.006)
    parser.add_argument("--conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--ref-view-strategy", default="saddle_balanced")
    parser.add_argument("--seed", type=int, default=35)
    parser.add_argument(
        "--camera-mode",
        choices=["pose_conditioned", "image_only"],
        default="pose_conditioned",
        help=(
            "pose_conditioned mirrors the optional DA3 API mode with input cameras; "
            "image_only mirrors official DA3-Streaming's default model.inference(images, ...)."
        ),
    )
    args = parser.parse_args()

    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.official_src))
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    import torch
    from depth_anything_3.api import DepthAnything3
    from depth_anything_3.utils.pose_align import align_poses_umeyama

    manifest = read_json(args.manifest)
    rows = list(manifest.get("frames") or [])
    image_paths = [str(resolve_image(args.frames_dir, row["jpegPath"])) for row in rows]
    extrinsics = None
    intrinsics = None
    if args.camera_mode == "pose_conditioned":
        extrinsics = np.stack([np.asarray(row["cameraExtrinsic4x4"], dtype=np.float32).reshape(4, 4) for row in rows])
        intrinsics = np.stack([intrinsics_matrix(row["cameraIntrinsicFxFyCxCy"]) for row in rows])

    device = choose_device(torch, args.device)
    load_t0 = time.perf_counter()
    model = DepthAnything3.from_pretrained(str(args.model_path))
    model = model.to(device=device)
    model.model.eval()
    load_ms = (time.perf_counter() - load_t0) * 1000.0

    rss_before = rss_mb()
    run_t0 = time.perf_counter()
    imgs_cpu, ex_pre, in_pre = model._preprocess_inputs(
        image_paths,
        extrinsics,
        intrinsics,
        args.process_res,
        args.process_res_method,
    )
    imgs, ex_t, in_t = model._prepare_model_inputs(imgs_cpu, ex_pre, in_pre)
    ex_t_norm = model._normalize_extrinsics(ex_t.clone() if ex_t is not None else None)
    raw_output = model._run_model_forward(
        imgs,
        ex_t_norm,
        in_t,
        export_feat_layers=[],
        infer_gs=False,
        use_ray_pose=False,
        ref_view_strategy=args.ref_view_strategy,
    )
    prediction = model._convert_to_prediction(raw_output)
    pose_scale = None
    aligned_extrinsics = None
    if args.camera_mode == "pose_conditioned":
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
    run_ms = (time.perf_counter() - run_t0) * 1000.0
    rss_after = rss_mb()

    depth = np.asarray(prediction.depth, dtype=np.float32)
    conf = np.asarray(prediction.conf, dtype=np.float32)
    pred_intrinsics = np.asarray(prediction.intrinsics, dtype=np.float32)
    pred_extrinsics = np.asarray(prediction.extrinsics, dtype=np.float32)
    images = processed_images_to_uint8(np.asarray(prediction.processed_images))

    np.save(args.out_dir / "pytorch_depth.npy", depth)
    np.save(args.out_dir / "pytorch_conf.npy", conf)
    np.save(args.out_dir / "pytorch_intrinsics.npy", pred_intrinsics)
    np.save(args.out_dir / "pytorch_extrinsics.npy", pred_extrinsics)
    np.save(args.out_dir / "pytorch_processed_images.npy", images)

    rng = np.random.default_rng(args.seed)
    cloud = sample_cloud(
        depth=depth,
        conf=conf,
        intrinsics=pred_intrinsics,
        extrinsics=pred_extrinsics,
        images=images,
        sample_ratio=args.sample_ratio,
        conf_threshold_coef=args.conf_threshold_coef,
        rng=rng,
    )
    ply_path = args.out_dir / f"official_pytorch_{args.camera_mode}_k35_process_res_{args.process_res}_single_rgb.ply"
    png_path = args.out_dir / f"official_pytorch_{args.camera_mode}_k35_process_res_{args.process_res}_single_views.png"
    write_point_cloud(ply_path, cloud["points"], cloud["colors"])
    write_views_png(
        png_path,
        cloud["points"],
        cloud["colors"],
        title=f"official PyTorch {args.camera_mode} K35 process_res={args.process_res}",
    )

    report = {
        "schema_version": "pocketworld_official_pytorch_window_export_v1",
        "note": "process_res may be lower than the CoreML 476x742 target; use this as a PyTorch API/contract diagnostic, not final quality parity.",
        "inputs": {
            "frames_dir": str(args.frames_dir),
            "manifest": str(args.manifest),
            "model_path": str(args.model_path),
            "official_src": str(args.official_src),
        },
        "parameters": {
            "device": str(device),
            "process_res": args.process_res,
            "process_res_method": args.process_res_method,
            "camera_mode": args.camera_mode,
            "ref_view_strategy": args.ref_view_strategy,
            "sample_ratio": args.sample_ratio,
            "conf_threshold_coef": args.conf_threshold_coef,
            "conf_threshold_coef_source": "npz_output_process.py CLI default is 0.5; this window-export PLY is diagnostic and still uses per-frame visualization sampling.",
        },
        "runtime": {
            "torch": torch.__version__,
            "load_ms": load_ms,
            "run_ms": run_ms,
            "rss_before_mb": rss_before,
            "rss_after_mb": rss_after,
            "rss_delta_mb": rss_after - rss_before,
        },
        "official_alignment": {
            "mode": args.camera_mode,
            "input_camera_umeyama_applied": args.camera_mode == "pose_conditioned",
            "umeyama_scale": None if pose_scale is None else float(pose_scale),
            "aligned_extrinsics_shape": None if aligned_extrinsics is None else list(np.asarray(aligned_extrinsics).shape),
        },
        "outputs": {
            "depth_npy": str(args.out_dir / "pytorch_depth.npy"),
            "conf_npy": str(args.out_dir / "pytorch_conf.npy"),
            "intrinsics_npy": str(args.out_dir / "pytorch_intrinsics.npy"),
            "extrinsics_npy": str(args.out_dir / "pytorch_extrinsics.npy"),
            "processed_images_npy": str(args.out_dir / "pytorch_processed_images.npy"),
            "single_ply": str(ply_path),
            "single_views_png": str(png_path),
        },
        "metrics": {
            "frame_count": int(depth.shape[0]),
            "processed_shape_nhwc": list(images.shape),
            "depth": summarize_array(depth.reshape(-1)),
            "confidence": summarize_array(conf.reshape(-1)),
            "pose": pose_metrics(pred_extrinsics),
            "pred_intrinsics": {
                "fx": summarize_array(pred_intrinsics[:, 0, 0]),
                "fy": summarize_array(pred_intrinsics[:, 1, 1]),
            },
            "point_cloud": cloud_metrics(cloud["points"]),
            "valid_point_count_before_sampling": int(cloud["valid_point_count_before_sampling"]),
            "sampled_point_count": int(cloud["points"].shape[0]),
        },
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    write_json(args.out_dir / "official_pytorch_window_000_export_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def choose_device(torch: Any, requested: str) -> Any:
    if requested == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(requested)


def tensor_to_numpy(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def resolve_image(frames_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else frames_dir / path


def intrinsics_matrix(values: list[float]) -> np.ndarray:
    if len(values) == 4:
        fx, fy, cx, cy = [float(v) for v in values]
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
    arr = np.asarray(arr)
    if np.issubdtype(arr.dtype, np.floating):
        if float(np.nanmax(arr)) <= 1.5:
            arr = arr * 255.0
        arr = np.clip(arr, 0, 255)
    return arr.astype(np.uint8)


def sample_cloud(
    *,
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    images: np.ndarray,
    sample_ratio: float,
    conf_threshold_coef: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    points_all: list[np.ndarray] = []
    colors_all: list[np.ndarray] = []
    valid_before = 0
    for index in range(depth.shape[0]):
        point_map = depth_to_point_map(depth[index], intrinsics[index], extrinsics[index])
        flat_points = point_map.reshape(-1, 3)
        flat_conf = conf[index].reshape(-1)
        threshold = float(np.nanmean(conf[index])) * conf_threshold_coef
        mask = (
            np.isfinite(flat_points).all(axis=1)
            & np.isfinite(flat_conf)
            & (flat_conf >= threshold)
            & (flat_conf > 1e-5)
        )
        valid_indices = np.flatnonzero(mask)
        valid_before += int(valid_indices.size)
        sample_count = max(1, int(valid_indices.size * sample_ratio)) if valid_indices.size else 0
        if sample_count and sample_count < valid_indices.size:
            selected = rng.choice(valid_indices, size=sample_count, replace=False)
        else:
            selected = valid_indices
        if selected.size:
            points = flat_points[selected].astype(np.float32)
            colors = images[index].reshape(-1, 3)[selected].astype(np.uint8)
            finite = np.isfinite(points).all(axis=1)
            points_all.append(points[finite])
            colors_all.append(colors[finite])
    if not points_all:
        raise RuntimeError("No sampled PyTorch points")
    return {
        "points": np.concatenate(points_all, axis=0),
        "colors": np.concatenate(colors_all, axis=0),
        "valid_point_count_before_sampling": valid_before,
    }


def depth_to_point_map(depth: np.ndarray, intrinsics: np.ndarray, extrinsics: np.ndarray) -> np.ndarray:
    height, width = depth.shape
    u, v = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    pixels = np.stack([u, v, np.ones_like(u)], axis=-1).reshape(-1, 3)
    rays = pixels @ np.linalg.inv(intrinsics.astype(np.float64)).T
    camera_points = rays * depth.reshape(-1, 1).astype(np.float64)
    camera_points_h = np.concatenate([camera_points, np.ones((camera_points.shape[0], 1))], axis=1)
    w2c = np.eye(4, dtype=np.float64)
    w2c[:3, :4] = extrinsics.astype(np.float64)
    c2w = np.linalg.inv(w2c)
    world_points = camera_points_h @ c2w.T
    return world_points[:, :3].reshape(height, width, 3)


def write_point_cloud(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    colors_u8 = np.clip(colors, 0, 255).astype(np.uint8)
    points_f32 = points.astype("<f4", copy=False)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {points_f32.shape[0]}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    with path.open("wb") as handle:
        handle.write(header)
        for point, color in zip(points_f32, colors_u8):
            handle.write(struct.pack("<fffBBB", float(point[0]), float(point[1]), float(point[2]), int(color[0]), int(color[1]), int(color[2])))


def write_views_png(path: Path, points: np.ndarray, colors: np.ndarray, *, title: str) -> None:
    rng = np.random.default_rng(123)
    pts = points.astype(np.float64)
    cols = np.clip(colors.astype(np.float64) / 255.0, 0.0, 1.0)
    lo = np.percentile(pts, 1.0, axis=0)
    hi = np.percentile(pts, 99.0, axis=0)
    mask = np.all((pts >= lo) & (pts <= hi), axis=1)
    pts = pts[mask]
    cols = cols[mask]
    if pts.shape[0] > 160_000:
        idx = rng.choice(pts.shape[0], size=160_000, replace=False)
        pts = pts[idx]
        cols = cols[idx]
    views = [("front XY", (0, 1)), ("top XZ", (0, 2)), ("side YZ", (1, 2))]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), facecolor="white")
    fig.suptitle(title)
    for ax, (view_name, (a, b)) in zip(axes, views):
        ax.scatter(pts[:, a], pts[:, b], s=0.35, c=cols, linewidths=0)
        ax.set_aspect("equal", "box")
        ax.set_title(view_name)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)


def cloud_metrics(points: np.ndarray) -> dict[str, Any]:
    lo = np.percentile(points, 1.0, axis=0)
    hi = np.percentile(points, 99.0, axis=0)
    extent = hi - lo
    return {
        "point_count": int(points.shape[0]),
        "bbox_p01": [float(v) for v in lo],
        "bbox_p99": [float(v) for v in hi],
        "bbox_extent_p01_p99": [float(v) for v in extent],
        "bbox_diag_p01_p99": float(np.linalg.norm(extent)),
    }


def pose_metrics(extrinsics: np.ndarray) -> dict[str, Any]:
    centers = []
    for extrinsic in extrinsics:
        rotation = extrinsic[:3, :3].astype(np.float64)
        translation = extrinsic[:3, 3].astype(np.float64)
        centers.append((-rotation.T @ translation).astype(np.float32))
    centers_arr = np.stack(centers, axis=0)
    lo = np.min(centers_arr, axis=0)
    hi = np.max(centers_arr, axis=0)
    extent = hi - lo
    radii = np.linalg.norm(centers_arr - np.mean(centers_arr, axis=0), axis=1)
    return {
        "count": int(centers_arr.shape[0]),
        "camera_center_min": [float(v) for v in lo],
        "camera_center_max": [float(v) for v in hi],
        "camera_center_extent": [float(v) for v in extent],
        "camera_center_diag": float(np.linalg.norm(extent)),
        "center_radius_mean": float(np.mean(radii)),
        "center_radius_max": float(np.max(radii)),
    }


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


def rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return usage / (1024.0 * 1024.0)
    return usage / 1024.0


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
