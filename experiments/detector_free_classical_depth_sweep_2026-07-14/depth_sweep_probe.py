#!/usr/bin/env python3
"""Model-free known-pose multi-view depth sweep probe for cap50."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import resource
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
PLANE_SWEEP = ROOT / "experiments/floor_plane_sweep_densifier_2026-07-13/fr_planesweep_wall_ceiling.py"
META = ROOT / "data/pocketworld_captures/cap50/private_manifests/subset_meta_cap50full.json"
LEDGER = ROOT / "data/pocketworld_captures/cap50/private_manifests/sfm_fed_frames.jsonl"
PHOTOS = ROOT / "data/pocketworld_captures/cap50/raw/photos_highres"
SPARSE = ROOT / "data/pocketworld_captures/cap50/sfm/sfm_sparse.ply"
STRUCTURAL_PLANES = ROOT / (
    "experiments/floor_plane_sweep_densifier_2026-07-13/runs/"
    "cap50_pure_a_wall_ceiling_20260714/structural_planes_v4_zncc_certified.json"
)
CAP56_LEDGER = ROOT / (
    "data/pocketworld_captures/cap56/fresh_device_pull_2026-07-15T1002+0800/"
    "sfm_fed_frames.jsonl"
)
CAP56_PHOTOS = ROOT / "data/pocketworld_captures/cap56/raw/photos_highres"
CAP56_SPARSE = ROOT / (
    "data/pocketworld_captures/cap56/fresh_device_pull_2026-07-15T1002+0800/"
    "sfm_sparse.ply"
)

SAFE_QUADRATIC_MIN_ABS_OFFSET_SAMPLES = 0.20
SAFE_QUADRATIC_MAX_ABS_OFFSET_SAMPLES = 0.30
SAFE_QUADRATIC_MAX_NCC = 0.925
SAFE_QUADRATIC_MAX_DEPTH_M = 1.50
CONSERVATIVE_QUADRATIC_MIN_ABS_OFFSET_SAMPLES = 0.15
CONSERVATIVE_QUADRATIC_MAX_ABS_OFFSET_SAMPLES = 0.40
CONSERVATIVE_QUADRATIC_MAX_NCC = 0.80
CONSERVATIVE_QUADRATIC_MAX_MARGIN = 0.15
CONSERVATIVE_QUADRATIC_MAX_DEPTH_M = 1.50


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def capture_bundle_sha256(frames) -> str:
    """Hash the ordered first-party image/sidecar bundle used by a run."""
    digest = hashlib.sha256()
    for frame in frames:
        digest.update(f"{frame.frame_id}:{frame.image_path.name}\n".encode())
        digest.update(bytes.fromhex(sha256(frame.image_path)))
        sidecar_path = frame.image_path.with_suffix(".json")
        if sidecar_path.is_file():
            digest.update(bytes.fromhex(sha256(sidecar_path)))
    return digest.hexdigest()


def load_geometry_module():
    spec = importlib.util.spec_from_file_location("depth_sweep_geometry", PLANE_SWEEP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_sidecar_frames(geometry_module, ledger_path: Path, photo_dir: Path):
    """Load every durable capture frame; missing JPEG/sidecar is a hard failure."""
    ledger_rows = [
        json.loads(line) for line in ledger_path.read_text().splitlines() if line
    ]
    ledger_rows.sort(key=lambda row: int(row["frameId"]))
    frame_ids = [int(row["frameId"]) for row in ledger_rows]
    if len(frame_ids) != len(set(frame_ids)):
        raise ValueError("duplicate frameId in durable capture ledger")
    frames = []
    for ledger in ledger_rows:
        image_path = photo_dir / Path(ledger["jpegPath"]).name
        sidecar_path = image_path.with_suffix(".json")
        if not image_path.is_file() or not sidecar_path.is_file():
            raise FileNotFoundError(
                f"durable capture bundle is incomplete for frame {ledger['frameId']}: "
                f"{image_path.name}"
            )
        sidecar = json.loads(sidecar_path.read_text())
        with Image.open(image_path) as image:
            width, height = image.size
        if (width, height) != (
            int(sidecar["image_w"]),
            int(sidecar["image_h"]),
        ):
            raise ValueError(f"sidecar image dimensions disagree for {image_path.name}")
        fx, fy, cx, cy = map(float, sidecar["intrinsics_fxfycxcy"])
        K = np.asarray(
            [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        camera_to_world_arkit = np.asarray(
            sidecar["extrinsic"], dtype=np.float64
        ).reshape(4, 4).T
        center = camera_to_world_arkit[:3, 3].copy()
        camera_to_world_cv = (
            camera_to_world_arkit[:3, :3] @ geometry_module.FLIP_ARKIT_TO_CV
        )
        R = camera_to_world_cv.T
        t = -R @ center
        ledger_center = np.asarray(
            ledger["arkitCameraCenterWorld"], dtype=np.float64
        )
        if np.linalg.norm(ledger_center - center) > 1e-4:
            raise ValueError(f"pose center mismatch for {image_path.name}")
        frames.append(
            geometry_module.Frame(
                frame_id=int(ledger["frameId"]),
                image_path=image_path,
                K=K,
                R=R,
                t=t,
                C=center,
                width=width,
                height=height,
            )
        )
    if len(frames) < 3:
        raise ValueError("fewer than three complete durable capture frames")
    return frames


def select_source_indices(
    frames,
    reference_index: int,
    count: int,
    min_baseline_m: float = 0.08,
    max_baseline_m: float = 0.75,
    max_forward_angle_deg: float = 45.0,
) -> list[int]:
    """Select likely-overlapping sources from pose geometry alone."""
    if count <= 0:
        raise ValueError("source count must be positive")
    reference = frames[reference_index]
    reference_forward = reference.R.T[:, 2]
    candidates = []
    for index, frame in enumerate(frames):
        if index == reference_index:
            continue
        baseline = float(np.linalg.norm(frame.C - reference.C))
        cosine = float(np.dot(reference_forward, frame.R.T[:, 2]))
        forward_angle = math.degrees(math.acos(np.clip(cosine, -1.0, 1.0)))
        if not (
            min_baseline_m <= baseline <= max_baseline_m
            and forward_angle <= max_forward_angle_deg
        ):
            continue
        score = abs(math.log(baseline / 0.25)) + forward_angle / max_forward_angle_deg
        candidates.append((score, index))
    if len(candidates) < count:
        raise ValueError(
            f"only {len(candidates)} pose-overlap sources satisfy gates; need {count}"
        )
    candidates.sort()
    return [index for _, index in candidates[:count]]


def load_gray(frame, width: int, height: int) -> np.ndarray:
    with Image.open(frame.image_path) as source:
        image = np.asarray(source.convert("RGB"), dtype=np.uint8)
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY).astype(np.float32)


def scaled_intrinsics(frame, width: int, height: int) -> np.ndarray:
    scale_x = width / frame.width
    scale_y = height / frame.height
    K = frame.K.copy()
    K[0] *= scale_x
    K[1] *= scale_y
    return K


def local_zncc(reference: np.ndarray, warped: np.ndarray, patch_n: int):
    area = float(patch_n * patch_n)
    box = lambda values: cv2.boxFilter(
        values, cv2.CV_32F, (patch_n, patch_n), normalize=False,
        borderType=cv2.BORDER_REFLECT101
    )
    sum_reference = box(reference)
    sum_warped = box(warped)
    variance_reference = np.maximum(
        box(reference * reference) - sum_reference * sum_reference / area, 0.0
    )
    variance_warped = np.maximum(
        box(warped * warped) - sum_warped * sum_warped / area, 0.0
    )
    covariance = box(reference * warped) - sum_reference * sum_warped / area
    denominator = np.sqrt(variance_reference * variance_warped) + 1e-6
    ncc = covariance / denominator
    reference_std = np.sqrt(variance_reference / area)
    warped_std = np.sqrt(variance_warped / area)
    return ncc, reference_std, warped_std


def quadratic_peak_offsets(cost_volume: np.ndarray, best_index: np.ndarray) -> np.ndarray:
    """Refine a strict discrete maximum without changing its birth decision.

    The returned offset is expressed in samples of the cost-volume coordinate.
    Only finite, interior, concave three-sample peaks are refined.  Sentinel or
    boundary neighbors leave the discrete winner unchanged.
    """
    if cost_volume.ndim != 3 or best_index.shape != cost_volume.shape[1:]:
        raise ValueError("cost volume and best-index shapes are inconsistent")
    depth_count = cost_volume.shape[0]
    offsets = np.zeros(best_index.shape, dtype=np.float32)
    if depth_count < 3:
        return offsets
    center_index = best_index[None, ...]
    left_index = np.clip(best_index - 1, 0, depth_count - 1)[None, ...]
    right_index = np.clip(best_index + 1, 0, depth_count - 1)[None, ...]
    left = np.take_along_axis(cost_volume, left_index, axis=0)[0].astype(np.float64)
    center = np.take_along_axis(cost_volume, center_index, axis=0)[0].astype(np.float64)
    right = np.take_along_axis(cost_volume, right_index, axis=0)[0].astype(np.float64)
    curvature = left - 2.0 * center + right
    valid = (
        (best_index > 0)
        & (best_index < depth_count - 1)
        & np.isfinite(left)
        & np.isfinite(center)
        & np.isfinite(right)
        & (left > -1.5)
        & (right > -1.5)
        & (center >= left)
        & (center >= right)
        & (curvature < -1e-8)
    )
    raw = np.zeros(best_index.shape, dtype=np.float64)
    np.divide(0.5 * (left - right), curvature, out=raw, where=valid)
    valid &= np.abs(raw) <= 1.0
    offsets[valid] = raw[valid].astype(np.float32)
    return offsets


def safe_quadratic_refinement_mask(
    peak_offset_samples: np.ndarray,
    discrete_depth_m: np.ndarray,
    best_ncc: np.ndarray,
) -> np.ndarray:
    """Select the cap50 zero-regression quadratic-refinement support region.

    This gate never controls point birth.  It only permits a sub-sample inverse-
    depth adjustment after a discrete hypothesis has passed every product gate.
    Thresholds remain explicit because cap56 is an external validation capture,
    not permission to silently broaden the product route.
    """
    if not (
        peak_offset_samples.shape == discrete_depth_m.shape == best_ncc.shape
    ):
        raise ValueError("quadratic refinement gate shapes are inconsistent")
    absolute_offset = np.abs(peak_offset_samples)
    return (
        (absolute_offset >= SAFE_QUADRATIC_MIN_ABS_OFFSET_SAMPLES)
        & (absolute_offset < SAFE_QUADRATIC_MAX_ABS_OFFSET_SAMPLES)
        & (discrete_depth_m < SAFE_QUADRATIC_MAX_DEPTH_M)
        & (best_ncc < SAFE_QUADRATIC_MAX_NCC)
    )


def conservative_quadratic_refinement_mask(
    peak_offset_samples: np.ndarray,
    discrete_depth_m: np.ndarray,
    best_ncc: np.ndarray,
    ncc_margin: np.ndarray,
) -> np.ndarray:
    """Holdout candidate selected from cap50 plus three cap56 design views."""
    if not (
        peak_offset_samples.shape
        == discrete_depth_m.shape
        == best_ncc.shape
        == ncc_margin.shape
    ):
        raise ValueError("conservative quadratic gate shapes are inconsistent")
    absolute_offset = np.abs(peak_offset_samples)
    return (
        (absolute_offset >= CONSERVATIVE_QUADRATIC_MIN_ABS_OFFSET_SAMPLES)
        & (absolute_offset < CONSERVATIVE_QUADRATIC_MAX_ABS_OFFSET_SAMPLES)
        & (discrete_depth_m < CONSERVATIVE_QUADRATIC_MAX_DEPTH_M)
        & (best_ncc < CONSERVATIVE_QUADRATIC_MAX_NCC)
        & (ncc_margin < CONSERVATIVE_QUADRATIC_MAX_MARGIN)
    )


def read_sparse_xyz(path: Path) -> np.ndarray:
    data = path.read_bytes()
    marker = b"end_header\n"
    header_end = data.index(marker) + len(marker)
    header = data[:header_end].decode("ascii")
    count = int(
        next(line.split()[2] for line in header.splitlines() if line.startswith("element vertex"))
    )
    dtype = np.dtype(
        [("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
         ("red", "u1"), ("green", "u1"), ("blue", "u1")]
    )
    vertices = np.frombuffer(data, offset=header_end, count=count, dtype=dtype)
    return np.column_stack([vertices["x"], vertices["y"], vertices["z"]]).astype(np.float64)


def sweep_depth(
    reference,
    reference_gray: np.ndarray,
    reference_K: np.ndarray,
    sources,
    source_grays,
    source_K,
    depths: np.ndarray,
    width: int,
    height: int,
    patch_n: int,
    ncc_min: float,
    depth_margin: float,
    min_views: int,
    peak_exclusion_radius: int,
    quadratic_refine_mode: str = "off",
):
    """Estimate reference-camera Z using only images and known camera poses."""
    yy, xx = np.mgrid[0:height, 0:width]
    pixels = np.stack([xx, yy, np.ones_like(xx)], axis=-1).astype(np.float64)
    rays = pixels @ np.linalg.inv(reference_K).T
    cost_volume = np.full((len(depths), height, width), -2.0, dtype=np.float32)
    view_volume = np.zeros_like(cost_volume, dtype=np.uint8)
    patch_margin = patch_n // 2 + 1
    for depth_index, depth in enumerate(depths):
        camera_points = rays * depth
        world = (camera_points - reference.t) @ reference.R
        scores = []
        valid_rows = []
        for frame, gray, K in zip(sources, source_grays, source_K, strict=True):
            source_camera = world @ frame.R.T + frame.t
            z = source_camera[..., 2]
            homogeneous = source_camera @ K.T
            map_x = (homogeneous[..., 0] / np.where(z > 1e-12, z, 1.0)).astype(np.float32)
            map_y = (homogeneous[..., 1] / np.where(z > 1e-12, z, 1.0)).astype(np.float32)
            valid = (
                (z > 0.05)
                & (map_x >= patch_margin)
                & (map_x < width - patch_margin)
                & (map_y >= patch_margin)
                & (map_y < height - patch_margin)
            )
            warped = cv2.remap(
                gray, map_x, map_y, cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT, borderValue=0
            )
            ncc, reference_std, warped_std = local_zncc(reference_gray, warped, patch_n)
            valid &= (reference_std >= 6.0) & (warped_std >= 6.0)
            scores.append(np.where(valid, ncc, -2.0))
            valid_rows.append(valid)
        stacked = np.stack(scores)
        valid_count = np.stack(valid_rows).sum(axis=0)
        ordered = np.sort(stacked, axis=0)
        selected = ordered[-min_views:]
        selected_mean = selected.mean(axis=0)
        usable = valid_count >= min_views
        cost_volume[depth_index] = np.where(usable, selected_mean, -2.0)
        view_volume[depth_index] = valid_count

    best_index = np.argmax(cost_volume, axis=0)
    best_score = np.take_along_axis(cost_volume, best_index[None, ...], axis=0)[0]
    best_views = np.take_along_axis(view_volume, best_index[None, ...], axis=0)[0]
    suppressed = cost_volume.copy()
    for delta in range(-peak_exclusion_radius, peak_exclusion_radius + 1):
        index = np.clip(best_index + delta, 0, len(depths) - 1)
        np.put_along_axis(suppressed, index[None, ...], -2.0, axis=0)
    second_score = suppressed.max(axis=0)
    score_margin = best_score - second_score
    discrete_best_depth = depths[best_index]
    raw_peak_offset = np.zeros(best_index.shape, dtype=np.float32)
    peak_offset = raw_peak_offset
    best_depth = discrete_best_depth
    if quadratic_refine_mode not in {"off", "safe", "conservative", "all"}:
        raise ValueError(f"unknown quadratic refinement mode: {quadratic_refine_mode}")
    if quadratic_refine_mode != "off":
        inverse_depths = 1.0 / depths
        steps = np.diff(inverse_depths)
        if len(steps) == 0 or not np.allclose(steps, steps[0], rtol=1e-7, atol=1e-12):
            raise ValueError("quadratic refinement requires uniform inverse-depth samples")
        raw_peak_offset = quadratic_peak_offsets(cost_volume, best_index)
        peak_offset = raw_peak_offset
        if quadratic_refine_mode == "safe":
            supported = safe_quadratic_refinement_mask(
                raw_peak_offset, discrete_best_depth, best_score
            )
            peak_offset = np.where(supported, raw_peak_offset, 0.0).astype(np.float32)
        elif quadratic_refine_mode == "conservative":
            supported = conservative_quadratic_refinement_mask(
                raw_peak_offset,
                discrete_best_depth,
                best_score,
                score_margin,
            )
            peak_offset = np.where(supported, raw_peak_offset, 0.0).astype(np.float32)
        refined_inverse_depth = inverse_depths[best_index] + peak_offset * steps[0]
        best_depth = 1.0 / refined_inverse_depth
    accepted = (
        (best_score >= ncc_min)
        & (score_margin >= depth_margin)
        & (best_views >= min_views)
    )
    return {
        "depth": best_depth,
        "discrete_depth": discrete_best_depth,
        "peak_offset_samples": peak_offset,
        "raw_peak_offset_samples": raw_peak_offset,
        "accepted": accepted,
        "best_score": best_score,
        "second_score": second_score,
        "score_margin": score_margin,
        "best_views": best_views,
        "rays": rays,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", choices=("cap50", "cap56"), default="cap50")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=144)
    parser.add_argument("--depth-samples", type=int, default=96)
    parser.add_argument("--depth-min", type=float, default=0.8)
    parser.add_argument("--depth-max", type=float, default=4.3)
    parser.add_argument("--patch-n", type=int, default=5)
    parser.add_argument("--ncc-min", type=float, default=0.75)
    parser.add_argument("--depth-margin", type=float, default=0.03)
    parser.add_argument("--peak-exclusion-radius", type=int, default=2)
    parser.add_argument("--min-views", type=int, default=2)
    parser.add_argument("--consistency-views", type=int, default=0)
    parser.add_argument("--consistency-absolute-m", type=float, default=0.08)
    parser.add_argument("--consistency-relative", type=float, default=0.05)
    parser.add_argument("--min-parallax-deg", type=float, default=0.0)
    parser.add_argument("--reference-index", type=int, default=0)
    parser.add_argument("--floor-ownership-slab-m", type=float, default=0.0)
    quadratic = parser.add_mutually_exclusive_group()
    quadratic.add_argument(
        "--quadratic-refine",
        action="store_true",
        help="apply only the registered cap50 zero-regression support gate",
    )
    quadratic.add_argument(
        "--quadratic-refine-all",
        action="store_true",
        help="diagnostic only: refine every valid concave peak",
    )
    quadratic.add_argument(
        "--quadratic-refine-conservative",
        action="store_true",
        help="holdout candidate: weak-texture near-depth refinement gate",
    )
    parser.add_argument("--source-index", type=int, action="append")
    parser.add_argument("--auto-source-count", type=int, default=0)
    args = parser.parse_args()
    quadratic_refine_mode = (
        "all"
        if args.quadratic_refine_all
        else "conservative"
        if args.quadratic_refine_conservative
        else "safe"
        if args.quadratic_refine
        else "off"
    )
    if args.source_index and args.auto_source_count:
        parser.error("use explicit sources or automatic selection, not both")

    module = load_geometry_module()
    if args.capture == "cap50":
        frames = module.load_frames(META, LEDGER, PHOTOS)
        meta_path = META
        ledger_path = LEDGER
        photo_dir = PHOTOS
        sparse_path = SPARSE
        structural_planes_path = STRUCTURAL_PLANES
        source_indices = (
            args.source_index
            or (
                select_source_indices(
                    frames, args.reference_index, args.auto_source_count
                )
                if args.auto_source_count
                else [1, 2, 3]
            )
        )
    else:
        frames = load_sidecar_frames(module, CAP56_LEDGER, CAP56_PHOTOS)
        meta_path = None
        ledger_path = CAP56_LEDGER
        photo_dir = CAP56_PHOTOS
        sparse_path = CAP56_SPARSE
        structural_planes_path = None
        source_indices = args.source_index or select_source_indices(
            frames,
            args.reference_index,
            args.auto_source_count or 7,
        )
    if args.reference_index in source_indices:
        parser.error("reference index must not also be a source index")
    if not (0 <= args.reference_index < len(frames)) or any(
        not (0 <= index < len(frames)) for index in source_indices
    ):
        parser.error(f"frame index outside [0, {len(frames) - 1}]")
    reference = frames[args.reference_index]
    sources = [frames[index] for index in source_indices]
    selected_frames = [reference, *sources]
    selected_grays = [load_gray(frame, args.width, args.height) for frame in selected_frames]
    selected_K = [scaled_intrinsics(frame, args.width, args.height) for frame in selected_frames]
    reference_gray = selected_grays[0]
    reference_K = selected_K[0]
    inverse_depth = np.linspace(
        1.0 / args.depth_max, 1.0 / args.depth_min, args.depth_samples,
        dtype=np.float64,
    )
    depths = 1.0 / inverse_depth
    started = time.perf_counter()
    sweep = sweep_depth(
        reference, reference_gray, reference_K,
        sources, selected_grays[1:], selected_K[1:], depths,
        args.width, args.height, args.patch_n, args.ncc_min,
        args.depth_margin, args.min_views, args.peak_exclusion_radius,
        quadratic_refine_mode,
    )
    best_depth = sweep["depth"]
    gate_depth = sweep["discrete_depth"]
    best_score = sweep["best_score"]
    second_score = sweep["second_score"]
    score_margin = sweep["score_margin"]
    best_views = sweep["best_views"]
    pre_consistency_accepted = sweep["accepted"]
    accepted = pre_consistency_accepted.copy()
    consistency_count = np.zeros_like(best_views, dtype=np.uint8)
    max_consistent_parallax = np.zeros_like(best_score, dtype=np.float32)
    consistency_errors = []
    proposal_depth_maps = [best_depth.astype(np.float32)]
    proposal_accepted_maps = [pre_consistency_accepted.copy()]
    # Birth gates deliberately stay on the frozen discrete winner.  Quadratic
    # refinement only changes the geometry of points that already earned a
    # product identity, so enabling it cannot trade coverage for precision.
    gate_reference_world = (
        sweep["rays"] * gate_depth[..., None] - reference.t
    ) @ reference.R
    reference_world = (sweep["rays"] * best_depth[..., None] - reference.t) @ reference.R
    if args.consistency_views > 0:
        reference_center = -reference.t @ reference.R
        reference_vector = gate_reference_world - reference_center
        reference_norm = np.linalg.norm(reference_vector, axis=-1)
        for source_offset, source in enumerate(sources, start=1):
            reciprocal_offsets = [index for index in range(len(selected_frames)) if index != source_offset]
            reciprocal = sweep_depth(
                source,
                selected_grays[source_offset],
                selected_K[source_offset],
                [selected_frames[index] for index in reciprocal_offsets],
                [selected_grays[index] for index in reciprocal_offsets],
                [selected_K[index] for index in reciprocal_offsets],
                depths, args.width, args.height, args.patch_n, args.ncc_min,
                args.depth_margin, args.min_views, args.peak_exclusion_radius,
                quadratic_refine_mode,
            )
            proposal_depth_maps.append(reciprocal["depth"].astype(np.float32))
            proposal_accepted_maps.append(reciprocal["accepted"].copy())
            source_camera = gate_reference_world @ source.R.T + source.t
            predicted_z = source_camera[..., 2]
            projected = source_camera @ selected_K[source_offset].T
            projected_x = projected[..., 0] / np.where(predicted_z > 1e-12, predicted_z, 1.0)
            projected_y = projected[..., 1] / np.where(predicted_z > 1e-12, predicted_z, 1.0)
            sample_x = np.rint(projected_x).astype(np.int32)
            sample_y = np.rint(projected_y).astype(np.int32)
            inside = (
                (predicted_z > 0.05)
                & (sample_x >= 0) & (sample_x < args.width)
                & (sample_y >= 0) & (sample_y < args.height)
            )
            clipped_x = np.clip(sample_x, 0, args.width - 1)
            clipped_y = np.clip(sample_y, 0, args.height - 1)
            reciprocal_depth = reciprocal["discrete_depth"][clipped_y, clipped_x]
            reciprocal_accepted = reciprocal["accepted"][clipped_y, clipped_x]
            error = np.abs(reciprocal_depth - predicted_z)
            tolerance = np.maximum(
                args.consistency_absolute_m,
                args.consistency_relative * np.maximum(predicted_z, 0.0),
            )
            source_center = -source.t @ source.R
            source_vector = gate_reference_world - source_center
            source_norm = np.linalg.norm(source_vector, axis=-1)
            cosine = np.sum(reference_vector * source_vector, axis=-1) / np.maximum(
                reference_norm * source_norm, 1e-12
            )
            parallax_deg = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
            photometrically_consistent = inside & reciprocal_accepted & (error <= tolerance)
            max_consistent_parallax = np.maximum(
                max_consistent_parallax,
                np.where(photometrically_consistent, parallax_deg, 0.0),
            )
            consistent = photometrically_consistent & (parallax_deg >= args.min_parallax_deg)
            consistency_count += consistent.astype(np.uint8)
            consistency_errors.append(error[inside & reciprocal_accepted])
        accepted &= consistency_count >= args.consistency_views
    post_consistency_accepted = accepted.copy()

    floor_distance = None
    if structural_planes_path is not None:
        structural_planes = json.loads(structural_planes_path.read_text())
        floor = structural_planes["floor"]
        floor_normal = np.asarray(floor["normal"], dtype=np.float64)
        floor_normal /= np.linalg.norm(floor_normal)
        floor_value = float(floor["plane_value_n_dot_x"])
        floor_distance = reference_world @ floor_normal - floor_value
        if args.floor_ownership_slab_m > 0.0:
            # Free-depth hypotheses in/below this slab never become emitted points.
            # The independent known-plane generator owns that spatial region.
            accepted &= floor_distance > args.floor_ownership_slab_m
    elif args.floor_ownership_slab_m > 0.0:
        parser.error("floor ownership requires a certified structural plane")

    sparse_xyz = read_sparse_xyz(sparse_path)
    sparse_camera = sparse_xyz @ reference.R.T + reference.t
    sparse_z = sparse_camera[:, 2]
    sparse_uv = sparse_camera @ reference_K.T
    sparse_uv = sparse_uv[:, :2] / np.where(sparse_z[:, None] > 1e-12, sparse_z[:, None], 1.0)
    sparse_x = np.rint(sparse_uv[:, 0]).astype(np.int32)
    sparse_y = np.rint(sparse_uv[:, 1]).astype(np.int32)
    inside = (
        (sparse_z > 0.05)
        & (sparse_x >= 0) & (sparse_x < args.width)
        & (sparse_y >= 0) & (sparse_y < args.height)
    )
    sparse_x = sparse_x[inside]
    sparse_y = sparse_y[inside]
    sparse_z = sparse_z[inside]
    sparse_depth = np.full((args.height, args.width), np.inf, dtype=np.float64)
    np.minimum.at(sparse_depth, (sparse_y, sparse_x), sparse_z)
    comparable = accepted & np.isfinite(sparse_depth)
    absolute_error = np.abs(best_depth[comparable] - sparse_depth[comparable])
    relative_error = absolute_error / np.maximum(sparse_depth[comparable], 1e-6)
    sparse_true_depth = sparse_depth[comparable]
    elapsed = time.perf_counter() - started

    args.output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output_dir / "depth_sweep.npz",
        depth_m=best_depth.astype(np.float32),
        discrete_depth_m=sweep["discrete_depth"].astype(np.float32),
        peak_offset_samples=sweep["peak_offset_samples"],
        raw_peak_offset_samples=sweep["raw_peak_offset_samples"],
        accepted=accepted,
        best_ncc=best_score,
        second_ncc=second_score,
        ncc_margin=score_margin,
        views=best_views,
        consistency_views=consistency_count,
        max_consistent_parallax_deg=max_consistent_parallax,
        floor_distance_m=(
            floor_distance.astype(np.float32)
            if floor_distance is not None
            else np.empty((0, 0), dtype=np.float32)
        ),
        proposal_frame_indices=np.asarray(
            [args.reference_index, *source_indices], dtype=np.int32
        ),
        proposal_depth_maps_m=np.stack(proposal_depth_maps),
        proposal_accepted_maps=np.stack(proposal_accepted_maps),
        sparse_depth_eval_m=sparse_depth.astype(np.float32),
    )
    visualization = np.zeros((args.height, args.width, 3), dtype=np.uint8)
    normalized_depth = np.clip(
        (best_depth - args.depth_min) / (args.depth_max - args.depth_min), 0.0, 1.0
    )
    visualization[:] = cv2.applyColorMap(
        np.rint(normalized_depth * 255).astype(np.uint8), cv2.COLORMAP_TURBO
    )
    visualization[~accepted] = 0
    cv2.imwrite(str(args.output_dir / "accepted_depth.png"), visualization)

    def quantiles(values):
        if len(values) == 0:
            return None
        return {
            str(q): float(np.percentile(values, q))
            for q in (0, 10, 25, 50, 75, 90, 95, 99, 100)
        }

    def error_summary(mask):
        values = absolute_error[mask]
        if len(values) == 0:
            return None
        return {
            "count": int(len(values)),
            "absolute_error_m": quantiles(values),
            "within_0_05_m": float(np.mean(values <= 0.05)),
            "within_0_10_m": float(np.mean(values <= 0.10)),
            "within_0_20_m": float(np.mean(values <= 0.20)),
            "within_0_50_m": float(np.mean(values <= 0.50)),
        }

    depth_error_strata = {}
    for label, low, high in (
        ("0_8_to_1_5_m", 0.8, 1.5),
        ("1_5_to_2_5_m", 1.5, 2.5),
        ("2_5_to_3_5_m", 2.5, 3.5),
        ("3_5_to_4_3_m", 3.5, 4.3),
    ):
        depth_error_strata[label] = error_summary(
            (sparse_true_depth >= low) & (sparse_true_depth < high)
        )

    if floor_distance is None:
        floor_distance_post_consistency = None
        floor_distance_accepted = None
        floor_ghost_post_consistency = 0
        floor_ghost_emitted = 0
        below_floor_emitted = 0
    else:
        floor_distance_post_consistency = quantiles(
            floor_distance[post_consistency_accepted]
        )
        floor_distance_accepted = quantiles(floor_distance[accepted])
        floor_ghost_post_consistency = int(
            (
                post_consistency_accepted
                & (floor_distance >= -0.050)
                & (floor_distance < -0.015)
            ).sum()
        )
        floor_ghost_emitted = int(
            (
                accepted
                & (floor_distance >= -0.050)
                & (floor_distance < -0.015)
            ).sum()
        )
        below_floor_emitted = int(
            (accepted & (floor_distance < -0.015)).sum()
        )

    quadratic_gate_config = None
    if quadratic_refine_mode == "safe":
        quadratic_gate_config = {
            "profile": "cap50_design_v1_failed_cap56_external_validation",
            "min_abs_offset_samples_inclusive": SAFE_QUADRATIC_MIN_ABS_OFFSET_SAMPLES,
            "max_abs_offset_samples_exclusive": SAFE_QUADRATIC_MAX_ABS_OFFSET_SAMPLES,
            "max_ncc_exclusive": SAFE_QUADRATIC_MAX_NCC,
            "max_discrete_depth_m_exclusive": SAFE_QUADRATIC_MAX_DEPTH_M,
            "controls_point_birth": False,
        }
    elif quadratic_refine_mode == "conservative":
        quadratic_gate_config = {
            "profile": "cap50_plus_cap56_design_views_v2_pending_holdout",
            "min_abs_offset_samples_inclusive": CONSERVATIVE_QUADRATIC_MIN_ABS_OFFSET_SAMPLES,
            "max_abs_offset_samples_exclusive": CONSERVATIVE_QUADRATIC_MAX_ABS_OFFSET_SAMPLES,
            "max_ncc_exclusive": CONSERVATIVE_QUADRATIC_MAX_NCC,
            "max_ncc_margin_exclusive": CONSERVATIVE_QUADRATIC_MAX_MARGIN,
            "max_discrete_depth_m_exclusive": CONSERVATIVE_QUADRATIC_MAX_DEPTH_M,
            "controls_point_birth": False,
        }

    metrics = {
        "schema": "pocketworld_model_free_known_pose_depth_sweep_v1",
        "route": "self_developed_model_free_detector_free_known_pose_mvs",
        "license": {
            "learned_model": None,
            "training_data": None,
            "third_party_matcher_output_consumed": False,
            "production_algorithm_dependencies": ["numpy", "opencv_for_host_probe_only"],
        },
        "inputs": {
            "frame_meta": (
                {"path": str(meta_path.relative_to(ROOT)), "sha256": sha256(meta_path)}
                if meta_path is not None
                else None
            ),
            "ledger": {
                "path": str(ledger_path.relative_to(ROOT)),
                "sha256": sha256(ledger_path),
            },
            "photo_bundle": {
                "path": str(photo_dir.relative_to(ROOT)),
                "frame_count": len(frames),
                "ordered_jpeg_sidecar_sha256": capture_bundle_sha256(frames),
            },
            "sparse_eval_only": {
                "path": str(sparse_path.relative_to(ROOT)),
                "sha256": sha256(sparse_path),
            },
            "structural_planes": (
                {
                    "path": str(structural_planes_path.relative_to(ROOT)),
                    "sha256": sha256(structural_planes_path),
                }
                if structural_planes_path is not None
                else None
            ),
            "reference": {
                "index": args.reference_index,
                "frame_id": reference.frame_id,
                "file": reference.image_path.name,
            },
            "sources": [
                {"index": index, "frame_id": frame.frame_id, "file": frame.image_path.name}
                for index, frame in zip(source_indices, sources, strict=True)
            ],
        },
        "config": {
            "capture": args.capture,
            "width": args.width,
            "height": args.height,
            "depth_samples": args.depth_samples,
            "inverse_depth_uniform": True,
            "depth_min_m": args.depth_min,
            "depth_max_m": args.depth_max,
            "patch_n": args.patch_n,
            "ncc_min": args.ncc_min,
            "second_peak_exclusion_radius_samples": args.peak_exclusion_radius,
            "depth_ncc_margin": args.depth_margin,
            "min_views": args.min_views,
            "consistency_views": args.consistency_views,
            "consistency_absolute_m": args.consistency_absolute_m,
            "consistency_relative": args.consistency_relative,
            "min_parallax_deg": args.min_parallax_deg,
            "floor_ownership_slab_m": args.floor_ownership_slab_m,
            "quadratic_inverse_depth_refinement_mode": quadratic_refine_mode,
            "quadratic_refinement_gate": quadratic_gate_config,
        },
        "metrics": {
            "pixels": args.width * args.height,
            "accepted_pixels": int(accepted.sum()),
            "accepted_fraction": float(accepted.mean()),
            "pre_consistency_accepted_pixels": int(pre_consistency_accepted.sum()),
            "consistency_rejected_pixels": int(
                (pre_consistency_accepted & ~post_consistency_accepted).sum()
            ),
            "post_consistency_accepted_pixels": int(post_consistency_accepted.sum()),
            "floor_ownership_rejected_pixels": int(
                (post_consistency_accepted & ~accepted).sum()
            ),
            "floor_distance_m_post_consistency": floor_distance_post_consistency,
            "floor_distance_m_accepted": floor_distance_accepted,
            "floor_ghost_band_minus50_to_minus15mm_post_consistency": floor_ghost_post_consistency,
            "floor_ghost_band_minus50_to_minus15mm_emitted": floor_ghost_emitted,
            "below_floor_minus15mm_emitted": below_floor_emitted,
            "quadratic_refined_pixels": int(
                np.count_nonzero(sweep["peak_offset_samples"])
            ),
            "quadratic_candidate_pixels": int(
                np.count_nonzero(sweep["raw_peak_offset_samples"])
            ),
            "quadratic_depth_adjustment_m": quantiles(
                np.abs(best_depth - sweep["discrete_depth"])[accepted]
            ),
            "consistency_count_preaccepted": quantiles(
                consistency_count[pre_consistency_accepted]
            ),
            "reciprocal_depth_error_m": quantiles(
                np.concatenate(consistency_errors) if consistency_errors else np.empty(0)
            ),
            "max_consistent_parallax_deg_accepted": quantiles(
                max_consistent_parallax[accepted]
            ),
            "best_ncc_quantiles_accepted": quantiles(best_score[accepted]),
            "ncc_margin_quantiles_accepted": quantiles(score_margin[accepted]),
            "sparse_projected_samples": int(len(sparse_z)),
            "sparse_zbuffer_pixels": int(np.isfinite(sparse_depth).sum()),
            "sparse_comparable_pixels": int(comparable.sum()),
            "sparse_absolute_depth_error_m": quantiles(absolute_error),
            "sparse_relative_depth_error": quantiles(relative_error),
            "sparse_accuracy": error_summary(np.ones(len(absolute_error), dtype=bool)),
            "sparse_error_by_true_depth": depth_error_strata,
            "elapsed_seconds": elapsed,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    }
    metrics_path = args.output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
