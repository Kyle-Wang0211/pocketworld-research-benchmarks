#!/usr/bin/env python3
"""Verify shared-C camera-envelope walls against four frozen scenes."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
BASELINES = {
    "cap40": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap40_bed_scene_20260716/wall_envelope_proposals_tls_v3.json",
    "cap41": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap41_bed_scene_20260716/wall_envelope_proposals_tls_v3.json",
    "cap50": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap50_wall_envelope_proposals_tls_v3.json",
    "cap51": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap51_wall_envelope_proposals_tls_v3.json",
}


class Options(ctypes.Structure):
    _fields_ = [
        ("maximum_candidates", ctypes.c_int32),
        ("theta_step_deg", ctypes.c_int32),
        ("minimum_height_m", ctypes.c_double),
        ("maximum_height_percentile", ctypes.c_double),
        ("rho_step_m", ctypes.c_double),
        ("fit_band_m", ctypes.c_double),
        ("minimum_support", ctypes.c_int32),
        ("minimum_tangent_span_m", ctypes.c_double),
        ("minimum_height_span_m", ctypes.c_double),
        ("camera_crossing_tolerance_m", ctypes.c_double),
        ("duplicate_angle_deg", ctypes.c_int32),
        ("duplicate_plane_value_m", ctypes.c_double),
    ]


class Wall(ctypes.Structure):
    _fields_ = [
        ("proposal_index", ctypes.c_int32),
        ("support_points_35mm", ctypes.c_int32),
        ("coverage_cells_10cm", ctypes.c_int32),
        ("theta_deg", ctypes.c_double),
        ("normal_xyz", ctypes.c_double * 3),
        ("basis_u_xyz", ctypes.c_double * 3),
        ("basis_v_xyz", ctypes.c_double * 3),
        ("plane_value_n_dot_x", ctypes.c_double),
        ("bounds_u_m", ctypes.c_double * 2),
        ("bounds_height_m", ctypes.c_double * 2),
        ("score", ctypes.c_double),
        ("camera_distance_min_m", ctypes.c_double),
        ("camera_distance_max_m", ctypes.c_double),
        ("camera_clearance_min_abs_m", ctypes.c_double),
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def configure(library: Path):
    api = ctypes.CDLL(str(library))
    api.aether_structural_envelope_wall_options_default.argtypes = [
        ctypes.POINTER(Options)
    ]
    api.aether_structural_propose_envelope_walls.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_double,
        ctypes.POINTER(Options),
        ctypes.POINTER(Wall),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
    ]
    api.aether_structural_propose_envelope_walls.restype = ctypes.c_int32
    return api


def selected_floor(path: Path) -> dict:
    result = json.loads(path.read_text())
    winner = result["selection"]["winner_surface_id"]
    return next(
        row["proposal"]
        for row in result["candidates"]
        if row["proposal"]["surface_id"] == winner
    )


def camera_centers(path: Path) -> np.ndarray:
    frames = json.loads(path.read_text())["frames"]
    result = []
    for frame in frames:
        transform = np.asarray(frame["extrinsic"], dtype=np.float64).reshape(4, 4).T
        result.append(transform[:3, 3])
    return np.ascontiguousarray(result, dtype=np.float64)


def compare(actual: Wall, expected: dict, index: int) -> dict:
    vector_fields = {
        "normal": (actual.normal_xyz, expected["normal"]),
        "basis_u": (actual.basis_u_xyz, expected["basis_u"]),
        "basis_v": (actual.basis_v_xyz, expected["basis_v"]),
        "bounds_u_m": (actual.bounds_u_m, expected["bounds_u_m"]),
        "bounds_height_m": (actual.bounds_height_m, expected["bounds_height_m"]),
    }
    vector_error = max(
        float(np.max(np.abs(np.asarray(left) - np.asarray(right))))
        for left, right in vector_fields.values()
    )
    scalar_errors = {
        "theta_deg": abs(actual.theta_deg - expected["theta_deg_in_horizontal_basis"]),
        "plane_value_m": abs(actual.plane_value_n_dot_x - expected["plane_value_n_dot_x"]),
        "score": abs(actual.score - expected["score"]),
        "camera_min_m": abs(actual.camera_distance_min_m - expected["camera_distance_min_m"]),
        "camera_max_m": abs(actual.camera_distance_max_m - expected["camera_distance_max_m"]),
        "camera_clearance_m": abs(actual.camera_clearance_min_abs_m - expected["camera_clearance_min_abs_m"]),
    }
    discrete = (
        actual.proposal_index == index
        and actual.support_points_35mm == expected["support_points_35mm"]
        and actual.coverage_cells_10cm == expected["coverage_cells_10cm"]
    )
    maximum_scalar_error = max(scalar_errors.values())
    passed = discrete and vector_error <= 1e-8 and maximum_scalar_error <= 1e-8
    return {
        "surface_id": expected["surface_id"],
        "discrete_exact": discrete,
        "maximum_vector_abs_error": vector_error,
        "scalar_abs_errors": scalar_errors,
        "pass": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    aether_root = args.aether_root.resolve()
    library = aether_root / "aether_cpp/build/libaether3d_ffi.dylib"
    header = aether_root / "aether_cpp/include/aether_structural_plane_fit_c.h"
    source = aether_root / "aether_cpp/src/pipeline/aether_structural_plane_fit_c.cpp"
    api = configure(library)
    captures = []
    for capture, baseline_path in BASELINES.items():
        baseline = json.loads(baseline_path.read_text())
        cloud_path = ROOT / baseline["inputs"]["metric_cloud"]["path"]
        floor_path = ROOT / baseline["inputs"]["floor_selection"]["path"]
        frame_path = ROOT / baseline["inputs"]["frame_meta"]["path"]
        xyz = np.ascontiguousarray(np.load(cloud_path)["xyz"], dtype=np.float32)
        cameras = camera_centers(frame_path)
        floor = selected_floor(floor_path)
        options = Options()
        api.aether_structural_envelope_wall_options_default(ctypes.byref(options))
        options.maximum_candidates = baseline["config"]["maximum_candidates"]
        walls = (Wall * options.maximum_candidates)()
        count = ctypes.c_int32()
        normal = (ctypes.c_double * 3)(*floor["normal"])
        rc = api.aether_structural_propose_envelope_walls(
            xyz.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            len(xyz),
            cameras.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            len(cameras),
            normal,
            floor["plane_value_n_dot_x"],
            ctypes.byref(options),
            walls,
            options.maximum_candidates,
            ctypes.byref(count),
        )
        expected = baseline["walls"]
        comparisons = [
            compare(walls[index], expected[index], index)
            for index in range(min(count.value, len(expected)))
        ]
        passed = rc == 0 and count.value == len(expected) and all(
            row["pass"] for row in comparisons
        )
        captures.append(
            {
                "capture": capture,
                "rc": rc,
                "actual_count": count.value,
                "expected_count": len(expected),
                "comparisons": comparisons,
                "inputs": {
                    "metric_cloud": {"path": str(cloud_path), "sha256": sha256(cloud_path)},
                    "floor_selection": {"path": str(floor_path), "sha256": sha256(floor_path)},
                    "frame_meta": {"path": str(frame_path), "sha256": sha256(frame_path)},
                    "baseline": {"path": str(baseline_path), "sha256": sha256(baseline_path)},
                },
                "verdict": "PASS_ENVELOPE_WALL_PARITY" if passed else "FAIL",
            }
        )
    passed = all(row["verdict"].startswith("PASS") for row in captures)
    result = {
        "schema": "pocketworld_structural_envelope_wall_c_abi_parity_v1",
        "implementation": {
            "library": {"path": str(library), "sha256": sha256(library)},
            "header": {"path": str(header), "sha256": sha256(header)},
            "source": {"path": str(source), "sha256": sha256(source)},
        },
        "captures": captures,
        "forbidden_inputs_consumed": {
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
            "reference_plane": False,
        },
        "verdict": "PASS_CAP40_41_50_51_ENVELOPE_WALL_PARITY" if passed else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
