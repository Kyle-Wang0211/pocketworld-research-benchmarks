#!/usr/bin/env python3
"""Export DA3-BASE K35 official-loop aligned point cloud and standard fusion previews."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps


RESEARCH_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = RESEARCH_ROOT / "tools/python"
OFFICIAL_DA3_STREAMING = RESEARCH_ROOT / "tools/vendor/official_da3_streaming"
for path in (TOOLS_DIR, OFFICIAL_DA3_STREAMING):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import official_k35_loop_sim3_evaluate as loop_eval  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequential-capture-dir", type=Path, required=True)
    parser.add_argument("--sequential-da3-dir", type=Path, required=True)
    parser.add_argument("--vpr-backend-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sample-ratio", type=float, default=0.015)
    parser.add_argument("--conf-threshold-coef", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=35)
    parser.add_argument("--poisson-depth", type=int, default=8)
    args = parser.parse_args()

    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    seq_plan = read_json(args.sequential_capture_dir / "da3_k_windows.json")
    seq_report = read_json(args.sequential_da3_dir / "mac_da3_window_reports.json")
    retrieval_report = read_json(args.vpr_backend_dir / "loop_retrieval_report.json")
    loop_plan = read_json(args.vpr_backend_dir / "loop_capture" / "da3_k_windows.json")
    loop_report = read_json(args.vpr_backend_dir / "loop_da3" / "mac_da3_window_reports.json")

    seq_report_by_window = {str(window["windowID"]): window for window in seq_report.get("windows", [])}
    loop_report_by_window = {str(window["windowID"]): window for window in loop_report.get("windows", [])}

    print("Estimating adjacent dense Sim3 edges...")
    sequential_transforms, adjacent_edges = loop_eval.estimate_sequential_transforms(
        seq_plan=seq_plan,
        seq_report_by_window=seq_report_by_window,
        da3_dir=args.sequential_da3_dir,
    )
    print("Estimating official loop dense Sim3 constraints...")
    loop_constraints, loop_edges = loop_eval.estimate_loop_constraints(
        loop_plan=loop_plan,
        loop_report_by_window=loop_report_by_window,
        seq_report_by_window=seq_report_by_window,
        seq_da3_dir=args.sequential_da3_dir,
        loop_da3_dir=args.vpr_backend_dir / "loop_da3",
    )
    optimizer = run_official_optimizer(sequential_transforms, loop_constraints)
    optimized_transforms = optimizer.pop("optimized_transforms", [])
    if optimizer.get("status") != "completed" or not optimized_transforms:
        raise RuntimeError(f"Official Sim3LoopOptimizer did not complete: {optimizer}")

    cumulative = accumulate_sim3_transforms(optimized_transforms)
    transforms_by_window = {"window_000": identity_transform()}
    for index, transform in enumerate(cumulative, start=1):
        transforms_by_window[f"window_{index:03d}"] = tuple_to_transform(transform)

    transforms_path = args.out_dir / "official_loop_optimized_window_transforms.json"
    write_json(
        transforms_path,
        {
            "schema_version": "pocketworld_official_da3_k35_loop_optimized_transforms_v1",
            "route": "DA3-BASE K35@476x742 official sequential chunks -> SelaVPR++ -> official loop chunks -> dense Sim3 -> official Sim3LoopOptimizer",
            "backend": retrieval_report.get("backend"),
            "transforms": transforms_by_window,
        },
    )

    print("Projecting optimized DA3 point maps into the shared root frame...")
    depth_index = read_json(args.sequential_da3_dir / "depth_index.json")
    raw_points, raw_colors, export_stats = export_sampled_points(
        frames=depth_index.get("frames", []),
        capture_dir=args.sequential_capture_dir,
        da3_dir=args.sequential_da3_dir,
        transforms_by_window=transforms_by_window,
        sample_ratio=args.sample_ratio,
        conf_threshold_coef=args.conf_threshold_coef,
        seed=args.seed,
    )

    raw_ply = args.out_dir / "official_loop_optimizer_raw_sampled.ply"
    fused_ply = args.out_dir / "official_loop_optimizer_voxel_clean.ply"
    mesh_ply = args.out_dir / "official_loop_optimizer_poisson_mesh.ply"
    write_open3d_outputs(
        points=raw_points,
        colors=raw_colors,
        raw_ply=raw_ply,
        fused_ply=fused_ply,
        mesh_ply=mesh_ply,
        poisson_depth=args.poisson_depth,
    )

    report = {
        "schema_version": "pocketworld_official_da3_k35_loop_fusion_export_v1",
        "backend": retrieval_report.get("backend"),
        "route": "official DA3 streaming route plus standard Open3D pointcloud/mesh fusion preview",
        "inputs": {
            "sequential_capture_dir": str(args.sequential_capture_dir),
            "sequential_da3_dir": str(args.sequential_da3_dir),
            "vpr_backend_dir": str(args.vpr_backend_dir),
        },
        "official_streaming": {
            "sequential_window_count": len(seq_plan.get("windows", [])),
            "loop_window_count": len(loop_plan.get("windows", [])),
            "adjacent_edge_count": len(adjacent_edges),
            "loop_constraint_count": len(loop_constraints),
            "adjacent": loop_eval.summarize_edges(adjacent_edges),
            "loop": loop_eval.summarize_edges(loop_edges),
            "optimizer": optimizer,
        },
        "fusion": {
            **export_stats,
            "raw_ply": str(raw_ply),
            "fused_ply": str(fused_ply),
            "mesh_ply": str(mesh_ply),
            "sample_ratio": args.sample_ratio,
            "conf_threshold_coef": args.conf_threshold_coef,
            "poisson_depth": args.poisson_depth,
        },
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    report_path = args.out_dir / "official_loop_fusion_export_report.json"
    write_json(report_path, report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def run_official_optimizer(
    sequential_transforms: list[tuple[float, np.ndarray, np.ndarray]],
    loop_constraints: list[tuple[int, int, tuple[float, np.ndarray, np.ndarray]]],
) -> dict[str, Any]:
    if not loop_constraints:
        return {"status": "not_run_no_loop_constraints", "optimized_transforms": []}
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
    optimizer = Sim3LoopOptimizer(config)
    optimized = optimizer.optimize(sequential_transforms, loop_constraints)
    return {
        "status": "completed",
        "sequential_transform_count": len(sequential_transforms),
        "optimized_transform_count": len(optimized),
        "loop_constraint_count": len(loop_constraints),
        "pre_scale_mean": loop_eval.safe_mean([row[0] for row in sequential_transforms]),
        "post_scale_mean": loop_eval.safe_mean([row[0] for row in optimized]),
        "pre_scale_std": loop_eval.safe_std([row[0] for row in sequential_transforms]),
        "post_scale_std": loop_eval.safe_std([row[0] for row in optimized]),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "optimized_transforms": optimized,
    }


def accumulate_sim3_transforms(
    transforms: list[tuple[float, np.ndarray, np.ndarray]]
) -> list[tuple[float, np.ndarray, np.ndarray]]:
    """Official DA3 Streaming accumulate_sim3_transforms, copied to avoid Triton import on Mac."""
    if not transforms:
        return []

    cumulative_transforms = [transforms[0]]

    for i in range(1, len(transforms)):
        s_cum_prev, r_cum_prev, t_cum_prev = cumulative_transforms[i - 1]
        s_next, r_next, t_next = transforms[i]
        r_cum_new = r_cum_prev @ r_next
        s_cum_new = s_cum_prev * s_next
        t_cum_new = s_cum_prev * (r_cum_prev @ t_next) + t_cum_prev
        cumulative_transforms.append((s_cum_new, r_cum_new, t_cum_new))

    return cumulative_transforms


def export_sampled_points(
    *,
    frames: list[dict[str, Any]],
    capture_dir: Path,
    da3_dir: Path,
    transforms_by_window: dict[str, dict[str, Any]],
    sample_ratio: float,
    conf_threshold_coef: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    rng = np.random.default_rng(seed)
    all_points: list[np.ndarray] = []
    all_colors: list[np.ndarray] = []
    skipped = 0
    valid_before_sampling = 0

    for index, frame in enumerate(frames):
        window_id = str(frame.get("windowID"))
        transform = transforms_by_window.get(window_id)
        if transform is None:
            skipped += 1
            continue
        point_map, conf = loop_eval.load_point_map_and_conf(frame, da3_dir)
        conf_threshold = float(np.mean(conf)) * conf_threshold_coef
        flat_points = point_map.reshape(-1, 3)
        flat_conf = conf.reshape(-1)
        mask = np.isfinite(flat_points).all(axis=1) & np.isfinite(flat_conf) & (flat_conf >= conf_threshold) & (flat_conf > 1e-5)
        valid_indices = np.flatnonzero(mask)
        valid_before_sampling += int(valid_indices.size)
        if valid_indices.size == 0:
            skipped += 1
            continue
        sample_count = max(1, int(valid_indices.size * sample_ratio))
        if sample_count < valid_indices.size:
            selected = rng.choice(valid_indices, size=sample_count, replace=False)
        else:
            selected = valid_indices

        sampled_points = apply_sim3(flat_points[selected], transform).astype(np.float32)
        sampled_colors = load_frame_colors(frame, capture_dir).reshape(-1, 3)[selected]
        all_points.append(sampled_points)
        all_colors.append(sampled_colors.astype(np.float32) / 255.0)

        if index % 25 == 0:
            print(f"  sampled frame {index + 1}/{len(frames)}: {sum(len(v) for v in all_points):,} points")

    if not all_points:
        raise RuntimeError("No sampled points were produced")
    points = np.concatenate(all_points, axis=0)
    colors = np.concatenate(all_colors, axis=0)
    finite = np.isfinite(points).all(axis=1)
    points = points[finite]
    colors = colors[finite]
    return points, colors, {
        "frame_count": len(frames),
        "skipped_frame_count": skipped,
        "valid_point_count_before_sampling": int(valid_before_sampling),
        "raw_sampled_point_count": int(points.shape[0]),
    }


def write_open3d_outputs(
    *,
    points: np.ndarray,
    colors: np.ndarray,
    raw_ply: Path,
    fused_ply: Path,
    mesh_ply: Path,
    poisson_depth: int,
) -> None:
    import open3d as o3d

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(np.clip(colors.astype(np.float64), 0.0, 1.0))
    o3d.io.write_point_cloud(str(raw_ply), pcd, write_ascii=False, compressed=False)

    bbox = pcd.get_axis_aligned_bounding_box()
    diag = float(np.linalg.norm(np.asarray(bbox.get_extent())))
    voxel_size = min(max(diag / 450.0, 0.002), 0.02) if math.isfinite(diag) and diag > 0 else 0.005
    print(f"Open3D voxel fusion: bbox_diag={diag:.4f}, voxel_size={voxel_size:.5f}")
    fused = pcd.voxel_down_sample(voxel_size)
    if len(fused.points) > 64:
        fused, _ = fused.remove_statistical_outlier(nb_neighbors=24, std_ratio=2.0)
    if len(fused.points) > 64:
        fused, _ = fused.remove_radius_outlier(nb_points=4, radius=voxel_size * 5.0)
    o3d.io.write_point_cloud(str(fused_ply), fused, write_ascii=False, compressed=False)

    if len(fused.points) < 256:
        print("Skipping Poisson mesh: not enough fused points")
        return
    fused.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel_size * 8.0, max_nn=40))
    try:
        fused.orient_normals_consistent_tangent_plane(30)
    except Exception as exc:
        print(f"Normal orientation warning: {type(exc).__name__}: {exc}")
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(fused, depth=poisson_depth)
    densities_np = np.asarray(densities)
    if densities_np.size:
        keep = densities_np > np.quantile(densities_np, 0.06)
        mesh.remove_vertices_by_mask(~keep)
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(str(mesh_ply), mesh, write_ascii=False, compressed=False)


def load_frame_colors(frame: dict[str, Any], capture_dir: Path) -> np.ndarray:
    width = int(frame["depthWidth"])
    height = int(frame["depthHeight"])
    image_path = capture_dir / str(frame["imageRelativePath"])
    image = Image.open(image_path)
    image = ImageOps.exif_transpose(image).convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
    return np.asarray(image, dtype=np.uint8)


def apply_sim3(points: np.ndarray, transform: dict[str, Any]) -> np.ndarray:
    return float(transform["scale"]) * (
        points.astype(np.float64) @ np.asarray(transform["rotation"], dtype=np.float64).T
    ) + np.asarray(transform["translation"], dtype=np.float64)


def identity_transform() -> dict[str, Any]:
    return {"scale": 1.0, "rotation": np.eye(3), "translation": np.zeros(3)}


def tuple_to_transform(transform: tuple[float, np.ndarray, np.ndarray]) -> dict[str, Any]:
    scale, rotation, translation = transform
    return {
        "scale": float(scale),
        "rotation": np.asarray(rotation, dtype=np.float64),
        "translation": np.asarray(translation, dtype=np.float64),
    }


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "backend": report["backend"],
        "official_streaming": report["official_streaming"]["optimizer"],
        "fusion": report["fusion"],
        "elapsed_s": report["elapsed_s"],
    }


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
