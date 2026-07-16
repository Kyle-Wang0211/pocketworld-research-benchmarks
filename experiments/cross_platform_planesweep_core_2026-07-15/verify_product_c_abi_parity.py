#!/usr/bin/env python3
"""Verify the product plane-sweep C ABI against a frozen research fixture."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import platform
import subprocess
import tempfile
from pathlib import Path

import numpy as np


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compile_library(aether_root: Path, output: Path) -> list[str]:
    source = aether_root / "aether_cpp/src/pipeline/aether_structural_planesweep_c.cpp"
    command = [
        "clang++",
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fPIC",
        "-I",
        str(aether_root / "aether_cpp/include"),
        str(source),
    ]
    command += ["-dynamiclib" if platform.system() == "Darwin" else "-shared"]
    command += ["-o", str(output)]
    subprocess.run(command, check=True)
    return command


def load_api(path: Path):
    library = ctypes.CDLL(str(path))
    float_ptr = ctypes.POINTER(ctypes.c_float)
    u8_ptr = ctypes.POINTER(ctypes.c_uint8)
    i32_ptr = ctypes.POINTER(ctypes.c_int32)
    library.aether_planesweep_score_scale.argtypes = [
        float_ptr,
        u8_ptr,
        u8_ptr,
        float_ptr,
        float_ptr,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(BirthOptions),
        i32_ptr,
        float_ptr,
        float_ptr,
        u8_ptr,
    ]
    library.aether_planesweep_score_scale.restype = ctypes.c_int32
    library.aether_planesweep_apply_unique_depth.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        i32_ptr,
        float_ptr,
        float_ptr,
        u8_ptr,
        ctypes.POINTER(BirthOptions),
        ctypes.POINTER(CandidateResult),
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    library.aether_planesweep_apply_unique_depth.restype = ctypes.c_int32
    return library


def pointer(array: np.ndarray, ctype):
    assert array.flags.c_contiguous
    return array.ctypes.data_as(ctypes.POINTER(ctype))


def options_from(config: dict) -> BirthOptions:
    return BirthOptions(
        minimum_views=int(config["min_views"]),
        ncc_min=float(config["ncc_min"]),
        minimum_parallax_deg=float(config["min_parallax_deg"]),
        unique_depth_margin=float(config["depth_ncc_margin"]),
        post_min_ncc=float(config.get("post_min_ncc", 0.0)),
        post_minimum_views=int(config.get("post_minimum_views", 0)),
        post_minimum_parallax_deg=float(
            config.get("post_minimum_parallax_deg", 0.0)
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    fixture = args.fixture.resolve()
    manifest_path = fixture / "fixture_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    scale_count = len(manifest["scales"])
    view_count = len(manifest["frames"])
    point_count = int(manifest["point_count"])
    candidate_count = int(manifest["candidate_count"])
    hypothesis_count = int(manifest["hypothesis_count"])
    sample_count = int(manifest["patch_sample_count"])

    patches_path = fixture / "expected_normalized_patches.f32"
    valid_path = fixture / "expected_valid.u8"
    points_path = fixture / "points.f32"
    for path, expected in (
        (patches_path, manifest["expected"]["normalized_patches_sha256"]),
        (valid_path, manifest["expected"]["valid_sha256"]),
        (points_path, manifest["expected"]["points_sha256"]),
    ):
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"fixture hash mismatch: {path}: {actual} != {expected}")

    patches = np.fromfile(patches_path, dtype="<f4").reshape(
        scale_count, view_count, point_count, sample_count
    )
    valid = np.fromfile(valid_path, dtype=np.uint8).reshape(
        scale_count, view_count, point_count
    )
    points = np.fromfile(points_path, dtype="<f4").reshape(point_count, 3)
    cameras = np.asarray(
        [frame["camera_center_f32"] for frame in manifest["frames"]],
        dtype=np.float32,
    )
    tables = manifest["candidate_resource_frame_indices_by_scale"]

    union_results = (CandidateResult * candidate_count)()
    accepted_by_scale: list[list[int]] = []
    evidence_by_scale: list[list[dict]] = []
    compile_command: list[str]
    with tempfile.TemporaryDirectory(prefix="pw_planesweep_cabi_") as temp:
        library_path = Path(temp) / (
            "libplanesweep.dylib" if platform.system() == "Darwin" else "libplanesweep.so"
        )
        compile_command = compile_library(args.aether_root.resolve(), library_path)
        api = load_api(library_path)
        for scale, config in enumerate(manifest["scales"]):
            masks = np.zeros((point_count, view_count), dtype=np.uint8)
            for point, frame_indices in enumerate(tables[scale]):
                masks[point, np.asarray(frame_indices, dtype=np.int64)] = 1
            supporting = np.zeros(point_count, dtype=np.int32)
            ncc = np.full(point_count, -np.inf, dtype=np.float32)
            parallax = np.zeros(point_count, dtype=np.float32)
            score_valid = np.zeros(point_count, dtype=np.uint8)
            options = options_from(config)
            rc = api.aether_planesweep_score_scale(
                pointer(np.ascontiguousarray(patches[scale]), ctypes.c_float),
                pointer(np.ascontiguousarray(valid[scale]), ctypes.c_uint8),
                pointer(masks, ctypes.c_uint8),
                pointer(cameras, ctypes.c_float),
                pointer(points, ctypes.c_float),
                view_count,
                point_count,
                sample_count,
                ctypes.byref(options),
                pointer(supporting, ctypes.c_int32),
                pointer(ncc, ctypes.c_float),
                pointer(parallax, ctypes.c_float),
                pointer(score_valid, ctypes.c_uint8),
            )
            if rc != 0:
                raise RuntimeError(f"score_scale[{scale}] failed: {rc}")
            raw_results = (CandidateResult * candidate_count)()
            rc = api.aether_planesweep_apply_unique_depth(
                candidate_count,
                hypothesis_count,
                pointer(supporting, ctypes.c_int32),
                pointer(ncc, ctypes.c_float),
                pointer(parallax, ctypes.c_float),
                pointer(score_valid, ctypes.c_uint8),
                ctypes.byref(options),
                raw_results,
                candidate_count,
                0,
            )
            if rc != 0:
                raise RuntimeError(f"apply_unique_depth raw[{scale}] failed: {rc}")
            raw_indices = [
                index for index, result in enumerate(raw_results) if result.accepted
            ]
            accepted_by_scale.append(raw_indices)
            evidence_by_scale.append(
                [
                    {
                        "local_index": index,
                        "views": int(raw_results[index].supporting_views),
                        "ncc": float(raw_results[index].median_ncc),
                        "parallax_deg": float(raw_results[index].max_parallax_deg),
                        "depth_ncc_margin": (
                            float(raw_results[index].observed_depth_margin)
                            if math.isfinite(raw_results[index].observed_depth_margin)
                            else None
                        ),
                    }
                    for index in raw_indices
                ]
            )
            rc = api.aether_planesweep_apply_unique_depth(
                candidate_count,
                hypothesis_count,
                pointer(supporting, ctypes.c_int32),
                pointer(ncc, ctypes.c_float),
                pointer(parallax, ctypes.c_float),
                pointer(score_valid, ctypes.c_uint8),
                ctypes.byref(options),
                union_results,
                candidate_count,
                1 if scale else 0,
            )
            if rc != 0:
                raise RuntimeError(f"apply_unique_depth union[{scale}] failed: {rc}")

    expected = manifest["expected"]
    expected_by_scale = [
        expected["baseline_accepted_local_indices"],
        expected["rescue_accepted_local_indices"],
    ]
    union = [
        index for index, result in enumerate(union_results) if result.accepted
    ]
    exact_by_scale = [
        actual == frozen for actual, frozen in zip(accepted_by_scale, expected_by_scale)
    ]
    union_exact = union == expected["union_accepted_local_indices"]
    verdict = {
        "schema": "pocketworld_product_planesweep_c_abi_parity_v1",
        "decision": (
            "PASS_PRODUCT_C_ABI_EXACT_PARITY"
            if all(exact_by_scale) and union_exact
            else "FAIL_PRODUCT_C_ABI_PARITY"
        ),
        "fixture_manifest": str(manifest_path),
        "fixture_manifest_sha256": sha256(manifest_path),
        "product_source": str(
            args.aether_root.resolve()
            / "aether_cpp/src/pipeline/aether_structural_planesweep_c.cpp"
        ),
        "product_source_sha256": sha256(
            args.aether_root.resolve()
            / "aether_cpp/src/pipeline/aether_structural_planesweep_c.cpp"
        ),
        "compile_command": compile_command,
        "actual_by_scale": accepted_by_scale,
        "expected_by_scale": expected_by_scale,
        "exact_by_scale": exact_by_scale,
        "actual_union": union,
        "expected_union": expected["union_accepted_local_indices"],
        "union_exact": union_exact,
        "evidence_by_scale": evidence_by_scale,
        "no_matcher_lidar_or_scene_depth_consumed": True,
    }
    encoded = json.dumps(verdict, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0 if verdict["decision"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
