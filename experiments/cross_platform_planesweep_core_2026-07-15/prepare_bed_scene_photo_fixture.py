#!/usr/bin/env python3
"""Prepare cap40/cap41 photo-pose fixtures and an independent floor reference.

The ARKit raw-feature anchors in the high-resolution photo sidecars are used only
as an offline reference plane.  They are deliberately kept out of the product
plane-sweep input contract, which remains images + poses + a sparse-proposed
plane.  The reference lets the experiment distinguish the physical floor from
the parallel sparse ghost layers visible around the bed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_sidecars(photo_dir: Path) -> list[tuple[Path, dict]]:
    rows = []
    for path in sorted(photo_dir.glob("*.json")):
        row = json.loads(path.read_text())
        image = path.with_suffix(".jpg")
        if not image.is_file():
            raise RuntimeError(f"missing JPEG for {path.name}")
        if int(row["image_w"]) <= 1 or int(row["image_h"]) <= 1:
            raise RuntimeError(f"invalid image dimensions in {path.name}")
        rows.append((path, row))
    if len(rows) < 3:
        raise RuntimeError("fewer than three complete photo sidecars")
    return rows


def ledger_by_name(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text().splitlines():
        if not line:
            continue
        row = json.loads(line)
        rows[Path(row["jpegPath"]).name] = row
    return rows


def unique_points_5mm(rows: list[tuple[Path, dict]]) -> np.ndarray:
    chunks = []
    for _, row in rows:
        points = np.asarray(row.get("anchors_world", []), dtype=np.float64)
        if points.ndim == 2 and points.shape[1] == 3:
            chunks.append(points)
    if not chunks:
        raise RuntimeError("photo sidecars contain no raw feature anchors")
    points = np.concatenate(chunks)
    finite = points[np.all(np.isfinite(points), axis=1)]
    quantized = np.rint(finite / 0.005).astype(np.int64)
    _, first = np.unique(quantized, axis=0, return_index=True)
    return finite[np.sort(first)]


def coverage_cells(points: np.ndarray, cell_m: float = 0.10) -> int:
    cells = np.floor(points[:, [0, 2]] / cell_m).astype(np.int64)
    return int(len(np.unique(cells, axis=0)))


def fit_reference_floor(points: np.ndarray, camera_y: np.ndarray) -> dict:
    # A floor must lie below the camera path.  Rank only those low candidates;
    # otherwise the densely textured bed can displace the physical floor peak.
    maximum_height = float(np.percentile(camera_y, 10) - 0.10)
    low = float(np.percentile(points[:, 1], 1))
    high = min(float(np.percentile(points[:, 1], 90)), maximum_height)
    if high <= low:
        raise RuntimeError("no gravity-low floor search interval")
    step = 0.01
    edges = np.arange(low, high + step * 1.001, step)
    counts, _ = np.histogram(points[:, 1], bins=edges)
    candidates = []
    for index in range(len(counts)):
        center = float((edges[index] + edges[index + 1]) * 0.5)
        mask = np.abs(points[:, 1] - center) <= 0.012
        support = int(mask.sum())
        if support < 100:
            continue
        cells = coverage_cells(points[mask])
        if cells < 50:
            continue
        score = support * np.sqrt(cells)
        candidates.append((score, -center, center, support, cells))
    if not candidates:
        raise RuntimeError("no independently certified floor reference")
    _, _, anchor, anchor_support, anchor_cells = max(candidates)

    # Three narrow LSQ refinements match the production plane convention while
    # preventing adjacent ghost layers from joining the fit.
    normal = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    offset = -anchor
    fit_support = 0
    for _ in range(3):
        mask = np.abs(points @ normal + offset) < 0.01
        fit_support = int(mask.sum())
        if fit_support < 100:
            raise RuntimeError("reference floor lost support during refinement")
        chosen = points[mask]
        centroid = chosen.mean(axis=0)
        _, _, vh = np.linalg.svd(chosen - centroid, full_matrices=False)
        normal = vh[-1]
        if normal[1] < 0:
            normal = -normal
        normal /= np.linalg.norm(normal)
        offset = -float(normal @ centroid)
    value = -offset
    residual = points @ normal - value
    support_mask = np.abs(residual) <= 0.02
    support_points = points[support_mask]
    if len(support_points) < 100:
        raise RuntimeError("reference floor has insufficient 2cm support")

    basis_u = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    basis_u -= float(basis_u @ normal) * normal
    basis_u /= np.linalg.norm(basis_u)
    basis_v = np.cross(normal, basis_u)
    basis_v /= np.linalg.norm(basis_v)
    u = support_points @ basis_u
    v = support_points @ basis_v
    bounds_u = (np.percentile(u, [1, 99]) + np.array([-0.05, 0.05])).tolist()
    bounds_v = (np.percentile(v, [1, 99]) + np.array([-0.05, 0.05])).tolist()
    return {
        "surface_id": "floor_reference_0",
        "kind": "floor",
        "normal": normal.tolist(),
        "plane_value_n_dot_x": value,
        "basis_u": basis_u.tolist(),
        "basis_v": basis_v.tolist(),
        "bounds_u_m": bounds_u,
        "bounds_v_m": bounds_v,
        "support_points_20mm": int(len(support_points)),
        "coverage_cells_10cm": coverage_cells(support_points),
        "rms_error_m": float(np.sqrt(np.mean(residual[support_mask] ** 2))),
        "certified_for_generation": True,
        "reference_only_not_product_input": True,
        "reference_peak": {
            "anchor_y_m": anchor,
            "support_12mm": anchor_support,
            "coverage_cells_10cm": anchor_cells,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    photo_dir = args.capture_dir / "photos_highres"
    ledger_path = args.capture_dir / "sfm_fed_frames.jsonl"
    rows = read_sidecars(photo_dir)
    ledger = ledger_by_name(ledger_path)
    frames = []
    centers = []
    consumed_sidecars = []
    for sidecar, row in rows:
        image_name = sidecar.with_suffix(".jpg").name
        fed = ledger.get(image_name)
        if fed is None:
            raise RuntimeError(f"photo {image_name} is absent from durable SfM ledger")
        center = np.asarray(row["extrinsic"], dtype=np.float64).reshape(4, 4).T[:3, 3]
        ledger_center = np.asarray(fed["arkitCameraCenterWorld"], dtype=np.float64)
        if np.linalg.norm(center - ledger_center) > 1e-4:
            raise RuntimeError(f"pose mismatch for {image_name}")
        fx, fy, cx, cy = [float(value) for value in row["intrinsics_fxfycxcy"]]
        frames.append(
            {
                "src": image_name,
                "fx": fx,
                "fy": fy,
                "cx": cx,
                "cy": cy,
                "extrinsic": row["extrinsic"],
            }
        )
        centers.append(center)
        consumed_sidecars.append(
            {"path": str(sidecar), "sha256": sha256(sidecar)}
        )
    widths = {int(row["image_w"]) for _, row in rows}
    heights = {int(row["image_h"]) for _, row in rows}
    if len(widths) != 1 or len(heights) != 1:
        raise RuntimeError("mixed JPEG dimensions are not supported by this fixture")

    anchors = unique_points_5mm(rows)
    floor = fit_reference_floor(anchors, np.asarray(centers)[:, 1])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame_meta_path = args.output_dir / "frame_meta.json"
    planes_path = args.output_dir / "reference_floor.json"
    manifest_path = args.output_dir / "fixture_manifest.json"
    frame_meta = {
        "schema": "aether_bed_scene_photo_fixture_v1",
        "work_w": next(iter(widths)),
        "work_h": next(iter(heights)),
        "frames": frames,
    }
    planes = {
        "schema": "aether_reference_structural_planes_v1",
        "floor": floor,
        "surfaces": [],
        "warning": (
            "ARKit raw-feature anchors define offline reference truth only; "
            "they are forbidden as a cross-platform product plane-sweep input"
        ),
    }
    frame_meta_path.write_text(json.dumps(frame_meta, indent=2, sort_keys=True) + "\n")
    planes_path.write_text(json.dumps(planes, indent=2, sort_keys=True) + "\n")
    manifest = {
        "schema": "aether_bed_scene_photo_fixture_manifest_v1",
        "capture_dir": str(args.capture_dir),
        "photo_count": len(frames),
        "ledger": {"path": str(ledger_path), "sha256": sha256(ledger_path)},
        "sidecars": consumed_sidecars,
        "unique_anchor_sites_5mm": int(len(anchors)),
        "reference_floor": floor,
        "outputs": {
            "frame_meta": {"path": str(frame_meta_path), "sha256": sha256(frame_meta_path)},
            "planes": {"path": str(planes_path), "sha256": sha256(planes_path)},
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
