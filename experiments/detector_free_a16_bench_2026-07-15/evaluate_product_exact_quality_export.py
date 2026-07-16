#!/usr/bin/env python3
"""Independently score product-exact D rows against three blind SfM folds.

The Dart exporter records the exact float32 candidate XYZ and product ABI masks
for every 128x72 pixel.  This evaluator recomputes structural ownership and the
three-fold local-manifold certificate in Python, reports every blind metric,
and requires bit-exact parity with the product masks before returning success.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
GATE_PATH = HERE / "evaluate_local_manifold_birth_gate.py"


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


def load_rows(path: Path) -> np.ndarray:
    dtype = np.dtype(
        [
            ("xyz", "<f4", (3,)),
            ("eligible", "u1"),
            ("floor", "u1"),
            ("wall", "u1"),
            ("structural", "u1"),
            ("born", "u1"),
        ],
        align=False,
    )
    if dtype.itemsize != 17:
        raise RuntimeError(f"unexpected row stride {dtype.itemsize}")
    return np.fromfile(path, dtype=dtype)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--planes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--jpeg-backend",
        choices=["stb_diagnostic", "libjpeg_turbo_product"],
        default="stb_diagnostic",
    )
    args = parser.parse_args()

    gate = load_module(GATE_PATH, "pw_product_exact_gate")
    manifest_path = args.manifest.resolve()
    planes_path = args.planes.resolve()
    manifest = json.loads(manifest_path.read_text())
    planes = json.loads(planes_path.read_text())
    selected = set(planes["selected_surface_ids"])
    walls = [
        surface
        for surface in planes["surfaces"]
        if surface["surface_id"] in selected
        and surface.get("certified_for_generation", False)
        and surface.get("kind") == "wall"
    ]
    floor = planes["floor"]

    sparse_source = Path(manifest["metric_sparse"]["path"])
    sparse = np.fromfile(sparse_source, dtype="<f4")
    if sparse.size % 3:
        raise RuntimeError("metric sparse XYZ is malformed")
    sparse_xyz = sparse.reshape(-1, 3).astype(np.float64)
    partitions = gate.deterministic_partitions(sparse_xyz, 3)

    config = {
        "neighbors": 8,
        "maximum_nearest_m": 0.12,
        "maximum_neighbor_radius_m": 0.25,
        "maximum_neighbor_rms_m": 0.03,
        "maximum_perpendicular_m": 0.02,
        "floor_ownership_slab_m": 0.08,
        "floor_domain_margin_m": 0.05,
        "wall_ownership_slab_m": 0.08,
        "wall_domain_margin_m": 0.05,
        "production_fold": 2,
    }
    totals = {
        "references": 0,
        "reciprocal_eligible": 0,
        "floor_owned": 0,
        "wall_owned": 0,
        "structural_owned": 0,
        "pre_certificate_births": 0,
        "blocked_births": 0,
        "product_births": 0,
        "b_structural_conflicts_born_by_d": 0,
        "floor_mask_mismatches": 0,
        "wall_mask_mismatches": 0,
        "structural_mask_mismatches": 0,
        "product_birth_mask_mismatches": 0,
        "failed_fold_mask_mismatches": 0,
    }
    references = []
    for source in manifest["references"]:
        row_path = Path(source["candidate_file"]["path"])
        rows = load_rows(row_path)
        expected_count = int(source["width"]) * int(source["height"])
        if len(rows) != expected_count:
            raise RuntimeError(
                f"reference {source['reference_frame_id']} row count mismatch"
            )
        xyz = rows["xyz"].astype(np.float64)
        eligible = rows["eligible"].astype(bool)
        product_floor = rows["floor"].astype(bool)
        product_wall = rows["wall"].astype(bool)
        product_structural = rows["structural"].astype(bool)
        product_born = rows["born"].astype(bool)

        py_floor = gate.floor_ownership_mask(
            xyz,
            floor,
            config["floor_ownership_slab_m"],
            config["floor_domain_margin_m"],
        )
        py_wall = gate.wall_ownership_mask(
            xyz,
            walls,
            floor,
            config["wall_ownership_slab_m"],
            config["wall_domain_margin_m"],
        )
        py_structural = py_floor | py_wall
        internal_indices = np.flatnonzero(eligible & ~py_structural)
        internal_xyz = xyz[internal_indices]

        partition_gates = []
        partition_stats = []
        for partition in partitions:
            supported, stats = gate.local_manifold_gate(
                internal_xyz,
                partition,
                config["neighbors"],
                config["maximum_nearest_m"],
                config["maximum_neighbor_radius_m"],
                config["maximum_neighbor_rms_m"],
                config["maximum_perpendicular_m"],
            )
            partition_gates.append(supported)
            partition_stats.append(stats)

        folds = []
        failed_fold_mask = 0
        for fold in range(3):
            priors = [(fold + 1) % 3, (fold + 2) % 3]
            fold_gate = partition_gates[priors[0]] & partition_gates[priors[1]]
            before = gate.error_summary(internal_xyz, partitions[fold])
            after = gate.error_summary(internal_xyz[fold_gate], partitions[fold])
            non_regression = gate.non_regression(before, after)
            if not non_regression:
                failed_fold_mask |= 1 << fold
            folds.append(
                {
                    "fold": fold,
                    "prior_partition_indices": priors,
                    "blind_truth_points": int(len(partitions[fold])),
                    "independent_support": [
                        partition_stats[index] for index in priors
                    ],
                    "before": before,
                    "after": after,
                    "non_regression": non_regression,
                }
            )

        production_priors = [0, 1]
        production_internal = (
            partition_gates[production_priors[0]]
            & partition_gates[production_priors[1]]
        )
        py_born = np.zeros(len(rows), dtype=bool)
        pre_certificate = int(np.count_nonzero(production_internal))
        blocked = pre_certificate if failed_fold_mask else 0
        if failed_fold_mask == 0:
            py_born[internal_indices[production_internal]] = True

        floor_mismatches = int(np.count_nonzero(py_floor != product_floor))
        wall_mismatches = int(np.count_nonzero(py_wall != product_wall))
        structural_mismatches = int(
            np.count_nonzero(py_structural != product_structural)
        )
        birth_mismatches = int(np.count_nonzero(py_born != product_born))
        fold_mask_mismatch = int(failed_fold_mask != source["failed_fold_mask"])
        b_conflicts = int(np.count_nonzero(product_born & product_structural))

        totals["references"] += 1
        totals["reciprocal_eligible"] += int(np.count_nonzero(eligible))
        totals["floor_owned"] += int(np.count_nonzero(product_floor))
        totals["wall_owned"] += int(np.count_nonzero(product_wall))
        totals["structural_owned"] += int(np.count_nonzero(product_structural))
        totals["pre_certificate_births"] += pre_certificate
        totals["blocked_births"] += blocked
        totals["product_births"] += int(np.count_nonzero(product_born))
        totals["b_structural_conflicts_born_by_d"] += b_conflicts
        totals["floor_mask_mismatches"] += floor_mismatches
        totals["wall_mask_mismatches"] += wall_mismatches
        totals["structural_mask_mismatches"] += structural_mismatches
        totals["product_birth_mask_mismatches"] += birth_mismatches
        totals["failed_fold_mask_mismatches"] += fold_mask_mismatch
        references.append(
            {
                "reference_frame_id": source["reference_frame_id"],
                "row_file": {
                    "path": str(row_path),
                    "sha256": sha256(row_path),
                },
                "reciprocal_eligible": int(np.count_nonzero(eligible)),
                "nonstructural_eligible": int(len(internal_xyz)),
                "failed_fold_mask_product": source["failed_fold_mask"],
                "failed_fold_mask_python": failed_fold_mask,
                "pre_certificate_births": pre_certificate,
                "blocked_births": blocked,
                "product_births": int(np.count_nonzero(product_born)),
                "b_structural_conflicts_born_by_d": b_conflicts,
                "parity": {
                    "floor_mask_mismatches": floor_mismatches,
                    "wall_mask_mismatches": wall_mismatches,
                    "structural_mask_mismatches": structural_mismatches,
                    "product_birth_mask_mismatches": birth_mismatches,
                    "failed_fold_mask_mismatch": bool(fold_mask_mismatch),
                },
                "folds": folds,
            }
        )

    exact = (
        manifest["scheduler_parity"]["exact"]
        and totals["floor_mask_mismatches"] == 0
        and totals["wall_mask_mismatches"] == 0
        and totals["structural_mask_mismatches"] == 0
        and totals["product_birth_mask_mismatches"] == 0
        and totals["failed_fold_mask_mismatches"] == 0
        and totals["b_structural_conflicts_born_by_d"] == 0
    )
    diagnostic_only = args.jpeg_backend != "libjpeg_turbo_product"
    result = {
        "schema": "pocketworld_product_exact_d_blind_quality_v1",
        "decision": (
            (
                "PASS_PRODUCT_EXACT_D_BLIND_QUALITY_AND_MASK_PARITY"
                if diagnostic_only
                else "PASS_FINAL_PRODUCT_EXACT_D_BLIND_QUALITY_AND_MASK_PARITY"
            )
            if exact
            else "FAIL_PRODUCT_EXACT_D_BLIND_QUALITY_OR_MASK_PARITY"
        ),
        "jpeg_backend": args.jpeg_backend,
        "diagnostic_only": diagnostic_only,
        "diagnostic_reason": (
            "candidate JPEG preprocessing backend is STB; repeat unchanged "
            "with the product libjpeg-turbo ABI before a final certificate"
            if diagnostic_only
            else None
        ),
        "inputs": {
            "manifest": {
                "path": str(manifest_path),
                "sha256": sha256(manifest_path),
            },
            "metric_sparse": {
                "path": str(sparse_source),
                "sha256": sha256(sparse_source),
                "points": int(len(sparse_xyz)),
            },
            "structural_planes": {
                "path": str(planes_path),
                "sha256": sha256(planes_path),
            },
        },
        "config": config,
        "totals": totals,
        "all_masks_exact": exact,
        "original_sparse_points_removed": 0,
        "references": references,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "diagnostic_only": diagnostic_only,
                "totals": totals,
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
