#!/usr/bin/env python3
"""Refine stored keypoint positions from multi-view grayscale agreement.

For every verified match, pyramidal Lucas-Kanade alignment proposes a refined
location in both images while starting from the stored match coordinates.  A
keypoint moves only when at least two independent matched views propose a
consistent location.  Match identities, descriptors, frames, and photographs
are never removed.  Two-view geometries must be re-estimated afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pycolmap


def copy_database(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as output_db:
        source_db.backup(output_db)
        output_db.execute("PRAGMA journal_mode=DELETE")
        output_db.commit()


def summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"median": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
    array = np.asarray(values, dtype=np.float64)
    return {
        "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)),
        "p95": float(np.percentile(array, 95)),
        "max": float(np.max(array)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--geometry-db",
        type=Path,
        help=(
            "optional database supplying verified match identities; keypoint "
            "coordinates are always read from --input"
        ),
    )
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--gray-dir", type=Path, required=True)
    parser.add_argument(
        "--jpeg-dir",
        type=Path,
        help="fallback directory for full-resolution JPEGs when .sfm-gray is absent",
    )
    parser.add_argument(
        "--allow-missing-images",
        action="store_true",
        help="leave missing-image keypoints unchanged and skip their pair proposals",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--window", type=int, default=15)
    parser.add_argument("--levels", type=int, default=2)
    parser.add_argument("--max-lk-error", type=float, default=20.0)
    parser.add_argument("--max-pair-shift-px", type=float, default=2.0)
    parser.add_argument("--min-view-support", type=int, default=2)
    parser.add_argument("--consensus-radius-px", type=float, default=0.75)
    parser.add_argument("--max-final-shift-px", type=float, default=2.0)
    args = parser.parse_args()

    if args.stats.exists():
        raise FileExistsError(args.stats)
    ledger = {
        int(row["frameId"]): os.path.basename(row["jpegPath"])
        for line in args.ledger.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    copy_database(args.input, args.output)
    cv2.setNumThreads(1)

    proposals: dict[tuple[int, int], list[np.ndarray]] = defaultdict(list)
    accepted_edges = 0
    attempted_edges = 0
    skipped_missing_edges = 0
    skipped_missing_pairs = 0
    pair_shift: list[float] = []
    with pycolmap.Database.open(args.output) as database:
        images = {int(image.image_id): image for image in database.read_all_images()}
        cameras = {
            image_id: database.read_camera(image.camera_id)
            for image_id, image in images.items()
        }
        keypoints = {
            image_id: np.asarray(database.read_keypoints(image_id), dtype=np.float32)
            for image_id in images
        }
        gray_images: dict[int, np.ndarray] = {}
        missing_image_ids: list[int] = []
        gray_source_counts = {"sfm_gray": 0, "jpeg": 0}
        for image_id in images:
            frame_id = image_id - 1
            if frame_id not in ledger:
                raise RuntimeError(f"missing ledger row for frame {frame_id}")
            gray_name = Path(ledger[frame_id]).with_suffix(".sfm-gray").name
            camera = cameras[image_id]
            gray_path = args.gray_dir / gray_name
            expected_bytes = int(camera.width * camera.height)
            if gray_path.exists():
                if gray_path.stat().st_size != expected_bytes:
                    raise RuntimeError(
                        f"{gray_path} has {gray_path.stat().st_size} bytes, "
                        f"expected {expected_bytes}"
                    )
                gray_images[image_id] = np.memmap(
                    gray_path,
                    dtype=np.uint8,
                    mode="r",
                    shape=(int(camera.height), int(camera.width)),
                )
                gray_source_counts["sfm_gray"] += 1
                continue
            jpeg_path = args.jpeg_dir / ledger[frame_id] if args.jpeg_dir else None
            if jpeg_path is not None and jpeg_path.exists():
                # The capture JPEG stores the raw 3840x2160 sensor raster and
                # EXIF orientation=6 for gallery display.  COLMAP keypoints and
                # intrinsics are expressed in the raw sensor coordinates, so
                # OpenCV must not auto-rotate the pixels while decoding.
                decoded = cv2.imread(
                    str(jpeg_path),
                    cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION,
                )
                if decoded is None:
                    raise RuntimeError(f"failed to decode {jpeg_path}")
                expected_shape = (int(camera.height), int(camera.width))
                if decoded.shape != expected_shape:
                    raise RuntimeError(
                        f"{jpeg_path} has shape {decoded.shape}, "
                        f"expected {expected_shape}"
                    )
                gray_images[image_id] = decoded
                gray_source_counts["jpeg"] += 1
                continue
            if not args.allow_missing_images:
                raise FileNotFoundError(gray_path)
            missing_image_ids.append(image_id)

        if args.geometry_db is None:
            pair_ids, geometries = database.read_two_view_geometries()
        else:
            with pycolmap.Database.open(args.geometry_db) as geometry_database:
                pair_ids, geometries = geometry_database.read_two_view_geometries()
        lk_options = {
            "winSize": (args.window, args.window),
            "maxLevel": args.levels,
            "criteria": (
                cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                30,
                0.01,
            ),
            "flags": cv2.OPTFLOW_USE_INITIAL_FLOW,
            "minEigThreshold": 1e-4,
        }
        for pair_index, (pair_id, geometry) in enumerate(
            zip(pair_ids, geometries, strict=True), start=1
        ):
            matches = np.asarray(geometry.inlier_matches, dtype=np.uint32)
            if len(matches) == 0:
                continue
            image1, image2 = pycolmap.pair_id_to_image_pair(pair_id)
            image1 = int(image1)
            image2 = int(image2)
            if image1 not in gray_images or image2 not in gray_images:
                skipped_missing_pairs += 1
                skipped_missing_edges += len(matches)
                continue
            points1 = keypoints[image1][matches[:, 0], :2][:, None, :]
            points2 = keypoints[image2][matches[:, 1], :2][:, None, :]
            refined2, status12, error12 = cv2.calcOpticalFlowPyrLK(
                gray_images[image1],
                gray_images[image2],
                points1,
                points2.copy(),
                **lk_options,
            )
            refined1, status21, error21 = cv2.calcOpticalFlowPyrLK(
                gray_images[image2],
                gray_images[image1],
                points2,
                points1.copy(),
                **lk_options,
            )
            attempted_edges += len(matches)
            shift1 = np.linalg.norm(refined1[:, 0] - points1[:, 0], axis=1)
            shift2 = np.linalg.norm(refined2[:, 0] - points2[:, 0], axis=1)
            valid = (
                (status12[:, 0] > 0)
                & (status21[:, 0] > 0)
                & np.isfinite(error12[:, 0])
                & np.isfinite(error21[:, 0])
                & (error12[:, 0] <= args.max_lk_error)
                & (error21[:, 0] <= args.max_lk_error)
                & (shift1 <= args.max_pair_shift_px)
                & (shift2 <= args.max_pair_shift_px)
            )
            for match, point1, point2, displacement1, displacement2 in zip(
                matches[valid],
                refined1[valid, 0],
                refined2[valid, 0],
                shift1[valid],
                shift2[valid],
                strict=True,
            ):
                proposals[(image1, int(match[0]))].append(point1.copy())
                proposals[(image2, int(match[1]))].append(point2.copy())
                pair_shift.extend((float(displacement1), float(displacement2)))
            accepted_edges += int(np.count_nonzero(valid))
            if pair_index % 25 == 0 or pair_index == len(pair_ids):
                print(
                    f"LK pair {pair_index}/{len(pair_ids)} "
                    f"accepted_edges={accepted_edges}/{attempted_edges}",
                    flush=True,
                )

        refined_keypoints = 0
        supported_keypoints = 0
        consensus_rejected = 0
        final_shift: list[float] = []
        support_counts: list[int] = []
        for (image_id, keypoint_index), values in proposals.items():
            if len(values) < args.min_view_support:
                continue
            supported_keypoints += 1
            array = np.asarray(values, dtype=np.float64)
            center = np.median(array, axis=0)
            distances = np.linalg.norm(array - center, axis=1)
            consensus = array[distances <= args.consensus_radius_px]
            if len(consensus) < args.min_view_support:
                consensus_rejected += 1
                continue
            center = np.median(consensus, axis=0)
            original = keypoints[image_id][keypoint_index, :2].astype(np.float64)
            displacement = float(np.linalg.norm(center - original))
            if displacement > args.max_final_shift_px:
                consensus_rejected += 1
                continue
            keypoints[image_id][keypoint_index, :2] = center.astype(np.float32)
            refined_keypoints += 1
            final_shift.append(displacement)
            support_counts.append(len(consensus))

        for image_id, values in keypoints.items():
            database.update_keypoints(image_id, values)

    stats = {
        "schema": "pocketworld_multiview_lk_keypoint_refinement_v1",
        "input_db": str(args.input),
        "geometry_db": str(args.geometry_db or args.input),
        "output_db": str(args.output),
        "ledger": str(args.ledger),
        "gray_dir": str(args.gray_dir),
        "images": len(images),
        "images_with_pixels": len(gray_images),
        "missing_image_ids": missing_image_ids,
        "gray_source_counts": gray_source_counts,
        "verified_pairs": len(pair_ids),
        "skipped_missing_pairs": skipped_missing_pairs,
        "skipped_missing_edges": skipped_missing_edges,
        "attempted_match_edges": attempted_edges,
        "accepted_symmetric_lk_edges": accepted_edges,
        "accepted_edge_pct": 100.0 * accepted_edges / max(1, attempted_edges),
        "keypoints_with_any_proposal": len(proposals),
        "keypoints_with_min_view_support": supported_keypoints,
        "consensus_rejected_keypoints": consensus_rejected,
        "refined_keypoints": refined_keypoints,
        "pair_proposal_shift_px": summary(pair_shift),
        "final_keypoint_shift_px": summary(final_shift),
        "accepted_support_count": summary([float(value) for value in support_counts]),
        "parameters": {
            "window": args.window,
            "levels": args.levels,
            "max_lk_error": args.max_lk_error,
            "max_pair_shift_px": args.max_pair_shift_px,
            "min_view_support": args.min_view_support,
            "consensus_radius_px": args.consensus_radius_px,
            "max_final_shift_px": args.max_final_shift_px,
            "opencv_threads": 1,
        },
        "uses_lidar_or_scene_depth": False,
        "deletes_frames_matches_or_points": False,
    }
    args.stats.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
