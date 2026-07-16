#!/usr/bin/env python3
"""Transfer D candidates inside a selected floor domain to B ownership.

Each current D birth is orthogonally moved to the unique selected floor plane
before it has a product identity. The replacement must independently pass the
same first-party image-only multi-view ZNCC, texture, parallax, and neighboring
depth competition used by B. No existing sparse or generated point is deleted.
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
ANALYSIS_PATH = EXPERIMENT / "analyze_floor_birth_ownership.py"
RUNNER_PATH = (
    EXPERIMENT.parent
    / "floor_plane_sweep_densifier_2026-07-13"
    / "fr_planesweep_wall_ceiling.py"
)


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


def sweep_config(runner, values: dict):
    return runner.SweepConfig(
        **{
            key: (
                tuple(value)
                if key == "depth_competition_offsets_m"
                else value
            )
            for key, value in values.items()
            if key in runner.SweepConfig.__dataclass_fields__
        }
    )


def score_floor_site(runner, point, floor, frames, cache, config):
    normal = np.asarray(floor["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    visible, head_on, _ = runner.project_centers(
        point[None, :], frames, normal, config
    )
    selected = runner.select_point_views(
        visible[:, 0], head_on[:, 0], config.max_views
    )
    images = cache.get_many(selected) if selected else {}
    offsets = runner.patch_offsets(floor, floor, config)
    center, reason = runner.score_point_hypothesis(
        point, offsets, frames, selected, images, config
    )
    if center is None:
        return None, reason
    alternatives = []
    for depth_offset in config.depth_competition_offsets_m:
        shifted = point + normal * depth_offset
        alt_visible, _, _ = runner.project_centers(
            shifted[None, :], frames, normal, config
        )
        alt_selected = [index for index in selected if alt_visible[index, 0]]
        alternative, _ = runner.score_point_hypothesis(
            shifted, offsets, frames, alt_selected, images, config
        )
        if alternative is not None:
            alternatives.append((alternative["views"], alternative["ncc"]))
    unique, depth_margin = runner.unique_depth_winner(
        center["views"], center["ncc"], alternatives, config.depth_ncc_margin
    )
    if not unique:
        return None, "ambiguous_depth"
    return {
        "views": int(center["views"]),
        "parallax_deg": float(center["parallax"]),
        "zncc_median": float(center["ncc"]),
        "candidate_views": int(center["candidate_views"]),
        "depth_ncc_margin_observed": depth_margin,
        "clique_frame_ids": [
            int(frames[index].frame_id)
            for index in center["clique_frame_indices"]
        ],
        "rgb_u8": [
            int(np.clip(np.rint(value), 0, 255))
            for value in center["color"]
        ],
    }, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--floor-selection", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--b-quality-verdict", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--floor-ownership-slab-m", type=float, default=0.08)
    parser.add_argument("--floor-domain-margin-m", type=float, default=0.05)
    parser.add_argument("--production-fold", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")

    analysis = load_module(ANALYSIS_PATH, "pw_floor_birth_reroute_analysis")
    gate = load_module(analysis.GATE_PATH, "pw_floor_birth_reroute_gate")
    quality = load_module(gate.QUALITY_PATH, "pw_floor_birth_reroute_quality")
    depth = quality.load_module(
        quality.DEPTH_PATH, "pw_floor_birth_reroute_depth"
    )
    geometry = quality.load_module(
        quality.GEOMETRY_PATH, "pw_floor_birth_reroute_geometry"
    )
    runner = load_module(RUNNER_PATH, "pw_floor_birth_reroute_runner")

    result_path = args.result.resolve()
    selection_path = args.floor_selection.resolve()
    photos_path = args.photos.resolve()
    b_path = args.b_quality_verdict.resolve()
    source = json.loads(result_path.read_text())
    selection = json.loads(selection_path.read_text())
    b_quality = json.loads(b_path.read_text())
    capture = source["capture"]
    scene = b_quality["scenes"][capture]
    if not scene["quality_pass"] or not selection["selection"]["decisive"]:
        raise RuntimeError("B floor selection is not quality-passing and decisive")
    winner_id = selection["selection"]["winner_surface_id"]
    winner = next(
        row for row in selection["candidates"]
        if row["proposal"]["surface_id"] == winner_id
    )
    floor = winner["proposal"]
    config = sweep_config(runner, selection["config"]["coarse"])
    root = quality.ROOT
    meta_path = root / selection["inputs"]["frame_meta"]["path"]
    ledger_path = root / selection["inputs"]["ledger"]["path"]
    frames = runner.load_frames(meta_path, ledger_path, photos_path)
    cache = runner.ImageCache(
        frames, max(config.image_cache_images, config.max_views)
    )

    loaded_frames, sparse_path, _ = quality.load_capture(
        depth, geometry, capture
    )
    sparse_xyz = np.asarray(
        quality.read_sparse_xyz(depth, sparse_path), dtype=np.float32
    ).astype(np.float64)
    partitions = gate.deterministic_partitions(sparse_xyz, 3)

    stats_path = root / scene["inputs"]["wall_stats"]["path"]
    stats = json.loads(stats_path.read_text())
    planes_path = root / stats["inputs"]["planes"]["path"]
    planes = json.loads(planes_path.read_text())
    selected_walls = set(planes["selected_surface_ids"])
    walls = [
        surface
        for surface in planes["surfaces"]
        if surface["surface_id"] in selected_walls
        and surface.get("certified_for_generation", False)
    ]

    candidates = []
    for reference in source["references"]:
        npz_path = Path(reference["npz"])
        if not npz_path.is_absolute():
            npz_path = root / npz_path
        with np.load(npz_path) as archive:
            internal_birth = np.asarray(archive["final_birth"], dtype=bool)
            product_depth, _ = gate.load_product_depth(archive, source)
        frame = loaded_frames[int(reference["reference_index"])]
        raw_xyz = np.asarray(
            gate.candidate_world_xyz(
                depth, frame, product_depth, internal_birth
            ),
            dtype=np.float32,
        ).astype(np.float64)
        wall_owned = gate.wall_ownership_mask(
            raw_xyz, walls, floor, 0.08, 0.05
        )
        nonwall = raw_xyz[~wall_owned]
        partition_gates = []
        for partition in partitions:
            accepted, _ = gate.local_manifold_gate(
                nonwall, partition, 8, 0.12, 0.25, 0.03, 0.02
            )
            partition_gates.append(accepted)
        priors = [index for index in range(3) if index != args.production_fold]
        product_gate = partition_gates[priors[0]] & partition_gates[priors[1]]
        floor_class = analysis.floor_domain_classification(
            nonwall,
            floor,
            args.floor_ownership_slab_m,
            args.floor_domain_margin_m,
        )
        for index in np.flatnonzero(product_gate & floor_class["owned"]):
            xyz = nonwall[index]
            signed = float(floor_class["signed_distance_m"][index])
            normal = np.asarray(floor["normal"], dtype=np.float64)
            normal /= np.linalg.norm(normal)
            replacement = xyz - signed * normal
            candidates.append({
                "reference_index": int(reference["reference_index"]),
                "source_xyz": xyz,
                "source_signed_floor_distance_m": signed,
                "replacement_xyz": replacement,
            })

    rows = []
    unique_accepted = []
    for candidate in candidates:
        replacement = candidate["replacement_xyz"]
        duplicate_index = next(
            (
                index for index, prior in enumerate(unique_accepted)
                if np.linalg.norm(replacement - prior["replacement_xyz_array"])
                < 0.02
            ),
            None,
        )
        evidence, rejection = score_floor_site(
            runner, replacement, floor, frames, cache, config
        )
        row = {
            "reference_index": candidate["reference_index"],
            "source_xyz": [float(value) for value in candidate["source_xyz"]],
            "source_signed_floor_distance_m": candidate[
                "source_signed_floor_distance_m"
            ],
            "replacement_xyz": [float(value) for value in replacement],
            "accepted_by_b": evidence is not None,
            "rejection": rejection,
            "evidence": evidence,
            "duplicate_of_prior_replacement": (
                duplicate_index
            ),
        }
        rows.append(row)
        if evidence is not None and duplicate_index is None:
            row["replacement_xyz_array"] = replacement
            unique_accepted.append(row)

    accepted_count = sum(row["accepted_by_b"] for row in rows)
    adjudicated = all(
        row["accepted_by_b"] or row["rejection"] is not None
        for row in rows
    )
    result = {
        "schema": "pocketworld_d_floor_birth_reroute_v1",
        "decision": (
            "PASS_ALL_D_FLOOR_CANDIDATES_ADJUDICATED_BY_B"
            if rows and adjudicated
            else "FAIL_D_FLOOR_OWNERSHIP_ADJUDICATION"
        ),
        "method": "prepublication_orthogonal_floor_transfer_then_b_multiview_birth",
        "inputs": {
            "d_result": {"path": str(result_path), "sha256": sha256(result_path)},
            "floor_selection": {
                "path": str(selection_path),
                "sha256": sha256(selection_path),
            },
            "b_quality_verdict": {"path": str(b_path), "sha256": sha256(b_path)},
        },
        "invariants": {
            "original_sparse_points_removed": 0,
            "d_floor_candidates_received_product_identity": 0,
            "original_b_floor_births_retained": int(
                scene["floor"]["accepted"]
            ),
            "replacement_plane_value_exact": True,
            "learned_matcher_consumed": False,
            "lidar_or_scene_depth_consumed": False,
        },
        "counts": {
            "d_floor_owned_candidates": len(rows),
            "accepted_by_b": accepted_count,
            "unique_b_replacements": len(unique_accepted),
            "rejected_by_b": len(rows) - accepted_count,
            "invalid_d_candidates_not_republished": len(rows) - accepted_count,
        },
        "image_cache": {
            "decoded_loads": cache.loads,
            "peak_bytes": cache.peak_bytes,
        },
        "candidates": [
            {key: value for key, value in row.items() if key != "replacement_xyz_array"}
            for row in rows
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "decision": result["decision"],
        "counts": result["counts"],
        "image_cache": result["image_cache"],
        "rejections": [row["rejection"] for row in rows if row["rejection"]],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
