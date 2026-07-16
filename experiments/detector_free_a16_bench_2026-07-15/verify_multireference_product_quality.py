#!/usr/bin/env python3
"""Evaluate the product detector-free C ABI with independent reciprocal births.

The shipped sparse cloud is immutable in this experiment.  Every reported D
point is an additive candidate, and rejected candidates never acquire a point
identity.  The C++ reciprocal gate is recomputed independently in Python from
the same discrete depth maps before a result can pass.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import math
import resource
import sys
import time
from pathlib import Path

import numpy as np


EXPERIMENT = Path(__file__).resolve().parent
ROOT = EXPERIMENT.parents[1]
DEPTH_PATH = ROOT / (
    "experiments/detector_free_classical_depth_sweep_2026-07-14/"
    "depth_sweep_probe.py"
)
GEOMETRY_PATH = ROOT / (
    "experiments/floor_plane_sweep_densifier_2026-07-13/"
    "fr_planesweep_wall_ceiling.py"
)
PRODUCT_VERIFY_PATH = EXPERIMENT / "verify_product_c_abi.py"

CAPTURE_SPECS = {
    "cap40": {
        "meta": ROOT
        / "experiments/cross_platform_planesweep_core_2026-07-15/runs/"
        "cap40_bed_scene_20260716/frame_meta.json",
        "ledger": ROOT
        / "data/pocketworld_captures/cap40/device_2026-07-16/"
        "sfm_fed_frames.jsonl",
        "photos": ROOT
        / "data/pocketworld_captures/cap40/device_2026-07-16/photos_highres",
        "sparse": ROOT
        / "data/pocketworld_captures/cap40/device_2026-07-16/"
        "sfm_sparse_metric.npz",
        "structural": ROOT
        / "experiments/cross_platform_planesweep_core_2026-07-15/runs/"
        "cap40_bed_scene_20260716/wall_owner_strict_adjudication_v1.json",
    },
    "cap41": {
        "meta": ROOT
        / "experiments/cross_platform_planesweep_core_2026-07-15/runs/"
        "cap41_bed_scene_20260716/frame_meta.json",
        "ledger": ROOT
        / "data/pocketworld_captures/cap41/device_2026-07-16/"
        "sfm_fed_frames.jsonl",
        "photos": ROOT
        / "data/pocketworld_captures/cap41/device_2026-07-16/photos_highres",
        "sparse": ROOT
        / "data/pocketworld_captures/cap41/device_2026-07-16/"
        "sfm_sparse_metric.npz",
        "structural": ROOT
        / "experiments/cross_platform_planesweep_core_2026-07-15/runs/"
        "cap41_bed_scene_20260716/wall_owner_strict_adjudication_v1.json",
    },
    "cap51": {
        "meta": ROOT
        / "experiments/floor_plane_sweep_densifier_2026-07-13/runs/"
        "cap51_pure_a_wall_holdout_20260715/frame_meta_cap51_available81.json",
        "ledger": ROOT
        / "data/pocketworld_captures/cap51/private_manifests/"
        "sfm_fed_frames.jsonl",
        "photos": ROOT
        / "data/pocketworld_captures/cap51/photos_highres_device_2026-07-16",
        "sparse": ROOT
        / "data/pocketworld_captures/cap51/fresh_device_pull_2026-07-14T085404+0800/"
        "retry/sfm_sparse.ply",
        "structural": ROOT
        / "experiments/cross_platform_planesweep_core_2026-07-15/runs/"
        "cap51_wall_owner_incumbent_selection_v3.json",
    },
}


class ReciprocalOptions(ctypes.Structure):
    _fields_ = [
        ("minimum_reciprocal_views", ctypes.c_int32),
        ("absolute_depth_tolerance_m", ctypes.c_float),
        ("relative_depth_tolerance", ctypes.c_float),
        ("minimum_parallax_deg", ctypes.c_float),
    ]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pointer(array: np.ndarray, ctype):
    if not array.flags.c_contiguous:
        raise ValueError("C ABI array is not contiguous")
    return array.ctypes.data_as(ctypes.POINTER(ctype))


def reconstruct_index_depths_like_c(
    best_index: np.ndarray,
    inverse_depth_first: float,
    inverse_depth_step: float,
) -> np.ndarray:
    """Reconstruct index-ABI depths with the exact C operand precision.

    The ABI receives ``inverse_depth_first`` and ``inverse_depth_step`` as
    floats, then promotes each operand to double before multiplying by the
    uint16 index and taking the reciprocal.  Keeping this result in float64 is
    intentional: rounding it to the product's float32 diagnostic depth map
    before the independent gate can change a tolerance-boundary decision.
    """
    first = float(np.float32(inverse_depth_first))
    step = float(np.float32(inverse_depth_step))
    indices = np.asarray(best_index, dtype=np.uint16).astype(
        np.float64, copy=False
    )
    return 1.0 / (first + indices * step)


def load_api(product_verify, path: Path):
    api = product_verify.load_api(path)
    api.aether_detector_free_reciprocal_options_default.argtypes = [
        ctypes.POINTER(ReciprocalOptions)
    ]
    api.aether_detector_free_filter_reciprocal_births.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ReciprocalOptions),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
    ]
    api.aether_detector_free_filter_reciprocal_births.restype = ctypes.c_int32
    api.aether_detector_free_filter_reciprocal_depth_births.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ReciprocalOptions),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
    ]
    api.aether_detector_free_filter_reciprocal_depth_births.restype = ctypes.c_int32
    return api


def projection(depth, reference, source, width: int, height: int) -> np.ndarray:
    source_k = depth.scaled_intrinsics(source, width, height)
    rotation = source.R @ reference.R.T
    translation = source.t - rotation @ reference.t
    return source_k @ np.column_stack([rotation, translation])


def run_session(
    api,
    product_verify,
    depth,
    reference,
    sources,
    gray_cache: dict[int, np.ndarray],
    reference_index: int,
    source_indices: list[int],
    width: int,
    height: int,
    depth_count: int,
    inverse_depth_first: float,
    inverse_depth_step: float,
    refine: bool,
    interpolate: bool,
    fine_depth_count: int,
    coarse_step_span: float,
    view_aggregation: int,
):
    gray = np.stack(
        [gray_cache[reference_index], *[gray_cache[index] for index in source_indices]]
    ).astype(np.float32, copy=False)
    projections = np.stack(
        [projection(depth, reference, source, width, height) for source in sources]
    ).astype(np.float32)

    options = product_verify.Options()
    api.aether_detector_free_options_default(ctypes.byref(options))
    options.image_width = width
    options.image_height = height
    options.max_tile_width = width
    options.max_tile_height = height
    options.depth_count = depth_count
    options.source_count = len(sources)
    options.patch_n = 5
    options.minimum_views = 4
    options.exclusion_radius_samples = 2
    options.minimum_std_u8 = 6.0
    options.ncc_min = 0.75
    options.unique_depth_margin = 0.03
    options.inverse_depth_first = inverse_depth_first
    options.inverse_depth_step = inverse_depth_step
    inverse_k = np.linalg.inv(
        depth.scaled_intrinsics(reference, width, height)
    ).astype(np.float32)
    for index, value in enumerate(inverse_k.ravel()):
        options.reference_inverse_k_row_major_3x3[index] = value

    flattened_gray = np.ascontiguousarray(gray.ravel(), dtype=np.float32)
    flattened_projection = np.ascontiguousarray(projections.ravel(), dtype=np.float32)
    session = ctypes.c_void_p()
    started = time.perf_counter()
    rc = api.aether_detector_free_session_create(
        ctypes.byref(options),
        pointer(flattened_gray, ctypes.c_float),
        flattened_gray.size,
        pointer(flattened_projection, ctypes.c_float),
        flattened_projection.size,
        ctypes.byref(session),
    )
    if rc != 0:
        raise RuntimeError(f"session_create failed for frame {reference_index}: {rc}")
    try:
        rc = api.aether_detector_free_session_set_view_aggregation(
            session, view_aggregation
        )
        if rc != 0:
            raise RuntimeError(
                f"set_view_aggregation({view_aggregation}) failed for "
                f"frame {reference_index}: {rc}"
            )
        diagnostic = (
            product_verify.run_diagnostic_tile(
                api, session, 0, 0, width, height
            )
            if view_aggregation == 3
            else None
        )
        interpolated = (
            product_verify.run_interpolated_tile(
                api, session, 0, 0, width, height
            )
            if interpolate and diagnostic is None
            else None
        )
        coarse = (
            diagnostic[:6]
            if diagnostic is not None
            else
            (
                interpolated[0],
                interpolated[3],
                interpolated[4],
                interpolated[5],
                interpolated[6],
                interpolated[7],
            )
            if interpolated is not None
            else product_verify.run_tile(api, session, 0, 0, width, height)
        )
        refined = (
            product_verify.run_refined_tile(
                api,
                session,
                0,
                0,
                width,
                height,
                coarse[0],
                coarse[4],
                fine_depth_count,
                coarse_step_span,
            )
            if refine
            else None
        )
    finally:
        api.aether_detector_free_session_free(session)
    if refined is None:
        depth_m = (
            interpolated[1]
            if interpolated is not None
            else 1.0
            / (
                float(np.float32(inverse_depth_first))
                + coarse[0].astype(np.float64)
                * float(np.float32(inverse_depth_step))
            )
        )
        best_score = coarse[1]
        second_score = coarse[2]
        views = coarse[3]
        accepted = coarse[4]
        refine_ms = 0.0
    else:
        depth_m = refined[0]
        best_score = refined[1]
        second_score = refined[2]
        views = refined[3]
        accepted = refined[4]
        refine_ms = refined[5]
    return {
        "best_index": coarse[0],
        "depth_m": np.asarray(depth_m, dtype=np.float32),
        "best_score": best_score,
        "second_score": second_score,
        "views": views,
        "accepted": accepted,
        "coarse_accepted": coarse[4],
        "coarse_best_score": coarse[1],
        "coarse_second_score": coarse[2],
        "coarse_views": coarse[3],
        "coarse_kernel_ms": coarse[5],
        "refine_kernel_ms": refine_ms,
        "kernel_ms": coarse[5] + refine_ms,
        "session_and_kernel_ms": (time.perf_counter() - started) * 1000.0,
        "inverse_k": inverse_k,
        "source_indices": source_indices,
        "projections": projections,
        "interpolation_peak_min_neighbor_drop": (
            interpolated[2]
            if interpolated is not None
            else np.zeros((height, width), dtype=np.float32)
        ),
        "all_view_dissent": (
            diagnostic[6]
            if diagnostic is not None
            else np.zeros((height, width), dtype=np.float32)
        ),
    }


def independent_source_indices(depth, frames, reference_index: int, excluded: set[int]):
    """Return up to seven supports, with at least four, excluding the primary."""
    upper = min(len(frames) - 1, 12)
    maximum_independent = 0
    for requested in range(upper, 3, -1):
        try:
            candidates = depth.select_source_indices(
                frames, reference_index, requested
            )
        except ValueError:
            continue
        selected = [index for index in candidates if index not in excluded]
        maximum_independent = max(maximum_independent, len(selected))
        if len(selected) >= 4:
            return selected[:7]
    raise ValueError(
        f"only {maximum_independent} independent supports for frame "
        f"{reference_index}; need 4"
    )


def primary_source_indices(depth, frames, reference_index: int):
    for requested in range(7, 3, -1):
        try:
            return depth.select_source_indices(frames, reference_index, requested)
        except ValueError:
            continue
    raise ValueError(f"fewer than four overlap sources for frame {reference_index}")


def python_reciprocal_gate(
    primary,
    reciprocal_depths_m: np.ndarray,
    reciprocal_accepted: np.ndarray,
    projections: np.ndarray,
    centers: np.ndarray,
    minimum_views: int,
    absolute_tolerance_m: float,
    relative_tolerance: float,
    minimum_parallax_deg: float,
):
    height, width = primary["accepted"].shape
    consistent = np.zeros((height, width), dtype=np.uint8)
    eligible = np.zeros((height, width), dtype=np.uint8)
    accepted = primary["accepted"] != 0
    inverse_k = primary["inverse_k"].astype(np.float64)
    absolute_tolerance = float(np.float32(absolute_tolerance_m))
    relative_tolerance = float(np.float32(relative_tolerance))
    parallax_gate = float(np.float32(minimum_parallax_deg))
    for y, x in np.argwhere(accepted):
        point = inverse_k @ np.asarray([x, y, 1.0], dtype=np.float64)
        point *= float(primary["depth_m"][y, x])
        reference_norm = float(np.linalg.norm(point))
        if not reference_norm > 0.0:
            continue
        for view in range(reciprocal_depths_m.shape[0]):
            projection_matrix = projections[view].astype(np.float64)
            projected = projection_matrix[:, :3] @ point + projection_matrix[:, 3]
            predicted_depth = float(projected[2])
            if not predicted_depth > 0.05:
                continue
            reciprocal_x = int(np.rint(projected[0] / predicted_depth))
            reciprocal_y = int(np.rint(projected[1] / predicted_depth))
            if not (0 <= reciprocal_x < width and 0 <= reciprocal_y < height):
                continue
            if reciprocal_accepted[view, reciprocal_y, reciprocal_x] == 0:
                continue
            source_ray = point - centers[view].astype(np.float64)
            source_norm = float(np.linalg.norm(source_ray))
            if not source_norm > 0.0:
                continue
            cosine = float(np.clip(np.dot(point, source_ray) / (reference_norm * source_norm), -1.0, 1.0))
            parallax = math.degrees(math.acos(cosine))
            if parallax < parallax_gate:
                continue
            eligible[y, x] += 1
            reciprocal_depth = float(
                reciprocal_depths_m[view, reciprocal_y, reciprocal_x]
            )
            tolerance = max(absolute_tolerance, relative_tolerance * predicted_depth)
            if abs(reciprocal_depth - predicted_depth) <= tolerance:
                consistent[y, x] += 1
    birth = (consistent >= minimum_views).astype(np.uint8)
    conflict = accepted & (eligible >= minimum_views) & (consistent < minimum_views)
    return consistent, birth, eligible, conflict


def sparse_zbuffer(depth, frame, sparse_xyz: np.ndarray, width: int, height: int):
    k = depth.scaled_intrinsics(frame, width, height)
    camera = sparse_xyz @ frame.R.T + frame.t
    z = camera[:, 2]
    uvw = camera @ k.T
    uv = uvw[:, :2] / np.where(z[:, None] > 1e-12, z[:, None], 1.0)
    x = np.rint(uv[:, 0]).astype(np.int32)
    y = np.rint(uv[:, 1]).astype(np.int32)
    inside = (z > 0.05) & (x >= 0) & (x < width) & (y >= 0) & (y < height)
    result = np.full((height, width), np.inf, dtype=np.float64)
    np.minimum.at(result, (y[inside], x[inside]), z[inside])
    return result


def error_summary(mask: np.ndarray, depth_map: np.ndarray, sparse_depth: np.ndarray):
    comparable = mask & np.isfinite(sparse_depth)
    values = np.abs(depth_map[comparable] - sparse_depth[comparable])
    if not values.size:
        return {"count": 0}
    return {
        "count": int(values.size),
        "median_m": float(np.median(values)),
        "p90_m": float(np.percentile(values, 90)),
        "p95_m": float(np.percentile(values, 95)),
        "max_m": float(np.max(values)),
        "within_0_05_m": float(np.mean(values <= 0.05)),
        "within_0_10_m": float(np.mean(values <= 0.10)),
        "within_0_20_m": float(np.mean(values <= 0.20)),
    }


def non_regression(before: dict, after: dict) -> bool:
    if after.get("count", 0) < 10:
        return False
    epsilon = 1e-9
    return (
        after["median_m"] <= before["median_m"] + epsilon
        and after["p90_m"] <= before["p90_m"] + epsilon
        and after["p95_m"] <= before["p95_m"] + epsilon
        and after["max_m"] <= before["max_m"] + epsilon
        and after["within_0_05_m"] + epsilon >= before["within_0_05_m"]
        and after["within_0_10_m"] + epsilon >= before["within_0_10_m"]
        and after["within_0_20_m"] + epsilon >= before["within_0_20_m"]
    )


def load_capture(depth, geometry, capture: str):
    if capture == "cap50":
        frames = geometry.load_frames(depth.META, depth.LEDGER, depth.PHOTOS)
        return frames, depth.SPARSE, depth.STRUCTURAL_PLANES
    if capture == "cap56":
        frames = depth.load_sidecar_frames(
            geometry, depth.CAP56_LEDGER, depth.CAP56_PHOTOS
        )
        return frames, depth.CAP56_SPARSE, None
    spec = CAPTURE_SPECS[capture]
    frames = geometry.load_frames(spec["meta"], spec["ledger"], spec["photos"])
    return frames, spec["sparse"], spec["structural"]


def read_sparse_xyz(depth, sparse_path: Path) -> np.ndarray:
    if sparse_path.suffix == ".npz":
        with np.load(sparse_path) as archive:
            xyz = np.asarray(archive["xyz"], dtype=np.float64)
        if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
            raise ValueError(f"invalid metric sparse XYZ: {sparse_path}")
        return xyz
    return depth.read_sparse_xyz(sparse_path)


def evaluate_reference(
    api,
    product_verify,
    depth,
    frames,
    sparse_xyz: np.ndarray,
    structural_planes_path: Path | None,
    capture: str,
    reference_index: int,
    output_dir: Path,
    width: int,
    height: int,
    depth_count: int,
    refine: bool,
    interpolate: bool,
    fine_depth_count: int,
    coarse_step_span: float,
    preserve_coarse_births: bool,
    minimum_reciprocal_views: int,
    absolute_depth_tolerance_m: float,
    relative_depth_tolerance: float,
    minimum_parallax_deg: float,
    view_aggregation: int,
):
    source_indices = primary_source_indices(depth, frames, reference_index)
    reciprocal_support_indices = {
        reciprocal_index: independent_source_indices(
            depth,
            frames,
            reciprocal_index,
            {reference_index, reciprocal_index},
        )
        for reciprocal_index in source_indices
    }
    if any(
        reference_index in supports
        for supports in reciprocal_support_indices.values()
    ):
        raise AssertionError("primary frame leaked into reciprocal support")
    needed_indices = {
        reference_index,
        *source_indices,
        *(index for supports in reciprocal_support_indices.values() for index in supports),
    }
    gray_cache = {
        index: depth.load_gray(frames[index], width, height)
        for index in sorted(needed_indices)
    }
    inverse_depths = np.linspace(1.0 / 4.3, 1.0 / 0.8, depth_count, dtype=np.float32)
    inverse_depth_first = float(inverse_depths[0])
    inverse_depth_step = float(inverse_depths[1] - inverse_depths[0])
    primary = run_session(
        api,
        product_verify,
        depth,
        frames[reference_index],
        [frames[index] for index in source_indices],
        gray_cache,
        reference_index,
        source_indices,
        width,
        height,
        depth_count,
        inverse_depth_first,
        inverse_depth_step,
        refine,
        interpolate,
        fine_depth_count,
        coarse_step_span,
        view_aggregation,
    )
    reciprocal_maps = [
        run_session(
            api,
            product_verify,
            depth,
            frames[reciprocal_index],
            [frames[index] for index in reciprocal_support_indices[reciprocal_index]],
            gray_cache,
            reciprocal_index,
            reciprocal_support_indices[reciprocal_index],
            width,
            height,
            depth_count,
            inverse_depth_first,
            inverse_depth_step,
            refine,
            interpolate,
            fine_depth_count,
            coarse_step_span,
            view_aggregation,
        )
        for reciprocal_index in source_indices
    ]
    maps = [primary, *reciprocal_maps]
    reciprocal_indices = np.ascontiguousarray(
        np.stack([entry["best_index"] for entry in maps[1:]]), dtype=np.uint16
    )
    reciprocal_depths_m = np.ascontiguousarray(
        np.stack([entry["depth_m"] for entry in maps[1:]]), dtype=np.float32
    )
    reciprocal_accepted = np.ascontiguousarray(
        np.stack([entry["accepted"] for entry in maps[1:]]), dtype=np.uint8
    )
    reciprocal_coarse_accepted = np.ascontiguousarray(
        np.stack([entry["coarse_accepted"] for entry in maps[1:]]),
        dtype=np.uint8,
    )
    primary_projections = np.ascontiguousarray(primary["projections"], dtype=np.float32)
    reference = frames[reference_index]
    centers = np.ascontiguousarray(
        np.stack(
            [reference.R @ frames[index].C + reference.t for index in source_indices]
        ),
        dtype=np.float32,
    )
    reciprocal_options = ReciprocalOptions()
    api.aether_detector_free_reciprocal_options_default(
        ctypes.byref(reciprocal_options)
    )
    reciprocal_options.minimum_reciprocal_views = minimum_reciprocal_views
    reciprocal_options.absolute_depth_tolerance_m = absolute_depth_tolerance_m
    reciprocal_options.relative_depth_tolerance = relative_depth_tolerance
    reciprocal_options.minimum_parallax_deg = minimum_parallax_deg
    c_consistent = np.empty((height, width), dtype=np.uint8)
    c_birth = np.empty((height, width), dtype=np.uint8)
    primary_index = np.ascontiguousarray(primary["best_index"], dtype=np.uint16)
    primary_accepted = np.ascontiguousarray(primary["accepted"], dtype=np.uint8)
    primary_coarse_accepted = np.ascontiguousarray(
        primary["coarse_accepted"], dtype=np.uint8
    )
    inverse_k = np.ascontiguousarray(primary["inverse_k"], dtype=np.float32)
    primary_depth_m = np.ascontiguousarray(primary["depth_m"], dtype=np.float32)
    oracle_primary_index_depth_m = reconstruct_index_depths_like_c(
        primary_index, inverse_depth_first, inverse_depth_step
    )
    oracle_reciprocal_index_depths_m = reconstruct_index_depths_like_c(
        reciprocal_indices, inverse_depth_first, inverse_depth_step
    )
    # These float32 arrays are product-output diagnostics.  The independent
    # index-ABI oracle below deliberately uses the unrounded float64 arrays.
    coarse_primary_depth_m = np.ascontiguousarray(
        oracle_primary_index_depth_m, dtype=np.float32
    )
    coarse_reciprocal_depths_m = np.ascontiguousarray(
        oracle_reciprocal_index_depths_m, dtype=np.float32
    )
    coarse_consistent = np.zeros((height, width), dtype=np.uint8)
    coarse_birth = np.zeros((height, width), dtype=np.uint8)
    coarse_eligible = np.zeros((height, width), dtype=np.uint8)
    coarse_conflict = np.zeros((height, width), dtype=bool)
    coarse_gate_exact = True
    metric_depth = refine or interpolate
    if metric_depth:
        rc = api.aether_detector_free_filter_reciprocal_depth_births(
            width,
            height,
            pointer(inverse_k, ctypes.c_float),
            pointer(primary_depth_m, ctypes.c_float),
            pointer(primary_accepted, ctypes.c_uint8),
            reciprocal_depths_m.shape[0],
            pointer(reciprocal_depths_m, ctypes.c_float),
            pointer(reciprocal_accepted, ctypes.c_uint8),
            pointer(primary_projections, ctypes.c_float),
            pointer(centers, ctypes.c_float),
            ctypes.byref(reciprocal_options),
            pointer(c_consistent, ctypes.c_uint8),
            pointer(c_birth, ctypes.c_uint8),
            width * height,
        )
    else:
        rc = api.aether_detector_free_filter_reciprocal_births(
            width,
            height,
            depth_count,
            inverse_depth_first,
            inverse_depth_step,
            pointer(inverse_k, ctypes.c_float),
            pointer(primary_index, ctypes.c_uint16),
            pointer(primary_accepted, ctypes.c_uint8),
            reciprocal_indices.shape[0],
            pointer(reciprocal_indices, ctypes.c_uint16),
            pointer(reciprocal_accepted, ctypes.c_uint8),
            pointer(primary_projections, ctypes.c_float),
            pointer(centers, ctypes.c_float),
            ctypes.byref(reciprocal_options),
            pointer(c_consistent, ctypes.c_uint8),
            pointer(c_birth, ctypes.c_uint8),
            width * height,
        )
    if rc != 0:
        raise RuntimeError(f"reciprocal birth gate failed: {rc}")

    if metric_depth:
        rc = api.aether_detector_free_filter_reciprocal_births(
            width,
            height,
            depth_count,
            inverse_depth_first,
            inverse_depth_step,
            pointer(inverse_k, ctypes.c_float),
            pointer(primary_index, ctypes.c_uint16),
            pointer(primary_coarse_accepted, ctypes.c_uint8),
            reciprocal_indices.shape[0],
            pointer(reciprocal_indices, ctypes.c_uint16),
            pointer(reciprocal_coarse_accepted, ctypes.c_uint8),
            pointer(primary_projections, ctypes.c_float),
            pointer(centers, ctypes.c_float),
            ctypes.byref(reciprocal_options),
            pointer(coarse_consistent, ctypes.c_uint8),
            pointer(coarse_birth, ctypes.c_uint8),
            width * height,
        )
        if rc != 0:
            raise RuntimeError(f"coarse reciprocal diagnostic failed: {rc}")

    oracle_primary = primary
    oracle_reciprocal_depths_m = reciprocal_depths_m
    if not metric_depth:
        oracle_primary = dict(primary)
        oracle_primary["depth_m"] = oracle_primary_index_depth_m
        oracle_reciprocal_depths_m = oracle_reciprocal_index_depths_m
    py_consistent, py_birth, eligible, conflict = python_reciprocal_gate(
        oracle_primary,
        oracle_reciprocal_depths_m,
        reciprocal_accepted,
        primary_projections,
        centers,
        minimum_reciprocal_views,
        absolute_depth_tolerance_m,
        relative_depth_tolerance,
        minimum_parallax_deg,
    )
    gate_exact = np.array_equal(c_consistent, py_consistent) and np.array_equal(
        c_birth, py_birth
    )
    if metric_depth:
        coarse_primary = dict(primary)
        coarse_primary["depth_m"] = oracle_primary_index_depth_m
        coarse_primary["accepted"] = np.ascontiguousarray(
            primary["coarse_accepted"], dtype=np.uint8
        )
        (
            coarse_py_consistent,
            coarse_py_birth,
            coarse_eligible,
            coarse_conflict,
        ) = python_reciprocal_gate(
            coarse_primary,
            oracle_reciprocal_index_depths_m,
            reciprocal_coarse_accepted,
            primary_projections,
            centers,
            minimum_reciprocal_views,
            absolute_depth_tolerance_m,
            relative_depth_tolerance,
            minimum_parallax_deg,
        )
        coarse_gate_exact = np.array_equal(
            coarse_consistent, coarse_py_consistent
        ) and np.array_equal(coarse_birth, coarse_py_birth)
        gate_exact = gate_exact and coarse_gate_exact
    raw_metric_depth_map = primary_depth_m.astype(np.float64)
    metric_birth_mask = c_birth != 0
    safe_interpolation_mask = np.zeros((height, width), dtype=bool)
    preserve_identity = interpolate or (refine and preserve_coarse_births)
    if interpolate:
        with np.errstate(divide="ignore", invalid="ignore"):
            interpolated_index = (
                (
                    1.0 / raw_metric_depth_map
                    - float(np.float32(inverse_depth_first))
                )
                / float(np.float32(inverse_depth_step))
            )
        interpolation_offset = interpolated_index - primary_index.astype(np.float64)
        safe_interpolation_mask = (
            (coarse_birth != 0)
            & metric_birth_mask
            & np.isfinite(interpolation_offset)
            & (np.abs(interpolation_offset) <= 0.30)
        )
        depth_map = np.where(
            safe_interpolation_mask,
            raw_metric_depth_map,
            coarse_primary_depth_m.astype(np.float64),
        )
        # Product identity remains exactly the proven 48-layer reciprocal set.
        # Interpolation may improve the coordinate of an existing birth, but it
        # can neither add nor remove a point.  A metric-depth reciprocal pass is
        # additionally required before the interpolated coordinate is used.
        birth_mask = coarse_birth != 0
        conflict = coarse_conflict
    elif refine and preserve_coarse_births:
        safe_interpolation_mask = (
            (coarse_birth != 0)
            & metric_birth_mask
            & np.isfinite(raw_metric_depth_map)
            & (raw_metric_depth_map > 0.0)
        )
        depth_map = np.where(
            safe_interpolation_mask,
            raw_metric_depth_map,
            coarse_primary_depth_m.astype(np.float64),
        )
        birth_mask = coarse_birth != 0
        conflict = coarse_conflict
    else:
        depth_map = raw_metric_depth_map
        birth_mask = metric_birth_mask
    sparse_depth = sparse_zbuffer(depth, reference, sparse_xyz, width, height)
    baseline_mask = (
        primary_coarse_accepted != 0
        if preserve_identity
        else primary_accepted != 0
    )
    final_mask = birth_mask.copy()
    floor_owned_rejected = 0
    below_floor_before = 0
    below_floor_after = 0
    interpolation_structural_fallbacks = 0
    floor_distance = np.empty((0, 0), dtype=np.float32)
    if structural_planes_path is not None:
        structural = json.loads(structural_planes_path.read_text())
        floor = structural["floor"]
        normal = np.asarray(floor["normal"], dtype=np.float64)
        normal /= np.linalg.norm(normal)
        plane_value = float(floor["plane_value_n_dot_x"])
        yy, xx = np.mgrid[0:height, 0:width]
        pixels = np.stack([xx, yy, np.ones_like(xx)], axis=-1)
        rays = pixels @ primary["inverse_k"].astype(np.float64).T
        if preserve_identity:
            raw_camera_points = rays * raw_metric_depth_map[..., None]
            raw_world = (raw_camera_points - reference.t) @ reference.R
            raw_floor_distance = raw_world @ normal - plane_value
            crosses_ownership = safe_interpolation_mask & (
                raw_floor_distance <= 0.08
            )
            interpolation_structural_fallbacks = int(
                np.count_nonzero(crosses_ownership)
            )
            safe_interpolation_mask &= ~crosses_ownership
            depth_map = np.where(
                safe_interpolation_mask,
                raw_metric_depth_map,
                coarse_primary_depth_m.astype(np.float64),
            )
        camera_points = rays * depth_map[..., None]
        world = (camera_points - reference.t) @ reference.R
        floor_distance = (world @ normal - plane_value).astype(np.float32)
        if preserve_identity:
            coarse_camera_points = (
                rays * coarse_primary_depth_m.astype(np.float64)[..., None]
            )
            coarse_world = (coarse_camera_points - reference.t) @ reference.R
            owned = coarse_world @ normal - plane_value <= 0.08
        else:
            owned = floor_distance <= 0.08
        floor_owned_rejected = int(np.count_nonzero(birth_mask & owned))
        below_floor_before = int(np.count_nonzero(birth_mask & (floor_distance < -0.015)))
        final_mask &= ~owned
        below_floor_after = int(np.count_nonzero(final_mask & (floor_distance < -0.015)))

    baseline_error = error_summary(baseline_mask, depth_map, sparse_depth)
    birth_error = error_summary(birth_mask, depth_map, sparse_depth)
    final_error = error_summary(final_mask, depth_map, sparse_depth)
    retained_depth_identity = bool(
        np.array_equal(depth_map[final_mask], depth_map[baseline_mask & final_mask])
    )
    conflict_born = int(np.count_nonzero(conflict & final_mask))
    reference_pass = bool(
        gate_exact
        and retained_depth_identity
        and np.count_nonzero(final_mask) > 0
        and conflict_born == 0
        and below_floor_after == 0
        and non_regression(baseline_error, final_error)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = output_dir / f"{capture}_ref{reference_index}_product_quality.npz"
    np.savez_compressed(
        npz_path,
        selected_frame_indices=np.asarray([reference_index, *source_indices], dtype=np.int32),
        best_index=primary_index,
        depth_m=primary_depth_m,
        product_depth_m=np.asarray(depth_map, dtype=np.float32),
        accepted=primary_accepted,
        best_score=np.asarray(primary["best_score"], dtype=np.float32),
        second_score=np.asarray(primary["second_score"], dtype=np.float32),
        supporting_views=np.asarray(primary["views"], dtype=np.uint32),
        coarse_depth_m=coarse_primary_depth_m,
        coarse_accepted=np.asarray(primary["coarse_accepted"], dtype=np.uint8),
        coarse_best_score=np.asarray(primary["coarse_best_score"], dtype=np.float32),
        coarse_second_score=np.asarray(
            primary["coarse_second_score"], dtype=np.float32
        ),
        coarse_supporting_views=np.asarray(primary["coarse_views"], dtype=np.uint32),
        interpolation_peak_min_neighbor_drop=np.asarray(
            primary["interpolation_peak_min_neighbor_drop"], dtype=np.float32
        ),
        all_view_dissent=np.asarray(
            primary["all_view_dissent"], dtype=np.float32
        ),
        coarse_reciprocal_consistent_views=coarse_consistent,
        coarse_reciprocal_birth=coarse_birth,
        coarse_reciprocal_eligible_views=coarse_eligible,
        reciprocal_consistent_views=c_consistent,
        reciprocal_eligible_views=eligible,
        reciprocal_birth=c_birth,
        safe_interpolation_birth=safe_interpolation_mask,
        final_birth=final_mask,
        floor_distance_m=floor_distance,
        sparse_depth_m=sparse_depth.astype(np.float32),
    )
    return {
        "reference_index": reference_index,
        "selected_frame_indices": [reference_index, *source_indices],
        "selected_frame_ids": [
            int(frames[index].frame_id) for index in [reference_index, *source_indices]
        ],
        "reciprocal_support_frame_indices": reciprocal_support_indices,
        "source_view_count": len(source_indices),
        "primary_frame_excluded_from_all_reciprocal_support": True,
        "baseline_births": int(np.count_nonzero(baseline_mask)),
        "coarse_primary_births": int(
            np.count_nonzero(primary["coarse_accepted"])
        ),
        "coarse_reciprocal_births": int(np.count_nonzero(coarse_birth)),
        "coarse_vs_refined_birth_intersection": int(
            np.count_nonzero((coarse_birth != 0) & metric_birth_mask)
        ),
        "coarse_only_births": int(
            np.count_nonzero((coarse_birth != 0) & ~metric_birth_mask)
        ),
        "refined_only_births": int(
            np.count_nonzero((coarse_birth == 0) & metric_birth_mask)
        ),
        "metric_depth_reciprocal_births": int(
            np.count_nonzero(metric_birth_mask)
        ),
        "safe_interpolated_births": int(
            np.count_nonzero(safe_interpolation_mask)
        ),
        "safe_metric_updated_births": int(
            np.count_nonzero(safe_interpolation_mask)
        ),
        "interpolation_structural_fallbacks": interpolation_structural_fallbacks,
        "reciprocal_births": int(np.count_nonzero(birth_mask)),
        "final_births": int(np.count_nonzero(final_mask)),
        "depth_conflict_candidates": int(np.count_nonzero(conflict)),
        "depth_conflict_candidates_born": conflict_born,
        "floor_owned_candidates_not_born": floor_owned_rejected,
        "below_floor_before_ownership": below_floor_before,
        "below_floor_after_ownership": below_floor_after,
        "c_vs_independent_python_gate_bit_exact": gate_exact,
        "coarse_c_vs_independent_python_gate_bit_exact": coarse_gate_exact,
        "retained_candidate_depths_bit_identical": retained_depth_identity,
        "sparse_points_removed": 0,
        "baseline_sparse_error": baseline_error,
        "reciprocal_sparse_error": birth_error,
        "final_sparse_error": final_error,
        "kernel_ms": [float(entry["kernel_ms"]) for entry in maps],
        "coarse_kernel_ms": [
            float(entry["coarse_kernel_ms"]) for entry in maps
        ],
        "refine_kernel_ms": [
            float(entry["refine_kernel_ms"]) for entry in maps
        ],
        "session_and_kernel_ms": [
            float(entry["session_and_kernel_ms"]) for entry in maps
        ],
        "npz": str(npz_path),
        "npz_sha256": sha256(npz_path),
        "pass": reference_pass,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument(
        "--capture",
        choices=("cap40", "cap41", "cap50", "cap51", "cap56"),
        required=True,
    )
    parser.add_argument("--reference-index", type=int, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=128)
    parser.add_argument("--height", type=int, default=72)
    parser.add_argument("--depth-count", type=int, default=48)
    parser.add_argument("--refine", action="store_true")
    parser.add_argument("--interpolate", action="store_true")
    parser.add_argument("--fine-depth-count", type=int, default=17)
    parser.add_argument("--coarse-step-span", type=float, default=1.0)
    parser.add_argument("--preserve-coarse-births", action="store_true")
    parser.add_argument("--minimum-reciprocal-views", type=int, default=4)
    parser.add_argument(
        "--skip-insufficient-support",
        action="store_true",
        help=(
            "record references with fewer than the required independent "
            "support views as explicit zero-birth no-ops instead of aborting "
            "the full-scene run"
        ),
    )
    parser.add_argument("--absolute-depth-tolerance-m", type=float, default=0.08)
    parser.add_argument("--relative-depth-tolerance", type=float, default=0.05)
    parser.add_argument("--minimum-parallax-deg", type=float, default=8.0)
    parser.add_argument(
        "--view-aggregation",
        choices=(
            "top_minimum",
            "trimmed_all",
            "mean_all",
            "top_minimum_with_dissent",
        ),
        default="top_minimum",
    )
    args = parser.parse_args()
    if args.refine and args.interpolate:
        parser.error("--refine and --interpolate are mutually exclusive")
    if args.preserve_coarse_births and not (args.refine or args.interpolate):
        parser.error("--preserve-coarse-births requires --refine or --interpolate")

    depth = load_module(DEPTH_PATH, "pw_product_quality_depth")
    geometry = load_module(GEOMETRY_PATH, "pw_product_quality_geometry")
    product_verify = load_module(PRODUCT_VERIFY_PATH, "pw_product_quality_cabi")
    library = args.library.resolve()
    api = load_api(product_verify, library)
    view_aggregation = {
        "top_minimum": 0,
        "trimmed_all": 1,
        "mean_all": 2,
        "top_minimum_with_dissent": 3,
    }[args.view_aggregation]
    frames, sparse_path, structural_planes_path = load_capture(
        depth, geometry, args.capture
    )
    sparse_xyz = read_sparse_xyz(depth, sparse_path)
    started = time.perf_counter()
    references = []
    skipped_references = []
    for reference_index in args.reference_index:
        try:
            reference = evaluate_reference(
                api,
                product_verify,
                depth,
                frames,
                sparse_xyz,
                structural_planes_path,
                args.capture,
                reference_index,
                args.output_dir,
                args.width,
                args.height,
                args.depth_count,
                args.refine,
                args.interpolate,
                args.fine_depth_count,
                args.coarse_step_span,
                args.preserve_coarse_births,
                args.minimum_reciprocal_views,
                args.absolute_depth_tolerance_m,
                args.relative_depth_tolerance,
                args.minimum_parallax_deg,
                view_aggregation,
            )
        except ValueError as error:
            message = str(error)
            if not (
                args.skip_insufficient_support
                and (
                    " independent supports for frame " in message
                    or message.startswith(
                        "fewer than four overlap sources for frame "
                    )
                )
            ):
                raise
            skipped_references.append(
                {
                    "reference_index": reference_index,
                    "births": 0,
                    "reason": message,
                }
            )
            continue
        references.append(reference)
    all_pass = bool(references) and all(
        reference["pass"] for reference in references
    )
    strict_benefit = sum(
        reference["depth_conflict_candidates"] for reference in references
    ) > 0
    decision_pass = all_pass and strict_benefit
    result = {
        "schema": "pocketworld_detector_free_multireference_product_quality_v2",
        "decision": (
            "PASS_ADDITIVE_RECIPROCAL_BIRTH_ZERO_REGRESSION"
            if decision_pass
            else "FAIL_RECIPROCAL_BIRTH_QUALITY_GATE"
        ),
        "capture": args.capture,
        "library": str(library),
        "library_sha256": sha256(library),
        "sparse_path": str(sparse_path),
        "sparse_sha256": sha256(sparse_path),
        "ordered_capture_bundle_sha256": depth.capture_bundle_sha256(frames),
        "requested_reference_count": len(args.reference_index),
        "evaluated_reference_count": len(references),
        "skipped_references": skipped_references,
        "config": {
            "width": args.width,
            "height": args.height,
            "depth_count": args.depth_count,
            "coarse_to_fine_refinement": args.refine,
            "single_pass_parabolic_interpolation": args.interpolate,
            "fine_depth_count": args.fine_depth_count if args.refine else 0,
            "coarse_step_span": args.coarse_step_span if args.refine else 0.0,
            "preserve_coarse_births": args.preserve_coarse_births,
            "depth_min_m": 0.8,
            "depth_max_m": 4.3,
            "source_views": "4_to_7_pose_overlap_views",
            "view_aggregation": args.view_aggregation,
            "minimum_views": 4,
            "minimum_reciprocal_views": args.minimum_reciprocal_views,
            "insufficient_support_behavior": (
                "explicit_zero_birth_noop"
                if args.skip_insufficient_support
                else "abort"
            ),
            "absolute_depth_tolerance_m": args.absolute_depth_tolerance_m,
            "relative_depth_tolerance": args.relative_depth_tolerance,
            "minimum_parallax_deg": args.minimum_parallax_deg,
            "floor_ownership_slab_m": 0.08 if structural_planes_path else 0.0,
            "learned_model_or_training_data_consumed": False,
            "third_party_matcher_output_consumed": False,
            "lidar_or_scene_depth_consumed": False,
        },
        "acceptance": {
            "all_c_gates_match_independent_python_bit_exact": True,
            "all_retained_depths_bit_identical": True,
            "all_original_sparse_points_removed": 0,
            "all_depth_conflict_candidates_born": 0,
            "all_below_floor_points_after_ownership": 0,
            "all_insufficient_support_references_birth_zero_points": True,
            "each_reference_sparse_median_p90_p95_non_regression": True,
            "each_reference_sparse_max_error_non_regression": True,
            "each_reference_sparse_within_5cm_10cm_20cm_non_regression": True,
            "minimum_comparable_final_pixels_per_reference": 10,
            "strict_benefit_requires_at_least_one_depth_conflict_rejected": True,
        },
        "references": references,
        "totals": {
            "baseline_births": sum(item["baseline_births"] for item in references),
            "reciprocal_births": sum(item["reciprocal_births"] for item in references),
            "final_births": sum(item["final_births"] for item in references),
            "depth_conflict_candidates": sum(
                item["depth_conflict_candidates"] for item in references
            ),
            "depth_conflict_candidates_born": sum(
                item["depth_conflict_candidates_born"] for item in references
            ),
            "floor_owned_candidates_not_born": sum(
                item["floor_owned_candidates_not_born"] for item in references
            ),
            "sparse_points_removed": 0,
        },
        "elapsed_s": time.perf_counter() - started,
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if decision_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
