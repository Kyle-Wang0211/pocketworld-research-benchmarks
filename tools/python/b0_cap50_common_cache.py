#!/usr/bin/env python3
"""Generate the frozen common cap50 depth input for the B0 meshing A/B test.

This program stops before meshing.  It validates the real 115-frame cap50
capture, freezes a five-view CoreML CasDiffMVS input contract using only input
cameras and optimized-SfM sparse points, predicts raw camera-Z depth/confidence once,
and applies the certified ``ofull`` geometric mask once.  The resulting masked
depth cache is then suitable for *both* FuseCut and TSDF, so the mesher is the
only intended experimental variable.

Every invocation requires explicit immutable inputs and a brand-new output
directory.  A ``--limit`` invocation is permanently labelled smoke-only and
must never be promoted as the 115-frame cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import struct
import sys
import time
import traceback
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np

from b0_input_contract import load_input_contract, validate_input_contract


WORK_W, WORK_H = 1024, 576
PROC_W, PROC_H = 896, 512
EXPECTED_FRAME_COUNT = 115
EXPECTED_SFM_FRAME_COUNT = 139
NVIEW = 5
SOURCE_COUNT = NVIEW - 1
FUSION_NEIGHBORS = 8
MIN_SOURCE_BASELINE_M = 0.06
MAX_SOURCE_BASELINE_M = 1.50
MAX_SOURCE_FORWARD_ANGLE_DEG = 45.0
TARGET_SOURCE_BASELINE_M = 0.25
MIN_FUSION_BASELINE_M = 0.04
DEPTH_VALUES = 384

GEO_MASK = 3
PHOTO = 0.5
BOUND_REL = 0.03
NORMAL_COS = 0.5
GEO_PIX = 1.0
GEO_DEP = 0.01
SPLIT_ID = "cap50_93r22h_strict"
FROZEN_CAP50_FRAME_ORDER_SHA256 = (
    "b632e81a048b1de96d36539e2edab67b0a721f7447d0392369cf2f96cf500c61"
)
FROZEN_CAP50_RECONSTRUCTION_ORDER_SHA256 = (
    "8ef00f3b310ed5d3c0ee00ff49f92e46cdfbadf703faec23e46a203367822666"
)
FROZEN_CAP50_HELDOUT_ORDER_SHA256 = (
    "2cf47fa3fcdb329711f762bfd360668158d3fb5915d7fd754bdfc2d6df577980"
)
FIXED_K_PROC = np.array(
    [[598.656006, 0.0, 449.573212], [0.0, 608.158508, 256.515503], [0.0, 0.0, 1.0]],
    dtype=np.float32,
)

FULL_SIGNATURE = (
    "B0_CAP50_COMMON_CAMERA_Z_MASKED_115_896x512_"
    "G3_P0.5_BOUND0.03_NORMAL0.5_PIX1_DEPTH0.01_V1"
)
FROZEN_COREML_MODEL_TREE_SHA256 = "9fdbcd59356ea01e0e7c96d492a942c92d994d687dfc382d4fd8d11eb5932843"
FROZEN_COREML_DEPTH_KEY = "var_16044"
FROZEN_COREML_CONFIDENCE_KEY = "var_16002"
FROZEN_COREML_OUTPUT_EVIDENCE_SHA256 = "a1b8560c5315b39f52b240f43246bf647fd7358f529214baf0e84897a88256ba"
FROZEN_COREML_OUTPUT_EVIDENCE_RELATIVE_PATH = Path("python/gpu_sfm_ab/precision_probe_130.log")
FROZEN_COREML_OUTPUT_EVIDENCE_LINE = (
    "[probe] fp16 out: depth=var_16044 conf=var_16002 | "
    "fp32 out: depth=var_16044 conf=var_16002"
)


class ContractError(RuntimeError):
    """The frozen input/output contract was not satisfied."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path, chunk_bytes: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Canonical package hash: relative path, file hash, and byte size."""
    if not path.is_dir():
        raise ContractError(f"model package is not a directory: {path}")
    rows: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for item in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.relative_to(path).as_posix()):
        rel = item.relative_to(path).as_posix()
        size = item.stat().st_size
        file_hash = sha256_file(item)
        digest.update(f"{rel}\t{file_hash}\t{size}\n".encode("utf-8"))
        rows.append({"relative_path": rel, "sha256": file_hash, "size_bytes": size})
    if not rows:
        raise ContractError(f"empty model package: {path}")
    return digest.hexdigest(), rows


def ordered_names_sha256(names: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for name in names:
        digest.update(f"{name}\n".encode("utf-8"))
    return digest.hexdigest()


def require_frozen_cap50_cohort(
    names: Sequence[str],
    reconstruction_names: Sequence[str],
    heldout_names: Sequence[str],
) -> dict[str, str]:
    """Reject any cohort or split order other than the pre-registered cap50."""
    hashes = {
        "frame_order_sha256": ordered_names_sha256(names),
        "reconstruction_order_sha256": ordered_names_sha256(reconstruction_names),
        "heldout_order_sha256": ordered_names_sha256(heldout_names),
    }
    expected = {
        "frame_order_sha256": FROZEN_CAP50_FRAME_ORDER_SHA256,
        "reconstruction_order_sha256": FROZEN_CAP50_RECONSTRUCTION_ORDER_SHA256,
        "heldout_order_sha256": FROZEN_CAP50_HELDOUT_ORDER_SHA256,
    }
    mismatches = [key for key in expected if hashes[key] != expected[key]]
    if mismatches:
        raise ContractError(
            "frozen cap50 ordered cohort hash mismatch: "
            + ", ".join(
                f"{key}=actual:{hashes[key]},expected:{expected[key]}"
                for key in mismatches
            )
        )
    return hashes


def image_root_manifest_sha256(
    names: Sequence[str], images_by_name: Mapping[str, Mapping[str, Any]]
) -> str:
    digest = hashlib.sha256()
    for name in names:
        row = images_by_name[name]
        digest.update(f"{name}\t{row['sha256']}\t{int(row['size_bytes'])}\n".encode("utf-8"))
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(struct.pack("<I", array.ndim))
    digest.update(struct.pack(f"<{array.ndim}Q", *array.shape))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write(_json_bytes(value))


def write_npz_exclusive(path: Path, **arrays: Any) -> None:
    with path.open("xb") as handle:
        np.savez_compressed(handle, **arrays)


def write_names_exclusive(path: Path, names: Sequence[str]) -> None:
    with path.open("xb") as handle:
        for name in names:
            handle.write(f"{name}\n".encode("utf-8"))


def create_exclusive_output_dir(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ContractError(f"output directory already exists; refusing overwrite: {path}")
    if not path.parent.is_dir():
        raise ContractError(f"output parent must already exist and be a directory: {path.parent}")
    try:
        path.mkdir(mode=0o755)
    except FileExistsError as exc:
        raise ContractError(f"output directory already exists; refusing overwrite: {path}") from exc


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ContractError(f"{label} is not a regular file: {path}")


def scale_intrinsics(
    K: np.ndarray,
    source_wh: tuple[int, int] = (WORK_W, WORK_H),
    target_wh: tuple[int, int] = (PROC_W, PROC_H),
) -> np.ndarray:
    source_w, source_h = source_wh
    target_w, target_h = target_wh
    value = np.asarray(K, dtype=np.float64)
    if value.shape != (3, 3) or not np.isfinite(value).all():
        raise ContractError(f"invalid 3x3 intrinsics: shape={value.shape}")
    if source_w <= 0 or source_h <= 0 or target_w <= 0 or target_h <= 0:
        raise ContractError("image sizes must be positive")
    out = value.copy()
    out[0, :] *= target_w / source_w
    out[1, :] *= target_h / source_h
    out[2, :] = (0.0, 0.0, 1.0)
    return out.astype(np.float32)


def decode_arkit_extrinsic_to_w2c(extrinsic: Sequence[float]) -> np.ndarray:
    values = np.asarray(extrinsic, dtype=np.float64)
    if values.shape != (16,) or not np.isfinite(values).all():
        raise ContractError("ARKit extrinsic must contain 16 finite numbers")
    c2w_arkit = values.reshape(4, 4).T
    c2w_cv = np.eye(4, dtype=np.float64)
    c2w_cv[:3, :3] = c2w_arkit[:3, :3] @ np.diag([1.0, -1.0, -1.0])
    c2w_cv[:3, 3] = c2w_arkit[:3, 3]
    return np.linalg.inv(c2w_cv)


def camera_center(w2c: np.ndarray) -> np.ndarray:
    value = np.asarray(w2c, dtype=np.float64)
    return -value[:3, :3].T @ value[:3, 3]


def _validate_w2c(w2c: np.ndarray, name: str) -> None:
    value = np.asarray(w2c, dtype=np.float64)
    if value.shape != (4, 4) or not np.isfinite(value).all():
        raise ContractError(f"invalid w2c for {name}")
    if not np.allclose(value[3], [0, 0, 0, 1], atol=2e-6):
        raise ContractError(f"invalid homogeneous w2c row for {name}: {value[3].tolist()}")
    rotation = value[:3, :3]
    if not np.allclose(rotation @ rotation.T, np.eye(3), atol=3e-6):
        raise ContractError(f"non-orthonormal w2c rotation for {name}")
    if not np.isclose(np.linalg.det(rotation), 1.0, atol=3e-6):
        raise ContractError(f"improper w2c rotation for {name}")


def decode_rgb(
    path: Path,
    target_wh: tuple[int, int] = (PROC_W, PROC_H),
    expected_raw_wh: tuple[int, int] = (3840, 2160),
) -> np.ndarray:
    # cap50 JPEGs carry EXIF Orientation=6.  CoreML K is defined on the encoded
    # raw raster, so OpenCV's default EXIF autorotation would silently turn the
    # image into 2160x3840 and invalidate every projection matrix.
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    if bgr is None:
        raise ContractError(f"OpenCV could not decode image: {path}")
    expected_w, expected_h = expected_raw_wh
    if bgr.shape[:2] != (expected_h, expected_w):
        raise ContractError(
            f"raw encoded image must be {expected_w}x{expected_h} before resize: "
            f"{path} decoded as {bgr.shape[1]}x{bgr.shape[0]}"
        )
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, target_wh, interpolation=cv2.INTER_AREA)
    return (rgb.astype(np.float32) / np.float32(255.0))


def quaternion_wxyz_to_rotation(quaternion: Sequence[float]) -> np.ndarray:
    q = np.asarray(quaternion, dtype=np.float64)
    if q.shape != (4,) or not np.isfinite(q).all():
        raise ContractError("SfM quaternion must contain four finite wxyz values")
    norm = float(np.linalg.norm(q))
    if not np.isclose(norm, 1.0, atol=2e-6):
        raise ContractError(f"SfM quaternion is not unit length: {norm}")
    w, x, y, z = q / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def sfm_pose_to_w2c(pose: Mapping[str, Any]) -> np.ndarray:
    if pose.get("registered") is not True:
        raise ContractError(f"unregistered SfM pose: frame_id={pose.get('frame_id')}")
    out = np.eye(4, dtype=np.float64)
    out[:3, :3] = quaternion_wxyz_to_rotation(pose["quat_wxyz"])
    translation = np.asarray(pose["t"], dtype=np.float64)
    if translation.shape != (3,) or not np.isfinite(translation).all():
        raise ContractError(f"invalid SfM translation: frame_id={pose.get('frame_id')}")
    out[:3, 3] = translation
    return out


def _umeyama(source: np.ndarray, target: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    src = np.asarray(source, dtype=np.float64)
    dst = np.asarray(target, dtype=np.float64)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[1] != 3 or len(src) < 3:
        raise ContractError("Sim3 fit requires aligned Nx3 camera centers")
    src_mean, dst_mean = src.mean(axis=0), dst.mean(axis=0)
    src_zero, dst_zero = src - src_mean, dst - dst_mean
    covariance = dst_zero.T @ src_zero / len(src)
    left, singular, right_t = np.linalg.svd(covariance)
    sign = np.eye(3)
    sign[-1, -1] = np.sign(np.linalg.det(left @ right_t))
    rotation = left @ sign @ right_t
    variance = float(np.mean(np.sum(src_zero * src_zero, axis=1)))
    scale = float(np.trace(np.diag(singular) @ sign) / variance)
    translation = dst_mean - scale * rotation @ src_mean
    return scale, rotation, translation


def frozen_split(total: int) -> tuple[list[int], list[int]]:
    if total != EXPECTED_FRAME_COUNT:
        raise ContractError(f"cap50 strict split requires {EXPECTED_FRAME_COUNT} frames, got {total}")
    heldout = list(range(4, 110, 5))
    reconstruction = [index for index in range(total) if index not in set(heldout)]
    if len(reconstruction) != 93 or len(heldout) != 22:
        raise AssertionError("internal cap50 split cardinality error")
    return reconstruction, heldout


def visible_sparse_points(
    points: np.ndarray,
    K: np.ndarray,
    w2c: np.ndarray,
    image_wh: tuple[int, int] = (WORK_W, WORK_H),
    min_depth_m: float = 0.05,
    metres_per_model_unit: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    xyz = np.asarray(points, dtype=np.float64)
    intrinsic = np.asarray(K, dtype=np.float64)
    pose = np.asarray(w2c, dtype=np.float64)
    if xyz.ndim != 2 or xyz.shape[1] != 3 or not np.isfinite(xyz).all():
        raise ContractError("sparse points must be finite Nx3")
    camera = (pose[:3, :3] @ xyz.T + pose[:3, 3:4]).T
    z = camera[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        projected = (intrinsic @ camera.T).T
        u = projected[:, 0] / projected[:, 2]
        v = projected[:, 1] / projected[:, 2]
    width, height = image_wh
    visible = (
        np.isfinite(u)
        & np.isfinite(v)
        & np.isfinite(z)
        & (z > min_depth_m / metres_per_model_unit)
        & (u >= 0.0)
        & (u < width)
        & (v >= 0.0)
        & (v < height)
    )
    return visible, z


def input_depth_range(
    points: np.ndarray,
    visible: np.ndarray,
    camera_z: np.ndarray,
    metres_per_model_unit: float = 1.0,
) -> tuple[float, float, int]:
    del points  # Included in the API to make the input-only provenance explicit.
    selected = np.asarray(camera_z, dtype=np.float64)[np.asarray(visible, dtype=bool)]
    selected = selected[
        np.isfinite(selected) & (selected > 0.05 / metres_per_model_unit)
    ]
    if selected.size < 8:
        raise ContractError(f"too few visible optimized-SfM sparse points for depth range: {selected.size}")
    lo, hi = np.percentile(selected, [2.0, 99.5])
    dmin = float(max(0.1 / metres_per_model_unit, lo * 0.70))
    dmax = float(hi * 1.50)
    if not np.isfinite([dmin, dmax]).all() or not (dmax > dmin > 0):
        raise ContractError(f"invalid input-derived depth range: [{dmin}, {dmax}]")
    return dmin, dmax, int(selected.size)


def _camera_forward_world(w2c: np.ndarray) -> np.ndarray:
    pose = np.asarray(w2c, dtype=np.float64)
    if pose.shape != (4, 4) or not np.isfinite(pose).all():
        raise ContractError("camera forward-axis requires a finite 4x4 w2c")
    axis = pose[:3, :3].T @ np.array([0.0, 0.0, 1.0], dtype=np.float64)
    length = float(np.linalg.norm(axis))
    if not np.isfinite(length) or length <= 0:
        raise ContractError("camera forward-axis is degenerate")
    return axis / length


def _forward_angle_deg(ref_w2c: np.ndarray, src_w2c: np.ndarray) -> float:
    cosine = float(np.dot(_camera_forward_world(ref_w2c), _camera_forward_world(src_w2c)))
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def select_sources_for_ref(
    ref_index: int,
    visibility: np.ndarray,
    points: np.ndarray,
    centers: np.ndarray,
    w2c: np.ndarray,
    names: Sequence[str],
    *,
    k: int = SOURCE_COUNT,
    min_baseline_m: float = MIN_SOURCE_BASELINE_M,
    max_baseline_m: float = MAX_SOURCE_BASELINE_M,
    max_forward_angle_deg: float = MAX_SOURCE_FORWARD_ANGLE_DEG,
    target_baseline_m: float = TARGET_SOURCE_BASELINE_M,
    metres_per_model_unit: float,
    candidate_indices: Sequence[int],
) -> tuple[list[str], list[dict[str, Any]]]:
    vis = np.asarray(visibility, dtype=bool)
    xyz = np.asarray(points, dtype=np.float64)
    camera_centers = np.asarray(centers, dtype=np.float64)
    camera_w2c = np.asarray(w2c, dtype=np.float64)
    if vis.shape != (len(names), len(xyz)):
        raise ContractError(f"visibility shape {vis.shape} does not match names/points")
    if not 0 <= ref_index < len(names):
        raise ContractError(f"reference index out of range: {ref_index}")
    if camera_centers.shape != (len(names), 3) or camera_w2c.shape != (len(names), 4, 4):
        raise ContractError("source-selection camera arrays do not match frame order")
    candidates: list[dict[str, Any]] = []
    if not np.isfinite(metres_per_model_unit) or metres_per_model_unit <= 0:
        raise ContractError("metres_per_model_unit must be finite and positive")
    if not (0 < min_baseline_m <= max_baseline_m and target_baseline_m > 0):
        raise ContractError("invalid frozen source baseline thresholds")
    if not 0 < max_forward_angle_deg <= 180:
        raise ContractError("invalid frozen source forward-angle threshold")
    for src_index in candidate_indices:
        if not 0 <= src_index < len(names):
            raise ContractError(f"source candidate index out of range: {src_index}")
        src_name = names[src_index]
        if src_index == ref_index:
            continue
        baseline_model_units = float(np.linalg.norm(camera_centers[src_index] - camera_centers[ref_index]))
        baseline_m = baseline_model_units * metres_per_model_unit
        if baseline_m < min_baseline_m or baseline_m > max_baseline_m:
            continue
        forward_angle_deg = _forward_angle_deg(camera_w2c[ref_index], camera_w2c[src_index])
        if forward_angle_deg > max_forward_angle_deg:
            continue
        shared_mask = vis[ref_index] & vis[src_index]
        shared_count = int(np.count_nonzero(shared_mask))
        if shared_count < 5:
            continue
        selection_score = float(
            abs(np.log(baseline_m / target_baseline_m))
            + forward_angle_deg / max_forward_angle_deg
        )
        candidates.append(
            {
                "source_index": src_index,
                "source": src_name,
                "shared_visible_points": shared_count,
                "baseline_model_units": baseline_model_units,
                "baseline_m": baseline_m,
                "forward_angle_deg": forward_angle_deg,
                "selection_score": selection_score,
            }
        )
    candidates.sort(
        key=lambda row: (
            float(row["selection_score"]),
            int(row["source_index"]),
            str(row["source"]),
        )
    )
    if len(candidates) < k:
        raise ContractError(
            f"{names[ref_index]} has only {len(candidates)} input-valid sources; need {k}"
        )
    selected = candidates[:k]
    for rank, row in enumerate(selected, start=1):
        row["rank"] = rank
        row["selected"] = True
    return [str(row["source"]) for row in selected], selected


def build_projection_pyramid(K: np.ndarray, w2c: np.ndarray) -> dict[str, np.ndarray]:
    intrinsics = np.asarray(K, dtype=np.float32)
    extrinsics = np.asarray(w2c, dtype=np.float32)
    if intrinsics.shape != (NVIEW, 3, 3) or extrinsics.shape != (NVIEW, 4, 4):
        raise ContractError(
            f"CoreML requires exactly five views; got K={intrinsics.shape}, w2c={extrinsics.shape}"
        )
    packed = np.zeros((NVIEW, 2, 4, 4), dtype=np.float32)
    packed[:, 0] = extrinsics
    packed[:, 1, :3, :3] = intrinsics
    result: dict[str, np.ndarray] = {}
    for name, factor in (("p1", 0.125), ("p2", 0.25), ("p3", 0.5), ("p4", 1.0)):
        value = packed.copy()
        value[:, 1, :2, :] *= np.float32(factor)
        result[name] = value[None]
    return result


def depth_values(depth_range: tuple[float, float]) -> np.ndarray:
    dmin, dmax = depth_range
    if not (np.isfinite([dmin, dmax]).all() and dmax > dmin > 0):
        raise ContractError(f"invalid depth range: {depth_range}")
    return np.linspace(1.0 / dmax, 1.0 / dmin, DEPTH_VALUES, dtype=np.float32)[None]


def resolve_frozen_coreml_output_contract(
    *,
    model_tree_sha256: str,
    spec_output_order: Sequence[str],
    semantic_evidence_sha256: str,
) -> dict[str, Any]:
    """Resolve heads from immutable model/evidence identity, never tensor values.

    The exported CoreML features have generated names and empty descriptions.
    Their semantics are nevertheless frozen by the exact package tree, the
    traced wrapper tuple rank (depth first, confidence second), and an archived
    inference log for this exact fp32 package.  A different package, evidence
    file, or spec rank is a different contract and is rejected.
    """
    expected_order = [FROZEN_COREML_DEPTH_KEY, FROZEN_COREML_CONFIDENCE_KEY]
    if model_tree_sha256 != FROZEN_COREML_MODEL_TREE_SHA256:
        raise ContractError(
            "CoreML model tree has no frozen output-semantic contract: "
            f"{model_tree_sha256}"
        )
    if list(spec_output_order) != expected_order:
        raise ContractError(
            f"CoreML spec output order mismatch: expected {expected_order}, "
            f"got {list(spec_output_order)}"
        )
    if semantic_evidence_sha256 != FROZEN_COREML_OUTPUT_EVIDENCE_SHA256:
        raise ContractError(
            "CoreML output-semantic evidence hash mismatch: "
            f"{semantic_evidence_sha256}"
        )
    return {
        "method": "exact model tree + spec tuple rank + frozen research evidence; never value inferred",
        "mapping_was_value_inferred": False,
        "model_tree_sha256": model_tree_sha256,
        "spec_output_order": expected_order,
        "depth_key": FROZEN_COREML_DEPTH_KEY,
        "confidence_key": FROZEN_COREML_CONFIDENCE_KEY,
        "semantic_evidence_sha256": semantic_evidence_sha256,
    }


def _canonical_coreml_output(raw: np.ndarray, key: str) -> np.ndarray:
    value = np.asarray(raw)
    if value.shape == (1, PROC_H, PROC_W):
        value = value[0]
    elif value.shape != (PROC_H, PROC_W):
        raise ContractError(f"CoreML output {key} has invalid shape {value.shape}")
    return value.astype(np.float32, copy=False)


def extract_frozen_coreml_outputs(
    outputs: Mapping[str, np.ndarray], output_contract: Mapping[str, Any]
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Extract frozen heads and validate semantics without reclassifying them."""
    depth_key = output_contract.get("depth_key")
    confidence_key = output_contract.get("confidence_key")
    if (
        output_contract.get("mapping_was_value_inferred") is not False
        or depth_key != FROZEN_COREML_DEPTH_KEY
        or confidence_key != FROZEN_COREML_CONFIDENCE_KEY
        or output_contract.get("model_tree_sha256") != FROZEN_COREML_MODEL_TREE_SHA256
    ):
        raise ContractError("invalid or unfrozen CoreML output contract")
    expected_keys = {FROZEN_COREML_DEPTH_KEY, FROZEN_COREML_CONFIDENCE_KEY}
    if set(outputs) != expected_keys:
        raise ContractError(
            f"CoreML runtime output keys changed: expected {sorted(expected_keys)}, "
            f"got {sorted(outputs)}"
        )
    depth = _canonical_coreml_output(outputs[FROZEN_COREML_DEPTH_KEY], FROZEN_COREML_DEPTH_KEY)
    confidence = _canonical_coreml_output(
        outputs[FROZEN_COREML_CONFIDENCE_KEY], FROZEN_COREML_CONFIDENCE_KEY
    )
    if not np.isfinite(depth).all() or np.any(depth <= 0):
        raise ContractError("frozen CoreML depth output must be finite and strictly positive")
    if (
        not np.isfinite(confidence).all()
        or float(np.min(confidence)) < -1e-4
        or float(np.max(confidence)) > 1.0001
    ):
        raise ContractError("frozen CoreML confidence output must be finite and in [0,1]")
    validation = {
        "mapping_was_value_inferred": False,
        "depth_key": FROZEN_COREML_DEPTH_KEY,
        "confidence_key": FROZEN_COREML_CONFIDENCE_KEY,
        "runtime_keys": sorted(outputs),
        "depth": _output_statistics(depth),
        "confidence": _output_statistics(confidence),
    }
    return depth, confidence, validation


def world_normals(depth: np.ndarray, K: np.ndarray, w2c: np.ndarray) -> np.ndarray:
    value = np.asarray(depth, dtype=np.float32)
    height, width = value.shape
    uu, vv = np.meshgrid(np.arange(width), np.arange(height))
    x = (uu - K[0, 2]) / K[0, 0] * value
    y = (vv - K[1, 2]) / K[1, 1] * value
    points = np.stack([x, y, value], axis=-1)
    du = np.zeros_like(points)
    dv = np.zeros_like(points)
    du[:, 1:-1] = points[:, 2:] - points[:, :-2]
    dv[1:-1] = points[2:] - points[:-2]
    normals = np.cross(du, dv)
    length = np.linalg.norm(normals, axis=-1, keepdims=True)
    normals = np.divide(normals, length, out=np.zeros_like(normals), where=length > 1e-9)
    normals[np.sum(normals * points, axis=-1) > 0] *= -1
    world = normals.reshape(-1, 3) @ np.asarray(w2c, dtype=np.float64)[:3, :3]
    return world.reshape(height, width, 3).astype(np.float32)


def boundary_keep(depth: np.ndarray, rel: float = BOUND_REL) -> np.ndarray:
    value = np.asarray(depth, dtype=np.float32)
    gx = np.zeros_like(value)
    gy = np.zeros_like(value)
    gx[:, 1:-1] = np.abs(value[:, 2:] - value[:, :-2])
    gy[1:-1] = np.abs(value[2:] - value[:-2])
    gradient = np.maximum(gx, gy)
    return (
        np.isfinite(value)
        & (value > 0)
        & (gradient / np.maximum(value, np.float32(1e-6)) < rel)
    )


def reproject_with_depth(
    depth_ref: np.ndarray,
    intrinsics_ref: np.ndarray,
    extrinsics_ref: np.ndarray,
    depth_src: np.ndarray,
    intrinsics_src: np.ndarray,
    extrinsics_src: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    height, width = depth_ref.shape
    x_ref, y_ref = np.meshgrid(np.arange(width), np.arange(height))
    x_flat, y_flat = x_ref.reshape(-1), y_ref.reshape(-1)
    xyz_ref = np.linalg.inv(intrinsics_ref) @ (
        np.vstack((x_flat, y_flat, np.ones_like(x_flat))) * depth_ref.reshape(-1)
    )
    xyz_src = (extrinsics_src @ np.linalg.inv(extrinsics_ref) @ np.vstack((xyz_ref, np.ones_like(x_flat))))[:3]
    projected_src = intrinsics_src @ xyz_src
    with np.errstate(divide="ignore", invalid="ignore"):
        xy_src = projected_src[:2] / projected_src[2:3]
    x_src = np.clip(xy_src[0], -1e8, 1e8).reshape(height, width).astype(np.float32)
    y_src = np.clip(xy_src[1], -1e8, 1e8).reshape(height, width).astype(np.float32)
    sampled_src = cv2.remap(
        depth_src,
        x_src,
        y_src,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    xyz_src_back = np.linalg.inv(intrinsics_src) @ (
        np.vstack((xy_src, np.ones_like(x_flat))) * sampled_src.reshape(-1)
    )
    xyz_reprojected = (
        extrinsics_ref @ np.linalg.inv(extrinsics_src) @ np.vstack((xyz_src_back, np.ones_like(x_flat)))
    )[:3]
    depth_reprojected = xyz_reprojected[2].reshape(height, width).astype(np.float32)
    projected_ref = intrinsics_ref @ xyz_reprojected
    projected_ref = np.where(projected_ref == 0, 1e-5, projected_ref)
    with np.errstate(divide="ignore", invalid="ignore"):
        xy_reprojected = projected_ref[:2] / projected_ref[2:3]
    xy_reprojected = np.clip(xy_reprojected, -1e8, 1e8)
    x_reprojected = xy_reprojected[0].reshape(height, width).astype(np.float32)
    y_reprojected = xy_reprojected[1].reshape(height, width).astype(np.float32)
    return depth_reprojected, x_reprojected, y_reprojected, x_src, y_src


def check_geometric_consistency(
    depth_ref: np.ndarray,
    K_ref: np.ndarray,
    w2c_ref: np.ndarray,
    depth_src: np.ndarray,
    K_src: np.ndarray,
    w2c_src: np.ndarray,
    depth_range: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    dmin, dmax = depth_range
    height, width = depth_ref.shape
    x_ref, y_ref = np.meshgrid(np.arange(width), np.arange(height))
    depth_reproj, x_reproj, y_reproj, x_src, y_src = reproject_with_depth(
        depth_ref, K_ref, w2c_ref, depth_src, K_src, w2c_src
    )
    distance = np.sqrt((x_reproj - x_ref) ** 2 + (y_reproj - y_ref) ** 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        relative_depth = np.abs(depth_reproj - depth_ref) / depth_ref
    mask = (
        np.isfinite(distance)
        & np.isfinite(relative_depth)
        & np.isfinite(depth_ref)
        & np.isfinite(depth_reproj)
        & (depth_ref > dmin)
        & (depth_ref < dmax)
        & (depth_reproj > 0)
        & (distance < GEO_PIX)
        & (relative_depth < GEO_DEP)
    )
    depth_reproj = np.where(mask, depth_reproj, 0.0).astype(np.float32)
    return mask, depth_reproj, x_src, y_src


def _nearest_indices(
    ref_index: int,
    centers: np.ndarray,
    candidate_indices: Iterable[int],
    *,
    k: int,
    min_baseline_m: float,
    metres_per_model_unit: float,
) -> list[int]:
    values = []
    for index in candidate_indices:
        if index == ref_index:
            continue
        distance_model_units = float(np.linalg.norm(centers[index] - centers[ref_index]))
        distance_m = distance_model_units * metres_per_model_unit
        if distance_m >= min_baseline_m:
            values.append((distance_m, index))
    values.sort(key=lambda row: (row[0], row[1]))
    return [index for _, index in values[:k]]


def mask_all_depths(
    names: Sequence[str],
    depth: np.ndarray,
    confidence: np.ndarray,
    K: np.ndarray,
    w2c: np.ndarray,
    centers: np.ndarray,
    depth_ranges: np.ndarray,
    *,
    neighbors: int = FUSION_NEIGHBORS,
    eligible_neighbor_indices: Sequence[int] | None = None,
    metres_per_model_unit: float = 1.0,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    raw_depth = np.asarray(depth, dtype=np.float32)
    raw_conf = np.asarray(confidence, dtype=np.float32)
    count = len(names)
    expected = (count, raw_depth.shape[1], raw_depth.shape[2]) if raw_depth.ndim == 3 else None
    if raw_depth.ndim != 3 or raw_depth.shape != expected or raw_conf.shape != raw_depth.shape:
        raise ContractError("depth/conf arrays must be aligned NxHxW")
    if K.shape != (count, 3, 3) or w2c.shape != (count, 4, 4) or centers.shape != (count, 3):
        raise ContractError("camera arrays do not match raw depth frames")
    normal_cache: dict[int, np.ndarray] = {}

    def normal(index: int) -> np.ndarray:
        if index not in normal_cache:
            normal_cache[index] = world_normals(raw_depth[index], K[index], w2c[index])
        return normal_cache[index]

    masked = np.zeros_like(raw_depth, dtype=np.float32)
    stats: list[dict[str, Any]] = []
    available = list(range(count)) if eligible_neighbor_indices is None else list(eligible_neighbor_indices)
    if any(not 0 <= index < count for index in available):
        raise ContractError("eligible geometric-mask neighbor index is outside the depth cache")
    for ref_index, name in enumerate(names):
        d_ref = raw_depth[ref_index]
        geo_sum = np.zeros_like(d_ref, dtype=np.int32)
        depth_acc = d_ref.copy()
        selected_neighbors = _nearest_indices(
            ref_index,
            centers,
            available,
            k=neighbors,
            min_baseline_m=MIN_FUSION_BASELINE_M,
            metres_per_model_unit=metres_per_model_unit,
        )
        n_ref = normal(ref_index)
        for src_index in selected_neighbors:
            consistent, depth_reproj, x_src, y_src = check_geometric_consistency(
                d_ref,
                K[ref_index].astype(np.float64),
                w2c[ref_index].astype(np.float64),
                raw_depth[src_index],
                K[src_index].astype(np.float64),
                w2c[src_index].astype(np.float64),
                tuple(float(x) for x in depth_ranges[ref_index]),
            )
            sampled_normal = cv2.remap(
                normal(src_index),
                x_src,
                y_src,
                interpolation=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=0,
            )
            normal_ok = np.sum(n_ref * sampled_normal, axis=2) > NORMAL_COS
            consistent &= normal_ok
            geo_sum += consistent.astype(np.int32)
            depth_acc += depth_reproj * consistent
        final = (
            (geo_sum >= GEO_MASK)
            & (raw_conf[ref_index] > PHOTO)
            & boundary_keep(d_ref, BOUND_REL)
        )
        d_avg = depth_acc / (geo_sum + 1)
        masked[ref_index] = np.where(final, d_avg, 0.0).astype(np.float32)
        stats.append(
            {
                "frame": name,
                "fusion_neighbor_indices": selected_neighbors,
                "fusion_neighbors": [str(names[index]) for index in selected_neighbors],
                "geometric_support_required": GEO_MASK,
                "available_fusion_neighbors": len(selected_neighbors),
                "kept_count": int(np.count_nonzero(final)),
                "kept_fraction": float(np.mean(final)),
            }
        )
        # Bound memory: normals are cheap to recompute and large to retain for all frames.
        if len(normal_cache) > neighbors + 2:
            keep = {ref_index, *selected_neighbors}
            normal_cache = {key: value for key, value in normal_cache.items() if key in keep}
    return masked, stats


def cache_signature(limit: int | None, total: int) -> str:
    if limit is None:
        if total != EXPECTED_FRAME_COUNT:
            raise ContractError(f"full cache requires exactly {EXPECTED_FRAME_COUNT} frames, got {total}")
        return FULL_SIGNATURE
    return f"{FULL_SIGNATURE}.SMOKE_ONLY_LIMIT_{limit}"


def run_mode(limit: int | None, total: int) -> str:
    del total
    return "full_common_cache" if limit is None else "smoke_only"


def common_provenance_skeleton(
    *,
    dataset_id: str,
    names: Sequence[str],
    reconstruction_names: Sequence[str],
    heldout_names: Sequence[str],
    metres_per_model_unit: float,
    images_by_name: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    frame_hash = ordered_names_sha256(names)
    reconstruction_hash = ordered_names_sha256(reconstruction_names)
    heldout_hash = ordered_names_sha256(heldout_names)
    return {
        # This is component provenance, not the final b0-input-contract-v1.  The
        # preregistration step binds these immutable cache identities into that
        # final route contract before either mesher may run.
        "schema_version": "b0-cap50-common-cache-provenance-v1",
        "dataset_id": dataset_id,
        "coordinate_frame": "optimized_sfm_cv",
        "metres_per_model_unit": float(metres_per_model_unit),
        "transductive_policy": {
            "present": True,
            "route_allowed": True,
            "quality_scoring_forbidden": False,
            "reason": (
                "transductive only because the pre-existing 139-frame optimized SfM pose solution "
                "and its 139-center metric scale include the 22 heldout cameras; CoreML sources and "
                "geometric-mask neighbors are reconstruction-only, and no heldout depth, score, or "
                "mesher output selects scale or parameters"
            ),
        },
        "dmcache": {
            "sha256": None,
            "signature": None,
            "depth": {"shape": [len(names), PROC_H, PROC_W], "dtype": "float32"},
            "frame_order": list(names),
            "frame_order_sha256": frame_hash,
        },
        "model_cache": {
            "sha256": None,
            "frame_order": list(names),
            "frame_order_sha256": frame_hash,
        },
        "splits": {
            SPLIT_ID: {
                "reconstruction": {
                    "frames": list(reconstruction_names),
                    "file_sha256": None,
                    "semantic_sha256": reconstruction_hash,
                },
                "heldout": {
                    "frames": list(heldout_names),
                    "file_sha256": None,
                    "semantic_sha256": heldout_hash,
                },
            }
        },
        "images": {
            "root_manifest_sha256": image_root_manifest_sha256(names, images_by_name),
            "by_name": dict(images_by_name),
        },
    }


def build_final_input_contract(
    data: Mapping[str, Any],
    *,
    dataset_id: str,
    dmcache_path: Path,
    model_cache_path: Path,
    signature: str,
    depth_shape: tuple[int, int, int],
) -> dict[str, Any]:
    """Bind completed full-cache artifacts into the shared publishable schema."""
    names = list(data["names"])
    frozen_hashes = require_frozen_cap50_cohort(
        names,
        list(data["reconstruction_names"]),
        list(data["heldout_names"]),
    )
    if tuple(depth_shape) != (len(names), PROC_H, PROC_W):
        raise ContractError(
            f"final input contract depth shape mismatch: {depth_shape} vs {(len(names), PROC_H, PROC_W)}"
        )
    split_files = data.get("split_files")
    if not isinstance(split_files, Mapping):
        raise ContractError("final input contract requires materialized split files")
    identity = data.get("identity")
    image_identity = identity.get("image_root") if isinstance(identity, Mapping) else None
    image_root_value = image_identity.get("path") if isinstance(image_identity, Mapping) else None
    if not isinstance(image_root_value, str) or not Path(image_root_value).is_absolute():
        raise ContractError("final input contract requires an absolute validated image root")
    image_root = Path(image_root_value).resolve()
    if not image_root.is_dir():
        raise ContractError(f"final input contract image root is not a directory: {image_root}")
    validation = data.get("validation")
    raw_size_wh = (
        validation.get("jpeg_raw_dimensions_ignore_exif")
        if isinstance(validation, Mapping)
        else None
    )
    if raw_size_wh != [3840, 2160]:
        raise ContractError(
            "final input contract requires validated raw JPEG width/height [3840,2160]"
        )
    payload = common_provenance_skeleton(
        dataset_id=dataset_id,
        names=names,
        reconstruction_names=data["reconstruction_names"],
        heldout_names=data["heldout_names"],
        metres_per_model_unit=float(data["metres_per_model_unit"]),
        images_by_name=data["images_by_name"],
    )
    if (
        payload["dmcache"]["frame_order_sha256"]
        != frozen_hashes["frame_order_sha256"]
        or payload["splits"][SPLIT_ID]["reconstruction"]["semantic_sha256"]
        != frozen_hashes["reconstruction_order_sha256"]
        or payload["splits"][SPLIT_ID]["heldout"]["semantic_sha256"]
        != frozen_hashes["heldout_order_sha256"]
    ):
        raise AssertionError("final contract cohort hashes drifted after validation")
    payload["schema_version"] = "b0-input-contract-v1"
    payload["created_utc"] = utc_now()
    payload["component"] = "cap50_common_camera_z_masked_depth"
    payload["images"].update(
        {
            "root": str(image_root),
            "raw_size_wh": [int(raw_size_wh[0]), int(raw_size_wh[1])],
        }
    )
    payload["dmcache"].update(
        {
            "path": str(dmcache_path.resolve()),
            "sha256": sha256_file(dmcache_path),
            "signature": signature,
            "depth": {"shape": list(depth_shape), "dtype": "float32"},
        }
    )
    payload["model_cache"].update(
        {
            "path": str(model_cache_path.resolve()),
            "sha256": sha256_file(model_cache_path),
        }
    )
    split = payload["splits"][SPLIT_ID]
    for role in ("reconstruction", "heldout"):
        role_identity = split_files.get(role)
        if not isinstance(role_identity, Mapping):
            raise ContractError(f"missing materialized {role} split identity")
        split[role].update(
            {
                "path": str(Path(str(role_identity["path"])).resolve()),
                "file_sha256": str(role_identity["sha256"]),
            }
        )
    try:
        validate_input_contract(payload)
    except Exception as exc:
        raise ContractError(f"generated final input contract failed shared validation: {exc}") from exc
    return payload


def _write_json_atomic_exclusive(path: Path, value: Any) -> None:
    """Publish complete JSON bytes atomically while refusing an existing target."""
    if path.exists() or path.is_symlink():
        raise ContractError(f"input contract already exists; refusing overwrite: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    payload = _json_bytes(value)
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ContractError(f"input contract already exists; refusing overwrite: {path}") from exc
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def write_and_reload_final_input_contract(path: Path, payload: Mapping[str, Any]) -> str:
    """Shared-validate, atomic-publish, reload, and re-hash the final contract."""
    try:
        validate_input_contract(payload)
    except Exception as exc:
        raise ContractError(f"final input contract pre-write validation failed: {exc}") from exc
    _write_json_atomic_exclusive(path, payload)
    try:
        reloaded, loaded_hash = load_input_contract(path)
    except Exception as exc:
        raise ContractError(f"final input contract reload validation failed: {exc}") from exc
    if dict(reloaded) != dict(payload) or loaded_hash != sha256_file(path):
        raise ContractError("final input contract reload/hash identity mismatch")
    return loaded_hash


def _load_json(path: Path, label: str) -> Any:
    _require_file(path, label)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid {label} JSON {path}: {exc}") from exc


def _load_jsonl(path: Path, label: str) -> list[Any]:
    _require_file(path, label)
    rows: list[Any] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ContractError(f"blank line in {label} at line {line_number}")
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid {label} JSONL {path}: {exc}") from exc
    return rows


def _image_identity(names: Sequence[str], image_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    images: dict[str, dict[str, Any]] = {}
    sidecars: dict[str, dict[str, Any]] = {}
    for name in names:
        image = image_root / name
        sidecar = image.with_suffix(".json")
        _require_file(image, "cap50 image")
        _require_file(sidecar, "cap50 sidecar")
        images[name] = {"sha256": sha256_file(image), "size_bytes": image.stat().st_size}
        sidecars[sidecar.name] = {"sha256": sha256_file(sidecar), "size_bytes": sidecar.stat().st_size}
    return images, sidecars


def _sidecar_manifest_sha256(names: Sequence[str], sidecars: Mapping[str, Mapping[str, Any]]) -> str:
    ordered = [Path(name).with_suffix(".json").name for name in names]
    return image_root_manifest_sha256(ordered, sidecars)


def load_and_validate_inputs(args: argparse.Namespace) -> dict[str, Any]:
    """Load the authoritative optimized-SfM cap50 camera contract.

    The older ARKit sidecar/``poses.json`` camera path is deliberately not used
    for MVS.  Sidecars remain image-integrity evidence only.  Optimized SfM
    q/t supplies w2c, the device arbitration plan supplies the single frozen K,
    and all 139 feed rows supply the independently verifiable metric scale.
    """
    metadata_path = args.metadata.resolve()
    sfm_meta_path = args.sfm_meta.resolve()
    sfm_frames_path = args.sfm_frames.resolve()
    arbitration_path = args.arbitration_plan.resolve()
    sparse_path = args.sparse_points.resolve()
    image_root = args.image_root.resolve()
    model_path = args.model.resolve()
    if not image_root.is_dir():
        raise ContractError(f"image root is not a directory: {image_root}")
    if not model_path.is_dir():
        raise ContractError(f"CoreML model is not a package directory: {model_path}")

    metadata = _load_json(metadata_path, "subset metadata")
    sfm_document = _load_json(sfm_meta_path, "optimized SfM metadata")
    feed_rows = _load_jsonl(sfm_frames_path, "SfM feed-frame ledger")
    arbitration = _load_json(arbitration_path, "device arbitration plan")
    frames = metadata.get("frames") if isinstance(metadata, dict) else None
    if not isinstance(frames, list) or len(frames) != EXPECTED_FRAME_COUNT:
        raise ContractError(f"subset metadata must contain exactly {EXPECTED_FRAME_COUNT} frames")
    if metadata.get("work_w") != WORK_W or metadata.get("work_h") != WORK_H:
        raise ContractError(f"metadata work size must be {WORK_W}x{WORK_H}")

    expected_logical = [f"frame_{index:03d}.png" for index in range(EXPECTED_FRAME_COUNT)]
    logical_names = [str(row.get("name")) for row in frames]
    names = [str(row.get("src")) for row in frames]
    if logical_names != expected_logical:
        raise ContractError("metadata frame order is not frame_000..frame_114")
    if len(set(names)) != EXPECTED_FRAME_COUNT or any(Path(name).name != name for name in names):
        raise ContractError("metadata src values must be 115 unique JPEG basenames")
    reconstruction_indices, heldout_indices = frozen_split(EXPECTED_FRAME_COUNT)
    reconstruction_names = [names[index] for index in reconstruction_indices]
    heldout_names = [names[index] for index in heldout_indices]
    frozen_cohort_hashes = require_frozen_cap50_cohort(
        names, reconstruction_names, heldout_names
    )

    disk_jpegs = sorted(path.name for path in image_root.glob("*.jpg"))
    disk_sidecars = sorted(path.name for path in image_root.glob("*.json"))
    expected_sidecars = sorted(Path(name).with_suffix(".json").name for name in names)
    if len(disk_jpegs) != EXPECTED_FRAME_COUNT or set(disk_jpegs) != set(names):
        raise ContractError("image root must contain exactly the selected 115 JPG files")
    if len(disk_sidecars) != EXPECTED_FRAME_COUNT or disk_sidecars != expected_sidecars:
        raise ContractError("image root must contain exactly one matching sidecar per JPG")

    sfm_poses = sfm_document.get("poses") if isinstance(sfm_document, dict) else None
    summary = sfm_document.get("summary", {}) if isinstance(sfm_document, dict) else {}
    if (
        sfm_document.get("schema") != "pw_sfm_sparse_meta_v1"
        or sfm_document.get("refined") is not True
        or not isinstance(sfm_poses, list)
        or len(sfm_poses) != EXPECTED_SFM_FRAME_COUNT
    ):
        raise ContractError("SfM metadata must contain the 139 refined optimized poses")
    if (
        summary.get("result") != "ok"
        or int(summary.get("n_registered", -1)) != EXPECTED_SFM_FRAME_COUNT
        or not np.isclose(float(summary.get("reproj_px", np.nan)), 0.7236, atol=1e-8)
    ):
        raise ContractError(f"optimized SfM summary mismatch: {summary}")
    if len(feed_rows) != EXPECTED_SFM_FRAME_COUNT:
        raise ContractError("SfM feed ledger must contain exactly 139 rows")

    pose_by_id = {int(row.get("frame_id", -1)): row for row in sfm_poses}
    feed_by_id = {int(row.get("frameId", -1)): row for row in feed_rows}
    all_ids = set(range(EXPECTED_SFM_FRAME_COUNT))
    if set(pose_by_id) != all_ids or set(feed_by_id) != all_ids:
        raise ContractError("optimized poses and feed ledger must each cover IDs 0..138")
    feed_by_name = {Path(str(row.get("jpegPath", ""))).name: row for row in feed_rows}
    if len(feed_by_name) != EXPECTED_SFM_FRAME_COUNT or not set(names).issubset(feed_by_name):
        raise ContractError("the selected 115 basenames do not join one-to-one to the SfM ledger")

    sfm_w2c_by_id: dict[int, np.ndarray] = {}
    sfm_centers_all: list[np.ndarray] = []
    arkit_centers_all: list[np.ndarray] = []
    for frame_id in range(EXPECTED_SFM_FRAME_COUNT):
        w2c = sfm_pose_to_w2c(pose_by_id[frame_id])
        _validate_w2c(w2c, f"optimized-sfm-{frame_id}")
        sfm_w2c_by_id[frame_id] = w2c
        sfm_centers_all.append(camera_center(w2c))
        arkit = np.asarray(feed_by_id[frame_id].get("arkitCameraCenterWorld"), dtype=np.float64)
        if arkit.shape != (3,) or not np.isfinite(arkit).all():
            raise ContractError(f"invalid ARKit camera center for feed frame {frame_id}")
        arkit_centers_all.append(arkit)
    sfm_all = np.stack(sfm_centers_all)
    arkit_all = np.stack(arkit_centers_all)
    fitted_scale, sfm_to_arkit_R, sfm_to_arkit_t = _umeyama(sfm_all, arkit_all)
    requested_scale = float(args.metres_per_model_unit)
    if not np.isfinite(requested_scale) or requested_scale <= 0:
        raise ContractError("--metres-per-model-unit must be finite and positive")
    if not np.isclose(requested_scale, fitted_scale, atol=5e-13, rtol=0):
        raise ContractError(
            "scale must equal the frozen 139-center SfM->ARKit Umeyama result: "
            f"requested={requested_scale:.17g}, fitted={fitted_scale:.17g}"
        )
    residual = np.linalg.norm(
        fitted_scale * (sfm_to_arkit_R @ sfm_all.T).T + sfm_to_arkit_t - arkit_all,
        axis=1,
    )

    # Validate the production L1DP evidence: 40 packed stage4 views independently
    # reproduce both the optimized SfM w2c and the one fixed 896x512 K.
    if (
        arbitration.get("w") != PROC_W
        or arbitration.get("h") != PROC_H
        or arbitration.get("n_views") != NVIEW
        or arbitration.get("n_depth") != DEPTH_VALUES
    ):
        raise ContractError("arbitration plan has the wrong CoreML dimensions")
    plan_pose_max_abs = 0.0
    plan_K_max_abs = 0.0
    plan_view_count = 0
    for ref in arbitration.get("refs", []):
        views = ref.get("views", [])
        packed = np.asarray(ref.get("proj", {}).get("stage4"), dtype=np.float64)
        if len(views) != NVIEW or packed.size != NVIEW * 2 * 4 * 4:
            raise ContractError("invalid stage4 block in arbitration plan")
        packed = packed.reshape(NVIEW, 2, 4, 4)
        for slot, view in enumerate(views):
            frame_id = int(view["frame_id"])
            if Path(str(view["jpeg"])).name != Path(str(feed_by_id[frame_id]["jpegPath"])).name:
                raise ContractError(f"arbitration JPEG/frame mismatch for frame {frame_id}")
            plan_pose_max_abs = max(
                plan_pose_max_abs,
                float(np.max(np.abs(packed[slot, 0] - sfm_w2c_by_id[frame_id]))),
            )
            plan_K_max_abs = max(
                plan_K_max_abs,
                float(np.max(np.abs(packed[slot, 1, :3, :3] - FIXED_K_PROC))),
            )
            plan_view_count += 1
    if plan_view_count != 40 or plan_pose_max_abs > 1e-6 or plan_K_max_abs > 1e-6:
        raise ContractError(
            f"production L1DP parity failed: views={plan_view_count}, "
            f"pose_max={plan_pose_max_abs}, K_max={plan_K_max_abs}"
        )

    selected_frame_ids: list[int] = []
    K_rows: list[np.ndarray] = []
    w2c_rows: list[np.ndarray] = []
    center_rows: list[np.ndarray] = []
    for index, (row, name, logical_name) in enumerate(zip(frames, names, logical_names, strict=True)):
        image_path = image_root / name
        sidecar = _load_json(image_path.with_suffix(".json"), f"sidecar for {name}")
        # Ignore EXIF orientation before the raw-raster dimension assertion.
        raw = cv2.imread(str(image_path), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if raw is None or raw.shape[:2] != (2160, 3840):
            shape = None if raw is None else raw.shape
            raise ContractError(f"{name} raw encoded raster must be 3840x2160, got {shape}")
        if sidecar.get("image_w") != 3840 or sidecar.get("image_h") != 2160:
            raise ContractError(f"sidecar image dimensions mismatch for {name}")
        if sidecar.get("trackingStateName") != "normal" or not sidecar.get("is_tracking"):
            raise ContractError(f"non-normal tracking sidecar in frozen cap50: {name}")
        if not np.allclose(
            np.asarray(sidecar.get("extrinsic")), np.asarray(row.get("extrinsic")), atol=0, rtol=0
        ):
            raise ContractError(f"metadata/sidecar identity mismatch for {name}")
        # Sidecar K is not the route K, but verifies the image/metadata join.
        highres_K = np.asarray(sidecar.get("intrinsics_fxfycxcy"), dtype=np.float64)
        expected_highres_K = np.array([row["fx"], row["fy"], row["cx"], row["cy"]]) * 3.75
        if highres_K.shape != (4,) or not np.allclose(highres_K, expected_highres_K, atol=2e-6):
            raise ContractError(f"sidecar/metadata K identity mismatch for {name}")
        if index != int(logical_name[6:9]):
            raise ContractError(f"logical frame index mismatch for {name}")
        frame_id = int(feed_by_name[name]["frameId"])
        selected_frame_ids.append(frame_id)
        w2c = sfm_w2c_by_id[frame_id]
        K_rows.append(FIXED_K_PROC.copy())
        w2c_rows.append(w2c.astype(np.float32))
        center_rows.append(camera_center(w2c).astype(np.float32))
    if len(set(selected_frame_ids)) != EXPECTED_FRAME_COUNT:
        raise ContractError("selected images map to duplicate optimized SfM frame IDs")

    _require_file(sparse_path, "optimized-SfM sparse points")
    with np.load(sparse_path, allow_pickle=False) as sparse:
        if set(sparse.files) != {"xyz", "rgb"}:
            raise ContractError(f"optimized-SfM sparse NPZ keys must be xyz,rgb; got {sparse.files}")
        points = np.asarray(sparse["xyz"], dtype=np.float32)
        colors = np.asarray(sparse["rgb"])
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 100 or not np.isfinite(points).all():
        raise ContractError(f"invalid optimized-SfM sparse xyz: {points.shape}")
    if colors.shape != (len(points), 3):
        raise ContractError(f"optimized-SfM sparse rgb is not aligned: {colors.shape}")

    K_array = np.stack(K_rows).astype(np.float32)
    w2c_array = np.stack(w2c_rows).astype(np.float32)
    center_array = np.stack(center_rows).astype(np.float32)
    visibility = np.zeros((EXPECTED_FRAME_COUNT, len(points)), dtype=bool)
    camera_z = np.zeros((EXPECTED_FRAME_COUNT, len(points)), dtype=np.float32)
    depth_ranges = np.zeros((EXPECTED_FRAME_COUNT, 2), dtype=np.float32)
    visible_counts = np.zeros(EXPECTED_FRAME_COUNT, dtype=np.int32)
    for index in range(EXPECTED_FRAME_COUNT):
        visible, z = visible_sparse_points(
            points,
            K_array[index],
            w2c_array[index],
            image_wh=(PROC_W, PROC_H),
            metres_per_model_unit=requested_scale,
        )
        dmin, dmax, count = input_depth_range(
            points, visible, z, metres_per_model_unit=requested_scale
        )
        visibility[index] = visible
        camera_z[index] = z.astype(np.float32)
        depth_ranges[index] = (dmin, dmax)
        visible_counts[index] = count

    source_indices = np.zeros((EXPECTED_FRAME_COUNT, SOURCE_COUNT), dtype=np.int32)
    source_scores = np.zeros((EXPECTED_FRAME_COUNT, SOURCE_COUNT), dtype=np.float64)
    source_contract: list[dict[str, Any]] = []
    name_to_index = {name: index for index, name in enumerate(names)}
    for ref_index, name in enumerate(names):
        selected_names, selected_rows = select_sources_for_ref(
            ref_index,
            visibility,
            points,
            center_array,
            w2c_array,
            names,
            metres_per_model_unit=requested_scale,
            candidate_indices=reconstruction_indices,
        )
        source_indices[ref_index] = [name_to_index[source] for source in selected_names]
        if any(index not in reconstruction_indices for index in source_indices[ref_index]):
            raise AssertionError("heldout image leaked into CoreML source selection")
        source_scores[ref_index] = [float(row["selection_score"]) for row in selected_rows]
        source_contract.append(
            {
                "reference": name,
                "reference_index": ref_index,
                "reference_role": "heldout_observation" if ref_index in heldout_indices else "reconstruction",
                "sources": selected_names,
                "source_indices": source_indices[ref_index].tolist(),
                "source_policy": "reconstruction-only",
                "details": selected_rows,
            }
        )

    try:
        frame20_index = selected_frame_ids.index(20)
        production_frame20 = next(
            row for row in arbitration.get("refs", []) if int(row.get("frame_id", -1)) == 20
        )
    except (ValueError, StopIteration) as exc:
        raise ContractError("feed frame 20 is missing from cap50 or production arbitration") from exc
    production_view_ids = [int(row["frame_id"]) for row in production_frame20["views"]]
    common_view_indices = [frame20_index, *source_indices[frame20_index].tolist()]
    common_view_ids = [selected_frame_ids[index] for index in common_view_indices]
    common_projection = build_projection_pyramid(K_array[common_view_indices], w2c_array[common_view_indices])
    stage_pairs = (("stage1", "p1"), ("stage2", "p2"), ("stage3", "p3"), ("stage4", "p4"))
    projection_comparison: dict[str, Any] = {}
    for stage_name, common_name in stage_pairs:
        production_packed = np.asarray(production_frame20["proj"][stage_name], dtype=np.float32).reshape(
            NVIEW, 2, 4, 4
        )
        common_packed = np.asarray(common_projection[common_name][0], dtype=np.float32)
        projection_comparison[stage_name] = {
            "production_sha256": _array_sha256(production_packed),
            "common_sha256": _array_sha256(common_packed),
            "all_slots_max_abs": float(np.max(np.abs(production_packed - common_packed))),
            "reference_slot_max_abs": float(
                np.max(np.abs(production_packed[0] - common_packed[0]))
            ),
            "intrinsics_all_slots_max_abs": float(
                np.max(np.abs(production_packed[:, 1] - common_packed[:, 1]))
            ),
        }
    production_dv = np.asarray(production_frame20["dv"], dtype=np.float32)
    common_dv = depth_values(tuple(float(x) for x in depth_ranges[frame20_index]))[0]
    production_frame20_input_comparison = {
        "reference_feed_frame_id": 20,
        "reference_universe_index": frame20_index,
        "reference": names[frame20_index],
        "production_view_frame_ids": production_view_ids,
        "common_view_frame_ids": common_view_ids,
        "view_order_identical": production_view_ids == common_view_ids,
        "source_overlap_count": len(set(production_view_ids[1:]) & set(common_view_ids[1:])),
        "production_depth_range_model_units": [
            float(production_frame20["dmin"]),
            float(production_frame20["dmax"]),
        ],
        "common_depth_range_model_units": depth_ranges[frame20_index].astype(float).tolist(),
        "production_dv_sha256": _array_sha256(production_dv),
        "common_dv_sha256": _array_sha256(common_dv),
        "dv_max_abs": float(np.max(np.abs(production_dv - common_dv))),
        "fixed_K_max_abs": float(np.max(np.abs(K_array[frame20_index] - FIXED_K_PROC))),
        "projection": projection_comparison,
        "interpretation": (
            "numerical identity evidence; all-slot projection equality is expected only when the "
            "frozen common source order equals the production source order"
        ),
    }

    images_by_name, sidecars_by_name = _image_identity(names, image_root)
    model_sha, model_files = sha256_tree(model_path)
    view_lines = "".join(
        f"{row['reference']}\t{','.join(row['sources'])}\n" for row in source_contract
    ).encode("utf-8")
    range_lines = "".join(
        f"{name}\t{float(depth_ranges[i, 0]):.17g}\t{float(depth_ranges[i, 1]):.17g}\t{int(visible_counts[i])}\n"
        for i, name in enumerate(names)
    ).encode("utf-8")
    return {
        "names": names,
        "logical_names": logical_names,
        "selected_frame_ids": selected_frame_ids,
        "K": K_array,
        "w2c": w2c_array,
        "centers": center_array,
        "points": points,
        "visibility": visibility,
        "depth_ranges": depth_ranges,
        "visible_counts": visible_counts,
        "source_indices": source_indices,
        "source_scores": source_scores,
        "source_contract": source_contract,
        "reconstruction_indices": reconstruction_indices,
        "heldout_indices": heldout_indices,
        "reconstruction_names": reconstruction_names,
        "heldout_names": heldout_names,
        "metres_per_model_unit": requested_scale,
        "sfm_to_arkit_R": sfm_to_arkit_R,
        "sfm_to_arkit_t": sfm_to_arkit_t,
        "images_by_name": images_by_name,
        "sidecars_by_name": sidecars_by_name,
        "identity": {
            "metadata": {"path": str(metadata_path), "sha256": sha256_file(metadata_path)},
            "sfm_meta": {"path": str(sfm_meta_path), "sha256": sha256_file(sfm_meta_path)},
            "sfm_frames": {"path": str(sfm_frames_path), "sha256": sha256_file(sfm_frames_path)},
            "arbitration_plan": {"path": str(arbitration_path), "sha256": sha256_file(arbitration_path)},
            "sparse_points": {
                "path": str(sparse_path),
                "sha256": sha256_file(sparse_path),
                "coordinate_frame": "optimized_sfm_cv",
                "values_pre_scaled_to_metres": False,
                "warning": "legacy filename sfm_sparse_metric.npz is misleading",
            },
            "image_root": {
                "path": str(image_root),
                "manifest_sha256": image_root_manifest_sha256(names, images_by_name),
                "sidecar_manifest_sha256": _sidecar_manifest_sha256(names, sidecars_by_name),
            },
            "coreml_model": {"path": str(model_path), "tree_sha256": model_sha, "files": model_files},
        },
        "validation": {
            "frame_count": EXPECTED_FRAME_COUNT,
            "reconstruction_count": len(reconstruction_indices),
            "heldout_count": len(heldout_indices),
            "optimized_sfm_pose_count": EXPECTED_SFM_FRAME_COUNT,
            "optimized_sfm_reprojection_px": float(summary["reproj_px"]),
            "jpeg_count": len(names),
            "sidecar_count": len(sidecars_by_name),
            "jpeg_raw_dimensions_ignore_exif": [3840, 2160],
            "inference_dimensions": [PROC_W, PROC_H],
            "pose_join": "subset src -> sfm_fed_frames basename/frameId -> optimized SfM q_wxyz+t",
            "fixed_K_896x512": FIXED_K_PROC.tolist(),
            "arbitration_stage4_view_checks": plan_view_count,
            "arbitration_pose_max_abs": plan_pose_max_abs,
            "arbitration_K_max_abs": plan_K_max_abs,
            "production_l1dp_frame20_input_comparison": production_frame20_input_comparison,
            "sparse_point_count": int(len(points)),
            "sparse_coordinate_frame": "optimized_sfm_cv",
            "sparse_values_pre_scaled_to_metres": False,
            "scale_fit": {
                "method": "Umeyama optimized-SfM centers -> ARKit centers, all 139 feed frames",
                "metres_per_model_unit": requested_scale,
                "input_count": EXPECTED_SFM_FRAME_COUNT,
                "median_residual_m": float(np.median(residual)),
                "rmse_m": float(np.sqrt(np.mean(residual**2))),
                "p95_residual_m": float(np.percentile(residual, 95)),
                "max_residual_m": float(np.max(residual)),
                "rotation": sfm_to_arkit_R.tolist(),
                "translation_m": sfm_to_arkit_t.tolist(),
            },
        },
        "hashes": {
            "frame_order_sha256": frozen_cohort_hashes["frame_order_sha256"],
            "logical_frame_order_sha256": ordered_names_sha256(logical_names),
            "reconstruction_order_sha256": frozen_cohort_hashes[
                "reconstruction_order_sha256"
            ],
            "heldout_order_sha256": frozen_cohort_hashes["heldout_order_sha256"],
            "view_selection_sha256": hashlib.sha256(view_lines).hexdigest(),
            "depth_ranges_sha256": hashlib.sha256(range_lines).hexdigest(),
            "K_sha256": _array_sha256(K_array),
            "w2c_sha256": _array_sha256(w2c_array),
            "centers_sha256": _array_sha256(center_array),
            "source_indices_sha256": _array_sha256(source_indices),
        },
    }


def _model_cache_arrays(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "names": np.asarray(data["names"]),
        "logical_names": np.asarray(data["logical_names"]),
        "frame_order": np.asarray(data["names"]),
        "frame_order_sha256": np.asarray(data["hashes"]["frame_order_sha256"]),
        "sfm_frame_ids": np.asarray(data["selected_frame_ids"], dtype=np.int32),
        "K": np.asarray(data["K"], dtype=np.float32),
        "w2c": np.asarray(data["w2c"], dtype=np.float32),
        "centers": np.asarray(data["centers"], dtype=np.float32),
        "metres_per_model_unit": np.asarray(data["metres_per_model_unit"], dtype=np.float64),
        "sfm_to_arkit_R": np.asarray(data["sfm_to_arkit_R"], dtype=np.float64),
        "sfm_to_arkit_t": np.asarray(data["sfm_to_arkit_t"], dtype=np.float64),
        "source_indices": np.asarray(data["source_indices"], dtype=np.int32),
        "source_scores": np.asarray(data["source_scores"], dtype=np.float64),
        "depth_ranges": np.asarray(data["depth_ranges"], dtype=np.float32),
        "visible_sparse_counts": np.asarray(data["visible_counts"], dtype=np.int32),
        "reconstruction_indices": np.asarray(data["reconstruction_indices"], dtype=np.int32),
        "heldout_indices": np.asarray(data["heldout_indices"], dtype=np.int32),
        "sig": np.asarray("B0_CAP50_MODEL_CAMERA_CACHE_115_896x512_V1"),
    }


def _coreml_compute_unit(ct: Any, requested: str) -> Any:
    if requested == "cpu_and_gpu":
        return ct.ComputeUnit.CPU_AND_GPU
    if requested == "cpu_only":
        return ct.ComputeUnit.CPU_ONLY
    raise ContractError(f"unsupported compute unit (ANE is forbidden): {requested}")


def _multiarray_shape(feature: Any) -> list[int]:
    return [int(value) for value in feature.type.multiArrayType.shape]


def load_coreml_model(model_path: Path, requested_compute_unit: str) -> tuple[Any, dict[str, Any]]:
    try:
        import coremltools as ct
    except ImportError as exc:
        raise ContractError("coremltools is required for non-dry cache generation") from exc
    resolved_model_path = model_path.resolve()
    model_tree_sha256, _ = sha256_tree(resolved_model_path)
    if len(resolved_model_path.parents) < 3:
        raise ContractError(f"cannot resolve frozen output evidence beside model: {resolved_model_path}")
    evidence_path = (
        resolved_model_path.parents[2] / FROZEN_COREML_OUTPUT_EVIDENCE_RELATIVE_PATH
    )
    _require_file(evidence_path, "frozen CoreML output-semantic evidence")
    evidence_sha256 = sha256_file(evidence_path)
    try:
        evidence_lines = evidence_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read CoreML output-semantic evidence: {evidence_path}") from exc
    matching_lines = [
        index + 1
        for index, line in enumerate(evidence_lines)
        if line == FROZEN_COREML_OUTPUT_EVIDENCE_LINE
    ]
    if len(matching_lines) != 1:
        raise ContractError(
            "frozen CoreML output-semantic evidence must contain its exact mapping line once; "
            f"found at {matching_lines}"
        )

    compute_unit = _coreml_compute_unit(ct, requested_compute_unit)
    model = ct.models.MLModel(str(resolved_model_path), compute_units=compute_unit)
    spec = model.get_spec()
    inputs = {feature.name: _multiarray_shape(feature) for feature in spec.description.input}
    expected_inputs = {
        **{f"i{index}": [1, 3, PROC_H, PROC_W] for index in range(NVIEW)},
        **{f"p{index}": [1, NVIEW, 2, 4, 4] for index in range(1, 5)},
        "dv": [1, DEPTH_VALUES],
    }
    if inputs != expected_inputs:
        raise ContractError(f"CoreML input signature mismatch: actual={inputs}, expected={expected_inputs}")
    output_order = [feature.name for feature in spec.description.output]
    outputs = {feature.name: _multiarray_shape(feature) for feature in spec.description.output}
    if len(outputs) != 2 or any(shape != [1, PROC_H, PROC_W] for shape in outputs.values()):
        raise ContractError(f"CoreML output signature mismatch: {outputs}")
    output_contract = resolve_frozen_coreml_output_contract(
        model_tree_sha256=model_tree_sha256,
        spec_output_order=output_order,
        semantic_evidence_sha256=evidence_sha256,
    )
    output_contract["semantic_evidence"] = {
        "path": str(evidence_path),
        "sha256": evidence_sha256,
        "size_bytes": evidence_path.stat().st_size,
        "mapping_line_number": matching_lines[0],
        "mapping_line": FROZEN_COREML_OUTPUT_EVIDENCE_LINE,
    }
    output_contract["spec_output_descriptions"] = {
        feature.name: feature.shortDescription for feature in spec.description.output
    }
    metadata = {
        "coremltools": str(ct.__version__),
        "compute_units": requested_compute_unit,
        "ane_allowed": False,
        "inputs": inputs,
        "outputs": outputs,
        "frozen_output_contract": output_contract,
        "macos": platform.mac_ver()[0],
    }
    return model, metadata


class ImageCache:
    def __init__(self, image_root: Path, max_items: int = 20) -> None:
        self.image_root = image_root
        self.max_items = max_items
        self.values: OrderedDict[str, np.ndarray] = OrderedDict()

    def get(self, name: str) -> np.ndarray:
        value = self.values.pop(name, None)
        if value is None:
            value = decode_rgb(self.image_root / name).transpose(2, 0, 1)[None]
        self.values[name] = value
        while len(self.values) > self.max_items:
            self.values.popitem(last=False)
        return value


def build_coreml_feed(data: Mapping[str, Any], ref_index: int, images: ImageCache) -> dict[str, np.ndarray]:
    indices = [ref_index, *np.asarray(data["source_indices"])[ref_index].tolist()]
    if len(indices) != NVIEW or len(set(indices)) != NVIEW:
        raise ContractError(f"invalid frozen five-view selection for {data['names'][ref_index]}")
    feed = {f"i{slot}": images.get(data["names"][index]) for slot, index in enumerate(indices)}
    projection = build_projection_pyramid(np.asarray(data["K"])[indices], np.asarray(data["w2c"])[indices])
    feed.update(projection)
    feed["dv"] = depth_values(tuple(float(value) for value in data["depth_ranges"][ref_index]))
    return {name: np.asarray(value, dtype=np.float32) for name, value in feed.items()}


def _output_statistics(value: np.ndarray) -> dict[str, Any]:
    array = np.asarray(value, dtype=np.float32)
    return {
        "shape": list(array.shape),
        "dtype": array.dtype.str,
        "finite_fraction": float(np.mean(np.isfinite(array))),
        "min": float(np.nanmin(array)),
        "median": float(np.nanmedian(array)),
        "max": float(np.nanmax(array)),
    }


def load_l1dp_v1(
    path: Path,
    *,
    expected_frame_id: int,
    expected_hw: tuple[int, int] = (PROC_H, PROC_W),
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Parse the production device L1DP v1 depth/confidence artifact fail-closed."""
    source = path.resolve()
    _require_file(source, "production L1DP depth")
    raw = source.read_bytes()
    header_size = struct.calcsize("<4sIIII")
    if len(raw) < header_size:
        raise ContractError(f"L1DP byte size is shorter than its v1 header: {len(raw)}")
    magic, version, frame_id, height, width = struct.unpack("<4sIIII", raw[:header_size])
    if magic != b"L1DP":
        raise ContractError(f"L1DP magic mismatch: {magic!r}")
    if version != 1:
        raise ContractError(f"L1DP version mismatch: {version}")
    if frame_id != expected_frame_id:
        raise ContractError(
            f"L1DP frame ID mismatch: expected {expected_frame_id}, got {frame_id}"
        )
    if (height, width) != expected_hw:
        raise ContractError(
            f"L1DP dimensions mismatch: expected {expected_hw}, got {(height, width)}"
        )
    count = height * width
    expected_bytes = header_size + 2 * count * np.dtype("<f4").itemsize
    if len(raw) != expected_bytes:
        raise ContractError(f"L1DP byte size mismatch: expected {expected_bytes}, got {len(raw)}")
    depth = np.frombuffer(raw, dtype="<f4", count=count, offset=header_size).copy().reshape(height, width)
    confidence = np.frombuffer(
        raw, dtype="<f4", count=count, offset=header_size + count * 4
    ).copy().reshape(height, width)
    if not np.isfinite(depth).all() or np.any(depth <= 0):
        raise ContractError("production L1DP depth must be finite and positive")
    if (
        not np.isfinite(confidence).all()
        or float(np.min(confidence)) < -1e-4
        or float(np.max(confidence)) > 1.0001
    ):
        raise ContractError("production L1DP confidence must be finite and in [0,1]")
    identity = {
        "path": str(source),
        "sha256": sha256_file(source),
        "size_bytes": len(raw),
        "magic": magic.decode("ascii"),
        "version": version,
        "frame_id": frame_id,
        "height": height,
        "width": width,
        "depth": _output_statistics(depth),
        "confidence": _output_statistics(confidence),
    }
    return depth, confidence, identity


def _four_stats(values: np.ndarray) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        raise ContractError("comparison statistic input must be a non-empty finite vector")
    return {
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "max": float(np.max(array)),
    }


def compare_raw_to_production_l1dp(
    raw_depth: np.ndarray,
    raw_confidence: np.ndarray,
    production_depth: np.ndarray,
    production_confidence: np.ndarray,
) -> dict[str, Any]:
    """Report numerical parity evidence without imposing an equality gate."""
    depth = np.asarray(raw_depth, dtype=np.float64)
    confidence = np.asarray(raw_confidence, dtype=np.float64)
    device_depth = np.asarray(production_depth, dtype=np.float64)
    device_confidence = np.asarray(production_confidence, dtype=np.float64)
    if not (depth.shape == confidence.shape == device_depth.shape == device_confidence.shape):
        raise ContractError("raw and production L1DP arrays must have the same shape")
    overlap = (
        np.isfinite(depth)
        & np.isfinite(confidence)
        & np.isfinite(device_depth)
        & np.isfinite(device_confidence)
        & (depth > 0)
        & (device_depth > 0)
    )
    count = int(np.count_nonzero(overlap))
    if count == 0:
        raise ContractError("raw/production L1DP comparison has no finite positive overlap")
    delta = depth[overlap] - device_depth[overlap]
    absolute = np.abs(delta)
    absrel = absolute / device_depth[overlap]
    confidence_abs = np.abs(confidence[overlap] - device_confidence[overlap])
    return {
        "gate": "evidence_only_no_equality_threshold",
        "shape": list(depth.shape),
        "finite_positive_overlap_count": count,
        "finite_positive_overlap_fraction": float(count / depth.size),
        "depth_absrel": _four_stats(absrel),
        "depth_abs_delta_model_units": _four_stats(absolute),
        "depth_signed_delta_model_units": {
            "mean": float(np.mean(delta)),
            "median": float(np.median(delta)),
        },
        "depth_rmse_model_units": float(np.sqrt(np.mean(delta * delta))),
        "confidence_abs_delta": _four_stats(confidence_abs),
    }


def require_bit_identical_repeat(
    depth: np.ndarray,
    confidence: np.ndarray,
    repeat_depth: np.ndarray,
    repeat_confidence: np.ndarray,
) -> dict[str, Any]:
    depth_equal = bool(np.array_equal(depth, repeat_depth))
    confidence_equal = bool(np.array_equal(confidence, repeat_confidence))
    evidence = {
        "depth_bit_identical": depth_equal,
        "confidence_bit_identical": confidence_equal,
        "depth_max_abs": float(
            np.max(np.abs(np.asarray(depth, dtype=np.float64) - np.asarray(repeat_depth, dtype=np.float64)))
        ),
        "confidence_max_abs": float(
            np.max(
                np.abs(
                    np.asarray(confidence, dtype=np.float64)
                    - np.asarray(repeat_confidence, dtype=np.float64)
                )
            )
        ),
    }
    if not depth_equal or not confidence_equal:
        raise ContractError(f"same-feed CoreML repeat is not bit-identical: {evidence}")
    return evidence


def predict_raw_depths(
    data: Mapping[str, Any],
    args: argparse.Namespace,
    out: Path,
    prediction_indices: Sequence[int],
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    model, coreml_metadata = load_coreml_model(args.model.resolve(), args.compute_units)
    output_contract = coreml_metadata["frozen_output_contract"]
    write_json_exclusive(out / "coreml_output_contract.json", output_contract)
    images = ImageCache(args.image_root.resolve())
    depth_rows: list[np.ndarray] = []
    confidence_rows: list[np.ndarray] = []
    raw_rows: list[dict[str, Any]] = []
    first_identification: dict[str, Any] | None = None
    raw_dir = out / "raw_frames"
    raw_dir.mkdir()
    selected_count = len(prediction_indices)
    for local_index, ref_index in enumerate(prediction_indices):
        frame_start = time.monotonic()
        feed = build_coreml_feed(data, ref_index, images)
        result = model.predict(feed)
        depth, confidence, output_validation = extract_frozen_coreml_outputs(
            result, output_contract
        )

        # Persist the validated primary prediction before the repeat gate.  If
        # the backend is nondeterministic, failure.json and this immutable NPZ
        # together retain the exact evidence instead of losing the first result.
        frame_name = str(data["names"][ref_index])
        frame_path = raw_dir / f"{local_index:03d}_ref{ref_index:03d}.npz"
        write_npz_exclusive(
            frame_path,
            frame=np.asarray(frame_name),
            depth=depth,
            conf=confidence,
            depth_range=np.asarray(data["depth_ranges"][ref_index], dtype=np.float32),
            source_indices=np.asarray(data["source_indices"][ref_index], dtype=np.int32),
        )

        if local_index == 0:
            repeated = model.predict(feed)
            repeat_depth, repeat_conf, _ = extract_frozen_coreml_outputs(
                repeated, output_contract
            )
            try:
                repeat_evidence = require_bit_identical_repeat(
                    depth, confidence, repeat_depth, repeat_conf
                )
            except ContractError:
                write_npz_exclusive(
                    raw_dir / f"{local_index:03d}_ref{ref_index:03d}.repeat_failure.npz",
                    first_depth=depth,
                    first_conf=confidence,
                    repeat_depth=repeat_depth,
                    repeat_conf=repeat_conf,
                )
                raise
            first_identification = {
                "method": output_contract["method"],
                "mapping_was_value_inferred": False,
                "depth_key": output_contract["depth_key"],
                "confidence_key": output_contract["confidence_key"],
                "model_tree_sha256": output_contract["model_tree_sha256"],
                "semantic_evidence": output_contract["semantic_evidence"],
                "depth": _output_statistics(depth),
                "confidence": _output_statistics(confidence),
                "same_feed_repeat": repeat_evidence,
            }

        row = {
            "cache_index": local_index,
            "universe_index": ref_index,
            "sfm_frame_id": int(data["selected_frame_ids"][ref_index]),
            "frame": frame_name,
            "raw_frame_path": str(frame_path),
            "raw_frame_sha256": sha256_file(frame_path),
            "predict_seconds": time.monotonic() - frame_start,
            "depth": _output_statistics(depth),
            "confidence": _output_statistics(confidence),
            "output_validation": output_validation,
        }
        write_json_exclusive(raw_dir / f"{local_index:03d}_ref{ref_index:03d}.json", row)
        raw_rows.append(row)
        depth_rows.append(depth)
        confidence_rows.append(confidence)
        print(
            f"[CoreML {local_index + 1}/{selected_count}] {frame_name} "
            f"depth_med={np.median(depth):.3f} conf_med={np.median(confidence):.3f} "
            f"{row['predict_seconds']:.2f}s",
            flush=True,
        )
    if first_identification is None:
        raise ContractError("no CoreML frames were predicted")
    coreml_metadata["resolved_outputs"] = first_identification
    return (
        np.stack(depth_rows).astype(np.float32),
        np.stack(confidence_rows).astype(np.float32),
        raw_rows,
        coreml_metadata,
    )


def _environment_identity() -> dict[str, Any]:
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "macos": platform.mac_ver()[0],
        "machine": platform.machine(),
        "numpy": np.__version__,
        "opencv": cv2.__version__,
        "thread_environment": {
            key: os.environ.get(key)
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS")
        },
    }


def _contract_document(data: Mapping[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": "b0-cap50-common-cache-preflight-v1",
        "status": "component_preflight_only",
        "publishable_input_contract": False,
        "final_input_contract": "input_contract.json is emitted only after a successful full 115-frame run",
        "dataset_id": args.dataset_id,
        "created_utc": utc_now(),
        "run_mode": run_mode(args.limit, len(data["names"])),
        "publishable_as_full": args.limit is None,
        "frame_count": len(data["names"]),
        "frame_order": data["names"],
        "logical_frame_order": data["logical_names"],
        "identity": data["identity"],
        "validation": data["validation"],
        "hashes": data["hashes"],
        "camera_contract": {
            "coordinate_frame": "optimized_sfm_cv",
            "pose": "optimized SfM OpenCV world-to-camera q_wxyz+t",
            "depth": "camera-Z optimized-SfM model units",
            "metres_per_model_unit": data["metres_per_model_unit"],
            "intrinsics": FIXED_K_PROC.tolist(),
            "intrinsics_resolution": [PROC_W, PROC_H],
            "resize": "cv2.IMREAD_IGNORE_ORIENTATION raw 3840x2160; cv2.INTER_AREA RGB float32 [0,1]",
        },
        "coreml_contract": {
            "views": NVIEW,
            "source_views": SOURCE_COUNT,
            "source_selection": (
                "reconstruction93-only; >=5 shared visible input sparse points; baseline 0.06m..1.50m; "
                "camera forward-axis angle <=45deg; ascending abs(log(baseline_m/0.25))+angle_deg/45; "
                "stable tie by canonical source index"
            ),
            "minimum_source_baseline_m": MIN_SOURCE_BASELINE_M,
            "maximum_source_baseline_m": MAX_SOURCE_BASELINE_M,
            "maximum_source_forward_angle_deg": MAX_SOURCE_FORWARD_ANGLE_DEG,
            "target_source_baseline_m": TARGET_SOURCE_BASELINE_M,
            "heldout_as_source": False,
            "depth_range": (
                "visible input sparse camera-Z p2*0.70 .. p99.5*1.50; "
                "values in optimized-SfM model units"
            ),
            "compute_units": args.compute_units,
            "ane_allowed": False,
        },
        "mask_contract": {
            "GEO_MASK": GEO_MASK,
            "PHOTO": PHOTO,
            "BOUND_REL": BOUND_REL,
            "NORMAL_COS": NORMAL_COS,
            "GEO_PIX": GEO_PIX,
            "GEO_DEP": GEO_DEP,
            "fusion_neighbors": FUSION_NEIGHBORS,
            "minimum_fusion_baseline_m": MIN_FUSION_BASELINE_M,
            "neighbor_policy": "reconstruction93-only for every ref, including heldout observation refs",
            "photo_color": None,
            "free_space": None,
            "reprojection_residual_gate": None,
            "erosion": None,
            "output": "camera-Z d_avg where final mask is true; zero otherwise",
        },
        "view_selection": data["source_contract"],
        "depth_ranges": [
            {
                "frame": name,
                "min_model_units": float(data["depth_ranges"][index, 0]),
                "max_model_units": float(data["depth_ranges"][index, 1]),
                "visible_sparse_points": int(data["visible_counts"][index]),
            }
            for index, name in enumerate(data["names"])
        ],
    }


def _base_provenance(
    data: Mapping[str, Any], args: argparse.Namespace, selected_names: Sequence[str]
) -> dict[str, Any]:
    # Parent B0 contract fields use the selected cache order. Image identity remains
    # the exact full 115-frame universe even for a one-frame smoke.
    selected_images = {name: data["images_by_name"][name] for name in selected_names}
    result = common_provenance_skeleton(
        dataset_id=args.dataset_id,
        names=selected_names,
        reconstruction_names=data["reconstruction_names"],
        heldout_names=data["heldout_names"],
        metres_per_model_unit=data["metres_per_model_unit"],
        images_by_name=selected_images,
    )
    result["images"]["full_universe_root_manifest_sha256"] = data["identity"]["image_root"]["manifest_sha256"]
    result["images"]["full_universe_by_name"] = data["images_by_name"]
    result["images"]["full_universe_frame_order"] = data["names"]
    result["images"]["full_universe_frame_order_sha256"] = data["hashes"]["frame_order_sha256"]
    result.update(
        {
            "generator": {
                "script": str(Path(__file__).resolve()),
                "script_sha256": sha256_file(Path(__file__).resolve()),
                "started_utc": utc_now(),
                "environment": _environment_identity(),
            },
            "run_mode": run_mode(args.limit, len(data["names"])),
            "publishable_as_full": args.limit is None,
            "requested_limit": args.limit,
            "input_identity": data["identity"],
            "validation": data["validation"],
            "frozen_hashes": data["hashes"],
            "view_selection": data["source_contract"],
            "depth_ranges": [
                {
                    "frame": name,
                    "min_model_units": float(data["depth_ranges"][index, 0]),
                    "max_model_units": float(data["depth_ranges"][index, 1]),
                    "visible_sparse_points": int(data["visible_counts"][index]),
                }
                for index, name in enumerate(data["names"])
            ],
            "mask": {
                "GEO_MASK": GEO_MASK,
                "PHOTO": PHOTO,
                "BOUND_REL": BOUND_REL,
                "NORMAL_COS": NORMAL_COS,
                "GEO_PIX": GEO_PIX,
                "GEO_DEP": GEO_DEP,
                "fusion_neighbors": FUSION_NEIGHBORS,
                "neighbor_policy": "reconstruction93-only",
                "photo_color": False,
                "free_space": False,
                "reprojection_residual_gate": False,
                "erosion": False,
            },
        }
    )
    result["model_cache"]["frame_order_sha256"] = data["hashes"]["frame_order_sha256"]
    result["model_cache"]["frame_order"] = data["names"]
    split = result["splits"][SPLIT_ID]
    if "split_files" in data:
        split["reconstruction"]["path"] = data["split_files"]["reconstruction"]["path"]
        split["reconstruction"]["file_sha256"] = data["split_files"]["reconstruction"]["sha256"]
        split["heldout"]["path"] = data["split_files"]["heldout"]["path"]
        split["heldout"]["file_sha256"] = data["split_files"]["heldout"]["sha256"]
    return result


def _prediction_indices(data: Mapping[str, Any], limit: int | None) -> list[int]:
    total = len(data["names"])
    if limit is None:
        return list(range(total))
    if not 1 <= limit <= total:
        raise ContractError(f"--limit must be in [1,{total}], got {limit}")
    # Production L1DP evidence includes feed frame 20, so smoke begins there and
    # can compare the exact w2c/K/feed identity against arbitration_plan.json.
    try:
        priority = list(data["selected_frame_ids"]).index(20)
    except ValueError as exc:
        raise ContractError("selected cap50 universe does not contain SfM feed frame 20") from exc
    order = [priority, *(index for index in range(total) if index != priority)]
    return order[:limit]


def execute(args: argparse.Namespace, out: Path) -> None:
    started = time.monotonic()
    data = load_and_validate_inputs(args)
    reconstruction_path = out / "reconstruction_frames.txt"
    heldout_path = out / "heldout_frames.txt"
    write_names_exclusive(reconstruction_path, data["reconstruction_names"])
    write_names_exclusive(heldout_path, data["heldout_names"])
    data["split_files"] = {
        "reconstruction": {"path": str(reconstruction_path), "sha256": sha256_file(reconstruction_path)},
        "heldout": {"path": str(heldout_path), "sha256": sha256_file(heldout_path)},
    }
    contract = _contract_document(data, args)
    write_json_exclusive(out / "contract.json", contract)

    model_cache_path = out / "model_cache.npz"
    write_npz_exclusive(model_cache_path, **_model_cache_arrays(data))
    model_cache_sha = sha256_file(model_cache_path)

    if args.dry_contract:
        provenance = _base_provenance(data, args, data["names"])
        provenance["status"] = "dry_contract_complete"
        provenance["dry_contract"] = True
        provenance["publishable_as_full"] = False
        provenance["model_cache"].update(
            {
                "sha256": model_cache_sha,
                "path": str(model_cache_path),
                "frame_order_sha256": data["hashes"]["frame_order_sha256"],
            }
        )
        provenance["dmcache"]["signature"] = None
        provenance["generator"]["completed_utc"] = utc_now()
        provenance["generator"]["wall_seconds"] = time.monotonic() - started
        write_json_exclusive(out / "provenance.json", provenance)
        print(f"DRY CONTRACT OK: {out}", flush=True)
        return

    total = len(data["names"])
    prediction_indices = _prediction_indices(data, args.limit)
    production_l1dp: tuple[np.ndarray, np.ndarray, dict[str, Any]] | None = None
    if args.limit is not None:
        if args.production_l1_depth is None:
            raise ContractError("smoke --limit requires --production-l1-depth for feed20 comparison")
        production_l1dp = load_l1dp_v1(
            args.production_l1_depth,
            expected_frame_id=20,
            expected_hw=(PROC_H, PROC_W),
        )
    elif args.production_l1_depth is not None:
        raise ContractError("--production-l1-depth is a smoke-only --limit evidence input")
    selected_count = len(prediction_indices)
    selected_names = [data["names"][index] for index in prediction_indices]
    raw_depth, raw_conf, raw_rows, coreml_metadata = predict_raw_depths(
        data, args, out, prediction_indices
    )
    selected_source_indices = np.asarray(data["source_indices"])[prediction_indices].astype(np.int32)
    selected_ranges = np.asarray(data["depth_ranges"])[prediction_indices].astype(np.float32)
    raw_cache_path = out / "raw_depth_conf.npz"
    write_npz_exclusive(
        raw_cache_path,
        frames=np.asarray(selected_names),
        depth=raw_depth,
        conf=raw_conf,
        depth_ranges=selected_ranges,
        source_indices=selected_source_indices,
        universe_indices=np.asarray(prediction_indices, dtype=np.int32),
        sig=np.asarray(cache_signature(args.limit, total) + ".RAW"),
    )

    if args.limit is not None:
        if production_l1dp is None or int(data["selected_frame_ids"][prediction_indices[0]]) != 20:
            raise AssertionError("smoke production comparison must use feed frame 20 first")
        device_depth, device_confidence, device_identity = production_l1dp
        numerical_comparison = compare_raw_to_production_l1dp(
            raw_depth[0], raw_conf[0], device_depth, device_confidence
        )
        provenance = _base_provenance(data, args, selected_names)
        provenance["status"] = "raw_smoke_only"
        provenance["dry_contract"] = False
        provenance["coreml"] = coreml_metadata
        provenance["production_l1dp_comparison"] = {
            "device_artifact": device_identity,
            "raw_coreml_vs_device": numerical_comparison,
            "input_range_K_projection_identity": data["validation"][
                "production_l1dp_frame20_input_comparison"
            ],
        }
        provenance["raw_cache"] = {
            "path": str(raw_cache_path),
            "sha256": sha256_file(raw_cache_path),
            "depth_shape": list(raw_depth.shape),
            "depth_dtype": raw_depth.dtype.str,
            "confidence_shape": list(raw_conf.shape),
            "confidence_dtype": raw_conf.dtype.str,
            "per_frame": raw_rows,
        }
        provenance["model_cache"].update(
            {
                "path": str(model_cache_path),
                "sha256": model_cache_sha,
                "frame_order_sha256": data["hashes"]["frame_order_sha256"],
            }
        )
        provenance["dmcache"] = {
            "status": "not_evaluated_insufficient_predicted_neighbors",
            "generated": False,
            "sha256": None,
            "signature": None,
            "reason": (
                "--limit is raw CoreML smoke only; the certified geometric mask is evaluated only "
                "after all 115 observations are predicted"
            ),
        }
        provenance["mask"]["status"] = "not_evaluated_insufficient_predicted_neighbors"
        provenance["generator"]["completed_utc"] = utc_now()
        provenance["generator"]["wall_seconds"] = time.monotonic() - started
        write_json_exclusive(out / "provenance.json", provenance)
        print(
            f"RAW SMOKE OK feed=20 frames={selected_count} "
            f"mean_absrel={numerical_comparison['depth_absrel']['mean']:.6f} -> {out}",
            flush=True,
        )
        return

    global_to_local = {global_index: local_index for local_index, global_index in enumerate(prediction_indices)}
    eligible_local_neighbors = [
        global_to_local[index]
        for index in data["reconstruction_indices"]
        if index in global_to_local
    ]
    masked, mask_stats = mask_all_depths(
        selected_names,
        raw_depth,
        raw_conf,
        np.asarray(data["K"])[prediction_indices],
        np.asarray(data["w2c"])[prediction_indices],
        np.asarray(data["centers"])[prediction_indices],
        selected_ranges,
        eligible_neighbor_indices=eligible_local_neighbors,
        metres_per_model_unit=data["metres_per_model_unit"],
    )
    dmcache_path = out / "dmcache.npz"
    signature = cache_signature(args.limit, total)
    write_npz_exclusive(
        dmcache_path,
        frames=np.asarray(selected_names),
        dm=masked.astype(np.float32),
        universe_indices=np.asarray(prediction_indices, dtype=np.int32),
        reconstruction_indices=np.asarray(data["reconstruction_indices"], dtype=np.int32),
        heldout_indices=np.asarray(data["heldout_indices"], dtype=np.int32),
        metres_per_model_unit=np.asarray(data["metres_per_model_unit"], dtype=np.float64),
        sig=np.asarray(signature),
    )
    input_contract_payload = build_final_input_contract(
        data,
        dataset_id=args.dataset_id,
        dmcache_path=dmcache_path,
        model_cache_path=model_cache_path,
        signature=signature,
        depth_shape=tuple(int(value) for value in masked.shape),
    )
    input_contract_path = out / "input_contract.json"
    input_contract_sha = write_and_reload_final_input_contract(
        input_contract_path, input_contract_payload
    )

    provenance = _base_provenance(data, args, selected_names)
    provenance["status"] = "complete"
    provenance["dry_contract"] = False
    provenance["coreml"] = coreml_metadata
    provenance["raw_cache"] = {
        "path": str(raw_cache_path),
        "sha256": sha256_file(raw_cache_path),
        "depth_shape": list(raw_depth.shape),
        "depth_dtype": raw_depth.dtype.str,
        "confidence_shape": list(raw_conf.shape),
        "confidence_dtype": raw_conf.dtype.str,
        "per_frame": raw_rows,
    }
    provenance["model_cache"].update(
        {
            "path": str(model_cache_path),
            "sha256": model_cache_sha,
            "frame_order_sha256": data["hashes"]["frame_order_sha256"],
        }
    )
    provenance["dmcache"].update(
        {
            "path": str(dmcache_path),
            "sha256": sha256_file(dmcache_path),
            "signature": signature,
            "depth": {"shape": list(masked.shape), "dtype": masked.dtype.str},
            "positive_count": int(np.count_nonzero(masked)),
            "positive_fraction": float(np.mean(masked > 0)),
            "universe_indices": prediction_indices,
            "reconstruction_only_neighbor_indices_local": eligible_local_neighbors,
            "depth_units": "optimized_sfm_model_units",
            "metres_per_model_unit": data["metres_per_model_unit"],
        }
    )
    provenance["mask"]["per_frame"] = mask_stats
    provenance["final_input_contract"] = {
        "path": str(input_contract_path),
        "sha256": input_contract_sha,
        "schema_version": "b0-input-contract-v1",
        "shared_validator": "b0_input_contract.validate_input_contract + load_input_contract",
        "prewrite_validated": True,
        "postwrite_reloaded_and_hash_verified": True,
    }
    provenance["generator"]["completed_utc"] = utc_now()
    provenance["generator"]["wall_seconds"] = time.monotonic() - started
    write_json_exclusive(out / "provenance.json", provenance)
    print(
        f"COMMON CACHE OK mode={provenance['run_mode']} frames={selected_count} "
        f"positive={provenance['dmcache']['positive_fraction']:.4f} -> {out}",
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True, type=Path, help="subset_meta_cap50full.json")
    parser.add_argument("--sfm-meta", required=True, type=Path, help="optimized sfm_sparse_meta.json")
    parser.add_argument("--sfm-frames", required=True, type=Path, help="139-row sfm_fed_frames.jsonl")
    parser.add_argument("--arbitration-plan", required=True, type=Path, help="production L1DP arbitration_plan.json")
    parser.add_argument(
        "--production-l1-depth",
        type=Path,
        help="required with --limit: production feed20 L1DP v1 depth/conf artifact",
    )
    parser.add_argument(
        "--sparse-points",
        required=True,
        type=Path,
        help="optimized-SfM sparse xyz/rgb NPZ (legacy filename sfm_sparse_metric.npz)",
    )
    parser.add_argument("--image-root", required=True, type=Path, help="raw/photos_highres")
    parser.add_argument("--model", required=True, type=Path, help="CasDiffMVS_fp32.mlpackage")
    parser.add_argument("--out", required=True, type=Path, help="new output directory (must not exist)")
    parser.add_argument("--dataset-id", default="cap50-real-115")
    parser.add_argument(
        "--metres-per-model-unit",
        required=True,
        type=float,
        help="must equal the frozen all-139 optimized-SfM -> ARKit Umeyama scale",
    )
    parser.add_argument("--compute-units", choices=("cpu_and_gpu", "cpu_only"), default="cpu_and_gpu")
    parser.add_argument("--dry-contract", action="store_true", help="validate and freeze contract; do not predict")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="smoke-only prediction count starting at feed20; never publishable as full",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = args.out.resolve()
    create_exclusive_output_dir(out)
    try:
        cv2.setNumThreads(1)
        execute(args, out)
    except BaseException as exc:
        failure = {
            "schema_version": "b0-cap50-common-cache-failure-v1",
            "status": "failed_preserved",
            "failed_utc": utc_now(),
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "traceback": traceback.format_exc(),
            "script": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
            "arguments": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
            "output_directory_preserved": str(out),
            "warning": "Do not overwrite this directory; use a new --out for any retry.",
        }
        try:
            write_json_exclusive(out / "failure.json", failure)
        except OSError:
            pass
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
