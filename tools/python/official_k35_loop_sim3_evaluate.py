#!/usr/bin/env python3
"""Evaluate DA3-BASE K35 official-style loop Sim3 and Sim3LoopOptimizer outputs."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


RESEARCH_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DA3_STREAMING = RESEARCH_ROOT / "tools/vendor/official_da3_streaming"
if str(OFFICIAL_DA3_STREAMING) not in sys.path:
    sys.path.insert(0, str(OFFICIAL_DA3_STREAMING))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequential-capture-dir", type=Path, required=True)
    parser.add_argument("--sequential-da3-dir", type=Path, required=True)
    parser.add_argument("--vpr-backend-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    seq_plan = read_json(args.sequential_capture_dir / "da3_k_windows.json")
    seq_report = read_json(args.sequential_da3_dir / "mac_da3_window_reports.json")
    retrieval_report = read_json(args.vpr_backend_dir / "loop_retrieval_report.json")
    loop_capture_dir = args.vpr_backend_dir / "loop_capture"
    loop_da3_dir = args.vpr_backend_dir / "loop_da3"
    loop_plan = read_json(loop_capture_dir / "da3_k_windows.json")
    loop_report = read_json(loop_da3_dir / "mac_da3_window_reports.json")

    seq_report_by_window = {
        str(window["windowID"]): window for window in seq_report.get("windows", [])
    }
    loop_report_by_window = {
        str(window["windowID"]): window for window in loop_report.get("windows", [])
    }

    sequential_transforms, adjacent_edges = estimate_sequential_transforms(
        seq_plan=seq_plan,
        seq_report_by_window=seq_report_by_window,
        da3_dir=args.sequential_da3_dir,
    )
    loop_constraints, loop_edges = estimate_loop_constraints(
        loop_plan=loop_plan,
        loop_report_by_window=loop_report_by_window,
        seq_report_by_window=seq_report_by_window,
        seq_da3_dir=args.sequential_da3_dir,
        loop_da3_dir=loop_da3_dir,
    )
    optimizer_report = run_optimizer(sequential_transforms, loop_constraints)
    report = {
        "schema_version": "aether_official_da3_k35_loop_sim3_eval_v1",
        "backend": retrieval_report.get("backend"),
        "route": "DA3-BASE K35 sequential -> VPR loop retrieval -> official loop chunks -> dense Sim3 -> Sim3LoopOptimizer",
        "note": (
            "Dense Sim3 uses the same weighted Sim3/IRLS math as the official DA3-Streaming "
            "path. The official Triton module is not imported on this Mac because Triton is "
            "not available; the optimizer itself is the official Sim3LoopOptimizer."
        ),
        "sequential_window_count": len(seq_plan.get("windows", [])),
        "loop_window_count": len(loop_plan.get("windows", [])),
        "adjacent_edge_count": len(adjacent_edges),
        "loop_constraint_count": len(loop_constraints),
        "retrieval": {
            "raw_loop_pair_count": retrieval_report.get("raw_loop_pair_count"),
            "loop_result_count": retrieval_report.get("loop_result_count"),
            "threshold_sweep": retrieval_report.get("threshold_sweep"),
            "parameters": retrieval_report.get("parameters"),
        },
        "adjacent": summarize_edges(adjacent_edges),
        "loop": summarize_edges(loop_edges),
        "optimizer": optimizer_report,
        "adjacent_edges": adjacent_edges,
        "loop_edges": loop_edges,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2)[:20000])
    return 0


def estimate_sequential_transforms(
    *,
    seq_plan: dict[str, Any],
    seq_report_by_window: dict[str, dict[str, Any]],
    da3_dir: Path,
) -> tuple[list[tuple[float, np.ndarray, np.ndarray]], list[dict[str, Any]]]:
    transforms = []
    edges = []
    windows = list(seq_plan.get("windows", []))
    for index in range(1, len(windows)):
        current = windows[index]
        parent_id = str(current.get("parentWindowID") or windows[index - 1].get("id"))
        current_id = str(current.get("id"))
        parent_rows = rows_by_frame(seq_report_by_window[parent_id])
        current_rows = rows_by_frame(seq_report_by_window[current_id])
        shared = [str(frame_id) for frame_id in current.get("bridgeFrameIDs", [])]
        target_rows = [parent_rows[fid] for fid in shared if fid in parent_rows and fid in current_rows]
        source_rows = [current_rows[fid] for fid in shared if fid in parent_rows and fid in current_rows]
        transform, edge = estimate_dense_sim3_rows(
            target_rows=target_rows,
            source_rows=source_rows,
            target_da3_dir=da3_dir,
            source_da3_dir=da3_dir,
        )
        transforms.append(transform_to_tuple(transform))
        edges.append(
            {
                "edgeType": "adjacent",
                "parentWindowID": parent_id,
                "currentWindowID": current_id,
                "sharedFrameCount": len(target_rows),
                **edge,
            }
        )
    return transforms, edges


def estimate_loop_constraints(
    *,
    loop_plan: dict[str, Any],
    loop_report_by_window: dict[str, dict[str, Any]],
    seq_report_by_window: dict[str, dict[str, Any]],
    seq_da3_dir: Path,
    loop_da3_dir: Path,
) -> tuple[list[tuple[int, int, tuple[float, np.ndarray, np.ndarray]]], list[dict[str, Any]]]:
    constraints = []
    edges = []
    for loop_window in loop_plan.get("windows", []):
        window_id = str(loop_window.get("id"))
        if window_id not in loop_report_by_window:
            continue
        chunk = loop_window.get("loopChunk") or {}
        chunk_a = int(chunk["chunkIndexA"])
        chunk_b = int(chunk["chunkIndexB"])
        range_a = [int(v) for v in chunk["rangeA"]]
        range_b = [int(v) for v in chunk["rangeB"]]
        slot_a = [int(v) for v in chunk["slotRangeA"]]
        slot_b = [int(v) for v in chunk["slotRangeB"]]

        seq_a = seq_report_by_window[f"window_{chunk_a:03d}"]
        seq_b = seq_report_by_window[f"window_{chunk_b:03d}"]
        original_a_rows = rows_by_global_index(seq_a, range_a[0], range_a[1])
        original_b_rows = rows_by_global_index(seq_b, range_b[0], range_b[1])
        loop_rows = sorted(
            loop_report_by_window[window_id].get("frames", []),
            key=lambda row: int(row.get("windowSlot", 0)),
        )
        loop_a_rows = loop_rows[slot_a[0] : slot_a[1]]
        loop_b_rows = loop_rows[slot_b[0] : slot_b[1]]
        if not original_a_rows or not original_b_rows or not loop_a_rows or not loop_b_rows:
            edges.append(
                {
                    "edgeType": "loop",
                    "loopWindowID": window_id,
                    "chunkIndexA": chunk_a,
                    "chunkIndexB": chunk_b,
                    "status": "skipped_missing_rows",
                }
            )
            continue
        transform_a, edge_a = estimate_dense_sim3_rows(
            target_rows=original_a_rows,
            source_rows=loop_a_rows,
            target_da3_dir=seq_da3_dir,
            source_da3_dir=loop_da3_dir,
        )
        transform_b, edge_b = estimate_dense_sim3_rows(
            target_rows=original_b_rows,
            source_rows=loop_b_rows,
            target_da3_dir=seq_da3_dir,
            source_da3_dir=loop_da3_dir,
        )
        loop_ab = compute_sim3_ab(transform_to_tuple(transform_a), transform_to_tuple(transform_b))
        constraints.append((chunk_a, chunk_b, loop_ab))
        edges.append(
            {
                "edgeType": "loop",
                "loopWindowID": window_id,
                "chunkIndexA": chunk_a,
                "chunkIndexB": chunk_b,
                "rangeA": range_a,
                "rangeB": range_b,
                "status": "estimated",
                "a_point_count": edge_a.get("point_count"),
                "b_point_count": edge_b.get("point_count"),
                "a_rmse": edge_a.get("rmse"),
                "b_rmse": edge_b.get("rmse"),
                "a_p90": edge_a.get("p90"),
                "b_p90": edge_b.get("p90"),
                "sim3_scale": float(loop_ab[0]),
            }
        )
    return constraints, edges


def estimate_dense_sim3_rows(
    *,
    target_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    target_da3_dir: Path,
    source_da3_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target_points = []
    source_points = []
    weights = []
    median_confs = []
    payloads = []
    for target_row, source_row in zip(target_rows, source_rows):
        target_map, target_conf = load_point_map_and_conf(target_row, target_da3_dir)
        source_map, source_conf = load_point_map_and_conf(source_row, source_da3_dir)
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
        weights.append(np.sqrt(target_conf[mask].astype(np.float64) * source_conf[mask].astype(np.float64)))
    if not source_points:
        raise ValueError("No dense correspondences survived the confidence mask")
    src = np.concatenate(source_points, axis=0).astype(np.float64)
    dst = np.concatenate(target_points, axis=0).astype(np.float64)
    weight = np.concatenate(weights, axis=0).astype(np.float64)
    transform = robust_weighted_sim3(src, dst, weight, delta=0.1, max_iters=5, tol=1e-9)
    residual = np.linalg.norm(apply_sim3(src, transform) - dst, axis=1)
    return transform, {
        "status": "estimated",
        "point_count": int(src.shape[0]),
        "confidence_threshold": float(conf_threshold),
        "rmse": float(np.sqrt(np.mean(residual * residual))),
        "median": float(np.median(residual)),
        "p90": float(np.percentile(residual, 90)),
        "sim3_scale": float(transform["scale"]),
    }


def run_optimizer(
    sequential_transforms: list[tuple[float, np.ndarray, np.ndarray]],
    loop_constraints: list[tuple[int, int, tuple[float, np.ndarray, np.ndarray]]],
) -> dict[str, Any]:
    if not loop_constraints:
        return {"status": "not_run_no_loop_constraints"}
    from loop_utils.sim3loop import Sim3LoopOptimizer

    config = {
        "Loop": {
            "SIM3_Optimizer": {
                "lang_version": "python",
                "max_iterations": 30,
                "lambda_init": "1e-6",
            }
        }
    }
    started = time.perf_counter()
    try:
        optimizer = Sim3LoopOptimizer(config)
        optimized = optimizer.optimize(sequential_transforms, loop_constraints)
    except Exception as exc:
        return {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(time.perf_counter() - started, 3),
        }
    return {
        "status": "completed",
        "sequential_transform_count": len(sequential_transforms),
        "optimized_transform_count": len(optimized),
        "loop_constraint_count": len(loop_constraints),
        "pre_scale_mean": safe_mean([row[0] for row in sequential_transforms]),
        "post_scale_mean": safe_mean([row[0] for row in optimized]),
        "pre_scale_std": safe_std([row[0] for row in sequential_transforms]),
        "post_scale_std": safe_std([row[0] for row in optimized]),
        "elapsed_s": round(time.perf_counter() - started, 3),
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
            previous_error < float("inf") and abs(previous_error - current_error) < tol * max(previous_error, 1e-12)
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


def compute_sim3_ab(
    transform_a: tuple[float, np.ndarray, np.ndarray],
    transform_b: tuple[float, np.ndarray, np.ndarray],
) -> tuple[float, np.ndarray, np.ndarray]:
    s_a, r_a, t_a = transform_a
    s_b, r_b, t_b = transform_b
    s_ab = s_b / s_a
    r_ab = r_b @ r_a.T
    t_ab = t_b - s_ab * (r_ab @ t_a)
    return (float(s_ab), r_ab, t_ab)


def apply_sim3(points: np.ndarray, transform: dict[str, Any]) -> np.ndarray:
    return float(transform["scale"]) * (
        points.astype(np.float64) @ np.asarray(transform["rotation"], dtype=np.float64).T
    ) + np.asarray(transform["translation"], dtype=np.float64)


def huber_loss(residual: np.ndarray, delta: float) -> np.ndarray:
    abs_residual = np.abs(residual)
    return np.where(abs_residual <= delta, 0.5 * residual * residual, delta * (abs_residual - 0.5 * delta))


def rows_by_frame(window_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(frame["frameID"]): frame for frame in window_report.get("frames", [])}


def rows_by_global_index(window_report: dict[str, Any], start: int, end: int) -> list[dict[str, Any]]:
    rows = sorted(window_report.get("frames", []), key=lambda row: int(row.get("frameIndex", 0)))
    return [row for row in rows if start <= int(row.get("frameIndex", -1)) < end]


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
        "rmse_mean": safe_mean([edge.get("rmse") for edge in edges]),
        "p90_mean": safe_mean([edge.get("p90") for edge in edges]),
        "scale_mean": safe_mean([edge.get("sim3_scale") for edge in edges]),
        "scale_std": safe_std([edge.get("sim3_scale") for edge in edges]),
        "a_rmse_mean": safe_mean([edge.get("a_rmse") for edge in edges]),
        "b_rmse_mean": safe_mean([edge.get("b_rmse") for edge in edges]),
    }


def safe_mean(values: list[Any]) -> float:
    arr = np.asarray([float(value) for value in values if value is not None and np.isfinite(float(value))], dtype=np.float64)
    return float(np.mean(arr)) if arr.size else math.nan


def safe_std(values: list[Any]) -> float:
    arr = np.asarray([float(value) for value in values if value is not None and np.isfinite(float(value))], dtype=np.float64)
    return float(np.std(arr)) if arr.size else math.nan


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
