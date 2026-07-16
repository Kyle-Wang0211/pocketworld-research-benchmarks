#!/usr/bin/env python3
"""Verify Dawn session geometry parity and evidence-clique RGB colorization."""

from __future__ import annotations

import argparse
import ctypes
import itertools
import json
import math
import time
from pathlib import Path

import numpy as np


class SessionOptions(ctypes.Structure):
    _fields_ = [
        ("point_count", ctypes.c_int32),
        ("candidate_count", ctypes.c_int32),
        ("hypotheses_per_candidate", ctypes.c_int32),
        ("patch_n", ctypes.c_int32),
        ("max_views", ctypes.c_int32),
        ("scale_count", ctypes.c_int32),
        ("basis_u_xyz", ctypes.c_float * 3),
        ("basis_v_xyz", ctypes.c_float * 3),
    ]


class BirthOptions(ctypes.Structure):
    _fields_ = [
        ("minimum_views", ctypes.c_int32),
        ("ncc_min", ctypes.c_float),
        ("minimum_parallax_deg", ctypes.c_float),
        ("unique_depth_margin", ctypes.c_float),
        ("post_min_ncc", ctypes.c_float),
        ("post_minimum_views", ctypes.c_int32),
        ("post_minimum_parallax_deg", ctypes.c_float),
    ]


class CandidateResult(ctypes.Structure):
    _fields_ = [
        ("accepted", ctypes.c_int32),
        ("supporting_views", ctypes.c_int32),
        ("median_ncc", ctypes.c_float),
        ("max_parallax_deg", ctypes.c_float),
        ("observed_depth_margin", ctypes.c_float),
    ]


def load_api(path: Path):
    api = ctypes.CDLL(str(path))
    float_ptr = ctypes.POINTER(ctypes.c_float)
    u8_ptr = ctypes.POINTER(ctypes.c_uint8)
    api.aether_planesweep_session_options_default.argtypes = [
        ctypes.POINTER(SessionOptions)
    ]
    api.aether_planesweep_birth_options_default.argtypes = [
        ctypes.POINTER(BirthOptions)
    ]
    api.aether_planesweep_session_create.argtypes = [
        ctypes.POINTER(SessionOptions),
        float_ptr,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.aether_planesweep_session_create.restype = ctypes.c_int32
    api.aether_planesweep_session_add_view.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_int32,
        ctypes.c_int32,
        float_ptr,
        float_ptr,
        ctypes.c_float,
        ctypes.c_float,
    ]
    api.aether_planesweep_session_add_view.restype = ctypes.c_int32
    finish_args = [
        ctypes.c_void_p,
        u8_ptr,
        ctypes.POINTER(BirthOptions),
        ctypes.c_int32,
        ctypes.POINTER(CandidateResult),
        ctypes.c_int32,
    ]
    api.aether_planesweep_session_finish.argtypes = finish_args
    api.aether_planesweep_session_finish.restype = ctypes.c_int32
    api.aether_planesweep_session_finish_rgb.argtypes = finish_args + [
        u8_ptr,
        ctypes.c_int32,
    ]
    api.aether_planesweep_session_finish_rgb.restype = ctypes.c_int32
    api.aether_planesweep_session_free.argtypes = [ctypes.c_void_p]
    return api


def pointer(array: np.ndarray, ctype):
    assert array.flags.c_contiguous
    return array.ctypes.data_as(ctypes.POINTER(ctype))


def birth_options(api, config: dict) -> BirthOptions:
    options = BirthOptions()
    api.aether_planesweep_birth_options_default(ctypes.byref(options))
    options.minimum_views = int(config["min_views"])
    options.ncc_min = float(config["ncc_min"])
    options.minimum_parallax_deg = float(config["min_parallax_deg"])
    options.unique_depth_margin = float(config["depth_ncc_margin"])
    options.post_min_ncc = float(config.get("post_min_ncc", 0.0))
    options.post_minimum_views = int(config.get("post_minimum_views", 0))
    options.post_minimum_parallax_deg = float(
        config.get("post_minimum_parallax_deg", 0.0)
    )
    return options


def exact_clique_views(
    patches: np.ndarray,
    valid: np.ndarray,
    mask: np.ndarray,
    point: int,
    minimum_views: int,
    ncc_min: float,
) -> list[int]:
    candidates = [
        view
        for view in range(patches.shape[0])
        if valid[view, point] and mask[point, view]
    ]
    pair_scores: dict[tuple[int, int], float] = {}
    for a, b in itertools.combinations(candidates, 2):
        pair_scores[(a, b)] = float(np.dot(patches[a, point], patches[b, point]))
    for size in range(len(candidates), minimum_views - 1, -1):
        best: tuple[int, ...] | None = None
        best_median = -math.inf
        for subset in itertools.combinations(candidates, size):
            values = [pair_scores[(a, b)] for a, b in itertools.combinations(subset, 2)]
            if any(value < ncc_min for value in values):
                continue
            score = float(np.median(values))
            if best is None or score > best_median:
                best = subset
                best_median = score
        if best is not None:
            return list(best)
    return []


def bilinear_rgb(frame: np.ndarray, projection: np.ndarray, xyz: np.ndarray):
    x, y, z = (np.float32(value) for value in xyz)
    q0 = np.float32(
        projection[0] * x
        + projection[1] * y
        + projection[2] * z
        + projection[3]
    )
    q1 = np.float32(
        projection[4] * x
        + projection[5] * y
        + projection[6] * z
        + projection[7]
    )
    q2 = np.float32(
        projection[8] * x
        + projection[9] * y
        + projection[10] * z
        + projection[11]
    )
    if not q2 > np.float32(0.05):
        raise RuntimeError("accepted point projected behind a source view")
    px = np.float32(q0 / q2)
    py = np.float32(q1 / q2)
    x0, y0 = math.floor(float(px)), math.floor(float(py))
    x1, y1 = x0 + 1, y0 + 1
    if x0 < 0 or y0 < 0 or x1 >= frame.shape[1] or y1 >= frame.shape[0]:
        raise RuntimeError("accepted point projected outside a source view")
    dx = np.float32(px - np.float32(x0))
    dy = np.float32(py - np.float32(y0))
    weights = (
        np.float32((np.float32(1) - dx) * (np.float32(1) - dy)),
        np.float32(dx * (np.float32(1) - dy)),
        np.float32((np.float32(1) - dx) * dy),
        np.float32(dx * dy),
    )
    corners = ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
    rgb = []
    for channel in range(3):
        value = np.float32(0)
        for weight, (column, row) in zip(weights, corners):
            value = np.float32(value + weight * np.float32(frame[row, column, channel]))
        rgb.append(float(value))
    return rgb


def result_tuple(result: CandidateResult):
    return (
        int(result.accepted),
        int(result.supporting_views),
        float(result.median_ncc),
        float(result.max_parallax_deg),
        float(result.observed_depth_margin),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat-sessions", type=int, default=1)
    args = parser.parse_args()
    if args.repeat_sessions <= 0:
        parser.error("--repeat-sessions must be positive")

    fixture = args.fixture.resolve()
    manifest = json.loads((fixture / "fixture_manifest.json").read_text())
    points = np.fromfile(fixture / "points.f32", dtype="<f4")
    point_count = int(manifest["point_count"])
    candidate_count = int(manifest["candidate_count"])
    hypotheses = int(manifest["hypothesis_count"])
    view_count = len(manifest["frames"])
    scale_count = len(manifest["scales"])
    sample_count = int(manifest["patch_sample_count"])
    patches = np.fromfile(
        fixture / "expected_normalized_patches.f32", dtype="<f4"
    ).reshape(scale_count, view_count, point_count, sample_count)
    valid = np.fromfile(fixture / "expected_valid.u8", dtype=np.uint8).reshape(
        scale_count, view_count, point_count
    )
    masks = np.zeros((scale_count, point_count, view_count), dtype=np.uint8)
    for scale, table in enumerate(
        manifest["candidate_resource_frame_indices_by_scale"]
    ):
        for point, frame_indices in enumerate(table):
            masks[scale, point, np.asarray(frame_indices, dtype=np.int64)] = 1
    frames = []
    for frame_meta in manifest["frames"]:
        frame = np.fromfile(fixture / frame_meta["resource"], dtype=np.uint8).reshape(
            int(frame_meta["height"]), int(frame_meta["width"]), 4
        )
        frames.append(np.ascontiguousarray(frame))

    api = load_api(args.library.resolve())
    options = SessionOptions()
    api.aether_planesweep_session_options_default(ctypes.byref(options))
    options.point_count = point_count
    options.candidate_count = candidate_count
    options.hypotheses_per_candidate = hypotheses
    options.patch_n = int(manifest["patch_n"])
    options.max_views = view_count
    options.scale_count = scale_count
    for axis in range(3):
        options.basis_u_xyz[axis] = float(manifest["basis_u_f32"][axis])
        options.basis_v_xyz[axis] = float(manifest["basis_v_f32"][axis])
    native_options = (BirthOptions * scale_count)(
        *(birth_options(api, config) for config in manifest["scales"])
    )

    flat_masks = np.ascontiguousarray(masks.reshape(-1))
    session_timings_ms = []
    reference_plain = None
    reference_colored = None
    reference_rgb = None
    for iteration in range(args.repeat_sessions):
        session = ctypes.c_void_p()
        started = time.perf_counter()
        rc = api.aether_planesweep_session_create(
            ctypes.byref(options), pointer(points, ctypes.c_float), ctypes.byref(session)
        )
        created = time.perf_counter()
        if rc != 0:
            raise RuntimeError(f"session_create failed: {rc}")
        try:
            for scale, scale_config in enumerate(manifest["scales"]):
                for view, (frame_meta, frame) in enumerate(
                    zip(manifest["frames"], frames)
                ):
                    projection = np.ascontiguousarray(
                        frame_meta["projection_row_major_f32"], dtype=np.float32
                    )
                    center = np.ascontiguousarray(
                        frame_meta["camera_center_f32"], dtype=np.float32
                    )
                    rc = api.aether_planesweep_session_add_view(
                        session,
                        scale,
                        view,
                        pointer(frame.view(np.uint32).reshape(-1), ctypes.c_uint32),
                        frame.shape[1],
                        frame.shape[0],
                        pointer(projection, ctypes.c_float),
                        pointer(center, ctypes.c_float),
                        float(scale_config["patch_radius_m"]),
                        float(scale_config["min_std_u8"]),
                    )
                    if rc != 0:
                        raise RuntimeError(f"add_view[{scale},{view}] failed: {rc}")
            views_added = time.perf_counter()

            plain = (CandidateResult * candidate_count)()
            colored = (CandidateResult * candidate_count)()
            rgb = np.zeros(candidate_count * 3, dtype=np.uint8)
            rc = api.aether_planesweep_session_finish(
                session,
                pointer(flat_masks, ctypes.c_uint8),
                native_options,
                scale_count,
                plain,
                candidate_count,
            )
            plain_finished = time.perf_counter()
            if rc != 0:
                raise RuntimeError(f"session_finish failed: {rc}")
            rc = api.aether_planesweep_session_finish_rgb(
                session,
                pointer(flat_masks, ctypes.c_uint8),
                native_options,
                scale_count,
                colored,
                candidate_count,
                pointer(rgb, ctypes.c_uint8),
                rgb.size,
            )
            rgb_finished = time.perf_counter()
            if rc != 0:
                raise RuntimeError(f"session_finish_rgb failed: {rc}")
        finally:
            api.aether_planesweep_session_free(session)
        freed = time.perf_counter()

        session_timings_ms.append(
            {
                "iteration": iteration,
                "create": (created - started) * 1000.0,
                "add_all_views": (views_added - created) * 1000.0,
                "finish_plain": (plain_finished - views_added) * 1000.0,
                "finish_rgb": (rgb_finished - plain_finished) * 1000.0,
                "free": (freed - rgb_finished) * 1000.0,
                "total": (freed - started) * 1000.0,
            }
        )
        plain_snapshot = [result_tuple(plain[index]) for index in range(candidate_count)]
        colored_snapshot = [
            result_tuple(colored[index]) for index in range(candidate_count)
        ]
        rgb_snapshot = rgb.copy()
        if reference_plain is None:
            reference_plain = plain_snapshot
            reference_colored = colored_snapshot
            reference_rgb = rgb_snapshot
        elif (
            plain_snapshot != reference_plain
            or colored_snapshot != reference_colored
            or not np.array_equal(rgb_snapshot, reference_rgb)
        ):
            raise RuntimeError(f"session {iteration} changed deterministic output")

    geometry_exact = all(
        result_tuple(plain[index]) == result_tuple(colored[index])
        for index in range(candidate_count)
    )
    accepted = [index for index in range(candidate_count) if colored[index].accepted]
    expected_accepted = manifest["expected"]["union_accepted_local_indices"]
    expected_rgb = np.zeros((candidate_count, 3), dtype=np.uint8)
    accepted_scale: dict[int, int] = {}
    already_accepted: set[int] = set()
    for scale, key in enumerate(
        ("baseline_accepted_local_indices", "rescue_accepted_local_indices")
    ):
        for candidate in manifest["expected"][key]:
            if candidate not in already_accepted:
                accepted_scale[candidate] = scale
                already_accepted.add(candidate)
    points_xyz = points.reshape(point_count, 3)
    for candidate in expected_accepted:
        scale = accepted_scale[candidate]
        center_point = candidate * hypotheses
        clique = exact_clique_views(
            patches[scale],
            valid[scale],
            masks[scale],
            center_point,
            int(manifest["scales"][scale]["min_views"]),
            float(manifest["scales"][scale]["ncc_min"]),
        )
        colors = []
        for view in clique:
            projection = np.asarray(
                manifest["frames"][view]["projection_row_major_f32"],
                dtype=np.float32,
            )
            colors.append(
                bilinear_rgb(frames[view], projection, points_xyz[center_point])
            )
        expected_rgb[candidate] = np.rint(np.median(colors, axis=0)).astype(np.uint8)

    actual_rgb = rgb.reshape(candidate_count, 3)
    rejected_black = all(
        not actual_rgb[index].any()
        for index in range(candidate_count)
        if index not in accepted
    )
    color_exact = np.array_equal(actual_rgb[expected_accepted], expected_rgb[expected_accepted])
    verdict_pass = (
        geometry_exact
        and accepted == expected_accepted
        and rejected_black
        and color_exact
    )
    result = {
        "schema": "pocketworld_host_dawn_rgb_parity_v1",
        "decision": (
            "PASS_HOST_DAWN_GEOMETRY_AND_CLIQUE_RGB_EXACT_PARITY"
            if verdict_pass
            else "FAIL_HOST_DAWN_GEOMETRY_OR_CLIQUE_RGB_PARITY"
        ),
        "fixture": str(fixture),
        "library": str(args.library.resolve()),
        "accepted_actual": accepted,
        "accepted_expected": expected_accepted,
        "plain_vs_rgb_geometry_exact": geometry_exact,
        "rejected_candidates_black": rejected_black,
        "accepted_rgb_exact": color_exact,
        "accepted_rgb_actual": actual_rgb[expected_accepted].tolist(),
        "accepted_rgb_expected": expected_rgb[expected_accepted].tolist(),
        "repeat_sessions": args.repeat_sessions,
        "sessions_deterministic": True,
        "session_timings_ms": session_timings_ms,
        "cold_create_ms": session_timings_ms[0]["create"],
        "warm_create_median_ms": (
            float(np.median([item["create"] for item in session_timings_ms[1:]]))
            if len(session_timings_ms) > 1
            else None
        ),
        "no_matcher_model_lidar_or_scene_depth_consumed": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if verdict_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
