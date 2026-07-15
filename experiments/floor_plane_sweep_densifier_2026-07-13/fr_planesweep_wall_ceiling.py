#!/usr/bin/env python3
"""Pure-A tiled known-plane plane sweep for floors, walls, and ceilings.

The executable path consumes only first-party images, camera intrinsics/poses,
and known or sparse-fitted plane equations.  It never reads feature matches or
learned-matcher output.  Candidate points are accepted only by multi-view ZNCC,
view-count, texture, cheirality, grazing-angle, and parallax gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image


FLIP_ARKIT_TO_CV = np.diag([1.0, -1.0, -1.0])
GRAY_WEIGHTS = np.array([0.299, 0.587, 0.114], dtype=np.float64)


@dataclass(frozen=True)
class Frame:
    frame_id: int
    image_path: Path
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    C: np.ndarray
    width: int
    height: int


@dataclass(frozen=True)
class SweepConfig:
    grid_m: float = 0.05
    patch_n: int = 7
    patch_radius_m: float = 0.015
    min_std: float = 6.0
    ncc_min: float = 0.70
    min_views: int = 3
    min_parallax_deg: float = 5.0
    max_views: int = 8
    base_max_views: int = 0
    rescue_min_ncc: float | None = None
    rescue_min_parallax_deg: float | None = None
    rescue_min_views: int = 0
    max_graze_deg: float = 72.0
    image_margin_px: float = 2.0
    tile_points: int = 256
    image_cache_images: int = 12
    depth_competition_offsets_m: tuple[float, ...] = ()
    depth_ncc_margin: float = 0.02


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_frames(meta_path: Path, ledger_path: Path, photo_dir: Path) -> list[Frame]:
    meta = json.loads(meta_path.read_text())
    ledger_by_name = {}
    for line in ledger_path.read_text().splitlines():
        if not line:
            continue
        row = json.loads(line)
        ledger_by_name[Path(row["jpegPath"]).name] = row
    work_width = int(meta["work_w"])
    work_height = int(meta["work_h"])
    frames = []
    for row in meta["frames"]:
        source_name = row["src"]
        ledger = ledger_by_name.get(source_name)
        image_path = photo_dir / source_name
        if ledger is None or not image_path.is_file():
            continue
        with Image.open(image_path) as image:
            width, height = image.size
        scale_x = width / work_width
        scale_y = height / work_height
        K = np.array(
            [
                [float(row["fx"]) * scale_x, 0.0, float(row["cx"]) * scale_x],
                [0.0, float(row["fy"]) * scale_y, float(row["cy"]) * scale_y],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        camera_to_world_arkit = np.asarray(row["extrinsic"], dtype=np.float64).reshape(4, 4).T
        center = camera_to_world_arkit[:3, 3].copy()
        camera_to_world_cv = camera_to_world_arkit[:3, :3] @ FLIP_ARKIT_TO_CV
        R = camera_to_world_cv.T
        t = -R @ center
        ledger_center = np.asarray(ledger["arkitCameraCenterWorld"], dtype=np.float64)
        if np.linalg.norm(ledger_center - center) > 1e-4:
            raise ValueError(f"pose center mismatch for {source_name}")
        frames.append(
            Frame(
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
    frames.sort(key=lambda frame: frame.frame_id)
    if len(frames) < 3:
        raise ValueError("fewer than three usable first-party frames")
    return frames


def bilinear_rgb(image: np.ndarray, xy: np.ndarray) -> np.ndarray:
    x = xy[:, 0]
    y = xy[:, 1]
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, image.shape[1] - 1)
    y1 = np.clip(y0 + 1, 0, image.shape[0] - 1)
    x0 = np.clip(x0, 0, image.shape[1] - 1)
    y0 = np.clip(y0, 0, image.shape[0] - 1)
    wx = x - x0
    wy = y - y0
    top = image[y0, x0].astype(np.float64) * (1.0 - wx[:, None]) + image[y0, x1].astype(
        np.float64
    ) * wx[:, None]
    bottom = image[y1, x0].astype(np.float64) * (1.0 - wx[:, None]) + image[
        y1, x1
    ].astype(np.float64) * wx[:, None]
    return top * (1.0 - wy[:, None]) + bottom * wy[:, None]


def largest_consistent_clique(ncc: np.ndarray, threshold: float, minimum: int) -> np.ndarray:
    """Return the largest all-pairs-consistent view set, not a star approximation."""
    count = len(ncc)
    if count < minimum:
        return np.empty(0, dtype=np.int32)
    neighbors = []
    for row in range(count):
        mask = 0
        for column in range(count):
            if row != column and ncc[row, column] >= threshold:
                mask |= 1 << column
        neighbors.append(mask)
    best_indices: tuple[int, ...] = ()
    best_median = -math.inf

    def consider(indices: tuple[int, ...]) -> None:
        nonlocal best_indices, best_median
        size = len(indices)
        if size < minimum or size < len(best_indices):
            return
        sub = ncc[np.ix_(indices, indices)]
        median = float(np.median(sub[np.triu_indices(size, 1)]))
        if size > len(best_indices) or median > best_median:
            best_indices = indices
            best_median = median

    def search(indices: tuple[int, ...], candidates: int) -> None:
        if len(indices) + candidates.bit_count() < max(minimum, len(best_indices)):
            return
        if candidates == 0:
            consider(indices)
            return
        remaining = candidates
        while remaining:
            if len(indices) + remaining.bit_count() < max(minimum, len(best_indices)):
                break
            lowest = remaining & -remaining
            vertex = lowest.bit_length() - 1
            search(indices + (vertex,), remaining & neighbors[vertex])
            remaining &= ~lowest

    search((), (1 << count) - 1)
    return np.asarray(best_indices, dtype=np.int32)


def unique_depth_winner(
    center_views: int,
    center_ncc: float,
    alternatives: list[tuple[int, float]],
    ncc_margin: float,
) -> tuple[bool, float | None]:
    """Require the selected plane to beat every accepted neighboring depth."""
    if not alternatives:
        return True, None
    best_alternative_ncc = max(ncc for _, ncc in alternatives)
    unique = all(
        center_views >= views and center_ncc >= ncc + ncc_margin
        for views, ncc in alternatives
    )
    return unique, center_ncc - best_alternative_ncc


def passes_rescue_gate(
    evidence: dict,
    minimum_ncc: float | None,
    minimum_parallax_deg: float | None,
    minimum_views: int,
) -> bool:
    return (
        (minimum_ncc is None or evidence["ncc"] >= minimum_ncc)
        and (
            minimum_parallax_deg is None
            or evidence["parallax"] >= minimum_parallax_deg
        )
        and evidence["views"] >= minimum_views
    )


def surface_grid(surface: dict, floor: dict, grid_m: float, offset_m: float = 0.0) -> np.ndarray:
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    axis_u = np.asarray(surface["basis_u"], dtype=np.float64)
    axis_u /= np.linalg.norm(axis_u)
    value = float(surface["plane_value_n_dot_x"]) + offset_m
    u0, u1 = [float(value) for value in surface["bounds_u_m"]]
    u_values = np.arange(u0, u1 + grid_m * 0.25, grid_m)
    if surface["kind"] in {"floor", "ceiling"}:
        axis_v = np.asarray(surface["basis_v"], dtype=np.float64)
        axis_v /= np.linalg.norm(axis_v)
        v0, v1 = [float(value) for value in surface["bounds_v_m"]]
        v_values = np.arange(v0, v1 + grid_m * 0.25, grid_m)
        origin = value * normal
    elif surface["kind"] == "wall":
        axis_v = np.asarray(floor["normal"], dtype=np.float64)
        axis_v /= np.linalg.norm(axis_v)
        v0, v1 = [float(value) for value in surface["bounds_height_m"]]
        v_values = np.arange(v0, v1 + grid_m * 0.25, grid_m)
        origin = value * normal + float(floor["plane_value_n_dot_x"]) * axis_v
    else:
        raise ValueError(f"unsupported surface kind {surface['kind']!r}")
    uu, vv = np.meshgrid(u_values, v_values, indexing="ij")
    return origin + uu.reshape(-1, 1) * axis_u + vv.reshape(-1, 1) * axis_v


def select_surfaces(
    planes: dict,
    requested_ids: list[str] | None,
    allow_uncertified: bool,
) -> list[dict]:
    surfaces = list(planes["surfaces"])
    floor = planes.get("floor")
    if floor and all(
        key in floor
        for key in ("surface_id", "kind", "bounds_u_m", "bounds_v_m")
    ):
        surfaces.insert(0, floor)
    if requested_ids:
        requested = set(requested_ids)
        surfaces = [surface for surface in surfaces if surface["surface_id"] in requested]
    if not allow_uncertified:
        surfaces = [surface for surface in surfaces if surface.get("certified_for_generation") is True]
    return surfaces


def patch_offsets(surface: dict, floor: dict, config: SweepConfig) -> np.ndarray:
    axis_u = np.asarray(surface["basis_u"], dtype=np.float64)
    axis_u /= np.linalg.norm(axis_u)
    if surface["kind"] == "wall":
        axis_v = np.asarray(floor["normal"], dtype=np.float64)
    else:
        axis_v = np.asarray(surface["basis_v"], dtype=np.float64)
    axis_v /= np.linalg.norm(axis_v)
    values = np.linspace(-config.patch_radius_m, config.patch_radius_m, config.patch_n)
    uu, vv = np.meshgrid(values, values, indexing="ij")
    return uu.reshape(-1, 1) * axis_u + vv.reshape(-1, 1) * axis_v


def project_centers(points: np.ndarray, frames: list[Frame], normal: np.ndarray, config: SweepConfig):
    count_frames = len(frames)
    count_points = len(points)
    visible = np.zeros((count_frames, count_points), dtype=bool)
    head_on = np.zeros((count_frames, count_points), dtype=np.float64)
    centers = np.empty((count_frames, count_points, 2), dtype=np.float64)
    for frame_index, frame in enumerate(frames):
        camera_points = (frame.R @ points.T).T + frame.t
        depth = camera_points[:, 2]
        homogeneous = (frame.K @ camera_points.T).T
        xy = homogeneous[:, :2] / np.where(depth[:, None] > 1e-12, depth[:, None], 1.0)
        rays = points - frame.C
        ray_norm = np.linalg.norm(rays, axis=1) + 1e-12
        cosine = np.abs(rays @ normal) / ray_norm
        centers[frame_index] = xy
        head_on[frame_index] = cosine
        visible[frame_index] = (
            (depth > 0.05)
            & (xy[:, 0] > config.image_margin_px)
            & (xy[:, 0] < frame.width - 1 - config.image_margin_px)
            & (xy[:, 1] > config.image_margin_px)
            & (xy[:, 1] < frame.height - 1 - config.image_margin_px)
            & (cosine > math.cos(math.radians(config.max_graze_deg)))
        )
    return visible, head_on, centers


def select_point_views(visible: np.ndarray, head_on: np.ndarray, maximum: int) -> list[int]:
    """Select each point's own most head-on visible views with deterministic tie-breaking."""
    candidate = np.flatnonzero(visible)
    if not len(candidate):
        return []
    order = np.lexsort((candidate, -head_on[candidate]))
    return [int(index) for index in candidate[order[:maximum]]]


class ImageCache:
    """Small LRU cache that bounds decoded high-resolution image memory."""

    def __init__(self, frames: list[Frame], capacity: int):
        if capacity <= 0:
            raise ValueError("image cache capacity must be positive")
        self.frames = frames
        self.capacity = capacity
        self.images: OrderedDict[int, np.ndarray] = OrderedDict()
        self.current_bytes = 0
        self.peak_bytes = 0
        self.loads = 0

    def get_many(self, indices: Iterable[int]) -> dict[int, np.ndarray]:
        requested = list(dict.fromkeys(int(index) for index in indices))
        if len(requested) > self.capacity:
            raise ValueError("requested view set exceeds image cache capacity")
        protected = set(requested)
        for index in requested:
            if index in self.images:
                self.images.move_to_end(index)
        for index in requested:
            if index in self.images:
                continue
            while len(self.images) >= self.capacity:
                evict = next(key for key in self.images if key not in protected)
                array = self.images.pop(evict)
                self.current_bytes -= array.nbytes
            with Image.open(self.frames[index].image_path) as source:
                array = np.asarray(source.convert("RGB"), dtype=np.uint8)
            self.images[index] = array
            self.current_bytes += array.nbytes
            self.peak_bytes = max(self.peak_bytes, self.current_bytes)
            self.loads += 1
        return {index: self.images[index] for index in requested}


def load_selected_images(frames: list[Frame], indices: Iterable[int]) -> tuple[dict[int, np.ndarray], int]:
    images = {}
    total_bytes = 0
    for index in indices:
        with Image.open(frames[index].image_path) as source:
            array = np.asarray(source.convert("RGB"), dtype=np.uint8)
        images[index] = array
        total_bytes += array.nbytes
    return images, total_bytes


def score_point_hypothesis(
    point: np.ndarray,
    offsets: np.ndarray,
    frames: list[Frame],
    candidate: list[int],
    images: dict[int, np.ndarray],
    config: SweepConfig,
) -> tuple[dict | None, str | None]:
    if len(candidate) < config.min_views:
        return None, "few_geometry_views"
    samples = point[None, :] + offsets
    gray_patches = []
    center_colors = []
    used = []
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
        rgb = bilinear_rgb(images[frame_index], xy)
        gray = rgb @ GRAY_WEIGHTS
        if float(gray.std()) < config.min_std:
            continue
        gray_patches.append(gray)
        center_colors.append(rgb[len(rgb) // 2])
        used.append(frame_index)
    if len(used) < config.min_views:
        return None, "few_texture_views"
    patches = np.stack(gray_patches)
    normalized = patches - patches.mean(axis=1, keepdims=True)
    normalized /= np.linalg.norm(normalized, axis=1, keepdims=True) + 1e-9
    ncc = normalized @ normalized.T
    np.fill_diagonal(ncc, 1.0)
    clique = largest_consistent_clique(ncc, config.ncc_min, config.min_views)
    if len(clique) < config.min_views:
        return None, "few_zncc_views"
    clique_frames = [used[index] for index in clique]
    rays = np.stack([point - frames[index].C for index in clique_frames])
    rays /= np.linalg.norm(rays, axis=1, keepdims=True) + 1e-12
    cosine = np.clip(rays @ rays.T, -1.0, 1.0)
    parallax = float(np.degrees(np.arccos(cosine)).max())
    if parallax < config.min_parallax_deg:
        return None, "low_parallax"
    sub = ncc[np.ix_(clique, clique)]
    pair_ncc = sub[np.triu_indices(len(clique), 1)]
    return {
        "views": len(clique),
        "parallax": parallax,
        "ncc": float(np.median(pair_ncc)),
        "candidate_views": len(candidate),
        "color": np.median(np.stack([center_colors[index] for index in clique]), axis=0),
    }, None


def sweep_surface(
    surface: dict,
    floor: dict,
    frames: list[Frame],
    config: SweepConfig,
    offset_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    points = surface_grid(surface, floor, config.grid_m, offset_m)
    offsets = patch_offsets(surface, floor, config)
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    accepted_points = []
    accepted_colors = []
    accepted_meta = []
    rejected = {
        "few_geometry_views": 0,
        "few_texture_views": 0,
        "few_zncc_views": 0,
        "low_parallax": 0,
        "ambiguous_depth": 0,
        "rescue_quality": 0,
    }
    base_accepted = 0
    rescue_accepted = 0
    accepted_depth_margins = []
    image_cache = ImageCache(frames, max(config.image_cache_images, config.max_views))
    tiles = 0
    start = time.perf_counter()
    for tile_start in range(0, len(points), config.tile_points):
        tile = points[tile_start : tile_start + config.tile_points]
        visible, head_on, _ = project_centers(tile, frames, normal, config)
        tiles += 1
        for local_index, point in enumerate(tile):
            candidate = select_point_views(
                visible[:, local_index], head_on[:, local_index], config.max_views
            )
            images = image_cache.get_many(candidate) if candidate else {}
            base_count = (
                min(config.base_max_views, config.max_views)
                if config.base_max_views > 0
                else config.max_views
            )
            base_candidate = candidate[:base_count]
            center, reason = score_point_hypothesis(
                point, offsets, frames, base_candidate, images, config
            )
            accepted_by_rescue = False
            used_candidate = base_candidate
            if center is None and base_count < config.max_views and len(candidate) > base_count:
                rescue, rescue_reason = score_point_hypothesis(
                    point, offsets, frames, candidate, images, config
                )
                if rescue is not None and passes_rescue_gate(
                    rescue,
                    config.rescue_min_ncc,
                    config.rescue_min_parallax_deg,
                    config.rescue_min_views,
                ):
                    center = rescue
                    reason = None
                    accepted_by_rescue = True
                    used_candidate = candidate
                elif rescue is not None:
                    reason = "rescue_quality"
                else:
                    reason = rescue_reason
            if center is None:
                rejected[reason] += 1
                continue
            alternatives = []
            for depth_offset in config.depth_competition_offsets_m:
                shifted = point + normal * depth_offset
                alt_visible, _, _ = project_centers(
                    shifted[None, :], frames, normal, config
                )
                alt_candidate = [index for index in used_candidate if alt_visible[index, 0]]
                alternative, _ = score_point_hypothesis(
                    shifted, offsets, frames, alt_candidate, images, config
                )
                if alternative is not None:
                    alternatives.append((alternative["views"], alternative["ncc"]))
            unique, observed_margin = unique_depth_winner(
                center["views"], center["ncc"], alternatives, config.depth_ncc_margin
            )
            if not unique:
                rejected["ambiguous_depth"] += 1
                continue
            if observed_margin is not None:
                accepted_depth_margins.append(observed_margin)
            accepted_points.append(point)
            accepted_colors.append(center["color"])
            accepted_meta.append(
                [center["views"], center["parallax"], center["ncc"], center["candidate_views"]]
            )
            if accepted_by_rescue:
                rescue_accepted += 1
            else:
                base_accepted += 1
    elapsed = time.perf_counter() - start
    accepted_points_array = np.asarray(accepted_points, dtype=np.float64).reshape(-1, 3)
    accepted_colors_array = np.asarray(accepted_colors, dtype=np.float64).reshape(-1, 3)
    accepted_meta_array = np.asarray(accepted_meta, dtype=np.float64).reshape(-1, 4)
    if len(accepted_points_array):
        axis_u = np.asarray(surface["basis_u"], dtype=np.float64)
        axis_v = (
            np.asarray(floor["normal"], dtype=np.float64)
            if surface["kind"] == "wall"
            else np.asarray(surface["basis_v"], dtype=np.float64)
        )
        cells = np.floor(
            np.column_stack([accepted_points_array @ axis_u, accepted_points_array @ axis_v]) / 0.05
        ).astype(np.int64)
        coverage_cells = int(len(np.unique(cells, axis=0)))
    else:
        coverage_cells = 0
    metrics = {
        "surface_id": surface["surface_id"],
        "kind": surface["kind"],
        "plane_offset_m": offset_m,
        "grid_candidates": len(points),
        "accepted": len(accepted_points_array),
        "base_accepted": base_accepted,
        "rescue_accepted": rescue_accepted,
        "acceptance_rate": len(accepted_points_array) / len(points) if len(points) else 0.0,
        "coverage_cells_5cm": coverage_cells,
        "rejected": rejected,
        "zncc_median": float(np.median(accepted_meta_array[:, 2])) if len(accepted_meta_array) else None,
        "zncc_p10": float(np.percentile(accepted_meta_array[:, 2], 10)) if len(accepted_meta_array) else None,
        "views_median": float(np.median(accepted_meta_array[:, 0])) if len(accepted_meta_array) else None,
        "parallax_median_deg": float(np.median(accepted_meta_array[:, 1])) if len(accepted_meta_array) else None,
        "elapsed_s": elapsed,
        "tiles": tiles,
        "peak_loaded_image_bytes": image_cache.peak_bytes,
        "decoded_image_loads": image_cache.loads,
        "depth_competition_offsets_m": list(config.depth_competition_offsets_m),
        "depth_ncc_margin_required": config.depth_ncc_margin,
        "depth_ncc_margin_observed_min": (
            float(np.min(accepted_depth_margins)) if accepted_depth_margins else None
        ),
        "depth_ncc_margin_observed_median": (
            float(np.median(accepted_depth_margins)) if accepted_depth_margins else None
        ),
    }
    return accepted_points_array, accepted_colors_array, accepted_meta_array, metrics


def write_ply(path: Path, xyz: np.ndarray, rgb: np.ndarray, metadata: np.ndarray) -> None:
    with path.open("w", encoding="utf-8") as stream:
        stream.write("ply\nformat ascii 1.0\n")
        stream.write(f"element vertex {len(xyz)}\n")
        stream.write("property float x\nproperty float y\nproperty float z\n")
        stream.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        stream.write("property float nviews\nproperty float parallax_deg\n")
        stream.write("property float zncc_median\nproperty float candidate_views\nend_header\n")
        for point, color, meta in zip(xyz, rgb, metadata, strict=True):
            color_u8 = np.clip(np.rint(color), 0, 255).astype(np.uint8)
            stream.write(
                f"{point[0]:.7f} {point[1]:.7f} {point[2]:.7f} "
                f"{color_u8[0]} {color_u8[1]} {color_u8[2]} "
                f"{meta[0]:.0f} {meta[1]:.5f} {meta[2]:.6f} {meta[3]:.0f}\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame-meta", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--planes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--surface-id", action="append")
    parser.add_argument("--grid-m", type=float, default=0.05)
    parser.add_argument("--tile-points", type=int, default=256)
    parser.add_argument("--image-cache-images", type=int, default=12)
    parser.add_argument("--max-views", type=int, default=8)
    parser.add_argument("--base-max-views", type=int, default=0)
    parser.add_argument("--rescue-min-ncc", type=float)
    parser.add_argument("--rescue-min-parallax-deg", type=float)
    parser.add_argument("--rescue-min-views", type=int, default=0)
    parser.add_argument("--patch-n", type=int, default=7)
    parser.add_argument("--plane-offset-m", type=float, default=0.0)
    parser.add_argument("--allow-uncertified", action="store_true")
    parser.add_argument("--ncc-min", type=float, default=0.70)
    parser.add_argument("--min-views", type=int, default=3)
    parser.add_argument("--min-parallax-deg", type=float, default=5.0)
    parser.add_argument("--patch-radius-m", type=float, default=0.015)
    parser.add_argument("--max-graze-deg", type=float, default=72.0)
    parser.add_argument("--depth-competition-offset-m", type=float, action="append", default=[])
    parser.add_argument("--depth-ncc-margin", type=float, default=0.02)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = SweepConfig(
        grid_m=args.grid_m,
        tile_points=args.tile_points,
        image_cache_images=args.image_cache_images,
        max_views=args.max_views,
        base_max_views=args.base_max_views,
        rescue_min_ncc=args.rescue_min_ncc,
        rescue_min_parallax_deg=args.rescue_min_parallax_deg,
        rescue_min_views=args.rescue_min_views,
        patch_n=args.patch_n,
        ncc_min=args.ncc_min,
        min_views=args.min_views,
        min_parallax_deg=args.min_parallax_deg,
        patch_radius_m=args.patch_radius_m,
        depth_competition_offsets_m=tuple(
            offset for offset in args.depth_competition_offset_m if offset != 0.0
        ),
        depth_ncc_margin=args.depth_ncc_margin,
        max_graze_deg=args.max_graze_deg,
    )
    planes = json.loads(args.planes.read_text())
    surfaces = select_surfaces(planes, args.surface_id, args.allow_uncertified)
    if not surfaces:
        raise ValueError("no selected surfaces")
    frames = load_frames(args.frame_meta, args.ledger, args.photos)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_xyz = []
    all_rgb = []
    all_meta = []
    surface_metrics = []
    start = time.perf_counter()
    for surface in surfaces:
        xyz, rgb, metadata, metrics = sweep_surface(
            surface,
            planes["floor"],
            frames,
            config,
            args.plane_offset_m,
        )
        all_xyz.append(xyz)
        all_rgb.append(rgb)
        all_meta.append(metadata)
        surface_metrics.append(metrics)
        print(json.dumps(metrics, sort_keys=True), flush=True)
    xyz = np.concatenate(all_xyz) if all_xyz else np.empty((0, 3))
    rgb = np.concatenate(all_rgb) if all_rgb else np.empty((0, 3))
    metadata = np.concatenate(all_meta) if all_meta else np.empty((0, 4))
    suffix = "main" if args.plane_offset_m == 0 else f"offset_{args.plane_offset_m:+.3f}m"
    includes_floor = any(surface["kind"] == "floor" for surface in surfaces)
    output_prefix = "structural_planesweep" if includes_floor else "wall_ceiling_planesweep"
    ply_path = args.output_dir / f"{output_prefix}_{suffix}.ply"
    write_ply(ply_path, xyz, rgb, metadata)
    elapsed = time.perf_counter() - start
    depth_competition_enabled = bool(config.depth_competition_offsets_m)
    stats = {
        "schema": (
            "aether_pure_a_structural_planesweep_v3"
            if includes_floor
            else (
                "aether_pure_a_wall_ceiling_planesweep_v2"
                if depth_competition_enabled
                else "aether_pure_a_wall_ceiling_planesweep_v1"
            )
        ),
        "method": (
            "known_or_sparse_fitted_plane_tiled_multiview_zncc_unique_depth"
            if depth_competition_enabled
            else "known_or_sparse_fitted_plane_tiled_multiview_zncc"
        ),
        "plane_offset_m": args.plane_offset_m,
        "is_wrong_acceptance_probe": args.plane_offset_m != 0,
        "forbidden_matcher_outputs_consumed": False,
        "inputs": {
            "frame_meta": {"path": str(args.frame_meta), "sha256": sha256(args.frame_meta)},
            "ledger": {"path": str(args.ledger), "sha256": sha256(args.ledger)},
            "planes": {"path": str(args.planes), "sha256": sha256(args.planes)},
            "photo_count": len(frames),
        },
        "config": config.__dict__,
        "surfaces": surface_metrics,
        "totals": {
            "grid_candidates": sum(row["grid_candidates"] for row in surface_metrics),
            "accepted": len(xyz),
            "coverage_cells_5cm_sum": sum(row["coverage_cells_5cm"] for row in surface_metrics),
            "elapsed_s": elapsed,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "max_tile_loaded_image_bytes": max(
                (row["peak_loaded_image_bytes"] for row in surface_metrics), default=0
            ),
        },
        "output": {"ply": str(ply_path), "sha256": sha256(ply_path)},
    }
    stats_path = args.output_dir / f"{output_prefix}_{suffix}_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
