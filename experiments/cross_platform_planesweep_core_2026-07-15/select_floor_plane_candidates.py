#!/usr/bin/env python3
"""Select one physical floor from sparse parallel-layer proposals.

The selector is deliberately split into two stages:

1. A cheap sparse proposal stage enumerates gravity-horizontal peaks that lie
   below the complete camera trajectory.  Proposals do not create product
   points and may include ghost layers.
2. A coarse 10 cm image sweep applies the same multi-view texture, all-pairs
   ZNCC, parallax, and unique-depth rules as the full 5 cm structural sweep.
   It selects a single floor only when the winner is decisively stronger.

No learned matcher, LiDAR, sceneDepth, ARKit plane anchor, or reference plane is
used for selection.  An optional reference JSON is read only after selection to
score the experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/"
    "fr_planesweep_wall_ceiling.py"
)


def load_runner():
    spec = importlib.util.spec_from_file_location("aether_floor_candidate_runner", RUNNER_PATH)
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


def coverage_cells(points: np.ndarray, cell_m: float = 0.10) -> int:
    cells = np.floor(points[:, [0, 2]] / cell_m).astype(np.int64)
    return int(len(np.unique(cells, axis=0)))


def refine_plane(points: np.ndarray, keep: np.ndarray, anchor: float):
    normal = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    offset = -anchor
    for _ in range(3):
        mask = keep & (np.abs(points @ normal + offset) < 0.01)
        if int(mask.sum()) < 20:
            return None
        chosen = points[mask]
        centroid = chosen.mean(axis=0)
        _, _, vh = np.linalg.svd(chosen - centroid, full_matrices=False)
        normal = vh[-1]
        if normal[1] < 0:
            normal = -normal
        normal /= np.linalg.norm(normal)
        offset = -float(normal @ centroid)
    value = -offset
    residual = points @ normal - value
    support_mask = np.abs(residual) <= 0.02
    support = points[support_mask]
    if len(support) < 100:
        return None
    cells = coverage_cells(support)
    tilt = math.degrees(math.acos(float(np.clip(normal[1], -1.0, 1.0))))
    if cells < 30 or tilt > 12.0:
        return None
    basis_u = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    basis_u -= float(basis_u @ normal) * normal
    basis_u /= np.linalg.norm(basis_u)
    basis_v = np.cross(normal, basis_u)
    basis_v /= np.linalg.norm(basis_v)
    u = support @ basis_u
    v = support @ basis_v
    return {
        "surface_id": "",
        "kind": "floor",
        "normal": normal.tolist(),
        "plane_value_n_dot_x": value,
        "basis_u": basis_u.tolist(),
        "basis_v": basis_v.tolist(),
        "bounds_u_m": (np.percentile(u, [2, 98]) + [-0.05, 0.05]).tolist(),
        "bounds_v_m": (np.percentile(v, [2, 98]) + [-0.05, 0.05]).tolist(),
        "support_points_20mm": int(len(support)),
        "coverage_cells_10cm": cells,
        "rms_error_m": float(np.sqrt(np.mean(residual[support_mask] ** 2))),
        "tilt_deg": tilt,
        "certified_for_generation": False,
        "proposal_only": True,
        "prior_score": float(len(support) * math.sqrt(cells)),
    }


def propose_floors(
    points: np.ndarray,
    minimum_camera_y: float,
    maximum_candidates: int,
) -> list[dict]:
    low = np.percentile(points, 2, axis=0)
    high = np.percentile(points, 98, axis=0)
    lower_bound = low - 0.5 * (high - low)
    upper_bound = high + 0.5 * (high - low)
    keep = np.all((points >= lower_bound) & (points <= upper_bound), axis=1)
    heights = points[keep, 1]
    minimum = float(heights.min())
    maximum = min(
        float(heights.max()),
        float(low[1] + 0.25 * (high[1] - low[1])),
        minimum_camera_y - 0.05,
    )
    if maximum <= minimum:
        return []
    step = 0.02
    edges = np.arange(minimum, maximum + step * 1.001, step)
    counts, _ = np.histogram(heights, bins=edges)
    peaks = []
    for index, count in enumerate(counts):
        left = counts[index - 1] if index else -1
        right = counts[index + 1] if index + 1 < len(counts) else -1
        if count < 20 or count < left or count < right:
            continue
        center = float((edges[index] + edges[index + 1]) * 0.5)
        proposal = refine_plane(points, keep, center)
        if proposal is not None:
            peaks.append(proposal)
    # Adjacent histogram bins can converge to the same physical plane.  Keep
    # the stronger one within 3 cm; preserve 5 cm ghost layers as competitors.
    peaks.sort(key=lambda row: row["prior_score"], reverse=True)
    distinct = []
    for proposal in peaks:
        value = float(proposal["plane_value_n_dot_x"])
        if any(abs(value - float(row["plane_value_n_dot_x"])) < 0.03 for row in distinct):
            continue
        distinct.append(proposal)
    distinct = distinct[:maximum_candidates]
    distinct.sort(key=lambda row: row["plane_value_n_dot_x"])
    for index, proposal in enumerate(distinct):
        proposal["surface_id"] = f"floor_proposal_{index}"
    return distinct


def winner_score(metrics: dict) -> float:
    accepted = int(metrics["accepted"])
    # A null observed margin means every parallel competitor failed its own
    # photometric gate, not that the center had zero advantage.  Rank the
    # coarse selector by independently certified site count and median ZNCC;
    # unique-depth remains a hard per-site gate inside sweep_surface.
    median_ncc = metrics.get("zncc_median")
    return accepted * max(float(median_ncc or 0.0), 0.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric-cloud", type=Path, required=True)
    parser.add_argument("--frame-meta", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-planes", type=Path)
    parser.add_argument("--maximum-candidates", type=int, default=16)
    args = parser.parse_args()

    runner = load_runner()
    frames = runner.load_frames(args.frame_meta, args.ledger, args.photos)
    points = np.asarray(np.load(args.metric_cloud)["xyz"], dtype=np.float64)
    proposals = propose_floors(
        points,
        min(float(frame.C[1]) for frame in frames),
        args.maximum_candidates,
    )
    if not proposals:
        raise RuntimeError("sparse proposal stage produced no floor candidates")
    config = runner.SweepConfig(
        grid_m=0.10,
        patch_n=7,
        patch_radius_m=0.015,
        min_std=6.0,
        ncc_min=0.70,
        min_views=3,
        min_parallax_deg=5.0,
        max_views=10,
        max_graze_deg=72.0,
        tile_points=128,
        image_cache_images=10,
        depth_competition_offsets_m=(-0.05, 0.05),
        depth_ncc_margin=0.02,
    )
    rows = []
    started = time.perf_counter()
    for proposal in proposals:
        _, _, _, metrics = runner.sweep_surface(
            proposal,
            proposal,
            frames,
            config,
            offset_m=0.0,
        )
        rows.append(
            {
                "proposal": proposal,
                "coarse_sweep": metrics,
                "winner_score": winner_score(metrics),
            }
        )
    ranking = sorted(
        range(len(rows)),
        key=lambda index: (
            rows[index]["winner_score"],
            rows[index]["coarse_sweep"]["accepted"],
        ),
        reverse=True,
    )
    winner = rows[ranking[0]]
    runner_up = rows[ranking[1]] if len(ranking) > 1 else None
    accepted = int(winner["coarse_sweep"]["accepted"])
    second_accepted = int(runner_up["coarse_sweep"]["accepted"]) if runner_up else 0
    selection_stage = "coarse_10cm"
    selected_score = winner["winner_score"]
    runner_up_score = runner_up["winner_score"] if runner_up else None
    decisive = (
        accepted >= 12
        and int(winner["coarse_sweep"]["coverage_cells_5cm"]) >= 12
        and winner["winner_score"] >= (runner_up["winner_score"] * 1.25 if runner_up else 0.0)
        and accepted >= second_accepted + 5
    )
    fine_config = None
    if not decisive and runner_up is None:
        # A sole sparse proposal still has no right to win by default.  Increase
        # only the sampling density and require twelve independently certified
        # image sites; all per-site quality and unique-depth gates stay fixed.
        fine_config = replace(config, grid_m=0.05)
        proposal = winner["proposal"]
        _, _, _, metrics = runner.sweep_surface(
            proposal,
            proposal,
            frames,
            fine_config,
            offset_m=0.0,
        )
        winner["fine_sweep"] = metrics
        winner["fine_winner_score"] = winner_score(metrics)
        accepted = int(metrics["accepted"])
        second_accepted = 0
        selected_score = winner["fine_winner_score"]
        runner_up_score = None
        selection_stage = "fine_5cm_single"
        decisive = (
            accepted >= 12
            and int(metrics["coverage_cells_5cm"]) >= 12
        )
    elif not decisive and runner_up is not None:
        # Ambiguous coarse selection refines only its top two candidates.  It
        # never expands the proposal population or relaxes a birth threshold.
        fine_config = replace(config, grid_m=0.05)
        top_two = ranking[:2]
        for index in top_two:
            proposal = rows[index]["proposal"]
            _, _, _, metrics = runner.sweep_surface(
                proposal,
                proposal,
                frames,
                fine_config,
                offset_m=0.0,
            )
            rows[index]["fine_sweep"] = metrics
            rows[index]["fine_winner_score"] = winner_score(metrics)
        fine_ranking = sorted(
            top_two,
            key=lambda index: (
                rows[index]["fine_winner_score"],
                rows[index]["fine_sweep"]["accepted"],
            ),
            reverse=True,
        )
        winner = rows[fine_ranking[0]]
        runner_up = rows[fine_ranking[1]]
        accepted = int(winner["fine_sweep"]["accepted"])
        second_accepted = int(runner_up["fine_sweep"]["accepted"])
        selected_score = winner["fine_winner_score"]
        runner_up_score = runner_up["fine_winner_score"]
        selection_stage = "fine_5cm_top2"
        decisive = (
            accepted >= 20
            and int(winner["fine_sweep"]["coverage_cells_5cm"]) >= 20
            and selected_score >= runner_up_score * 1.25
            and accepted >= second_accepted + 10
        )

    evaluation = None
    if args.reference_planes is not None:
        reference = json.loads(args.reference_planes.read_text())["floor"]
        selected_value = float(winner["proposal"]["plane_value_n_dot_x"])
        reference_value = float(reference["plane_value_n_dot_x"])
        evaluation = {
            "reference_read_after_selection": True,
            "reference_plane_value_n_dot_x": reference_value,
            "selected_plane_value_n_dot_x": selected_value,
            "absolute_value_error_m": abs(selected_value - reference_value),
            "pass_within_3cm": decisive and abs(selected_value - reference_value) <= 0.03,
        }
    result = {
        "schema": "aether_sparse_multi_floor_image_selector_v5",
        "method": "gravity_low_sparse_proposals_then_adaptive_multiview_unique_depth",
        "forbidden_inputs_consumed": {
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
            "reference_plane_during_selection": False,
        },
        "inputs": {
            "metric_cloud": {"path": str(args.metric_cloud), "sha256": sha256(args.metric_cloud)},
            "frame_meta": {"path": str(args.frame_meta), "sha256": sha256(args.frame_meta)},
            "ledger": {"path": str(args.ledger), "sha256": sha256(args.ledger)},
            "photo_count": len(frames),
        },
        "config": {
            "coarse": config.__dict__,
            "fine_top2": fine_config.__dict__ if fine_config is not None else None,
            "coarse_decision": {
                "minimum_accepted": 12,
                "minimum_coverage_cells": 12,
                "minimum_score_ratio": 1.25,
                "minimum_accepted_lead": 5,
            },
            "fine_decision": {
                "minimum_accepted": 20,
                "minimum_coverage_cells": 20,
                "minimum_score_ratio": 1.25,
                "minimum_accepted_lead": 10,
            },
            "fine_single_decision": {
                "minimum_accepted": 12,
                "minimum_coverage_cells": 12,
                "note": "same per-site gates; denser sampling only",
            },
        },
        "proposal_count": len(proposals),
        "candidates": rows,
        "selection": {
            "decisive": decisive,
            "stage": selection_stage,
            "winner_surface_id": winner["proposal"]["surface_id"] if decisive else None,
            "winner_score": selected_score,
            "runner_up_score": runner_up_score,
            "accepted": accepted,
            "runner_up_accepted": second_accepted,
        },
        "evaluation": evaluation,
        "elapsed_s": time.perf_counter() - started,
        "verdict": (
            "PASS_REFERENCE_WITHOUT_SELECTION_LEAKAGE"
            if evaluation and evaluation["pass_within_3cm"]
            else "PASS_DECISIVE_NO_REFERENCE"
            if decisive and evaluation is None
            else "FAIL_CLOSED_AMBIGUOUS_OR_WRONG"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
