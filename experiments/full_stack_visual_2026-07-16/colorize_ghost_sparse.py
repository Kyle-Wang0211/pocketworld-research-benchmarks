#!/usr/bin/env python3
"""Colorize a ghost-owner published PLY from its exact COLMAP tracks.

This is deliberately not a spatial color transfer.  The published PLY rows are
first re-derived from the debug model with the exact depth-conflict ownership
gate and checked byte-for-byte against the input XYZ payload.  Every color then
comes only from that point's own registered 2D observations and the fed-frame
ledger's JPEG for the same frame.
"""

from __future__ import annotations

import argparse
import collections
import functools
import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pycolmap
from PIL import Image


PLY_DTYPE = np.dtype([("xyz", "<f4", (3,)), ("rgb", "u1", (3,))])
FRAME_NAME = re.compile(r"^frame_(\d+)\.jpg$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_ply(path: Path) -> tuple[bytes, np.ndarray]:
    payload = path.read_bytes()
    marker = b"end_header\n"
    body_offset = payload.index(marker) + len(marker)
    header = payload[:body_offset]
    vertex_line = next(
        line for line in header.decode("ascii").splitlines()
        if line.startswith("element vertex ")
    )
    count = int(vertex_line.rsplit(" ", 1)[1])
    expected = body_offset + count * PLY_DTYPE.itemsize
    if len(payload) != expected:
        raise RuntimeError(
            f"unsupported PLY payload: size={len(payload)} expected={expected}"
        )
    return header, np.frombuffer(payload, dtype=PLY_DTYPE, offset=body_offset)


def exact_site_key(xy: np.ndarray) -> bytes:
    # ExactSiteKey in aether_sfm_c.cc casts each coordinate to float32 then
    # compares the two bit patterns.
    return np.asarray(xy, dtype="<f4").tobytes()


def triangulation_angle(a: np.ndarray, b: np.ndarray, xyz: np.ndarray) -> float:
    va = xyz - a
    vb = xyz - b
    cosine = float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))
    angle = math.acos(max(-1.0, min(1.0, cosine)))
    return min(angle, math.pi - angle)


@dataclass(frozen=True)
class Candidate:
    point_id: int
    point: object
    xyz: np.ndarray
    error: float
    track_length: int
    max_angle_rad: float


def candidate_compare(a: Candidate, b: Candidate) -> int:
    # AETHER_PUBLISH_DEPTH_OWNER_ERROR_FIRST=1 comparator, including the
    # negative-error sentinel semantics and the source's 1e-12 comparisons.
    if abs(a.error - b.error) > 1e-12:
        return -1 if a.error < b.error else 1
    if a.track_length != b.track_length:
        return -1 if a.track_length > b.track_length else 1
    if abs(a.error - b.error) > 1e-12:
        return -1 if a.error < b.error else 1
    if abs(a.max_angle_rad - b.max_angle_rad) > 1e-12:
        return -1 if a.max_angle_rad > b.max_angle_rad else 1
    return -1 if a.point_id < b.point_id else (1 if a.point_id > b.point_id else 0)


def umeyama_scale(model_centers: np.ndarray, capture_centers: np.ndarray) -> float:
    """Return Eigen::umeyama(model, capture, true)'s uniform scale."""
    model_mean = model_centers.mean(axis=1, keepdims=True)
    capture_mean = capture_centers.mean(axis=1, keepdims=True)
    model_zero = model_centers - model_mean
    capture_zero = capture_centers - capture_mean
    covariance = capture_zero @ model_zero.T / model_centers.shape[1]
    u, singular, vt = np.linalg.svd(covariance)
    signs = np.ones(3, dtype=np.float64)
    if np.linalg.det(u) * np.linalg.det(vt) < 0.0:
        signs[-1] = -1.0
    variance = float(np.sum(model_zero * model_zero) / model_centers.shape[1])
    return float(np.dot(singular, signs) / variance)


def reconstruct_published_points(
    reconstruction: pycolmap.Reconstruction,
    ledger_by_frame: dict[int, dict],
    min_depth_gap_m: float,
) -> tuple[list[Candidate], dict]:
    image_centers = {
        int(image_id): np.asarray(image.projection_center(), dtype=np.float64)
        for image_id, image in reconstruction.images.items()
    }
    candidates: list[Candidate] = []
    for point_id, point in reconstruction.points3D.items():
        xyz = np.asarray(point.xyz, dtype=np.float64)
        centers = [image_centers[int(e.image_id)] for e in point.track.elements]
        max_angle = 0.0
        for i, first in enumerate(centers):
            for second in centers[i + 1:]:
                max_angle = max(
                    max_angle, triangulation_angle(first, second, xyz)
                )
        raw_error = float(point.error)
        error = (
            raw_error
            if math.isfinite(raw_error) and raw_error >= 0.0
            else math.inf
        )
        candidates.append(
            Candidate(
                point_id=int(point_id),
                point=point,
                xyz=xyz,
                error=error,
                track_length=len(point.track.elements),
                max_angle_rad=max_angle,
            )
        )
    candidates.sort(key=functools.cmp_to_key(candidate_compare))
    by_id = {candidate.point_id: candidate for candidate in candidates}

    image_ids = sorted(int(image_id) for image_id in reconstruction.images)
    model_centers = np.stack(
        [image_centers[image_id] for image_id in image_ids], axis=1
    )
    capture_centers = np.stack(
        [
            np.asarray(
                ledger_by_frame[image_id - 1]["arkitCameraCenterWorld"],
                dtype=np.float64,
            )
            for image_id in image_ids
        ],
        axis=1,
    )
    model_to_metric_scale = umeyama_scale(model_centers, capture_centers)

    sites: dict[tuple[int, bytes], list[int]] = collections.defaultdict(list)
    for candidate in candidates:
        for element in candidate.point.track.elements:
            image_id = int(element.image_id)
            point2d = reconstruction.images[image_id].points2D[element.point2D_idx]
            sites[(image_id, exact_site_key(point2d.xy))].append(
                candidate.point_id
            )

    pair_evidence: collections.Counter[tuple[int, int]] = collections.Counter()
    for (image_id, _), members in sites.items():
        if len(members) < 2:
            continue
        pose = reconstruction.images[image_id].cam_from_world()
        depths = {
            point_id: float((pose * by_id[point_id].xyz)[2])
            for point_id in members
        }
        for i, first in enumerate(members):
            first_depth = depths[first]
            if first_depth <= 0.0:
                continue
            for second in members[i + 1:]:
                if first == second:
                    continue
                second_depth = depths[second]
                if second_depth <= 0.0:
                    continue
                if (
                    abs(first_depth - second_depth) * model_to_metric_scale
                    < min_depth_gap_m
                ):
                    continue
                pair_evidence[tuple(sorted((first, second)))] += 1

    conflicts: dict[int, set[int]] = collections.defaultdict(set)
    certified_pairs = 0
    for (first, second), evidence in pair_evidence.items():
        if evidence < 2:
            continue
        conflicts[first].add(second)
        conflicts[second].add(first)
        certified_pairs += 1

    accepted_ids: set[int] = set()
    published: list[Candidate] = []
    for candidate in candidates:
        if any(other in accepted_ids for other in conflicts[candidate.point_id]):
            continue
        accepted_ids.add(candidate.point_id)
        published.append(candidate)
    return published, {
        "internal_points": len(candidates),
        "published_points": len(published),
        "withheld_points": len(candidates) - len(published),
        "exact_image_sites": len(sites),
        "depth_conflict_pairs_with_two_view_proof": certified_pairs,
        "model_to_capture_metric_scale": model_to_metric_scale,
        "minimum_depth_gap_m": min_depth_gap_m,
    }


def bilinear_rgb(image: np.ndarray, x: float, y: float) -> tuple[float, float, float] | None:
    x0 = math.floor(x)
    y0 = math.floor(y)
    x1 = x0 + 1
    y1 = y0 + 1
    height, width = image.shape[:2]
    if x0 < 0 or y0 < 0 or x1 >= width or y1 >= height:
        return None
    dx = x - x0
    dy = y - y0
    w00 = (1.0 - dx) * (1.0 - dy)
    w01 = dx * (1.0 - dy)
    w10 = (1.0 - dx) * dy
    w11 = dx * dy
    rgb = (
        w00 * image[y0, x0].astype(np.float64)
        + w01 * image[y0, x1].astype(np.float64)
        + w10 * image[y1, x0].astype(np.float64)
        + w11 * image[y1, x1].astype(np.float64)
    )
    # Dart stores every sample in Float32List before luma ranking.
    rgb = rgb.astype(np.float32)
    return float(rgb[0]), float(rgb[1]), float(rgb[2])


def representative_sample(samples: list[tuple[float, float, float]]) -> tuple[int, int, int]:
    lumas = [0.299 * r + 0.587 * g + 0.114 * b for r, g, b in samples]
    median = sorted(lumas)[(len(lumas) - 1) >> 1]
    best = 0
    best_distance = math.inf
    for index, luma in enumerate(lumas):
        distance = abs(luma - median)
        if distance < best_distance or (
            distance == best_distance and luma < lumas[best]
        ):
            best = index
            best_distance = distance
    # Uint8List assignment in Dart truncates a positive double toward zero.
    return tuple(max(0, min(255, int(channel))) for channel in samples[best])


def colorize(
    reconstruction: pycolmap.Reconstruction,
    published: list[Candidate],
    ledger_by_frame: dict[int, dict],
    photo_root: Path,
) -> tuple[np.ndarray, dict, list[dict]]:
    samples: list[list[tuple[float, float, float]]] = [
        [] for _ in published
    ]
    by_frame: dict[int, list[tuple[int, float, float]]] = {}
    # Preserve the product's LinkedHashMap insertion order: rows first, then
    # each track's stored element order.
    for row_index, candidate in enumerate(published):
        for element in candidate.point.track.elements:
            image_id = int(element.image_id)
            image = reconstruction.images[image_id]
            match = FRAME_NAME.match(image.name)
            if match is None or int(match.group(1)) != image_id - 1:
                raise RuntimeError(
                    f"non-canonical debug image mapping: {image_id} {image.name}"
                )
            point2d = image.points2D[element.point2D_idx]
            by_frame.setdefault(image_id - 1, []).append(
                (row_index, float(point2d.xy[0]), float(point2d.xy[1]))
            )

    frame_sources: list[dict] = []
    missing_frame_sources: list[dict] = []
    decoded_frames = 0
    sampled_observations = 0
    skipped_observations = 0
    for frame_id, observations in by_frame.items():
        meta = ledger_by_frame[frame_id]
        photo = photo_root / Path(meta["jpegPath"]).name
        if not photo.is_file():
            missing_frame_sources.append(
                {
                    "image_id": frame_id + 1,
                    "frame_id": frame_id,
                    "debug_image_name": f"frame_{frame_id:06d}.jpg",
                    "expected_jpeg_path": str(photo),
                    "ledger_jpeg_path": meta["jpegPath"],
                    "track_observations": len(observations),
                }
            )
            continue
        with Image.open(photo) as opened:
            exif_orientation = opened.getexif().get(274)
            # Intentionally do not exif-transpose.  Fed-gray XY and the encoded
            # JPEG raster share the same 3840x2160 sensor orientation.
            rgb = np.asarray(opened.convert("RGB"), dtype=np.uint8)
        height, width = rgb.shape[:2]
        gray_width = int(meta["grayW"])
        gray_height = int(meta["grayH"])
        scale_x = width / gray_width
        scale_y = height / gray_height
        for row_index, x, y in observations:
            sample = bilinear_rgb(
                rgb, x * scale_x - 0.5, y * scale_y - 0.5
            )
            if sample is None:
                skipped_observations += 1
                continue
            samples[row_index].append(sample)
            sampled_observations += 1
        decoded_frames += 1
        frame_sources.append(
            {
                "image_id": frame_id + 1,
                "frame_id": frame_id,
                "debug_image_name": f"frame_{frame_id:06d}.jpg",
                "jpeg_path": str(photo),
                "jpeg_sha256": sha256(photo),
                "encoded_width": width,
                "encoded_height": height,
                "gray_width": gray_width,
                "gray_height": gray_height,
                "exif_orientation_ignored": exif_orientation,
                "track_observations": len(observations),
            }
        )

    colors = np.empty((len(published), 3), dtype=np.uint8)
    colored = 0
    for index, point_samples in enumerate(samples):
        if point_samples:
            colors[index] = representative_sample(point_samples)
            colored += 1
        else:
            colors[index] = (185, 185, 190)
    stats = {
        "decoded_frames": decoded_frames,
        "frames_referenced_by_tracks": len(by_frame),
        "sampled_observations": sampled_observations,
        "skipped_out_of_bounds_observations": skipped_observations,
        "colored_points": colored,
        "fallback_gray_points": len(published) - colored,
        "nonzero_rgb_points": int(np.any(colors != 0, axis=1).sum()),
        "unique_rgb_values": int(len(np.unique(colors, axis=0))),
        "missing_jpeg_frames": [
            source["frame_id"] for source in missing_frame_sources
        ],
        "missing_jpeg_basenames": [
            Path(source["expected_jpeg_path"]).name
            for source in missing_frame_sources
        ],
    }
    return colors, stats, frame_sources


def observation_identity_sha(published: Iterable[Candidate]) -> str:
    digest = hashlib.sha256()
    for candidate in published:
        digest.update(struct.pack("<Q", candidate.point_id))
        digest.update(struct.pack("<I", len(candidate.point.track.elements)))
        for element in candidate.point.track.elements:
            digest.update(
                struct.pack(
                    "<II", int(element.image_id), int(element.point2D_idx)
                )
            )
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input-ply", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--output-ply", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--frame-sources", type=Path, required=True)
    parser.add_argument("--min-depth-gap-m", type=float, default=0.012)
    args = parser.parse_args()

    ledger_rows = [
        json.loads(line) for line in args.ledger.read_text().splitlines()
        if line.strip()
    ]
    ledger_by_frame = {int(row["frameId"]): row for row in ledger_rows}
    if len(ledger_by_frame) != len(ledger_rows):
        raise RuntimeError("duplicate frameId in ledger")

    reconstruction = pycolmap.Reconstruction(str(args.model_dir))
    missing_ledger_frames = sorted(
        int(image_id) - 1
        for image_id in reconstruction.images
        if int(image_id) - 1 not in ledger_by_frame
    )
    if missing_ledger_frames:
        raise RuntimeError(
            f"debug model images missing from ledger: {missing_ledger_frames}"
        )
    header, input_rows = read_ply(args.input_ply)
    published, gate_stats = reconstruct_published_points(
        reconstruction, ledger_by_frame, args.min_depth_gap_m
    )
    if len(published) != len(input_rows):
        raise RuntimeError(
            f"published count mismatch: model gate={len(published)} "
            f"PLY={len(input_rows)}"
        )
    expected_xyz = np.stack(
        [candidate.xyz.astype("<f4") for candidate in published]
    )
    if expected_xyz.tobytes() != input_rows["xyz"].tobytes():
        bad = np.flatnonzero(
            np.any(expected_xyz.view("<u4") != input_rows["xyz"].view("<u4"), axis=1)
        )
        raise RuntimeError(
            f"published point identity mismatch at {len(bad)} rows; "
            f"first={bad[:10].tolist()}"
        )

    colors, color_stats, frame_sources = colorize(
        reconstruction, published, ledger_by_frame, args.photos
    )
    output_rows = np.empty(len(input_rows), dtype=PLY_DTYPE)
    output_rows["xyz"] = input_rows["xyz"]
    output_rows["rgb"] = colors
    args.output_ply.parent.mkdir(parents=True, exist_ok=True)
    args.output_ply.write_bytes(header + output_rows.tobytes())
    args.frame_sources.write_text(
        json.dumps(frame_sources, indent=2, sort_keys=True) + "\n"
    )

    _, written_rows = read_ply(args.output_ply)
    xyz_preserved = written_rows["xyz"].tobytes() == input_rows["xyz"].tobytes()
    if not xyz_preserved:
        raise RuntimeError("output XYZ payload changed")
    source_registered = sum(
        1 for image in reconstruction.images.values() if image.has_pose
    )
    provenance = {
        "schema": "pocketworld_exact_track_truecolor_v1",
        "method": {
            "point_identity": "exact replay of publish depth-conflict owner; output XYZ byte equality required",
            "color_source": "each published point's own debug-model track only",
            "frame_mapping": "image_id - 1 == ledger.frameId; ledger JPEG basename under immutable local photo root",
            "sampling": "raw encoded JPEG raster, no EXIF transpose; xy*(jpeg/gray)-0.5 bilinear",
            "reduction": "lower-median luma representative real observation; no RGB averaging",
            "nearest_neighbor_color_transfer": False,
        },
        "gate_environment": {
            "AETHER_PUBLISH_GATE": "0",
            "AETHER_PUBLISH_DEPTH_CONFLICT_OWNER": "1",
            "AETHER_PUBLISH_DEPTH_OWNER_ERROR_FIRST": "1",
            "AETHER_EXACT_SITE_OWNER_MIN_DEPTH_M": str(args.min_depth_gap_m),
        },
        "inputs": {
            "model_dir": str(args.model_dir),
            "input_ply": str(args.input_ply),
            "input_ply_sha256": sha256(args.input_ply),
            "points3D_bin_sha256": sha256(args.model_dir / "points3D.bin"),
            "images_bin_sha256": sha256(args.model_dir / "images.bin"),
            "ledger": str(args.ledger),
            "ledger_sha256": sha256(args.ledger),
            "photos": str(args.photos),
        },
        "identity": {
            "registered_images": source_registered,
            "total_images": len(reconstruction.images),
            "ledger_frames": len(ledger_by_frame),
            "xyz_payload_byte_identical": xyz_preserved,
            "published_point_ids_and_observations_sha256": observation_identity_sha(published),
        },
        "gate_stats": gate_stats,
        "color_stats": color_stats,
        "outputs": {
            "ply": str(args.output_ply),
            "ply_sha256": sha256(args.output_ply),
            "frame_sources": str(args.frame_sources),
            "frame_sources_sha256": sha256(args.frame_sources),
        },
    }
    args.provenance.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(provenance, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
