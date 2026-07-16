#!/usr/bin/env python3
"""Diagnose PIL-side patch texture for a focused Dart/GPU boundary result."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


GRAY_WEIGHTS = np.asarray([0.299, 0.587, 0.114], dtype=np.float64)


def largest_consistent_clique(
    ncc: np.ndarray, threshold: float, minimum: int
) -> np.ndarray:
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
        score = float(np.median(sub[np.triu_indices(size, 1)]))
        if size > len(best_indices) or score > best_median:
            best_indices = indices
            best_median = score

    def search(indices: tuple[int, ...], candidates: int) -> None:
        if len(indices) + candidates.bit_count() < max(minimum, len(best_indices)):
            return
        if candidates == 0:
            consider(indices)
            return
        remaining = candidates
        while remaining:
            if len(indices) + remaining.bit_count() < max(
                minimum, len(best_indices)
            ):
                break
            lowest = remaining & -remaining
            vertex = lowest.bit_length() - 1
            search(indices + (vertex,), remaining & neighbors[vertex])
            remaining &= ~lowest

    search((), (1 << count) - 1)
    return np.asarray(best_indices, dtype=np.int32)


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
    top = image[y0, x0].astype(np.float64) * (1.0 - wx[:, None])
    top += image[y0, x1].astype(np.float64) * wx[:, None]
    bottom = image[y1, x0].astype(np.float64) * (1.0 - wx[:, None])
    bottom += image[y1, x1].astype(np.float64) * wx[:, None]
    return top * (1.0 - wy[:, None]) + bottom * wy[:, None]


def patch_offsets(batch: dict) -> np.ndarray:
    values = np.linspace(
        -float(batch["patch_radius_m_by_scale"][0]),
        float(batch["patch_radius_m_by_scale"][0]),
        int(batch["patch_n"]),
    )
    uu, vv = np.meshgrid(values, values, indexing="ij")
    return (
        uu.reshape(-1, 1) * np.asarray(batch["basis_u"], dtype=np.float64)
        + vv.reshape(-1, 1) * np.asarray(batch["basis_v"], dtype=np.float64)
    )


def score_surface(batch: dict, frame_by_id: dict[int, dict]) -> dict:
    point = np.asarray(batch["center_point_xyz"], dtype=np.float64)
    samples = point[None, :] + patch_offsets(batch)
    rows = []
    normalized = []
    normalized_frame_ids = []
    for selected in batch["views"]:
        frame = frame_by_id[int(selected["frame_id"])]
        projection = np.asarray(frame["projection_3x4"], dtype=np.float64).reshape(3, 4)
        homogeneous = np.column_stack([samples, np.ones(len(samples))]) @ projection.T
        xy = homogeneous[:, :2] / homogeneous[:, 2:3]
        inside = bool(
            np.all(homogeneous[:, 2] > 0.05)
            and np.all(xy[:, 0] >= 0)
            and np.all(xy[:, 0] <= int(frame["width"]) - 1)
            and np.all(xy[:, 1] >= 0)
            and np.all(xy[:, 1] <= int(frame["height"]) - 1)
        )
        with Image.open(frame["jpeg_path"]) as source:
            image = np.asarray(source.convert("RGB"), dtype=np.uint8)
        gray = bilinear_rgb(image, xy) @ GRAY_WEIGHTS
        sigma = float(gray.std())
        centered = gray - gray.mean()
        norm = float(np.linalg.norm(centered))
        row = {
            "frame_id": int(selected["frame_id"]),
            "inside": inside,
            "std_u8": sigma,
            "passes_min_std": sigma >= float(batch["minimum_std_u8_by_scale"][0]),
            "gray_min": float(gray.min()),
            "gray_max": float(gray.max()),
            "gray_mean": float(gray.mean()),
        }
        rows.append(row)
        if inside and row["passes_min_std"]:
            normalized.append(centered / (norm + 1e-9))
            normalized_frame_ids.append(int(selected["frame_id"]))
    pairwise = []
    for left in range(len(normalized)):
        for right in range(left + 1, len(normalized)):
            pairwise.append(
                {
                    "frame_ids": [normalized_frame_ids[left], normalized_frame_ids[right]],
                    "ncc": float(normalized[left] @ normalized[right]),
                }
            )
    return {"views": rows, "pairwise_ncc": pairwise}


def score_pil_hypotheses(
    batch: dict,
    frame_by_id: dict[int, dict],
    *,
    minimum_views: int,
    ncc_min: float,
    minimum_parallax_deg: float,
    unique_depth_margin: float,
) -> dict:
    points = np.asarray(batch["hypothesis_points_xyz"], dtype=np.float64)
    offsets = patch_offsets(batch)
    images = {}
    for view in batch["views"]:
        frame_id = int(view["frame_id"])
        with Image.open(frame_by_id[frame_id]["jpeg_path"]) as source:
            images[frame_id] = np.asarray(source.convert("RGB"), dtype=np.uint8)
    rows = []
    for hypothesis, point in enumerate(points):
        samples = point[None, :] + offsets
        candidates = []
        for local_view, selected in enumerate(batch["views"]):
            if not selected["hypothesis_masks_scale0"][hypothesis]:
                continue
            frame_id = int(selected["frame_id"])
            frame = frame_by_id[frame_id]
            projection = np.asarray(frame["projection_3x4"], dtype=np.float64).reshape(
                3, 4
            )
            homogeneous = (
                np.column_stack([samples, np.ones(len(samples))]) @ projection.T
            )
            xy = homogeneous[:, :2] / homogeneous[:, 2:3]
            inside = bool(
                np.all(homogeneous[:, 2] > 0.05)
                and np.all(xy[:, 0] >= 0)
                and np.all(xy[:, 0] <= int(frame["width"]) - 1)
                and np.all(xy[:, 1] >= 0)
                and np.all(xy[:, 1] <= int(frame["height"]) - 1)
            )
            if not inside:
                continue
            gray = bilinear_rgb(images[frame_id], xy) @ GRAY_WEIGHTS
            if float(gray.std()) < float(batch["minimum_std_u8_by_scale"][0]):
                continue
            centered = gray - gray.mean()
            candidates.append((frame_id, centered / (np.linalg.norm(centered) + 1e-9)))
        count = len(candidates)
        ncc = np.eye(count, dtype=np.float64)
        for left in range(count):
            for right in range(left + 1, count):
                value = float(candidates[left][1] @ candidates[right][1])
                ncc[left, right] = value
                ncc[right, left] = value
        clique = largest_consistent_clique(ncc, ncc_min, minimum_views)
        clique_frames = [candidates[index][0] for index in clique]
        if len(clique) >= minimum_views:
            sub = ncc[np.ix_(clique, clique)]
            median_ncc = float(np.median(sub[np.triu_indices(len(clique), 1)]))
            rays = np.stack(
                [
                    point
                    - np.asarray(frame_by_id[frame_id]["camera_center"], dtype=np.float64)
                    for frame_id in clique_frames
                ]
            )
            rays /= np.linalg.norm(rays, axis=1, keepdims=True) + 1e-12
            parallax = float(
                np.degrees(np.arccos(np.clip(rays @ rays.T, -1.0, 1.0))).max()
            )
        else:
            median_ncc = None
            parallax = 0.0
        rows.append(
            {
                "hypothesis": hypothesis,
                "candidate_frame_ids": [frame_id for frame_id, _ in candidates],
                "clique_frame_ids": clique_frames,
                "supporting_views": int(len(clique)),
                "median_ncc": median_ncc,
                "parallax_deg": parallax,
                "valid_score": bool(
                    len(clique) >= minimum_views
                    and parallax >= minimum_parallax_deg
                ),
            }
        )
    center = rows[0]
    alternatives = [row for row in rows[1:] if row["valid_score"]]
    accepted = bool(center["valid_score"])
    if accepted:
        accepted = all(
            center["supporting_views"] >= row["supporting_views"]
            and center["median_ncc"] >= row["median_ncc"] + unique_depth_margin
            for row in alternatives
        )
    return {
        "hypotheses": rows,
        "unique_depth_accepted": accepted,
        "best_alternative_ncc": max(
            (row["median_ncc"] for row in alternatives), default=None
        ),
    }


def score_shader_surface(
    batch: dict,
    shader: dict,
    frame_by_id: dict[int, dict],
    *,
    minimum_views: int,
    ncc_min: float,
    minimum_parallax_deg: float,
    unique_depth_margin: float,
) -> dict:
    scale = shader["scales"][0]
    points = np.asarray(batch["hypothesis_points_xyz"], dtype=np.float64)
    rows = []
    for hypothesis, point in enumerate(points):
        candidates = []
        for local_view, view in enumerate(scale["views"]):
            mask = batch["views"][local_view]["hypothesis_masks_scale0"][hypothesis]
            evidence = view["hypotheses"][hypothesis]
            if mask and evidence["valid"]:
                candidates.append(
                    (
                        int(view["frame_id"]),
                        np.asarray(evidence["normalized_patch"], dtype=np.float64),
                    )
                )
        count = len(candidates)
        ncc = np.eye(count, dtype=np.float64)
        for left in range(count):
            for right in range(left + 1, count):
                value = float(candidates[left][1] @ candidates[right][1])
                ncc[left, right] = value
                ncc[right, left] = value
        clique = largest_consistent_clique(ncc, ncc_min, minimum_views)
        clique_frames = [candidates[index][0] for index in clique]
        if len(clique) >= minimum_views:
            sub = ncc[np.ix_(clique, clique)]
            median_ncc = float(np.median(sub[np.triu_indices(len(clique), 1)]))
            rays = np.stack(
                [
                    point
                    - np.asarray(frame_by_id[frame_id]["camera_center"], dtype=np.float64)
                    for frame_id in clique_frames
                ]
            )
            rays /= np.linalg.norm(rays, axis=1, keepdims=True) + 1e-12
            cosine = np.clip(rays @ rays.T, -1.0, 1.0)
            parallax = float(np.degrees(np.arccos(cosine)).max())
        else:
            median_ncc = None
            parallax = 0.0
        rows.append(
            {
                "hypothesis": hypothesis,
                "candidate_frame_ids": [frame_id for frame_id, _ in candidates],
                "clique_frame_ids": clique_frames,
                "supporting_views": int(len(clique)),
                "median_ncc": median_ncc,
                "parallax_deg": parallax,
                "valid_score": bool(
                    len(clique) >= minimum_views
                    and parallax >= minimum_parallax_deg
                ),
            }
        )
    center = rows[0]
    alternatives = [row for row in rows[1:] if row["valid_score"]]
    accepted = bool(center["valid_score"])
    if accepted:
        accepted = all(
            center["supporting_views"] >= row["supporting_views"]
            and center["median_ncc"] >= row["median_ncc"] + unique_depth_margin
            for row in alternatives
        )
    return {
        "hypotheses": rows,
        "unique_depth_accepted": accepted,
        "best_alternative_ncc": max(
            (row["median_ncc"] for row in alternatives), default=None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    diagnostic = json.loads(args.diagnostic.read_text())
    scene = next(row for row in manifest["scenes"] if row["capture"] == diagnostic["capture"])
    frame_by_id = {int(frame["frame_id"]): frame for frame in scene["views"]}
    output = {
        "schema": "pocketworld_patch_texture_diagnostic_v1",
        "capture": diagnostic["capture"],
        "floor": score_surface(diagnostic["floor"]["batch_diagnostic"], frame_by_id),
        "wall": score_surface(diagnostic["wall"]["batch_diagnostic"], frame_by_id),
        "floor_shader_scores": score_shader_surface(
            diagnostic["floor"]["batch_diagnostic"],
            diagnostic["floor"]["shader_readback"],
            frame_by_id,
            minimum_views=3,
            ncc_min=0.70,
            minimum_parallax_deg=5.0,
            unique_depth_margin=0.02,
        ),
        "wall_shader_scores": score_shader_surface(
            diagnostic["wall"]["batch_diagnostic"],
            diagnostic["wall"]["shader_readback"],
            frame_by_id,
            minimum_views=4,
            ncc_min=0.80,
            minimum_parallax_deg=10.0,
            unique_depth_margin=0.02,
        ),
        "floor_pil_scores": score_pil_hypotheses(
            diagnostic["floor"]["batch_diagnostic"],
            frame_by_id,
            minimum_views=3,
            ncc_min=0.70,
            minimum_parallax_deg=5.0,
            unique_depth_margin=0.02,
        ),
        "wall_pil_scores": score_pil_hypotheses(
            diagnostic["wall"]["batch_diagnostic"],
            frame_by_id,
            minimum_views=4,
            ncc_min=0.80,
            minimum_parallax_deg=10.0,
            unique_depth_margin=0.02,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        "PATCH_TEXTURE_RESULT",
        f"floor_valid={sum(row['passes_min_std'] for row in output['floor']['views'])}",
        f"wall_valid={sum(row['passes_min_std'] for row in output['wall']['views'])}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
