#!/usr/bin/env python3
"""Verify the product tiled detector-free C ABI against the frozen fixture."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import time
from pathlib import Path

import numpy as np


class Options(ctypes.Structure):
    _fields_ = [
        ("image_width", ctypes.c_int32),
        ("image_height", ctypes.c_int32),
        ("max_tile_width", ctypes.c_int32),
        ("max_tile_height", ctypes.c_int32),
        ("depth_count", ctypes.c_int32),
        ("source_count", ctypes.c_int32),
        ("patch_n", ctypes.c_int32),
        ("minimum_views", ctypes.c_int32),
        ("exclusion_radius_samples", ctypes.c_int32),
        ("minimum_std_u8", ctypes.c_float),
        ("ncc_min", ctypes.c_float),
        ("unique_depth_margin", ctypes.c_float),
        ("inverse_depth_first", ctypes.c_float),
        ("inverse_depth_step", ctypes.c_float),
        ("reference_inverse_k_row_major_3x3", ctypes.c_float * 9),
    ]


class RefineOptions(ctypes.Structure):
    _fields_ = [
        ("fine_depth_count", ctypes.c_int32),
        ("coarse_step_span", ctypes.c_float),
        ("uniqueness_absolute_m", ctypes.c_float),
        ("uniqueness_relative", ctypes.c_float),
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pointer(array: np.ndarray, ctype):
    assert array.flags.c_contiguous
    return array.ctypes.data_as(ctypes.POINTER(ctype))


def load_api(path: Path):
    api = ctypes.CDLL(str(path))
    api.aether_detector_free_options_default.argtypes = [ctypes.POINTER(Options)]
    api.aether_detector_free_session_create.argtypes = [
        ctypes.POINTER(Options),
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.aether_detector_free_session_create.restype = ctypes.c_int32
    api.aether_detector_free_session_set_view_aggregation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
    ]
    api.aether_detector_free_session_set_view_aggregation.restype = ctypes.c_int32
    api.aether_detector_free_session_run_tile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
    ]
    api.aether_detector_free_session_run_tile.restype = ctypes.c_int32
    api.aether_detector_free_session_run_interpolated_tile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
    ]
    api.aether_detector_free_session_run_interpolated_tile.restype = ctypes.c_int32
    api.aether_detector_free_session_run_diagnostic_tile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
    ]
    api.aether_detector_free_session_run_diagnostic_tile.restype = ctypes.c_int32
    api.aether_detector_free_refine_options_default.argtypes = [
        ctypes.POINTER(RefineOptions)
    ]
    api.aether_detector_free_session_run_refined_tile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(RefineOptions),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
    ]
    api.aether_detector_free_session_run_refined_tile.restype = ctypes.c_int32
    api.aether_detector_free_session_free.argtypes = [ctypes.c_void_p]
    return api


def run_tile(api, session, x: int, y: int, width: int, height: int):
    count = width * height
    best_index = np.empty(count, dtype=np.uint16)
    best_score = np.empty(count, dtype=np.float32)
    second_score = np.empty(count, dtype=np.float32)
    views = np.empty(count, dtype=np.uint8)
    accepted = np.empty(count, dtype=np.uint8)
    started = time.perf_counter()
    rc = api.aether_detector_free_session_run_tile(
        session,
        x,
        y,
        width,
        height,
        pointer(best_index, ctypes.c_uint16),
        pointer(best_score, ctypes.c_float),
        pointer(second_score, ctypes.c_float),
        pointer(views, ctypes.c_uint8),
        pointer(accepted, ctypes.c_uint8),
        count,
    )
    if rc != 0:
        raise RuntimeError(f"run_tile({x},{y},{width},{height}) failed: {rc}")
    return (
        best_index.reshape(height, width),
        best_score.reshape(height, width),
        second_score.reshape(height, width),
        views.reshape(height, width),
        accepted.reshape(height, width),
        (time.perf_counter() - started) * 1000.0,
    )


def run_interpolated_tile(api, session, x: int, y: int, width: int, height: int):
    count = width * height
    best_index = np.empty(count, dtype=np.uint16)
    depth_m = np.empty(count, dtype=np.float32)
    peak_min_neighbor_drop = np.empty(count, dtype=np.float32)
    best_score = np.empty(count, dtype=np.float32)
    second_score = np.empty(count, dtype=np.float32)
    views = np.empty(count, dtype=np.uint8)
    accepted = np.empty(count, dtype=np.uint8)
    started = time.perf_counter()
    rc = api.aether_detector_free_session_run_interpolated_tile(
        session,
        x,
        y,
        width,
        height,
        pointer(best_index, ctypes.c_uint16),
        pointer(depth_m, ctypes.c_float),
        pointer(peak_min_neighbor_drop, ctypes.c_float),
        pointer(best_score, ctypes.c_float),
        pointer(second_score, ctypes.c_float),
        pointer(views, ctypes.c_uint8),
        pointer(accepted, ctypes.c_uint8),
        count,
    )
    if rc != 0:
        raise RuntimeError(
            f"run_interpolated_tile({x},{y},{width},{height}) failed: {rc}"
        )
    return (
        best_index.reshape(height, width),
        depth_m.reshape(height, width),
        peak_min_neighbor_drop.reshape(height, width),
        best_score.reshape(height, width),
        second_score.reshape(height, width),
        views.reshape(height, width),
        accepted.reshape(height, width),
        (time.perf_counter() - started) * 1000.0,
    )


def run_diagnostic_tile(api, session, x: int, y: int, width: int, height: int):
    count = width * height
    best_index = np.empty(count, dtype=np.uint16)
    all_view_dissent = np.empty(count, dtype=np.float32)
    best_score = np.empty(count, dtype=np.float32)
    second_score = np.empty(count, dtype=np.float32)
    views = np.empty(count, dtype=np.uint8)
    accepted = np.empty(count, dtype=np.uint8)
    started = time.perf_counter()
    rc = api.aether_detector_free_session_run_diagnostic_tile(
        session,
        x,
        y,
        width,
        height,
        pointer(best_index, ctypes.c_uint16),
        pointer(all_view_dissent, ctypes.c_float),
        pointer(best_score, ctypes.c_float),
        pointer(second_score, ctypes.c_float),
        pointer(views, ctypes.c_uint8),
        pointer(accepted, ctypes.c_uint8),
        count,
    )
    if rc != 0:
        raise RuntimeError(
            f"run_diagnostic_tile({x},{y},{width},{height}) failed: {rc}"
        )
    return (
        best_index.reshape(height, width),
        best_score.reshape(height, width),
        second_score.reshape(height, width),
        views.reshape(height, width),
        accepted.reshape(height, width),
        (time.perf_counter() - started) * 1000.0,
        all_view_dissent.reshape(height, width),
    )


def run_refined_tile(
    api,
    session,
    x: int,
    y: int,
    width: int,
    height: int,
    coarse_best_index: np.ndarray,
    coarse_accepted: np.ndarray,
    fine_depth_count: int = 17,
    coarse_step_span: float = 1.0,
):
    count = width * height
    coarse_best_index = np.ascontiguousarray(coarse_best_index, dtype=np.uint16)
    coarse_accepted = np.ascontiguousarray(coarse_accepted, dtype=np.uint8)
    depth_m = np.empty(count, dtype=np.float32)
    best_score = np.empty(count, dtype=np.float32)
    second_score = np.empty(count, dtype=np.float32)
    views = np.empty(count, dtype=np.uint8)
    accepted = np.empty(count, dtype=np.uint8)
    options = RefineOptions()
    api.aether_detector_free_refine_options_default(ctypes.byref(options))
    options.fine_depth_count = fine_depth_count
    options.coarse_step_span = coarse_step_span
    started = time.perf_counter()
    rc = api.aether_detector_free_session_run_refined_tile(
        session,
        x,
        y,
        width,
        height,
        pointer(coarse_best_index, ctypes.c_uint16),
        pointer(coarse_accepted, ctypes.c_uint8),
        ctypes.byref(options),
        pointer(depth_m, ctypes.c_float),
        pointer(best_score, ctypes.c_float),
        pointer(second_score, ctypes.c_float),
        pointer(views, ctypes.c_uint8),
        pointer(accepted, ctypes.c_uint8),
        count,
    )
    if rc != 0:
        raise RuntimeError(f"run_refined_tile({x},{y},{width},{height}) failed: {rc}")
    return (
        depth_m.reshape(height, width),
        best_score.reshape(height, width),
        second_score.reshape(height, width),
        views.reshape(height, width),
        accepted.reshape(height, width),
        (time.perf_counter() - started) * 1000.0,
    )


def parity(expected, actual):
    expected_index, expected_best, expected_second, expected_views, expected_accepted = expected
    actual_index, actual_best, actual_second, actual_views, actual_accepted = actual
    valid = (expected_best > -1.5) & (actual_best > -1.5)
    best_abs = np.abs(expected_best[valid] - actual_best[valid])
    second_abs = np.abs(expected_second[valid] - actual_second[valid])
    accepted_both = (expected_accepted != 0) & (actual_accepted != 0)
    return {
        "valid_mismatch": int(np.count_nonzero((expected_best > -1.5) != (actual_best > -1.5))),
        "accepted_mismatch": int(np.count_nonzero(expected_accepted != actual_accepted)),
        "accepted_depth_index_mismatch": int(
            np.count_nonzero(expected_index[accepted_both] != actual_index[accepted_both])
        ),
        "views_mismatch": int(np.count_nonzero(expected_views[valid] != actual_views[valid])),
        "accepted_actual": int(np.count_nonzero(actual_accepted)),
        "best_score_mean_abs": float(best_abs.mean()) if best_abs.size else 0.0,
        "best_score_max_abs": float(best_abs.max()) if best_abs.size else 0.0,
        "second_score_mean_abs": float(second_abs.mean()) if second_abs.size else 0.0,
        "second_score_max_abs": float(second_abs.max()) if second_abs.size else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    experiment = args.experiment.resolve()
    resources = experiment / "ios_bench/Resources"
    manifest_path = resources / "fixture_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    contract = manifest["contract"]
    geometry = manifest["geometry"]
    width = int(contract["width"])
    height = int(contract["height"])
    gray = np.fromfile(resources / "gray_frames.f32", dtype="<f4")
    projections = np.fromfile(resources / "source_projections.f32", dtype="<f4")
    expected = (
        np.fromfile(resources / "expected_best_index.u16", dtype="<u2").reshape(height, width),
        np.fromfile(resources / "expected_best_score.f32", dtype="<f4").reshape(height, width),
        np.fromfile(resources / "expected_second_score.f32", dtype="<f4").reshape(height, width),
        np.fromfile(resources / "expected_views.u8", dtype=np.uint8).reshape(height, width),
        np.fromfile(resources / "expected_accepted.u8", dtype=np.uint8).reshape(height, width),
    )

    api = load_api(args.library.resolve())
    options = Options()
    api.aether_detector_free_options_default(ctypes.byref(options))
    options.image_width = width
    options.image_height = height
    options.max_tile_width = width
    options.max_tile_height = height
    options.depth_count = int(contract["depth_samples"])
    options.source_count = int(contract["source_count"])
    options.patch_n = int(contract["patch_n"])
    options.minimum_views = int(contract["min_views"])
    options.exclusion_radius_samples = int(contract["peak_exclusion_radius_samples"])
    options.minimum_std_u8 = float(contract["min_std_u8"])
    options.ncc_min = float(contract["ncc_min"])
    options.unique_depth_margin = float(contract["depth_margin"])
    options.inverse_depth_first = float(geometry["inverse_depth_first"])
    options.inverse_depth_step = float(geometry["inverse_depth_step"])
    for index, value in enumerate(geometry["reference_inverse_k_row_major_f32"]):
        options.reference_inverse_k_row_major_3x3[index] = value

    session = ctypes.c_void_p()
    rc = api.aether_detector_free_session_create(
        ctypes.byref(options),
        pointer(gray, ctypes.c_float),
        gray.size,
        pointer(projections, ctypes.c_float),
        projections.size,
        ctypes.byref(session),
    )
    if rc != 0:
        raise RuntimeError(f"session_create failed: {rc}")
    try:
        full = run_tile(api, session, 0, 0, width, height)
        tiled_arrays = [np.empty((height, width), dtype=array.dtype) for array in full[:5]]
        tile_times = []
        tile_width, tile_height = 32, 24
        for y in range(0, height, tile_height):
            for x in range(0, width, tile_width):
                current_width = min(tile_width, width - x)
                current_height = min(tile_height, height - y)
                tile = run_tile(
                    api, session, x, y, current_width, current_height
                )
                for target, source in zip(tiled_arrays, tile[:5]):
                    target[y : y + current_height, x : x + current_width] = source
                tile_times.append(tile[5])
    finally:
        api.aether_detector_free_session_free(session)

    metrics = parity(expected, full[:5])
    thresholds = manifest["registered_thresholds"]
    full_pass = (
        metrics["valid_mismatch"] <= thresholds["valid_mismatch_max"]
        and metrics["accepted_mismatch"] <= thresholds["accepted_mismatch_max"]
        and metrics["accepted_depth_index_mismatch"]
        <= thresholds["accepted_best_index_mismatch_max"]
        and metrics["views_mismatch"] <= thresholds["views_mismatch_max"]
        and metrics["best_score_mean_abs"] <= thresholds["score_mean_abs_max"]
        and metrics["best_score_max_abs"] <= thresholds["score_max_abs_max"]
        and metrics["second_score_mean_abs"] <= thresholds["score_mean_abs_max"]
        and metrics["second_score_max_abs"] <= thresholds["score_max_abs_max"]
    )
    tiled_exact = all(
        np.array_equal(full_array, tiled_array)
        for full_array, tiled_array in zip(full[:5], tiled_arrays)
    )
    decision_pass = full_pass and tiled_exact
    result = {
        "schema": "pocketworld_detector_free_product_c_abi_v1",
        "decision": (
            "PASS_PRODUCT_C_ABI_FROZEN_PARITY_AND_TILED_IDENTITY"
            if decision_pass
            else "FAIL_PRODUCT_C_ABI_PARITY_OR_TILED_IDENTITY"
        ),
        "library": str(args.library.resolve()),
        "fixture_manifest": str(manifest_path),
        "fixture_manifest_sha256": sha256(manifest_path),
        "metrics": metrics,
        "full_tile_wall_ms": full[5],
        "tiled_32x24_total_wall_ms": sum(tile_times),
        "tiled_32x24_max_wall_ms": max(tile_times),
        "tile_count": len(tile_times),
        "full_vs_tiled_arrays_bit_exact": tiled_exact,
        "original_sparse_points_removed": 0,
        "rejected_pixels_gain_product_identity": 0,
        "learned_model_matcher_lidar_scene_depth_consumed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if decision_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
