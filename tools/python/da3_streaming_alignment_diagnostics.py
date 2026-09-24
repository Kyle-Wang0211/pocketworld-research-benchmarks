#!/usr/bin/env python3
"""Diagnose where DA3-BASE K35 streaming point clouds start to drift."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image, ImageOps

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RESEARCH_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = RESEARCH_ROOT / "tools/python"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import official_k35_loop_sim3_evaluate as loop_eval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--da3-dir", type=Path, required=True)
    parser.add_argument("--transforms-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sample-ratio", type=float, default=0.006)
    parser.add_argument("--shared-sample-ratio", type=float, default=0.01)
    parser.add_argument("--conf-threshold-coef", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=35)
    args = parser.parse_args()

    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    plan = read_json(args.capture_dir / "da3_k_windows.json")
    reports = read_json(args.da3_dir / "mac_da3_window_reports.json")
    transform_doc = read_json(args.transforms_json)
    transforms = transform_doc["transforms"]

    window_reports = {str(row["windowID"]): row for row in reports.get("windows", [])}
    plan_windows = list(plan.get("windows", []))
    window_ids = [str(window["id"]) for window in plan_windows]

    report: dict[str, Any] = {
        "schema_version": "pocketworld_da3_streaming_alignment_diagnostics_v1",
        "route": "DA3-BASE K35@476x742 official sequential chunks + SelaVPR++ loop + official Sim3LoopOptimizer; point cloud diagnostics only",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "da3_dir": str(args.da3_dir),
            "transforms_json": str(args.transforms_json),
        },
        "windows": {
            "count": len(window_ids),
            "window_ids": window_ids,
            "chunk_size": plan.get("windowSize"),
            "overlap": (plan.get("windowingPolicy") or {}).get("overlap"),
            "step": (plan.get("windowingPolicy") or {}).get("step"),
        },
        "outputs": {},
        "metrics": {},
    }

    print("Exporting window_000 single-window point cloud...")
    w0 = export_window_cloud(
        window_id="window_000",
        window_report=window_reports["window_000"],
        transform=identity_transform(),
        capture_dir=args.capture_dir,
        da3_dir=args.da3_dir,
        sample_ratio=args.sample_ratio,
        conf_threshold_coef=args.conf_threshold_coef,
        rng=rng,
    )
    w0_ply = args.out_dir / "window_000_single_rgb.ply"
    w0_png = args.out_dir / "window_000_single_views.png"
    write_point_cloud(w0_ply, w0["points"], w0["colors"])
    write_views_png(w0_png, w0["points"], w0["colors"], title="window_000 single window")
    report["outputs"]["window_000_single_ply"] = str(w0_ply)
    report["outputs"]["window_000_single_views_png"] = str(w0_png)
    report["metrics"]["window_000"] = cloud_metrics(w0["points"], extra=w0["stats"])

    print("Exporting window_000 + window_001 shared-frame alignment diagnostics...")
    shared_report = export_shared_alignment(
        plan_windows=plan_windows,
        window_reports=window_reports,
        transforms=transforms,
        capture_dir=args.capture_dir,
        da3_dir=args.da3_dir,
        out_dir=args.out_dir,
        sample_ratio=args.shared_sample_ratio,
        conf_threshold_coef=args.conf_threshold_coef,
        rng=rng,
    )
    report["outputs"].update(shared_report["outputs"])
    report["metrics"]["window_000_001_shared"] = shared_report["metrics"]

    print("Exporting incremental 1/2/4/8/24 window point clouds...")
    incremental = export_incremental_clouds(
        window_ids=window_ids,
        window_reports=window_reports,
        transforms=transforms,
        capture_dir=args.capture_dir,
        da3_dir=args.da3_dir,
        out_dir=args.out_dir,
        sample_ratio=args.sample_ratio,
        conf_threshold_coef=args.conf_threshold_coef,
        rng=rng,
    )
    report["outputs"]["incremental"] = incremental["outputs"]
    report["metrics"]["incremental"] = incremental["metrics"]

    report["elapsed_s"] = round(time.perf_counter() - started, 3)
    write_json(args.out_dir / "alignment_diagnostics_report.json", report)
    write_markdown(args.out_dir / "alignment_diagnostics_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def export_window_cloud(
    *,
    window_id: str,
    window_report: dict[str, Any],
    transform: dict[str, Any],
    capture_dir: Path,
    da3_dir: Path,
    sample_ratio: float,
    conf_threshold_coef: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    points_all: list[np.ndarray] = []
    colors_all: list[np.ndarray] = []
    valid_before = 0
    frames = sorted(window_report.get("frames", []), key=lambda row: int(row.get("windowSlot", 0)))
    for frame in frames:
        points, colors, valid = sample_frame_points(
            frame,
            capture_dir=capture_dir,
            da3_dir=da3_dir,
            transform=transform,
            sample_ratio=sample_ratio,
            conf_threshold_coef=conf_threshold_coef,
            rng=rng,
        )
        valid_before += valid
        if points.size:
            points_all.append(points)
            colors_all.append(colors)
    if not points_all:
        raise RuntimeError(f"No points exported for {window_id}")
    points_cat = np.concatenate(points_all, axis=0)
    colors_cat = np.concatenate(colors_all, axis=0)
    return {
        "points": points_cat,
        "colors": colors_cat,
        "stats": {
            "window_id": window_id,
            "frame_slot_count": len(frames),
            "valid_point_count_before_sampling": int(valid_before),
            "sampled_point_count": int(points_cat.shape[0]),
        },
    }


def export_shared_alignment(
    *,
    plan_windows: list[dict[str, Any]],
    window_reports: dict[str, dict[str, Any]],
    transforms: dict[str, dict[str, Any]],
    capture_dir: Path,
    da3_dir: Path,
    out_dir: Path,
    sample_ratio: float,
    conf_threshold_coef: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    window_1_plan = next(window for window in plan_windows if str(window.get("id")) == "window_001")
    shared_ids = [str(frame_id) for frame_id in window_1_plan.get("bridgeFrameIDs", [])]
    rows0 = loop_eval.rows_by_frame(window_reports["window_000"])
    rows1 = loop_eval.rows_by_frame(window_reports["window_001"])
    paired = [(rows0[fid], rows1[fid]) for fid in shared_ids if fid in rows0 and fid in rows1]
    if not paired:
        raise RuntimeError("window_000/window_001 has no shared rows")

    transform_001 = transforms["window_001"]
    residual_stats = compute_shared_residual(
        paired=paired,
        da3_dir=da3_dir,
        source_transform=transform_001,
    )

    parent_points: list[np.ndarray] = []
    parent_colors: list[np.ndarray] = []
    current_points: list[np.ndarray] = []
    current_colors: list[np.ndarray] = []
    current_source_colors: list[np.ndarray] = []
    parent_source_colors: list[np.ndarray] = []
    valid_before = 0

    for parent_row, current_row in paired:
        pts0, rgb0, valid0 = sample_frame_points(
            parent_row,
            capture_dir=capture_dir,
            da3_dir=da3_dir,
            transform=identity_transform(),
            sample_ratio=sample_ratio,
            conf_threshold_coef=conf_threshold_coef,
            rng=rng,
        )
        pts1, rgb1, valid1 = sample_frame_points(
            current_row,
            capture_dir=capture_dir,
            da3_dir=da3_dir,
            transform=transform_001,
            sample_ratio=sample_ratio,
            conf_threshold_coef=conf_threshold_coef,
            rng=rng,
        )
        valid_before += valid0 + valid1
        if pts0.size:
            parent_points.append(pts0)
            parent_colors.append(rgb0)
            parent_source_colors.append(np.tile(np.array([[0.05, 0.35, 1.0]], dtype=np.float32), (pts0.shape[0], 1)))
        if pts1.size:
            current_points.append(pts1)
            current_colors.append(rgb1)
            current_source_colors.append(np.tile(np.array([[1.0, 0.45, 0.05]], dtype=np.float32), (pts1.shape[0], 1)))

    rgb_points = np.concatenate(parent_points + current_points, axis=0)
    rgb_colors = np.concatenate(parent_colors + current_colors, axis=0)
    source_points = rgb_points
    source_colors = np.concatenate(parent_source_colors + current_source_colors, axis=0)

    rgb_ply = out_dir / "window_000_001_shared_aligned_rgb.ply"
    source_ply = out_dir / "window_000_001_shared_aligned_source_color.ply"
    source_png = out_dir / "window_000_001_shared_source_color_views.png"
    write_point_cloud(rgb_ply, rgb_points, rgb_colors)
    write_point_cloud(source_ply, source_points, source_colors)
    write_views_png(source_png, source_points, source_colors, title="window_000 blue vs window_001 orange")

    return {
        "outputs": {
            "window_000_001_shared_rgb_ply": str(rgb_ply),
            "window_000_001_shared_source_color_ply": str(source_ply),
            "window_000_001_shared_source_color_views_png": str(source_png),
        },
        "metrics": {
            **residual_stats,
            "shared_frame_count": len(paired),
            "shared_frame_ids": shared_ids,
            "valid_point_count_before_sampling": int(valid_before),
            "sampled_point_count": int(rgb_points.shape[0]),
            **cloud_metrics(rgb_points),
        },
    }


def export_incremental_clouds(
    *,
    window_ids: list[str],
    window_reports: dict[str, dict[str, Any]],
    transforms: dict[str, dict[str, Any]],
    capture_dir: Path,
    da3_dir: Path,
    out_dir: Path,
    sample_ratio: float,
    conf_threshold_coef: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    checkpoints = [1, 2, 4, 8, len(window_ids)]
    checkpoints = sorted(set(v for v in checkpoints if 1 <= v <= len(window_ids)))
    points_by_window: list[np.ndarray] = []
    colors_by_window: list[np.ndarray] = []
    metrics: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    for idx, window_id in enumerate(window_ids, start=1):
        transform = transforms.get(window_id) or identity_transform()
        cloud = export_window_cloud(
            window_id=window_id,
            window_report=window_reports[window_id],
            transform=transform,
            capture_dir=capture_dir,
            da3_dir=da3_dir,
            sample_ratio=sample_ratio,
            conf_threshold_coef=conf_threshold_coef,
            rng=rng,
        )
        points_by_window.append(cloud["points"])
        colors_by_window.append(cloud["colors"])
        metrics[window_id] = cloud_metrics(cloud["points"], extra=cloud["stats"])

        if idx in checkpoints:
            label = f"first_{idx:02d}_windows"
            points = np.concatenate(points_by_window, axis=0)
            colors = np.concatenate(colors_by_window, axis=0)
            ply = out_dir / f"{label}_rgb.ply"
            png = out_dir / f"{label}_views.png"
            write_point_cloud(ply, points, colors)
            write_views_png(png, points, colors, title=label)
            outputs[label] = {"ply": str(ply), "views_png": str(png)}
            metrics[label] = cloud_metrics(
                points,
                extra={
                    "window_count": idx,
                    "sampled_point_count": int(points.shape[0]),
                },
            )
            print(f"  wrote {label}: {points.shape[0]:,} points")

    return {"outputs": outputs, "metrics": metrics}


def compute_shared_residual(
    *,
    paired: list[tuple[dict[str, Any], dict[str, Any]]],
    da3_dir: Path,
    source_transform: dict[str, Any],
) -> dict[str, Any]:
    residuals: list[np.ndarray] = []
    point_count = 0
    median_confs: list[float] = []
    payloads = []
    for target_row, source_row in paired:
        target_map, target_conf = loop_eval.load_point_map_and_conf(target_row, da3_dir)
        source_map, source_conf = loop_eval.load_point_map_and_conf(source_row, da3_dir)
        payloads.append((target_map, target_conf, source_map, source_conf))
        median_confs.extend([float(np.median(target_conf)), float(np.median(source_conf))])
    conf_threshold = min(median_confs) * 0.1 if median_confs else 0.0
    for target_map, target_conf, source_map, source_conf in payloads:
        transformed_source = apply_sim3(source_map.reshape(-1, 3), source_transform).reshape(source_map.shape)
        mask = (
            np.isfinite(target_map).all(axis=2)
            & np.isfinite(transformed_source).all(axis=2)
            & np.isfinite(target_conf)
            & np.isfinite(source_conf)
            & (target_conf > conf_threshold)
            & (source_conf > conf_threshold)
        )
        if not np.any(mask):
            continue
        res = np.linalg.norm(transformed_source[mask] - target_map[mask], axis=1)
        residuals.append(res.astype(np.float32))
        point_count += int(res.shape[0])
    if not residuals:
        return {"residual_status": "no_points"}
    residual = np.concatenate(residuals)
    return {
        "residual_status": "estimated",
        "residual_point_count": point_count,
        "residual_rmse": float(np.sqrt(np.mean(residual * residual))),
        "residual_median": float(np.median(residual)),
        "residual_p90": float(np.percentile(residual, 90)),
        "residual_p95": float(np.percentile(residual, 95)),
        "residual_max": float(np.max(residual)),
        "residual_conf_threshold": float(conf_threshold),
    }


def sample_frame_points(
    frame: dict[str, Any],
    *,
    capture_dir: Path,
    da3_dir: Path,
    transform: dict[str, Any],
    sample_ratio: float,
    conf_threshold_coef: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, int]:
    point_map, conf = loop_eval.load_point_map_and_conf(frame, da3_dir)
    flat_points = point_map.reshape(-1, 3)
    flat_conf = conf.reshape(-1)
    threshold = float(np.mean(conf)) * conf_threshold_coef
    mask = np.isfinite(flat_points).all(axis=1) & np.isfinite(flat_conf) & (flat_conf >= threshold) & (flat_conf > 1e-5)
    valid_indices = np.flatnonzero(mask)
    if valid_indices.size == 0:
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.float32), 0
    sample_count = max(1, int(valid_indices.size * sample_ratio))
    if sample_count < valid_indices.size:
        selected = rng.choice(valid_indices, size=sample_count, replace=False)
    else:
        selected = valid_indices
    colors = load_frame_colors(frame, capture_dir).reshape(-1, 3)[selected].astype(np.float32) / 255.0
    points = apply_sim3(flat_points[selected], transform).astype(np.float32)
    finite = np.isfinite(points).all(axis=1)
    return points[finite], colors[finite], int(valid_indices.size)


def load_frame_colors(frame: dict[str, Any], capture_dir: Path) -> np.ndarray:
    width = int(frame["depthWidth"])
    height = int(frame["depthHeight"])
    image = Image.open(capture_dir / str(frame["imageRelativePath"]))
    image = ImageOps.exif_transpose(image).convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


def write_point_cloud(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    import open3d as o3d

    path.parent.mkdir(parents=True, exist_ok=True)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(np.clip(colors.astype(np.float64), 0.0, 1.0))
    o3d.io.write_point_cloud(str(path), pcd, write_ascii=False, compressed=False)


def write_views_png(path: Path, points: np.ndarray, colors: np.ndarray, *, title: str) -> None:
    if points.shape[0] == 0:
        return
    rng = np.random.default_rng(123)
    pts = points.astype(np.float64)
    cols = np.clip(colors.astype(np.float64), 0.0, 1.0)
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


def cloud_metrics(points: np.ndarray, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metrics: dict[str, Any] = dict(extra or {})
    if points.shape[0] == 0:
        metrics.update({"point_count": 0, "status": "empty"})
        return metrics
    lo = np.percentile(points, 1.0, axis=0)
    hi = np.percentile(points, 99.0, axis=0)
    extent = hi - lo
    metrics.update(
        {
            "point_count": int(points.shape[0]),
            "bbox_p01": [float(v) for v in lo],
            "bbox_p99": [float(v) for v in hi],
            "bbox_extent_p01_p99": [float(v) for v in extent],
            "bbox_diag_p01_p99": float(np.linalg.norm(extent)),
        }
    )
    return metrics


def apply_sim3(points: np.ndarray, transform: dict[str, Any]) -> np.ndarray:
    return float(transform["scale"]) * (
        points.astype(np.float64) @ np.asarray(transform["rotation"], dtype=np.float64).T
    ) + np.asarray(transform["translation"], dtype=np.float64)


def identity_transform() -> dict[str, Any]:
    return {"scale": 1.0, "rotation": np.eye(3), "translation": np.zeros(3)}


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "window_000": report["metrics"].get("window_000"),
        "shared": report["metrics"].get("window_000_001_shared"),
        "incremental_keys": list((report["outputs"].get("incremental") or {}).keys()),
        "out_dir": str(Path(report["outputs"]["window_000_single_ply"]).parent),
        "elapsed_s": report["elapsed_s"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    inc = report["metrics"].get("incremental", {})
    lines = [
        "# DA3 Streaming 对齐诊断",
        "",
        "## 路线",
        report["route"],
        "",
        "## 关键指标",
        "",
        "| 项目 | 点数 | bbox diag | RMSE | P90 |",
        "|---|---:|---:|---:|---:|",
    ]
    w0 = report["metrics"].get("window_000", {})
    shared = report["metrics"].get("window_000_001_shared", {})
    lines.append(
        f"| window_000 单窗 | {w0.get('point_count')} | {fmt(w0.get('bbox_diag_p01_p99'))} | - | - |"
    )
    lines.append(
        f"| window_000+001 共享帧 | {shared.get('point_count')} | {fmt(shared.get('bbox_diag_p01_p99'))} | "
        f"{fmt(shared.get('residual_rmse'))} | {fmt(shared.get('residual_p90'))} |"
    )
    for key in ["first_01_windows", "first_02_windows", "first_04_windows", "first_08_windows", "first_24_windows"]:
        if key not in inc:
            continue
        row = inc[key]
        lines.append(f"| {key} | {row.get('point_count')} | {fmt(row.get('bbox_diag_p01_p99'))} | - | - |")
    lines.extend(
        [
            "",
            "## 输出",
            "",
        ]
    )
    for key, value in report.get("outputs", {}).items():
        if isinstance(value, dict):
            lines.append(f"- {key}: `{json.dumps(value, ensure_ascii=False)}`")
        else:
            lines.append(f"- {key}: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt(value: Any) -> str:
    try:
        v = float(value)
    except Exception:
        return "-"
    if not math.isfinite(v):
        return "-"
    return f"{v:.4f}"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
