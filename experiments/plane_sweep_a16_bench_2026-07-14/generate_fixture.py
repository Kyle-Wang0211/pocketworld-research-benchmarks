#!/usr/bin/env python3
"""Build a lossless cap50 floor tile for the accepted A16 plane-sweep gates."""

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
    "cap50_pure_a_wall_ceiling_20260714/structural_planes_v5_floor.json"
)
META = ROOT / "data/pocketworld_captures/cap50/private_manifests/subset_meta_cap50full.json"
LEDGER = ROOT / "data/pocketworld_captures/cap50/private_manifests/sfm_fed_frames.jsonl"
PHOTOS = ROOT / "data/pocketworld_captures/cap50/raw/photos_highres"
RESOURCES = Path(__file__).resolve().parent / "ios_bench/Resources"

SURFACE_ID = "floor_0"
TILE_INDEX = 47
TILE_POINTS = 64


def fixture_contract() -> dict:
    """Return the frozen B milestone gates exercised by the device fixture."""
    return {
        "surface_id": SURFACE_ID,
        "tile_index": TILE_INDEX,
        "tile_points": TILE_POINTS,
        "grid_m": 0.05,
        "patch_n": 7,
        "patch_radius_m": 0.015,
        "min_std_u8": 6.0,
        "ncc_min": 0.70,
        "min_views": 3,
        "min_parallax_deg": 5.0,
        "base_max_views": 10,
        "max_views": 48,
        "rescue_min_ncc": 0.8500471980155323,
        "rescue_min_parallax_deg": 10.241134230890212,
        "rescue_min_views": 3,
        "max_graze_deg": 72.0,
        "depth_competition_offsets_m": (),
    }


def map_point_view_indices(per_point_global: list[list[int]]) -> tuple[list[int], list[list[int]]]:
    """Map ordered global frame indices to a compact resource-frame table."""
    union = sorted({index for row in per_point_global for index in row})
    resource_index = {global_index: index for index, global_index in enumerate(union)}
    return union, [
        [resource_index[global_index] for global_index in row]
        for row in per_point_global
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module():
    spec = importlib.util.spec_from_file_location("floor_plane_sweep", PLANE_SWEEP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalized_patch(module, point, offsets, frame, image, min_std):
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
    standard_deviation = float(gray.std())
    if standard_deviation < min_std:
        return None, standard_deviation
    centered = gray - gray.mean()
    normalized = centered / (np.linalg.norm(centered) + 1e-9)
    return normalized.astype("<f4"), standard_deviation


def main() -> None:
    module = load_module()
    contract = fixture_contract()
    planes = json.loads(PLANES.read_text())
    surface = planes["floor"]
    if surface["surface_id"] != contract["surface_id"]:
        raise ValueError("accepted floor owner is missing from the plane manifest")
    frames = module.load_frames(META, LEDGER, PHOTOS)
    config = module.SweepConfig(
        grid_m=contract["grid_m"],
        tile_points=contract["tile_points"],
        image_cache_images=contract["max_views"],
        max_views=contract["max_views"],
        base_max_views=contract["base_max_views"],
        min_views=contract["min_views"],
        max_graze_deg=contract["max_graze_deg"],
        patch_n=contract["patch_n"],
        patch_radius_m=contract["patch_radius_m"],
        min_std=contract["min_std_u8"],
        ncc_min=contract["ncc_min"],
        min_parallax_deg=contract["min_parallax_deg"],
        rescue_min_ncc=contract["rescue_min_ncc"],
        rescue_min_parallax_deg=contract["rescue_min_parallax_deg"],
        rescue_min_views=contract["rescue_min_views"],
        depth_competition_offsets_m=contract["depth_competition_offsets_m"],
    )
    all_points = module.surface_grid(surface, planes["floor"], config.grid_m, 0.0)
    start = contract["tile_index"] * contract["tile_points"]
    centers = all_points[start : start + contract["tile_points"]]
    if len(centers) != contract["tile_points"]:
        raise ValueError("selected fixture tile is incomplete")
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    visible, head_on, _ = module.project_centers(centers, frames, normal, config)
    per_point_global = [
        module.select_point_views(visible[:, index], head_on[:, index], config.max_views)
        for index in range(len(centers))
    ]
    selected, per_point_resource = map_point_view_indices(per_point_global)
    selected_frames = [frames[index] for index in selected]
    patch_offsets = module.patch_offsets(surface, planes["floor"], config)
    flat_points = centers

    RESOURCES.mkdir(parents=True, exist_ok=True)
    for stale in RESOURCES.glob("frame_*.png"):
        stale.unlink()

    patch_count = config.patch_n * config.patch_n
    expected = np.zeros(
        (len(selected_frames), len(flat_points), patch_count), dtype="<f4"
    )
    valid = np.zeros((len(selected_frames), len(flat_points)), dtype=np.uint8)
    stddev = np.zeros((len(selected_frames), len(flat_points)), dtype="<f4")
    frame_rows = []
    for frame_index, frame in enumerate(selected_frames):
        with Image.open(frame.image_path) as source:
            image = np.asarray(source.convert("RGB"), dtype=np.uint8)
            output_name = f"frame_{frame.frame_id}.png"
            Image.fromarray(image).save(
                RESOURCES / output_name, format="PNG", compress_level=6
            )
        for point_index, point in enumerate(flat_points):
            patch, sigma = normalized_patch(
                module, point, patch_offsets, frame, image, config.min_std
            )
            stddev[frame_index, point_index] = sigma
            if patch is not None:
                expected[frame_index, point_index] = patch
                valid[frame_index, point_index] = 1
        projection = frame.K @ np.column_stack([frame.R, frame.t])
        resource = RESOURCES / output_name
        frame_rows.append(
            {
                "frame_id": frame.frame_id,
                "resource": output_name,
                "resource_sha256": sha256(resource),
                "resource_bytes": resource.stat().st_size,
                "width": frame.width,
                "height": frame.height,
                "projection_row_major_f32": projection.astype(np.float32).reshape(-1).tolist(),
                "camera_center_f32": frame.C.astype(np.float32).tolist(),
            }
        )

    points_path = RESOURCES / "points.f32"
    patches_path = RESOURCES / "expected_normalized_patches.f32"
    valid_path = RESOURCES / "expected_valid.u8"
    stddev_path = RESOURCES / "expected_stddev.f32"
    flat_points.astype("<f4").tofile(points_path)
    expected.tofile(patches_path)
    valid.tofile(valid_path)
    stddev.tofile(stddev_path)

    image_cache = module.ImageCache(frames, config.image_cache_images)
    accepted_local_indices = []
    base_accepted_local_indices = []
    rescue_accepted_local_indices = []
    accepted_evidence = []
    for local_index, center in enumerate(centers):
        candidate = per_point_global[local_index]
        images = image_cache.get_many(candidate) if candidate else {}
        center_score, _ = module.score_point_hypothesis(
            center,
            patch_offsets,
            frames,
            candidate[: config.base_max_views],
            images,
            config,
        )
        accepted_by = "base"
        if center_score is None and len(candidate) > config.base_max_views:
            rescue, _ = module.score_point_hypothesis(
                center, patch_offsets, frames, candidate, images, config
            )
            if rescue is not None and module.passes_rescue_gate(
                rescue,
                config.rescue_min_ncc,
                config.rescue_min_parallax_deg,
                config.rescue_min_views,
            ):
                center_score = rescue
                accepted_by = "rescue"
        if center_score is None:
            continue
        accepted_local_indices.append(local_index)
        if accepted_by == "base":
            base_accepted_local_indices.append(local_index)
        else:
            rescue_accepted_local_indices.append(local_index)
        accepted_evidence.append(
            {
                "local_index": local_index,
                "accepted_by": accepted_by,
                "views": center_score["views"],
                "ncc": center_score["ncc"],
                "parallax_deg": center_score["parallax"],
            }
        )

    manifest = {
        "schema": "pocketworld_a16_planesweep_streaming_fixture_v2",
        "source": {
            "planes": {"path": str(PLANES.relative_to(ROOT)), "sha256": sha256(PLANES)},
            "frame_meta": {"path": str(META.relative_to(ROOT)), "sha256": sha256(META)},
            "ledger": {"path": str(LEDGER.relative_to(ROOT)), "sha256": sha256(LEDGER)},
            "forbidden_matcher_outputs_consumed": False,
        },
        "surface_id": surface["surface_id"],
        "tile_index": contract["tile_index"],
        "candidate_count": len(centers),
        "candidate_resource_frame_indices": per_point_resource,
        "hypothesis_offsets_m": [0.0],
        "hypothesis_count": 1,
        "point_count": len(flat_points),
        "patch_n": config.patch_n,
        "patch_radius_m": config.patch_radius_m,
        "patch_sample_count": patch_count,
        "min_std_u8": config.min_std,
        "min_views": config.min_views,
        "ncc_min": config.ncc_min,
        "min_parallax_deg": config.min_parallax_deg,
        "base_max_views": config.base_max_views,
        "max_views": config.max_views,
        "rescue_min_ncc": config.rescue_min_ncc,
        "rescue_min_parallax_deg": config.rescue_min_parallax_deg,
        "rescue_min_views": config.rescue_min_views,
        "depth_competition_offsets_m": [],
        "basis_u_f32": np.asarray(surface["basis_u"], dtype=np.float32).tolist(),
        "basis_v_f32": np.asarray(surface["basis_v"], dtype=np.float32).tolist(),
        "normal_f32": normal.astype(np.float32).tolist(),
        "frames": frame_rows,
        "expected": {
            "accepted_local_indices": accepted_local_indices,
            "accepted_count": len(accepted_local_indices),
            "base_accepted_local_indices": base_accepted_local_indices,
            "rescue_accepted_local_indices": rescue_accepted_local_indices,
            "accepted_evidence": accepted_evidence,
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
                "selected_frame_ids": [frame.frame_id for frame in selected_frames],
                "resource_frame_count": len(selected_frames),
                "resource_bytes": sum(path.stat().st_size for path in RESOURCES.iterdir()),
                "expected_accepted": accepted_local_indices,
                "expected_base_accepted": base_accepted_local_indices,
                "expected_rescue_accepted": rescue_accepted_local_indices,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
