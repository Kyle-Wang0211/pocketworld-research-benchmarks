#!/usr/bin/env python3
"""Prepare compact immutable inputs for the real Dart B quality runner."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "experiments/floor_plane_sweep_densifier_2026-07-13/fr_planesweep_wall_ceiling.py"
QUALITY_VERDICT = ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/bcd_four_scene_quality_verdict_v4_floor_wall_ownership_20260716.json"
WALL_BIRTH_ADJUSTMENTS = {
    "cap41": ROOT
    / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap41_wall_envelope5_grid480_additive_ownership_v1_20260716.json",
}
SCENES = {
    "cap40": {
        "floor": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap40_bed_scene_20260716/floor_candidate_selection_floor_contract_v5.json",
        "walls": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap40_bed_scene_20260716/wall_owner_strict_adjudication_v1.json",
        "photos": ROOT / "data/pocketworld_captures/cap40/device_2026-07-16/photos_highres",
    },
    "cap41": {
        "floor": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap41_bed_scene_20260716/floor_candidate_selection_floor_contract_v5.json",
        "walls": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap41_bed_scene_20260716/wall_owner_strict_adjudication_v1.json",
        "photos": ROOT / "data/pocketworld_captures/cap41/device_2026-07-16/photos_highres",
    },
    "cap50": {
        "floor": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap50_floor_candidate_selection_floor_contract_v5.json",
        "walls": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap50_wall_owner_strict_adjudication_v1.json",
        "photos": ROOT / "data/pocketworld_captures/cap50/raw/photos_highres",
        "known_floor": ROOT
        / "data/pocketworld_captures/cap50/private_manifests/ghost_mask.json",
    },
    "cap51": {
        "floor": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap51_floor_candidate_selection_floor_contract_v5.json",
        "walls": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap51_wall_owner_strict_adjudication_v1.json",
        "photos": ROOT / "data/pocketworld_captures/cap51/photos_highres_device_2026-07-16",
    },
}


def load_runner():
    spec = importlib.util.spec_from_file_location("aether_dart_bcd_fixture", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {RUNNER}")
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


def product_wall_id(surface_id: str) -> str:
    if surface_id.startswith("legacy_c_abi__wall_proposal_"):
        return "legacy__wall_" + surface_id.rsplit("_", 1)[-1]
    return surface_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = load_runner()
    quality_verdict = json.loads(QUALITY_VERDICT.read_text())
    scenes = []
    for capture, paths in SCENES.items():
        floor_doc = json.loads(paths["floor"].read_text())
        inputs = floor_doc["inputs"]
        cloud_path = ROOT / inputs["metric_cloud"]["path"]
        frame_path = ROOT / inputs["frame_meta"]["path"]
        ledger_path = ROOT / inputs["ledger"]["path"]
        frames = runner.load_frames(frame_path, ledger_path, paths["photos"])
        xyz = np.ascontiguousarray(np.load(cloud_path)["xyz"], dtype="<f4")
        raw_path = output_dir / f"{capture}_sparse_xyz.f32"
        xyz.tofile(raw_path)
        wall_doc = json.loads(paths["walls"].read_text())
        expected_walls = [
            product_wall_id(surface_id)
            for surface_id in wall_doc["selected_surface_ids"]
        ]
        expected_quality = quality_verdict["scenes"][capture]
        floor_births = int(expected_quality["b_floor_births"])
        wall_births = int(expected_quality["b_wall_births"])
        wall_adjustment_path = WALL_BIRTH_ADJUSTMENTS.get(capture)
        wall_adjustment = None
        if wall_adjustment_path is not None:
            wall_adjustment = json.loads(wall_adjustment_path.read_text())
            adjustment = wall_adjustment["frozen_contract_adjustment"]
            if (
                wall_adjustment["decision"] != "PASS_ADDITIVE_TRUE_WALL_BIRTH"
                or int(adjustment["previous_wall_births"]) != wall_births
            ):
                raise RuntimeError(f"invalid wall birth adjustment for {capture}")
            wall_births = int(adjustment["quality_validated_wall_births"])
        scene = {
                "capture": capture,
                "sparse_xyz_f32": str(raw_path),
                "sparse_xyz_source": {
                    "path": str(cloud_path),
                    "sha256": sha256(cloud_path),
                    "raw_sha256": sha256(raw_path),
                    "point_count": len(xyz),
                },
                "views": [
                    {
                        "frame_id": frame.frame_id,
                        "jpeg_path": str(frame.image_path),
                        "projection_3x4": (
                            frame.K @ np.column_stack([frame.R, frame.t])
                        ).reshape(-1).tolist(),
                        "camera_center": frame.C.tolist(),
                        "width": frame.width,
                        "height": frame.height,
                    }
                    for frame in frames
                ],
                "expected": {
                    "floor_winner_proposal_index": int(
                        floor_doc["selection"]["winner_surface_id"].rsplit("_", 1)[-1]
                    ),
                    "wall_selected_candidate_ids": expected_walls,
                    "floor_births": floor_births,
                    "wall_births": wall_births,
                    "structural_birth_points": floor_births + wall_births,
                },
                "input_hashes": {
                    "frame_meta": sha256(frame_path),
                    "ledger": sha256(ledger_path),
                    "quality_verdict": sha256(QUALITY_VERDICT),
                },
            }
        if wall_adjustment_path is not None:
            scene["input_hashes"]["wall_birth_adjustment"] = sha256(
                wall_adjustment_path
            )
        known_floor_path = paths.get("known_floor")
        if known_floor_path is not None:
            known_floor = json.loads(known_floor_path.read_text())
            scene["known_floor"] = {
                "plane_n": known_floor["plane_n"],
                "plane_d": known_floor["plane_d"],
                "source": {
                    "path": str(known_floor_path),
                    "sha256": sha256(known_floor_path),
                },
            }
            scene["input_hashes"]["known_floor"] = sha256(known_floor_path)
        scenes.append(scene)
    manifest = {
        "schema": "pocketworld_dart_bcd_quality_fixture_v1",
        "method": "first_party_images_poses_sparse_metric_only",
        "scenes": scenes,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"manifest": str(manifest_path), "scenes": len(scenes)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
