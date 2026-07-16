#!/usr/bin/env python3
"""Print frozen cap50 floor-winner birth evidence for C++ parity diagnosis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import select_floor_plane_candidates as selector


ROOT = Path(__file__).resolve().parents[2]
SELECTION = (
    ROOT
    / "experiments/cross_platform_planesweep_core_2026-07-15/runs/"
    "cap50_floor_candidate_selection_floor_contract_v5.json"
)


def _score_json(score: dict | None, reason: str | None, frames: list) -> dict:
    if score is None:
        return {"valid": False, "reason": reason}
    return {
        "valid": True,
        "views": score["views"],
        "ncc": score["ncc"],
        "parallax_deg": score["parallax"],
        "candidate_views": score["candidate_views"],
        "clique_frame_ids": [
            frames[index].frame_id for index in score["clique_frame_indices"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid-index", type=int)
    args = parser.parse_args()
    frozen = json.loads(SELECTION.read_text())
    runner = selector.load_runner()
    frames = runner.load_frames(
        ROOT / frozen["inputs"]["frame_meta"]["path"],
        ROOT / frozen["inputs"]["ledger"]["path"],
        ROOT / "data/pocketworld_captures/cap50/raw/photos_highres",
    )
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
    proposal = frozen["candidates"][1]["proposal"]
    if args.grid_index is not None:
        points = runner.surface_grid(proposal, proposal, config.grid_m, 0.0)
        point = points[args.grid_index]
        offsets = runner.patch_offsets(proposal, proposal, config)
        normal = np.asarray(proposal["normal"], dtype=np.float64)
        normal /= np.linalg.norm(normal)
        visible, head_on, _ = runner.project_centers(
            point[None, :], frames, normal, config
        )
        candidate = runner.select_point_views(
            visible[:, 0], head_on[:, 0], config.max_views
        )
        images = runner.ImageCache(frames, config.max_views).get_many(candidate)
        samples = point[None, :] + offsets
        used = []
        normalized_patches = []
        texture_std = []
        for frame_index in candidate:
            frame = frames[frame_index]
            camera_points = (frame.R @ samples.T).T + frame.t
            depth = camera_points[:, 2]
            if np.any(depth <= 0.05):
                continue
            homogeneous = (frame.K @ camera_points.T).T
            xy = homogeneous[:, :2] / depth[:, None]
            if (
                xy[:, 0].min() < 0
                or xy[:, 0].max() > frame.width - 1
                or xy[:, 1].min() < 0
                or xy[:, 1].max() > frame.height - 1
            ):
                continue
            rgb = runner.bilinear_rgb(images[frame_index], xy)
            gray = rgb @ runner.GRAY_WEIGHTS
            std = float(gray.std())
            texture_std.append({"frame_id": frame.frame_id, "std_u8": std})
            if std < config.min_std:
                continue
            normalized = gray - gray.mean()
            normalized /= np.linalg.norm(normalized) + 1.0e-9
            normalized_patches.append(normalized)
            used.append(frame_index)
        pairwise = []
        if normalized_patches:
            matrix = np.stack(normalized_patches) @ np.stack(normalized_patches).T
            for left in range(len(used)):
                for right in range(left + 1, len(used)):
                    pairwise.append(
                        {
                            "frame_ids": [
                                frames[used[left]].frame_id,
                                frames[used[right]].frame_id,
                            ],
                            "ncc": float(matrix[left, right]),
                        }
                    )
        center, center_reason = runner.score_point_hypothesis(
            point, offsets, frames, candidate, images, config
        )
        alternatives = []
        ownership_inputs = []
        for depth_offset in config.depth_competition_offsets_m:
            shifted = point + normal * depth_offset
            alternative_visible, _, _ = runner.project_centers(
                shifted[None, :], frames, normal, config
            )
            alternative_candidate = [
                index for index in candidate if alternative_visible[index, 0]
            ]
            alternative, reason = runner.score_point_hypothesis(
                shifted,
                offsets,
                frames,
                alternative_candidate,
                images,
                config,
            )
            alternatives.append(
                {
                    "offset_m": depth_offset,
                    **_score_json(alternative, reason, frames),
                }
            )
            if alternative is not None:
                ownership_inputs.append(
                    (alternative["views"], alternative["ncc"])
                )
        unique = None
        margin = None
        if center is not None:
            unique, margin = runner.unique_depth_winner(
                center["views"],
                center["ncc"],
                ownership_inputs,
                config.depth_ncc_margin,
            )
        print(
            json.dumps(
                {
                    "grid_index": args.grid_index,
                    "xyz": point.tolist(),
                    "center": _score_json(center, center_reason, frames),
                    "candidate_frame_ids": [frames[index].frame_id for index in candidate],
                    "texture_std": texture_std,
                    "pairwise_ncc_ge_0_68": sorted(
                        (row for row in pairwise if row["ncc"] >= 0.68),
                        key=lambda row: row["ncc"],
                        reverse=True,
                    ),
                    "alternatives": alternatives,
                    "unique": unique,
                    "observed_margin": margin,
                }
            )
        )
        return

    evidence: list[dict] = []
    _, _, _, metrics = runner.sweep_surface(
        proposal,
        proposal,
        frames,
        config,
        offset_m=0.0,
        evidence_sink=evidence,
    )
    print(json.dumps({"metrics": metrics, "accepted": evidence}))


if __name__ == "__main__":
    main()
