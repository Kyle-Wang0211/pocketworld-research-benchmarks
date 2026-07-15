#!/usr/bin/env python3
"""Generate a cap56 fixture for the model-free A16 depth-sweep kernel."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEPTH_MODULE = ROOT / (
    "experiments/detector_free_classical_depth_sweep_2026-07-14/"
    "depth_sweep_probe.py"
)
GEOMETRY_MODULE = ROOT / (
    "experiments/floor_plane_sweep_densifier_2026-07-13/"
    "fr_planesweep_wall_ceiling.py"
)
RESOURCES = Path(__file__).resolve().parent / "ios_bench/Resources"


def fixture_contract(reference_index: int = 10) -> dict[str, object]:
    return {
        "capture": "cap56",
        "reference_index": reference_index,
        "source_count": 7,
        "width": 128,
        "height": 72,
        "depth_samples": 48,
        "depth_min_m": 0.8,
        "depth_max_m": 4.3,
        "patch_n": 5,
        "min_std_u8": 6.0,
        "ncc_min": 0.75,
        "depth_margin": 0.03,
        "min_views": 4,
        "peak_exclusion_radius_samples": 2,
        "learned_model_consumed": False,
        "training_data_consumed": False,
        "third_party_matcher_output_consumed": False,
        "lidar_or_scene_depth_consumed": False,
    }


def registered_thresholds() -> dict[str, object]:
    """Product-point parity gates frozen before a device run.

    A rejected candidate never becomes a product point, so its internal argmax
    is diagnostic. Accepted point births and their depth identities remain
    exact, while score tolerance only covers backend floating-point ordering.
    """
    return {
        "valid_mismatch_max": 0,
        "accepted_mismatch_max": 0,
        "accepted_best_index_mismatch_max": 0,
        "views_mismatch_max": 0,
        "score_mean_abs_max": 0.002,
        "score_max_abs_max": 0.02,
        "all_valid_best_index_mismatch": "diagnostic_only_for_rejected_candidates",
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_geometry_module():
    return _load(GEOMETRY_MODULE, "detector_free_a16_geometry")


def load_depth_module():
    return _load(DEPTH_MODULE, "detector_free_a16_depth")


def reference_camera_projection(reference, source, width: int, height: int) -> np.ndarray:
    """Return K_source [R_sr | t_sr] from reference-camera coordinates."""
    depth = load_depth_module()
    source_k = depth.scaled_intrinsics(source, width, height)
    rotation = source.R @ reference.R.T
    translation = source.t - rotation @ reference.t
    return source_k @ np.column_stack([rotation, translation])


def portable_float32_sweep(
    depth_module,
    reference_gray: np.ndarray,
    reference_k: np.ndarray,
    source_grays: list[np.ndarray],
    source_projections: list[np.ndarray],
    depths: np.ndarray,
    contract: dict[str, object],
) -> dict[str, np.ndarray]:
    """Vectorized reference for the explicitly float32 cross-device shader."""
    width = int(contract["width"])
    height = int(contract["height"])
    patch_n = int(contract["patch_n"])
    min_views = int(contract["min_views"])
    yy, xx = np.mgrid[0:height, 0:width]
    pixels = np.stack([xx, yy, np.ones_like(xx)], axis=-1).astype(np.float32)
    inverse_k = np.linalg.inv(reference_k.astype(np.float32)).astype(np.float32)
    rays = pixels @ inverse_k.T
    cost_volume = np.full((len(depths), height, width), -2.0, dtype=np.float32)
    view_volume = np.zeros_like(cost_volume, dtype=np.uint8)
    patch_margin = patch_n // 2 + 1
    for depth_index, depth_value in enumerate(depths.astype(np.float32)):
        reference_camera = rays * depth_value
        homogeneous_reference = np.concatenate(
            [reference_camera, np.ones((height, width, 1), dtype=np.float32)], axis=-1
        )
        scores = []
        valid_rows = []
        for gray, projection in zip(source_grays, source_projections, strict=True):
            projected = homogeneous_reference @ projection.astype(np.float32).T
            z = projected[..., 2]
            denominator = np.where(z > np.float32(1e-12), z, np.float32(1.0))
            map_x = (projected[..., 0] / denominator).astype(np.float32)
            map_y = (projected[..., 1] / denominator).astype(np.float32)
            valid = (
                (z > np.float32(0.05))
                & (map_x >= patch_margin)
                & (map_x < width - patch_margin)
                & (map_y >= patch_margin)
                & (map_y < height - patch_margin)
            )
            warped = __import__("cv2").remap(
                gray.astype(np.float32),
                map_x,
                map_y,
                __import__("cv2").INTER_LINEAR,
                borderMode=__import__("cv2").BORDER_CONSTANT,
                borderValue=0,
            )
            ncc, reference_std, warped_std = depth_module.local_zncc(
                reference_gray.astype(np.float32), warped, patch_n
            )
            valid &= (reference_std >= 6.0) & (warped_std >= 6.0)
            scores.append(np.where(valid, ncc, -2.0))
            valid_rows.append(valid)
        stacked = np.stack(scores)
        valid_count = np.stack(valid_rows).sum(axis=0)
        selected = np.sort(stacked, axis=0)[-min_views:]
        usable = valid_count >= min_views
        cost_volume[depth_index] = np.where(usable, selected.mean(axis=0), -2.0)
        view_volume[depth_index] = valid_count
    best_index = np.argmax(cost_volume, axis=0)
    best_score = np.take_along_axis(cost_volume, best_index[None], axis=0)[0]
    best_views = np.take_along_axis(view_volume, best_index[None], axis=0)[0]
    suppressed = cost_volume.copy()
    exclusion = int(contract["peak_exclusion_radius_samples"])
    for delta in range(-exclusion, exclusion + 1):
        index = np.clip(best_index + delta, 0, len(depths) - 1)
        np.put_along_axis(suppressed, index[None], -2.0, axis=0)
    second_score = suppressed.max(axis=0)
    accepted = (
        (best_score >= float(contract["ncc_min"]))
        & (best_score - second_score >= float(contract["depth_margin"]))
        & (best_views >= min_views)
    )
    return {
        "best_index": best_index,
        "best_score": best_score,
        "second_score": second_score,
        "best_views": best_views,
        "accepted": accepted,
    }


def _resource_record(path: Path) -> dict[str, object]:
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main(reference_index: int = 10) -> None:
    contract = fixture_contract(reference_index)
    geometry = load_geometry_module()
    depth = load_depth_module()
    frames = depth.load_sidecar_frames(
        geometry, depth.CAP56_LEDGER, depth.CAP56_PHOTOS
    )
    reference_index = int(contract["reference_index"])
    source_indices = depth.select_source_indices(
        frames, reference_index, int(contract["source_count"])
    )
    reference = frames[reference_index]
    sources = [frames[index] for index in source_indices]
    width = int(contract["width"])
    height = int(contract["height"])
    selected = [reference, *sources]
    grays = [depth.load_gray(frame, width, height) for frame in selected]
    intrinsics = [depth.scaled_intrinsics(frame, width, height) for frame in selected]
    inverse_depths = np.linspace(
        1.0 / float(contract["depth_max_m"]),
        1.0 / float(contract["depth_min_m"]),
        int(contract["depth_samples"]),
        dtype=np.float64,
    )
    depths = 1.0 / inverse_depths
    legacy_expected = depth.sweep_depth(
        reference,
        grays[0],
        intrinsics[0],
        sources,
        grays[1:],
        intrinsics[1:],
        depths,
        width,
        height,
        int(contract["patch_n"]),
        float(contract["ncc_min"]),
        float(contract["depth_margin"]),
        int(contract["min_views"]),
        int(contract["peak_exclusion_radius_samples"]),
        "off",
    )
    source_projections = [
        reference_camera_projection(reference, source, width, height)
        for source in sources
    ]
    expected = portable_float32_sweep(
        depth,
        grays[0],
        intrinsics[0],
        grays[1:],
        source_projections,
        depths,
        contract,
    )
    if not np.array_equal(expected["accepted"], legacy_expected["accepted"]):
        raise ValueError("portable float32 contract changes point birth versus legacy reference")

    RESOURCES.mkdir(parents=True, exist_ok=True)
    inverse_k_f32 = np.linalg.inv(intrinsics[0]).astype(np.float32)
    params_blob = struct.pack(
        "<8I20f",
        width,
        height,
        width * height,
        int(contract["depth_samples"]),
        int(contract["source_count"]),
        int(contract["patch_n"]),
        int(contract["min_views"]),
        int(contract["peak_exclusion_radius_samples"]),
        float(contract["min_std_u8"]),
        float(contract["ncc_min"]),
        float(contract["depth_margin"]),
        float(inverse_depths[0]),
        float(inverse_depths[1] - inverse_depths[0]),
        0.0,
        0.0,
        0.0,
        *inverse_k_f32[0].tolist(),
        0.0,
        *inverse_k_f32[1].tolist(),
        0.0,
        *inverse_k_f32[2].tolist(),
        0.0,
    )
    if len(params_blob) != 112:
        raise ValueError(f"portable params ABI changed: {len(params_blob)} bytes")
    resource_arrays = {
        "gray_frames.f32": np.stack(grays).astype("<f4"),
        "source_projections.f32": np.stack(source_projections).astype("<f4"),
        "expected_best_index.u16": expected["best_index"].astype("<u2"),
        "expected_best_score.f32": expected["best_score"].astype("<f4"),
        "expected_second_score.f32": expected["second_score"].astype("<f4"),
        "expected_views.u8": expected["best_views"].astype("u1"),
        "expected_accepted.u8": expected["accepted"].astype("u1"),
    }
    resources: dict[str, dict[str, object]] = {}
    for name, values in resource_arrays.items():
        path = RESOURCES / name
        values.tofile(path)
        resources[name] = _resource_record(path)
    params_path = RESOURCES / "params.bin"
    params_path.write_bytes(params_blob)
    resources[params_path.name] = _resource_record(params_path)

    photo_rows = []
    for index, frame in zip([reference_index, *source_indices], selected, strict=True):
        sidecar = frame.image_path.with_suffix(".json")
        photo_rows.append(
            {
                "index": index,
                "frame_id": frame.frame_id,
                "jpeg": frame.image_path.name,
                "jpeg_sha256": sha256(frame.image_path),
                "sidecar_sha256": sha256(sidecar),
            }
        )
    manifest = {
        "schema": "pocketworld_model_free_depth_sweep_a16_fixture_v1",
        "route": "self_developed_model_free_known_pose_multiview_depth_sweep",
        "contract": contract,
        "inputs": {
            "ledger": {
                "path": str(depth.CAP56_LEDGER.relative_to(ROOT)),
                "sha256": sha256(depth.CAP56_LEDGER),
            },
            "photos": photo_rows,
            "forbidden_matcher_outputs_consumed": False,
            "lidar_or_scene_depth_consumed": False,
        },
        "geometry": {
            "reference_inverse_k_row_major_f32": inverse_k_f32
            .reshape(-1)
            .tolist(),
            "inverse_depth_first": float(inverse_depths[0]),
            "inverse_depth_step": float(inverse_depths[1] - inverse_depths[0]),
            "source_indices": source_indices,
            "source_frame_ids": [frame.frame_id for frame in sources],
        },
        "resources": resources,
        "expected": {
            "accepted_pixels": int(expected["accepted"].sum()),
            "valid_best_pixels": int((expected["best_score"] > -1.5).sum()),
            "depth_index_definition": "argmax over ordered inverse-depth samples",
            "portable_float32_vs_legacy": {
                "accepted_mismatch_count": int(
                    np.count_nonzero(expected["accepted"] != legacy_expected["accepted"])
                ),
                "best_index_mismatch_all_valid": int(
                    np.count_nonzero(
                        (expected["best_index"] != np.argmax(
                            np.asarray([
                                np.isclose(legacy_expected["discrete_depth"], value)
                                for value in depths
                            ]),
                            axis=0,
                        ))
                        & (legacy_expected["best_score"] > -1.5)
                    )
                ),
                "best_score_mean_abs": float(
                    np.mean(np.abs(expected["best_score"] - legacy_expected["best_score"]))
                ),
                "best_score_max_abs": float(
                    np.max(np.abs(expected["best_score"] - legacy_expected["best_score"]))
                ),
            },
        },
        "registered_thresholds": registered_thresholds(),
    }
    manifest_path = RESOURCES / "fixture_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "manifest_sha256": sha256(manifest_path),
                "source_indices": source_indices,
                "accepted_pixels": manifest["expected"]["accepted_pixels"],
                "resource_bytes": sum(row["bytes"] for row in resources.values()),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-index", type=int, default=10)
    args = parser.parse_args()
    main(args.reference_index)
