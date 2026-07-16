#!/usr/bin/env python3
"""Measure D births that overlap the selected finite B floor domain.

This is a quality diagnostic, not a post-generation point filter. It replays
the current fixed production-fold local-manifold gate and classifies which D
candidates would have been denied point identity had the selected B floor
owned its finite domain before D publication.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


EXPERIMENT = Path(__file__).resolve().parent
GATE_PATH = EXPERIMENT / "evaluate_local_manifold_birth_gate.py"


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


def floor_domain_classification(
    candidates: np.ndarray,
    floor: dict,
    slab_m: float,
    domain_margin_m: float,
) -> dict[str, np.ndarray]:
    normal = np.asarray(floor["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    basis_u = np.asarray(floor["basis_u"], dtype=np.float64)
    basis_v = np.asarray(floor["basis_v"], dtype=np.float64)
    signed = candidates @ normal - float(floor["plane_value_n_dot_x"])
    u = candidates @ basis_u
    v = candidates @ basis_v
    u_min, u_max = [float(value) for value in floor["bounds_u_m"]]
    v_min, v_max = [float(value) for value in floor["bounds_v_m"]]
    inside = (
        (u >= u_min - domain_margin_m)
        & (u <= u_max + domain_margin_m)
        & (v >= v_min - domain_margin_m)
        & (v <= v_max + domain_margin_m)
    )
    return {
        "inside": inside,
        "near_band": inside & (np.abs(signed) <= slab_m),
        "below_band": inside & (signed < -slab_m),
        "owned": inside & (signed <= slab_m),
        "signed_distance_m": signed,
        "u": u,
        "v": v,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, action="append", required=True)
    parser.add_argument("--b-quality-verdict", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--floor-ownership-slab-m", type=float, default=0.08)
    parser.add_argument("--floor-domain-margin-m", type=float, default=0.05)
    parser.add_argument("--production-fold", type=int, default=2)
    parser.add_argument("--neighbors", type=int, default=8)
    parser.add_argument("--maximum-nearest-m", type=float, default=0.12)
    parser.add_argument("--maximum-neighbor-radius-m", type=float, default=0.25)
    parser.add_argument("--maximum-neighbor-rms-m", type=float, default=0.03)
    parser.add_argument("--maximum-perpendicular-m", type=float, default=0.02)
    parser.add_argument("--wall-ownership-slab-m", type=float, default=0.08)
    parser.add_argument("--wall-domain-margin-m", type=float, default=0.05)
    args = parser.parse_args()
    if args.production_fold not in range(3):
        parser.error("--production-fold must be 0, 1, or 2")

    gate = load_module(GATE_PATH, "pw_floor_ownership_gate")
    quality = load_module(gate.QUALITY_PATH, "pw_floor_ownership_quality")
    depth = quality.load_module(
        quality.DEPTH_PATH, "pw_floor_ownership_depth"
    )
    geometry = quality.load_module(
        quality.GEOMETRY_PATH, "pw_floor_ownership_geometry"
    )

    b_path = args.b_quality_verdict.resolve()
    b_quality = json.loads(b_path.read_text())
    if not b_quality.get("quality_pass"):
        raise RuntimeError("B quality verdict is not passing")

    structural = {}
    for capture, scene in b_quality["scenes"].items():
        stats_path = quality.ROOT / scene["inputs"]["wall_stats"]["path"]
        stats = json.loads(stats_path.read_text())
        planes_path = quality.ROOT / stats["inputs"]["planes"]["path"]
        planes = json.loads(planes_path.read_text())
        selected = set(planes["selected_surface_ids"])
        structural[capture] = {
            "floor": planes["floor"],
            "walls": [
                surface
                for surface in planes["surfaces"]
                if surface["surface_id"] in selected
                and surface.get("certified_for_generation", False)
            ],
        }

    captures = []
    totals = {
        "current_d_births": 0,
        "finite_floor_owned_current_d_births": 0,
        "near_floor_band_current_d_births": 0,
        "below_floor_band_current_d_births": 0,
        "remaining_nonstructural_d_births": 0,
        "original_sparse_points_removed": 0,
    }
    for result_path in args.result:
        result_path = result_path.resolve()
        source = json.loads(result_path.read_text())
        capture = source["capture"]
        frames, sparse_path, _ = quality.load_capture(
            depth, geometry, capture
        )
        sparse_xyz = np.asarray(
            quality.read_sparse_xyz(depth, sparse_path), dtype=np.float32
        ).astype(np.float64)
        partitions = gate.deterministic_partitions(sparse_xyz, 3)
        floor = structural[capture]["floor"]
        references = []
        for reference in source["references"]:
            npz_path = Path(reference["npz"])
            if not npz_path.is_absolute():
                npz_path = quality.ROOT / npz_path
            with np.load(npz_path) as archive:
                internal_birth = np.asarray(archive["final_birth"], dtype=bool)
                product_depth, _ = gate.load_product_depth(archive, source)
            frame = frames[int(reference["reference_index"])]
            raw_xyz = np.asarray(
                gate.candidate_world_xyz(
                    depth, frame, product_depth, internal_birth
                ),
                dtype=np.float32,
            ).astype(np.float64)
            wall_owned = gate.wall_ownership_mask(
                raw_xyz,
                structural[capture]["walls"],
                floor,
                args.wall_ownership_slab_m,
                args.wall_domain_margin_m,
            )
            candidates = raw_xyz[~wall_owned]
            partition_gates = []
            for partition in partitions:
                accepted, _ = gate.local_manifold_gate(
                    candidates,
                    partition,
                    args.neighbors,
                    args.maximum_nearest_m,
                    args.maximum_neighbor_radius_m,
                    args.maximum_neighbor_rms_m,
                    args.maximum_perpendicular_m,
                )
                partition_gates.append(accepted)
            priors = [
                index for index in range(3)
                if index != args.production_fold
            ]
            product_gate = (
                partition_gates[priors[0]] & partition_gates[priors[1]]
            )
            floor_class = floor_domain_classification(
                candidates,
                floor,
                args.floor_ownership_slab_m,
                args.floor_domain_margin_m,
            )
            current = int(np.count_nonzero(product_gate))
            owned_births = product_gate & floor_class["owned"]
            near_births = product_gate & floor_class["near_band"]
            below_births = product_gate & floor_class["below_band"]
            remaining = product_gate & ~floor_class["owned"]
            occupied_cells = {
                (
                    int(np.floor(floor_class["u"][index] / 0.05)),
                    int(np.floor(floor_class["v"][index] / 0.05)),
                )
                for index in np.flatnonzero(owned_births)
            }
            row = {
                "reference_index": int(reference["reference_index"]),
                "raw_internal_candidates": int(len(raw_xyz)),
                "wall_owned_candidates": int(np.count_nonzero(wall_owned)),
                "current_d_births": current,
                "finite_floor_owned_current_d_births": int(
                    np.count_nonzero(owned_births)
                ),
                "near_floor_band_current_d_births": int(
                    np.count_nonzero(near_births)
                ),
                "below_floor_band_current_d_births": int(
                    np.count_nonzero(below_births)
                ),
                "owned_floor_cells_5cm": len(occupied_cells),
                "remaining_nonstructural_d_births": int(
                    np.count_nonzero(remaining)
                ),
            }
            references.append(row)
            for key in totals:
                if key in row:
                    totals[key] += row[key]
        captures.append(
            {
                "capture": capture,
                "source_result": str(result_path),
                "source_result_sha256": sha256(result_path),
                "floor": floor,
                "references": references,
                "totals": {
                    key: sum(row.get(key, 0) for row in references)
                    for key in totals
                    if key != "original_sparse_points_removed"
                },
            }
        )

    result = {
        "schema": "pocketworld_d_finite_floor_ownership_diagnostic_v1",
        "decision": (
            "FLOOR_OWNERSHIP_REQUIRED"
            if totals["finite_floor_owned_current_d_births"] > 0
            else "NO_D_FLOOR_OWNERSHIP_OVERLAP"
        ),
        "config": {
            "floor_ownership_slab_m": args.floor_ownership_slab_m,
            "floor_domain_margin_m": args.floor_domain_margin_m,
            "below_selected_floor_within_domain_is_floor_owned": True,
            "production_fold": args.production_fold,
            "product_xyz_storage": "float32",
        },
        "inputs": {
            "b_quality_verdict": {
                "path": str(b_path),
                "sha256": sha256(b_path),
            }
        },
        "totals": totals,
        "captures": captures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "decision": result["decision"],
        "totals": totals,
        "captures": [
            {"capture": item["capture"], **item["totals"]}
            for item in captures
        ],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
