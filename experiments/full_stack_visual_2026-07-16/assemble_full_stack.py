#!/usr/bin/env python3
"""Assemble a visual full-stack cloud without re-introducing the old sparse cloud.

The ghost-gated replay cloud is the sole sparse layer.  Its world gauge is
aligned to the device/raw gauge from overlapping camera centres.  B and D are
already expected in device/raw gauge and are appended without changing either
coordinates or RGB bytes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np


TOOL_SCHEMA = "pw_full_stack_visual_assembler_v1"
REQUIRED_GHOST_ENV = {
    "AETHER_PUBLISH_GATE": "0",
    "AETHER_PUBLISH_DEPTH_CONFLICT_OWNER": "1",
    "AETHER_PUBLISH_DEPTH_OWNER_ERROR_FIRST": "1",
    "AETHER_EXACT_SITE_OWNER_MIN_DEPTH_M": "0.012",
}
STRICT_MIN_SIM3_INLIER_FRACTION = 0.80
STRICT_MAX_SIM3_P95_M = 0.03
STRICT_MIN_NONZERO_RGB_FRACTION = 0.95
STRICT_BASELINE_DIAGONAL_RATIO_MIN = 0.80
STRICT_BASELINE_DIAGONAL_RATIO_MAX = 1.25
STRICT_BASELINE_MIN_WITHIN_3CM_FRACTION = 0.50
STRICT_BASELINE_MAX_MEDIAN_NN_M = 0.10
STRICT_BASELINE_MAX_P90_NN_M = 0.20
PLY_TYPES = {
    "char": ("i1", 1),
    "uchar": ("u1", 1),
    "int8": ("i1", 1),
    "uint8": ("u1", 1),
    "short": ("i2", 2),
    "ushort": ("u2", 2),
    "int16": ("i2", 2),
    "uint16": ("u2", 2),
    "int": ("i4", 4),
    "uint": ("u4", 4),
    "int32": ("i4", 4),
    "uint32": ("u4", 4),
    "float": ("f4", 4),
    "float32": ("f4", 4),
    "double": ("f8", 8),
    "float64": ("f8", 8),
}


class AssemblyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Cloud:
    xyz: np.ndarray
    rgb: np.ndarray

    def __post_init__(self) -> None:
        xyz = np.asarray(self.xyz)
        rgb = np.asarray(self.rgb)
        if xyz.ndim != 2 or xyz.shape[1] != 3:
            raise AssemblyError(f"xyz must be N x 3, got {xyz.shape}")
        if rgb.shape != xyz.shape:
            raise AssemblyError(f"rgb shape {rgb.shape} does not match xyz {xyz.shape}")
        if not np.all(np.isfinite(xyz)):
            raise AssemblyError("PLY contains non-finite coordinates")
        if np.any(rgb < 0) or np.any(rgb > 255):
            raise AssemblyError("PLY RGB is outside uchar range")


@dataclass(frozen=True)
class Sim3:
    scale: float
    rotation: np.ndarray
    translation: np.ndarray

    def apply(self, xyz: np.ndarray) -> np.ndarray:
        return self.scale * (np.asarray(xyz, dtype=np.float64) @ self.rotation.T) + self.translation


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_ply_header(stream) -> tuple[str, int, list[tuple[str, str]], int]:
    first = stream.readline()
    if first != b"ply\n" and first != b"ply\r\n":
        raise AssemblyError("not a PLY file")
    fmt = None
    vertex_count = None
    properties: list[tuple[str, str]] = []
    current_element = None
    other_nonempty_elements: list[str] = []
    while True:
        line = stream.readline()
        if not line:
            raise AssemblyError("truncated PLY header")
        text = line.decode("ascii").strip()
        fields = text.split()
        if not fields or fields[0] in {"comment", "obj_info"}:
            continue
        if fields[0] == "format":
            if len(fields) != 3 or fields[2] != "1.0":
                raise AssemblyError(f"unsupported PLY format line: {text}")
            fmt = fields[1]
        elif fields[0] == "element":
            if len(fields) != 3:
                raise AssemblyError(f"invalid element line: {text}")
            current_element = fields[1]
            count = int(fields[2])
            if current_element == "vertex":
                vertex_count = count
            elif count:
                other_nonempty_elements.append(current_element)
        elif fields[0] == "property" and current_element == "vertex":
            if len(fields) != 3 or fields[1] == "list":
                raise AssemblyError("vertex list properties are unsupported")
            if fields[1] not in PLY_TYPES:
                raise AssemblyError(f"unsupported PLY scalar type {fields[1]}")
            properties.append((fields[2], fields[1]))
        elif fields[0] == "end_header":
            break
    if fmt not in {"ascii", "binary_little_endian", "binary_big_endian"}:
        raise AssemblyError(f"unsupported PLY encoding {fmt}")
    if vertex_count is None:
        raise AssemblyError("PLY has no vertex element")
    if other_nonempty_elements:
        raise AssemblyError(f"non-empty non-vertex elements unsupported: {other_nonempty_elements}")
    return fmt, vertex_count, properties, stream.tell()


def read_rgb_ply(path: Path) -> Cloud:
    with path.open("rb") as stream:
        fmt, count, properties, _ = _read_ply_header(stream)
        names = [name for name, _ in properties]
        required = ["x", "y", "z", "red", "green", "blue"]
        missing = [name for name in required if name not in names]
        if missing:
            raise AssemblyError(f"{path}: missing PLY properties {missing}")
        property_types = dict(properties)
        for name in ("red", "green", "blue"):
            if property_types[name] not in {"uchar", "uint8"}:
                raise AssemblyError(f"{path}: {name} must be uchar, got {property_types[name]}")
        if fmt == "ascii":
            rows: list[list[str]] = []
            for index in range(count):
                line = stream.readline()
                if not line:
                    raise AssemblyError(f"{path}: truncated at ASCII vertex {index}")
                fields = line.split()
                if len(fields) != len(properties):
                    raise AssemblyError(
                        f"{path}: vertex {index} has {len(fields)} fields, expected {len(properties)}"
                    )
                rows.append([field.decode("ascii") for field in fields])
            cols = {name: index for index, (name, _) in enumerate(properties)}
            xyz_values = [[float(row[cols[name]]) for name in ("x", "y", "z")] for row in rows]
            rgb_values = [[int(row[cols[name]]) for name in ("red", "green", "blue")] for row in rows]
            if any(value < 0 or value > 255 for row in rgb_values for value in row):
                raise AssemblyError(f"{path}: ASCII RGB outside uchar range")
            xyz = np.asarray(xyz_values, dtype=np.float64).reshape((-1, 3))
            rgb = np.asarray(rgb_values, dtype=np.uint8).reshape((-1, 3))
            return Cloud(xyz, rgb)

        endian = "<" if fmt == "binary_little_endian" else ">"
        dtype = np.dtype([(name, endian + PLY_TYPES[kind][0]) for name, kind in properties])
        payload = stream.read(count * dtype.itemsize)
        if len(payload) != count * dtype.itemsize:
            raise AssemblyError(f"{path}: truncated binary vertex payload")
        array = np.frombuffer(payload, dtype=dtype, count=count)
        xyz = np.column_stack([array[name] for name in ("x", "y", "z")]).astype(np.float64)
        rgb = np.column_stack([array[name] for name in ("red", "green", "blue")]).astype(np.uint8)
        return Cloud(xyz, rgb)


def canonical_payload(cloud: Cloud) -> bytes:
    dtype = np.dtype(
        [("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")]
    )
    out = np.empty(len(cloud.xyz), dtype=dtype)
    for index, name in enumerate(("x", "y", "z")):
        out[name] = cloud.xyz[:, index].astype(np.float32)
    for index, name in enumerate(("red", "green", "blue")):
        out[name] = cloud.rgb[:, index]
    return out.tobytes(order="C")


def rgb_payload(cloud: Cloud) -> bytes:
    return np.ascontiguousarray(cloud.rgb, dtype=np.uint8).tobytes(order="C")


def write_rgb_ply(path: Path, clouds: Sequence[Cloud]) -> str:
    count = sum(len(cloud.xyz) for cloud in clouds)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment PocketWorld full-stack visual: ghost-gated sparse + B + D\n"
        f"element vertex {count}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(header)
        for cloud in clouds:
            stream.write(canonical_payload(cloud))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return sha256_file(path)


def quaternion_to_rotation(q: Sequence[float]) -> np.ndarray:
    w, x, y, z = (float(v) for v in q)
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm <= 0.0 or not math.isfinite(norm):
        raise AssemblyError("invalid zero/non-finite quaternion")
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def camera_center(q: Sequence[float], translation: Sequence[float], convention: str) -> np.ndarray:
    value = np.asarray(translation, dtype=np.float64)
    if value.shape != (3,) or not np.all(np.isfinite(value)):
        raise AssemblyError("invalid pose translation")
    if convention == "camera_center":
        return value
    if convention != "tvec":
        raise AssemblyError(f"unknown translation convention {convention}")
    return -(quaternion_to_rotation(q).T @ value)


def read_device_centres(path: Path, convention: str) -> tuple[dict[str, np.ndarray], int, int]:
    document = json.loads(path.read_text(encoding="utf-8"))
    poses = document.get("poses")
    if not isinstance(poses, list):
        raise AssemblyError(f"{path}: poses must be a list")
    centres: dict[str, np.ndarray] = {}
    registered = 0
    for pose in poses:
        if not pose.get("registered", False):
            continue
        registered += 1
        frame_id = str(pose["frame_id"])
        if frame_id in centres:
            raise AssemblyError(f"{path}: duplicate registered frame_id {frame_id}")
        centres[frame_id] = camera_center(pose["quat_wxyz"], pose["t"], convention)
    return centres, registered, len(poses)


def _csv_truth(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def read_replay_centres(
    path: Path, convention: str
) -> tuple[dict[str, np.ndarray], int, int, list[str], list[str]]:
    centres: dict[str, np.ndarray] = {}
    registered = 0
    total = 0
    unregistered_frame_ids: list[str] = []
    row_frame_ids: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"frame_id", "registered", "qw", "qx", "qy", "qz", "tx", "ty", "tz"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise AssemblyError(f"{path}: missing pose CSV fields {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            total += 1
            frame_id = str(row["frame_id"])
            if frame_id in row_frame_ids:
                raise AssemblyError(f"{path}: duplicate pose CSV frame_id {frame_id}")
            row_frame_ids.append(frame_id)
            if not _csv_truth(row["registered"]):
                unregistered_frame_ids.append(frame_id)
                continue
            registered += 1
            centres[frame_id] = camera_center(
                [row["qw"], row["qx"], row["qy"], row["qz"]],
                [row["tx"], row["ty"], row["tz"]],
                convention,
            )
    return centres, registered, total, unregistered_frame_ids, row_frame_ids


def read_replay_ledger_ids(path: Path) -> list[str]:
    frame_ids: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            document = json.loads(line)
            if "frameId" not in document:
                raise AssemblyError(f"{path}:{line_number}: missing frameId")
            frame_id = str(document["frameId"])
            if frame_id in seen:
                raise AssemblyError(f"{path}:{line_number}: duplicate frameId {frame_id}")
            seen.add(frame_id)
            frame_ids.append(frame_id)
    if not frame_ids:
        raise AssemblyError(f"{path}: empty replay ledger")
    return frame_ids


def umeyama(source: np.ndarray, target: np.ndarray) -> Sim3:
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3 or len(source) < 3:
        raise AssemblyError("Sim3 needs at least three paired 3D points")
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    xs = source - source_mean
    yt = target - target_mean
    variance = float(np.sum(xs * xs) / len(source))
    if variance <= np.finfo(np.float64).eps:
        raise AssemblyError("degenerate source centres for Sim3")
    covariance = (yt.T @ xs) / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    signs = np.ones(3, dtype=np.float64)
    if np.linalg.det(u @ vt) < 0:
        signs[-1] = -1.0
    rotation = u @ np.diag(signs) @ vt
    scale = float(np.sum(singular * signs) / variance)
    if not math.isfinite(scale) or scale <= 0:
        raise AssemblyError(f"invalid Sim3 scale {scale}")
    translation = target_mean - scale * (rotation @ source_mean)
    return Sim3(scale, rotation, translation)


def _nondegenerate(points: np.ndarray) -> bool:
    centred = points - points.mean(axis=0)
    singular = np.linalg.svd(centred, compute_uv=False)
    return len(singular) >= 2 and singular[1] > max(1e-12, singular[0] * 1e-8)


def robust_sim3(source: np.ndarray, target: np.ndarray) -> tuple[Sim3, np.ndarray, dict[str, float | int]]:
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if source.shape != target.shape or len(source) < 3:
        raise AssemblyError("robust Sim3 needs at least three overlapping poses")
    radius = float(np.median(np.linalg.norm(target - np.median(target, axis=0), axis=1)))
    threshold = max(1e-7, radius * 0.02)
    minimum_threshold = max(1e-8, radius * 1e-6)

    triples: list[tuple[int, int, int]] = []
    if len(source) <= 18:
        triples.extend(itertools.combinations(range(len(source)), 3))
    else:
        # Fixed seed and sorted unique triples make the robust fit repeatable.
        generator = np.random.default_rng(0x504F434B4554)
        seen: set[tuple[int, int, int]] = set()
        while len(seen) < 768:
            seen.add(tuple(sorted(int(v) for v in generator.choice(len(source), 3, replace=False))))
        triples.extend(sorted(seen))
    best = None
    for triple in triples:
        idx = np.asarray(triple, dtype=np.int64)
        if not _nondegenerate(source[idx]) or not _nondegenerate(target[idx]):
            continue
        try:
            candidate = umeyama(source[idx], target[idx])
        except AssemblyError:
            continue
        residual = np.linalg.norm(candidate.apply(source) - target, axis=1)
        inliers = residual <= threshold
        score = (int(np.count_nonzero(inliers)), -float(np.median(residual[inliers])) if np.any(inliers) else -math.inf)
        if best is None or score > best[0]:
            best = (score, candidate, inliers)
    if best is None or int(np.count_nonzero(best[2])) < 3:
        raise AssemblyError("no non-degenerate robust Sim3 hypothesis")

    inliers = best[2]
    for _ in range(8):
        transform = umeyama(source[inliers], target[inliers])
        residual = np.linalg.norm(transform.apply(source) - target, axis=1)
        centre = float(np.median(residual[inliers]))
        mad = float(np.median(np.abs(residual[inliers] - centre)))
        refined_threshold = max(minimum_threshold, centre + 4.5 * 1.4826 * mad)
        refined_threshold = min(threshold, refined_threshold)
        next_inliers = residual <= refined_threshold
        if int(np.count_nonzero(next_inliers)) < 3:
            break
        if np.array_equal(next_inliers, inliers):
            inliers = next_inliers
            break
        inliers = next_inliers
    transform = umeyama(source[inliers], target[inliers])
    residual = np.linalg.norm(transform.apply(source) - target, axis=1)
    metrics: dict[str, float | int] = {
        "overlap_count": int(len(source)),
        "inlier_count": int(np.count_nonzero(inliers)),
        "outlier_count": int(len(source) - np.count_nonzero(inliers)),
        "ransac_threshold": float(threshold),
        "rmse_inliers": float(np.sqrt(np.mean(np.square(residual[inliers])))),
        "median_inliers": float(np.median(residual[inliers])),
        "p95_inliers": float(np.percentile(residual[inliers], 95)),
        "max_inliers": float(np.max(residual[inliers])),
        "max_all": float(np.max(residual)),
    }
    return transform, inliers, metrics


def _sim3_from_document(document: Mapping, scale_key: str, rotation_key: str, translation_key: str) -> Sim3:
    scale = float(document[scale_key])
    rotation = np.asarray(document[rotation_key], dtype=np.float64).reshape((3, 3))
    translation = np.asarray(document[translation_key], dtype=np.float64)
    if translation.shape != (3,) or not np.all(np.isfinite(rotation)) or not np.all(np.isfinite(translation)):
        raise AssemblyError("invalid certified Sim3 matrix/vector")
    if scale <= 0 or not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-5):
        raise AssemblyError("certified Sim3 has invalid scale/rotation determinant")
    return Sim3(scale, rotation, translation)


def _compose_sim3(first: Sim3, second: Sim3) -> Sim3:
    # first maps A->B, second maps B->C.
    return Sim3(
        first.scale * second.scale,
        second.rotation @ first.rotation,
        second.scale * (second.rotation @ first.translation) + second.translation,
    )


def _resolve_manifest_path(manifest_path: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    return candidate


def load_certified_chained_sim3(
    replay_to_metric_path: Path,
    metric_to_raw_path: Path,
    ghost_source_path: Path,
    ghost_source: Cloud,
) -> tuple[Sim3, dict, dict[str, float | int]]:
    first_document = json.loads(replay_to_metric_path.read_text(encoding="utf-8"))
    second_document = json.loads(metric_to_raw_path.read_text(encoding="utf-8"))
    if first_document.get("schema") != "pw_d_metric_transform_v1":
        raise AssemblyError(f"{replay_to_metric_path}: wrong replay-to-metric schema")
    if second_document.get("schema") != "pw_d_and_ghost_metric_to_device_raw_v1":
        raise AssemblyError(f"{metric_to_raw_path}: wrong metric-to-raw schema")
    source_record = first_document.get("source_ghost")
    metric_record = first_document.get("output_ghost")
    raw_input_record = (second_document.get("inputs") or {}).get("ghost_metric")
    raw_output_record = (second_document.get("outputs") or {}).get("ghost_raw")
    if not all(isinstance(record, dict) for record in (source_record, metric_record, raw_input_record, raw_output_record)):
        raise AssemblyError("certified Sim3 chain is missing ghost anchor records")
    source_sha = sha256_file(ghost_source_path)
    if source_record.get("sha256") != source_sha:
        raise AssemblyError("replay-to-metric certificate does not bind the ghost source PLY")
    if metric_record.get("sha256") != raw_input_record.get("sha256"):
        raise AssemblyError("Sim3 chain metric anchor hashes do not join")

    metric_anchor_path = _resolve_manifest_path(replay_to_metric_path, str(metric_record["path"]))
    raw_anchor_path = _resolve_manifest_path(metric_to_raw_path, str(raw_output_record["path"]))
    if not metric_anchor_path.is_file() or sha256_file(metric_anchor_path) != metric_record["sha256"]:
        raise AssemblyError("replay-to-metric anchor file/hash is unavailable")
    if not raw_anchor_path.is_file() or sha256_file(raw_anchor_path) != raw_output_record["sha256"]:
        raise AssemblyError("metric-to-raw anchor file/hash is unavailable")

    first = _sim3_from_document(
        first_document["sim3"], "scale", "rotation_row_major", "translation"
    )
    second = _sim3_from_document(
        second_document["metric_to_raw_sim3"],
        "scale_metric_to_raw",
        "rotation_metric_to_raw_row_major",
        "translation_metric_to_raw",
    )
    combined = _compose_sim3(first, second)
    metric_anchor = read_rgb_ply(metric_anchor_path)
    raw_anchor = read_rgb_ply(raw_anchor_path)
    if len(ghost_source.xyz) != len(metric_anchor.xyz) or len(ghost_source.xyz) != len(raw_anchor.xyz):
        raise AssemblyError("Sim3 chain anchors do not preserve exact ghost point count")
    if not np.array_equal(ghost_source.rgb, metric_anchor.rgb) or not np.array_equal(ghost_source.rgb, raw_anchor.rgb):
        raise AssemblyError("Sim3 chain anchors do not preserve exact ghost RGB/order")
    residual_values = np.linalg.norm(combined.apply(ghost_source.xyz) - raw_anchor.xyz, axis=1)
    residual = {
        "overlap_count": int(len(residual_values)),
        "inlier_count": int(len(residual_values)),
        "outlier_count": 0,
        "inlier_fraction": 1.0,
        "rmse_inliers": float(np.sqrt(np.mean(np.square(residual_values)))),
        "median_inliers": float(np.median(residual_values)),
        "p95_inliers": float(np.percentile(residual_values, 95)),
        "max_inliers": float(np.max(residual_values)),
        "max_all": float(np.max(residual_values)),
        "p95_source_metric_units": float(np.percentile(residual_values, 95)) / combined.scale,
        "rmse_source_metric_units": float(np.sqrt(np.mean(np.square(residual_values)))) / combined.scale,
        "max_source_metric_units": float(np.max(residual_values)) / combined.scale,
    }
    evidence = {
        "kind": "certified_replay_metric_raw_chain",
        "replay_to_metric_manifest": {
            "path": str(replay_to_metric_path.resolve()),
            "sha256": sha256_file(replay_to_metric_path),
        },
        "metric_to_raw_manifest": {
            "path": str(metric_to_raw_path.resolve()),
            "sha256": sha256_file(metric_to_raw_path),
        },
        "metric_anchor": {"path": str(metric_anchor_path.resolve()), "sha256": sha256_file(metric_anchor_path)},
        "raw_anchor": {"path": str(raw_anchor_path.resolve()), "sha256": sha256_file(raw_anchor_path)},
        "pointwise_chain_verified": True,
    }
    return combined, evidence, residual


def _bbox_stats(cloud: Cloud) -> dict[str, object]:
    if not len(cloud.xyz):
        return {"min": None, "max": None, "diagonal": 0.0, "centre": None}
    lower = np.min(cloud.xyz, axis=0)
    upper = np.max(cloud.xyz, axis=0)
    return {
        "min": lower.tolist(),
        "max": upper.tolist(),
        "diagonal": float(np.linalg.norm(upper - lower)),
        "centre": ((lower + upper) * 0.5).tolist(),
    }


def _device_baseline_alignment_stats(
    device: Cloud, candidate: Cloud, raw_units_per_metre: float
) -> dict:
    """Check the actual sparse geometry, not only camera-centre Sim3 agreement."""
    if not math.isfinite(raw_units_per_metre) or raw_units_per_metre <= 0:
        raise AssemblyError("invalid raw-units-per-metre for device baseline alignment")
    try:
        from scipy.spatial import cKDTree
    except ImportError as error:
        raise AssemblyError("strict device baseline alignment requires scipy.spatial.cKDTree") from error

    device_xyz = np.asarray(device.xyz, dtype=np.float64)
    candidate_xyz = np.asarray(candidate.xyz, dtype=np.float64)
    if len(device_xyz) == 0 or len(candidate_xyz) == 0:
        raise AssemblyError("device baseline alignment requires two non-empty clouds")
    candidate_to_device = cKDTree(device_xyz).query(candidate_xyz, k=1, workers=1)[0]
    device_to_candidate = cKDTree(candidate_xyz).query(device_xyz, k=1, workers=1)[0]

    def summarize(raw: np.ndarray) -> dict:
        metric = np.asarray(raw, dtype=np.float64) / raw_units_per_metre
        return {
            "median_m": float(np.median(metric)),
            "p90_m": float(np.quantile(metric, 0.90)),
            "p95_m": float(np.quantile(metric, 0.95)),
            "within_3cm_fraction": float(np.mean(metric <= 0.03)),
        }

    device_diagonal = float(_bbox_stats(device)["diagonal"])
    candidate_diagonal = float(_bbox_stats(candidate)["diagonal"])
    diagonal_ratio = candidate_diagonal / device_diagonal if device_diagonal > 0 else math.inf
    return {
        "device_point_count": int(len(device_xyz)),
        "candidate_point_count": int(len(candidate_xyz)),
        "raw_units_per_metre": float(raw_units_per_metre),
        "device_bbox_diagonal_raw": device_diagonal,
        "candidate_bbox_diagonal_raw": candidate_diagonal,
        "candidate_to_device_diagonal_ratio": float(diagonal_ratio),
        "candidate_to_device": summarize(candidate_to_device),
        "device_to_candidate": summarize(device_to_candidate),
    }


def _validate_device_baseline_alignment(stats: Mapping) -> None:
    ratio = float(stats["candidate_to_device_diagonal_ratio"])
    if not (STRICT_BASELINE_DIAGONAL_RATIO_MIN <= ratio <= STRICT_BASELINE_DIAGONAL_RATIO_MAX):
        raise AssemblyError(
            "strict device baseline geometry mismatch: bbox diagonal ratio "
            f"{ratio:.6f} outside [{STRICT_BASELINE_DIAGONAL_RATIO_MIN}, "
            f"{STRICT_BASELINE_DIAGONAL_RATIO_MAX}]"
        )
    for direction in ("candidate_to_device", "device_to_candidate"):
        values = stats[direction]
        if float(values["within_3cm_fraction"]) < STRICT_BASELINE_MIN_WITHIN_3CM_FRACTION:
            raise AssemblyError(
                f"strict device baseline geometry mismatch: {direction} within-3cm fraction "
                f"{values['within_3cm_fraction']:.6f} < {STRICT_BASELINE_MIN_WITHIN_3CM_FRACTION}"
            )
        if float(values["median_m"]) > STRICT_BASELINE_MAX_MEDIAN_NN_M:
            raise AssemblyError(
                f"strict device baseline geometry mismatch: {direction} median NN "
                f"{values['median_m']:.6f}m > {STRICT_BASELINE_MAX_MEDIAN_NN_M}m"
            )
        if float(values["p90_m"]) > STRICT_BASELINE_MAX_P90_NN_M:
            raise AssemblyError(
                f"strict device baseline geometry mismatch: {direction} p90 NN "
                f"{values['p90_m']:.6f}m > {STRICT_BASELINE_MAX_P90_NN_M}m"
            )


def _layer_record(
    name: str,
    path: Path,
    cloud: Cloud,
    assembled: Cloud,
    offset: int,
    source_gauge: str,
    sim3_applied: bool,
) -> dict:
    source_rgb_sha = sha256_bytes(rgb_payload(cloud))
    assembled_rgb_sha = sha256_bytes(rgb_payload(assembled))
    if source_rgb_sha != assembled_rgb_sha:
        raise AssemblyError(f"{name}: RGB changed during assembly")
    return {
        "name": name,
        "path": str(path.resolve()),
        "point_count": int(len(cloud.xyz)),
        "vertex_offset_begin": int(offset),
        "vertex_offset_end_exclusive": int(offset + len(cloud.xyz)),
        "source_sha256": sha256_file(path),
        "source_rgb_sha256": source_rgb_sha,
        "assembled_rgb_sha256": assembled_rgb_sha,
        "assembled_payload_sha256": sha256_bytes(canonical_payload(assembled)),
        "source_gauge": source_gauge,
        "sim3_replay_to_device_raw_applied": sim3_applied,
        "source_bounds": _bbox_stats(cloud),
        "assembled_device_raw_bounds": _bbox_stats(assembled),
    }


def _validate_gauge_vector(paths: Sequence[str], gauges: Sequence[str], role: str) -> list[str]:
    if len(paths) != len(gauges):
        raise AssemblyError(f"{role}: every PLY requires one explicit gauge, got {len(paths)} paths/{len(gauges)} gauges")
    invalid = [gauge for gauge in gauges if gauge not in {"metric_replay", "device_raw"}]
    if invalid:
        raise AssemblyError(f"{role}: invalid gauges {invalid}")
    return list(gauges)


def _parse_env(values: Sequence[str], strict_final: bool) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise AssemblyError(f"ghost env must be KEY=VALUE, got {value!r}")
        key, item = value.split("=", 1)
        if not key or key in result:
            raise AssemblyError(f"invalid/duplicate ghost env key {key!r}")
        result[key] = item
    if strict_final:
        if result != REQUIRED_GHOST_ENV:
            raise AssemblyError(
                f"strict FULL requires exact ghost environment {REQUIRED_GHOST_ENV}, got {result}"
            )
    elif not result:
        raise AssemblyError("at least one ghost environment value is required")
    return dict(sorted(result.items()))


def _c_backend_identity(value: str | None, path: Path | None) -> dict:
    if (value is None) == (path is None):
        raise AssemblyError("provide exactly one of --c-backend or --c-backend-json")
    if path is not None:
        return {
            "kind": "json_file",
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "value": json.loads(path.read_text(encoding="utf-8")),
        }
    return {"kind": "literal", "value": value}


def _validate_c_backend_certificate(
    document: dict,
    certificate_path: Path,
    expected_role_outputs: Mapping[str, Sequence[str]],
) -> dict:
    if document.get("schema") != "pw_c_backend_certificate_v1" or document.get("status") != "PASS":
        raise AssemblyError(f"{certificate_path}: C backend certificate schema/status invalid")
    artifact = document.get("artifact")
    if not isinstance(artifact, dict):
        raise AssemblyError(f"{certificate_path}: C certificate has no artifact binding")
    artifact_path_value = artifact.get("path")
    expected_sha = artifact.get("sha256")
    if not isinstance(artifact_path_value, str) or not isinstance(expected_sha, str):
        raise AssemblyError(f"{certificate_path}: C artifact path/SHA missing")
    artifact_path = Path(artifact_path_value)
    if not artifact_path.is_absolute():
        artifact_path = certificate_path.parent / artifact_path
    if not artifact_path.is_file():
        raise AssemblyError(f"{certificate_path}: C artifact missing: {artifact_path}")
    actual_sha = sha256_file(artifact_path)
    if actual_sha != expected_sha:
        raise AssemblyError(f"{certificate_path}: C artifact SHA mismatch")
    backend = document.get("backend")
    if not isinstance(backend, str) or not backend:
        raise AssemblyError(f"{certificate_path}: C backend identity missing")

    report_record = document.get("execution_report")
    if not isinstance(report_record, dict) or not isinstance(report_record.get("path"), str):
        raise AssemblyError(f"{certificate_path}: C applied execution report binding missing")
    report_path = _resolve_manifest_path(certificate_path, report_record["path"])
    if not report_path.is_file() or sha256_file(report_path) != report_record.get("sha256"):
        raise AssemblyError(f"{certificate_path}: C execution report path/SHA mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "pw_c_tiled_execution_report_v1" or report.get("status") != "PASS":
        raise AssemblyError(f"{report_path}: C execution report schema/status invalid")
    if report.get("backend") != backend or report.get("backend_exercised") is not True:
        raise AssemblyError(f"{report_path}: C backend was not actually exercised")
    if report.get("backend_artifact_sha256") != actual_sha:
        raise AssemblyError(f"{report_path}: C execution used a different backend artifact")
    executions = report.get("executions")
    if not isinstance(executions, list) or not executions:
        raise AssemblyError(f"{report_path}: C applied execution records missing")
    expected_pairs = sorted(
        (role, output_sha)
        for role, output_hashes in expected_role_outputs.items()
        for output_sha in output_hashes
    )
    actual_pairs: list[tuple[str, str]] = []
    execution_summaries = []
    for execution in executions:
        if not isinstance(execution, dict):
            raise AssemblyError(f"{report_path}: malformed C applied execution record")
        role = execution.get("algorithm_role")
        parameters = execution.get("effective_parameters")
        input_identity = execution.get("input_identity")
        output_identity = execution.get("output_identity")
        if role not in expected_role_outputs or not isinstance(parameters, dict) or not parameters:
            raise AssemblyError(f"{report_path}: C execution role/effective parameters invalid")
        if (
            not isinstance(input_identity, dict)
            or not isinstance(input_identity.get("sha256"), str)
            or len(input_identity["sha256"]) != 64
            or not isinstance(output_identity, dict)
            or not isinstance(output_identity.get("sha256"), str)
        ):
            raise AssemblyError(f"{report_path}: C execution input/output identity missing")
        validation = execution.get("output_validation")
        if (
            not isinstance(validation, dict)
            or validation.get("exact") is not True
            or validation.get("mismatch_count") != 0
            or validation.get("max_abs_error") != 0.0
        ):
            raise AssemblyError(f"{report_path}: C applied output is not bit-exact with its reference")
        elapsed_ms = execution.get("elapsed_ms")
        peak_memory_bytes = execution.get("peak_memory_bytes")
        if (
            not isinstance(elapsed_ms, (int, float))
            or not math.isfinite(float(elapsed_ms))
            or float(elapsed_ms) < 0
            or not isinstance(peak_memory_bytes, int)
            or peak_memory_bytes <= 0
        ):
            raise AssemblyError(f"{report_path}: C execution timing/memory evidence invalid")
        actual_pairs.append((role, output_identity["sha256"]))
        execution_summaries.append(
            {
                "algorithm_role": role,
                "effective_parameters": parameters,
                "input_sha256": input_identity["sha256"],
                "output_sha256": output_identity["sha256"],
                "elapsed_ms": float(elapsed_ms),
                "peak_memory_bytes": peak_memory_bytes,
            }
        )
    if sorted(actual_pairs) != expected_pairs:
        raise AssemblyError(
            f"{report_path}: C execution outputs do not bind exact B floor/wall PLYs; "
            f"expected={expected_pairs}, actual={sorted(actual_pairs)}"
        )
    source_records = report.get("source_artifacts")
    if not isinstance(source_records, list) or not source_records:
        raise AssemblyError(f"{report_path}: C source/shader artifact bindings missing")
    resolved_sources = []
    for source_record in source_records:
        if not isinstance(source_record, dict) or not isinstance(source_record.get("path"), str):
            raise AssemblyError(f"{report_path}: malformed C source artifact binding")
        source_path = _resolve_manifest_path(report_path, source_record["path"])
        if not source_path.is_file() or sha256_file(source_path) != source_record.get("sha256"):
            raise AssemblyError(f"{report_path}: C source artifact path/SHA mismatch")
        resolved_sources.append({"path": str(source_path.resolve()), "sha256": sha256_file(source_path)})
    return {
        "kind": "verified_certificate",
        "path": str(certificate_path.resolve()),
        "sha256": sha256_file(certificate_path),
        "schema": document["schema"],
        "status": document["status"],
        "backend": backend,
        "artifact": {"path": str(artifact_path.resolve()), "sha256": actual_sha},
        "execution_report": {
            "path": str(report_path.resolve()),
            "sha256": sha256_file(report_path),
            "executions": execution_summaries,
            "source_artifacts": resolved_sources,
        },
    }


def _all_scalar_strings(value) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            result.add(str(key))
            result.update(_all_scalar_strings(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_all_scalar_strings(item))
    elif isinstance(value, (str, int, float, bool)) or value is None:
        result.add(str(value))
    return result


def _load_bound_certificate(path: Path, expected_hashes: Sequence[str], role: str) -> tuple[dict, dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    values = _all_scalar_strings(document)
    missing = sorted(set(expected_hashes) - values)
    if missing:
        raise AssemblyError(f"{role} certificate {path} does not bind hashes {missing}")
    record = {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "schema": document.get("schema") if isinstance(document, dict) else None,
        "bound_sha256": sorted(set(expected_hashes)),
    }
    return document, record


def _validate_ghost_provenance(document: dict, cloud: Cloud, path: Path, expected_sha: str) -> None:
    if document.get("schema") != "pw_ghost_truecolor_certificate_v1" or document.get("status") != "PASS":
        raise AssemblyError(f"{path}: ghost true-colour certificate schema/status invalid")
    if document.get("full_set_owner_arm") is not True:
        raise AssemblyError(f"{path}: ghost provenance does not certify full_set_owner_arm=true")
    if document.get("generic_publish_subset") is not False:
        raise AssemblyError(f"{path}: ghost provenance must certify generic_publish_subset=false")
    if document.get("color_source") not in {"tracked_observation", "full_resolution_colorize"}:
        raise AssemblyError(f"{path}: unsupported/unproven ghost color_source")
    if document.get("gauge") != "metric_replay":
        raise AssemblyError(f"{path}: ghost sparse must be certified in metric_replay gauge")
    if document.get("output_sha256") != expected_sha:
        raise AssemblyError(f"{path}: ghost output_sha256 does not bind the exact PLY")

    source_record = document.get("source_provenance")
    if not isinstance(source_record, dict) or not isinstance(source_record.get("path"), str):
        raise AssemblyError(f"{path}: detailed track-colour provenance is not bound")
    detailed_path = _resolve_manifest_path(path, source_record["path"])
    if not detailed_path.is_file() or sha256_file(detailed_path) != source_record.get("sha256"):
        raise AssemblyError(f"{path}: detailed track-colour provenance path/SHA mismatch")
    detailed = json.loads(detailed_path.read_text(encoding="utf-8"))
    if detailed.get("schema") != "pocketworld_exact_track_truecolor_v1":
        raise AssemblyError(f"{detailed_path}: wrong detailed true-colour schema")
    detailed_output = detailed.get("outputs") or {}
    if detailed_output.get("ply_sha256") != expected_sha:
        raise AssemblyError(f"{detailed_path}: detailed provenance does not bind exact ghost PLY")
    color_stats = detailed.get("color_stats") or {}

    actual_count = int(len(cloud.rgb))
    actual_nonzero = int(np.count_nonzero(np.any(cloud.rgb != 0, axis=1)))
    if document.get("point_count") != actual_count:
        raise AssemblyError(f"{path}: ghost provenance point_count does not match PLY")
    if document.get("colorized_point_count") != actual_count:
        raise AssemblyError(f"{path}: not every ghost sparse point is certified colorized")
    if document.get("nonzero_rgb_point_count") != actual_nonzero:
        raise AssemblyError(f"{path}: ghost nonzero RGB count does not match PLY")
    if color_stats.get("colored_points") != actual_count or color_stats.get("nonzero_rgb_points") != actual_nonzero:
        raise AssemblyError(f"{detailed_path}: detailed color counts do not match PLY")
    if color_stats.get("fallback_gray_points") != 0:
        raise AssemblyError(
            f"{detailed_path}: fallback_gray_points={color_stats.get('fallback_gray_points')} cannot be labelled truecolor PASS"
        )
    for key in ("missing_jpeg_frames", "missing_jpeg_basenames"):
        if color_stats.get(key) not in (None, []):
            raise AssemblyError(f"{detailed_path}: {key} is non-empty")
    fraction = (actual_nonzero / actual_count) if actual_count else 0.0
    if fraction < STRICT_MIN_NONZERO_RGB_FRACTION:
        raise AssemblyError(
            f"{path}: true-colour nonzero coverage {fraction:.6f} < {STRICT_MIN_NONZERO_RGB_FRACTION}"
        )


def _validate_b_provenance(
    document: dict, path: Path, cloud: Cloud, expected_sha: str, expected_gauge: str
) -> None:
    point_count = len(cloud.xyz)
    if document.get("schema") != "pw_b_dense_planesweep_certificate_v1" or document.get("status") != "PASS":
        raise AssemblyError(f"{path}: B dense certificate schema/status invalid")
    config = document.get("config") if isinstance(document, dict) else None
    grid_m = config.get("grid_m") if isinstance(config, dict) else None
    if not isinstance(grid_m, (int, float)) or float(grid_m) > 0.0100001:
        raise AssemblyError(f"{path}: B FULL requires actual <=1cm resweep, got grid_m={grid_m}")
    if document.get("forbidden_matcher_outputs_consumed") is not False:
        raise AssemblyError(f"{path}: B provenance does not prove pure-A matcher-free input")
    if document.get("gauge") != expected_gauge:
        raise AssemblyError(f"{path}: B provenance gauge does not match declared input gauge")
    output = document.get("output")
    if not isinstance(output, dict) or output.get("sha256") != expected_sha:
        raise AssemblyError(f"{path}: B output SHA does not bind the exact PLY")
    totals = document.get("totals")
    quality = document.get("quality")
    if not isinstance(totals, dict) or totals.get("accepted") != point_count or point_count <= 0:
        raise AssemblyError(f"{path}: B accepted count does not exactly match non-empty PLY")
    if not isinstance(quality, dict):
        raise AssemblyError(f"{path}: B quality certificate missing")
    offplane = quality.get("max_abs_plane_residual_m")
    zncc = quality.get("zncc_median")
    ncc_min = config.get("ncc_min")
    if not isinstance(offplane, (int, float)) or float(offplane) > 1e-5:
        raise AssemblyError(f"{path}: B off-plane residual is not certified <=10um")
    if not isinstance(zncc, (int, float)) or not isinstance(ncc_min, (int, float)) or float(zncc) < float(ncc_min):
        raise AssemblyError(f"{path}: B ZNCC quality is below its configured acceptance floor")
    if quality.get("zncc_statistic") != "actual_median_of_retained_births":
        raise AssemblyError(f"{path}: B ZNCC must be the actual retained-birth median, not a lower bound")
    if "lower_bound" in str(quality.get("zncc_semantics", "")).lower():
        raise AssemblyError(f"{path}: configured ZNCC lower bound cannot masquerade as an actual median")
    evidence_record = document.get("quality_evidence")
    if not isinstance(evidence_record, dict) or not isinstance(evidence_record.get("path"), str):
        raise AssemblyError(f"{path}: B retained-birth quality evidence missing")
    evidence_path = _resolve_manifest_path(path, evidence_record["path"])
    if not evidence_path.is_file() or sha256_file(evidence_path) != evidence_record.get("sha256"):
        raise AssemblyError(f"{path}: B retained-birth quality evidence path/SHA mismatch")
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("schema") != "pw_b_retained_quality_evidence_v1":
        raise AssemblyError(f"{evidence_path}: wrong B retained-quality evidence schema")
    if evidence.get("output_sha256") != expected_sha or evidence.get("point_count") != point_count:
        raise AssemblyError(f"{evidence_path}: B evidence does not bind exact output/count")
    rows = evidence.get("rows")
    if not isinstance(rows, list) or len(rows) != point_count:
        raise AssemblyError(f"{evidence_path}: B evidence row count mismatch")
    indices = [row.get("output_point_index") for row in rows if isinstance(row, dict)]
    if indices != list(range(point_count)):
        raise AssemblyError(f"{evidence_path}: B evidence indices are not exact ordered output points")
    xyz_bits = np.ascontiguousarray(cloud.xyz.astype("<f4")).view("<u4").reshape((-1, 3))
    evidence_bits = np.asarray([row.get("xyz_f32_bits") for row in rows], dtype=np.uint32)
    if evidence_bits.shape != xyz_bits.shape or not np.array_equal(evidence_bits, xyz_bits):
        raise AssemblyError(f"{evidence_path}: B evidence XYZ/order is not bit-exact with output PLY")

    source_records = evidence.get("source_birth_evidence")
    if not isinstance(source_records, list) or not source_records:
        raise AssemblyError(f"{evidence_path}: source birth-evidence bindings missing")
    source_rows: list[list[dict]] = []
    for source_record in source_records:
        if not isinstance(source_record, dict) or not isinstance(source_record.get("path"), str):
            raise AssemblyError(f"{evidence_path}: malformed source birth-evidence binding")
        source_path = _resolve_manifest_path(evidence_path, source_record["path"])
        if not source_path.is_file() or sha256_file(source_path) != source_record.get("sha256"):
            raise AssemblyError(f"{evidence_path}: source birth-evidence path/SHA mismatch")
        parsed_rows = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        source_rows.append(parsed_rows)

    seen_source_rows: set[tuple[int, int]] = set()
    for row in rows:
        source_file_index = row.get("source_file_index")
        source_row_index = row.get("source_row_index")
        if not isinstance(source_file_index, int) or not isinstance(source_row_index, int):
            raise AssemblyError(f"{evidence_path}: source row mapping missing")
        if source_file_index < 0 or source_file_index >= len(source_rows):
            raise AssemblyError(f"{evidence_path}: source file index out of range")
        if source_row_index < 0 or source_row_index >= len(source_rows[source_file_index]):
            raise AssemblyError(f"{evidence_path}: source row index out of range")
        key = (source_file_index, source_row_index)
        if key in seen_source_rows:
            raise AssemblyError(f"{evidence_path}: duplicate source birth row mapping")
        seen_source_rows.add(key)
        source_zncc = source_rows[source_file_index][source_row_index].get("zncc_median")
        if not isinstance(source_zncc, (int, float)) or not math.isclose(
            float(row.get("zncc_median")), float(source_zncc), abs_tol=1e-12
        ):
            raise AssemblyError(f"{evidence_path}: retained ZNCC does not match source birth evidence")

    zncc_values = np.asarray([row.get("zncc_median") for row in rows], dtype=np.float64)
    residual_values = np.asarray([row.get("abs_plane_residual_m") for row in rows], dtype=np.float64)
    if not np.all(np.isfinite(zncc_values)) or not np.all(np.isfinite(residual_values)):
        raise AssemblyError(f"{evidence_path}: B evidence contains non-finite values")
    if np.any(zncc_values < -1) or np.any(zncc_values > 1) or np.any(residual_values < 0):
        raise AssemblyError(f"{evidence_path}: B evidence values outside physical bounds")
    recomputed_residuals = []
    for index, row in enumerate(rows):
        normal = np.asarray(row.get("plane_normal_output_gauge"), dtype=np.float64)
        plane_value = row.get("plane_value_output_gauge")
        if normal.shape != (3,) or not np.all(np.isfinite(normal)) or not isinstance(plane_value, (int, float)):
            raise AssemblyError(f"{evidence_path}: output-gauge plane equation missing")
        normal_norm = float(np.linalg.norm(normal))
        if not math.isclose(normal_norm, 1.0, abs_tol=1e-6):
            raise AssemblyError(f"{evidence_path}: plane normal is not unit length")
        recomputed = abs(float(np.dot(normal, cloud.xyz[index]) - float(plane_value)))
        if not math.isclose(recomputed, float(residual_values[index]), abs_tol=1e-7):
            raise AssemblyError(f"{evidence_path}: plane residual does not match output XYZ")
        recomputed_residuals.append(recomputed)
    actual_median = float(np.median(zncc_values))
    actual_offplane = float(np.max(recomputed_residuals))
    if not math.isclose(float(zncc), actual_median, abs_tol=1e-12):
        raise AssemblyError(f"{path}: B reported ZNCC median does not match retained evidence")
    if not math.isclose(float(offplane), actual_offplane, abs_tol=1e-12):
        raise AssemblyError(f"{path}: B reported off-plane maximum does not match retained evidence")


def _validate_d_certificate(
    document: dict,
    path: Path,
    capture_name: str,
    ghost_sha: str,
    floor_hashes: Sequence[str],
    wall_hashes: Sequence[str],
    d_hashes: Sequence[str],
    floor_gauges: Sequence[str],
    wall_gauges: Sequence[str],
    d_gauges: Sequence[str],
    inventory_path: Path,
    d_point_counts: Sequence[int],
    c_backend: Mapping,
) -> dict:
    if document.get("schema") != "pw_d_final_stack_certificate_v1" or document.get("status") != "PASS":
        raise AssemblyError(f"{path}: D final-stack certificate schema/status invalid")
    if document.get("commercial_clean") is not True or document.get("recomputed_for_final_stack") is not True:
        raise AssemblyError(f"{path}: D is not certified commercial-clean and recomputed for this stack")

    exact_record = document.get("exact_certificate") or document.get("exact_execution")
    if not isinstance(exact_record, dict) or not isinstance(exact_record.get("path"), str):
        raise AssemblyError(f"{path}: normalized exact D certificate binding missing")
    exact_path = _resolve_manifest_path(path, exact_record["path"])
    if not exact_path.is_file() or sha256_file(exact_path) != exact_record.get("sha256"):
        raise AssemblyError(f"{path}: normalized exact D certificate path/SHA mismatch")
    exact = json.loads(exact_path.read_text(encoding="utf-8"))
    if exact.get("schema") != "pw_d_exact_final_input_certificate_v1" or not str(exact.get("status", "")).startswith("PASS"):
        raise AssemblyError(f"{exact_path}: exact D certificate schema/status invalid")
    if exact.get("capture") != capture_name:
        raise AssemblyError(f"{exact_path}: exact D capture identity mismatch")
    clean = exact.get("commercial_clean")
    if not isinstance(clean, dict) or any(
        clean.get(key) is not False
        for key in (
            "forbidden_matcher_outputs_consumed",
            "loftr_consumed",
            "scannet_consumed",
            "model_weights_consumed",
        )
    ):
        raise AssemblyError(f"{exact_path}: exact D commercial-clean fields are not all false")
    exact_execution = exact.get("execution")
    if not isinstance(exact_execution, dict) or exact_execution.get("final_births") != sum(d_point_counts):
        raise AssemblyError(f"{exact_path}: exact D birth count does not match D PLY")
    parity = exact_execution.get("scheduler_parity")
    if not isinstance(parity, dict) or parity.get("exact") is not True or any(
        parity.get(key) != 0
        for key in (
            "floor_mask_mismatches",
            "product_birth_mask_mismatches",
            "structural_mask_mismatches",
            "wall_mask_mismatches",
        )
    ):
        raise AssemblyError(f"{exact_path}: exact D scheduler parity is not zero-mismatch")
    native_record = (exact.get("inputs") or {}).get("native_library")
    if not isinstance(native_record, dict) or not isinstance(native_record.get("path"), str):
        raise AssemblyError(f"{exact_path}: exact D native backend binding missing")
    native_path = _resolve_manifest_path(exact_path, native_record["path"])
    if not native_path.is_file() or sha256_file(native_path) != native_record.get("sha256"):
        raise AssemblyError(f"{exact_path}: exact D native backend path/SHA mismatch")
    c_artifact_sha = ((c_backend.get("artifact") or {}).get("sha256")) if isinstance(c_backend, Mapping) else None
    if c_artifact_sha != native_record.get("sha256"):
        raise AssemblyError(f"{exact_path}: D native backend differs from certified C backend")
    exact_outputs = exact.get("outputs") or {}
    metric_output = exact_outputs.get("d_metric_gauge")
    if not isinstance(metric_output, dict) or metric_output.get("point_count") != sum(d_point_counts):
        raise AssemblyError(f"{exact_path}: exact D metric output/count missing")
    metric_output_path = _resolve_manifest_path(exact_path, str(metric_output.get("path")))
    if not metric_output_path.is_file() or sha256_file(metric_output_path) != metric_output.get("sha256"):
        raise AssemblyError(f"{exact_path}: exact D metric output path/SHA mismatch")
    completeness = document.get("asset_completeness")
    if completeness not in {"full", "partial"}:
        raise AssemblyError(f"{path}: D asset_completeness must be full or partial")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("schema") != "pw_d_asset_inventory_v1" or inventory.get("capture_name") != capture_name:
        raise AssemblyError(f"{inventory_path}: invalid D asset inventory identity")
    total = inventory.get("total_count")
    available = inventory.get("available_count")
    missing = inventory.get("missing_inputs")
    coverage = inventory.get("coverage_fraction")
    if not isinstance(total, int) or not isinstance(available, int) or total <= 0 or not isinstance(missing, list):
        raise AssemblyError(f"{inventory_path}: malformed D asset counts/list")
    if any(not isinstance(item, dict) or set(item) != {"id", "path"} for item in missing):
        raise AssemblyError(f"{inventory_path}: each D missing input must contain exact id/path")
    identities = [(str(item["id"]), str(item["path"])) for item in missing]
    if len(set(identities)) != len(identities) or available + len(missing) != total:
        raise AssemblyError(f"{inventory_path}: D missing list/counts are inconsistent")
    expected_coverage = available / total
    if not isinstance(coverage, (int, float)) or not math.isclose(float(coverage), expected_coverage, abs_tol=1e-12):
        raise AssemblyError(f"{inventory_path}: D coverage fraction is inconsistent")
    if completeness == "full" and (missing or available != total):
        raise AssemblyError(f"{path}: D claims full assets but inventory is partial")
    if completeness == "partial" and (capture_name not in {"cap40", "cap50", "cap51"} or not missing):
        raise AssemblyError(f"{path}: historical partial D is only valid for cap40/50/51 with exact missing inputs")
    if document.get("asset_inventory_sha256") != sha256_file(inventory_path):
        raise AssemblyError(f"{path}: D certificate does not bind the exact asset inventory")
    expected_bindings = {
        "ghost_gated_sparse_sha256": ghost_sha,
        "b_floor_sha256": list(floor_hashes),
        "b_wall_sha256": list(wall_hashes),
        "d_cloud_sha256": list(d_hashes),
        "gauges": {
            "ghost_gated_sparse": "metric_replay",
            "b_floor": list(floor_gauges),
            "b_wall": list(wall_gauges),
            "d_cloud": list(d_gauges),
        },
    }
    if document.get("bindings") != expected_bindings:
        raise AssemblyError(f"{path}: D structured input bindings do not match this exact final stack")
    if all(gauge == "metric_replay" for gauge in d_gauges):
        if list(d_hashes) != [metric_output.get("sha256")]:
            raise AssemblyError(f"{path}: D metric layer does not match exact execution output")
    elif all(gauge == "device_raw" for gauge in d_gauges):
        raw_transform_record = document.get("raw_transform")
        if not isinstance(raw_transform_record, dict) or not isinstance(raw_transform_record.get("path"), str):
            raise AssemblyError(f"{path}: raw D requires a bound metric-to-raw transform manifest")
        raw_transform_path = _resolve_manifest_path(path, raw_transform_record["path"])
        if not raw_transform_path.is_file() or sha256_file(raw_transform_path) != raw_transform_record.get("sha256"):
            raise AssemblyError(f"{path}: D raw transform manifest path/SHA mismatch")
        raw_transform = json.loads(raw_transform_path.read_text(encoding="utf-8"))
        if raw_transform.get("schema") != "pw_d_and_ghost_metric_to_device_raw_v1":
            raise AssemblyError(f"{raw_transform_path}: wrong raw D transform schema")
        if ((raw_transform.get("inputs") or {}).get("d_metric") or {}).get("sha256") != metric_output.get("sha256"):
            raise AssemblyError(f"{raw_transform_path}: raw transform does not bind exact metric D")
        if list(d_hashes) != [((raw_transform.get("outputs") or {}).get("d_raw") or {}).get("sha256")]:
            raise AssemblyError(f"{raw_transform_path}: raw transform output does not match D layer")
    else:
        raise AssemblyError(f"{path}: mixed D gauges are not supported by one exact execution certificate")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "schema": document["schema"],
        "status": document["status"],
        "commercial_clean": True,
        "recomputed_for_final_stack": True,
        "asset_completeness": completeness,
        "missing_inputs": missing or [],
        "asset_total_count": total,
        "asset_available_count": available,
        "coverage_fraction": expected_coverage,
        "asset_inventory": {"path": str(inventory_path.resolve()), "sha256": sha256_file(inventory_path)},
        "exact_certificate": {"path": str(exact_path.resolve()), "sha256": sha256_file(exact_path)},
        "bindings": expected_bindings,
    }


def _validate_registration_exception(
    document: dict,
    path: Path,
    replay_registered: int,
    replay_total: int,
    replay_unregistered_frame_ids: Sequence[str],
    ledger_total: int,
) -> dict:
    expected = {
        "schema": "pw_cap40_registration_exception_v1",
        "status": "HISTORICAL_INPUT_EXCEPTION",
        "capture_name": "cap40",
        "replay_registered": replay_registered,
        "replay_pose_rows": replay_total,
        "ledger_frame_count": ledger_total,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise AssemblyError(f"{path}: cap40 exception field {key} mismatch")
    declared = document.get("unregistered_frame_ids")
    actual = sorted((str(value) for value in replay_unregistered_frame_ids), key=lambda value: (len(value), value))
    required_cap40 = ["79", "80", "81", "82"]
    if declared != required_cap40 or actual != required_cap40:
        raise AssemblyError(
            f"{path}: cap40 exception must exactly match replay registered=false IDs {required_cap40}; "
            f"declared={declared}, replay={actual}"
        )
    if ledger_total - replay_registered != len(actual):
        raise AssemblyError(f"{path}: cap40 unregistered count is inconsistent")
    return {**expected, "unregistered_frame_ids": declared, "sha256": sha256_file(path)}


def _json_write(path: Path, document: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def assemble(args: argparse.Namespace) -> dict:
    source_specs = [
        ("device_sparse", Path(args.device_sparse)),
        ("device_meta", Path(args.device_meta)),
        ("ghost_sparse", Path(args.ghost_sparse)),
        ("ghost_poses", Path(args.ghost_poses)),
    ]
    for name, values in (("b_floor", args.b_floor), ("b_wall", args.b_wall), ("d", args.d_cloud)):
        source_specs.extend((name, Path(value)) for value in values)
    if args.c_backend_json:
        source_specs.append(("c_backend", Path(args.c_backend_json)))
    if args.replay_ledger:
        source_specs.append(("replay_ledger", Path(args.replay_ledger)))
    if args.replay_to_metric_manifest:
        source_specs.append(("replay_to_metric_manifest", Path(args.replay_to_metric_manifest)))
    if args.metric_to_raw_manifest:
        source_specs.append(("metric_to_raw_manifest", Path(args.metric_to_raw_manifest)))
    for name, values in (
        ("ghost_provenance", [args.ghost_provenance_json] if args.ghost_provenance_json else []),
        ("b_floor_provenance", args.b_floor_provenance_json),
        ("b_wall_provenance", args.b_wall_provenance_json),
        ("d_certificate", [args.d_certificate_json] if args.d_certificate_json else []),
        ("d_asset_inventory", [args.d_asset_inventory_json] if args.d_asset_inventory_json else []),
        (
            "registration_exception",
            [args.registration_exception_json] if args.registration_exception_json else [],
        ),
    ):
        source_specs.extend((name, Path(value)) for value in values)
    missing_inputs = [
        {"layer": name, "path": str(path.resolve())} for name, path in source_specs if not path.is_file()
    ]
    required_absent = []
    if args.require_b_floor and not args.b_floor:
        required_absent.append("b_floor")
    if args.require_b_wall and not args.b_wall:
        required_absent.append("b_wall")
    if args.require_d and not args.d_cloud:
        required_absent.append("d")
    if args.strict_final:
        if args.review_classification != "STRICT_FULL":
            required_absent.append("review_classification_STRICT_FULL")
        if not args.b_floor:
            required_absent.append("b_floor")
        if not args.b_wall:
            required_absent.append("b_wall")
        if not args.d_cloud:
            required_absent.append("d")
        if not args.ghost_provenance_json:
            required_absent.append("ghost_provenance")
        if len(args.b_floor_provenance_json) != len(args.b_floor):
            required_absent.append("b_floor_provenance_one_per_cloud")
        if len(args.b_wall_provenance_json) != len(args.b_wall):
            required_absent.append("b_wall_provenance_one_per_cloud")
        if not args.d_certificate_json:
            required_absent.append("d_certificate")
        if not args.d_asset_inventory_json:
            required_absent.append("d_asset_inventory")
        if not args.c_backend_json or args.c_backend:
            required_absent.append("c_backend_verified_json_only")
        if args.expected_registered is None or args.expected_frame_count is None:
            required_absent.append("expected_registration_counts")
        if not args.replay_ledger:
            required_absent.append("replay_ledger")
        if bool(args.replay_to_metric_manifest) != bool(args.metric_to_raw_manifest):
            required_absent.append("complete_two_manifest_sim3_chain")
        if args.capture_name == "cap40" and not args.registration_exception_json:
            required_absent.append("cap40_registration_exception")
        if args.capture_name != "cap40" and args.registration_exception_json:
            required_absent.append("registration_exception_only_allowed_for_cap40")
    if missing_inputs or required_absent:
        manifest = {
            "schema": TOOL_SCHEMA,
            "status": "input_error",
            "missing_inputs": missing_inputs,
            "required_layers_not_declared": required_absent,
        }
        _json_write(Path(args.output_manifest), manifest)
        raise AssemblyError(f"missing inputs={missing_inputs}; required layers absent={required_absent}")

    floor_gauges = _validate_gauge_vector(args.b_floor, args.b_floor_gauge, "B floor")
    wall_gauges = _validate_gauge_vector(args.b_wall, args.b_wall_gauge, "B wall")
    d_gauges = _validate_gauge_vector(args.d_cloud, args.d_cloud_gauge, "D")
    b_floor_hashes = [sha256_file(Path(path)) for path in args.b_floor]
    b_wall_hashes = [sha256_file(Path(path)) for path in args.b_wall]
    d_hashes = [sha256_file(Path(path)) for path in args.d_cloud]

    ghost_env = _parse_env(args.ghost_env, args.strict_final)
    c_backend = _c_backend_identity(args.c_backend, Path(args.c_backend_json) if args.c_backend_json else None)
    device_sparse_path = Path(args.device_sparse)
    device_meta_path = Path(args.device_meta)
    ghost_sparse_path = Path(args.ghost_sparse)
    ghost_poses_path = Path(args.ghost_poses)

    # Read the original only to certify its identity/count.  Its points are intentionally excluded.
    device_sparse = read_rgb_ply(device_sparse_path)
    ghost_sparse = read_rgb_ply(ghost_sparse_path)
    device_centres, device_registered, device_total = read_device_centres(
        device_meta_path, args.device_translation
    )
    (
        replay_centres,
        replay_registered,
        replay_total,
        replay_explicit_unregistered_frame_ids,
        replay_pose_row_ids,
    ) = read_replay_centres(ghost_poses_path, args.replay_translation)
    ledger_frame_ids = read_replay_ledger_ids(Path(args.replay_ledger)) if args.replay_ledger else replay_pose_row_ids
    ledger_set = set(ledger_frame_ids)
    pose_row_set = set(replay_pose_row_ids)
    pose_extra_vs_ledger = sorted(pose_row_set - ledger_set, key=lambda value: (len(value), value))
    if pose_extra_vs_ledger:
        raise AssemblyError(f"pose CSV has frame IDs absent from immutable replay ledger: {pose_extra_vs_ledger}")
    replay_unregistered_frame_ids = sorted(
        ledger_set - set(replay_centres), key=lambda value: (len(value), value)
    )
    ledger_total = len(ledger_frame_ids)
    overlap_ids = sorted(set(device_centres) & set(replay_centres), key=lambda value: (len(value), value))
    if len(overlap_ids) < 3:
        raise AssemblyError(f"only {len(overlap_ids)} overlapping registered frames")
    source = np.vstack([replay_centres[frame] for frame in overlap_ids])
    target = np.vstack([device_centres[frame] for frame in overlap_ids])
    pose_transform, inliers, pose_residual = robust_sim3(source, target)
    pose_residual["inlier_fraction"] = float(pose_residual["inlier_count"]) / float(
        pose_residual["overlap_count"]
    )
    pose_residual["p95_source_metric_units"] = float(pose_residual["p95_inliers"]) / pose_transform.scale
    pose_residual["rmse_source_metric_units"] = float(pose_residual["rmse_inliers"]) / pose_transform.scale
    pose_residual["max_source_metric_units"] = float(pose_residual["max_inliers"]) / pose_transform.scale
    transform = pose_transform
    residual = pose_residual
    sim3_evidence: dict[str, object] = {"kind": "robust_overlapping_camera_centres"}
    if args.replay_to_metric_manifest and args.metric_to_raw_manifest:
        transform, sim3_evidence, residual = load_certified_chained_sim3(
            Path(args.replay_to_metric_manifest),
            Path(args.metric_to_raw_manifest),
            ghost_sparse_path,
            ghost_sparse,
        )
    sim3_inlier_fraction = float(residual["inlier_count"]) / float(residual["overlap_count"])
    # Target coordinates may be the historical device/raw gauge (cap41 scale ~30),
    # not metres. Divide target-gauge residuals by Sim3 scale before applying the
    # metre-quality gate; retain both values in the manifest.
    if args.strict_final:
        if sim3_inlier_fraction < STRICT_MIN_SIM3_INLIER_FRACTION:
            raise AssemblyError(
                f"strict FULL Sim3 inlier fraction {sim3_inlier_fraction:.6f} < {STRICT_MIN_SIM3_INLIER_FRACTION}"
            )
        if float(residual["p95_source_metric_units"]) > STRICT_MAX_SIM3_P95_M:
            raise AssemblyError(
                f"strict FULL Sim3 normalized p95 {residual['p95_source_metric_units']:.6f}m "
                f"> {STRICT_MAX_SIM3_P95_M}m"
            )

    ghost_aligned = Cloud(transform.apply(ghost_sparse.xyz), ghost_sparse.rgb.copy())
    device_baseline_alignment: dict[str, object] = {"status": "NOT_CHECKED_NON_STRICT"}
    if args.strict_final:
        device_baseline_alignment = _device_baseline_alignment_stats(
            device_sparse, ghost_aligned, transform.scale
        )
        try:
            _validate_device_baseline_alignment(device_baseline_alignment)
        except AssemblyError as error:
            device_baseline_alignment["status"] = "REJECTED_GEOMETRY_MISMATCH"
            _json_write(
                Path(args.output_manifest),
                {
                    "schema": TOOL_SCHEMA,
                    "status": "rejected_device_baseline_geometry",
                    "capture_name": args.capture_name,
                    "reason": str(error),
                    "device_baseline_geometry_alignment": device_baseline_alignment,
                    "device_original_sparse": {
                        "path": str(device_sparse_path.resolve()),
                        "point_count": int(len(device_sparse.xyz)),
                        "sha256": sha256_file(device_sparse_path),
                    },
                    "rejected_ghost_sparse": {
                        "path": str(ghost_sparse_path.resolve()),
                        "point_count": int(len(ghost_sparse.xyz)),
                        "sha256": sha256_file(ghost_sparse_path),
                        "transform_evidence": sim3_evidence,
                    },
                    "strict_thresholds": {
                        "bbox_diagonal_ratio": [
                            STRICT_BASELINE_DIAGONAL_RATIO_MIN,
                            STRICT_BASELINE_DIAGONAL_RATIO_MAX,
                        ],
                        "minimum_within_3cm_fraction_each_direction": STRICT_BASELINE_MIN_WITHIN_3CM_FRACTION,
                        "maximum_median_nn_m_each_direction": STRICT_BASELINE_MAX_MEDIAN_NN_M,
                        "maximum_p90_nn_m_each_direction": STRICT_BASELINE_MAX_P90_NN_M,
                    },
                },
            )
            raise
        device_baseline_alignment["status"] = "PASS"

        c_document = json.loads(Path(args.c_backend_json).read_text(encoding="utf-8"))
        c_backend = _validate_c_backend_certificate(
            c_document,
            Path(args.c_backend_json),
            {
                "known_plane_b_floor": b_floor_hashes,
                "known_plane_b_wall": b_wall_hashes,
            },
        )
    clouds = [ghost_aligned]
    offset = 0
    layer_records = [
        _layer_record(
            "ghost_gated_sparse",
            ghost_sparse_path,
            ghost_sparse,
            ghost_aligned,
            offset,
            "metric_replay",
            True,
        )
    ]
    offset += len(ghost_aligned.xyz)
    for name, paths, gauges in (
        ("b_floor", args.b_floor, floor_gauges),
        ("b_wall", args.b_wall, wall_gauges),
        ("d", args.d_cloud, d_gauges),
    ):
        for index, (value, gauge) in enumerate(zip(paths, gauges)):
            path = Path(value)
            cloud = read_rgb_ply(path)
            assembled = Cloud(
                transform.apply(cloud.xyz) if gauge == "metric_replay" else cloud.xyz.copy(),
                cloud.rgb.copy(),
            )
            clouds.append(assembled)
            layer_records.append(
                _layer_record(
                    f"{name}[{index}]",
                    path,
                    cloud,
                    assembled,
                    offset,
                    gauge,
                    gauge == "metric_replay",
                )
            )
            offset += len(assembled.xyz)

    provenance: dict[str, object] = {}
    if args.ghost_provenance_json:
        ghost_document, ghost_record = _load_bound_certificate(
            Path(args.ghost_provenance_json), [sha256_file(ghost_sparse_path)], "ghost"
        )
        _validate_ghost_provenance(
            ghost_document,
            ghost_sparse,
            Path(args.ghost_provenance_json),
            sha256_file(ghost_sparse_path),
        )
        provenance["ghost_gated_sparse"] = ghost_record
    if args.b_floor_provenance_json:
        records = []
        for cloud_path, certificate_path, gauge in zip(
            args.b_floor, args.b_floor_provenance_json, floor_gauges
        ):
            document, record = _load_bound_certificate(
                Path(certificate_path), [sha256_file(Path(cloud_path))], "B floor"
            )
            _validate_b_provenance(
                document,
                Path(certificate_path),
                read_rgb_ply(Path(cloud_path)),
                sha256_file(Path(cloud_path)),
                gauge,
            )
            records.append(record)
        provenance["b_floor"] = records
    if args.b_wall_provenance_json:
        records = []
        for cloud_path, certificate_path, gauge in zip(
            args.b_wall, args.b_wall_provenance_json, wall_gauges
        ):
            document, record = _load_bound_certificate(
                Path(certificate_path), [sha256_file(Path(cloud_path))], "B wall"
            )
            _validate_b_provenance(
                document,
                Path(certificate_path),
                read_rgb_ply(Path(cloud_path)),
                sha256_file(Path(cloud_path)),
                gauge,
            )
            records.append(record)
        provenance["b_wall"] = records
    if args.d_certificate_json:
        d_document = json.loads(Path(args.d_certificate_json).read_text(encoding="utf-8"))
        d_record = _validate_d_certificate(
            d_document,
            Path(args.d_certificate_json),
            args.capture_name,
            sha256_file(ghost_sparse_path),
            b_floor_hashes,
            b_wall_hashes,
            d_hashes,
            floor_gauges,
            wall_gauges,
            d_gauges,
            Path(args.d_asset_inventory_json),
            [len(read_rgb_ply(Path(value)).xyz) for value in args.d_cloud],
            c_backend,
        )
        provenance["d_final_stack_certificate"] = d_record

    if args.expected_registered is not None and replay_registered != args.expected_registered:
        raise AssemblyError(
            f"registered frame mismatch: replay={replay_registered}, expected={args.expected_registered}"
        )
    effective_frame_count = ledger_total if args.replay_ledger else replay_total
    if args.expected_frame_count is not None and effective_frame_count != args.expected_frame_count:
        raise AssemblyError(
            f"frame count mismatch: immutable ledger={effective_frame_count}, expected={args.expected_frame_count}"
        )

    registration_verdict: dict[str, object]
    if args.strict_final and args.capture_name != "cap40":
        if (
            replay_registered != ledger_total
            or args.expected_registered != args.expected_frame_count
            or pose_row_set != ledger_set
        ):
            raise AssemblyError(
                f"{args.capture_name} strict FULL requires pose IDs exactly equal immutable ledger IDs; "
                f"registered={replay_registered}/{ledger_total}, pose_rows={replay_total}"
            )
        registration_verdict = {"status": "PASS_100_PERCENT", "capture_name": args.capture_name}
    elif args.strict_final:
        exception_document = json.loads(Path(args.registration_exception_json).read_text(encoding="utf-8"))
        registration_verdict = _validate_registration_exception(
            exception_document,
            Path(args.registration_exception_json),
            replay_registered,
            replay_total,
            replay_unregistered_frame_ids,
            ledger_total,
        )
    else:
        registration_verdict = {"status": "RECORDED_NOT_STRICT", "capture_name": args.capture_name}

    output_path = Path(args.output_ply)
    output_sha = write_rgb_ply(output_path, clouds)
    layer_counts = {
        key: int(sum(record["point_count"] for record in layer_records if record["name"].split("[")[0] == key))
        for key in ("ghost_gated_sparse", "b_floor", "b_wall", "d")
    }
    manifest = {
        "schema": TOOL_SCHEMA,
        "status": "ok",
        "review_classification": args.review_classification,
        "known_limitations": list(args.known_limitation),
        "assembly_order": [record["name"] for record in layer_records],
        "old_device_sparse_included": False,
        "missing_inputs": [],
        "strict_final": bool(args.strict_final),
        "ghost_environment": ghost_env,
        "registration": {
            "device_registered": device_registered,
            "device_pose_rows": device_total,
            "replay_registered": replay_registered,
            "replay_pose_rows": replay_total,
            "replay_explicit_unregistered_frame_ids": replay_explicit_unregistered_frame_ids,
            "immutable_ledger_frame_count": ledger_total,
            "immutable_ledger_path": str(Path(args.replay_ledger).resolve()) if args.replay_ledger else None,
            "immutable_ledger_sha256": sha256_file(Path(args.replay_ledger)) if args.replay_ledger else None,
            "replay_unregistered_frame_ids": replay_unregistered_frame_ids,
            "overlap_registered": len(overlap_ids),
            "overlap_inlier_frame_ids": [frame for frame, keep in zip(overlap_ids, inliers) if keep],
            "verdict": registration_verdict,
        },
        "sim3_replay_to_device_raw": {
            "scale": transform.scale,
            "rotation_row_major": transform.rotation.tolist(),
            "translation": transform.translation.tolist(),
            "residual": residual,
            "evidence": sim3_evidence,
            "pose_fit_diagnostic_not_selected": pose_residual if sim3_evidence["kind"] != "robust_overlapping_camera_centres" else None,
            "device_translation_convention": args.device_translation,
            "replay_translation_convention": args.replay_translation,
        },
        "device_baseline_geometry_alignment": device_baseline_alignment,
        "c_backend_identity": c_backend,
        "provenance": provenance,
        "device_original_sparse": {
            "path": str(device_sparse_path.resolve()),
            "point_count": int(len(device_sparse.xyz)),
            "sha256": sha256_file(device_sparse_path),
            "meta_path": str(device_meta_path.resolve()),
            "meta_sha256": sha256_file(device_meta_path),
            "role": "gauge_and_identity_only_not_assembled",
        },
        "layers": layer_records,
        "layer_point_counts": layer_counts,
        "output": {
            "path": str(output_path.resolve()),
            "point_count": int(sum(layer_counts.values())),
            "sha256": output_sha,
            "encoding": "binary_little_endian xyz_float32_rgb_uint8",
        },
    }
    _json_write(Path(args.output_manifest), manifest)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-sparse", required=True)
    parser.add_argument("--device-meta", required=True)
    parser.add_argument("--ghost-sparse", required=True)
    parser.add_argument("--ghost-poses", required=True)
    parser.add_argument("--replay-ledger")
    parser.add_argument("--replay-to-metric-manifest")
    parser.add_argument("--metric-to-raw-manifest")
    parser.add_argument("--b-floor", action="append", default=[])
    parser.add_argument("--b-floor-gauge", action="append", default=[], choices=("metric_replay", "device_raw"))
    parser.add_argument("--b-wall", action="append", default=[])
    parser.add_argument("--b-wall-gauge", action="append", default=[], choices=("metric_replay", "device_raw"))
    parser.add_argument("--d-cloud", action="append", default=[])
    parser.add_argument("--d-cloud-gauge", action="append", default=[], choices=("metric_replay", "device_raw"))
    parser.add_argument("--require-b-floor", action="store_true")
    parser.add_argument("--require-b-wall", action="store_true")
    parser.add_argument("--require-d", action="store_true")
    parser.add_argument("--strict-final", action="store_true")
    parser.add_argument(
        "--review-classification",
        choices=("unclassified", "ALL_ALGORITHMS_RESEARCH_CANDIDATE", "STRICT_FULL"),
        default="unclassified",
    )
    parser.add_argument("--known-limitation", action="append", default=[])
    parser.add_argument("--capture-name", choices=("cap40", "cap41", "cap50", "cap51"), required=True)
    parser.add_argument("--ghost-provenance-json")
    parser.add_argument("--b-floor-provenance-json", action="append", default=[])
    parser.add_argument("--b-wall-provenance-json", action="append", default=[])
    parser.add_argument("--d-certificate-json")
    parser.add_argument("--d-asset-inventory-json")
    parser.add_argument("--registration-exception-json")
    parser.add_argument("--ghost-env", action="append", default=[], help="KEY=VALUE; strict FULL requires exact owner env")
    parser.add_argument("--c-backend")
    parser.add_argument("--c-backend-json")
    parser.add_argument("--device-translation", choices=("tvec", "camera_center"), default="tvec")
    parser.add_argument("--replay-translation", choices=("tvec", "camera_center"), default="tvec")
    parser.add_argument("--expected-registered", type=int)
    parser.add_argument("--expected-frame-count", type=int)
    parser.add_argument("--output-ply", required=True)
    parser.add_argument("--output-manifest", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = assemble(args)
    except (AssemblyError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "ok", "output": manifest["output"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
