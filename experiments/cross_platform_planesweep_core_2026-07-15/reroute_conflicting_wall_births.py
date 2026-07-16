#!/usr/bin/env python3
"""Reroute conflicting wall evidence onto the stronger structural plane.

No generated point is deleted.  A weaker competing wall hypothesis is denied a
product identity only after its unique certified image evidence has produced a
replacement point on the winning wall plane and that replacement independently
passes the strict multi-view ZNCC, parallax, view-count, and unique-depth gates.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

import apply_multiview_wall_birth_ownership as owner


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = (
    ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/"
    "fr_planesweep_wall_ceiling.py"
)


def load_runner():
    spec = importlib.util.spec_from_file_location("aether_wall_birth_reroute", RUNNER_PATH)
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


def project(frame, point: np.ndarray) -> np.ndarray | None:
    camera = frame.R @ point + frame.t
    if camera[2] <= 0.0:
        return None
    homogeneous = frame.K @ camera
    return homogeneous[:2] / homogeneous[2]


def ray_plane_intersection(frame, pixel: np.ndarray, surface: dict) -> np.ndarray | None:
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    center = frame.C
    camera_ray = np.linalg.solve(frame.K, np.asarray([pixel[0], pixel[1], 1.0]))
    world_ray = frame.R.T @ camera_ray
    world_ray /= np.linalg.norm(world_ray)
    denominator = float(normal @ world_ray)
    if abs(denominator) < 1e-8:
        return None
    distance = (float(surface["plane_value_n_dot_x"]) - float(normal @ center)) / denominator
    if distance <= 0.05:
        return None
    return center + distance * world_ray


def inside_wall_domain(point: np.ndarray, surface: dict, floor: dict) -> bool:
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    axis_u = np.asarray(surface["basis_u"], dtype=np.float64)
    axis_u /= np.linalg.norm(axis_u)
    axis_v = np.asarray(floor["normal"], dtype=np.float64)
    axis_v /= np.linalg.norm(axis_v)
    origin = (
        float(surface["plane_value_n_dot_x"]) * normal
        + float(floor["plane_value_n_dot_x"]) * axis_v
    )
    delta = point - origin
    u = float(delta @ axis_u)
    v = float(delta @ axis_v)
    u0, u1 = map(float, surface["bounds_u_m"])
    v0, v1 = map(float, surface["bounds_height_m"])
    return u0 - 1e-6 <= u <= u1 + 1e-6 and v0 - 1e-6 <= v <= v1 + 1e-6


def strict_thresholds(stats: dict, surface_id: str) -> dict[str, float]:
    config = stats["config"]
    surface = next(row for row in stats["surfaces"] if row["surface_id"] == surface_id)
    baseline = surface.get("scale_rescue", {}).get("baseline_metrics", surface)
    return {
        "min_views": float(
            max(
                int(config.get("scale_rescue_min_views") or config["min_views"]),
                math.ceil(float(baseline["views_median"] or 0.0)),
            )
        ),
        "min_parallax_deg": max(
            float(config.get("scale_rescue_min_parallax_deg") or config["min_parallax_deg"]),
            float(baseline["parallax_median_deg"] or 0.0),
        ),
        "min_ncc": max(
            float(config.get("scale_rescue_min_ncc") or config["ncc_min"]),
            float(baseline["zncc_median"] or 0.0),
        ),
        "depth_ncc_margin": float(
            config.get("scale_rescue_depth_ncc_margin") or config["depth_ncc_margin"]
        ),
    }


def score_candidate(runner, point, surface, floor, frames, cache, config, thresholds):
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    strict_config = replace(
        config,
        patch_radius_m=float(config.patch_radius_m * 2.0),
        depth_ncc_margin=thresholds["depth_ncc_margin"],
    )
    visible, head_on, _ = runner.project_centers(
        point[None, :], frames, normal, strict_config
    )
    candidate = runner.select_tile_views(visible, head_on, strict_config.max_views)
    images = cache.get_many(candidate) if candidate else {}
    offsets = runner.patch_offsets(surface, floor, strict_config)
    center, reason = runner.score_point_hypothesis(
        point, offsets, frames, candidate, images, strict_config
    )
    if center is None:
        return None, reason
    alternatives = []
    for depth_offset in strict_config.depth_competition_offsets_m:
        shifted = point + normal * depth_offset
        alt_visible, _, _ = runner.project_centers(
            shifted[None, :], frames, normal, strict_config
        )
        alt_candidate = [index for index in candidate if alt_visible[index, 0]]
        alternative, _ = runner.score_point_hypothesis(
            shifted, offsets, frames, alt_candidate, images, strict_config
        )
        if alternative is not None:
            alternatives.append((alternative["views"], alternative["ncc"]))
    unique, depth_margin = runner.unique_depth_winner(
        center["views"], center["ncc"], alternatives, strict_config.depth_ncc_margin
    )
    if not unique:
        return None, "ambiguous_depth"
    if (
        center["views"] < thresholds["min_views"]
        or center["parallax"] < thresholds["min_parallax_deg"]
        or center["ncc"] < thresholds["min_ncc"]
    ):
        return None, "strict_rescue_quality"
    return {
        "views": int(center["views"]),
        "parallax_deg": float(center["parallax"]),
        "zncc_median": float(center["ncc"]),
        "candidate_views": int(center["candidate_views"]),
        "clique_frame_ids": [
            int(frames[index].frame_id) for index in center["clique_frame_indices"]
        ],
        "depth_ncc_margin_observed": depth_margin,
    }, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stats", type=Path)
    parser.add_argument("photos", type=Path)
    parser.add_argument("ownership", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()
    root = (args.repo_root or ROOT).resolve()
    stats_path = owner.resolve(root, args.stats).resolve()
    photos = owner.resolve(root, args.photos).resolve()
    ownership_path = owner.resolve(root, args.ownership).resolve()
    output_path = owner.resolve(root, args.output).resolve()
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")

    stats = json.loads(stats_path.read_text())
    ownership = json.loads(ownership_path.read_text())
    if ownership.get("quality_pass"):
        raise ValueError("ownership already passes; no evidence reroute is needed")
    ply_path = owner.resolve(root, stats["output"]["ply"]).resolve()
    planes_path = owner.resolve(root, stats["inputs"]["planes"]["path"]).resolve()
    meta_path = owner.resolve(root, stats["inputs"]["frame_meta"]["path"]).resolve()
    ledger_path = owner.resolve(root, stats["inputs"]["ledger"]["path"]).resolve()
    evidence_path = owner.resolve(root, stats["output"]["birth_evidence"]).resolve()
    planes = json.loads(planes_path.read_text())
    surfaces = {row["surface_id"]: row for row in owner.selected_surfaces(planes)}
    points = owner.load_points(stats, planes, owner.read_ascii_ply(ply_path))
    certified_views = owner.load_certified_views(evidence_path, points)

    runner = load_runner()
    frames = runner.load_frames(meta_path, ledger_path, photos)
    frame_by_id = {int(frame.frame_id): frame for frame in frames}
    config_values = stats["config"]
    config = runner.SweepConfig(
        **{
            key: (
                tuple(value)
                if key == "depth_competition_offsets_m"
                else value
            )
            for key, value in config_values.items()
            if key in runner.SweepConfig.__dataclass_fields__
        }
    )
    cache = runner.ImageCache(frames, max(config.image_cache_images, config.max_views))

    proposals = []
    accepted_replacements = []
    seen = []
    for withheld in ownership["withheld_product_identities"]:
        loser_index = int(withheld["point_index"])
        loser = points[loser_index]
        winner_surface_id = withheld["owner_surface_id"]
        surface = surfaces[winner_surface_id]
        thresholds = strict_thresholds(stats, winner_surface_id)
        candidate_rows = []
        for frame_id in sorted(certified_views[loser_index]):
            frame = frame_by_id[frame_id]
            pixel = project(frame, loser.xyz)
            if pixel is None:
                continue
            candidate = ray_plane_intersection(frame, pixel, surface)
            if candidate is None or not inside_wall_domain(candidate, surface, planes["floor"]):
                continue
            if any(
                prior["surface_id"] == winner_surface_id
                and np.linalg.norm(candidate - prior["xyz_array"]) < 0.02
                for prior in seen
            ):
                continue
            evidence, rejection = score_candidate(
                runner,
                candidate,
                surface,
                planes["floor"],
                frames,
                cache,
                config,
                thresholds,
            )
            row = {
                "source_loser_point_index": loser_index,
                "source_frame_id": frame_id,
                "owner_surface_id": winner_surface_id,
                "xyz": [float(value) for value in candidate],
                "strict_thresholds": thresholds,
                "accepted": evidence is not None,
                "rejection": rejection,
                "evidence": evidence,
            }
            candidate_rows.append(row)
            if evidence is not None:
                row["xyz_array"] = candidate
                seen.append(row)
        winner = max(
            (row for row in candidate_rows if row["accepted"]),
            key=lambda row: (
                row["evidence"]["views"],
                row["evidence"]["zncc_median"],
                row["evidence"]["parallax_deg"],
                -row["source_frame_id"],
            ),
            default=None,
        )
        if winner is not None:
            accepted_replacements.append(winner)
        proposals.extend(candidate_rows)

    expanded_points = list(points)
    expanded_views = dict(certified_views)
    replacement_rows = []
    for replacement in accepted_replacements:
        index = len(expanded_points)
        evidence = replacement["evidence"]
        surface_id = replacement["owner_surface_id"]
        xyz = np.asarray(replacement["xyz"], dtype=np.float64)
        expanded_points.append(
            owner.PointEvidence(
                index=index,
                surface_id=surface_id,
                xyz=xyz,
                normal=np.asarray(surfaces[surface_id]["normal"], dtype=np.float64),
                nviews=float(evidence["views"]),
                parallax_deg=float(evidence["parallax_deg"]),
                zncc_median=float(evidence["zncc_median"]),
            )
        )
        expanded_views[index] = frozenset(evidence["clique_frame_ids"])
        replacement_rows.append(
            {
                "point_index": index,
                **{key: value for key, value in replacement.items() if key != "xyz_array"},
            }
        )

    published = sorted(
        list(ownership["published_point_indices"])
        + [row["point_index"] for row in replacement_rows]
    )
    _, conflicts = owner.find_conflicts(
        expanded_points,
        frames,
        float(
            ownership["contract"].get(
                "birth_radius_px", ownership["contract"].get("radius_px", 0.5)
            )
        ),
        float(ownership["contract"]["depth_gap_mm"][0]),
        float(ownership["contract"]["depth_gap_mm"][1]),
        int(ownership["contract"]["min_distinct_registered_views"]),
        float(ownership["contract"]["max_normal_angle_deg"]),
        expanded_views,
    )
    before_coverage = owner.coverage(
        expanded_points, frames, list(range(len(points))), expanded_views
    )
    after_coverage = owner.coverage(expanded_points, frames, published, expanded_views)
    coverage_exact = before_coverage["per_frame_32x18"] == after_coverage["per_frame_32x18"]
    conflicts_after = owner.remaining_conflicts(conflicts, published)
    rerouted_losers = {
        row["source_loser_point_index"] for row in replacement_rows
    }
    all_losers = {
        int(row["point_index"]) for row in ownership["withheld_product_identities"]
    }
    result = {
        "schema": "pocketworld_conflicting_wall_birth_reroute_v1",
        "method": "prebirth_evidence_transfer_to_stronger_structural_plane",
        "inputs": {
            "stats": {"path": str(stats_path.relative_to(root)), "sha256": sha256(stats_path)},
            "ownership": {"path": str(ownership_path.relative_to(root)), "sha256": sha256(ownership_path)},
            "ply": {"path": str(ply_path.relative_to(root)), "sha256": sha256(ply_path)},
            "birth_evidence": {"path": str(evidence_path.relative_to(root)), "sha256": sha256(evidence_path)},
        },
        "internal_hypotheses_unchanged": True,
        "input_ply_unchanged": True,
        "proposals": [
            {key: value for key, value in row.items() if key != "xyz_array"}
            for row in proposals
        ],
        "accepted_replacements": replacement_rows,
        "published_original_point_indices": ownership["published_point_indices"],
        "published_point_indices_after_reroute": published,
        "counts": {
            "original_wall_births": len(points),
            "original_withheld_identities": len(all_losers),
            "replacement_births": len(replacement_rows),
            "published_births_after_reroute": len(published),
            "parallel_layer_conflicts_after": conflicts_after,
        },
        "coverage_32x18": {"before": before_coverage, "after": after_coverage},
        "quality_gates": {
            "every_withheld_identity_has_strict_replacement": rerouted_losers == all_losers,
            "published_count_not_lower": len(published) >= len(points),
            "certified_image_cell_coverage_exact": coverage_exact,
            "parallel_layer_conflicts_after_zero": conflicts_after == 0,
            "input_ply_hash_unchanged": sha256(ply_path) == stats["output"]["sha256"],
            "internal_hypotheses_unchanged": True,
        },
    }
    result["quality_pass"] = all(result["quality_gates"].values())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "quality_pass": result["quality_pass"],
                **result["counts"],
                "coverage_exact": coverage_exact,
                "peak_loaded_image_bytes": cache.peak_bytes,
                "decoded_image_loads": cache.loads,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["quality_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
