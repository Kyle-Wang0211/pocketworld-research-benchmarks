#!/usr/bin/env python3
"""Prepare the frozen, input-only B0 mesh-evaluation archive.

The program consumes only the registered camera-Z depth cache, camera model,
frozen reconstruction/held-out lists, and registered source images.  It never
accepts or inspects a route mesh.  Geometry calculations use float64, while the
stored depth/camera arrays preserve their frozen float32 bytes and all masks are
stored as NumPy bool arrays.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Iterator, Mapping, Sequence
import zipfile

import cv2
import numpy as np

import b0_input_contract as input_contract_module
import b0_preregister as preregister
import mesh_ab_eval


SCHEMA_VERSION = "b0-prepared-evaluation-v1"
PROVENANCE_SCHEMA_VERSION = "b0-prepared-evaluation-provenance-v1"

# Re-export the preregistered identities as patchable module constants.  The
# defaults deliberately come from the single preregistration authority instead
# of maintaining a second set of literal hashes.
EXPECTED_DMCACHE_SHA256 = preregister.EXPECTED_DMCACHE_SHA256
EXPECTED_MODEL_CACHE_SHA256 = preregister.EXPECTED_MODEL_CACHE_SHA256
EXPECTED_DMCACHE_SIGNATURE = preregister.EXPECTED_DMCACHE_SIGNATURE
EXPECTED_DEPTH_SHAPE = preregister.EXPECTED_DEPTH_SHAPE
FROZEN_SPLIT_HASHES: Mapping[str, Mapping[str, object]] = {
    "cap100": {
        "reconstruction_sha256": preregister.EXPECTED_CAP_RECONSTRUCTION_SHA256,
        "heldout_sha256": preregister.EXPECTED_CAP_HELDOUT_SHA256,
        "reconstruction_count": 81,
        "heldout_count": 19,
    },
    "full413": {
        "reconstruction_sha256": preregister.EXPECTED_FULL_RECONSTRUCTION_SHA256,
        "heldout_sha256": preregister.EXPECTED_FULL_HELDOUT_SHA256,
        "reconstruction_count": 331,
        "heldout_count": 82,
    },
}

VALID_EROSION_RADIUS_PX = 5
PROJECTION_MARGIN_PX = 16
CANDIDATE_CAMERA_COUNT = 8
MIN_ROI_SUPPORT = 3
PIXEL_REPROJECTION_ERROR_PX = 1.0
RELATIVE_CAMERA_Z_ERROR = 0.01
METRES_PER_RAW_LAPA_UNIT = float(preregister.FROZEN_SIM3["scale"])
FROZEN_SIM3_SHA256 = str(preregister.FROZEN_SIM3["canonical_sha256"])
MIN_WEAK_BASELINE_METRES = 0.04
MIN_WEAK_BASELINE_RAW_LAPA = MIN_WEAK_BASELINE_METRES / METRES_PER_RAW_LAPA_UNIT
WORLD_NORMAL_DOT = 0.5
WEAK_SUPPORT_COUNTS = (3, 4)
TEXTURE_WINDOW = 11
LOW_TEXTURE_RMS = 0.015
PLANAR_WINDOW = 11
PLANAR_NORMAL_SPREAD_DEG = 5.0
PLANAR_MAX_RESIDUAL_METRES = 0.005
PLANAR_MAX_RESIDUAL_RAW_LAPA = (
    PLANAR_MAX_RESIDUAL_METRES / METRES_PER_RAW_LAPA_UNIT
)
PLANAR_BATCH_SIZE = 1024

SOBEL_X_OVER_8 = np.asarray(
    [[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]],
    dtype=np.float64,
) / 8.0
SOBEL_Y_OVER_8 = np.asarray(
    [[-1.0, -2.0, -1.0], [0.0, 0.0, 0.0], [1.0, 2.0, 1.0]],
    dtype=np.float64,
) / 8.0


class PreparationError(ValueError):
    """Raised when an input cannot satisfy the frozen preparation contract."""


def sha256_file(path: Path | str, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def provenance_path(output: Path | str) -> Path:
    path = Path(output)
    return path.with_name(path.name + ".provenance.json")


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _validate_name_list(names: object, *, label: str) -> list[str]:
    if not isinstance(names, list) or not names:
        raise PreparationError(f"{label} must be a non-empty list")
    result: list[str] = []
    seen: set[str] = set()
    for value in names:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or "\x00" in value
            or "/" in value
            or "\\" in value
            or Path(value).name != value
            or value in {".", ".."}
            or value in seen
        ):
            raise PreparationError(f"{label} has an invalid or duplicate basename: {value!r}")
        seen.add(value)
        result.append(value)
    return result


def _read_canonical_list(path: Path, *, label: str) -> tuple[list[str], str]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PreparationError(f"{label} is not readable canonical UTF-8: {path}") from exc
    names = _validate_name_list(text.splitlines(), label=label)
    canonical = ("\n".join(names) + "\n").encode("utf-8")
    if raw != canonical:
        raise PreparationError(
            f"{label} must be canonical UTF-8, one basename per line, with final newline"
        )
    return names, hashlib.sha256(raw).hexdigest()


def _require_hash(label: str, actual: str, expected: str) -> None:
    if actual != expected:
        raise PreparationError(
            f"{label} SHA-256 mismatch: expected {expected}, found {actual}"
        )


def _select_split_profile(
    reconstruction_hash: str,
    heldout_hash: str,
    reconstruction_count: int,
    heldout_count: int,
) -> str:
    for profile, contract in FROZEN_SPLIT_HASHES.items():
        if (
            reconstruction_hash == contract.get("reconstruction_sha256")
            and heldout_hash == contract.get("heldout_sha256")
            and reconstruction_count == contract.get("reconstruction_count")
            and heldout_count == contract.get("heldout_count")
        ):
            return profile
    raise PreparationError(
        "reconstruction/heldout lists do not match one frozen hash-and-count pair"
    )


@contextmanager
def _streaming_dmcache(
    path: Path, work_directory: Path
) -> Iterator[tuple[list[str], np.memmap, str]]:
    """Extract only dm.npy and memory-map it instead of inflating it into RAM."""

    try:
        with np.load(path, allow_pickle=False) as archive:
            required = {"frames", "dm", "sig"}
            missing = sorted(required - set(archive.files))
            if missing:
                raise PreparationError(f"dmcache lacks required arrays: {missing}")
            frames_raw = archive["frames"].tolist()
            signature_value = archive["sig"]
            if signature_value.shape != ():
                raise PreparationError("dmcache signature must be scalar")
            signature = str(signature_value.item())
        extracted = work_directory / "dm.npy"
        with zipfile.ZipFile(path, "r") as container:
            try:
                member = container.getinfo("dm.npy")
            except KeyError as exc:
                raise PreparationError("dmcache ZIP lacks dm.npy") from exc
            with container.open(member, "r") as source, extracted.open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
        depth = np.load(extracted, allow_pickle=False, mmap_mode="r")
    except PreparationError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise PreparationError(f"invalid dmcache: {path}") from exc

    frames = _validate_name_list(frames_raw, label="dmcache frames")
    if not isinstance(depth, np.memmap):
        raise PreparationError("dmcache depth could not be memory-mapped")
    try:
        yield frames, depth, signature
    finally:
        mapping = getattr(depth, "_mmap", None)
        if mapping is not None:
            mapping.close()


def _load_model_cache(path: Path, frame_count: int) -> tuple[list[str], np.ndarray, np.ndarray]:
    try:
        with np.load(path, allow_pickle=False) as archive:
            required = {"names", "K", "w2c"}
            missing = sorted(required - set(archive.files))
            if missing:
                raise PreparationError(f"model cache lacks required arrays: {missing}")
            names_raw = archive["names"].tolist()
            intrinsics = np.asarray(archive["K"])
            world_to_camera = np.asarray(archive["w2c"])
    except PreparationError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise PreparationError(f"invalid model cache: {path}") from exc

    names = _validate_name_list(names_raw, label="model cache names")
    if len(names) != frame_count:
        raise PreparationError("dmcache/model exact-name join has a different frame count")
    if intrinsics.shape != (frame_count, 3, 3) or intrinsics.dtype != np.float32:
        raise PreparationError(
            f"model K must be {frame_count}x3x3 float32, "
            f"found {intrinsics.shape} {intrinsics.dtype}"
        )
    if world_to_camera.shape != (frame_count, 4, 4) or world_to_camera.dtype != np.float32:
        raise PreparationError(
            "model w2c must be "
            f"{frame_count}x4x4 float32, found {world_to_camera.shape} {world_to_camera.dtype}"
        )
    if not np.isfinite(intrinsics).all() or not np.isfinite(world_to_camera).all():
        raise PreparationError("model K/w2c contains non-finite values")
    if np.any(intrinsics[:, 0, 0] <= 0.0) or np.any(intrinsics[:, 1, 1] <= 0.0):
        raise PreparationError("model K contains a non-positive focal length")
    try:
        np.linalg.inv(intrinsics.astype(np.float64))
        camera_to_world = np.linalg.inv(world_to_camera.astype(np.float64))
    except np.linalg.LinAlgError as exc:
        raise PreparationError("model K/w2c contains a singular matrix") from exc
    expected_bottom = np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float64)
    if not np.array_equal(
        world_to_camera[:, 3, :].astype(np.float64),
        np.broadcast_to(expected_bottom, (frame_count, 4)),
    ):
        raise PreparationError("model w2c bottom row is not exactly [0,0,0,1]")
    if not np.isfinite(camera_to_world).all():
        raise PreparationError("model inverse w2c contains non-finite values")
    return names, intrinsics, world_to_camera


def _valid_depth(depth: np.ndarray) -> np.ndarray:
    return np.isfinite(depth) & (depth > 0.0)


def _erode_valid(mask: np.ndarray) -> np.ndarray:
    kernel_size = 2 * VALID_EROSION_RADIUS_PX + 1
    eroded = cv2.erode(
        mask.astype(np.uint8, copy=False),
        np.ones((kernel_size, kernel_size), dtype=np.uint8),
        iterations=1,
        borderType=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return eroded.astype(np.bool_, copy=False)


def _pixel_grid(shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    yy, xx = np.indices((height, width), dtype=np.float64)
    return np.stack((xx, yy, np.ones_like(xx)), axis=-1)


def _world_points(
    depth: np.ndarray, intrinsics: np.ndarray, world_to_camera: np.ndarray
) -> np.ndarray:
    z = np.asarray(depth, dtype=np.float64)
    rays = _pixel_grid(z.shape) @ np.linalg.inv(np.asarray(intrinsics, dtype=np.float64)).T
    ray_z = rays[..., 2]
    valid = _valid_depth(z) & np.isfinite(rays).all(axis=-1) & (np.abs(ray_z) > 0.0)
    points_camera = np.full(z.shape + (3,), np.nan, dtype=np.float64)
    points_camera[valid] = rays[valid] * (z[valid] / ray_z[valid])[:, None]
    camera_to_world = np.linalg.inv(np.asarray(world_to_camera, dtype=np.float64))
    points_world = points_camera @ camera_to_world[:3, :3].T + camera_to_world[:3, 3]
    points_world[~valid] = np.nan
    return points_world


def _project_world(
    points_world: np.ndarray, intrinsics: np.ndarray, world_to_camera: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.asarray(points_world, dtype=np.float64)
    w2c = np.asarray(world_to_camera, dtype=np.float64)
    camera = points @ w2c[:3, :3].T + w2c[:3, 3]
    homogeneous = camera @ np.asarray(intrinsics, dtype=np.float64).T
    with np.errstate(divide="ignore", invalid="ignore"):
        u = homogeneous[:, 0] / homogeneous[:, 2]
        v = homogeneous[:, 1] / homogeneous[:, 2]
    return u, v, camera[:, 2]


def _bilinear_scalar(
    image: np.ndarray, u: np.ndarray, v: np.ndarray, eligible: np.ndarray
) -> np.ndarray:
    height, width = image.shape
    output = np.full(u.shape, np.nan, dtype=np.float64)
    selected = np.flatnonzero(eligible)
    if not selected.size:
        return output
    us = u[selected]
    vs = v[selected]
    x0 = np.floor(us).astype(np.int64)
    y0 = np.floor(vs).astype(np.int64)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = us - x0
    wy = vs - y0
    values = np.asarray(image)
    sampled = (
        (1.0 - wx) * (1.0 - wy) * values[y0, x0]
        + wx * (1.0 - wy) * values[y0, x1]
        + (1.0 - wx) * wy * values[y1, x0]
        + wx * wy * values[y1, x1]
    )
    output[selected] = sampled.astype(np.float64, copy=False)
    return output


def _bilinear_normals(
    normals: np.ndarray, u: np.ndarray, v: np.ndarray, eligible: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    height, width, _ = normals.shape
    output = np.full((len(u), 3), np.nan, dtype=np.float64)
    valid_output = np.zeros(len(u), dtype=np.bool_)
    selected = np.flatnonzero(eligible)
    if not selected.size:
        return output, valid_output
    us = u[selected]
    vs = v[selected]
    x0 = np.floor(us).astype(np.int64)
    y0 = np.floor(vs).astype(np.int64)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = us - x0
    wy = vs - y0
    corners = np.stack(
        (
            normals[y0, x0],
            normals[y0, x1],
            normals[y1, x0],
            normals[y1, x1],
        ),
        axis=1,
    )
    corner_valid = np.isfinite(corners).all(axis=(1, 2))
    weights = np.stack(
        (
            (1.0 - wx) * (1.0 - wy),
            wx * (1.0 - wy),
            (1.0 - wx) * wy,
            wx * wy,
        ),
        axis=1,
    )
    interpolated = np.sum(corners * weights[:, :, None], axis=1)
    lengths = np.linalg.norm(interpolated, axis=1)
    good = corner_valid & np.isfinite(lengths) & (lengths > 0.0)
    if np.any(good):
        chosen = selected[good]
        output[chosen] = interpolated[good] / lengths[good, None]
        valid_output[chosen] = True
    return output, valid_output


def _roundtrip_consistency(
    points_world: np.ndarray,
    original_pixels: np.ndarray,
    original_depth: np.ndarray,
    reference_intrinsics: np.ndarray,
    reference_w2c: np.ndarray,
    source_depth: np.ndarray,
    source_intrinsics: np.ndarray,
    source_w2c: np.ndarray,
    *,
    margin_px: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return strict heldout->source-depth->heldout consistency and source pixels."""

    source_u, source_v, source_projected_z = _project_world(
        points_world, source_intrinsics, source_w2c
    )
    height, width = source_depth.shape
    in_bounds = (
        np.isfinite(source_u)
        & np.isfinite(source_v)
        & np.isfinite(source_projected_z)
        & (source_projected_z > 0.0)
        & (source_u >= float(margin_px))
        & (source_v >= float(margin_px))
        & (source_u <= float(width - 1 - margin_px))
        & (source_v <= float(height - 1 - margin_px))
    )
    nearest_x = np.zeros(len(source_u), dtype=np.int64)
    nearest_y = np.zeros(len(source_v), dtype=np.int64)
    finite_uv = np.isfinite(source_u) & np.isfinite(source_v)
    nearest_x[finite_uv] = np.floor(source_u[finite_uv] + 0.5).astype(np.int64)
    nearest_y[finite_uv] = np.floor(source_v[finite_uv] + 0.5).astype(np.int64)
    nearest_x = np.clip(nearest_x, 0, width - 1)
    nearest_y = np.clip(nearest_y, 0, height - 1)
    source_valid = _valid_depth(source_depth)
    in_bounds &= source_valid[nearest_y, nearest_x]
    sampled_z = _bilinear_scalar(source_depth, source_u, source_v, in_bounds)
    sample_valid = in_bounds & np.isfinite(sampled_z) & (sampled_z > 0.0)

    source_pixels_h = np.stack(
        (source_u, source_v, np.ones_like(source_u)), axis=1
    )
    source_rays = source_pixels_h @ np.linalg.inv(
        np.asarray(source_intrinsics, dtype=np.float64)
    ).T
    source_ray_z = source_rays[:, 2]
    sample_valid &= np.isfinite(source_rays).all(axis=1) & (np.abs(source_ray_z) > 0.0)
    points_source = np.full_like(source_rays, np.nan, dtype=np.float64)
    points_source[sample_valid] = source_rays[sample_valid] * (
        sampled_z[sample_valid] / source_ray_z[sample_valid]
    )[:, None]
    source_c2w = np.linalg.inv(np.asarray(source_w2c, dtype=np.float64))
    returned_world = points_source @ source_c2w[:3, :3].T + source_c2w[:3, 3]
    returned_u, returned_v, returned_z = _project_world(
        returned_world, reference_intrinsics, reference_w2c
    )
    pixel_error = np.hypot(
        returned_u - original_pixels[:, 0], returned_v - original_pixels[:, 1]
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        relative_z_error = np.abs(returned_z - original_depth) / np.abs(original_depth)
    consistent = (
        sample_valid
        & np.isfinite(pixel_error)
        & np.isfinite(relative_z_error)
        & (pixel_error < PIXEL_REPROJECTION_ERROR_PX)
        & (relative_z_error < RELATIVE_CAMERA_Z_ERROR)
    )
    return consistent, source_u, source_v


def _depth_normals_world(
    depth: np.ndarray, intrinsics: np.ndarray, world_to_camera: np.ndarray
) -> np.ndarray:
    # Cross products are taken after backprojection into world coordinates, so
    # the result is already a world normal and must not receive another c2w
    # rotation.
    points = _world_points(depth, intrinsics, world_to_camera)
    normals = np.full(points.shape, np.nan, dtype=np.float64)
    dx = points[1:-1, 2:] - points[1:-1, :-2]
    dy = points[2:, 1:-1] - points[:-2, 1:-1]
    cross = np.cross(dx, dy)
    lengths = np.linalg.norm(cross, axis=-1)
    valid = np.isfinite(cross).all(axis=-1) & np.isfinite(lengths) & (lengths > 0.0)
    interior = normals[1:-1, 1:-1]
    interior[valid] = cross[valid] / lengths[valid, None]
    return normals


def _decode_srgb_image(
    payload: bytes,
    expected_shape: tuple[int, int],
    name: str,
    *,
    expected_raw_size_wh: tuple[int, int] | None = None,
) -> tuple[np.ndarray, dict[str, object]]:
    encoded = np.frombuffer(payload, dtype=np.uint8)
    decode_flags = cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION
    bgr = cv2.imdecode(encoded, decode_flags)
    if bgr is None:
        raise PreparationError(f"registered image cannot be decoded: {name}")
    if bgr.dtype != np.uint8 or bgr.ndim != 3 or bgr.shape[2] != 3:
        raise PreparationError(f"registered image did not decode as uint8 BGR: {name}")
    original_shape = (int(bgr.shape[0]), int(bgr.shape[1]))
    raw_size_wh = (original_shape[1], original_shape[0])
    if expected_raw_size_wh is not None:
        if (
            not isinstance(expected_raw_size_wh, tuple)
            or len(expected_raw_size_wh) != 2
            or any(type(value) is not int or value <= 0 for value in expected_raw_size_wh)
        ):
            raise PreparationError("expected raw image dimensions must be positive integers")
        if raw_size_wh != expected_raw_size_wh:
            raise PreparationError(
                "raw encoded image dimensions mismatch: "
                f"expected {expected_raw_size_wh[0]}x{expected_raw_size_wh[1]} "
                f"(width x height), found {raw_size_wh[0]}x{raw_size_wh[1]} for {name}"
            )
    # Match the common TSDF representation preparation: color channel
    # conversion happens first, followed unconditionally by deterministic
    # INTER_AREA resize to the frozen depth grid.  Ignoring EXIF orientation is
    # essential: intrinsics and depth are defined over the encoded raster, not
    # an auto-rotated presentation image.
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(
        rgb,
        (expected_shape[1], expected_shape[0]),
        interpolation=cv2.INTER_AREA,
    )
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    if rgb.shape != expected_shape + (3,) or rgb.dtype != np.uint8:
        raise PreparationError(f"prepared image shape/dtype is invalid for {name}")
    return rgb, {
        "decode": "cv2.imdecode IMREAD_COLOR|IMREAD_IGNORE_ORIENTATION",
        "exif_orientation_applied": False,
        "raw_size_wh": list(raw_size_wh),
        "original_size_hw": list(original_shape),
        "prepared_size_hw": list(expected_shape),
        "resize": "cv2.resize INTER_AREA after RGB conversion",
    }


def _low_texture_mask(rgb: np.ndarray, roi: np.ndarray) -> np.ndarray:
    srgb = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(
        srgb <= 0.04045,
        srgb / 12.92,
        ((srgb + 0.055) / 1.055) ** 2.4,
    )
    luminance = (
        0.2126 * linear[:, :, 0]
        + 0.7152 * linear[:, :, 1]
        + 0.0722 * linear[:, :, 2]
    )
    gx = cv2.filter2D(
        luminance, cv2.CV_64F, SOBEL_X_OVER_8, borderType=cv2.BORDER_REFLECT_101
    )
    gy = cv2.filter2D(
        luminance, cv2.CV_64F, SOBEL_Y_OVER_8, borderType=cv2.BORDER_REFLECT_101
    )
    mean_squared_gradient = cv2.boxFilter(
        gx * gx + gy * gy,
        cv2.CV_64F,
        (TEXTURE_WINDOW, TEXTURE_WINDOW),
        normalize=True,
        borderType=cv2.BORDER_REFLECT_101,
    )
    rms = np.sqrt(np.maximum(mean_squared_gradient, 0.0))
    return np.asarray(roi, dtype=np.bool_) & np.isfinite(rms) & (rms < LOW_TEXTURE_RMS)


def local_planar_mask(
    depth: np.ndarray,
    intrinsics: np.ndarray,
    world_to_camera: np.ndarray,
    roi: np.ndarray,
    *,
    max_absolute_residual_model_units: float = PLANAR_MAX_RESIDUAL_RAW_LAPA,
) -> np.ndarray:
    """Fit each 11x11 input window and apply the frozen planar-shell gates."""

    z = np.asarray(depth)
    region = np.asarray(roi)
    if z.ndim != 2 or region.shape != z.shape or region.dtype != np.bool_:
        raise PreparationError("local planar inputs have incompatible shape/dtype")
    if (
        not math.isfinite(float(max_absolute_residual_model_units))
        or max_absolute_residual_model_units <= 0.0
    ):
        raise PreparationError("planar residual threshold must be positive and finite")
    points = _world_points(z, intrinsics, world_to_camera)
    normals = _depth_normals_world(z, intrinsics, world_to_camera)
    height, width = z.shape
    radius = PLANAR_WINDOW // 2
    candidate_y, candidate_x = np.nonzero(region)
    inside = (
        (candidate_y >= radius)
        & (candidate_y < height - radius)
        & (candidate_x >= radius)
        & (candidate_x < width - radius)
    )
    candidate_y = candidate_y[inside]
    candidate_x = candidate_x[inside]
    output = np.zeros(z.shape, dtype=np.bool_)
    if not candidate_y.size:
        return output

    offsets_y, offsets_x = np.indices((PLANAR_WINDOW, PLANAR_WINDOW), dtype=np.int64)
    offsets_y = offsets_y.reshape(-1) - radius
    offsets_x = offsets_x.reshape(-1) - radius
    center_offset = (PLANAR_WINDOW * PLANAR_WINDOW) // 2
    cosine_limit = math.cos(math.radians(PLANAR_NORMAL_SPREAD_DEG))

    for begin in range(0, len(candidate_y), PLANAR_BATCH_SIZE):
        end = min(begin + PLANAR_BATCH_SIZE, len(candidate_y))
        cy = candidate_y[begin:end]
        cx = candidate_x[begin:end]
        rows = cy[:, None] + offsets_y[None, :]
        columns = cx[:, None] + offsets_x[None, :]
        point_windows = points[rows, columns]
        normal_windows = normals[rows, columns]
        valid = np.isfinite(point_windows).all(axis=(1, 2)) & np.isfinite(
            normal_windows
        ).all(axis=(1, 2))
        selected = np.flatnonzero(valid)
        if not selected.size:
            continue

        selected_normals = normal_windows[selected]
        reference = selected_normals[:, center_offset, :]
        signs = np.where(
            np.sum(selected_normals * reference[:, None, :], axis=2) < 0.0,
            -1.0,
            1.0,
        )
        oriented = selected_normals * signs[:, :, None]
        mean_normal = np.mean(oriented, axis=1)
        mean_length = np.linalg.norm(mean_normal, axis=1)
        mean_valid = np.isfinite(mean_length) & (mean_length > 0.0)
        normalized_mean = np.full_like(mean_normal, np.nan)
        normalized_mean[mean_valid] = mean_normal[mean_valid] / mean_length[mean_valid, None]
        normal_dots = np.abs(
            np.sum(selected_normals * normalized_mean[:, None, :], axis=2)
        )
        spread_ok = mean_valid & np.all(normal_dots >= cosine_limit, axis=1)
        spread_selected = np.flatnonzero(spread_ok)
        if not spread_selected.size:
            continue

        planar_points = point_windows[selected[spread_selected]]
        centered = planar_points - np.mean(planar_points, axis=1, keepdims=True)
        try:
            _u, _singular, vh = np.linalg.svd(centered, full_matrices=False)
        except np.linalg.LinAlgError as exc:
            raise PreparationError("float64 local plane SVD did not converge") from exc
        plane_normal = vh[:, -1, :]
        residual = np.max(
            np.abs(np.sum(centered * plane_normal[:, None, :], axis=2)), axis=1
        )
        residual_ok = np.isfinite(residual) & (
            residual <= max_absolute_residual_model_units
        )
        accepted_local = selected[spread_selected[residual_ok]]
        output[cy[accepted_local], cx[accepted_local]] = True
    return output & region


def _camera_centers(world_to_camera: np.ndarray) -> np.ndarray:
    camera_to_world = np.linalg.inv(np.asarray(world_to_camera, dtype=np.float64))
    return camera_to_world[:, :3, 3]


def _ordered_nearest_indices(
    reference_center: np.ndarray,
    reconstruction_centers: np.ndarray,
    *,
    minimum_baseline: float | None,
) -> list[int]:
    distances = np.linalg.norm(reconstruction_centers - reference_center[None, :], axis=1)
    eligible = np.isfinite(distances)
    if minimum_baseline is not None:
        eligible &= distances >= minimum_baseline
    ordered = sorted(
        np.flatnonzero(eligible).tolist(), key=lambda index: (float(distances[index]), index)
    )
    return ordered[:CANDIDATE_CAMERA_COUNT]


def _frame_masks(
    *,
    heldout_depth: np.ndarray,
    heldout_intrinsics: np.ndarray,
    heldout_w2c: np.ndarray,
    heldout_rgb: np.ndarray,
    reconstruction_depth: np.ndarray,
    reconstruction_intrinsics: np.ndarray,
    reconstruction_w2c: np.ndarray,
    reconstruction_depth_indices: Sequence[int],
    minimum_weak_baseline_model_units: float = MIN_WEAK_BASELINE_RAW_LAPA,
    planar_max_residual_model_units: float = PLANAR_MAX_RESIDUAL_RAW_LAPA,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    valid = _valid_depth(heldout_depth)
    eroded = _erode_valid(valid)
    world = _world_points(heldout_depth, heldout_intrinsics, heldout_w2c)
    flat_ids = np.flatnonzero(eroded.reshape(-1))
    roi = np.zeros(heldout_depth.shape, dtype=np.bool_)
    if not flat_ids.size:
        low_texture = _low_texture_mask(heldout_rgb, roi)
        planar = local_planar_mask(
            heldout_depth,
            heldout_intrinsics,
            heldout_w2c,
            roi,
            max_absolute_residual_model_units=planar_max_residual_model_units,
        )
        return roi, low_texture, roi.copy(), planar

    width = heldout_depth.shape[1]
    yy = flat_ids // width
    xx = flat_ids % width
    points = world[yy, xx]
    pixels = np.column_stack((xx, yy)).astype(np.float64, copy=False)
    reference_z = np.asarray(heldout_depth[yy, xx], dtype=np.float64)

    reconstruction_centers = _camera_centers(reconstruction_w2c)
    reference_center = _camera_centers(heldout_w2c[None, :, :])[0]
    roi_candidates = _ordered_nearest_indices(
        reference_center, reconstruction_centers, minimum_baseline=None
    )
    if len(roi_candidates) != CANDIDATE_CAMERA_COUNT:
        raise PreparationError("fewer than 8 reconstruction cameras are available for ROI")
    roi_support = np.zeros(len(flat_ids), dtype=np.uint8)
    for candidate in roi_candidates:
        source_depth = reconstruction_depth[reconstruction_depth_indices[candidate]]
        consistent, _source_u, _source_v = _roundtrip_consistency(
            points,
            pixels,
            reference_z,
            heldout_intrinsics,
            heldout_w2c,
            source_depth,
            reconstruction_intrinsics[candidate],
            reconstruction_w2c[candidate],
            margin_px=PROJECTION_MARGIN_PX,
        )
        roi_support += consistent.astype(np.uint8)
    roi_flat = roi.reshape(-1)
    roi_flat[flat_ids] = roi_support >= MIN_ROI_SUPPORT

    weak_candidates = _ordered_nearest_indices(
        reference_center,
        reconstruction_centers,
        minimum_baseline=minimum_weak_baseline_model_units,
    )
    if len(weak_candidates) != CANDIDATE_CAMERA_COUNT:
        raise PreparationError(
            "fewer than 8 reconstruction cameras satisfy the 0.04-metre "
            f"({minimum_weak_baseline_model_units:.17g} model-unit) "
            "weak-support baseline"
        )
    reference_normals_map = _depth_normals_world(
        heldout_depth, heldout_intrinsics, heldout_w2c
    )
    reference_normals = reference_normals_map[yy, xx]
    reference_normal_valid = np.isfinite(reference_normals).all(axis=1)
    weak_count = np.zeros(len(flat_ids), dtype=np.uint8)
    for candidate in weak_candidates:
        source_depth = reconstruction_depth[reconstruction_depth_indices[candidate]]
        consistent, source_u, source_v = _roundtrip_consistency(
            points,
            pixels,
            reference_z,
            heldout_intrinsics,
            heldout_w2c,
            source_depth,
            reconstruction_intrinsics[candidate],
            reconstruction_w2c[candidate],
            margin_px=0,
        )
        source_normal_map = _depth_normals_world(
            source_depth,
            reconstruction_intrinsics[candidate],
            reconstruction_w2c[candidate],
        )
        sampled_normal, sampled_valid = _bilinear_normals(
            source_normal_map, source_u, source_v, consistent
        )
        normal_dot = np.sum(reference_normals * sampled_normal, axis=1)
        supported = (
            consistent
            & reference_normal_valid
            & sampled_valid
            & np.isfinite(normal_dot)
            & (normal_dot > WORLD_NORMAL_DOT)
        )
        weak_count += supported.astype(np.uint8)
    weak_support = np.zeros_like(roi)
    weak_flat = weak_support.reshape(-1)
    weak_flat[flat_ids] = np.isin(weak_count, WEAK_SUPPORT_COUNTS)
    weak_support &= roi

    low_texture = _low_texture_mask(heldout_rgb, roi)
    planar = local_planar_mask(
        heldout_depth,
        heldout_intrinsics,
        heldout_w2c,
        roi,
        max_absolute_residual_model_units=planar_max_residual_model_units,
    )
    return roi, low_texture, weak_support, planar


def _semantic_manifest(
    names: Sequence[str],
    dm_index: Mapping[str, int],
    model_index: Mapping[str, int],
    depth: np.ndarray,
    intrinsics: np.ndarray,
    world_to_camera: np.ndarray,
) -> str:
    hashes = []
    for name in names:
        frame_depth = depth[dm_index[name]]
        hashes.append(
            input_contract_module.canonical_frame_semantic_sha256(
                name,
                _valid_depth(frame_depth),
                frame_depth,
                intrinsics[model_index[name]],
                world_to_camera[model_index[name]],
            )
        )
    return input_contract_module.semantic_manifest_sha256(hashes)


def _heldout_image_manifest(entries: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    digest.update(b"b0-heldout-images-v1\0")
    for entry in entries:
        digest.update(f"{entry['name']}\0{entry['sha256']}\n".encode("utf-8"))
    return digest.hexdigest()


def _verify_registered_image_identities(
    image_root: Path,
    frame_order: Sequence[str],
    identities: Mapping[str, Mapping[str, object]],
) -> str:
    """Verify every contract image and return the common ordered manifest hash."""
    observed: dict[str, dict[str, object]] = {}
    for name in frame_order:
        image_path = image_root / name
        if not image_path.is_file():
            raise PreparationError(f"image identity is missing: {name}")
        try:
            size_bytes = image_path.stat().st_size
            image_sha256 = sha256_file(image_path)
        except OSError as exc:
            raise PreparationError(f"image identity cannot be read: {name}") from exc
        expected = identities[name]
        if (
            size_bytes != expected["size_bytes"]
            or image_sha256 != expected["sha256"]
        ):
            raise PreparationError(f"image identity mismatch: {name}")
        observed[name] = {
            "sha256": image_sha256,
            "size_bytes": size_bytes,
        }
    try:
        return input_contract_module.image_identity_manifest_sha256(frame_order, observed)
    except input_contract_module.RouteInputNotEquivalent as exc:
        raise PreparationError("image identity manifest is invalid") from exc


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _publish_pair(
    temporary_archive: Path,
    output: Path,
    temporary_provenance: Path,
    provenance: Path,
) -> None:
    if _path_lexists(output):
        raise FileExistsError(f"output already exists: {output}")
    if _path_lexists(provenance):
        raise FileExistsError(f"provenance output already exists: {provenance}")
    archive_published = False
    try:
        os.link(temporary_archive, output)
        archive_published = True
        os.link(temporary_provenance, provenance)
    except Exception:
        if archive_published:
            # This removes only the hard link created by this function; the
            # complete temporary artifact remains available until cleanup.
            output.unlink()
        raise


def prepare_evaluation_inputs(
    *,
    dmcache: Path | str,
    model_cache: Path | str,
    reconstruction_list: Path | str,
    heldout_list: Path | str,
    image_root: Path | str,
    input_contract: Path | str | None = None,
    split_id: str | None = None,
    out: Path | str,
) -> dict[str, object]:
    dmcache_path = Path(dmcache)
    model_path = Path(model_cache)
    reconstruction_path = Path(reconstruction_list)
    heldout_path = Path(heldout_list)
    images_path = Path(image_root)
    output = Path(out)
    provenance = provenance_path(output)

    if output.suffix.lower() != ".npz":
        raise PreparationError("output must have a .npz suffix")
    if _path_lexists(output):
        raise FileExistsError(f"output already exists: {output}")
    if _path_lexists(provenance):
        raise FileExistsError(f"provenance output already exists: {provenance}")

    reconstruction_names, reconstruction_hash = _read_canonical_list(
        reconstruction_path, label="reconstruction list"
    )
    heldout_names, heldout_hash = _read_canonical_list(
        heldout_path, label="heldout list"
    )
    component_hashes = {
        "dmcache": sha256_file(dmcache_path),
        "model_cache": sha256_file(model_path),
        "reconstruction_list": reconstruction_hash,
        "heldout_list": heldout_hash,
    }

    generic_contract: Mapping[str, Any] | None = None
    selected_split: Mapping[str, Any] | None = None
    contract_path: Path | None = None
    expected_dm_frames: list[str] | None = None
    expected_model_frames: list[str] | None = None
    registered_images: Mapping[str, Mapping[str, object]] | None = None
    registered_image_manifest: str | None = None
    expected_raw_size_wh: tuple[int, int] | None = None
    contract_image_root: Path | None = None

    if input_contract is not None:
        if split_id is None:
            raise PreparationError(
                "split-id is required with the generic input contract"
            )
        contract_path = Path(input_contract)
        try:
            generic_contract, contract_file_sha256 = (
                input_contract_module.load_input_contract(contract_path)
            )
        except input_contract_module.RouteInputNotEquivalent as exc:
            raise PreparationError("input contract is invalid") from exc
        try:
            selected_split = input_contract_module.select_input_contract_split(
                generic_contract, split_id
            )
        except input_contract_module.RouteInputNotEquivalent as exc:
            raise PreparationError(
                f"input contract split is invalid: {split_id!r}"
            ) from exc

        dm_contract = generic_contract["dmcache"]
        model_contract = generic_contract["model_cache"]
        expected_depth_shape = tuple(dm_contract["depth"]["shape"])
        expected_depth_dtype = np.dtype(dm_contract["depth"]["dtype"])
        expected_signature = str(dm_contract["signature"])
        expected_dm_hash = str(dm_contract["sha256"])
        expected_model_hash = str(model_contract["sha256"])
        expected_dm_frames = list(dm_contract["frame_order"])
        expected_model_frames = list(model_contract["frame_order"])

        reconstruction_contract = selected_split["reconstruction"]
        heldout_contract = selected_split["heldout"]
        if reconstruction_names != list(reconstruction_contract["frames"]):
            raise PreparationError(
                "reconstruction list order does not match input contract split"
            )
        if heldout_names != list(heldout_contract["frames"]):
            raise PreparationError(
                "heldout list order does not match input contract split"
            )
        _require_hash(
            "reconstruction list",
            reconstruction_hash,
            str(reconstruction_contract["file_sha256"]),
        )
        _require_hash(
            "heldout list", heldout_hash, str(heldout_contract["file_sha256"])
        )
        if (
            input_contract_module.ordered_frame_names_sha256(reconstruction_names)
            != reconstruction_contract["semantic_sha256"]
            or input_contract_module.ordered_frame_names_sha256(heldout_names)
            != heldout_contract["semantic_sha256"]
        ):
            raise PreparationError("split ordered semantic SHA-256 mismatch")

        dataset_id = str(generic_contract["dataset_id"])
        split_profile = split_id
        coordinate_frame = str(generic_contract["coordinate_frame"])
        metres_per_model_unit = float(generic_contract["metres_per_model_unit"])
        policy = generic_contract["transductive_policy"]
        split_route_allowed = selected_split.get("route_allowed", True)
        split_quality_forbidden = selected_split.get(
            "quality_scoring_forbidden", False
        )
        if (
            type(split_route_allowed) is not bool
            or type(split_quality_forbidden) is not bool
        ):
            raise PreparationError("input contract split gates must be boolean")
        route_allowed = bool(policy["route_allowed"] and split_route_allowed)
        quality_scoring_forbidden = bool(
            policy["quality_scoring_forbidden"] or split_quality_forbidden
        )
        transductive_present = bool(policy["present"])
        transductive_warning = str(
            policy.get(
                "warning",
                policy.get(
                    "reason",
                    "The input contract marks this dataset as transductive."
                    if transductive_present
                    else "The input contract does not mark transductive leakage.",
                ),
            )
        )
        forbidden_claims = list(policy.get("forbidden_claims", []))
        if any(not isinstance(value, str) or not value for value in forbidden_claims):
            raise PreparationError("input contract forbidden_claims must be strings")
        images_contract = generic_contract["images"]
        raw_size_wh = images_contract.get("raw_size_wh")
        if (
            not isinstance(raw_size_wh, list)
            or len(raw_size_wh) != 2
            or any(type(value) is not int or value <= 0 for value in raw_size_wh)
        ):
            raise PreparationError(
                "input contract images.raw_size_wh must be [positive width, positive height]"
            )
        expected_raw_size_wh = (raw_size_wh[0], raw_size_wh[1])
        image_root_value = images_contract.get("root")
        if not isinstance(image_root_value, str) or not image_root_value:
            raise PreparationError("input contract images.root must be an absolute path")
        contract_image_root = Path(image_root_value)
        if not contract_image_root.is_absolute():
            raise PreparationError("input contract images.root must be an absolute path")
        contract_image_root = contract_image_root.resolve()
        registered_images = images_contract["by_name"]
        registered_image_manifest = str(
            images_contract["root_manifest_sha256"]
        )
        component_hashes["input_contract"] = contract_file_sha256
    else:
        if split_id is not None:
            raise PreparationError("split-id requires --input-contract")
        expected_depth_shape = EXPECTED_DEPTH_SHAPE
        expected_depth_dtype = np.dtype(np.float32)
        expected_signature = EXPECTED_DMCACHE_SIGNATURE
        expected_dm_hash = EXPECTED_DMCACHE_SHA256
        expected_model_hash = EXPECTED_MODEL_CACHE_SHA256
        split_profile = _select_split_profile(
            reconstruction_hash,
            heldout_hash,
            len(reconstruction_names),
            len(heldout_names),
        )
        dataset_id = {
            "cap100": "cap100_quality",
            "full413": "full413_quality",
        }.get(split_profile, f"legacy_trio_{split_profile}")
        coordinate_frame = "raw_lapa_model"
        metres_per_model_unit = METRES_PER_RAW_LAPA_UNIT
        route_allowed = True
        quality_scoring_forbidden = False
        transductive_present = True
        transductive_warning = (
            "The frozen inference/pass2 depth cache used information from the full "
            "registered sequence. Held-out applies only at fusion/evaluation, so these "
            "are transductive observation-consistency diagnostics, not independent "
            "held-out generalization."
        )
        forbidden_claims = [
            "independent held-out generalization",
            "ground-truth accuracy",
            "true completeness or hole area",
        ]
        component_hashes["frozen_sim3_canonical"] = FROZEN_SIM3_SHA256

    _require_hash("dmcache", component_hashes["dmcache"], expected_dm_hash)
    _require_hash("model cache", component_hashes["model_cache"], expected_model_hash)

    overlap = sorted(set(reconstruction_names) & set(heldout_names))
    if overlap:
        raise PreparationError(f"reconstruction/heldout lists overlap: {overlap[:5]}")

    image_root_resolved = images_path.resolve()
    if not image_root_resolved.is_dir():
        raise PreparationError(f"image root is not a directory: {images_path}")
    if contract_image_root is not None and image_root_resolved != contract_image_root:
        raise PreparationError(
            "image root does not match input contract images.root: "
            f"expected {contract_image_root}, found {image_root_resolved}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}.work.", dir=output.parent
    ) as temporary:
        work = Path(temporary)
        with _streaming_dmcache(dmcache_path, work) as (dm_names, dm_depth, signature):
            if (
                dm_depth.shape != expected_depth_shape
                or dm_depth.dtype != expected_depth_dtype
            ):
                raise PreparationError(
                    "dmcache depth contract mismatch: "
                    f"expected {expected_depth_shape} {expected_depth_dtype}, "
                    f"found {dm_depth.shape} {dm_depth.dtype}"
                )
            if signature != expected_signature:
                raise PreparationError(
                    "dmcache signature mismatch: "
                    f"expected {expected_signature!r}, found {signature!r}"
                )
            if expected_dm_frames is not None and dm_names != expected_dm_frames:
                raise PreparationError("dmcache frame order differs from input contract")
            model_names, model_intrinsics, model_w2c = _load_model_cache(
                model_path, len(dm_names)
            )
            if expected_model_frames is not None and model_names != expected_model_frames:
                raise PreparationError("model-cache frame order differs from input contract")
            if set(dm_names) != set(model_names):
                raise PreparationError("dmcache/model exact-name join differs")
            dm_name_set = set(dm_names)
            requested = reconstruction_names + heldout_names
            missing_join = [name for name in requested if name not in dm_name_set]
            if missing_join:
                raise PreparationError(
                    f"list exact-name join failed for {missing_join[:5]}"
                )
            if registered_images is not None:
                verified_image_manifest = _verify_registered_image_identities(
                    image_root_resolved, dm_names, registered_images
                )
                if verified_image_manifest != registered_image_manifest:
                    raise PreparationError("image identity root manifest mismatch")
                component_hashes["registered_image_root_manifest"] = (
                    verified_image_manifest
                )
            else:
                missing_images = [
                    name for name in dm_names if not (image_root_resolved / name).is_file()
                ]
                if missing_images:
                    raise PreparationError(
                        f"image-root exact-name join is missing {missing_images[:5]}"
                    )

            dm_index = {name: index for index, name in enumerate(dm_names)}
            model_index = {name: index for index, name in enumerate(model_names)}
            reconstruction_dm_indices = [dm_index[name] for name in reconstruction_names]
            reconstruction_model_indices = [model_index[name] for name in reconstruction_names]
            reconstruction_K = model_intrinsics[reconstruction_model_indices]
            reconstruction_w2c = model_w2c[reconstruction_model_indices]

            frame_count = len(heldout_names)
            height, width = dm_depth.shape[1:]
            result_shape = (frame_count, height, width)
            stored_depth = np.lib.format.open_memmap(
                work / "heldout_depth.npy",
                mode="w+",
                dtype=np.float32,
                shape=result_shape,
            )
            masks = {
                name: np.lib.format.open_memmap(
                    work / f"{name}.npy",
                    mode="w+",
                    dtype=np.bool_,
                    shape=result_shape,
                )
                for name in ("roi", "low_texture", "weak_support", "planar_single_surface")
            }
            stored_K = np.empty((frame_count, 3, 3), dtype=np.float32)
            stored_w2c = np.empty((frame_count, 4, 4), dtype=np.float32)
            image_entries: list[dict[str, object]] = []
            mask_counts: dict[str, list[int]] = {name: [] for name in masks}

            for frame_index, name in enumerate(heldout_names):
                depth_index = dm_index[name]
                camera_index = model_index[name]
                frame_depth = dm_depth[depth_index]
                np.copyto(stored_depth[frame_index], frame_depth)
                stored_K[frame_index] = model_intrinsics[camera_index]
                stored_w2c[frame_index] = model_w2c[camera_index]

                image_path = image_root_resolved / name
                try:
                    image_payload = image_path.read_bytes()
                except OSError as exc:
                    raise PreparationError(f"registered image cannot be read: {name}") from exc
                image_hash = hashlib.sha256(image_payload).hexdigest()
                if registered_images is not None:
                    expected_image = registered_images[name]
                    if (
                        len(image_payload) != expected_image["size_bytes"]
                        or image_hash != expected_image["sha256"]
                    ):
                        raise PreparationError(f"image identity mismatch: {name}")
                heldout_rgb, image_preparation = _decode_srgb_image(
                    image_payload,
                    (height, width),
                    name,
                    expected_raw_size_wh=expected_raw_size_wh,
                )
                image_entries.append(
                    {
                        "name": name,
                        "sha256": image_hash,
                        "size_bytes": len(image_payload),
                        **image_preparation,
                    }
                )

                frame_masks = _frame_masks(
                    heldout_depth=frame_depth,
                    heldout_intrinsics=model_intrinsics[camera_index],
                    heldout_w2c=model_w2c[camera_index],
                    heldout_rgb=heldout_rgb,
                    reconstruction_depth=dm_depth,
                    reconstruction_intrinsics=reconstruction_K,
                    reconstruction_w2c=reconstruction_w2c,
                    reconstruction_depth_indices=reconstruction_dm_indices,
                    minimum_weak_baseline_model_units=(
                        MIN_WEAK_BASELINE_METRES / metres_per_model_unit
                    ),
                    planar_max_residual_model_units=(
                        PLANAR_MAX_RESIDUAL_METRES / metres_per_model_unit
                    ),
                )
                for mask_name, value in zip(masks, frame_masks, strict=True):
                    masks[mask_name][frame_index] = value
                    mask_counts[mask_name].append(int(np.count_nonzero(value)))

            stored_depth.flush()
            for value in masks.values():
                value.flush()

            frames_dtype = np.dtype(f"<U{max(len(name) for name in heldout_names)}")
            stored_frames = np.asarray(heldout_names, dtype=frames_dtype)
            contract_arrays: dict[str, np.ndarray] = {
                "frames": stored_frames,
                "depth": stored_depth,
                "K": stored_K,
                "w2c": stored_w2c,
                "roi": masks["roi"],
                "low_texture": masks["low_texture"],
                "weak_support": masks["weak_support"],
                "planar_single_surface": masks["planar_single_surface"],
            }
            if tuple(contract_arrays) != mesh_ab_eval.CONTRACT_ARRAY_KEYS:
                raise AssertionError("prepared archive schema order changed")
            evaluator_digest = mesh_ab_eval.frozen_input_digest(contract_arrays)
            semantic_manifests = {
                "reconstruction": _semantic_manifest(
                    reconstruction_names,
                    dm_index,
                    model_index,
                    dm_depth,
                    model_intrinsics,
                    model_w2c,
                ),
                "heldout": _semantic_manifest(
                    heldout_names,
                    dm_index,
                    model_index,
                    dm_depth,
                    model_intrinsics,
                    model_w2c,
                ),
            }

            temporary_archive = work / "prepared.npz"
            with temporary_archive.open("xb") as handle:
                np.savez_compressed(handle, **contract_arrays)
                handle.flush()
                os.fsync(handle.fileno())
            component_hashes["output_npz"] = sha256_file(temporary_archive)
            component_hashes["heldout_images_manifest"] = _heldout_image_manifest(
                image_entries
            )
            component_hashes["b0_prepare_eval.py"] = sha256_file(Path(__file__))
            evaluator_source = Path(mesh_ab_eval.__file__).resolve()
            component_hashes["mesh_ab_eval.py"] = sha256_file(evaluator_source)

            # Detect source mutation between the initial frozen-hash check and
            # publication.  A changed input produces no final artifact.
            _require_hash("dmcache", sha256_file(dmcache_path), component_hashes["dmcache"])
            _require_hash("model cache", sha256_file(model_path), component_hashes["model_cache"])
            _require_hash(
                "reconstruction list",
                sha256_file(reconstruction_path),
                component_hashes["reconstruction_list"],
            )
            _require_hash(
                "heldout list",
                sha256_file(heldout_path),
                component_hashes["heldout_list"],
            )
            if contract_path is not None:
                _require_hash(
                    "input contract",
                    sha256_file(contract_path),
                    component_hashes["input_contract"],
                )
            if registered_images is not None:
                final_image_manifest = _verify_registered_image_identities(
                    image_root_resolved, dm_names, registered_images
                )
                if final_image_manifest != registered_image_manifest:
                    raise PreparationError("image identity root manifest changed")

            weak_minimum_baseline_model_units = (
                MIN_WEAK_BASELINE_METRES / metres_per_model_unit
            )
            planar_max_residual_model_units = (
                PLANAR_MAX_RESIDUAL_METRES / metres_per_model_unit
            )
            coordinate_scale: dict[str, object] = {
                "stored_coordinate_frame": (
                    "raw LAPA" if generic_contract is None else coordinate_frame
                ),
                "contract_coordinate_frame": coordinate_frame,
                "stored_arrays_rescaled": False,
                "metres_per_model_unit": metres_per_model_unit,
                "absolute_threshold_conversion": (
                    "model_units = metres / metres_per_model_unit"
                ),
            }
            if generic_contract is None:
                # Preserve the legacy trio provenance surface only on the
                # legacy path.  A generic cap50 contract must never inherit
                # this unrelated Sim(3) identity.
                coordinate_scale.update(
                    {
                        "metres_per_raw_lapa_unit": metres_per_model_unit,
                        "frozen_sim3_sha256": FROZEN_SIM3_SHA256,
                    }
                )

            split_binding = {
                "dataset_id": dataset_id,
                "split_id": split_profile,
                "route_allowed": route_allowed,
                "quality_scoring_forbidden": quality_scoring_forbidden,
                "reconstruction_file_sha256": reconstruction_hash,
                "heldout_file_sha256": heldout_hash,
                "reconstruction_ordered_semantic_sha256": (
                    input_contract_module.ordered_frame_names_sha256(
                        reconstruction_names
                    )
                ),
                "heldout_ordered_semantic_sha256": (
                    input_contract_module.ordered_frame_names_sha256(heldout_names)
                ),
            }

            provenance_payload: dict[str, object] = {
                "schema_version": PROVENANCE_SCHEMA_VERSION,
                "artifact_schema_version": SCHEMA_VERSION,
                "input_only": True,
                "mesh_inputs_accepted": False,
                "dataset_id": dataset_id,
                "split_id": split_profile,
                "split_profile": split_profile,
                "route_allowed": route_allowed,
                "quality_scoring_forbidden": quality_scoring_forbidden,
                "split_binding": split_binding,
                "frame_order": list(heldout_names),
                "frame_count": frame_count,
                "shape": [frame_count, height, width],
                "stored_dtypes": {
                    "frames": stored_frames.dtype.str,
                    "depth": stored_depth.dtype.str,
                    "K": stored_K.dtype.str,
                    "w2c": stored_w2c.dtype.str,
                    "masks": np.dtype(np.bool_).str,
                },
                "geometry_compute_dtype": "float64",
                "runtime_versions": {
                    "python": sys.version.split()[0],
                    "numpy": np.__version__,
                    "opencv": cv2.__version__,
                },
                "coordinate_scale": coordinate_scale,
                "image_contract": {
                    "image_root": str(image_root_resolved),
                    "contract_image_root": (
                        str(contract_image_root) if contract_image_root is not None else None
                    ),
                    "raw_size_wh": (
                        list(expected_raw_size_wh)
                        if expected_raw_size_wh is not None
                        else None
                    ),
                    "decode": "cv2.imdecode IMREAD_COLOR|IMREAD_IGNORE_ORIENTATION",
                    "exif_orientation_applied": False,
                },
                "component_sha256": component_hashes,
                "observation_semantic_manifest_sha256": semantic_manifests,
                "semantic_manifest_sha256": semantic_manifests,
                "heldout_images": image_entries,
                "evaluator_digest": evaluator_digest,
                "evaluation_digest": evaluator_digest,
                "evaluator_digest_function": "mesh_ab_eval.frozen_input_digest",
                "constants": {
                    "valid_mask": "isfinite(camera_Z) and camera_Z > 0",
                    "valid_erosion_chebyshev_radius_px": VALID_EROSION_RADIUS_PX,
                    "candidate_camera_count": CANDIDATE_CAMERA_COUNT,
                    "candidate_tie_break": "frozen reconstruction-list order",
                    "roi_minimum_consistent_candidates": MIN_ROI_SUPPORT,
                    "projection_margin_px": PROJECTION_MARGIN_PX,
                    "roundtrip_pixel_error_strict_less_than_px": PIXEL_REPROJECTION_ERROR_PX,
                    "roundtrip_relative_camera_z_strict_less_than": RELATIVE_CAMERA_Z_ERROR,
                    "weak_minimum_baseline_metres": MIN_WEAK_BASELINE_METRES,
                    "weak_minimum_baseline_model_units": (
                        weak_minimum_baseline_model_units
                    ),
                    "weak_world_normal_dot_strict_greater_than": WORLD_NORMAL_DOT,
                    "weak_support_counts_inclusive_set": list(WEAK_SUPPORT_COUNTS),
                    "low_texture_srgb_eotf": "IEC 61966-2-1 piecewise sRGB to linear",
                    "image_preparation": (
                        "cv2 IMREAD_COLOR|IMREAD_IGNORE_ORIENTATION decode of the encoded "
                        "raster, assert generic-contract raw width/height before resizing, "
                        "convert BGR to RGB, then cv2.resize to the frozen depth-grid size "
                        "with INTER_AREA unconditionally"
                    ),
                    "low_texture_linear_luminance_weights": [0.2126, 0.7152, 0.0722],
                    "sobel_gx_over_8": SOBEL_X_OVER_8.tolist(),
                    "sobel_gy_over_8": SOBEL_Y_OVER_8.tolist(),
                    "sobel_border": "OpenCV BORDER_REFLECT_101",
                    "texture_rms_window": [TEXTURE_WINDOW, TEXTURE_WINDOW],
                    "low_texture_rms_strict_less_than": LOW_TEXTURE_RMS,
                    "planar_window": [PLANAR_WINDOW, PLANAR_WINDOW],
                    "planar_fit": "unweighted float64 SVD",
                    "planar_unoriented_normal_spread_max_deg": PLANAR_NORMAL_SPREAD_DEG,
                    "planar_max_absolute_residual_metres": PLANAR_MAX_RESIDUAL_METRES,
                    "planar_max_absolute_residual_model_units": (
                        planar_max_residual_model_units
                    ),
                },
                "algorithms": {
                    "roi": (
                        "5px square erosion of positive-finite heldout camera-Z; then >=3 "
                        "strict round-trip-consistent projections among 8 nearest reconstruction "
                        "camera centers with a 16px source-image margin"
                    ),
                    "low_texture": (
                        "sRGB EOTF, linear-light luminance, fixed Sobel /8, and 11x11 "
                        "RMS gradient magnitude, intersected with ROI"
                    ),
                    "weak_support": (
                        "exactly 3 or 4 strict round-trip and world-normal-consistent views "
                        "among the 8 nearest reconstruction cameras with baseline >=0.04 m "
                        "converted through the input-contract coordinate scale, "
                        "intersected with ROI"
                    ),
                    "planar_single_surface": (
                        "11x11 valid input points/normals, unoriented normal spread, and "
                        "unweighted float64 SVD plane residual <=0.005 m converted through "
                        "the input-contract coordinate scale, intersected with ROI"
                    ),
                    "depth_sampling": "float64 bilinear camera-Z with nearest positive-finite mask",
                    "normal_sampling": (
                        "float64 bilinear world normals with all four samples finite"
                    ),
                },
                "mask_true_counts_per_frame": mask_counts,
                "limitations": {
                    "transductive_observation_consistency": transductive_present,
                    "route_allowed": route_allowed,
                    "quality_scoring_forbidden": quality_scoring_forbidden,
                    "warning": transductive_warning,
                    "not_ground_truth": True,
                    "forbidden_claims": forbidden_claims,
                },
            }
            if generic_contract is None:
                provenance_payload["constants"]["weak_minimum_baseline_raw_lapa"] = (
                    weak_minimum_baseline_model_units
                )
                provenance_payload["constants"][
                    "planar_max_absolute_residual_raw_lapa"
                ] = planar_max_residual_model_units
            temporary_provenance = work / "prepared.provenance.json"
            _write_json(temporary_provenance, provenance_payload)
            _publish_pair(
                temporary_archive,
                output,
                temporary_provenance,
                provenance,
            )

    return {
        "status": "PREPARED",
        "output": str(output.resolve()),
        "provenance": str(provenance.resolve()),
        "dataset_id": dataset_id,
        "split_id": split_profile,
        "split_profile": split_profile,
        "route_allowed": route_allowed,
        "quality_scoring_forbidden": quality_scoring_forbidden,
        "heldout_frame_count": len(heldout_names),
        "evaluator_digest": evaluator_digest,
        "evaluation_digest": evaluator_digest,
        "output_sha256": component_hashes["output_npz"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dmcache", type=Path, required=True)
    parser.add_argument("--model-cache", type=Path, required=True)
    parser.add_argument("--reconstruction-list", type=Path, required=True)
    parser.add_argument("--heldout-list", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument(
        "--input-contract",
        type=Path,
        help=(
            "pre-registered b0-input-contract-v1 JSON; requires --split-id. "
            "Omit both flags only for the frozen legacy trio contract"
        ),
    )
    parser.add_argument(
        "--split-id",
        help="explicit route/evaluation split key from --input-contract",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = prepare_evaluation_inputs(
            dmcache=args.dmcache,
            model_cache=args.model_cache,
            reconstruction_list=args.reconstruction_list,
            heldout_list=args.heldout_list,
            image_root=args.image_root,
            input_contract=args.input_contract,
            split_id=args.split_id,
            out=args.out,
        )
    except (PreparationError, FileExistsError, OSError) as exc:
        print(f"B0_PREPARE_EVAL_FAILED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
