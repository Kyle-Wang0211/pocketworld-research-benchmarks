#!/usr/bin/env python3
"""Generate a lossless cap50 wall tile for the strict two-scale Dawn bench."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
PLANE_SWEEP = ROOT / "experiments/floor_plane_sweep_densifier_2026-07-13/fr_planesweep_wall_ceiling.py"
PLANES = ROOT / (
    "experiments/floor_plane_sweep_densifier_2026-07-13/runs/"
    "cap50_pure_a_wall_ceiling_20260714/structural_planes_v4_zncc_certified.json"
)
META = ROOT / "data/pocketworld_captures/cap50/private_manifests/subset_meta_cap50full.json"
LEDGER = ROOT / "data/pocketworld_captures/cap50/private_manifests/sfm_fed_frames.jsonl"
PHOTOS = ROOT / "data/pocketworld_captures/cap50/raw/photos_highres"
RESOURCES = Path(__file__).resolve().parent / "ios_dawn_wall_bench/Resources"

SURFACE_ID = "wall_1"
TILE_INDEX = 0
TILE_POINTS = 64
HYPOTHESIS_OFFSETS_M = (0.0, -0.10, -0.05, 0.05, 0.10)
EXPECTED_BASELINE = [11, 12, 30, 35, 36, 37, 61]
EXPECTED_UNION = [5, 11, 12, 28, 29, 30, 35, 36, 37, 60, 61]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module():
    spec = importlib.util.spec_from_file_location("wall_planesweep", PLANE_SWEEP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def base_contract() -> dict:
    return {
        "surface_id": SURFACE_ID,
        "tile_index": TILE_INDEX,
        "tile_points": TILE_POINTS,
        "grid_m": 0.05,
        "patch_n": 9,
        "patch_radius_m": 0.03,
        "min_std_u8": 6.0,
        "ncc_min": 0.80,
        "min_views": 4,
        "min_parallax_deg": 10.0,
        "max_views": 10,
        "max_graze_deg": 72.0,
        "depth_ncc_margin": 0.02,
    }


def rescue_contract() -> dict:
    return {
        **base_contract(),
        "patch_radius_m": 0.06,
        "min_views": 5,
        "min_parallax_deg": 18.0,
        "depth_ncc_margin": 0.06,
        "post_min_ncc": 0.90,
    }


def make_config(module, contract: dict):
    return module.SweepConfig(
        grid_m=contract["grid_m"],
        tile_points=contract["tile_points"],
        image_cache_images=contract["max_views"],
        max_views=contract["max_views"],
        base_max_views=0,
        min_views=contract["min_views"],
        max_graze_deg=contract["max_graze_deg"],
        patch_n=contract["patch_n"],
        patch_radius_m=contract["patch_radius_m"],
        min_std=contract["min_std_u8"],
        ncc_min=contract["ncc_min"],
        min_parallax_deg=contract["min_parallax_deg"],
        depth_competition_offsets_m=HYPOTHESIS_OFFSETS_M[1:],
        depth_ncc_margin=contract["depth_ncc_margin"],
    )


def normalized_patch(module, point, offsets, frame, image, minimum_std):
    samples = point[None, :] + offsets
    camera_points = (frame.R @ samples.T).T + frame.t
    depth = camera_points[:, 2]
    if np.any(depth <= 0.05):
        return None, 0.0
    homogeneous = (frame.K @ camera_points.T).T
    xy = homogeneous[:, :2] / depth[:, None]
    if (
        xy[:, 0].min() < 0
        or xy[:, 0].max() > frame.width - 1
        or xy[:, 1].min() < 0
        or xy[:, 1].max() > frame.height - 1
    ):
        return None, 0.0
    gray = module.bilinear_rgb(image, xy) @ module.GRAY_WEIGHTS
    sigma = float(gray.std())
    if sigma < minimum_std:
        return None, sigma
    centered = gray - gray.mean()
    return (centered / (np.linalg.norm(centered) + 1e-9)).astype("<f4"), sigma


def crop_for_points(frame, image, flat_points, offsets_by_scale):
    projected = []
    projection = frame.K @ np.column_stack([frame.R, frame.t])
    for offsets in offsets_by_scale:
        samples = flat_points[:, None, :] + offsets[None, :, :]
        homogeneous = np.column_stack([samples.reshape(-1, 3), np.ones(samples.size // 3)])
        camera_z = homogeneous @ projection[2]
        valid = camera_z > 0.05
        xy_h = homogeneous[valid] @ projection.T
        if len(xy_h):
            projected.append(xy_h[:, :2] / xy_h[:, 2:3])
    xy = np.concatenate(projected, axis=0)
    in_image = (
        (xy[:, 0] >= 0)
        & (xy[:, 0] <= frame.width - 1)
        & (xy[:, 1] >= 0)
        & (xy[:, 1] <= frame.height - 1)
    )
    xy = xy[in_image]
    if not len(xy):
        raise ValueError(f"no projected wall samples in frame {frame.frame_id}")
    x0 = max(0, int(np.floor(xy[:, 0].min())) - 1)
    y0 = max(0, int(np.floor(xy[:, 1].min())) - 1)
    x1 = min(frame.width - 1, int(np.ceil(xy[:, 0].max())) + 1)
    y1 = min(frame.height - 1, int(np.ceil(xy[:, 1].max())) + 1)
    crop = np.ascontiguousarray(image[y0 : y1 + 1, x0 : x1 + 1])
    adjusted = projection.copy()
    adjusted[0] -= x0 * projection[2]
    adjusted[1] -= y0 * projection[2]
    return crop, adjusted, (x0, y0, x1 + 1, y1 + 1)


def pack_rgba8(image: np.ndarray) -> np.ndarray:
    rgb = image.astype(np.uint32)
    return (
        rgb[:, :, 0]
        | (rgb[:, :, 1] << 8)
        | (rgb[:, :, 2] << 16)
        | np.uint32(255 << 24)
    ).astype("<u4")


def score_tile(module, centers, surface, floor, frames, selected, images, config, post_min_ncc=None):
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    visible, _, _ = module.project_centers(centers, frames, normal, config)
    offsets = module.patch_offsets(surface, floor, config)
    accepted = []
    evidence = []
    for local_index, point in enumerate(centers):
        candidate = [index for index in selected if visible[index, local_index]]
        center, _ = module.score_point_hypothesis(
            point, offsets, frames, candidate, images, config
        )
        if center is None or (post_min_ncc is not None and center["ncc"] < post_min_ncc):
            continue
        alternatives = []
        for depth_offset in config.depth_competition_offsets_m:
            shifted = point + normal * depth_offset
            alt_visible, _, _ = module.project_centers(
                shifted[None, :], frames, normal, config
            )
            alt_candidate = [index for index in selected if alt_visible[index, 0]]
            alternative, _ = module.score_point_hypothesis(
                shifted, offsets, frames, alt_candidate, images, config
            )
            if alternative is not None:
                alternatives.append((alternative["views"], alternative["ncc"]))
        unique, margin = module.unique_depth_winner(
            center["views"], center["ncc"], alternatives, config.depth_ncc_margin
        )
        if not unique:
            continue
        accepted.append(local_index)
        evidence.append(
            {
                "local_index": local_index,
                "views": center["views"],
                "ncc": center["ncc"],
                "parallax_deg": center["parallax"],
                "depth_ncc_margin": margin,
            }
        )
    return accepted, evidence


def main() -> None:
    module = load_module()
    planes = json.loads(PLANES.read_text())
    floor = planes["floor"]
    surface = next(row for row in planes["surfaces"] if row["surface_id"] == SURFACE_ID)
    frames = module.load_frames(META, LEDGER, PHOTOS)
    base_cfg = make_config(module, base_contract())
    rescue_cfg = make_config(module, rescue_contract())
    all_points = module.surface_grid(surface, floor, base_cfg.grid_m, 0.0)
    start = TILE_INDEX * TILE_POINTS
    centers = all_points[start : start + TILE_POINTS]
    if len(centers) != TILE_POINTS:
        raise ValueError("selected wall fixture tile is incomplete")
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    visible, head_on, _ = module.project_centers(centers, frames, normal, base_cfg)
    selected = module.select_tile_views(visible, head_on, base_cfg.max_views)
    if len(selected) != base_cfg.max_views:
        raise ValueError("wall tile does not have the frozen ten shared views")
    images = module.ImageCache(frames, len(selected)).get_many(selected)
    baseline, baseline_evidence = score_tile(
        module, centers, surface, floor, frames, selected, images, base_cfg
    )
    rescue, rescue_evidence = score_tile(
        module,
        centers,
        surface,
        floor,
        frames,
        selected,
        images,
        rescue_cfg,
        rescue_contract()["post_min_ncc"],
    )
    union = sorted(set(baseline) | set(rescue))
    if baseline != EXPECTED_BASELINE or union != EXPECTED_UNION:
        raise RuntimeError(
            f"frozen host verdict changed: baseline={baseline}, rescue={rescue}, union={union}"
        )

    hypothesis_points = (
        centers[:, None, :] + normal[None, None, :] * np.asarray(HYPOTHESIS_OFFSETS_M)[None, :, None]
    ).reshape(-1, 3)
    configs = [base_cfg, rescue_cfg]
    offsets_by_scale = [module.patch_offsets(surface, floor, config) for config in configs]
    patch_count = base_cfg.patch_n * base_cfg.patch_n
    expected = np.zeros(
        (len(configs), len(selected), len(hypothesis_points), patch_count), dtype="<f4"
    )
    valid = np.zeros((len(configs), len(selected), len(hypothesis_points)), dtype=np.uint8)
    stddev = np.zeros_like(valid, dtype="<f4")

    RESOURCES.mkdir(parents=True, exist_ok=True)
    for stale in RESOURCES.iterdir():
        if stale.is_file():
            stale.unlink()
    frame_rows = []
    for resource_index, global_index in enumerate(selected):
        frame = frames[global_index]
        image = images[global_index]
        for scale_index, offsets in enumerate(offsets_by_scale):
            for point_index, point in enumerate(hypothesis_points):
                patch, sigma = normalized_patch(
                    module, point, offsets, frame, image, configs[scale_index].min_std
                )
                stddev[scale_index, resource_index, point_index] = sigma
                if patch is not None:
                    expected[scale_index, resource_index, point_index] = patch
                    valid[scale_index, resource_index, point_index] = 1
        crop, adjusted_projection, crop_bounds = crop_for_points(
            frame, image, hypothesis_points, offsets_by_scale
        )
        resource_name = f"frame_{frame.frame_id}.rgba8"
        resource_path = RESOURCES / resource_name
        pack_rgba8(crop).tofile(resource_path)
        frame_rows.append(
            {
                "frame_id": frame.frame_id,
                "resource": resource_name,
                "resource_sha256": sha256(resource_path),
                "resource_bytes": resource_path.stat().st_size,
                "width": int(crop.shape[1]),
                "height": int(crop.shape[0]),
                "crop_xyxy": list(crop_bounds),
                "projection_row_major_f32": adjusted_projection.astype(np.float32).reshape(-1).tolist(),
                "camera_center_f32": frame.C.astype(np.float32).tolist(),
            }
        )

    points_path = RESOURCES / "points.f32"
    patches_path = RESOURCES / "expected_normalized_patches.f32"
    valid_path = RESOURCES / "expected_valid.u8"
    stddev_path = RESOURCES / "expected_stddev.f32"
    hypothesis_points.astype("<f4").tofile(points_path)
    expected.tofile(patches_path)
    valid.tofile(valid_path)
    stddev.tofile(stddev_path)

    resource_index = {global_index: index for index, global_index in enumerate(selected)}
    candidate_tables = []
    for config in configs:
        hypothesis_visible, _, _ = module.project_centers(
            hypothesis_points, frames, normal, config
        )
        candidate_tables.append(
            [
                [resource_index[index] for index in selected if hypothesis_visible[index, point]]
                for point in range(len(hypothesis_points))
            ]
        )

    manifest = {
        "schema": "pocketworld_dawn_wall_scale_rescue_fixture_v1",
        "source": {
            "planes": {"path": str(PLANES.relative_to(ROOT)), "sha256": sha256(PLANES)},
            "frame_meta": {"path": str(META.relative_to(ROOT)), "sha256": sha256(META)},
            "ledger": {"path": str(LEDGER.relative_to(ROOT)), "sha256": sha256(LEDGER)},
            "forbidden_matcher_outputs_consumed": False,
            "lidar_or_scene_depth_consumed": False,
        },
        "surface_id": SURFACE_ID,
        "tile_index": TILE_INDEX,
        "candidate_count": len(centers),
        "hypothesis_offsets_m": list(HYPOTHESIS_OFFSETS_M),
        "hypothesis_count": len(HYPOTHESIS_OFFSETS_M),
        "point_count": len(hypothesis_points),
        "patch_n": base_cfg.patch_n,
        "patch_sample_count": patch_count,
        "basis_u_f32": np.asarray(surface["basis_u"], dtype=np.float32).tolist(),
        "basis_v_f32": np.asarray(floor["normal"], dtype=np.float32).tolist(),
        "normal_f32": normal.astype(np.float32).tolist(),
        "scales": [base_contract(), rescue_contract()],
        "candidate_resource_frame_indices_by_scale": candidate_tables,
        "frames": frame_rows,
        "expected": {
            "baseline_accepted_local_indices": baseline,
            "rescue_accepted_local_indices": rescue,
            "union_accepted_local_indices": union,
            "baseline_evidence": baseline_evidence,
            "rescue_evidence": rescue_evidence,
            "points_sha256": sha256(points_path),
            "normalized_patches_sha256": sha256(patches_path),
            "valid_sha256": sha256(valid_path),
            "stddev_sha256": sha256(stddev_path),
        },
    }
    manifest_path = RESOURCES / "fixture_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "manifest_sha256": sha256(manifest_path),
                "resource_frame_count": len(selected),
                "resource_bytes": sum(path.stat().st_size for path in RESOURCES.iterdir()),
                "baseline": baseline,
                "rescue": rescue,
                "union": union,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
