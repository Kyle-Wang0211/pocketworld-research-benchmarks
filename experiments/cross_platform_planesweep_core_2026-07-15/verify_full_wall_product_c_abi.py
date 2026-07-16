#!/usr/bin/env python3
"""Run the product C ABI over every certified wall candidate in a capture."""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import hashlib
import importlib.util
import json
import resource
import sys
import tempfile
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = (
    ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/fr_planesweep_wall_ceiling.py"
)
ABI_HELPER_PATH = Path(__file__).resolve().parent / "verify_product_c_abi_parity.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_patch(reference, point, offsets, frame, image, minimum_std):
    samples = point[None, :] + offsets
    camera_points = (frame.R @ samples.T).T + frame.t
    depth = camera_points[:, 2]
    if np.any(depth <= 0.05):
        return None
    homogeneous = (frame.K @ camera_points.T).T
    xy = homogeneous[:, :2] / depth[:, None]
    if (
        xy[:, 0].min() < 0
        or xy[:, 0].max() > frame.width - 1
        or xy[:, 1].min() < 0
        or xy[:, 1].max() > frame.height - 1
    ):
        return None
    gray = reference.bilinear_rgb(image, xy) @ reference.GRAY_WEIGHTS
    if float(gray.std()) < minimum_std:
        return None
    centered = gray - gray.mean()
    return (centered / (np.linalg.norm(centered) + 1e-9)).astype(np.float32)


def key_set(points: np.ndarray) -> set[tuple[float, float, float]]:
    return {tuple(row) for row in np.round(points, 9)}


def config_from_stats(reference, raw: dict):
    names = {field.name for field in dataclasses.fields(reference.SweepConfig)}
    values = {key: value for key, value in raw.items() if key in names}
    values["depth_competition_offsets_m"] = tuple(
        raw["depth_competition_offsets_m"]
    )
    return reference.SweepConfig(**values)


def reference_surface(reference, surface, floor, frames, base_config, stats_config):
    baseline_xyz, _, baseline_meta, _ = reference.sweep_surface(
        surface, floor, frames, base_config, 0.0
    )
    minimum_views, minimum_parallax, minimum_ncc = (
        reference.scale_rescue_nonregression_thresholds(
            baseline_meta,
            int(stats_config["scale_rescue_min_views"]),
            float(stats_config["scale_rescue_min_parallax_deg"]),
            float(stats_config["scale_rescue_min_ncc"]),
        )
    )
    rescue_config = dataclasses.replace(
        base_config,
        patch_radius_m=float(stats_config["scale_rescue_patch_radius_m"]),
        min_views=int(stats_config["scale_rescue_min_views"]),
        min_parallax_deg=float(stats_config["scale_rescue_min_parallax_deg"]),
        depth_ncc_margin=float(stats_config["scale_rescue_depth_ncc_margin"]),
    )
    rescue_xyz, _, rescue_meta, _ = reference.sweep_surface(
        surface, floor, frames, rescue_config, 0.0
    )
    mask = reference.scale_rescue_quality_mask(
        rescue_meta, minimum_views, minimum_parallax, minimum_ncc
    )
    rescue_xyz = rescue_xyz[mask]
    rescue_meta = rescue_meta[mask]
    merged_xyz, _, _, _ = reference.merge_scale_rescue_results(
        baseline_xyz,
        np.zeros((len(baseline_xyz), 3), dtype=np.float64),
        baseline_meta,
        rescue_xyz,
        np.zeros((len(rescue_xyz), 3), dtype=np.float64),
        rescue_meta,
    )
    return {
        "baseline": baseline_xyz,
        "rescue": rescue_xyz,
        "union": merged_xyz,
        "rescue_config": rescue_config,
        "post_minimum_views": minimum_views,
        "post_minimum_parallax_deg": minimum_parallax,
        "post_min_ncc": minimum_ncc,
    }


def run_c_scale(
    reference,
    abi,
    api,
    surface,
    floor,
    frames,
    config,
    post_minimum_views,
    post_minimum_parallax_deg,
    post_min_ncc,
):
    centers = reference.surface_grid(surface, floor, config.grid_m, 0.0)
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    patch_offsets = reference.patch_offsets(surface, floor, config)
    image_cache = reference.ImageCache(
        frames, max(config.image_cache_images, config.max_views)
    )
    accepted_indices: list[int] = []
    evidence: list[dict] = []
    options = abi.BirthOptions(
        minimum_views=int(config.min_views),
        ncc_min=float(config.ncc_min),
        minimum_parallax_deg=float(config.min_parallax_deg),
        unique_depth_margin=float(config.depth_ncc_margin),
        post_min_ncc=float(post_min_ncc),
        post_minimum_views=int(post_minimum_views),
        post_minimum_parallax_deg=float(post_minimum_parallax_deg),
    )
    depth_offsets = (0.0, *tuple(config.depth_competition_offsets_m))
    for tile_start in range(0, len(centers), config.tile_points):
        tile = centers[tile_start : tile_start + config.tile_points]
        visible, head_on, _ = reference.project_centers(
            tile, frames, normal, config
        )
        selected = reference.select_tile_views(visible, head_on, config.max_views)
        if not selected:
            continue
        images = image_cache.get_many(selected)
        hypotheses = (
            tile[:, None, :]
            + normal[None, None, :] * np.asarray(depth_offsets)[None, :, None]
        ).reshape(-1, 3)
        hypothesis_visible, _, _ = reference.project_centers(
            hypotheses, frames, normal, config
        )
        point_count = len(hypotheses)
        view_count = len(selected)
        sample_count = config.patch_n * config.patch_n
        patches = np.zeros(
            (view_count, point_count, sample_count), dtype=np.float32
        )
        valid = np.zeros((view_count, point_count), dtype=np.uint8)
        masks = np.zeros((point_count, view_count), dtype=np.uint8)
        for local_view, frame_index in enumerate(selected):
            masks[:, local_view] = hypothesis_visible[frame_index].astype(np.uint8)
            frame = frames[frame_index]
            image = images[frame_index]
            for point_index, point in enumerate(hypotheses):
                if masks[point_index, local_view] == 0:
                    continue
                patch = normalized_patch(
                    reference, point, patch_offsets, frame, image, config.min_std
                )
                if patch is None:
                    continue
                patches[local_view, point_index] = patch
                valid[local_view, point_index] = 1
        cameras = np.asarray([frames[index].C for index in selected], dtype=np.float32)
        points_f32 = np.ascontiguousarray(hypotheses, dtype=np.float32)
        supporting = np.zeros(point_count, dtype=np.int32)
        ncc = np.full(point_count, -np.inf, dtype=np.float32)
        parallax = np.zeros(point_count, dtype=np.float32)
        score_valid = np.zeros(point_count, dtype=np.uint8)
        rc = api.aether_planesweep_score_scale(
            abi.pointer(patches, ctypes.c_float),
            abi.pointer(valid, ctypes.c_uint8),
            abi.pointer(masks, ctypes.c_uint8),
            abi.pointer(cameras, ctypes.c_float),
            abi.pointer(points_f32, ctypes.c_float),
            view_count,
            point_count,
            sample_count,
            ctypes.byref(options),
            abi.pointer(supporting, ctypes.c_int32),
            abi.pointer(ncc, ctypes.c_float),
            abi.pointer(parallax, ctypes.c_float),
            abi.pointer(score_valid, ctypes.c_uint8),
        )
        if rc != 0:
            raise RuntimeError(f"score_scale failed at tile {tile_start}: {rc}")
        results = (abi.CandidateResult * len(tile))()
        rc = api.aether_planesweep_apply_unique_depth(
            len(tile),
            len(depth_offsets),
            abi.pointer(supporting, ctypes.c_int32),
            abi.pointer(ncc, ctypes.c_float),
            abi.pointer(parallax, ctypes.c_float),
            abi.pointer(score_valid, ctypes.c_uint8),
            ctypes.byref(options),
            results,
            len(tile),
            0,
        )
        if rc != 0:
            raise RuntimeError(f"apply_unique_depth failed at tile {tile_start}: {rc}")
        for local_index, result in enumerate(results):
            if not result.accepted:
                continue
            global_index = tile_start + local_index
            accepted_indices.append(global_index)
            evidence.append(
                {
                    "grid_index": global_index,
                    "views": int(result.supporting_views),
                    "ncc": float(result.median_ncc),
                    "parallax_deg": float(result.max_parallax_deg),
                    "observed_depth_margin": (
                        float(result.observed_depth_margin)
                        if np.isfinite(result.observed_depth_margin)
                        else None
                    ),
                }
            )
    return centers[np.asarray(accepted_indices, dtype=np.int64)], evidence, {
        "decoded_image_loads": image_cache.loads,
        "peak_loaded_image_bytes": image_cache.peak_bytes,
    }


def compare_points(actual: np.ndarray, expected: np.ndarray) -> dict:
    actual_set = key_set(actual)
    expected_set = key_set(expected)
    return {
        "actual": len(actual_set),
        "expected": len(expected_set),
        "exact": actual_set == expected_set,
        "missing": [list(point) for point in sorted(expected_set - actual_set)[:16]],
        "unexpected": [list(point) for point in sorted(actual_set - expected_set)[:16]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--photo-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reference = load_module("pw_full_wall_reference", REFERENCE_PATH)
    abi = load_module("pw_planesweep_abi_helper", ABI_HELPER_PATH)
    stats_path = args.stats.resolve()
    stats = json.loads(stats_path.read_text())
    config = config_from_stats(reference, stats["config"])
    planes_path = ROOT / stats["inputs"]["planes"]["path"]
    meta_path = ROOT / stats["inputs"]["frame_meta"]["path"]
    ledger_path = ROOT / stats["inputs"]["ledger"]["path"]
    planes = json.loads(planes_path.read_text())
    floor = planes["floor"]
    surfaces_by_id = {surface["surface_id"]: surface for surface in planes["surfaces"]}
    surface_stats = {surface["surface_id"]: surface for surface in stats["surfaces"]}
    frames = reference.load_frames(meta_path, ledger_path, args.photo_dir.resolve())
    started = time.perf_counter()
    surface_results = []

    with tempfile.TemporaryDirectory(prefix="pw_full_wall_cabi_") as temp:
        library_path = Path(temp) / "libplanesweep.dylib"
        compile_command = abi.compile_library(args.aether_root.resolve(), library_path)
        api = abi.load_api(library_path)
        for surface_id in surface_stats:
            surface = surfaces_by_id[surface_id]
            frozen = reference_surface(
                reference, surface, floor, frames, config, stats["config"]
            )
            baseline_actual, baseline_evidence, baseline_resources = run_c_scale(
                reference,
                abi,
                api,
                surface,
                floor,
                frames,
                config,
                0,
                0.0,
                0.0,
            )
            rescue_actual, rescue_evidence, rescue_resources = run_c_scale(
                reference,
                abi,
                api,
                surface,
                floor,
                frames,
                frozen["rescue_config"],
                frozen["post_minimum_views"],
                frozen["post_minimum_parallax_deg"],
                frozen["post_min_ncc"],
            )
            baseline_keys = key_set(baseline_actual)
            rescue_unique = np.asarray(
                [point for point in rescue_actual if tuple(np.round(point, 9)) not in baseline_keys],
                dtype=np.float64,
            ).reshape(-1, 3)
            union_actual = np.concatenate([baseline_actual, rescue_unique], axis=0)
            baseline_comparison = compare_points(baseline_actual, frozen["baseline"])
            rescue_comparison = compare_points(rescue_actual, frozen["rescue"])
            union_comparison = compare_points(union_actual, frozen["union"])
            expected_final = int(surface_stats[surface_id]["accepted"])
            surface_results.append(
                {
                    "surface_id": surface_id,
                    "grid_candidates": len(
                        reference.surface_grid(surface, floor, config.grid_m, 0.0)
                    ),
                    "baseline": baseline_comparison,
                    "rescue_after_quality_gate": rescue_comparison,
                    "union": union_comparison,
                    "frozen_stats_final_count": expected_final,
                    "frozen_stats_count_exact": union_comparison["actual"] == expected_final,
                    "post_gate": {
                        "minimum_views": frozen["post_minimum_views"],
                        "minimum_parallax_deg": frozen["post_minimum_parallax_deg"],
                        "minimum_ncc": frozen["post_min_ncc"],
                    },
                    "baseline_evidence": baseline_evidence,
                    "rescue_evidence": rescue_evidence,
                    "resources": {
                        "baseline": baseline_resources,
                        "rescue": rescue_resources,
                    },
                }
            )

    all_exact = all(
        surface[phase]["exact"]
        for surface in surface_results
        for phase in ("baseline", "rescue_after_quality_gate", "union")
    ) and all(surface["frozen_stats_count_exact"] for surface in surface_results)
    source_path = (
        args.aether_root.resolve()
        / "aether_cpp/src/pipeline/aether_structural_planesweep_c.cpp"
    )
    result = {
        "schema": "pocketworld_full_wall_product_c_abi_parity_v1",
        "decision": (
            "PASS_FULL_WALL_PRODUCT_C_ABI_EXACT_PARITY"
            if all_exact
            else "FAIL_FULL_WALL_PRODUCT_C_ABI_PARITY"
        ),
        "stats_path": str(stats_path),
        "stats_sha256": sha256(stats_path),
        "product_source": str(source_path),
        "product_source_sha256": sha256(source_path),
        "compile_command": compile_command,
        "frame_count": len(frames),
        "surface_count": len(surface_results),
        "total_grid_candidates": sum(
            surface["grid_candidates"] for surface in surface_results
        ),
        "elapsed_s": time.perf_counter() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "surfaces": surface_results,
        "no_matcher_lidar_or_scene_depth_consumed": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.write_text(encoded)
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "frame_count": result["frame_count"],
                "surface_count": result["surface_count"],
                "total_grid_candidates": result["total_grid_candidates"],
                "elapsed_s": result["elapsed_s"],
                "peak_rss_bytes": result["peak_rss_bytes"],
                "surface_counts": [
                    {
                        "surface_id": surface["surface_id"],
                        "baseline": surface["baseline"]["actual"],
                        "rescue": surface["rescue_after_quality_gate"]["actual"],
                        "union": surface["union"]["actual"],
                        "exact": surface["union"]["exact"],
                    }
                    for surface in surface_results
                ],
            },
            indent=2,
        )
    )
    return 0 if all_exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
