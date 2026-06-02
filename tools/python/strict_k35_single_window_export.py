#!/usr/bin/env python3
"""Export one strict DA3 K35 window as a point cloud plus diagnostics."""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image, ImageOps

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--da3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_000")
    parser.add_argument("--prefix", default="strict_window_000")
    parser.add_argument("--sample-ratio", type=float, default=0.006)
    parser.add_argument("--conf-threshold-coef", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=35)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    reports = read_json(args.da3_dir / "mac_da3_window_reports.json")
    window_reports = {str(row["windowID"]): row for row in reports.get("windows", [])}
    if args.window_id not in window_reports:
        raise KeyError(f"{args.window_id} not found in {args.da3_dir / 'mac_da3_window_reports.json'}")

    rng = np.random.default_rng(args.seed)
    export = export_window(
        window_report=window_reports[args.window_id],
        capture_dir=args.capture_dir,
        da3_dir=args.da3_dir,
        sample_ratio=args.sample_ratio,
        conf_threshold_coef=args.conf_threshold_coef,
        rng=rng,
    )
    ply_path = args.out_dir / f"{args.prefix}_single_rgb.ply"
    png_path = args.out_dir / f"{args.prefix}_single_views.png"
    write_point_cloud(ply_path, export["points"], export["colors"])
    write_views_png(png_path, export["points"], export["colors"], title=f"{args.prefix} single window")

    report = {
        "schema_version": "pocketworld_strict_k35_single_window_diagnostics_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "da3_dir": str(args.da3_dir),
            "window_id": args.window_id,
        },
        "parameters": {
            "sample_ratio": args.sample_ratio,
            "conf_threshold_coef": args.conf_threshold_coef,
            "seed": args.seed,
        },
        "outputs": {
            "single_ply": str(ply_path),
            "single_views_png": str(png_path),
        },
        "metrics": export["metrics"],
    }
    write_json(args.out_dir / f"{args.prefix}_single_report.json", report)
    write_markdown(args.out_dir / f"{args.prefix}_single_report_zh.md", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def export_window(
    *,
    window_report: dict[str, Any],
    capture_dir: Path,
    da3_dir: Path,
    sample_ratio: float,
    conf_threshold_coef: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    points_all: list[np.ndarray] = []
    colors_all: list[np.ndarray] = []
    depth_values: list[np.ndarray] = []
    conf_values: list[np.ndarray] = []
    camera_centers: list[np.ndarray] = []
    fx_values: list[float] = []
    fy_values: list[float] = []
    inference_ms: list[float] = []
    valid_before = 0
    frame_metrics = []

    frames = sorted(window_report.get("frames", []), key=lambda row: int(row.get("windowSlot", 0)))
    for frame in frames:
        height = int(frame["depthHeight"])
        width = int(frame["depthWidth"])
        depth = np.fromfile(da3_dir / str(frame["relativeDepthPath"]), dtype="<f4").reshape(height, width)
        conf = np.fromfile(da3_dir / str(frame["confidencePath"]), dtype="<f4").reshape(height, width)
        intrinsics = np.fromfile(da3_dir / str(frame["predIntrinsicsPath"]), dtype="<f4").reshape(3, 3)
        extrinsics = np.fromfile(da3_dir / str(frame["predExtrinsicsPath"]), dtype="<f4").reshape(3, 4)

        point_map = depth_to_point_map(depth, intrinsics, extrinsics)
        flat_points = point_map.reshape(-1, 3)
        flat_conf = conf.reshape(-1)
        threshold = float(np.nanmean(conf)) * conf_threshold_coef
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
            colors = load_frame_colors(frame, capture_dir).reshape(-1, 3)[selected]
            points = flat_points[selected].astype(np.float32)
            finite = np.isfinite(points).all(axis=1)
            points_all.append(points[finite])
            colors_all.append(colors[finite])

        finite_depth = depth[np.isfinite(depth)]
        finite_conf = conf[np.isfinite(conf)]
        if finite_depth.size:
            depth_values.append(finite_depth.astype(np.float32))
        if finite_conf.size:
            conf_values.append(finite_conf.astype(np.float32))

        center = camera_center_from_w2c(extrinsics)
        camera_centers.append(center)
        fx_values.append(float(intrinsics[0, 0]))
        fy_values.append(float(intrinsics[1, 1]))
        inference_ms.append(float(frame.get("inferenceMs") or 0.0))
        frame_metrics.append(
            {
                "frame_id": frame.get("frameID"),
                "window_slot": int(frame.get("windowSlot", 0)),
                "valid_point_count_before_sampling": int(valid_indices.size),
                "sampled_point_count": int(selected.size),
                "depth": summarize_array(finite_depth),
                "confidence": summarize_array(finite_conf),
                "camera_center": [float(v) for v in center],
                "fx": float(intrinsics[0, 0]),
                "fy": float(intrinsics[1, 1]),
            }
        )

    if not points_all:
        raise RuntimeError("No sampled points exported")
    points_cat = np.concatenate(points_all, axis=0)
    colors_cat = np.concatenate(colors_all, axis=0)
    depth_cat = np.concatenate(depth_values, axis=0) if depth_values else np.array([], dtype=np.float32)
    conf_cat = np.concatenate(conf_values, axis=0) if conf_values else np.array([], dtype=np.float32)
    centers = np.stack(camera_centers, axis=0) if camera_centers else np.zeros((0, 3), dtype=np.float32)
    cloud = cloud_metrics(points_cat)
    metrics = {
        "window_id": window_report.get("windowID"),
        "frame_slot_count": len(frames),
        "valid_point_count_before_sampling": int(valid_before),
        "sampled_point_count": int(points_cat.shape[0]),
        "point_cloud": cloud,
        "depth": summarize_array(depth_cat),
        "confidence": summarize_array(conf_cat),
        "pose": pose_metrics(centers),
        "pred_intrinsics": {
            "fx": summarize_numbers(fx_values),
            "fy": summarize_numbers(fy_values),
        },
        "inference_ms": summarize_numbers(inference_ms),
        "frames": frame_metrics,
    }
    return {"points": points_cat, "colors": colors_cat, "metrics": metrics}


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


def camera_center_from_w2c(extrinsics: np.ndarray) -> np.ndarray:
    rotation = extrinsics[:3, :3].astype(np.float64)
    translation = extrinsics[:3, 3].astype(np.float64)
    return (-rotation.T @ translation).astype(np.float32)


def load_frame_colors(frame: dict[str, Any], capture_dir: Path) -> np.ndarray:
    width = int(frame["depthWidth"])
    height = int(frame["depthHeight"])
    with Image.open(capture_dir / str(frame["imageRelativePath"])) as image:
        image = ImageOps.exif_transpose(image).convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
        return np.asarray(image, dtype=np.uint8)


def write_point_cloud(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    path.parent.mkdir(parents=True, exist_ok=True)
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


def pose_metrics(centers: np.ndarray) -> dict[str, Any]:
    if centers.size == 0:
        return {"count": 0}
    lo = np.min(centers, axis=0)
    hi = np.max(centers, axis=0)
    extent = hi - lo
    radii = np.linalg.norm(centers - np.mean(centers, axis=0), axis=1)
    return {
        "count": int(centers.shape[0]),
        "camera_center_min": [float(v) for v in lo],
        "camera_center_max": [float(v) for v in hi],
        "camera_center_extent": [float(v) for v in extent],
        "camera_center_diag": float(np.linalg.norm(extent)),
        "center_radius_mean": float(np.mean(radii)),
        "center_radius_max": float(np.max(radii)),
    }


def summarize_array(values: np.ndarray) -> dict[str, Any]:
    if values.size == 0:
        return {"count": 0}
    return {
        "count": int(values.size),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "p05": float(np.percentile(values, 5)),
        "p95": float(np.percentile(values, 95)),
    }


def summarize_numbers(values: list[float]) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    return summarize_array(arr)


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    cloud = metrics["point_cloud"]
    depth = metrics["depth"]
    pose = metrics["pose"]
    lines = [
        "# Strict K35 单窗诊断",
        "",
        f"- window: `{metrics['window_id']}`",
        f"- sampled points: `{metrics['sampled_point_count']}`",
        f"- bbox diag p01-p99: `{cloud['bbox_diag_p01_p99']:.6f}`",
        f"- depth min/max/mean: `{depth['min']:.6f}` / `{depth['max']:.6f}` / `{depth['mean']:.6f}`",
        f"- camera center diag: `{pose['camera_center_diag']:.6f}`",
        "",
        "## 输出",
        "",
        f"- PLY: `{report['outputs']['single_ply']}`",
        f"- views: `{report['outputs']['single_views_png']}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
