#!/usr/bin/env python3
"""Compare repeated JPEG decode with the one-decode multi-scale C ABI."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np


def load_reference_module():
    path = Path(__file__).with_name("verify_host_dawn_rgb_parity.py")
    spec = importlib.util.spec_from_file_location("host_dawn_parity", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def full_jpeg_projection(frame_meta: dict) -> np.ndarray:
    projection = np.asarray(
        frame_meta["projection_row_major_f32"], dtype=np.float32
    ).copy()
    crop_x, crop_y = frame_meta["crop_xyxy"][:2]
    projection[0:4] += np.float32(crop_x) * projection[8:12]
    projection[4:8] += np.float32(crop_y) * projection[8:12]
    return np.ascontiguousarray(projection)


def configure_jpeg_api(api) -> None:
    float_ptr = ctypes.POINTER(ctypes.c_float)
    i32_ptr = ctypes.POINTER(ctypes.c_int32)
    api.aether_planesweep_session_add_jpeg_view.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_char_p,
        float_ptr,
        float_ptr,
        ctypes.c_float,
        ctypes.c_float,
        i32_ptr,
        i32_ptr,
    ]
    api.aether_planesweep_session_add_jpeg_view.restype = ctypes.c_int32
    api.aether_planesweep_session_add_jpeg_view_scales.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int32,
        ctypes.c_char_p,
        float_ptr,
        float_ptr,
        float_ptr,
        float_ptr,
        ctypes.c_int32,
        i32_ptr,
        i32_ptr,
    ]
    api.aether_planesweep_session_add_jpeg_view_scales.restype = ctypes.c_int32


def run_session(
    *,
    abi,
    api,
    mode: str,
    options,
    points: np.ndarray,
    manifest: dict,
    jpeg_paths: list[Path],
    native_options,
    flat_masks: np.ndarray,
):
    candidate_count = int(manifest["candidate_count"])
    scale_count = len(manifest["scales"])
    session = ctypes.c_void_p()
    started = time.perf_counter()
    rc = api.aether_planesweep_session_create(
        ctypes.byref(options),
        abi.pointer(points, ctypes.c_float),
        ctypes.byref(session),
    )
    created = time.perf_counter()
    if rc != 0:
        raise RuntimeError(f"session_create failed: {rc}")
    try:
        if mode == "single":
            for scale, scale_config in enumerate(manifest["scales"]):
                for view, (frame_meta, jpeg_path) in enumerate(
                    zip(manifest["frames"], jpeg_paths)
                ):
                    projection = full_jpeg_projection(frame_meta)
                    center = np.ascontiguousarray(
                        frame_meta["camera_center_f32"], dtype=np.float32
                    )
                    width = ctypes.c_int32()
                    height = ctypes.c_int32()
                    rc = api.aether_planesweep_session_add_jpeg_view(
                        session,
                        scale,
                        view,
                        str(jpeg_path).encode(),
                        abi.pointer(projection, ctypes.c_float),
                        abi.pointer(center, ctypes.c_float),
                        float(scale_config["patch_radius_m"]),
                        float(scale_config["min_std_u8"]),
                        ctypes.byref(width),
                        ctypes.byref(height),
                    )
                    if rc != 0:
                        raise RuntimeError(
                            f"single add_jpeg[{scale},{view}] failed: {rc}"
                        )
        elif mode == "multi":
            patch_radii = np.ascontiguousarray(
                [item["patch_radius_m"] for item in manifest["scales"]],
                dtype=np.float32,
            )
            minimum_std = np.ascontiguousarray(
                [item["min_std_u8"] for item in manifest["scales"]],
                dtype=np.float32,
            )
            for view, (frame_meta, jpeg_path) in enumerate(
                zip(manifest["frames"], jpeg_paths)
            ):
                projection = full_jpeg_projection(frame_meta)
                center = np.ascontiguousarray(
                    frame_meta["camera_center_f32"], dtype=np.float32
                )
                width = ctypes.c_int32()
                height = ctypes.c_int32()
                rc = api.aether_planesweep_session_add_jpeg_view_scales(
                    session,
                    view,
                    str(jpeg_path).encode(),
                    abi.pointer(projection, ctypes.c_float),
                    abi.pointer(center, ctypes.c_float),
                    abi.pointer(patch_radii, ctypes.c_float),
                    abi.pointer(minimum_std, ctypes.c_float),
                    scale_count,
                    ctypes.byref(width),
                    ctypes.byref(height),
                )
                if rc != 0:
                    raise RuntimeError(f"multi add_jpeg[{view}] failed: {rc}")
        else:
            raise ValueError(mode)
        views_added = time.perf_counter()

        results = (abi.CandidateResult * candidate_count)()
        rgb = np.zeros(candidate_count * 3, dtype=np.uint8)
        rc = api.aether_planesweep_session_finish_rgb(
            session,
            abi.pointer(flat_masks, ctypes.c_uint8),
            native_options,
            scale_count,
            results,
            candidate_count,
            abi.pointer(rgb, ctypes.c_uint8),
            rgb.size,
        )
        finished = time.perf_counter()
        if rc != 0:
            raise RuntimeError(f"finish_rgb failed: {rc}")
    finally:
        api.aether_planesweep_session_free(session)
    freed = time.perf_counter()
    snapshot = {
        "results": [
            abi.result_tuple(results[index]) for index in range(candidate_count)
        ],
        "rgb": rgb.copy(),
    }
    timing = {
        "create": (created - started) * 1000.0,
        "add_all_views": (views_added - created) * 1000.0,
        "finish_rgb": (finished - views_added) * 1000.0,
        "free": (freed - finished) * 1000.0,
        "total": (freed - started) * 1000.0,
    }
    return snapshot, timing


def same_snapshot(left: dict, right: dict) -> bool:
    return left["results"] == right["results"] and np.array_equal(
        left["rgb"], right["rgb"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--jpeg-root", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("--iterations must be positive")

    abi = load_reference_module()
    fixture = args.fixture.resolve()
    manifest = json.loads((fixture / "fixture_manifest.json").read_text())
    points = np.ascontiguousarray(
        np.fromfile(fixture / "points.f32", dtype="<f4"), dtype=np.float32
    )
    jpeg_root = args.jpeg_root.resolve()
    jpeg_paths = [jpeg_root / item["source_photo"] for item in manifest["frames"]]
    missing = [str(path) for path in jpeg_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(missing)
    source_hashes_exact = all(
        sha256(path) == frame["source_photo_sha256"]
        for path, frame in zip(jpeg_paths, manifest["frames"])
    )
    if not source_hashes_exact:
        raise RuntimeError("source JPEG hash mismatch")

    point_count = int(manifest["point_count"])
    candidate_count = int(manifest["candidate_count"])
    hypotheses = int(manifest["hypothesis_count"])
    view_count = len(manifest["frames"])
    scale_count = len(manifest["scales"])
    masks = np.zeros((scale_count, point_count, view_count), dtype=np.uint8)
    for scale, table in enumerate(
        manifest["candidate_resource_frame_indices_by_scale"]
    ):
        for point, frame_indices in enumerate(table):
            masks[scale, point, np.asarray(frame_indices, dtype=np.int64)] = 1
    flat_masks = np.ascontiguousarray(masks.reshape(-1))

    api = abi.load_api(args.library.resolve())
    configure_jpeg_api(api)
    options = abi.SessionOptions()
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
    native_options = (abi.BirthOptions * scale_count)(
        *(abi.birth_options(api, config) for config in manifest["scales"])
    )

    kwargs = {
        "abi": abi,
        "api": api,
        "options": options,
        "points": points,
        "manifest": manifest,
        "jpeg_paths": jpeg_paths,
        "native_options": native_options,
        "flat_masks": flat_masks,
    }
    # Warm the shared Dawn runtime, JPEG page cache, and both code paths before
    # recording. Production still pays JPEG decode; only filesystem cache noise
    # is excluded from the comparison.
    warm_single, _ = run_session(mode="single", **kwargs)
    warm_multi, _ = run_session(mode="multi", **kwargs)
    if not same_snapshot(warm_single, warm_multi):
        raise RuntimeError("warm-up modes produced different results")

    timings = {"single": [], "multi": []}
    reference = warm_single
    all_exact = True
    for iteration in range(args.iterations):
        order = ("multi", "single") if iteration % 2 == 0 else ("single", "multi")
        pair = {}
        for mode in order:
            snapshot, timing = run_session(mode=mode, **kwargs)
            timings[mode].append(timing)
            pair[mode] = snapshot
            all_exact = all_exact and same_snapshot(reference, snapshot)
        all_exact = all_exact and same_snapshot(pair["single"], pair["multi"])

    single_add = float(
        np.median([item["add_all_views"] for item in timings["single"]])
    )
    multi_add = float(
        np.median([item["add_all_views"] for item in timings["multi"]])
    )
    speed_non_regression = multi_add <= single_add
    accepted = sum(1 for item in reference["results"] if item[0] != 0)
    passed = all_exact and speed_non_regression
    result = {
        "schema": "pocketworld_multiscale_jpeg_c_abi_bench_v1",
        "decision": (
            "PASS_EXACT_PARITY_AND_MULTISCALE_JPEG_SPEED"
            if passed
            else "FAIL_PARITY_OR_MULTISCALE_JPEG_SPEED"
        ),
        "fixture": str(fixture),
        "jpeg_root": str(jpeg_root),
        "library": str(args.library.resolve()),
        "source_jpeg_hashes_exact": source_hashes_exact,
        "iterations_per_mode": args.iterations,
        "candidate_count": candidate_count,
        "accepted_candidates": accepted,
        "single_vs_multi_results_and_rgb_exact": all_exact,
        "single_decode_per_scale_add_median_ms": single_add,
        "one_decode_all_scales_add_median_ms": multi_add,
        "add_speedup_ratio": single_add / multi_add,
        "add_time_saved_percent": (single_add - multi_add) / single_add * 100.0,
        "speed_non_regression": speed_non_regression,
        "production_path_uses_finish_rgb_once": True,
        "timings_ms": timings,
        "no_resolution_view_threshold_or_numeric_change": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
