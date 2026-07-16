#!/usr/bin/env python3
"""Verify selected-floor Python oracle and shared C ABI birth sets exactly."""

from __future__ import annotations

import argparse
import ctypes
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
FULL_HELPER_PATH = Path(__file__).resolve().parent / "verify_full_wall_product_c_abi.py"
REFERENCE_PATH = (
    ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/"
    "fr_planesweep_wall_ceiling.py"
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


def capture_name(selection_path: Path) -> str:
    for part in selection_path.parts:
        prefix = part.split("_", 1)[0]
        if prefix.startswith("cap") and prefix[3:].isdigit():
            return prefix
    name = selection_path.name
    for candidate in ("cap40", "cap41", "cap50", "cap51"):
        if candidate in name:
            return candidate
    raise RuntimeError(f"cannot identify capture from {selection_path}")


def run_c_floor_scale(reference, full, abi, api, surface, frames, config):
    """Mirror the floor oracle's per-point top-view selection exactly."""
    centers = reference.surface_grid(surface, surface, config.grid_m, 0.0)
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    patch_offsets = reference.patch_offsets(surface, surface, config)
    image_cache = reference.ImageCache(
        frames, max(config.image_cache_images, config.max_views)
    )
    accepted_indices = []
    evidence = []
    depth_offsets = (0.0, *tuple(config.depth_competition_offsets_m))
    options = abi.BirthOptions(
        minimum_views=int(config.min_views),
        ncc_min=float(config.ncc_min),
        minimum_parallax_deg=float(config.min_parallax_deg),
        unique_depth_margin=float(config.depth_ncc_margin),
        post_min_ncc=0.0,
        post_minimum_views=0,
        post_minimum_parallax_deg=0.0,
    )
    for tile_start in range(0, len(centers), config.tile_points):
        tile = centers[tile_start : tile_start + config.tile_points]
        visible, head_on, _ = reference.project_centers(
            tile, frames, normal, config
        )
        groups = {}
        for local_index in range(len(tile)):
            selected = tuple(
                reference.select_point_views(
                    visible[:, local_index],
                    head_on[:, local_index],
                    config.max_views,
                )
            )
            if selected:
                groups.setdefault(selected, []).append(local_index)
        for selected_tuple, local_indices_list in groups.items():
            selected = list(selected_tuple)
            local_indices = np.asarray(local_indices_list, dtype=np.int64)
            group_centers = tile[local_indices]
            images = image_cache.get_many(selected)
            hypotheses = (
                group_centers[:, None, :]
                + normal[None, None, :]
                * np.asarray(depth_offsets, dtype=np.float64)[None, :, None]
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
                masks[:, local_view] = hypothesis_visible[frame_index].astype(
                    np.uint8
                )
                frame = frames[frame_index]
                image = images[frame_index]
                for point_index, point in enumerate(hypotheses):
                    if masks[point_index, local_view] == 0:
                        continue
                    patch = full.normalized_patch(
                        reference,
                        point,
                        patch_offsets,
                        frame,
                        image,
                        config.min_std,
                    )
                    if patch is None:
                        continue
                    patches[local_view, point_index] = patch
                    valid[local_view, point_index] = 1
            cameras = np.asarray(
                [frames[index].C for index in selected], dtype=np.float32
            )
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
                raise RuntimeError(
                    f"floor score_scale failed at tile {tile_start}: {rc}"
                )
            results = (abi.CandidateResult * len(group_centers))()
            rc = api.aether_planesweep_apply_unique_depth(
                len(group_centers),
                len(depth_offsets),
                abi.pointer(supporting, ctypes.c_int32),
                abi.pointer(ncc, ctypes.c_float),
                abi.pointer(parallax, ctypes.c_float),
                abi.pointer(score_valid, ctypes.c_uint8),
                ctypes.byref(options),
                results,
                len(group_centers),
                0,
            )
            if rc != 0:
                raise RuntimeError(
                    f"floor unique_depth failed at tile {tile_start}: {rc}"
                )
            for group_index, result in enumerate(results):
                if not result.accepted:
                    continue
                global_index = tile_start + int(local_indices[group_index])
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
        "per_point_view_groups": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, action="append", required=True)
    parser.add_argument("--photo-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.selection) != len(args.photo_dir):
        parser.error("--selection and --photo-dir counts must match")

    full = load_module("pw_floor_full_helper", FULL_HELPER_PATH)
    reference = load_module("pw_floor_reference", REFERENCE_PATH)
    abi = load_module("pw_floor_abi_helper", ABI_HELPER_PATH)
    cases = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pw_full_floor_cabi_") as temp:
        library_path = Path(temp) / "libplanesweep.dylib"
        compile_command = abi.compile_library(args.aether_root.resolve(), library_path)
        api = abi.load_api(library_path)
        for selection_arg, photo_arg in zip(args.selection, args.photo_dir):
            selection_path = selection_arg.resolve()
            selection = json.loads(selection_path.read_text())
            selected = selection["selection"]
            if not selected["decisive"] or not selection["verdict"].startswith("PASS_"):
                raise RuntimeError(f"floor selection is not passing: {selection_path}")
            winner = next(
                row
                for row in selection["candidates"]
                if row["proposal"]["surface_id"] == selected["winner_surface_id"]
            )
            stage = selected["stage"]
            config_raw = (
                selection["config"]["fine_top2"]
                if stage.startswith("fine_")
                else selection["config"]["coarse"]
            )
            if config_raw is None:
                raise RuntimeError(f"missing config for selected stage {stage}")
            config = full.config_from_stats(reference, config_raw)
            meta_path = ROOT / selection["inputs"]["frame_meta"]["path"]
            ledger_path = ROOT / selection["inputs"]["ledger"]["path"]
            frames = reference.load_frames(
                meta_path, ledger_path, photo_arg.resolve()
            )
            surface = winner["proposal"]
            expected_xyz, _, expected_evidence, expected_metrics = (
                reference.sweep_surface(
                    surface, surface, frames, config, offset_m=0.0
                )
            )
            actual_xyz, actual_evidence, resources = run_c_floor_scale(
                reference,
                full,
                abi,
                api,
                surface,
                frames,
                config,
            )
            comparison = full.compare_points(actual_xyz, expected_xyz)
            selected_count_exact = (
                comparison["actual"]
                == comparison["expected"]
                == int(selected["accepted"])
                == int(expected_metrics["accepted"])
            )
            cases.append(
                {
                    "capture": capture_name(selection_path),
                    "selection_path": str(selection_path),
                    "selection_sha256": sha256(selection_path),
                    "photo_dir": str(photo_arg.resolve()),
                    "frame_count": len(frames),
                    "stage": stage,
                    "surface_id": surface["surface_id"],
                    "grid_candidates": int(expected_metrics["grid_candidates"]),
                    "python_oracle_accepted": int(len(expected_xyz)),
                    "c_abi_accepted": int(len(actual_xyz)),
                    "exact_point_set": comparison,
                    "selected_count_exact": selected_count_exact,
                    "python_evidence_count": int(len(expected_evidence)),
                    "c_abi_evidence_count": int(len(actual_evidence)),
                    "c_abi_evidence": actual_evidence,
                    "resources": resources,
                }
            )

    all_exact = all(
        case["exact_point_set"]["exact"] and case["selected_count_exact"]
        for case in cases
    )
    source_path = (
        args.aether_root.resolve()
        / "aether_cpp/src/pipeline/aether_structural_planesweep_c.cpp"
    )
    result = {
        "schema": "pocketworld_selected_floor_product_c_abi_parity_v1",
        "decision": (
            "PASS_SELECTED_FLOOR_PRODUCT_C_ABI_EXACT_PARITY"
            if all_exact
            else "FAIL_SELECTED_FLOOR_PRODUCT_C_ABI_PARITY"
        ),
        "compile_command": compile_command,
        "product_source": str(source_path),
        "product_source_sha256": sha256(source_path),
        "elapsed_s": time.perf_counter() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "no_matcher_lidar_or_scene_depth_consumed": True,
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "elapsed_s": result["elapsed_s"],
                "peak_rss_bytes": result["peak_rss_bytes"],
                "cases": [
                    {
                        "capture": case["capture"],
                        "stage": case["stage"],
                        "frames": case["frame_count"],
                        "grid_candidates": case["grid_candidates"],
                        "accepted": case["c_abi_accepted"],
                        "exact": case["exact_point_set"]["exact"],
                    }
                    for case in cases
                ],
            },
            indent=2,
        )
    )
    return 0 if all_exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
