#!/usr/bin/env python3
"""Export official-save frames after applying official adjacent dense Sim3.

This is a faithful, no-loop DA3-Streaming alignment export:

1. Use official-save slots from the fixed-K35 capture.
2. Read adjacent dense Sim3 edges estimated by
   official_k35_adjacent_dense_sim3_diagnostics.py.
3. Accumulate transforms with DA3-Streaming's accumulate_sim3_transforms rule.
4. Apply the accumulated chunk transform to each saved frame's point cloud.
5. Export with the same core-frame NPZ point-cloud confidence/downsample style used by
   official_save_sequence_pointcloud_export.py.

It does not run loop optimization, point cleanup, Poisson, meshing, or fusion.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from official_save_sequence_pointcloud_export import (  # noqa: E402
    first_order_mismatch,
    load_conf,
    load_depth,
    load_extrinsics,
    load_frame_colors,
    load_intrinsics,
    read_json,
    select_official_save_rows,
    write_json,
)
from strict_k35_window_official_filter_micro_audit import (  # noqa: E402
    as_homogeneous44,
    camera_center_from_w2c,
    cloud_metrics,
    optimized_vectorized_reservoir_sampling,
    pca_metrics,
    pose_metrics,
    summarize_array,
    write_point_cloud,
    write_views_png,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--da3-dir", type=Path, required=True)
    parser.add_argument("--adjacent-sim3-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--npz-sample-ratio", type=float, default=0.015)
    parser.add_argument("--seed", type=int, default=4300)
    parser.add_argument("--name", default="official_adjacent_sim3_full_sequence")
    parser.add_argument(
        "--confidence-mode",
        choices=["streaming_subtract_one", "raw"],
        default="streaming_subtract_one",
        help="DA3-Streaming subtracts 1.0 from prediction.conf before alignment/export.",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    capture = read_json(args.capture_dir / "da3_k_windows.json")
    bundle = read_json(args.capture_dir / "photo_bundle.json")
    reports = read_json(args.da3_dir / "mac_da3_window_reports.json")
    sim3_report = read_json(args.adjacent_sim3_json)

    source_frame_ids = [str(row["id"]) for row in bundle.get("frames", [])]
    selected_rows, selection = select_official_save_rows(capture, reports, source_frame_ids)
    if not selected_rows:
        raise ValueError("No official-save rows selected")

    transform_by_window = build_accumulated_window_transforms(capture, sim3_report)
    conf_mean = compute_conf_mean(selected_rows, args.da3_dir, args.confidence_mode)
    threshold = float(conf_mean * args.npz_conf_threshold_coef)
    valid_count = count_valid_points(
        selected_rows,
        args.da3_dir,
        threshold,
        args.confidence_mode,
    )
    points, colors = reservoir_export(
        selected_rows,
        capture_dir=args.capture_dir,
        da3_dir=args.da3_dir,
        transform_by_window=transform_by_window,
        conf_threshold=threshold,
        confidence_mode=args.confidence_mode,
        sample_ratio=args.npz_sample_ratio,
        seed=args.seed,
        valid_count=valid_count,
    )

    ply_path = args.out_dir / f"{args.name}_adjacent_sim3_npz_streaming_rgb.ply"
    png_path = args.out_dir / f"{args.name}_adjacent_sim3_npz_streaming_views.png"
    write_point_cloud(ply_path, points, colors)
    write_views_png(
        png_path,
        points,
        colors,
        title=f"{args.name} official adjacent Sim3 + NPZ streaming style",
    )

    report = build_report(
        args=args,
        capture=capture,
        source_frame_ids=source_frame_ids,
        selected_rows=selected_rows,
        selection=selection,
        transform_by_window=transform_by_window,
        sim3_report=sim3_report,
        conf_mean=conf_mean,
        threshold=threshold,
        valid_count=valid_count,
        points=points,
        ply_path=ply_path,
        png_path=png_path,
    )
    write_json(args.out_dir / "official_adjacent_sim3_pointcloud_report.json", report)
    write_markdown(args.out_dir / "official_adjacent_sim3_pointcloud_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def build_accumulated_window_transforms(
    capture: dict[str, Any],
    sim3_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    windows = list(capture.get("windows") or [])
    edges = sim3_edges_for_capture(windows, sim3_report)
    if len(edges) != max(0, len(windows) - 1):
        raise ValueError(
            f"Need one estimated adjacent edge per window transition: "
            f"{len(edges)} edges for {len(windows)} windows"
        )

    transforms: dict[str, dict[str, Any]] = {}
    if not windows:
        return transforms
    transforms[str(windows[0]["id"])] = identity_transform()
    cumulative: dict[str, Any] | None = None
    for index, edge in enumerate(edges):
        parent_id = str(windows[index]["id"])
        current_id = str(windows[index + 1]["id"])
        if str(edge.get("parentWindowID")) != parent_id or str(edge.get("currentWindowID")) != current_id:
            raise ValueError(
                "Adjacent edge order does not match capture windows: "
                f"edge {edge.get('parentWindowID')}->{edge.get('currentWindowID')} "
                f"vs capture {parent_id}->{current_id}"
            )
        edge_transform = transform_from_edge(edge)
        cumulative = edge_transform if cumulative is None else compose_sim3(cumulative, edge_transform)
        transforms[current_id] = cumulative
    return transforms


def sim3_edges_for_capture(
    windows: list[dict[str, Any]],
    sim3_report: dict[str, Any],
) -> list[dict[str, Any]]:
    if sim3_report.get("edges"):
        return [edge for edge in sim3_report.get("edges", []) if edge.get("status") == "estimated"]
    optimized = (sim3_report.get("optimizer") or {}).get("optimized_transforms") or []
    edges = []
    for index, transform in enumerate(optimized):
        if index + 1 >= len(windows):
            break
        edges.append(
            {
                "status": "estimated",
                "parentWindowID": str(windows[index]["id"]),
                "currentWindowID": str(windows[index + 1]["id"]),
                "sim3_scale": transform["sim3_scale"],
                "sim3_rotation": transform["sim3_rotation"],
                "sim3_translation": transform["sim3_translation"],
            }
        )
    return edges


def identity_transform() -> dict[str, Any]:
    return {
        "scale": 1.0,
        "rotation": np.eye(3, dtype=np.float64),
        "translation": np.zeros(3, dtype=np.float64),
    }


def transform_from_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "scale": float(edge["sim3_scale"]),
        "rotation": np.asarray(edge["sim3_rotation"], dtype=np.float64).reshape(3, 3),
        "translation": np.asarray(edge["sim3_translation"], dtype=np.float64).reshape(3),
    }


def compose_sim3(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Return first(second(x)), matching DA3 accumulate_sim3_transforms."""
    s1 = float(first["scale"])
    r1 = np.asarray(first["rotation"], dtype=np.float64)
    t1 = np.asarray(first["translation"], dtype=np.float64).reshape(3)
    s2 = float(second["scale"])
    r2 = np.asarray(second["rotation"], dtype=np.float64)
    t2 = np.asarray(second["translation"], dtype=np.float64).reshape(3)
    return {
        "scale": s1 * s2,
        "rotation": r1 @ r2,
        "translation": s1 * (r1 @ t2) + t1,
    }


def apply_sim3(points: np.ndarray, transform: dict[str, Any]) -> np.ndarray:
    scale = float(transform["scale"])
    rotation = np.asarray(transform["rotation"], dtype=np.float64)
    translation = np.asarray(transform["translation"], dtype=np.float64).reshape(3)
    return (scale * (points.astype(np.float64) @ rotation.T) + translation).astype(np.float32)


def normalize_conf(conf: np.ndarray, mode: str) -> np.ndarray:
    out = np.asarray(conf, dtype=np.float32)
    if mode == "streaming_subtract_one":
        out = out - 1.0
    return out


def compute_conf_mean(rows: list[dict[str, Any]], da3_dir: Path, confidence_mode: str) -> float:
    total = 0.0
    count = 0
    for row in rows:
        conf = normalize_conf(load_conf(row, da3_dir), confidence_mode)
        total += float(np.sum(conf.astype(np.float64)))
        count += int(conf.size)
    return total / max(count, 1)


def count_valid_points(
    rows: list[dict[str, Any]],
    da3_dir: Path,
    threshold: float,
    confidence_mode: str,
) -> int:
    count = 0
    for row in rows:
        depth = load_depth(row, da3_dir)
        conf = normalize_conf(load_conf(row, da3_dir), confidence_mode)
        mask = np.isfinite(depth) & np.isfinite(conf) & (conf >= threshold) & (conf > 1e-5)
        count += int(np.count_nonzero(mask))
    return count


def reservoir_export(
    rows: list[dict[str, Any]],
    *,
    capture_dir: Path,
    da3_dir: Path,
    transform_by_window: dict[str, dict[str, Any]],
    conf_threshold: float,
    confidence_mode: str,
    sample_ratio: float,
    seed: int,
    valid_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    num_samples = int(valid_count * sample_ratio) if sample_ratio < 1.0 else valid_count
    if num_samples <= 0:
        return (
            np.zeros((0, 3), dtype=np.float32),
            np.zeros((0, 3), dtype=np.uint8),
        )
    if sample_ratio >= 1.0:
        point_chunks = []
        color_chunks = []
        for row in rows:
            points, colors = row_points_and_colors(
                row,
                capture_dir=capture_dir,
                da3_dir=da3_dir,
                transform_by_window=transform_by_window,
                conf_threshold=conf_threshold,
                confidence_mode=confidence_mode,
            )
            point_chunks.append(points)
            color_chunks.append(colors)
        return np.concatenate(point_chunks, axis=0), np.concatenate(color_chunks, axis=0)

    np.random.seed(seed)
    reservoir_pts = np.zeros((num_samples, 3), dtype=np.float32)
    reservoir_clr = np.zeros((num_samples, 3), dtype=np.uint8)
    count = 0
    for row in rows:
        points, colors = row_points_and_colors(
            row,
            capture_dir=capture_dir,
            da3_dir=da3_dir,
            transform_by_window=transform_by_window,
            conf_threshold=conf_threshold,
            confidence_mode=confidence_mode,
        )
        n_valid = int(points.shape[0])
        if count < num_samples:
            fill_count = min(num_samples - count, n_valid)
            reservoir_pts[count : count + fill_count] = points[:fill_count]
            reservoir_clr[count : count + fill_count] = colors[:fill_count]
            count += fill_count
            if fill_count < n_valid:
                count, reservoir_pts, reservoir_clr = optimized_vectorized_reservoir_sampling(
                    points[fill_count:],
                    colors[fill_count:],
                    count,
                    reservoir_pts,
                    reservoir_clr,
                )
        else:
            count, reservoir_pts, reservoir_clr = optimized_vectorized_reservoir_sampling(
                points,
                colors,
                count,
                reservoir_pts,
                reservoir_clr,
            )
    return reservoir_pts, reservoir_clr


def row_points_and_colors(
    row: dict[str, Any],
    *,
    capture_dir: Path,
    da3_dir: Path,
    transform_by_window: dict[str, dict[str, Any]],
    conf_threshold: float,
    confidence_mode: str,
) -> tuple[np.ndarray, np.ndarray]:
    depth = load_depth(row, da3_dir)
    conf = normalize_conf(load_conf(row, da3_dir), confidence_mode)
    intrinsics = load_intrinsics(row, da3_dir)
    extrinsics = load_extrinsics(row, da3_dir)
    image = load_frame_colors(row, capture_dir)
    valid = np.isfinite(depth) & np.isfinite(conf) & (conf >= conf_threshold) & (conf > 1e-5)
    if not np.any(valid):
        return (
            np.zeros((0, 3), dtype=np.float32),
            np.zeros((0, 3), dtype=np.uint8),
        )

    height, width = depth.shape
    valid_indices = np.flatnonzero(valid.reshape(-1))
    u = (valid_indices % width).astype(np.float64)
    v = (valid_indices // width).astype(np.float64)
    pix = np.stack([u, v, np.ones_like(u)], axis=0)
    k_inv = np.linalg.inv(intrinsics.astype(np.float64))
    c2w = np.linalg.inv(as_homogeneous44(extrinsics).astype(np.float64))
    rays = k_inv @ pix
    depth_flat = depth.reshape(-1).astype(np.float64)
    camera_points = rays * depth_flat[valid_indices][None, :]
    camera_points_h = np.vstack([camera_points, np.ones((1, camera_points.shape[1]))])
    world_points = (c2w @ camera_points_h)[:3].T.astype(np.float32)
    transform = transform_by_window[str(row["officialSaveWindowID"])]
    world_points = apply_sim3(world_points, transform)
    colors = image.reshape(-1, 3)[valid_indices].astype(np.uint8)
    finite = np.isfinite(world_points).all(axis=1)
    return world_points[finite], colors[finite]


def build_report(
    *,
    args: argparse.Namespace,
    capture: dict[str, Any],
    source_frame_ids: list[str],
    selected_rows: list[dict[str, Any]],
    selection: dict[str, Any],
    transform_by_window: dict[str, dict[str, Any]],
    sim3_report: dict[str, Any],
    conf_mean: float,
    threshold: float,
    valid_count: int,
    points: np.ndarray,
    ply_path: Path,
    png_path: Path,
) -> dict[str, Any]:
    camera_centers = []
    depth_means = []
    conf_means = []
    transform_summary = summarize_transforms(transform_by_window)
    for row in selected_rows:
        extrinsics = load_extrinsics(row, args.da3_dir)
        center = camera_center_from_w2c(extrinsics)
        center = apply_sim3(center.reshape(1, 3), transform_by_window[str(row["officialSaveWindowID"])])[0]
        camera_centers.append(center)
        depth_means.append(float(np.mean(load_depth(row, args.da3_dir))))
        conf_means.append(float(np.mean(normalize_conf(load_conf(row, args.da3_dir), args.confidence_mode))))
    pixel_count = sum(int(row["depthWidth"]) * int(row["depthHeight"]) for row in selected_rows)
    return {
        "schema_version": "pocketworld_official_adjacent_sim3_pointcloud_export_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "da3_dir": str(args.da3_dir),
            "adjacent_sim3_json": str(args.adjacent_sim3_json),
            "name": args.name,
            "confidence_mode": args.confidence_mode,
        },
        "official_reference": {
            "source": "Depth-Anything-3 da3_streaming.py adjacent align + accumulate_sim3_transforms + apply_sim3_direct_torch",
            "note": "No loop closure optimizer, cleanup, Poisson, mesh, or new fusion was applied.",
        },
        "windowing": capture.get("windowingPolicy", {}),
        "selection": {
            **selection,
            "sourceFrameCount": len(source_frame_ids),
            "orderCheck": first_order_mismatch(source_frame_ids, [str(row["frameID"]) for row in selected_rows]),
        },
        "adjacent_sim3": {
            **sim3_input_summary(sim3_report),
            "accumulated_transform_summary": transform_summary,
        },
        "official_filter": {
            "style": "DA3-Streaming results_output/frame_*.npz + npz_output_process.py confidence/downsample style",
            "conf_threshold_coef": args.npz_conf_threshold_coef,
            "conf_threshold_coef_source": "npz_output_process.py CLI default is 0.5; DA3-Streaming Pointcloud_Save config uses 0.75 for full-chunk pcd export.",
            "conf_mean": conf_mean,
            "conf_threshold": threshold,
            "sample_ratio": args.npz_sample_ratio,
            "valid_point_count_before_downsample": valid_count,
            "valid_fraction_of_pixels": float(valid_count / max(pixel_count, 1)),
            "exported_point_count": int(points.shape[0]),
            "random_downsample_seed": args.seed,
        },
        "metrics": {
            "point_cloud": cloud_metrics(points) if points.shape[0] else {"point_count": 0},
            "pca": pca_metrics(points) if points.shape[0] >= 3 else {"status": "not_enough_points"},
            "pose": pose_metrics(np.stack(camera_centers, axis=0)) if camera_centers else {},
            "per_frame_depth_mean": summarize_array(np.asarray(depth_means, dtype=np.float64)),
            "per_frame_conf_mean": summarize_array(np.asarray(conf_means, dtype=np.float64)),
        },
        "outputs": {
            "ply": str(ply_path),
            "views_png": str(png_path),
            "report_json": str(args.out_dir / "official_adjacent_sim3_pointcloud_report.json"),
            "report_markdown": str(args.out_dir / "official_adjacent_sim3_pointcloud_report_zh.md"),
        },
    }


def sim3_input_summary(sim3_report: dict[str, Any]) -> dict[str, Any]:
    if "optimizer" in sim3_report:
        optimizer = sim3_report.get("optimizer") or {}
        adjacent = sim3_report.get("adjacent") or {}
        return {
            "source_type": "loop_optimizer",
            "input_edge_count": optimizer.get("optimized_transform_count"),
            "estimated_edge_count": optimizer.get("optimized_transform_count"),
            "input_summary": adjacent,
            "optimizer_summary": {
                key: value
                for key, value in optimizer.items()
                if key != "optimized_transforms"
            },
        }
    return {
        "source_type": "adjacent_diagnostic",
        "input_edge_count": sim3_report.get("edge_count"),
        "estimated_edge_count": sim3_report.get("estimated_edge_count"),
        "input_summary": sim3_report.get("summary", {}),
    }


def summarize_transforms(transform_by_window: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for window_id, transform in transform_by_window.items():
        rotation = np.asarray(transform["rotation"], dtype=np.float64)
        rows.append(
            {
                "windowID": window_id,
                "scale": float(transform["scale"]),
                "rotation_angle_deg": rotation_angle_degrees(rotation),
                "translation_norm": float(np.linalg.norm(transform["translation"])),
            }
        )
    scales = np.asarray([row["scale"] for row in rows], dtype=np.float64)
    rotations = np.asarray([row["rotation_angle_deg"] for row in rows], dtype=np.float64)
    translations = np.asarray([row["translation_norm"] for row in rows], dtype=np.float64)
    return {
        "window_count": len(rows),
        "scale_min": float(np.min(scales)) if scales.size else math.nan,
        "scale_max": float(np.max(scales)) if scales.size else math.nan,
        "rotation_angle_deg_max": float(np.max(rotations)) if rotations.size else math.nan,
        "translation_norm_max": float(np.max(translations)) if translations.size else math.nan,
        "per_window": rows,
    }


def rotation_angle_degrees(rotation: np.ndarray) -> float:
    value = (float(np.trace(rotation)) - 1.0) * 0.5
    value = max(-1.0, min(1.0, value))
    return float(np.degrees(np.arccos(value)))


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    filt = report["official_filter"]
    sel = report["selection"]
    adj = report["adjacent_sim3"]
    pc = report["metrics"]["point_cloud"]
    pca = report["metrics"]["pca"]
    accum = adj["accumulated_transform_summary"]
    lines = [
        "# Official Adjacent Dense Sim3 Point Cloud Export",
        "",
        "## 做了什么",
        "",
        "- 按 capture 的 `officialSaveSlotIndices` 选择保存帧。",
        "- 按 DA3-Streaming 相邻 dense Sim3 方向 `current chunk -> previous chunk` 累积并应用变换。",
        "- 按 streaming confidence 语义和 NPZ point-cloud 采样导出 PLY/三视图。",
        "- 不做 loop optimizer、不做清理、不做 Poisson、不做 mesh、不做自研融合。",
        "",
        "## 保存帧检查",
        "",
        f"- source_frame_count: {sel['sourceFrameCount']}",
        f"- selected_frame_count: {sel['selectedFrameCount']}",
        f"- selected_unique_frame_count: {sel['selectedUniqueFrameCount']}",
        f"- selected_duplicate_frame_count: {sel['selectedDuplicateFrameCount']}",
        f"- missing_frame_count: {len(sel['missingFrameIDs'])}",
        f"- order_matches_source: {sel['orderMatchesSource']}",
        "",
        "## Adjacent Sim3",
        "",
        f"- edge_count: {adj['input_edge_count']}",
        f"- estimated_edge_count: {adj['estimated_edge_count']}",
        f"- input_scale_range: {adj['input_summary'].get('scale_min', math.nan):.8g} .. {adj['input_summary'].get('scale_max', math.nan):.8g}",
        f"- input_rotation_angle_deg_max: {adj['input_summary'].get('rotation_angle_deg_max', math.nan):.8g}",
        f"- accumulated_scale_range: {accum.get('scale_min', math.nan):.8g} .. {accum.get('scale_max', math.nan):.8g}",
        f"- accumulated_rotation_angle_deg_max: {accum.get('rotation_angle_deg_max', math.nan):.8g}",
        f"- accumulated_translation_norm_max: {accum.get('translation_norm_max', math.nan):.8g}",
        "",
        "## 官方 Filter",
        "",
        f"- confidence_mode: {report['inputs']['confidence_mode']}",
        f"- conf_threshold_coef: {filt['conf_threshold_coef']}",
        f"- conf_threshold_coef_source: {filt['conf_threshold_coef_source']}",
        f"- conf_mean: {filt['conf_mean']:.8g}",
        f"- conf_threshold: {filt['conf_threshold']:.8g}",
        f"- sample_ratio: {filt['sample_ratio']}",
        f"- valid_point_count_before_downsample: {filt['valid_point_count_before_downsample']}",
        f"- exported_point_count: {filt['exported_point_count']}",
        "",
        "## 几何数值",
        "",
        f"- bbox_diag_p01_p99: {pc.get('bbox_diag_p01_p99', math.nan):.8g}",
        f"- bbox_extent_p01_p99: {pc.get('bbox_extent_p01_p99')}",
        f"- pca_minor_extent: {pca.get('minor_extent', math.nan):.8g}",
        f"- pca_minor_to_major_ratio: {pca.get('minor_to_major_ratio', math.nan):.8g}",
        "",
        "## 输出",
        "",
        f"- PLY: `{report['outputs']['ply']}`",
        f"- views PNG: `{report['outputs']['views_png']}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": report["inputs"]["name"],
        "confidence_mode": report["inputs"]["confidence_mode"],
        "selected_frame_count": report["selection"]["selectedFrameCount"],
        "selected_duplicate_frame_count": report["selection"]["selectedDuplicateFrameCount"],
        "missing_frame_count": len(report["selection"]["missingFrameIDs"]),
        "order_matches_source": report["selection"]["orderMatchesSource"],
        "edge_count": report["adjacent_sim3"]["input_edge_count"],
        "scale_range": [
            report["adjacent_sim3"]["input_summary"].get("scale_min"),
            report["adjacent_sim3"]["input_summary"].get("scale_max"),
        ],
        "accumulated_scale_range": [
            report["adjacent_sim3"]["accumulated_transform_summary"].get("scale_min"),
            report["adjacent_sim3"]["accumulated_transform_summary"].get("scale_max"),
        ],
        "conf_threshold": report["official_filter"]["conf_threshold"],
        "valid_points_before_downsample": report["official_filter"]["valid_point_count_before_downsample"],
        "exported_points": report["official_filter"]["exported_point_count"],
        "bbox_diag_p01_p99": report["metrics"]["point_cloud"].get("bbox_diag_p01_p99"),
        "pca_minor_extent": report["metrics"]["pca"].get("minor_extent"),
        "ply": report["outputs"]["ply"],
        "views_png": report["outputs"]["views_png"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
