#!/usr/bin/env python3
"""Export official-save DA3 frames with official core-frame downstream rules.

This reads a fixed-K35 capture produced by make_official_k35_fixed_save_capture.py
and a DA3 output directory, selects only officialSaveSlotIndices, then applies
the DA3-Streaming results_output/frame_*.npz + npz_output_process.py /
save_confident_pointcloud_batch confidence and reservoir-sampling semantics.
It is intentionally point-cloud only: no graph patch, no Poisson, no mesh, no
cleanup.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

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
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--npz-sample-ratio", type=float, default=0.015)
    parser.add_argument("--seed", type=int, default=4300)
    parser.add_argument("--name", default="official_save_full_sequence")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    capture = read_json(args.capture_dir / "da3_k_windows.json")
    bundle = read_json(args.capture_dir / "photo_bundle.json")
    reports = read_json(args.da3_dir / "mac_da3_window_reports.json")

    source_frame_ids = [str(row["id"]) for row in bundle.get("frames", [])]
    selected_rows, selection = select_official_save_rows(capture, reports, source_frame_ids)
    if not selected_rows:
        raise ValueError("No official-save rows selected")

    conf_mean = compute_conf_mean(selected_rows, args.da3_dir)
    threshold = float(conf_mean * args.npz_conf_threshold_coef)
    valid_count = count_valid_points(selected_rows, args.da3_dir, threshold)
    points, colors = reservoir_export(
        selected_rows,
        capture_dir=args.capture_dir,
        da3_dir=args.da3_dir,
        conf_threshold=threshold,
        sample_ratio=args.npz_sample_ratio,
        seed=args.seed,
        valid_count=valid_count,
    )

    ply_path = args.out_dir / f"{args.name}_npz_streaming_rgb.ply"
    png_path = args.out_dir / f"{args.name}_npz_streaming_views.png"
    write_point_cloud(ply_path, points, colors)
    write_views_png(
        png_path,
        points,
        colors,
        title=f"{args.name} official NPZ streaming style",
    )

    report = build_report(
        args=args,
        capture=capture,
        source_frame_ids=source_frame_ids,
        selected_rows=selected_rows,
        selection=selection,
        conf_mean=conf_mean,
        threshold=threshold,
        valid_count=valid_count,
        points=points,
        ply_path=ply_path,
        png_path=png_path,
    )
    write_json(args.out_dir / "official_save_sequence_pointcloud_report.json", report)
    write_markdown(args.out_dir / "official_save_sequence_pointcloud_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def select_official_save_rows(
    capture: dict[str, Any],
    reports: dict[str, Any],
    source_frame_ids: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    windows = list(capture.get("windows") or [])
    reports_by_id = {str(row["windowID"]): row for row in reports.get("windows", [])}
    selected_rows: list[dict[str, Any]] = []
    per_window = []
    for window_index, window in enumerate(windows):
        window_id = str(window.get("id") or f"window_{window_index:03d}")
        report = reports_by_id.get(window_id)
        if not report:
            raise KeyError(f"{window_id} missing from mac_da3_window_reports.json")
        rows_by_slot = {
            int(row.get("windowSlot", -1)): row
            for row in report.get("frames", [])
        }
        save_slots = window.get("officialSaveSlotIndices")
        if save_slots is None:
            save_slots = fallback_save_slots(capture, window, window_index, len(windows))
        save_slots = [int(slot) for slot in save_slots]
        saved_ids = []
        for slot in save_slots:
            if slot not in rows_by_slot:
                raise KeyError(f"{window_id} slot {slot} missing from DA3 report")
            row = dict(rows_by_slot[slot])
            row["officialSaveWindowID"] = window_id
            row["officialSaveSlot"] = slot
            row["officialChunkIndex"] = window_index
            selected_rows.append(row)
            saved_ids.append(str(row["frameID"]))
        per_window.append(
            {
                "windowID": window_id,
                "chunkStartIndex": window.get("chunkStartIndex"),
                "chunkEndIndexExclusive": window.get("chunkEndIndexExclusive"),
                "realFrameCount": window.get("realFrameCount"),
                "paddingFrameCount": window.get("paddingFrameCount"),
                "officialSaveSlotIndices": save_slots,
                "officialSaveFrameIDs": saved_ids,
            }
        )

    selected_ids = [str(row["frameID"]) for row in selected_rows]
    source_set = set(source_frame_ids)
    selected_set = set(selected_ids)
    return selected_rows, {
        "perWindow": per_window,
        "selectedFrameCount": len(selected_ids),
        "selectedUniqueFrameCount": len(selected_set),
        "selectedDuplicateFrameCount": len(selected_ids) - len(selected_set),
        "missingFrameIDs": [frame_id for frame_id in source_frame_ids if frame_id not in selected_set],
        "extraFrameIDs": [frame_id for frame_id in selected_ids if frame_id not in source_set],
        "orderMatchesSource": selected_ids == source_frame_ids,
        "firstOrderMismatch": first_order_mismatch(source_frame_ids, selected_ids),
    }


def fallback_save_slots(
    capture: dict[str, Any],
    window: dict[str, Any],
    window_index: int,
    window_count: int,
) -> list[int]:
    policy = dict(capture.get("windowingPolicy") or {})
    chunk_size = int(capture.get("windowSize") or policy.get("chunkSize") or 35)
    overlap = int(policy.get("overlap") or 0)
    step = int(policy.get("step") or (chunk_size - overlap))
    real_count = int(window.get("realFrameCount") or len(window.get("realFrameIDs") or window.get("frameIDs") or []))
    if window_index == window_count - 1:
        return list(range(real_count))
    return list(range(min(step, real_count)))


def first_order_mismatch(source: list[str], selected: list[str]) -> dict[str, Any] | None:
    limit = min(len(source), len(selected))
    for index in range(limit):
        if source[index] != selected[index]:
            return {
                "index": index,
                "sourceFrameID": source[index],
                "selectedFrameID": selected[index],
            }
    if len(source) != len(selected):
        return {
            "index": limit,
            "sourceFrameID": source[limit] if limit < len(source) else None,
            "selectedFrameID": selected[limit] if limit < len(selected) else None,
        }
    return None


def compute_conf_mean(rows: list[dict[str, Any]], da3_dir: Path) -> float:
    total = 0.0
    count = 0
    for row in rows:
        conf = load_conf(row, da3_dir)
        total += float(np.sum(conf.astype(np.float64)))
        count += int(conf.size)
    return total / max(count, 1)


def count_valid_points(rows: list[dict[str, Any]], da3_dir: Path, threshold: float) -> int:
    count = 0
    for row in rows:
        depth = load_depth(row, da3_dir)
        conf = load_conf(row, da3_dir)
        mask = np.isfinite(depth) & np.isfinite(conf) & (conf >= threshold) & (conf > 1e-5)
        count += int(np.count_nonzero(mask))
    return count


def reservoir_export(
    rows: list[dict[str, Any]],
    *,
    capture_dir: Path,
    da3_dir: Path,
    conf_threshold: float,
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
                conf_threshold=conf_threshold,
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
            conf_threshold=conf_threshold,
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
    conf_threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    depth = load_depth(row, da3_dir)
    conf = load_conf(row, da3_dir)
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
    for row in selected_rows:
        extrinsics = load_extrinsics(row, args.da3_dir)
        camera_centers.append(camera_center_from_w2c(extrinsics))
        depth_means.append(float(np.mean(load_depth(row, args.da3_dir))))
        conf_means.append(float(np.mean(load_conf(row, args.da3_dir))))
    pixel_count = sum(int(row["depthWidth"]) * int(row["depthHeight"]) for row in selected_rows)
    return {
        "schema_version": "pocketworld_official_save_sequence_pointcloud_export_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "da3_dir": str(args.da3_dir),
            "name": args.name,
        },
        "windowing": capture.get("windowingPolicy", {}),
        "selection": {
            **selection,
            "sourceFrameCount": len(source_frame_ids),
        },
        "official_filter": {
            "style": "npz_output_process.py + save_confident_pointcloud_batch",
            "source": "Depth-Anything-3/da3_streaming npz_output_process.py and loop_utils/sim3utils.py",
            "conf_threshold_coef": args.npz_conf_threshold_coef,
            "conf_threshold_coef_source": "npz_output_process.py CLI default is 0.5; DA3-Streaming Pointcloud_Save config uses 0.75 for full-chunk pcd export.",
            "conf_mean": conf_mean,
            "conf_threshold": threshold,
            "sample_ratio": args.npz_sample_ratio,
            "valid_point_count_before_downsample": valid_count,
            "valid_fraction_of_pixels": float(valid_count / max(pixel_count, 1)),
            "exported_point_count": int(points.shape[0]),
            "random_downsample_seed": args.seed,
            "note": "No cleanup, no Poisson, no mesh; only official confidence filter and reservoir sample.",
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
            "report_json": str(args.out_dir / "official_save_sequence_pointcloud_report.json"),
            "report_markdown": str(args.out_dir / "official_save_sequence_pointcloud_report_zh.md"),
        },
    }


def load_depth(row: dict[str, Any], da3_dir: Path) -> np.ndarray:
    return np.fromfile(
        da3_dir / str(row["relativeDepthPath"]),
        dtype="<f4",
    ).reshape(int(row["depthHeight"]), int(row["depthWidth"]))


def load_conf(row: dict[str, Any], da3_dir: Path) -> np.ndarray:
    return np.fromfile(
        da3_dir / str(row["confidencePath"]),
        dtype="<f4",
    ).reshape(int(row["depthHeight"]), int(row["depthWidth"]))


def load_intrinsics(row: dict[str, Any], da3_dir: Path) -> np.ndarray:
    return np.fromfile(
        da3_dir / str(row["predIntrinsicsPath"]),
        dtype="<f4",
    ).reshape(3, 3)


def load_extrinsics(row: dict[str, Any], da3_dir: Path) -> np.ndarray:
    return np.fromfile(
        da3_dir / str(row["predExtrinsicsPath"]),
        dtype="<f4",
    ).reshape(3, 4)


def load_frame_colors(row: dict[str, Any], capture_dir: Path) -> np.ndarray:
    width = int(row["depthWidth"])
    height = int(row["depthHeight"])
    with Image.open(capture_dir / str(row["imageRelativePath"])) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.BILINEAR)
        return np.asarray(image, dtype=np.uint8)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    filt = report["official_filter"]
    sel = report["selection"]
    pc = report["metrics"]["point_cloud"]
    pca = report["metrics"]["pca"]
    lines = [
        "# Official Save Sequence Point Cloud Export",
        "",
        "## 做了什么",
        "",
        "- 按 capture 的 `officialSaveSlotIndices` 选择保存帧。",
        "- 按官方 DA3-Streaming `npz_output_process.py + save_confident_pointcloud_batch` 语义导出点云。",
        "- 不做清理、不做 Poisson、不做 mesh、不做自研融合。",
        "",
        "## 保存帧检查",
        "",
        f"- source_frame_count: {sel['sourceFrameCount']}",
        f"- selected_frame_count: {sel['selectedFrameCount']}",
        f"- selected_unique_frame_count: {sel['selectedUniqueFrameCount']}",
        f"- selected_duplicate_frame_count: {sel['selectedDuplicateFrameCount']}",
        f"- missing_frame_count: {len(sel['missingFrameIDs'])}",
        f"- order_matches_source: {sel['orderMatchesSource']}",
        f"- first_order_mismatch: {sel['firstOrderMismatch']}",
        "",
        "## 官方 Filter",
        "",
        f"- conf_threshold_coef: {filt['conf_threshold_coef']}",
        f"- conf_threshold_coef_source: {filt['conf_threshold_coef_source']}",
        f"- conf_mean: {filt['conf_mean']:.8g}",
        f"- conf_threshold: {filt['conf_threshold']:.8g}",
        f"- sample_ratio: {filt['sample_ratio']}",
        f"- valid_point_count_before_downsample: {filt['valid_point_count_before_downsample']}",
        f"- valid_fraction_of_pixels: {filt['valid_fraction_of_pixels']:.8g}",
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
        "capture_dir": report["inputs"]["capture_dir"],
        "selected_frame_count": report["selection"]["selectedFrameCount"],
        "selected_duplicate_frame_count": report["selection"]["selectedDuplicateFrameCount"],
        "missing_frame_count": len(report["selection"]["missingFrameIDs"]),
        "order_matches_source": report["selection"]["orderMatchesSource"],
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
