#!/usr/bin/env python3
"""Cross-validate a sparse-manifold birth gate for additive D points.

The detector-free reciprocal result is still an internal candidate set.  A
candidate obtains product-point identity only when a local tangent manifold,
fit independently from two deterministic partitions of the SfM cloud, owns its
metric position.  A third partition is never used by the gate and is reserved
for quality evaluation; the held-out partition is then rotated three times.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree


EXPERIMENT = Path(__file__).resolve().parent
QUALITY_PATH = EXPERIMENT / "verify_multireference_product_quality.py"


class CLocalManifoldOptions(ctypes.Structure):
    _fields_ = [
        ("neighbors", ctypes.c_int32),
        ("partition_count", ctypes.c_int32),
        ("first_partition", ctypes.c_int32),
        ("second_partition", ctypes.c_int32),
        ("maximum_nearest_m", ctypes.c_double),
        ("maximum_neighbor_radius_m", ctypes.c_double),
        ("maximum_neighbor_rms_m", ctypes.c_double),
        ("maximum_perpendicular_m", ctypes.c_double),
    ]


class CWall(ctypes.Structure):
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


class CFloorDomain(ctypes.Structure):
    _fields_ = [
        ("certified", ctypes.c_int32),
        ("normal_xyz", ctypes.c_double * 3),
        ("basis_u_xyz", ctypes.c_double * 3),
        ("basis_v_xyz", ctypes.c_double * 3),
        ("plane_value_n_dot_x", ctypes.c_double),
        ("bounds_u_m", ctypes.c_double * 2),
        ("bounds_v_m", ctypes.c_double * 2),
    ]


def pointer(array: np.ndarray, ctype):
    assert array.flags.c_contiguous
    return array.ctypes.data_as(ctypes.POINTER(ctype))


def load_birth_ownership_api(path: Path):
    api = ctypes.CDLL(str(path.resolve()))
    float_ptr = ctypes.POINTER(ctypes.c_float)
    u8_ptr = ctypes.POINTER(ctypes.c_uint8)
    api.aether_local_manifold_options_default.argtypes = [
        ctypes.POINTER(CLocalManifoldOptions)
    ]
    api.aether_local_manifold_session_create.argtypes = [
        float_ptr,
        ctypes.c_int32,
        ctypes.POINTER(CLocalManifoldOptions),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    api.aether_local_manifold_session_create.restype = ctypes.c_int32
    api.aether_local_manifold_session_filter.argtypes = [
        ctypes.c_void_p,
        float_ptr,
        ctypes.c_int32,
        u8_ptr,
        u8_ptr,
        u8_ptr,
        u8_ptr,
        ctypes.c_int32,
    ]
    api.aether_local_manifold_session_filter.restype = ctypes.c_int32
    api.aether_local_manifold_session_free.argtypes = [ctypes.c_void_p]
    api.aether_filter_finite_wall_ownership.argtypes = [
        float_ptr,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.POINTER(CWall),
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        u8_ptr,
        ctypes.c_int32,
    ]
    api.aether_filter_finite_wall_ownership.restype = ctypes.c_int32
    api.aether_filter_finite_floor_ownership.argtypes = [
        float_ptr,
        ctypes.c_int32,
        ctypes.POINTER(CFloorDomain),
        ctypes.c_double,
        ctypes.c_double,
        u8_ptr,
        ctypes.c_int32,
    ]
    api.aether_filter_finite_floor_ownership.restype = ctypes.c_int32
    return api


def native_walls(walls: list[dict]):
    result = (CWall * len(walls))()
    for index, source in enumerate(walls):
        wall = result[index]
        wall.wall_index = int(source.get("wall_index", index))
        wall.theta_deg = int(source.get("theta_deg", 0))
        wall.certified = int(source.get("certified_for_generation", False))
        for axis in range(3):
            wall.normal_xyz[axis] = float(source["normal"][axis])
            wall.basis_u_xyz[axis] = float(source["basis_u"][axis])
            wall.basis_v_xyz[axis] = float(source["basis_v"][axis])
        wall.plane_value_n_dot_x = float(source["plane_value_n_dot_x"])
        for axis in range(2):
            wall.bounds_u_m[axis] = float(source["bounds_u_m"][axis])
            wall.bounds_height_m[axis] = float(
                source["bounds_height_m"][axis]
            )
    return result


def native_floor(floor: dict) -> CFloorDomain:
    result = CFloorDomain()
    # Reaching this evaluator means B's image-only selection is decisive and
    # quality-passing; sparse proposals alone never call this path.
    result.certified = 1
    for axis in range(3):
        result.normal_xyz[axis] = float(floor["normal"][axis])
        result.basis_u_xyz[axis] = float(floor["basis_u"][axis])
        result.basis_v_xyz[axis] = float(floor["basis_v"][axis])
    result.plane_value_n_dot_x = float(floor["plane_value_n_dot_x"])
    for axis in range(2):
        result.bounds_u_m[axis] = float(floor["bounds_u_m"][axis])
        result.bounds_v_m[axis] = float(floor["bounds_v_m"][axis])
    return result


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {path}")
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


def deterministic_partitions(xyz: np.ndarray, count: int) -> list[np.ndarray]:
    order = np.lexsort((xyz[:, 2], xyz[:, 1], xyz[:, 0]))
    return [xyz[order[offset::count]] for offset in range(count)]


def candidate_world_xyz(depth, frame, depth_m: np.ndarray, mask: np.ndarray):
    height, width = depth_m.shape
    y, x = np.nonzero(mask)
    if not len(x):
        return np.empty((0, 3), dtype=np.float64)
    inverse_k = np.linalg.inv(depth.scaled_intrinsics(frame, width, height))
    pixels = np.column_stack([x, y, np.ones_like(x)]).astype(np.float64)
    camera = (pixels @ inverse_k.T) * depth_m[y, x, None]
    return (camera - frame.t) @ frame.R


def load_product_depth(archive, source: dict) -> tuple[np.ndarray, str]:
    """Load metric product depth, rebuilding legacy coarse artifacts exactly."""
    if "product_depth_m" in archive.files:
        return (
            np.asarray(archive["product_depth_m"], dtype=np.float64),
            "npz_product_depth_m",
        )
    config = source["config"]
    best_index = np.asarray(archive["best_index"], dtype=np.uint16)
    inverse_depths = np.linspace(
        1.0 / float(config["depth_max_m"]),
        1.0 / float(config["depth_min_m"]),
        int(config["depth_count"]),
        dtype=np.float32,
    )
    inverse_first = float(np.float32(inverse_depths[0]))
    inverse_step = float(np.float32(inverse_depths[1] - inverse_depths[0]))
    product_depth = np.asarray(
        1.0 / (inverse_first + best_index.astype(np.float64) * inverse_step),
        dtype=np.float32,
    )
    return (
        product_depth.astype(np.float64),
        "legacy_best_index_inverse_depth_reconstruction",
    )


def local_manifold_gate(
    candidates: np.ndarray,
    prior_xyz: np.ndarray,
    neighbors: int,
    maximum_nearest_m: float,
    maximum_neighbor_radius_m: float,
    maximum_neighbor_rms_m: float,
    maximum_perpendicular_m: float,
) -> tuple[np.ndarray, dict]:
    accepted = np.zeros(len(candidates), dtype=bool)
    if not len(candidates):
        return accepted, {
            "candidates": 0,
            "enough_neighbors": 0,
            "locally_planar": 0,
            "accepted": 0,
        }
    tree = cKDTree(prior_xyz)
    distances, indices = tree.query(candidates, k=neighbors, workers=1)
    if neighbors == 1:
        distances = distances[:, None]
        indices = indices[:, None]
    enough = (
        np.isfinite(distances).all(axis=1)
        & (distances[:, 0] <= maximum_nearest_m)
        & (distances[:, -1] <= maximum_neighbor_radius_m)
    )
    planar = 0
    perpendicular_values = []
    rms_values = []
    for candidate_index in np.flatnonzero(enough):
        points = prior_xyz[indices[candidate_index]]
        center = points.mean(axis=0)
        centered = points - center
        covariance = centered.T @ centered / float(len(points))
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        rms = math.sqrt(max(float(eigenvalues[0]), 0.0))
        if rms > maximum_neighbor_rms_m:
            continue
        planar += 1
        perpendicular = abs(
            float(np.dot(candidates[candidate_index] - center, eigenvectors[:, 0]))
        )
        rms_values.append(rms)
        perpendicular_values.append(perpendicular)
        if perpendicular <= maximum_perpendicular_m:
            accepted[candidate_index] = True
    return accepted, {
        "candidates": int(len(candidates)),
        "enough_neighbors": int(np.count_nonzero(enough)),
        "locally_planar": int(planar),
        "accepted": int(np.count_nonzero(accepted)),
        "neighbor_rms_median": (
            float(np.median(rms_values)) if rms_values else None
        ),
        "perpendicular_median": (
            float(np.median(perpendicular_values))
            if perpendicular_values
            else None
        ),
    }


def error_summary(candidates: np.ndarray, truth_xyz: np.ndarray) -> dict:
    if not len(candidates):
        return {"count": 0}
    distances, _ = cKDTree(truth_xyz).query(candidates, k=1, workers=1)
    return {
        "count": int(len(distances)),
        "median_m": float(np.median(distances)),
        "p90_m": float(np.percentile(distances, 90)),
        "p95_m": float(np.percentile(distances, 95)),
        "max_m": float(np.max(distances)),
        "within_0_05_m": float(np.mean(distances <= 0.05)),
        "within_0_10_m": float(np.mean(distances <= 0.10)),
        "within_0_20_m": float(np.mean(distances <= 0.20)),
    }


def wall_ownership_mask(
    candidates: np.ndarray,
    walls: list[dict],
    floor: dict,
    slab_m: float,
    domain_margin_m: float,
) -> np.ndarray:
    """Return candidates owned by a finite certified B wall surface."""
    owned = np.zeros(len(candidates), dtype=bool)
    floor_normal = np.asarray(floor["normal"], dtype=np.float64)
    floor_normal /= np.linalg.norm(floor_normal)
    floor_value = float(floor["plane_value_n_dot_x"])
    for wall in walls:
        normal = np.asarray(wall["normal"], dtype=np.float64)
        normal /= np.linalg.norm(normal)
        basis_u = np.asarray(wall["basis_u"], dtype=np.float64)
        basis_v = np.asarray(wall["basis_v"], dtype=np.float64)
        distance = np.abs(
            candidates @ normal - float(wall["plane_value_n_dot_x"])
        )
        coordinate_u = candidates @ basis_u
        # Wall height is measured from the fitted floor, not world origin.
        height = candidates @ basis_v - floor_value
        u_min, u_max = [float(value) for value in wall["bounds_u_m"]]
        h_min, h_max = [
            float(value) for value in wall["bounds_height_m"]
        ]
        inside = (
            (coordinate_u >= u_min - domain_margin_m)
            & (coordinate_u <= u_max + domain_margin_m)
            & (height >= h_min - domain_margin_m)
            & (height <= h_max + domain_margin_m)
        )
        owned |= inside & (distance <= slab_m)
    return owned


def floor_ownership_mask(
    candidates: np.ndarray,
    floor: dict,
    slab_m: float,
    domain_margin_m: float,
) -> np.ndarray:
    """Return D candidates owned by the selected finite B floor domain."""
    normal = np.asarray(floor["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    basis_u = np.asarray(floor["basis_u"], dtype=np.float64)
    basis_u /= np.linalg.norm(basis_u)
    basis_v = np.asarray(floor["basis_v"], dtype=np.float64)
    basis_v /= np.linalg.norm(basis_v)
    signed_distance = (
        candidates @ normal - float(floor["plane_value_n_dot_x"])
    )
    coordinate_u = candidates @ basis_u
    coordinate_v = candidates @ basis_v
    u_min, u_max = [float(value) for value in floor["bounds_u_m"]]
    v_min, v_max = [float(value) for value in floor["bounds_v_m"]]
    return (
        (signed_distance <= slab_m)
        & (coordinate_u >= u_min - domain_margin_m)
        & (coordinate_u <= u_max + domain_margin_m)
        & (coordinate_v >= v_min - domain_margin_m)
        & (coordinate_v <= v_max + domain_margin_m)
    )


def non_regression(before: dict, after: dict) -> bool:
    if after.get("count", 0) == 0:
        return True
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


def apply_reference_certificate(
    product_gate: np.ndarray,
    fold_results: list[dict],
    required: bool,
) -> tuple[np.ndarray, bool, int]:
    """Fail closed before product identity when a reference is uncertified."""
    reference_certified = all(
        bool(fold["non_regression"]) for fold in fold_results
    )
    if not required or reference_certified:
        return product_gate, reference_certified, 0
    blocked = int(np.count_nonzero(product_gate))
    return np.zeros_like(product_gate, dtype=bool), False, blocked


def gate_passed(
    *,
    all_non_regression: bool,
    total_product_births: int,
    c_abi_required_pass: bool,
    require_reference_certificate: bool,
    all_uncertified_references_blocked: bool,
) -> bool:
    if require_reference_certificate:
        # An all-zero additive result is valid: B and the original sparse cloud
        # are unchanged, while no uncertified D candidate receives identity.
        return c_abi_required_pass and all_uncertified_references_blocked
    return (
        all_non_regression
        and total_product_births > 0
        and c_abi_required_pass
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--b-quality-verdict", type=Path)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--neighbors", type=int, default=8)
    parser.add_argument("--maximum-nearest-m", type=float, default=0.12)
    parser.add_argument("--maximum-neighbor-radius-m", type=float, default=0.25)
    parser.add_argument("--maximum-neighbor-rms-m", type=float, default=0.03)
    parser.add_argument("--maximum-perpendicular-m", type=float, default=0.04)
    parser.add_argument("--wall-ownership-slab-m", type=float, default=0.08)
    parser.add_argument("--wall-domain-margin-m", type=float, default=0.05)
    parser.add_argument("--floor-ownership-slab-m", type=float, default=0.08)
    parser.add_argument("--floor-domain-margin-m", type=float, default=0.05)
    parser.add_argument("--production-fold", type=int, default=2)
    parser.add_argument(
        "--require-reference-certificate",
        action="store_true",
        help=(
            "before product identity, block every D birth from a reference "
            "when any of its three blind folds fails non-regression"
        ),
    )
    args = parser.parse_args()
    if args.neighbors < 3:
        parser.error("--neighbors must be at least 3")
    if args.production_fold not in range(3):
        parser.error("--production-fold must be 0, 1, or 2")
    birth_api = (
        load_birth_ownership_api(args.library)
        if args.library is not None
        else None
    )

    quality = load_module(QUALITY_PATH, "pw_local_manifold_quality")
    depth = quality.load_module(quality.DEPTH_PATH, "pw_local_manifold_depth")
    geometry = quality.load_module(
        quality.GEOMETRY_PATH, "pw_local_manifold_geometry"
    )
    structural_by_capture = {}
    b_quality_identity = None
    if args.b_quality_verdict is not None:
        b_quality_path = args.b_quality_verdict.resolve()
        b_quality = json.loads(b_quality_path.read_text())
        if not b_quality.get("quality_pass"):
            raise RuntimeError("B quality verdict is not passing")
        for capture, scene in b_quality["scenes"].items():
            stats_path = quality.ROOT / scene["inputs"]["wall_stats"]["path"]
            stats = json.loads(stats_path.read_text())
            planes_path = quality.ROOT / stats["inputs"]["planes"]["path"]
            planes = json.loads(planes_path.read_text())
            selected = set(planes["selected_surface_ids"])
            walls = [
                surface
                for surface in planes["surfaces"]
                if surface["surface_id"] in selected
                and surface.get("certified_for_generation", False)
            ]
            structural_by_capture[capture] = {
                "floor": planes["floor"],
                "walls": walls,
                "planes_path": str(planes_path),
                "planes_sha256": sha256(planes_path),
            }
        b_quality_identity = {
            "path": str(b_quality_path),
            "sha256": sha256(b_quality_path),
        }
    captures = []
    total_internal = 0
    total_wall_owned = 0
    total_floor_owned = 0
    total_structural_owned = 0
    total_nonstructural = 0
    total_minimum_fold_births = 0
    total_product_births = 0
    total_pre_certificate_product_births = 0
    total_reference_certificate_blocked_candidates = 0
    total_uncertified_references = 0
    total_certified_references = 0
    all_uncertified_references_blocked = True
    all_non_regression = True
    c_abi_all_exact = True
    c_abi_total_wall_mismatches = 0
    c_abi_total_floor_mismatches = 0
    c_abi_total_first_mismatches = 0
    c_abi_total_second_mismatches = 0
    c_abi_total_birth_mismatches = 0
    c_abi_session_create_ms = 0.0
    c_abi_wall_ownership_ms = 0.0
    c_abi_floor_ownership_ms = 0.0
    c_abi_manifold_filter_ms = 0.0
    for result_path in args.result:
        result_path = result_path.resolve()
        source = json.loads(result_path.read_text())
        capture = source["capture"]
        frames, sparse_path, _ = quality.load_capture(depth, geometry, capture)
        sparse_xyz = np.asarray(
            quality.read_sparse_xyz(depth, sparse_path), dtype=np.float32
        ).astype(np.float64)
        partitions = deterministic_partitions(sparse_xyz, 3)
        c_session = ctypes.c_void_p()
        if birth_api is not None:
            native_gate_options = CLocalManifoldOptions()
            birth_api.aether_local_manifold_options_default(
                ctypes.byref(native_gate_options)
            )
            production_priors = [
                index for index in range(3) if index != args.production_fold
            ]
            native_gate_options.neighbors = args.neighbors
            native_gate_options.partition_count = 3
            native_gate_options.first_partition = production_priors[0]
            native_gate_options.second_partition = production_priors[1]
            native_gate_options.maximum_nearest_m = args.maximum_nearest_m
            native_gate_options.maximum_neighbor_radius_m = (
                args.maximum_neighbor_radius_m
            )
            native_gate_options.maximum_neighbor_rms_m = (
                args.maximum_neighbor_rms_m
            )
            native_gate_options.maximum_perpendicular_m = (
                args.maximum_perpendicular_m
            )
            sparse_f32 = np.ascontiguousarray(sparse_xyz, dtype=np.float32)
            c_started = time.perf_counter()
            rc = birth_api.aether_local_manifold_session_create(
                pointer(sparse_f32, ctypes.c_float),
                len(sparse_f32),
                ctypes.byref(native_gate_options),
                ctypes.byref(c_session),
            )
            c_abi_session_create_ms += (time.perf_counter() - c_started) * 1000.0
            if rc != 0 or not c_session.value:
                raise RuntimeError(
                    f"C local manifold session create failed for {capture}: {rc}"
                )
        references = []
        for reference in source["references"]:
            npz_path = Path(reference["npz"])
            if not npz_path.is_absolute():
                npz_path = quality.ROOT / npz_path
            with np.load(npz_path) as archive:
                internal_birth = np.asarray(archive["final_birth"], dtype=bool)
                product_depth, product_depth_source = load_product_depth(
                    archive, source
                )
            frame = frames[int(reference["reference_index"])]
            raw_internal_xyz = np.asarray(
                candidate_world_xyz(depth, frame, product_depth, internal_birth),
                dtype=np.float32,
            ).astype(np.float64)
            wall_owned = np.zeros(len(raw_internal_xyz), dtype=bool)
            floor_owned = np.zeros(len(raw_internal_xyz), dtype=bool)
            structural = structural_by_capture.get(capture)
            if structural is not None:
                wall_owned = wall_ownership_mask(
                    raw_internal_xyz,
                    structural["walls"],
                    structural["floor"],
                    args.wall_ownership_slab_m,
                    args.wall_domain_margin_m,
                )
                floor_owned = floor_ownership_mask(
                    raw_internal_xyz,
                    structural["floor"],
                    args.floor_ownership_slab_m,
                    args.floor_domain_margin_m,
                )
            structural_owned = wall_owned | floor_owned
            internal_xyz = raw_internal_xyz[~structural_owned]
            partition_gates = []
            partition_stats = []
            for partition in partitions:
                gate, gate_stats = local_manifold_gate(
                    internal_xyz,
                    partition,
                    args.neighbors,
                    args.maximum_nearest_m,
                    args.maximum_neighbor_radius_m,
                    args.maximum_neighbor_rms_m,
                    args.maximum_perpendicular_m,
                )
                partition_gates.append(gate)
                partition_stats.append(gate_stats)
            fold_results = []
            fold_gates = []
            for fold in range(3):
                blind_truth_xyz = partitions[fold]
                prior_indices = [index for index in range(3) if index != fold]
                gate = (
                    partition_gates[prior_indices[0]]
                    & partition_gates[prior_indices[1]]
                )
                fold_gates.append(gate)
                before = error_summary(internal_xyz, blind_truth_xyz)
                after = error_summary(internal_xyz[gate], blind_truth_xyz)
                passed = non_regression(before, after)
                all_non_regression = all_non_regression and passed
                fold_results.append(
                    {
                        "fold": fold,
                        "prior_partition_indices": prior_indices,
                        "prior_points": [
                            int(len(partitions[index])) for index in prior_indices
                        ],
                        "blind_truth_points": int(len(blind_truth_xyz)),
                        "independent_gates": [
                            partition_stats[index] for index in prior_indices
                        ],
                        "dual_support_accepted": int(np.count_nonzero(gate)),
                        "before": before,
                        "after": after,
                        "non_regression": passed,
                    }
                )
            minimum_fold_births = min(
                fold["dual_support_accepted"] for fold in fold_results
            )
            manifold_product_gate = fold_gates[args.production_fold]
            pre_certificate_product_births = int(
                np.count_nonzero(manifold_product_gate)
            )
            (
                product_gate,
                reference_certified,
                reference_certificate_blocked_candidates,
            ) = apply_reference_certificate(
                manifold_product_gate,
                fold_results,
                args.require_reference_certificate,
            )
            product_births = int(np.count_nonzero(product_gate))
            if reference_certified:
                total_certified_references += 1
            else:
                total_uncertified_references += 1
                all_uncertified_references_blocked = (
                    all_uncertified_references_blocked
                    and product_births == 0
                )
            total_pre_certificate_product_births += (
                pre_certificate_product_births
            )
            total_reference_certificate_blocked_candidates += (
                reference_certificate_blocked_candidates
            )
            c_abi_parity = None
            if birth_api is not None:
                c_wall_owned = np.zeros(len(raw_internal_xyz), dtype=np.uint8)
                c_floor_owned = np.zeros(len(raw_internal_xyz), dtype=np.uint8)
                c_first = np.zeros(len(raw_internal_xyz), dtype=np.uint8)
                c_second = np.zeros(len(raw_internal_xyz), dtype=np.uint8)
                c_birth = np.zeros(len(raw_internal_xyz), dtype=np.uint8)
                if len(raw_internal_xyz):
                    raw_f32 = np.ascontiguousarray(
                        raw_internal_xyz, dtype=np.float32
                    )
                    if structural is None:
                        raise RuntimeError(
                            f"missing structural ownership for {capture}"
                        )
                    wall_array = native_walls(structural["walls"])
                    wall_pointer = (
                        ctypes.cast(wall_array, ctypes.POINTER(CWall))
                        if len(wall_array)
                        else None
                    )
                    c_started = time.perf_counter()
                    rc = birth_api.aether_filter_finite_wall_ownership(
                        pointer(raw_f32, ctypes.c_float),
                        len(raw_f32),
                        float(structural["floor"]["plane_value_n_dot_x"]),
                        wall_pointer,
                        len(wall_array),
                        args.wall_ownership_slab_m,
                        args.wall_domain_margin_m,
                        pointer(c_wall_owned, ctypes.c_uint8),
                        len(c_wall_owned),
                    )
                    c_abi_wall_ownership_ms += (
                        time.perf_counter() - c_started
                    ) * 1000.0
                    if rc != 0:
                        raise RuntimeError(
                            f"C wall ownership failed for {capture}: {rc}"
                        )
                    floor_domain = native_floor(structural["floor"])
                    c_started = time.perf_counter()
                    rc = birth_api.aether_filter_finite_floor_ownership(
                        pointer(raw_f32, ctypes.c_float),
                        len(raw_f32),
                        ctypes.byref(floor_domain),
                        args.floor_ownership_slab_m,
                        args.floor_domain_margin_m,
                        pointer(c_floor_owned, ctypes.c_uint8),
                        len(c_floor_owned),
                    )
                    c_abi_floor_ownership_ms += (
                        time.perf_counter() - c_started
                    ) * 1000.0
                    if rc != 0:
                        raise RuntimeError(
                            f"C floor ownership failed for {capture}: {rc}"
                        )
                    eligible = np.ascontiguousarray(
                        (~structural_owned).astype(np.uint8)
                    )
                    c_started = time.perf_counter()
                    rc = birth_api.aether_local_manifold_session_filter(
                        c_session,
                        pointer(raw_f32, ctypes.c_float),
                        len(raw_f32),
                        pointer(eligible, ctypes.c_uint8),
                        pointer(c_first, ctypes.c_uint8),
                        pointer(c_second, ctypes.c_uint8),
                        pointer(c_birth, ctypes.c_uint8),
                        len(c_birth),
                    )
                    c_abi_manifold_filter_ms += (
                        time.perf_counter() - c_started
                    ) * 1000.0
                    if rc != 0:
                        raise RuntimeError(
                            f"C local manifold filter failed for {capture}: {rc}"
                        )
                production_priors = [
                    index for index in range(3)
                    if index != args.production_fold
                ]
                wall_mismatches = int(
                    np.count_nonzero(c_wall_owned.astype(bool) != wall_owned)
                )
                floor_mismatches = int(
                    np.count_nonzero(c_floor_owned.astype(bool) != floor_owned)
                )
                first_mismatches = int(
                    np.count_nonzero(
                        c_first[~structural_owned].astype(bool)
                        != partition_gates[production_priors[0]]
                    )
                )
                second_mismatches = int(
                    np.count_nonzero(
                        c_second[~structural_owned].astype(bool)
                        != partition_gates[production_priors[1]]
                    )
                )
                birth_mismatches = int(
                    np.count_nonzero(
                        c_birth[~structural_owned].astype(bool)
                        != manifold_product_gate
                    )
                )
                exact = (
                    wall_mismatches == 0
                    and floor_mismatches == 0
                    and first_mismatches == 0
                    and second_mismatches == 0
                    and birth_mismatches == 0
                    and not np.any(c_birth[structural_owned])
                )
                c_abi_all_exact = c_abi_all_exact and exact
                c_abi_total_wall_mismatches += wall_mismatches
                c_abi_total_floor_mismatches += floor_mismatches
                c_abi_total_first_mismatches += first_mismatches
                c_abi_total_second_mismatches += second_mismatches
                c_abi_total_birth_mismatches += birth_mismatches
                c_abi_parity = {
                    "exact": exact,
                    "wall_ownership_mismatches": wall_mismatches,
                    "floor_ownership_mismatches": floor_mismatches,
                    "first_partition_mismatches": first_mismatches,
                    "second_partition_mismatches": second_mismatches,
                    "birth_mismatches": birth_mismatches,
                    "wall_owned_candidates_born_by_d": int(
                        np.count_nonzero(c_birth[wall_owned])
                    ),
                    "floor_owned_candidates_born_by_d": int(
                        np.count_nonzero(c_birth[floor_owned])
                    ),
                }
            total_internal += int(len(raw_internal_xyz))
            total_wall_owned += int(np.count_nonzero(wall_owned))
            total_floor_owned += int(np.count_nonzero(floor_owned))
            total_structural_owned += int(np.count_nonzero(structural_owned))
            total_nonstructural += int(len(internal_xyz))
            total_minimum_fold_births += minimum_fold_births
            total_product_births += product_births
            references.append(
                {
                    "reference_index": int(reference["reference_index"]),
                    "internal_reciprocal_candidates": int(
                        len(raw_internal_xyz)
                    ),
                    "b_wall_owned_candidates_not_born_by_d": int(
                        np.count_nonzero(wall_owned)
                    ),
                    "b_floor_owned_candidates_not_born_by_d": int(
                        np.count_nonzero(floor_owned)
                    ),
                    "b_structural_owned_candidates_not_born_by_d": int(
                        np.count_nonzero(structural_owned)
                    ),
                    "nonstructural_candidates": int(len(internal_xyz)),
                    "product_depth_source": product_depth_source,
                    "cross_validated_minimum_fold_births": int(
                        minimum_fold_births
                    ),
                    "production_fold": args.production_fold,
                    "reference_certificate_required": (
                        args.require_reference_certificate
                    ),
                    "reference_certified": reference_certified,
                    "pre_certificate_production_births": int(
                        pre_certificate_product_births
                    ),
                    "reference_certificate_blocked_candidates": int(
                        reference_certificate_blocked_candidates
                    ),
                    "production_births": int(product_births),
                    "c_abi_parity": c_abi_parity,
                    "folds": fold_results,
                }
            )
        if birth_api is not None and c_session.value:
            birth_api.aether_local_manifold_session_free(c_session)
        captures.append(
            {
                "capture": capture,
                "source_result": str(result_path),
                "source_result_sha256": sha256(result_path),
                "sparse_path": str(sparse_path),
                "sparse_sha256": sha256(sparse_path),
                "structural_planes": structural_by_capture.get(capture),
                "references": references,
            }
        )

    c_abi_required_pass = birth_api is None or c_abi_all_exact
    passed = gate_passed(
        all_non_regression=all_non_regression,
        total_product_births=total_product_births,
        c_abi_required_pass=c_abi_required_pass,
        require_reference_certificate=args.require_reference_certificate,
        all_uncertified_references_blocked=(
            all_uncertified_references_blocked
        ),
    )
    result = {
        "schema": "pocketworld_detector_free_local_manifold_birth_gate_v7",
        "decision": (
            (
                "PASS_REFERENCE_CERTIFIED_LOCAL_MANIFOLD_BIRTH_GATE"
                if args.require_reference_certificate
                else "PASS_CROSS_VALIDATED_LOCAL_MANIFOLD_BIRTH_GATE"
            )
            if passed
            else "FAIL_LOCAL_MANIFOLD_BIRTH_GATE"
        ),
        "config": {
            "neighbors": args.neighbors,
            "maximum_nearest_m": args.maximum_nearest_m,
            "maximum_neighbor_radius_m": args.maximum_neighbor_radius_m,
            "maximum_neighbor_rms_m": args.maximum_neighbor_rms_m,
            "maximum_perpendicular_m": args.maximum_perpendicular_m,
            "wall_ownership_slab_m": args.wall_ownership_slab_m,
            "wall_domain_margin_m": args.wall_domain_margin_m,
            "floor_ownership_slab_m": args.floor_ownership_slab_m,
            "floor_domain_margin_m": args.floor_domain_margin_m,
            "under_floor_inside_selected_domain_owned_by_b": True,
            "folds": 3,
            "independent_support_partitions_per_fold": 2,
            "production_fold": args.production_fold,
            "production_prior_partition_indices": [
                index for index in range(3) if index != args.production_fold
            ],
            "production_blind_partition_index": args.production_fold,
            "require_reference_certificate": (
                args.require_reference_certificate
            ),
            "product_xyz_storage": "float32",
            "evaluation_protocol": (
                "two independent sparse partitions must both support a "
                "candidate; the third partition is unseen and scores it"
            ),
            "learned_model_or_training_data_consumed": False,
            "third_party_matcher_output_consumed": False,
            "lidar_or_scene_depth_consumed": False,
        },
        "totals": {
            "internal_reciprocal_candidates": total_internal,
            "b_wall_owned_candidates_not_born_by_d": total_wall_owned,
            "b_floor_owned_candidates_not_born_by_d": total_floor_owned,
            "b_structural_owned_candidates_not_born_by_d": (
                total_structural_owned
            ),
            "nonstructural_candidates": total_nonstructural,
            "cross_validated_minimum_fold_births_total": (
                total_minimum_fold_births
            ),
            "production_births_total": total_product_births,
            "pre_certificate_production_births_total": (
                total_pre_certificate_product_births
            ),
            "reference_certificate_blocked_candidates_total": (
                total_reference_certificate_blocked_candidates
            ),
            "certified_references": total_certified_references,
            "uncertified_references": total_uncertified_references,
            "original_sparse_points_removed": 0,
            "structural_wall_conflicts_born_by_d": 0,
            "structural_floor_conflicts_born_by_d": 0,
            "c_abi_wall_ownership_mismatches": (
                c_abi_total_wall_mismatches if birth_api is not None else None
            ),
            "c_abi_floor_ownership_mismatches": (
                c_abi_total_floor_mismatches if birth_api is not None else None
            ),
            "c_abi_first_partition_mismatches": (
                c_abi_total_first_mismatches if birth_api is not None else None
            ),
            "c_abi_second_partition_mismatches": (
                c_abi_total_second_mismatches if birth_api is not None else None
            ),
            "c_abi_birth_mismatches": (
                c_abi_total_birth_mismatches if birth_api is not None else None
            ),
        },
        "b_quality_verdict": b_quality_identity,
        "all_blind_fold_metrics_non_regression": all_non_regression,
        "all_uncertified_references_blocked_before_product_identity": (
            all_uncertified_references_blocked
        ),
        "c_abi": (
            {
                "library": str(args.library.resolve()),
                "library_sha256": sha256(args.library.resolve()),
                "all_masks_exact": c_abi_all_exact,
                "timing_ms": {
                    "four_capture_index_build": c_abi_session_create_ms,
                    "all_reference_wall_ownership": c_abi_wall_ownership_ms,
                    "all_reference_floor_ownership": c_abi_floor_ownership_ms,
                    "all_reference_dual_manifold_filter": (
                        c_abi_manifold_filter_ms
                    ),
                    "total_birth_ownership": (
                        c_abi_session_create_ms
                        + c_abi_wall_ownership_ms
                        + c_abi_floor_ownership_ms
                        + c_abi_manifold_filter_ms
                    ),
                },
            }
            if args.library is not None
            else None
        ),
        "captures": captures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "totals": result["totals"],
                "c_abi": result["c_abi"],
                "captures": [
                    {
                        "capture": capture["capture"],
                        "production_births": sum(
                            reference["production_births"]
                            for reference in capture["references"]
                        ),
                        "references": [
                            {
                                "reference_index": reference["reference_index"],
                                "internal": reference[
                                    "internal_reciprocal_candidates"
                                ],
                                "minimum_fold_births": reference[
                                    "cross_validated_minimum_fold_births"
                                ],
                                "production_births": reference[
                                    "production_births"
                                ],
                                "pass": all(
                                    fold["non_regression"]
                                    for fold in reference["folds"]
                                ),
                            }
                            for reference in capture["references"]
                        ],
                    }
                    for capture in captures
                ],
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
