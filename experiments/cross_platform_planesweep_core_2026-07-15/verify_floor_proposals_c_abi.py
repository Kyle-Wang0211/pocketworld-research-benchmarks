#!/usr/bin/env python3
"""Verify shared-C multi-floor proposals against all four frozen scenes."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SELECTIONS = {
    "cap40": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap40_bed_scene_20260716/floor_candidate_selection_floor_contract_v5.json",
    "cap41": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap41_bed_scene_20260716/floor_candidate_selection_floor_contract_v5.json",
    "cap50": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap50_floor_candidate_selection_floor_contract_v5.json",
    "cap51": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap51_floor_candidate_selection_floor_contract_v5.json",
}


class Options(ctypes.Structure):
    _fields_ = [
        ("maximum_candidates", ctypes.c_int32),
        ("histogram_step_m", ctypes.c_double),
        ("minimum_peak_support", ctypes.c_int32),
        ("refinement_band_m", ctypes.c_double),
        ("support_band_m", ctypes.c_double),
        ("minimum_support_points", ctypes.c_int32),
        ("minimum_coverage_cells_10cm", ctypes.c_int32),
        ("maximum_tilt_deg", ctypes.c_double),
        ("minimum_camera_clearance_m", ctypes.c_double),
        ("distinct_plane_value_m", ctypes.c_double),
    ]


class Proposal(ctypes.Structure):
    _fields_ = [
        ("proposal_index", ctypes.c_int32),
        ("support_points_20mm", ctypes.c_int32),
        ("coverage_cells_10cm", ctypes.c_int32),
        ("normal_xyz", ctypes.c_double * 3),
        ("value_n_dot_x", ctypes.c_double),
        ("basis_u_xyz", ctypes.c_double * 3),
        ("basis_v_xyz", ctypes.c_double * 3),
        ("bounds_u_m", ctypes.c_double * 2),
        ("bounds_v_m", ctypes.c_double * 2),
        ("rms_error_m", ctypes.c_double),
        ("tilt_deg", ctypes.c_double),
        ("prior_score", ctypes.c_double),
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def configure(library: Path):
    api = ctypes.CDLL(str(library))
    api.aether_structural_floor_proposal_options_default.argtypes = [
        ctypes.POINTER(Options)
    ]
    api.aether_structural_propose_floors.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_double,
        ctypes.POINTER(Options),
        ctypes.POINTER(Proposal),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
    ]
    api.aether_structural_propose_floors.restype = ctypes.c_int32
    return api


def camera_centers(path: Path) -> np.ndarray:
    frames = json.loads(path.read_text())["frames"]
    centers = []
    for frame in frames:
        transform = np.asarray(frame["extrinsic"], dtype=np.float64).reshape(4, 4).T
        centers.append(transform[:3, 3])
    return np.asarray(centers, dtype=np.float64)


def compare(actual: Proposal, expected: dict, index: int) -> dict:
    vectors = {
        "normal": (actual.normal_xyz, expected["normal"]),
        "basis_u": (actual.basis_u_xyz, expected["basis_u"]),
        "basis_v": (actual.basis_v_xyz, expected["basis_v"]),
        "bounds_u_m": (actual.bounds_u_m, expected["bounds_u_m"]),
        "bounds_v_m": (actual.bounds_v_m, expected["bounds_v_m"]),
    }
    vector_error = max(
        float(np.max(np.abs(np.asarray(left) - np.asarray(right))))
        for left, right in vectors.values()
    )
    scalar_errors = {
        "plane_value_m": abs(actual.value_n_dot_x - expected["plane_value_n_dot_x"]),
        "rms_m": abs(actual.rms_error_m - expected["rms_error_m"]),
        "tilt_deg": abs(actual.tilt_deg - expected["tilt_deg"]),
        "prior_score": abs(actual.prior_score - expected["prior_score"]),
    }
    discrete = (
        actual.proposal_index == index
        and actual.support_points_20mm == expected["support_points_20mm"]
        and actual.coverage_cells_10cm == expected["coverage_cells_10cm"]
    )
    passed = (
        discrete
        and vector_error <= 1e-9
        and scalar_errors["plane_value_m"] <= 1e-9
        and scalar_errors["rms_m"] <= 1e-9
        and scalar_errors["tilt_deg"] <= 1e-8
        and scalar_errors["prior_score"] <= 1e-8
    )
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
    source = aether_root / "aether_cpp/src/pipeline/aether_structural_plane_fit_c.cpp"
    header = aether_root / "aether_cpp/include/aether_structural_plane_fit_c.h"
    api = configure(library)
    captures = []
    for capture, selection_path in SELECTIONS.items():
        selection = json.loads(selection_path.read_text())
        cloud_path = ROOT / selection["inputs"]["metric_cloud"]["path"]
        frame_path = ROOT / selection["inputs"]["frame_meta"]["path"]
        xyz = np.ascontiguousarray(np.load(cloud_path)["xyz"], dtype=np.float32)
        centers = camera_centers(frame_path)
        options = Options()
        api.aether_structural_floor_proposal_options_default(ctypes.byref(options))
        proposals = (Proposal * options.maximum_candidates)()
        count = ctypes.c_int32()
        up = (ctypes.c_double * 3)(0.0, 1.0, 0.0)
        rc = api.aether_structural_propose_floors(
            xyz.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            len(xyz),
            up,
            float(np.min(centers[:, 1])),
            ctypes.byref(options),
            proposals,
            options.maximum_candidates,
            ctypes.byref(count),
        )
        expected = [row["proposal"] for row in selection["candidates"]]
        comparisons = [
            compare(proposals[index], expected[index], index)
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
                "winner_surface_id": selection["selection"]["winner_surface_id"],
                "comparisons": comparisons,
                "inputs": {
                    "metric_cloud": {"path": str(cloud_path), "sha256": sha256(cloud_path)},
                    "frame_meta": {"path": str(frame_path), "sha256": sha256(frame_path)},
                    "selection": {"path": str(selection_path), "sha256": sha256(selection_path)},
                },
                "verdict": "PASS_EXACT_MULTI_FLOOR_PROPOSAL_PARITY" if passed else "FAIL",
            }
        )
    passed = all(row["verdict"].startswith("PASS") for row in captures)
    result = {
        "schema": "pocketworld_structural_floor_proposal_c_abi_parity_v1",
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
        "verdict": "PASS_CAP40_41_50_51_EXACT_MULTI_FLOOR_PROPOSAL_PARITY" if passed else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
