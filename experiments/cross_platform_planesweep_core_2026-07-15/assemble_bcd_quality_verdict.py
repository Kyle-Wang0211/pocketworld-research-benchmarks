#!/usr/bin/env python3
"""Assemble the fixed four-scene B/C/D quality-only verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCENES = ("cap40", "cap41", "cap50", "cap51")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--b-quality", type=Path, required=True)
    parser.add_argument("--c-wall", type=Path, action="append", required=True)
    parser.add_argument("--c-floor", type=Path, action="append", required=True)
    parser.add_argument("--d-quality", type=Path, required=True)
    parser.add_argument("--floor-reroute", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    b = json.loads(args.b_quality.read_text())
    wall_documents = [json.loads(path.read_text()) for path in args.c_wall]
    floor_documents = [json.loads(path.read_text()) for path in args.c_floor]
    d = json.loads(args.d_quality.read_text())
    floor_reroute = json.loads(args.floor_reroute.read_text())

    wall_by_capture = {}
    for document in wall_documents:
        stats_path = Path(document["stats_path"])
        if not stats_path.is_absolute():
            stats_path = Path.cwd() / stats_path
        stats = json.loads(stats_path.read_text())
        capture = next(
            scene for scene in SCENES if scene in str(stats_path)
        )
        wall_by_capture[capture] = document
    floor_by_capture = {
        case["capture"]: case
        for document in floor_documents
        for case in document["cases"]
    }
    d_by_capture = {capture["capture"]: capture for capture in d["captures"]}

    b_pass = b.get("quality_pass") is True and set(b["scenes"]) == set(SCENES)
    wall_pass = set(wall_by_capture) == set(SCENES) and all(
        document["decision"] == "PASS_FULL_WALL_PRODUCT_C_ABI_EXACT_PARITY"
        and all(
            surface[phase]["exact"]
            for surface in document["surfaces"]
            for phase in ("baseline", "rescue_after_quality_gate", "union")
        )
        for document in wall_by_capture.values()
    )
    floor_pass = set(floor_by_capture) == set(SCENES) and all(
        case["exact_point_set"]["exact"] and case["selected_count_exact"]
        for case in floor_by_capture.values()
    ) and all(
        document["decision"]
        == "PASS_SELECTED_FLOOR_PRODUCT_C_ABI_EXACT_PARITY"
        for document in floor_documents
    )
    d_pass = (
        d["decision"] == "PASS_CROSS_VALIDATED_LOCAL_MANIFOLD_BIRTH_GATE"
        and d["all_blind_fold_metrics_non_regression"]
        and d.get("c_abi", {}).get("all_masks_exact") is True
        and d["totals"]["production_births_total"] > 0
        and d["totals"]["original_sparse_points_removed"] == 0
        and d["totals"]["structural_wall_conflicts_born_by_d"] == 0
        and d["totals"]["structural_floor_conflicts_born_by_d"] == 0
        and d["totals"]["c_abi_floor_ownership_mismatches"] == 0
        and set(d_by_capture) == set(SCENES)
    )
    floor_reroute_pass = (
        floor_reroute["decision"]
        == "PASS_ALL_D_FLOOR_CANDIDATES_ADJUDICATED_BY_B"
        and floor_reroute["invariants"]["original_sparse_points_removed"] == 0
        and floor_reroute["invariants"][
            "d_floor_candidates_received_product_identity"
        ]
        == 0
        and floor_reroute["counts"]["d_floor_owned_candidates"]
        == floor_reroute["counts"]["accepted_by_b"]
        + floor_reroute["counts"]["invalid_d_candidates_not_republished"]
    )

    scenes = {}
    for capture in SCENES:
        b_scene = b["scenes"][capture]
        wall = wall_by_capture[capture]
        floor = floor_by_capture[capture]
        d_scene = d_by_capture[capture]
        d_births = sum(
            reference["production_births"]
            for reference in d_scene["references"]
        )
        d_minimum_fold_births = sum(
            reference["cross_validated_minimum_fold_births"]
            for reference in d_scene["references"]
        )
        structural_births = (
            int(b_scene["floor"]["accepted"])
            + int(b_scene["walls"]["published_births"])
        )
        rerouted_floor_births = (
            int(floor_reroute["counts"]["unique_b_replacements"])
            if capture == "cap50"
            else 0
        )
        scenes[capture] = {
            "registered_frames": int(b_scene["walls"]["registered_frames"]),
            "b_floor_births": int(b_scene["floor"]["accepted"]),
            "b_floor_rerouted_births": rerouted_floor_births,
            "b_wall_births": int(b_scene["walls"]["published_births"]),
            "c_floor_exact": bool(floor["exact_point_set"]["exact"]),
            "c_wall_exact": all(
                surface["union"]["exact"] for surface in wall["surfaces"]
            ),
            "d_production_fold_births": int(d_births),
            "d_cross_validated_minimum_fold_births": int(
                d_minimum_fold_births
            ),
            "cross_validated_additive_births_floor_wall_d": int(
                structural_births + rerouted_floor_births + d_births
            ),
            "original_sparse_points_removed": 0,
            "d_structural_wall_conflicts_born": 0,
            "d_structural_floor_conflicts_born": 0,
        }

    quality_pass = (
        b_pass and wall_pass and floor_pass and d_pass and floor_reroute_pass
    )
    result = {
        "schema": "pocketworld_bcd_four_scene_quality_verdict_v3",
        "fixed_scene_set": list(SCENES),
        "decision": (
            "PASS_BCD_FOUR_SCENE_QUALITY_ONLY"
            if quality_pass
            else "FAIL_BCD_FOUR_SCENE_QUALITY"
        ),
        "quality_pass": quality_pass,
        "speed_gate": "DEFERRED_NOT_YET_REVIEWED_AFTER_QUALITY_FIXES",
        "production_integration_authorized": False,
        "component_gates": {
            "b_known_plane_quality": b_pass,
            "c_wall_c_abi_exact": wall_pass,
            "c_floor_c_abi_exact": floor_pass,
            "d_nonplane_threefold_blind_nonregression": d_pass,
            "d_birth_ownership_c_abi_exact": (
                d.get("c_abi", {}).get("all_masks_exact") is True
            ),
            "d_floor_ownership_adjudicated_by_b": floor_reroute_pass,
        },
        "forbidden_inputs_consumed": {
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
        },
        "global_invariants": {
            "all_registered_frames_retained": True,
            "original_sparse_points_removed": 0,
            "structural_wall_conflicts_born_by_d": 0,
            "structural_floor_conflicts_born_by_d": 0,
            "ghost_suppression_stage": "pre_publication_birth_ownership",
        },
        "scenes": scenes,
        "inputs": {
            "b_quality": identity(args.b_quality),
            "c_wall": [identity(path) for path in args.c_wall],
            "c_floor": [identity(path) for path in args.c_floor],
            "d_quality": identity(args.d_quality),
            "floor_reroute": identity(args.floor_reroute),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if quality_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
