#!/usr/bin/env python3
"""Resolve only ambiguous wall families with a stricter second physical scale.

The first-stage owner thresholds remain unchanged.  A family that already has
an owner is never revisited.  For an unresolved family, every contender that
passed the base birth minimum is replayed with the frozen 6 cm / >=5 view /
>=18 degree rescue contract.  A contender is eligible only when appending its
rescue births preserves all nine baseline quality metrics.  The family opens
only when one eligible contender remains or the same frozen 1.25x/+3 evidence
lead is decisive at the merged scale.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
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
    spec = importlib.util.spec_from_file_location("aether_wall_strict_adjudicator", RUNNER_PATH)
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


def metric_not_lower(baseline: dict, merged: dict, name: str) -> bool:
    baseline_value = baseline.get(name)
    merged_value = merged.get(name)
    return baseline_value is None or (
        merged_value is not None and merged_value >= baseline_value - 1e-12
    )


def strict_assessment(runner, surface: dict, floor: dict, frames, config) -> dict:
    baseline_xyz, baseline_rgb, baseline_meta, baseline = runner.sweep_surface(
        surface, floor, frames, config, 0.0
    )
    rescue_min_views, rescue_min_parallax, rescue_min_ncc = (
        runner.scale_rescue_nonregression_thresholds(
            baseline_meta, 5, 18.0, 0.90
        )
    )
    rescue_config = replace(
        config,
        patch_radius_m=0.06,
        min_views=5,
        min_parallax_deg=18.0,
        depth_ncc_margin=0.06,
    )
    rescue_xyz, rescue_rgb, rescue_meta, rescue = runner.sweep_surface(
        surface, floor, frames, rescue_config, 0.0
    )
    quality_mask = runner.scale_rescue_quality_mask(
        rescue_meta, rescue_min_views, rescue_min_parallax, rescue_min_ncc
    )
    rescue_xyz = rescue_xyz[quality_mask]
    rescue_rgb = rescue_rgb[quality_mask]
    rescue_meta = rescue_meta[quality_mask]
    xyz, _, metadata, added = runner.merge_scale_rescue_results(
        baseline_xyz,
        baseline_rgb,
        baseline_meta,
        rescue_xyz,
        rescue_rgb,
        rescue_meta,
    )
    depth_min_values = [
        value
        for value in (
            baseline["depth_ncc_margin_observed_min"],
            rescue["depth_ncc_margin_observed_min"],
        )
        if value is not None
    ]
    depth_median_values = [
        value
        for value in (
            baseline["depth_ncc_margin_observed_median"],
            rescue["depth_ncc_margin_observed_median"],
        )
        if value is not None
    ]
    merged = dict(baseline)
    merged.update(
        {
            "accepted": len(xyz),
            "coverage_cells_5cm": runner.surface_coverage_cells(
                xyz, surface, floor, 0.05
            ),
            "views_median": float(np.median(metadata[:, 0])) if len(metadata) else None,
            "parallax_median_deg": (
                float(np.median(metadata[:, 1])) if len(metadata) else None
            ),
            "zncc_median": float(np.median(metadata[:, 2])) if len(metadata) else None,
            "zncc_p10": (
                float(np.percentile(metadata[:, 2], 10)) if len(metadata) else None
            ),
            "depth_ncc_margin_observed_min": (
                min(depth_min_values) if depth_min_values else None
            ),
            "depth_ncc_margin_observed_median": (
                min(depth_median_values) if depth_median_values else None
            ),
            "scale_rescue_accepted": added,
        }
    )
    checks = {
        "baseline_point_prefix_exact": bool(
            np.array_equal(xyz[: len(baseline_xyz)], baseline_xyz)
        ),
        "accepted_not_lower": metric_not_lower(baseline, merged, "accepted"),
        "coverage_cells_5cm_not_lower": metric_not_lower(
            baseline, merged, "coverage_cells_5cm"
        ),
        "views_median_not_lower": metric_not_lower(baseline, merged, "views_median"),
        "parallax_median_not_lower": metric_not_lower(
            baseline, merged, "parallax_median_deg"
        ),
        "zncc_median_not_lower": metric_not_lower(baseline, merged, "zncc_median"),
        "zncc_p10_not_lower": metric_not_lower(baseline, merged, "zncc_p10"),
        "depth_margin_min_not_lower": metric_not_lower(
            baseline, merged, "depth_ncc_margin_observed_min"
        ),
        "depth_margin_median_not_lower": metric_not_lower(
            baseline, merged, "depth_ncc_margin_observed_median"
        ),
    }
    return {
        "surface_id": surface["surface_id"],
        "eligible": all(checks.values()),
        "baseline_metrics": baseline,
        "rescue_metrics": rescue,
        "rescue_quality_gate": {
            "minimum_views": rescue_min_views,
            "minimum_parallax_deg": rescue_min_parallax,
            "minimum_ncc": rescue_min_ncc,
            "depth_ncc_margin": 0.06,
            "accepted_after_quality_gate": len(rescue_xyz),
            "added_unique_points": added,
        },
        "merged_metrics": merged,
        "nonregression_checks": checks,
        "winner_score": int(merged["accepted"]) * float(merged["zncc_median"] or 0.0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--frame-meta", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runner = load_runner()
    selection = json.loads(args.selection.read_text())
    frames = runner.load_frames(args.frame_meta, args.ledger, args.photos)
    config_values = dict(selection["config"]["sweep"])
    config_values["depth_competition_offsets_m"] = tuple(
        config_values["depth_competition_offsets_m"]
    )
    config = runner.SweepConfig(**config_values)
    rows = {row["surface"]["surface_id"]: row for row in selection["candidates"]}
    selected_ids = list(selection["selected_surface_ids"])
    selected_set = set(selected_ids)
    adjudications = []
    started = time.perf_counter()

    for family in selection["families"]:
        if family["winner_surface_id"] is not None:
            continue
        contenders = [
            rows[surface_id]
            for surface_id in family["candidate_surface_ids"]
            if int(rows[surface_id]["metrics"]["accepted"]) >= 8
            and int(rows[surface_id]["metrics"]["coverage_cells_5cm"]) >= 8
        ]
        if len(contenders) < 2:
            continue
        assessments = [
            strict_assessment(runner, row["surface"], selection["floor"], frames, config)
            for row in contenders
        ]
        eligible = sorted(
            (row for row in assessments if row["eligible"]),
            key=lambda row: (
                row["winner_score"],
                int(row["merged_metrics"]["accepted"]),
            ),
            reverse=True,
        )
        winner_id = None
        decision = "fail_closed_strict_scale"
        if len(eligible) == 1:
            winner_id = eligible[0]["surface_id"]
            decision = "sole_nonregressing_strict_scale_owner"
        elif len(eligible) >= 2:
            winner, runner_up = eligible[:2]
            if (
                winner["winner_score"] >= runner_up["winner_score"] * 1.25
                and int(winner["merged_metrics"]["accepted"])
                >= int(runner_up["merged_metrics"]["accepted"]) + 3
            ):
                winner_id = winner["surface_id"]
                decision = "decisive_strict_scale_owner"
        if winner_id is not None and winner_id not in selected_set:
            selected_ids.append(winner_id)
            selected_set.add(winner_id)
        adjudications.append(
            {
                "family_index": family["family_index"],
                "base_candidate_surface_ids": family["candidate_surface_ids"],
                "contender_surface_ids": [row["surface_id"] for row in assessments],
                "winner_surface_id": winner_id,
                "decision": decision,
                "assessments": assessments,
            }
        )

    selected_surfaces = [
        {
            **row["surface"],
            "certified_for_generation": True,
            "proposal_only": False,
        }
        for row in selection["candidates"]
        if row["surface"]["surface_id"] in selected_set
    ]
    result = {
        "schema": "aether_strict_scale_wall_owner_adjudication_v1",
        "method": "base_owner_then_strict_nonregressing_scale_for_ambiguous_families",
        "forbidden_inputs_consumed": selection["forbidden_inputs_consumed"],
        "inputs": {
            "selection": {"path": str(args.selection), "sha256": sha256(args.selection)},
            "frame_meta": {"path": str(args.frame_meta), "sha256": sha256(args.frame_meta)},
            "ledger": {"path": str(args.ledger), "sha256": sha256(args.ledger)},
            "photo_count": len(frames),
        },
        "config": {
            "base_sweep": config.__dict__,
            "strict_patch_radius_m": 0.06,
            "strict_minimum_views": 5,
            "strict_minimum_parallax_deg": 18.0,
            "strict_minimum_ncc": 0.90,
            "strict_depth_ncc_margin": 0.06,
            "minimum_winner_score_ratio": 1.25,
            "minimum_accepted_lead": 3,
        },
        "floor": selection["floor"],
        "base_selected_surface_ids": selection["selected_surface_ids"],
        "selected_surface_ids": selected_ids,
        "surfaces": selected_surfaces,
        "adjudications": adjudications,
        "elapsed_s": time.perf_counter() - started,
        "verdict": "PASS_WALL_OWNERS" if selected_ids else "FAIL_CLOSED_NO_OWNER",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "verdict": result["verdict"],
                "base_selected": len(result["base_selected_surface_ids"]),
                "final_selected": len(result["selected_surface_ids"]),
                "adjudicated_families": len(adjudications),
                "selected_surface_ids": result["selected_surface_ids"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
