#!/usr/bin/env python3
"""Verify shared C wall fitting against the frozen cap50/cap51 baselines."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
REFERENCE = (
    ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/fit_structural_planes.py"
)
CAPTURES = {
    "cap50": ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/runs/"
    "cap50_pure_a_wall_ceiling_20260714/structural_planes_v5_floor.json",
    "cap51": ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/runs/"
    "cap51_pure_a_wall_holdout_20260715/structural_planes.json",
}


class FitOptions(ctypes.Structure):
    _fields_ = [
        ("max_walls", ctypes.c_int32),
        ("theta_step_deg", ctypes.c_int32),
        ("minimum_height_m", ctypes.c_double),
        ("wall_fit_band_m", ctypes.c_double),
        ("rho_step_m", ctypes.c_double),
        ("minimum_tangent_span_m", ctypes.c_double),
        ("minimum_height_span_m", ctypes.c_double),
        ("preliminary_minimum_support", ctypes.c_int32),
        ("certified_minimum_support", ctypes.c_int32),
        ("certified_minimum_cells", ctypes.c_int32),
    ]


class Floor(ctypes.Structure):
    _fields_ = [
        ("certified", ctypes.c_int32),
        ("support_points", ctypes.c_int32),
        ("coverage_cells_10cm", ctypes.c_int32),
        ("normal_xyz", ctypes.c_double * 3),
        ("value_n_dot_x", ctypes.c_double),
        ("rms_error_m", ctypes.c_double),
    ]


class Wall(ctypes.Structure):
    _fields_ = [
        ("wall_index", ctypes.c_int32),
        ("theta_deg", ctypes.c_int32),
        ("certified", ctypes.c_int32),
        ("support_points_35mm", ctypes.c_int32),
        ("coverage_cells_10cm", ctypes.c_int32),
        ("domain_points", ctypes.c_int32),
        ("support_points_20mm", ctypes.c_int32 * 5),
        ("support_cells_10cm", ctypes.c_int32 * 5),
        ("normal_xyz", ctypes.c_double * 3),
        ("basis_u_xyz", ctypes.c_double * 3),
        ("basis_v_xyz", ctypes.c_double * 3),
        ("plane_value_n_dot_x", ctypes.c_double),
        ("bounds_u_m", ctypes.c_double * 2),
        ("bounds_height_m", ctypes.c_double * 2),
        ("score", ctypes.c_double),
        ("support_prominence_vs_5cm", ctypes.c_double),
        ("coverage_prominence_vs_5cm", ctypes.c_double),
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_reference():
    spec = importlib.util.spec_from_file_location("pw_plane_fit_reference", REFERENCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {REFERENCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure_api(library: Path):
    api = ctypes.CDLL(str(library))
    api.aether_structural_fit_floor.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(Floor),
    ]
    api.aether_structural_fit_floor.restype = ctypes.c_int32
    api.aether_structural_plane_fit_options_default.argtypes = [
        ctypes.POINTER(FitOptions)
    ]
    api.aether_structural_fit_walls.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_double,
        ctypes.POINTER(FitOptions),
        ctypes.POINTER(Wall),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
    ]
    api.aether_structural_fit_walls.restype = ctypes.c_int32
    return api


def compare_floor(actual: Floor, expected: dict, rc: int, elapsed_ms: float) -> dict:
    actual_normal = np.asarray(actual.normal_xyz, dtype=np.float64)
    expected_normal = np.asarray(expected["normal"], dtype=np.float64)
    if float(np.dot(actual_normal, expected_normal)) < 0:
        actual_normal = -actual_normal
        actual_value = -actual.value_n_dot_x
    else:
        actual_value = actual.value_n_dot_x
    angle_deg = float(
        np.degrees(
            np.arccos(np.clip(np.dot(actual_normal, expected_normal), -1.0, 1.0))
        )
    )
    value_error_m = abs(actual_value - expected["plane_value_n_dot_x"])
    passed = (
        rc == 0
        and bool(actual.certified)
        and actual.support_points >= 500
        and actual.coverage_cells_10cm >= 50
        and actual.rms_error_m <= 0.02
        and angle_deg <= 1.0
        and value_error_m <= 0.02
    )
    return {
        "rc": rc,
        "certified": bool(actual.certified),
        "support_points": actual.support_points,
        "coverage_cells_10cm": actual.coverage_cells_10cm,
        "normal_xyz": list(actual.normal_xyz),
        "value_n_dot_x": actual.value_n_dot_x,
        "rms_error_m": actual.rms_error_m,
        "reference_angle_error_deg": angle_deg,
        "reference_plane_value_error_m": value_error_m,
        "elapsed_ms": elapsed_ms,
        "thresholds": {
            "minimum_support_points": 500,
            "minimum_coverage_cells_10cm": 50,
            "maximum_rms_error_m": 0.02,
            "maximum_reference_angle_error_deg": 1.0,
            "maximum_reference_plane_value_error_m": 0.02,
        },
        "verdict": "PASS_CERTIFIED_FLOOR_PARITY" if passed else "FAIL",
    }


def compare_wall(actual: Wall, expected: dict) -> dict:
    vector_fields = {
        "normal_xyz": (list(actual.normal_xyz), expected["normal"]),
        "basis_u_xyz": (list(actual.basis_u_xyz), expected["basis_u"]),
        "basis_v_xyz": (list(actual.basis_v_xyz), expected["basis_v"]),
        "bounds_u_m": (list(actual.bounds_u_m), expected["bounds_u_m"]),
        "bounds_height_m": (
            list(actual.bounds_height_m),
            expected["bounds_height_m"],
        ),
    }
    maximum_vector_error = max(
        float(np.max(np.abs(np.asarray(left) - np.asarray(right))))
        for left, right in vector_fields.values()
    )
    scalar_error = abs(
        actual.plane_value_n_dot_x - expected["plane_value_n_dot_x"]
    )
    exact_discrete = (
        actual.theta_deg == expected["theta_deg_in_horizontal_basis"]
        and actual.support_points_35mm == expected["support_points_35mm"]
        and actual.coverage_cells_10cm == expected["coverage_cells_10cm"]
        and bool(actual.certified) == bool(expected["certified_for_generation"])
    )
    return {
        "surface_id": expected["surface_id"],
        "theta_deg": actual.theta_deg,
        "plane_value_n_dot_x": actual.plane_value_n_dot_x,
        "support_points_35mm": actual.support_points_35mm,
        "coverage_cells_10cm": actual.coverage_cells_10cm,
        "certified": bool(actual.certified),
        "maximum_vector_abs_error": maximum_vector_error,
        "plane_value_abs_error": scalar_error,
        "exact_discrete": exact_discrete,
        "pass": exact_discrete
        and maximum_vector_error <= 1e-9
        and scalar_error <= 1e-9,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    aether_root = args.aether_root.resolve()
    header = aether_root / "aether_cpp/include/aether_structural_plane_fit_c.h"
    source = (
        aether_root
        / "aether_cpp/src/pipeline/aether_structural_plane_fit_c.cpp"
    )
    compile_command: list[str]
    reference = load_reference()
    results = []
    with tempfile.TemporaryDirectory(prefix="pw_structural_fit_") as temp:
        library = Path(temp) / "libstructural_plane_fit.dylib"
        compile_command = [
            "clang++",
            "-std=c++20",
            "-O2",
            "-fno-exceptions",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-dynamiclib",
            "-I",
            str(header.parent),
            str(source),
            "-o",
            str(library),
        ]
        subprocess.run(compile_command, check=True)
        api = configure_api(library)
        for capture, planes_path in CAPTURES.items():
            planes = json.loads(planes_path.read_text())
            cloud_path = ROOT / planes["inputs"]["sparse_cloud"]["path"]
            xyz = np.ascontiguousarray(reference.read_ply_xyz(cloud_path), np.float32)
            floor = planes["floor"]
            up_hint = (ctypes.c_double * 3)(0.0, 1.0, 0.0)
            fitted_floor = Floor()
            started = time.perf_counter()
            floor_rc = api.aether_structural_fit_floor(
                xyz.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                len(xyz),
                up_hint,
                ctypes.byref(fitted_floor),
            )
            floor_elapsed_ms = (time.perf_counter() - started) * 1000.0
            floor_comparison = compare_floor(
                fitted_floor, floor, floor_rc, floor_elapsed_ms
            )
            normal = (ctypes.c_double * 3)(*floor["normal"])
            options = FitOptions()
            api.aether_structural_plane_fit_options_default(ctypes.byref(options))
            walls = (Wall * options.max_walls)()
            count = ctypes.c_int32()
            rc = api.aether_structural_fit_walls(
                xyz.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                len(xyz),
                normal,
                floor["plane_value_n_dot_x"],
                ctypes.byref(options),
                walls,
                options.max_walls,
                ctypes.byref(count),
            )
            expected = [
                surface
                for surface in planes["surfaces"]
                if surface["kind"] == "wall"
            ]
            comparisons = [
                compare_wall(walls[index], expected[index])
                for index in range(min(count.value, len(expected)))
            ]
            passed = (
                floor_comparison["verdict"].startswith("PASS")
                and
                rc == 0
                and count.value == len(expected)
                and all(item["pass"] for item in comparisons)
            )
            results.append(
                {
                    "capture": capture,
                    "rc": rc,
                    "point_count": len(xyz),
                    "floor": floor_comparison,
                    "actual_wall_count": count.value,
                    "expected_wall_count": len(expected),
                    "walls": comparisons,
                    "inputs": {
                        "cloud": {"path": str(cloud_path), "sha256": sha256(cloud_path)},
                        "planes": {
                            "path": str(planes_path),
                            "sha256": sha256(planes_path),
                        },
                    },
                    "verdict": "PASS_EXACT_WALL_FIT_PARITY" if passed else "FAIL",
                }
            )
    passed = all(result["verdict"].startswith("PASS") for result in results)
    output = {
        "schema": "pocketworld_structural_plane_fit_c_abi_parity_v2",
        "implementation": {
            "header": {"path": str(header), "sha256": sha256(header)},
            "source": {"path": str(source), "sha256": sha256(source)},
        },
        "compile_command": compile_command,
        "captures": results,
        "verdict": "PASS_CAP50_CAP51_EXACT_WALL_FIT_PARITY" if passed else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
