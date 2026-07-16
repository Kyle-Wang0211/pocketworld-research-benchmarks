#!/usr/bin/env python3
"""Select one image-certified owner for each competing wall-plane family."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/"
    "fr_planesweep_wall_ceiling.py"
)


def load_runner():
    spec = importlib.util.spec_from_file_location("aether_wall_owner_selector", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def angle_distance(left: float, right: float) -> float:
    difference = abs(left - right) % 180.0
    return min(difference, 180.0 - difference)


def candidate_score(metrics: dict) -> float:
    return int(metrics["accepted"]) * float(metrics["zncc_median"] or 0.0)


def is_incumbent(surface: dict) -> bool:
    return bool(surface.get("candidate_source_certified_for_generation", False))


def competing_families(surfaces: list[dict]) -> list[list[int]]:
    """Cluster challengers around fixed representatives without merging incumbents.

    An independently certified input wall is a distinct physical anchor.  Two
    such walls must never collapse merely because a deliberately broad proposal
    family radius overlaps both of them.  Uncertified proposals attach to the
    nearest compatible anchor; remaining proposals form fixed-representative
    families exactly as before.
    """
    incumbent_indices = [
        index for index, surface in enumerate(surfaces) if is_incumbent(surface)
    ]
    families: list[dict] = [
        {"representative": index, "members": [index]} for index in incumbent_indices
    ]
    challenger_indices = [
        index for index, surface in enumerate(surfaces) if not is_incumbent(surface)
    ]
    order = sorted(
        challenger_indices,
        key=lambda index: float(surfaces[index].get("score", 0.0)),
        reverse=True,
    )
    for index in order:
        surface = surfaces[index]
        assignments = []
        for family_index, family in enumerate(families):
            representative = surfaces[family["representative"]]
            angle = angle_distance(
                float(surface["theta_deg_in_horizontal_basis"]),
                float(representative["theta_deg_in_horizontal_basis"]),
            )
            value_difference = abs(
                float(surface["plane_value_n_dot_x"])
                - float(representative["plane_value_n_dot_x"])
            )
            if angle <= 15.0 and value_difference <= 0.75:
                assignments.append((angle, value_difference, family_index))
        if assignments:
            _, _, family_index = min(assignments)
            families[family_index]["members"].append(index)
        else:
            families.append({"representative": index, "members": [index]})
    return [sorted(family["members"]) for family in families]


def passes_birth_minimum(row: dict) -> bool:
    return (
        int(row["metrics"]["accepted"]) >= 8
        and int(row["metrics"]["coverage_cells_5cm"]) >= 8
    )


def dual_evidence_dominates(winner: dict, runner_up: dict | None) -> bool:
    """Resolve an open family only when image and sparse evidence agree.

    This is deliberately not a relaxed version of the primary 1.25x/+3 gate.
    It covers the numerical-boundary case where two accepted image births can
    move between otherwise equivalent candidate domains: the photometric
    result must still lead by >=1.20x/+2, both ZNCC summaries must not regress,
    and independent sparse support must lead by >=1.50x.
    """
    if runner_up is None or not passes_birth_minimum(winner):
        return False
    winner_metrics = winner["metrics"]
    runner_metrics = runner_up["metrics"]
    winner_surface = winner["surface"]
    runner_surface = runner_up["surface"]
    quality_fields = ("zncc_median", "zncc_p10")
    if any(
        winner_metrics.get(name) is None or runner_metrics.get(name) is None
        for name in quality_fields
    ):
        return False
    return (
        int(winner_metrics["accepted"])
        >= int(runner_metrics["accepted"]) + 2
        and int(winner_metrics["coverage_cells_5cm"])
        >= int(runner_metrics["coverage_cells_5cm"]) + 2
        and winner["winner_score"] >= runner_up["winner_score"] * 1.20
        and all(
            float(winner_metrics[name]) >= float(runner_metrics[name])
            for name in quality_fields
        )
        and float(winner_surface.get("score", 0.0))
        >= float(runner_surface.get("score", 0.0)) * 1.50
        and int(winner_surface.get("support_points_35mm", 0))
        >= int(runner_surface.get("support_points_35mm", 0))
    )


def decisively_beats(
    winner: dict,
    runner_up: dict | None,
    *,
    allow_dual_evidence: bool = False,
) -> bool:
    if not passes_birth_minimum(winner):
        return False
    if runner_up is None:
        return True
    primary = (
        winner["winner_score"] >= runner_up["winner_score"] * 1.25
        and int(winner["metrics"]["accepted"])
        >= int(runner_up["metrics"]["accepted"]) + 3
    )
    return primary or (
        allow_dual_evidence and dual_evidence_dominates(winner, runner_up)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame-meta", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--planes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runner = load_runner()
    planes = json.loads(args.planes.read_text())
    surfaces = [surface for surface in planes["surfaces"] if surface["kind"] == "wall"]
    if not surfaces:
        raise RuntimeError("no wall proposals")
    frames = runner.load_frames(args.frame_meta, args.ledger, args.photos)
    config = runner.SweepConfig(
        grid_m=0.05,
        patch_n=9,
        patch_radius_m=0.03,
        min_std=6.0,
        ncc_min=0.80,
        min_views=4,
        min_parallax_deg=10.0,
        max_views=10,
        max_graze_deg=72.0,
        tile_points=64,
        image_cache_images=10,
        depth_competition_offsets_m=(-0.10, -0.05, 0.05, 0.10),
        depth_ncc_margin=0.02,
    )
    started = time.perf_counter()
    rows = []
    for surface in surfaces:
        _, _, _, metrics = runner.sweep_surface(
            surface, planes["floor"], frames, config, 0.0
        )
        rows.append(
            {
                "surface": surface,
                "metrics": metrics,
                "winner_score": candidate_score(metrics),
            }
        )

    family_results = []
    selected_ids = []
    for family_index, indices in enumerate(competing_families(surfaces)):
        ranking = sorted(
            indices,
            key=lambda index: (
                rows[index]["winner_score"],
                rows[index]["metrics"]["accepted"],
            ),
            reverse=True,
        )
        evidence_winner = rows[ranking[0]]
        evidence_runner_up = rows[ranking[1]] if len(ranking) > 1 else None
        incumbent_rows = [rows[index] for index in indices if is_incumbent(surfaces[index])]
        incumbent = max(
            (row for row in incumbent_rows if passes_birth_minimum(row)),
            key=lambda row: row["winner_score"],
            default=None,
        )
        if incumbent is None:
            winner = evidence_winner
            primary_decisive = decisively_beats(winner, evidence_runner_up)
            dual_decisive = (
                not primary_decisive
                and dual_evidence_dominates(winner, evidence_runner_up)
            )
            decisive = primary_decisive or dual_decisive
            decision = (
                "decisive_open_family_winner"
                if primary_decisive
                else (
                    "dual_evidence_dominant_open_family_winner"
                    if dual_decisive
                    else "fail_closed"
                )
            )
        elif evidence_winner is incumbent:
            winner = incumbent
            decisive = True
            decision = "reverified_incumbent_retained"
        elif decisively_beats(evidence_winner, incumbent):
            winner = evidence_winner
            decisive = True
            decision = "decisive_challenger_replacement"
        else:
            winner = incumbent
            decisive = True
            decision = "ambiguous_challenger_rejected_incumbent_retained"
        winner_id = winner["surface"]["surface_id"] if decisive else None
        if winner_id:
            selected_ids.append(winner_id)
        family_results.append(
            {
                "family_index": family_index,
                "candidate_surface_ids": [surfaces[index]["surface_id"] for index in indices],
                "winner_surface_id": winner_id,
                "decisive": decisive,
                "decision": decision,
                "incumbent_surface_id": (
                    incumbent["surface"]["surface_id"] if incumbent else None
                ),
                "evidence_winner_surface_id": evidence_winner["surface"]["surface_id"],
                "winner_accepted": int(winner["metrics"]["accepted"]),
                "runner_up_accepted": (
                    int(evidence_runner_up["metrics"]["accepted"])
                    if evidence_runner_up
                    else 0
                ),
                "winner_score": winner["winner_score"],
                "runner_up_score": (
                    evidence_runner_up["winner_score"] if evidence_runner_up else None
                ),
            }
        )

    selected_surfaces = [
        {**surface, "certified_for_generation": True, "proposal_only": False}
        for surface in surfaces
        if surface["surface_id"] in selected_ids
    ]
    result = {
        "schema": "aether_image_certified_wall_owner_selector_v4",
        "method": (
            "incumbent_anchored_candidate_union_then_family_unique_multiview_"
            "owner_with_dual_evidence_boundary_stability"
        ),
        "forbidden_inputs_consumed": {
            "reference_plane": False,
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
        },
        "ownership_policy": (
            "each reverified incumbent anchors a distinct family; an uncertified "
            "challenger replaces it only with decisive current evidence; an open "
            "family may also resolve when photometric and independent sparse "
            "evidence both dominate; otherwise at most one decisive plane per "
            "open family may own point birth"
        ),
        "inputs": {
            "frame_meta": {"path": str(args.frame_meta), "sha256": sha256(args.frame_meta)},
            "ledger": {"path": str(args.ledger), "sha256": sha256(args.ledger)},
            "planes": {"path": str(args.planes), "sha256": sha256(args.planes)},
            "photo_count": len(frames),
        },
        "config": {
            "sweep": config.__dict__,
            "family_maximum_angle_deg": 15.0,
            "family_maximum_plane_value_difference_m": 0.75,
            "minimum_accepted": 8,
            "minimum_coverage_cells": 8,
            "minimum_winner_score_ratio": 1.25,
            "minimum_accepted_lead": 3,
            "dual_evidence_minimum_winner_score_ratio": 1.20,
            "dual_evidence_minimum_accepted_lead": 2,
            "dual_evidence_minimum_coverage_lead": 2,
            "dual_evidence_minimum_sparse_score_ratio": 1.50,
            "dual_evidence_requires_zncc_median_and_p10_nonregression": True,
            "dual_evidence_requires_sparse_support_nonregression": True,
        },
        "floor": planes["floor"],
        "candidate_count": len(surfaces),
        "candidates": rows,
        "families": family_results,
        "selected_surface_ids": selected_ids,
        "surfaces": selected_surfaces,
        "elapsed_s": time.perf_counter() - started,
        "verdict": "PASS_DECISIVE_WALL_OWNERS" if selected_ids else "FAIL_CLOSED_NO_OWNER",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
