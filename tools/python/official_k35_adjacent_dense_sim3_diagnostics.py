#!/usr/bin/env python3
"""Official-style adjacent dense Sim3 diagnostics for fixed-K35 DA3 windows.

This is a read-only diagnostic. It mirrors the DA3-Streaming adjacent alignment
step: previous chunk tail overlap -> current chunk head overlap, dense pixel
correspondences, confidence-weighted Sim3 with IRLS. It does not apply the
transform, fuse point clouds, clean points, mesh, or run loop optimization.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--da3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--confidence-mode",
        choices=["streaming_subtract_one", "raw"],
        default="streaming_subtract_one",
        help="DA3-Streaming subtracts 1.0 from prediction.conf before alignment.",
    )
    parser.add_argument("--max-edges", type=int, default=0)
    args = parser.parse_args()

    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    capture = read_json(args.capture_dir / "da3_k_windows.json")
    reports = read_json(args.da3_dir / "mac_da3_window_reports.json")
    windows = list(capture.get("windows") or [])
    report_by_id = {str(row["windowID"]): row for row in reports.get("windows", [])}
    overlap = int((capture.get("windowingPolicy") or {}).get("overlap") or 0)
    if overlap <= 0:
        raise ValueError("capture windowingPolicy.overlap must be positive")

    edges = []
    transforms = []
    total_edges = max(0, len(windows) - 1)
    edge_limit = total_edges if args.max_edges <= 0 else min(total_edges, args.max_edges)
    for index in range(1, edge_limit + 1):
        parent = windows[index - 1]
        current = windows[index]
        parent_id = str(parent["id"])
        current_id = str(current["id"])
        parent_rows = rows_by_slot(report_by_id[parent_id])
        current_rows = rows_by_slot(report_by_id[current_id])
        parent_real_count = int(parent.get("realFrameCount") or len(parent.get("realFrameIDs") or parent.get("frameIDs") or []))
        current_real_count = int(current.get("realFrameCount") or len(current.get("realFrameIDs") or current.get("frameIDs") or []))
        local_overlap = min(overlap, parent_real_count, current_real_count)
        if local_overlap <= 0:
            edges.append(
                {
                    "edgeIndex": index - 1,
                    "parentWindowID": parent_id,
                    "currentWindowID": current_id,
                    "status": "skipped_no_real_overlap",
                }
            )
            continue
        parent_slots = list(range(parent_real_count - local_overlap, parent_real_count))
        current_slots = list(range(0, local_overlap))
        target_rows = [parent_rows[slot] for slot in parent_slots]
        source_rows = [current_rows[slot] for slot in current_slots]
        transform, edge = estimate_dense_sim3_rows(
            target_rows=target_rows,
            source_rows=source_rows,
            target_da3_dir=args.da3_dir,
            source_da3_dir=args.da3_dir,
            confidence_mode=args.confidence_mode,
        )
        transforms.append(transform_to_tuple(transform))
        edges.append(
            {
                "edgeIndex": index - 1,
                "edgeType": "adjacent_dense_sim3",
                "parentWindowID": parent_id,
                "currentWindowID": current_id,
                "parentChunkStartIndex": parent.get("chunkStartIndex"),
                "currentChunkStartIndex": current.get("chunkStartIndex"),
                "overlapFrameCount": local_overlap,
                "parentSlots": parent_slots,
                "currentSlots": current_slots,
                "sharedFrameIDs": [str(row["frameID"]) for row in target_rows],
                "sourceFrameIDs": [str(row["frameID"]) for row in source_rows],
                **edge,
            }
        )

    report = {
        "schema_version": "pocketworld_official_k35_adjacent_dense_sim3_diagnostics_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "da3_dir": str(args.da3_dir),
            "confidence_mode": args.confidence_mode,
        },
        "official_reference": {
            "source": "Depth-Anything-3 da3_streaming.py align_2pcds + weighted_align_point_maps",
            "adjacent_rule": "previous chunk tail overlap aligns current chunk head overlap",
            "confidence_threshold": "min(median(conf1), median(conf2)) * 0.1",
            "irls": {"delta": 0.1, "max_iters": 5, "tol": 1e-9, "align_method": "sim3"},
            "note": "This Mac diagnostic reimplements the official numpy/numba branch math because official sim3utils imports Triton eagerly; no point cloud output is modified.",
        },
        "windowing": capture.get("windowingPolicy", {}),
        "edge_count": len(edges),
        "estimated_edge_count": sum(1 for edge in edges if edge.get("status") == "estimated"),
        "summary": summarize_edges(edges),
        "edges": edges,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    write_json(args.out_dir / "official_k35_adjacent_dense_sim3_diagnostics.json", report)
    write_markdown(args.out_dir / "official_k35_adjacent_dense_sim3_diagnostics_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def estimate_dense_sim3_rows(
    *,
    target_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    target_da3_dir: Path,
    source_da3_dir: Path,
    confidence_mode: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target_points = []
    source_points = []
    weights = []
    median_confs = []
    payloads = []
    for target_row, source_row in zip(target_rows, source_rows):
        target_map, target_conf_raw = load_point_map_and_conf(target_row, target_da3_dir)
        source_map, source_conf_raw = load_point_map_and_conf(source_row, source_da3_dir)
        target_conf = normalize_conf(target_conf_raw, confidence_mode)
        source_conf = normalize_conf(source_conf_raw, confidence_mode)
        payloads.append((target_map, target_conf, source_map, source_conf))
        median_confs.extend([float(np.median(target_conf)), float(np.median(source_conf))])

    conf_threshold = min(median_confs) * 0.1 if median_confs else 0.0
    for target_map, target_conf, source_map, source_conf in payloads:
        mask = (
            np.isfinite(target_map).all(axis=2)
            & np.isfinite(source_map).all(axis=2)
            & np.isfinite(target_conf)
            & np.isfinite(source_conf)
            & (target_conf > conf_threshold)
            & (source_conf > conf_threshold)
        )
        if not np.any(mask):
            continue
        target_points.append(target_map[mask])
        source_points.append(source_map[mask])
        weights.append(
            np.sqrt(
                target_conf[mask].astype(np.float64)
                * source_conf[mask].astype(np.float64)
            )
        )
    if not source_points:
        raise ValueError("No dense correspondences survived the official confidence mask")

    src = np.concatenate(source_points, axis=0).astype(np.float64)
    dst = np.concatenate(target_points, axis=0).astype(np.float64)
    weight = np.concatenate(weights, axis=0).astype(np.float64)
    transform = robust_weighted_sim3(src, dst, weight, delta=0.1, max_iters=5, tol=1e-9)
    residual = np.linalg.norm(apply_sim3(src, transform) - dst, axis=1)
    rotation_angle = rotation_angle_degrees(np.eye(3), np.asarray(transform["rotation"]))
    return transform, {
        "status": "estimated",
        "point_count": int(src.shape[0]),
        "confidence_threshold": float(conf_threshold),
        "confidence_median_min": float(min(median_confs)),
        "rmse": float(np.sqrt(np.mean(residual * residual))),
        "mean": float(np.mean(residual)),
        "median": float(np.median(residual)),
        "p90": float(np.percentile(residual, 90)),
        "p95": float(np.percentile(residual, 95)),
        "p99": float(np.percentile(residual, 99)),
        "sim3_scale": float(transform["scale"]),
        "sim3_rotation_angle_deg": float(rotation_angle),
        "sim3_translation_norm": float(np.linalg.norm(transform["translation"])),
        "sim3_rotation": np.asarray(transform["rotation"], dtype=float).tolist(),
        "sim3_translation": np.asarray(transform["translation"], dtype=float).reshape(-1).tolist(),
    }


def load_point_map_and_conf(frame: dict[str, Any], da3_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    height = int(frame["depthHeight"])
    width = int(frame["depthWidth"])
    depth = np.fromfile(da3_dir / str(frame["relativeDepthPath"]), dtype="<f4").reshape(height, width)
    conf = np.fromfile(da3_dir / str(frame["confidencePath"]), dtype="<f4").reshape(height, width)
    intrinsics = np.fromfile(da3_dir / str(frame["predIntrinsicsPath"]), dtype="<f4").reshape(3, 3)
    extrinsics = np.fromfile(da3_dir / str(frame["predExtrinsicsPath"]), dtype="<f4").reshape(3, 4)
    return depth_to_point_map(depth, intrinsics, extrinsics), conf


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


def normalize_conf(conf: np.ndarray, mode: str) -> np.ndarray:
    out = np.asarray(conf, dtype=np.float32)
    if mode == "streaming_subtract_one":
        out = out - 1.0
    return out


def robust_weighted_sim3(
    src: np.ndarray,
    dst: np.ndarray,
    weights: np.ndarray,
    *,
    delta: float,
    max_iters: int,
    tol: float,
) -> dict[str, Any]:
    weights = np.asarray(weights, dtype=np.float64)
    weights = weights / max(float(np.sum(weights)), 1e-12)
    transform = weighted_sim3(src, dst, weights)
    previous_error = float("inf")
    for _ in range(max_iters):
        residual = np.linalg.norm(apply_sim3(src, transform) - dst, axis=1)
        huber = np.ones_like(residual)
        large = residual > delta
        huber[large] = delta / np.maximum(residual[large], 1e-12)
        combined = weights * huber
        combined = combined / max(float(np.sum(combined)), 1e-12)
        updated = weighted_sim3(src, dst, combined)
        param_change = abs(float(updated["scale"]) - float(transform["scale"])) + float(
            np.linalg.norm(np.asarray(updated["translation"]) - np.asarray(transform["translation"]))
        )
        rot_delta = np.asarray(updated["rotation"]) @ np.asarray(transform["rotation"]).T
        rot_angle = math.acos(min(1.0, max(-1.0, (float(np.trace(rot_delta)) - 1.0) / 2.0)))
        current_error = float(np.sum(huber_loss(residual, delta) * weights))
        transform = updated
        if (param_change < tol and rot_angle < math.radians(0.1)) or (
            previous_error < float("inf")
            and abs(previous_error - current_error) < tol * max(previous_error, 1e-12)
        ):
            break
        previous_error = current_error
    return transform


def weighted_sim3(src: np.ndarray, dst: np.ndarray, weights: np.ndarray) -> dict[str, Any]:
    total = float(np.sum(weights))
    if total < 1e-12:
        raise ValueError("Total weight too small for dense Sim3")
    normalized = weights / total
    mu_src = np.sum(normalized[:, None] * src, axis=0)
    mu_dst = np.sum(normalized[:, None] * dst, axis=0)
    src_centered = src - mu_src
    dst_centered = dst - mu_dst
    scale_src = math.sqrt(float(np.sum(normalized * np.sum(src_centered * src_centered, axis=1))))
    scale_dst = math.sqrt(float(np.sum(normalized * np.sum(dst_centered * dst_centered, axis=1))))
    scale = scale_dst / max(scale_src, 1e-12)
    weighted_src = (scale * src_centered) * np.sqrt(normalized)[:, None]
    weighted_dst = dst_centered * np.sqrt(normalized)[:, None]
    h = weighted_src.T @ weighted_dst
    u, _, vt = np.linalg.svd(h)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[2, :] *= -1
        rotation = vt.T @ u.T
    translation = mu_dst - scale * (rotation @ mu_src)
    return {"scale": float(scale), "rotation": rotation, "translation": translation}


def apply_sim3(points: np.ndarray, transform: dict[str, Any]) -> np.ndarray:
    return float(transform["scale"]) * (
        points.astype(np.float64) @ np.asarray(transform["rotation"], dtype=np.float64).T
    ) + np.asarray(transform["translation"], dtype=np.float64)


def huber_loss(residual: np.ndarray, delta: float) -> np.ndarray:
    abs_residual = np.abs(residual)
    return np.where(abs_residual <= delta, 0.5 * residual * residual, delta * (abs_residual - 0.5 * delta))


def rotation_angle_degrees(left_r: np.ndarray, right_r: np.ndarray) -> float:
    rel = left_r.astype(np.float64) @ right_r.astype(np.float64).T
    value = (float(np.trace(rel)) - 1.0) * 0.5
    value = max(-1.0, min(1.0, value))
    return float(np.degrees(np.arccos(value)))


def rows_by_slot(window_report: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(frame["windowSlot"]): frame for frame in window_report.get("frames", [])}


def transform_to_tuple(transform: dict[str, Any]) -> tuple[float, np.ndarray, np.ndarray]:
    return (
        float(transform["scale"]),
        np.asarray(transform["rotation"], dtype=np.float64),
        np.asarray(transform["translation"], dtype=np.float64),
    )


def summarize_edges(edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "edge_count": len(edges),
        "estimated_count": sum(1 for edge in edges if edge.get("status") == "estimated"),
        "point_count_mean": safe_mean([edge.get("point_count") for edge in edges]),
        "rmse_mean": safe_mean([edge.get("rmse") for edge in edges]),
        "rmse_max": safe_max([edge.get("rmse") for edge in edges]),
        "p90_mean": safe_mean([edge.get("p90") for edge in edges]),
        "p95_mean": safe_mean([edge.get("p95") for edge in edges]),
        "scale_mean": safe_mean([edge.get("sim3_scale") for edge in edges]),
        "scale_std": safe_std([edge.get("sim3_scale") for edge in edges]),
        "scale_min": safe_min([edge.get("sim3_scale") for edge in edges]),
        "scale_max": safe_max([edge.get("sim3_scale") for edge in edges]),
        "rotation_angle_deg_mean": safe_mean([edge.get("sim3_rotation_angle_deg") for edge in edges]),
        "rotation_angle_deg_max": safe_max([edge.get("sim3_rotation_angle_deg") for edge in edges]),
        "translation_norm_mean": safe_mean([edge.get("sim3_translation_norm") for edge in edges]),
        "translation_norm_max": safe_max([edge.get("sim3_translation_norm") for edge in edges]),
    }


def safe_values(values: list[Any]) -> np.ndarray:
    return np.asarray(
        [float(value) for value in values if value is not None and np.isfinite(float(value))],
        dtype=np.float64,
    )


def safe_mean(values: list[Any]) -> float:
    arr = safe_values(values)
    return float(np.mean(arr)) if arr.size else math.nan


def safe_std(values: list[Any]) -> float:
    arr = safe_values(values)
    return float(np.std(arr)) if arr.size else math.nan


def safe_min(values: list[Any]) -> float:
    arr = safe_values(values)
    return float(np.min(arr)) if arr.size else math.nan


def safe_max(values: list[Any]) -> float:
    arr = safe_values(values)
    return float(np.max(arr)) if arr.size else math.nan


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# Official K35 Adjacent Dense Sim3 Diagnostics",
        "",
        "## What This Is",
        "",
        "- Read-only diagnostic.",
        "- Mirrors DA3-Streaming adjacent dense Sim3 semantics.",
        "- Does not apply transforms, fuse points, clean points, mesh, or run loop optimization.",
        "",
        "## Inputs",
        "",
        f"- capture_dir: `{report['inputs']['capture_dir']}`",
        f"- da3_dir: `{report['inputs']['da3_dir']}`",
        f"- confidence_mode: `{report['inputs']['confidence_mode']}`",
        "",
        "## Summary",
        "",
        f"- edge_count: {summary['edge_count']}",
        f"- estimated_count: {summary['estimated_count']}",
        f"- point_count_mean: {summary['point_count_mean']:.8g}",
        f"- rmse_mean: {summary['rmse_mean']:.8g}",
        f"- rmse_max: {summary['rmse_max']:.8g}",
        f"- p90_mean: {summary['p90_mean']:.8g}",
        f"- scale_mean: {summary['scale_mean']:.8g}",
        f"- scale_std: {summary['scale_std']:.8g}",
        f"- scale_range: {summary['scale_min']:.8g} .. {summary['scale_max']:.8g}",
        f"- rotation_angle_deg_mean: {summary['rotation_angle_deg_mean']:.8g}",
        f"- rotation_angle_deg_max: {summary['rotation_angle_deg_max']:.8g}",
        f"- translation_norm_mean: {summary['translation_norm_mean']:.8g}",
        f"- translation_norm_max: {summary['translation_norm_max']:.8g}",
        "",
        "## Edges",
        "",
        "| edge | parent | current | overlap | points | scale | rot deg | trans | rmse | p90 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for edge in report["edges"]:
        lines.append(
            "| {idx} | {parent} | {current} | {overlap} | {points} | {scale:.8g} | {rot:.8g} | {trans:.8g} | {rmse:.8g} | {p90:.8g} |".format(
                idx=edge.get("edgeIndex"),
                parent=edge.get("parentWindowID"),
                current=edge.get("currentWindowID"),
                overlap=edge.get("overlapFrameCount"),
                points=edge.get("point_count", 0),
                scale=float(edge.get("sim3_scale", math.nan)),
                rot=float(edge.get("sim3_rotation_angle_deg", math.nan)),
                trans=float(edge.get("sim3_translation_norm", math.nan)),
                rmse=float(edge.get("rmse", math.nan)),
                p90=float(edge.get("p90", math.nan)),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "capture_dir": report["inputs"]["capture_dir"],
        "confidence_mode": report["inputs"]["confidence_mode"],
        "windowing": report["windowing"],
        "edge_count": report["edge_count"],
        "estimated_edge_count": report["estimated_edge_count"],
        "summary": report["summary"],
        "out_json": str(Path(report["inputs"]["capture_dir"]).parent / "diagnostics"),
        "elapsed_s": report["elapsed_s"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
