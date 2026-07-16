#!/usr/bin/env python3
"""Propose physical room walls from sparse XYZ and the camera trajectory.

Unlike the legacy density-only Top-K selector, this enumerates all supported
local Hough peaks and requires the camera trajectory to stay on one side of a
candidate.  The output is proposal-only: strict multi-view photometric evidence
is still required before any point may be born.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selected_floor(path: Path) -> dict:
    result = json.loads(path.read_text())
    winner_id = result["selection"].get("winner_surface_id")
    if not result["selection"].get("decisive") or not winner_id:
        raise RuntimeError("floor selection is not decisive")
    for candidate in result["candidates"]:
        if candidate["proposal"]["surface_id"] == winner_id:
            return candidate["proposal"]
    raise RuntimeError("selected floor is absent from candidate list")


def camera_centers(path: Path) -> np.ndarray:
    frames = json.loads(path.read_text())["frames"]
    centers = []
    for frame in frames:
        transform = np.asarray(frame["extrinsic"], dtype=np.float64).reshape(4, 4).T
        centers.append(transform[:3, 3])
    if len(centers) < 3:
        raise RuntimeError("fewer than three camera poses")
    return np.asarray(centers)


def horizontal_basis(up: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    seed = np.array([1.0, 0.0, 0.0])
    if abs(float(seed @ up)) > 0.9:
        seed = np.array([0.0, 0.0, 1.0])
    axis_u = seed - float(seed @ up) * up
    axis_u /= np.linalg.norm(axis_u)
    axis_v = np.cross(up, axis_u)
    axis_v /= np.linalg.norm(axis_v)
    return axis_u, axis_v


def cell_count(a: np.ndarray, b: np.ndarray, cell_m: float = 0.10) -> int:
    if not len(a):
        return 0
    cells = np.floor(np.column_stack([a, b]) / cell_m).astype(np.int64)
    return int(len(np.unique(cells, axis=0)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric-cloud", type=Path, required=True)
    parser.add_argument("--floor-selection", type=Path, required=True)
    parser.add_argument("--frame-meta", type=Path, required=True)
    parser.add_argument("--maximum-candidates", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.maximum_candidates <= 0:
        raise ValueError("maximum-candidates must be positive")

    xyz = np.asarray(np.load(args.metric_cloud)["xyz"], dtype=np.float64)
    floor = selected_floor(args.floor_selection)
    cameras = camera_centers(args.frame_meta)
    up = np.asarray(floor["normal"], dtype=np.float64)
    up /= np.linalg.norm(up)
    floor_value = float(floor["plane_value_n_dot_x"])
    axis_u, axis_v = horizontal_basis(up)
    heights = xyz @ up - floor_value
    supported_heights = heights[np.isfinite(heights) & (heights >= 0.15)]
    if len(supported_heights) < 100:
        raise RuntimeError("insufficient above-floor sparse support")
    maximum_height = float(np.percentile(supported_heights, 99.5))
    room_mask = (heights >= 0.15) & (heights <= maximum_height)
    points = xyz[room_mask]
    point_heights = heights[room_mask]
    point_u = points @ axis_u
    point_v = points @ axis_v

    raw = []
    rho_step_m = 0.03
    fit_band_m = 0.035
    for theta_deg in range(0, 180, 2):
        theta = math.radians(theta_deg)
        cosine, sine = math.cos(theta), math.sin(theta)
        rho = point_u * cosine + point_v * sine
        low = math.floor(float(np.percentile(rho, 0.5)) / rho_step_m) * rho_step_m
        high = math.ceil(float(np.percentile(rho, 99.5)) / rho_step_m) * rho_step_m
        edges = np.arange(low, high + rho_step_m * 1.01, rho_step_m)
        counts, _ = np.histogram(rho, bins=edges)
        for index, count in enumerate(counts):
            left = counts[index - 1] if index else -1
            right = counts[index + 1] if index + 1 < len(counts) else -1
            if count < 120 or count < left or count < right:
                continue
            initial = float((edges[index] + edges[index + 1]) * 0.5)
            preliminary = np.abs(rho - initial) <= fit_band_m
            if int(preliminary.sum()) < 120:
                continue
            value = float(np.median(rho[preliminary]))
            inlier = np.abs(rho - value) <= fit_band_m
            tangent = -point_u * sine + point_v * cosine
            tangent_inlier = tangent[inlier]
            height_inlier = point_heights[inlier]
            tangent_bounds = np.percentile(tangent_inlier, [1, 99])
            height_bounds = np.percentile(height_inlier, [1, 99])
            tangent_span = float(np.diff(np.percentile(tangent_inlier, [2, 98]))[0])
            height_span = float(np.diff(np.percentile(height_inlier, [2, 98]))[0])
            if tangent_span < 0.60 or height_span < 0.60:
                continue
            normal = cosine * axis_u + sine * axis_v
            camera_distance = cameras @ normal - value
            one_sided = bool(
                float(camera_distance.min()) >= -0.05
                or float(camera_distance.max()) <= 0.05
            )
            if not one_sided:
                continue
            cells = cell_count(tangent_inlier, height_inlier)
            raw.append(
                {
                    "theta_deg": theta_deg,
                    "value": value,
                    "normal": normal,
                    "tangent": -sine * axis_u + cosine * axis_v,
                    "support": int(inlier.sum()),
                    "cells": cells,
                    "score": float(cells * math.sqrt(int(inlier.sum()))),
                    "tangent_bounds": tangent_bounds,
                    "height_bounds": height_bounds,
                    "camera_distance_min_m": float(camera_distance.min()),
                    "camera_distance_max_m": float(camera_distance.max()),
                    "camera_clearance_min_abs_m": float(np.min(np.abs(camera_distance))),
                }
            )

    raw.sort(key=lambda row: row["score"], reverse=True)
    selected = []
    for candidate in raw:
        duplicate = False
        for prior in selected:
            angle = abs(candidate["theta_deg"] - prior["theta_deg"])
            angle = min(angle, 180 - angle)
            if angle <= 4 and abs(candidate["value"] - prior["value"]) < 0.10:
                duplicate = True
                break
        if duplicate:
            continue
        selected.append(candidate)
        if len(selected) >= args.maximum_candidates:
            break

    # Refine only after the complete local-peak population has been selected.
    # Refining before de-duplication can let a dominant object plane absorb a
    # weaker room-wall peak.  The original finite tangent/height domain keeps
    # this one-step TLS update local to the candidate that proposed it.
    for candidate in selected:
        original_normal = candidate["normal"]
        original_tangent = candidate["tangent"]
        u0, u1 = candidate["tangent_bounds"]
        h0, h1 = candidate["height_bounds"]
        local = (
            (point_heights >= h0)
            & (point_heights <= h1)
            & (points @ original_tangent >= u0)
            & (points @ original_tangent <= u1)
            & (np.abs(points @ original_normal - candidate["value"]) <= fit_band_m)
        )
        if int(local.sum()) < 120:
            continue
        horizontal = np.column_stack([point_u[local], point_v[local]])
        centered = horizontal - horizontal.mean(axis=0)
        _, eigenvectors = np.linalg.eigh(centered.T @ centered)
        refined = eigenvectors[:, 0]
        old_components = np.array(
            [float(original_normal @ axis_u), float(original_normal @ axis_v)]
        )
        if float(refined @ old_components) < 0.0:
            refined = -refined
        cosine, sine = float(refined[0]), float(refined[1])
        normal = cosine * axis_u + sine * axis_v
        value = float(np.median(points[local] @ normal))
        tangent = -sine * axis_u + cosine * axis_v
        camera_distance = cameras @ normal - value
        if not (
            float(camera_distance.min()) >= -0.05
            or float(camera_distance.max()) <= 0.05
        ):
            continue
        candidate["theta_deg"] = float(
            math.degrees(math.atan2(sine, cosine)) % 180.0
        )
        candidate["value"] = value
        candidate["normal"] = normal
        candidate["tangent"] = tangent
        candidate["support"] = int(local.sum())
        candidate["cells"] = cell_count(points[local] @ tangent, point_heights[local])
        candidate["score"] = float(
            candidate["cells"] * math.sqrt(candidate["support"])
        )
        candidate["tangent_bounds"] = np.percentile(points[local] @ tangent, [1, 99])
        candidate["height_bounds"] = np.percentile(point_heights[local], [1, 99])
        candidate["camera_distance_min_m"] = float(camera_distance.min())
        candidate["camera_distance_max_m"] = float(camera_distance.max())
        candidate["camera_clearance_min_abs_m"] = float(
            np.min(np.abs(camera_distance))
        )

    surfaces = []
    for index, candidate in enumerate(selected):
        surfaces.append(
            {
                "surface_id": f"wall_envelope_{index}",
                "kind": "wall",
                "proposal_only": True,
                "certified_for_generation": False,
                "normal": candidate["normal"].tolist(),
                "plane_value_n_dot_x": candidate["value"],
                "basis_u": candidate["tangent"].tolist(),
                "basis_v": up.tolist(),
                "bounds_u_m": candidate["tangent_bounds"].tolist(),
                "bounds_height_m": candidate["height_bounds"].tolist(),
                "theta_deg_in_horizontal_basis": candidate["theta_deg"],
                "support_points_35mm": candidate["support"],
                "coverage_cells_10cm": candidate["cells"],
                "score": candidate["score"],
                "camera_trajectory_one_sided": True,
                "camera_distance_min_m": candidate["camera_distance_min_m"],
                "camera_distance_max_m": candidate["camera_distance_max_m"],
                "camera_clearance_min_abs_m": candidate["camera_clearance_min_abs_m"],
            }
        )

    result = {
        "schema": "aether_camera_envelope_wall_proposals_v3",
        "method": (
            "all_local_sparse_hough_peaks_plus_vertical_tls_refinement_plus_"
            "camera_trajectory_one_sidedness"
        ),
        "birth_authority": False,
        "forbidden_inputs_consumed": {
            "reference_plane": False,
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
        },
        "inputs": {
            "metric_cloud": {"path": str(args.metric_cloud), "sha256": sha256(args.metric_cloud)},
            "floor_selection": {"path": str(args.floor_selection), "sha256": sha256(args.floor_selection)},
            "frame_meta": {"path": str(args.frame_meta), "sha256": sha256(args.frame_meta)},
            "point_count": len(xyz),
            "camera_count": len(cameras),
        },
        "config": {
            "theta_step_deg": 2,
            "rho_step_m": rho_step_m,
            "fit_band_m": fit_band_m,
            "minimum_support": 120,
            "minimum_tangent_span_m": 0.60,
            "minimum_height_span_m": 0.60,
            "camera_crossing_tolerance_m": 0.05,
            "maximum_candidates": args.maximum_candidates,
        },
        "floor": floor,
        "raw_candidate_count": len(raw),
        "wall_count": len(surfaces),
        "walls": surfaces,
        "surfaces": surfaces,
        "verdict": "PASS_PROPOSALS_ONLY" if surfaces else "FAIL_CLOSED_NO_CANDIDATES",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
