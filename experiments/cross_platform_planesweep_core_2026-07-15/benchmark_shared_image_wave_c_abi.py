#!/usr/bin/env python3
"""Verify exact multi-session output while sharing one decoded/uploaded JPEG."""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import time
from pathlib import Path

import numpy as np


def load_module(name: str):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_shared_api(api) -> None:
    float_ptr = ctypes.POINTER(ctypes.c_float)
    i32_ptr = ctypes.POINTER(ctypes.c_int32)
    api.aether_planesweep_image_decode_jpeg.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
        i32_ptr,
        i32_ptr,
    ]
    api.aether_planesweep_image_decode_jpeg.restype = ctypes.c_int32
    api.aether_planesweep_session_add_image_view_scales.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_void_p,
        float_ptr,
        float_ptr,
        float_ptr,
        float_ptr,
        ctypes.c_int32,
    ]
    api.aether_planesweep_session_add_image_view_scales.restype = ctypes.c_int32
    api.aether_planesweep_image_free.argtypes = [ctypes.c_void_p]
    api.aether_planesweep_image_free.restype = None


def create_session(api, abi, options, points: np.ndarray) -> ctypes.c_void_p:
    session = ctypes.c_void_p()
    rc = api.aether_planesweep_session_create(
        ctypes.byref(options),
        abi.pointer(points, ctypes.c_float),
        ctypes.byref(session),
    )
    if rc != 0 or not session:
        raise RuntimeError(f"session_create failed: {rc}")
    return session


def finish_session(
    api,
    abi,
    session,
    candidate_count: int,
    scale_count: int,
    masks: np.ndarray,
    native_options,
) -> dict:
    results = (abi.CandidateResult * candidate_count)()
    rgb = np.zeros(candidate_count * 3, dtype=np.uint8)
    rc = api.aether_planesweep_session_finish_rgb(
        session,
        abi.pointer(masks, ctypes.c_uint8),
        native_options,
        scale_count,
        results,
        candidate_count,
        abi.pointer(rgb, ctypes.c_uint8),
        rgb.size,
    )
    if rc != 0:
        raise RuntimeError(f"finish_rgb failed: {rc}")
    return {
        "results": [
            abi.result_tuple(results[index]) for index in range(candidate_count)
        ],
        "rgb": rgb.tolist(),
    }


def run_independent(
    *,
    api,
    abi,
    options,
    points,
    manifest,
    jpeg_paths,
    projections,
    centers,
    patch_radii,
    minimum_std,
    masks,
    native_options,
    repeats: int,
) -> tuple[list[dict], float]:
    started = time.perf_counter()
    snapshots = []
    for _ in range(repeats):
        session = create_session(api, abi, options, points)
        try:
            for view, jpeg_path in enumerate(jpeg_paths):
                width = ctypes.c_int32()
                height = ctypes.c_int32()
                rc = api.aether_planesweep_session_add_jpeg_view_scales(
                    session,
                    view,
                    str(jpeg_path).encode(),
                    abi.pointer(projections[view], ctypes.c_float),
                    abi.pointer(centers[view], ctypes.c_float),
                    abi.pointer(patch_radii, ctypes.c_float),
                    abi.pointer(minimum_std, ctypes.c_float),
                    len(manifest["scales"]),
                    ctypes.byref(width),
                    ctypes.byref(height),
                )
                if rc != 0:
                    raise RuntimeError(f"independent add[{view}] failed: {rc}")
            snapshots.append(
                finish_session(
                    api,
                    abi,
                    session,
                    int(manifest["candidate_count"]),
                    len(manifest["scales"]),
                    masks,
                    native_options,
                )
            )
        finally:
            api.aether_planesweep_session_free(session)
    return snapshots, (time.perf_counter() - started) * 1000.0


def run_shared(
    *,
    api,
    abi,
    options,
    points,
    manifest,
    jpeg_paths,
    projections,
    centers,
    patch_radii,
    minimum_std,
    masks,
    native_options,
    repeats: int,
) -> tuple[list[dict], float]:
    started = time.perf_counter()
    sessions = [create_session(api, abi, options, points) for _ in range(repeats)]
    try:
        for view, jpeg_path in enumerate(jpeg_paths):
            image = ctypes.c_void_p()
            width = ctypes.c_int32()
            height = ctypes.c_int32()
            rc = api.aether_planesweep_image_decode_jpeg(
                str(jpeg_path).encode(),
                ctypes.byref(image),
                ctypes.byref(width),
                ctypes.byref(height),
            )
            if rc != 0 or not image:
                raise RuntimeError(f"shared decode[{view}] failed: {rc}")
            try:
                for session_index, session in enumerate(sessions):
                    rc = api.aether_planesweep_session_add_image_view_scales(
                        session,
                        view,
                        image,
                        abi.pointer(projections[view], ctypes.c_float),
                        abi.pointer(centers[view], ctypes.c_float),
                        abi.pointer(patch_radii, ctypes.c_float),
                        abi.pointer(minimum_std, ctypes.c_float),
                        len(manifest["scales"]),
                    )
                    if rc != 0:
                        raise RuntimeError(
                            f"shared add[{view},{session_index}] failed: {rc}"
                        )
            finally:
                api.aether_planesweep_image_free(image)
        snapshots = [
            finish_session(
                api,
                abi,
                session,
                int(manifest["candidate_count"]),
                len(manifest["scales"]),
                masks,
                native_options,
            )
            for session in sessions
        ]
    finally:
        for session in reversed(sessions):
            api.aether_planesweep_session_free(session)
    return snapshots, (time.perf_counter() - started) * 1000.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--jpeg-root", type=Path, required=True)
    parser.add_argument("--wave-sessions", type=int, default=8)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.wave_sessions <= 1 or args.iterations <= 0:
        parser.error("wave sessions must be >1 and iterations must be positive")

    abi = load_module("verify_host_dawn_rgb_parity.py")
    jpeg_bench = load_module("benchmark_multiscale_jpeg_c_abi.py")
    manifest = json.loads((args.fixture / "fixture_manifest.json").read_text())
    points = np.ascontiguousarray(
        np.fromfile(args.fixture / "points.f32", dtype="<f4"), dtype=np.float32
    )
    jpeg_paths = [
        args.jpeg_root / frame["source_photo"] for frame in manifest["frames"]
    ]
    if any(not path.is_file() for path in jpeg_paths):
        raise FileNotFoundError([str(path) for path in jpeg_paths if not path.is_file()])
    if not all(
        jpeg_bench.sha256(path) == frame["source_photo_sha256"]
        for path, frame in zip(jpeg_paths, manifest["frames"])
    ):
        raise RuntimeError("source JPEG hash mismatch")

    api = abi.load_api(args.library.resolve())
    jpeg_bench.configure_jpeg_api(api)
    configure_shared_api(api)
    options = abi.SessionOptions()
    api.aether_planesweep_session_options_default(ctypes.byref(options))
    options.point_count = int(manifest["point_count"])
    options.candidate_count = int(manifest["candidate_count"])
    options.hypotheses_per_candidate = int(manifest["hypothesis_count"])
    options.patch_n = int(manifest["patch_n"])
    options.max_views = len(manifest["frames"])
    options.scale_count = len(manifest["scales"])
    for axis in range(3):
        options.basis_u_xyz[axis] = float(manifest["basis_u_f32"][axis])
        options.basis_v_xyz[axis] = float(manifest["basis_v_f32"][axis])
    projections = [
        jpeg_bench.full_jpeg_projection(frame) for frame in manifest["frames"]
    ]
    centers = [
        np.ascontiguousarray(frame["camera_center_f32"], dtype=np.float32)
        for frame in manifest["frames"]
    ]
    patch_radii = np.ascontiguousarray(
        [scale["patch_radius_m"] for scale in manifest["scales"]],
        dtype=np.float32,
    )
    minimum_std = np.ascontiguousarray(
        [scale["min_std_u8"] for scale in manifest["scales"]],
        dtype=np.float32,
    )
    masks = np.zeros(
        (len(manifest["scales"]), options.point_count, options.max_views),
        dtype=np.uint8,
    )
    for scale, table in enumerate(
        manifest["candidate_resource_frame_indices_by_scale"]
    ):
        for point, frame_indices in enumerate(table):
            masks[scale, point, np.asarray(frame_indices, dtype=np.int64)] = 1
    masks = np.ascontiguousarray(masks.reshape(-1))
    native_options = (abi.BirthOptions * len(manifest["scales"]))(
        *(abi.birth_options(api, scale) for scale in manifest["scales"])
    )
    kwargs = dict(
        api=api,
        abi=abi,
        options=options,
        points=points,
        manifest=manifest,
        jpeg_paths=jpeg_paths,
        projections=projections,
        centers=centers,
        patch_radii=patch_radii,
        minimum_std=minimum_std,
        masks=masks,
        native_options=native_options,
        repeats=args.wave_sessions,
    )

    warm_old, _ = run_independent(**kwargs)
    warm_new, _ = run_shared(**kwargs)
    reference = warm_old[0]
    exact = all(item == reference for item in warm_old + warm_new)
    timings = {"independent": [], "shared": []}
    for iteration in range(args.iterations):
        order = ("shared", "independent") if iteration % 2 == 0 else (
            "independent",
            "shared",
        )
        for mode in order:
            snapshots, elapsed = (
                run_shared(**kwargs) if mode == "shared" else run_independent(**kwargs)
            )
            exact = exact and all(item == reference for item in snapshots)
            timings[mode].append(elapsed)
    old_ms = float(np.median(timings["independent"]))
    new_ms = float(np.median(timings["shared"]))
    passed = exact and new_ms <= old_ms
    result = {
        "schema": "pocketworld_shared_image_wave_c_abi_bench_v1",
        "decision": "PASS_EXACT_SHARED_IMAGE_WAVE_SPEED" if passed else "FAIL",
        "library": str(args.library.resolve()),
        "fixture": str(args.fixture.resolve()),
        "wave_sessions": args.wave_sessions,
        "iterations": args.iterations,
        "all_candidate_results_ncc_rgb_exact": exact,
        "independent_median_ms": old_ms,
        "shared_image_wave_median_ms": new_ms,
        "speedup_ratio": old_ms / new_ms,
        "time_saved_percent": (old_ms - new_ms) / old_ms * 100.0,
        "timings_ms": timings,
        "bounded_residency": "one_decoded_and_one_gpu_image_at_a_time",
        "numeric_or_threshold_change": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
