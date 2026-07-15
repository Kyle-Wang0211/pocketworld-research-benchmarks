#!/usr/bin/env python3
"""Fit ceiling and vertical-wall sweep domains from a first-party sparse cloud.

Inputs are only the product sparse PLY and the product floor-plane metadata.  No
feature matches, learned matcher outputs, or rescue point clouds are consumed.
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


def read_ply_xyz(path: Path) -> np.ndarray:
    with path.open("rb") as stream:
        if stream.readline().strip() != b"ply":
            raise ValueError(f"not a PLY: {path}")
        fmt = stream.readline().strip()
        vertex_count = 0
        properties: list[tuple[str, str]] = []
        while True:
            line = stream.readline().strip()
            if line.startswith(b"element vertex"):
                vertex_count = int(line.split()[-1])
            elif line.startswith(b"property"):
                _, data_type, name = line.decode().split()
                properties.append((name, data_type))
            elif line == b"end_header":
                break
        if vertex_count <= 0:
            raise ValueError("PLY contains no vertices")
        if fmt == b"format ascii 1.0":
            xyz = np.empty((vertex_count, 3), dtype=np.float64)
            for index in range(vertex_count):
                xyz[index] = [float(value) for value in stream.readline().split()[:3]]
            return xyz
        if fmt != b"format binary_little_endian 1.0":
            raise ValueError(f"unsupported PLY format: {fmt!r}")
        type_map = {
            "float": "<f4",
            "double": "<f8",
            "uchar": "u1",
            "int": "<i4",
            "uint": "<u4",
        }
        dtype = np.dtype([(name, type_map[data_type]) for name, data_type in properties])
        records = np.frombuffer(stream.read(vertex_count * dtype.itemsize), dtype=dtype, count=vertex_count)
        return np.column_stack([records["x"], records["y"], records["z"]]).astype(np.float64)


def horizontal_basis(up: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    seed = np.array([1.0, 0.0, 0.0])
    if abs(seed @ up) > 0.9:
        seed = np.array([0.0, 0.0, 1.0])
    axis_u = seed - (seed @ up) * up
    axis_u /= np.linalg.norm(axis_u)
    axis_v = np.cross(up, axis_u)
    axis_v /= np.linalg.norm(axis_v)
    return axis_u, axis_v


def cell_count(a: np.ndarray, b: np.ndarray, cell: float = 0.10) -> int:
    if len(a) == 0:
        return 0
    cells = np.floor(np.column_stack([a, b]) / cell).astype(np.int64)
    return int(len(np.unique(cells, axis=0)))


def percentile_bounds(values: np.ndarray) -> list[float]:
    low, high = np.percentile(values, [1, 99])
    return [float(low), float(high)]


def build_floor_surface(
    xyz: np.ndarray,
    up: np.ndarray,
    floor_value: float,
    axis_u: np.ndarray,
    axis_v: np.ndarray,
    *,
    pad_m: float = 0.05,
    minimum_support: int = 500,
) -> dict:
    """Build the floor sweep domain from first-party sparse points near the known plane."""
    distance = np.abs(xyz @ up - floor_value)
    support = distance <= 0.020
    support_count = int(support.sum())
    if support_count < minimum_support:
        raise ValueError(
            f"known floor has only {support_count} sparse points within 20mm; "
            f"need {minimum_support}"
        )
    coordinate_u = xyz[support] @ axis_u
    coordinate_v = xyz[support] @ axis_v
    bounds_u = [float(coordinate_u.min() - pad_m), float(coordinate_u.max() + pad_m)]
    bounds_v = [float(coordinate_v.min() - pad_m), float(coordinate_v.max() + pad_m)]
    coverage_cells = cell_count(coordinate_u, coordinate_v, 0.05)
    checks = {
        "minimum_support": support_count >= minimum_support,
        "minimum_coverage": coverage_cells >= 50 or minimum_support < 50,
        "finite_positive_domain": bool(
            np.isfinite([*bounds_u, *bounds_v]).all()
            and bounds_u[1] > bounds_u[0]
            and bounds_v[1] > bounds_v[0]
        ),
    }
    return {
        "surface_id": "floor_0",
        "kind": "floor",
        "normal": up.tolist(),
        "plane_value_n_dot_x": floor_value,
        "basis_u": axis_u.tolist(),
        "basis_v": axis_v.tolist(),
        "bounds_u_m": bounds_u,
        "bounds_v_m": bounds_v,
        "support_points_20mm": support_count,
        "coverage_cells_5cm": coverage_cells,
        "domain_padding_m": pad_m,
        "plane_certification": {
            "source": "first-party known floor plane plus product sparse-cloud domain",
            "support_band_m": 0.020,
            "checks": checks,
        },
        "certified_for_generation": all(checks.values()),
    }


def fit_ceiling(
    xyz: np.ndarray,
    height: np.ndarray,
    axis_u: np.ndarray,
    axis_v: np.ndarray,
    floor_value: float,
    up: np.ndarray,
) -> tuple[dict, np.ndarray]:
    plausible = height[(height >= 1.80) & (height <= np.percentile(height, 99.8))]
    if len(plausible) < 100:
        raise ValueError("insufficient high points for a ceiling plane")
    step = 0.01
    edges = np.arange(1.80, plausible.max() + step * 1.01, step)
    histogram, _ = np.histogram(plausible, bins=edges)
    candidates = np.argsort(histogram)[-min(32, len(histogram)) :]
    best: tuple[float, float, np.ndarray] | None = None
    uv = np.column_stack([xyz @ axis_u, xyz @ axis_v])
    for index in candidates:
        center = (edges[index] + edges[index + 1]) * 0.5
        mask = np.abs(height - center) <= 0.035
        if mask.sum() < 100:
            continue
        cells = cell_count(uv[mask, 0], uv[mask, 1])
        score = float(mask.sum() * np.sqrt(max(cells, 1)))
        if best is None or score > best[0]:
            best = (score, center, mask)
    if best is None:
        raise ValueError("ceiling fit found no supported horizontal plane")
    _, _, initial_mask = best
    ceiling_height = float(np.median(height[initial_mask]))
    mask = np.abs(height - ceiling_height) <= 0.035
    ceiling_value = floor_value + ceiling_height
    return (
        {
            "surface_id": "ceiling_0",
            "kind": "ceiling",
            "normal": up.tolist(),
            "plane_value_n_dot_x": ceiling_value,
            "basis_u": axis_u.tolist(),
            "basis_v": axis_v.tolist(),
            "bounds_u_m": percentile_bounds(xyz[mask] @ axis_u),
            "bounds_v_m": percentile_bounds(xyz[mask] @ axis_v),
            "support_points_35mm": int(mask.sum()),
            "coverage_cells_10cm": cell_count(xyz[mask] @ axis_u, xyz[mask] @ axis_v),
            "height_above_floor_m": ceiling_height,
            "fit_band_m": 0.035,
        },
        mask,
    )


def wall_candidates(
    xyz: np.ndarray,
    height: np.ndarray,
    axis_u: np.ndarray,
    axis_v: np.ndarray,
    ceiling_height: float,
    max_walls: int,
) -> list[dict]:
    room_mask = (height >= 0.15) & (height <= ceiling_height - 0.10)
    points = xyz[room_mask]
    point_height = height[room_mask]
    point_u = points @ axis_u
    point_v = points @ axis_v
    raw: list[dict] = []
    rho_step = 0.03
    for theta_deg in range(0, 180, 2):
        theta = np.radians(theta_deg)
        cosine, sine = float(np.cos(theta)), float(np.sin(theta))
        rho = point_u * cosine + point_v * sine
        low = np.floor(np.percentile(rho, 0.5) / rho_step) * rho_step
        high = np.ceil(np.percentile(rho, 99.5) / rho_step) * rho_step
        edges = np.arange(low, high + rho_step * 1.01, rho_step)
        histogram, _ = np.histogram(rho, bins=edges)
        for index in np.argsort(histogram)[-min(8, len(histogram)) :]:
            initial = (edges[index] + edges[index + 1]) * 0.5
            preliminary = np.abs(rho - initial) <= 0.035
            if preliminary.sum() < 120:
                continue
            value = float(np.median(rho[preliminary]))
            inlier = np.abs(rho - value) <= 0.035
            tangent = -point_u * sine + point_v * cosine
            tangent_inlier = tangent[inlier]
            height_inlier = point_height[inlier]
            tangent_span = float(np.percentile(tangent_inlier, 98) - np.percentile(tangent_inlier, 2))
            height_span = float(np.percentile(height_inlier, 98) - np.percentile(height_inlier, 2))
            if tangent_span < 0.60 or height_span < 0.60:
                continue
            cells = cell_count(tangent_inlier, height_inlier)
            raw.append(
                {
                    "theta_deg": theta_deg,
                    "value": value,
                    "support": int(inlier.sum()),
                    "cells": cells,
                    "score": float(cells * np.sqrt(inlier.sum())),
                    "tangent_bounds": percentile_bounds(tangent_inlier),
                    "height_bounds": percentile_bounds(height_inlier),
                    "tangent_span": tangent_span,
                    "height_span": height_span,
                }
            )
    selected: list[dict] = []
    for candidate in sorted(raw, key=lambda item: item["score"], reverse=True):
        same_orientation = []
        duplicate_layer = False
        for prior in selected:
            angle = abs(candidate["theta_deg"] - prior["theta_deg"])
            angle = min(angle, 180 - angle)
            if angle <= 10:
                same_orientation.append(prior)
                if abs(candidate["value"] - prior["value"]) <= 0.75:
                    duplicate_layer = True
        # A rectangular room may legitimately have two opposing, parallel
        # walls.  More than two near-parallel layers are almost always object
        # faces or sparse-cloud ghost layers and must not become sweep planes.
        if duplicate_layer or len(same_orientation) >= 2:
            continue
        selected.append(candidate)
        if len(selected) >= max_walls:
            break
    walls = []
    for index, candidate in enumerate(selected):
        theta = np.radians(candidate["theta_deg"])
        normal = np.cos(theta) * axis_u + np.sin(theta) * axis_v
        tangent = -np.sin(theta) * axis_u + np.cos(theta) * axis_v
        walls.append(
            {
                "surface_id": f"wall_{index}",
                "kind": "wall",
                "normal": normal.tolist(),
                "plane_value_n_dot_x": candidate["value"],
                "basis_u": tangent.tolist(),
                "basis_v": np.asarray([0.0, 0.0, 0.0]).tolist(),
                "vertical_basis": "floor_normal",
                "bounds_u_m": candidate["tangent_bounds"],
                "bounds_height_m": candidate["height_bounds"],
                "support_points_35mm": candidate["support"],
                "coverage_cells_10cm": candidate["cells"],
                "theta_deg_in_horizontal_basis": candidate["theta_deg"],
                "fit_band_m": 0.035,
                "score": candidate["score"],
            }
        )
    return walls


def wall_height_limit(height: np.ndarray, ceiling: dict | None) -> float:
    """Keep wall fitting available when a capture has no observable ceiling."""
    if ceiling is not None:
        return float(ceiling["height_above_floor_m"])
    supported = height[np.isfinite(height) & (height >= 0.15)]
    if len(supported) < 100:
        raise ValueError("insufficient above-floor sparse support for wall fitting")
    # wall_candidates subtracts 10 cm from this limit. Adding it here makes
    # the effective cap the robust 99.5th percentile of observed support.
    return float(np.percentile(supported, 99.5) + 0.10)


def certify_surface(
    surface: dict,
    xyz: np.ndarray,
    height: np.ndarray,
    floor: dict,
) -> None:
    """Require the selected plane to be the unique local sparse-support mode."""
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    axis_u = np.asarray(surface["basis_u"], dtype=np.float64)
    coordinate_u = xyz @ axis_u
    u0, u1 = surface["bounds_u_m"]
    if surface["kind"] == "wall":
        coordinate_v = height
        v0, v1 = surface["bounds_height_m"]
    else:
        axis_v = np.asarray(surface["basis_v"], dtype=np.float64)
        coordinate_v = xyz @ axis_v
        v0, v1 = surface["bounds_v_m"]
    domain = (
        (coordinate_u >= u0)
        & (coordinate_u <= u1)
        & (coordinate_v >= v0)
        & (coordinate_v <= v1)
    )
    value = float(surface["plane_value_n_dot_x"])
    support = {}
    for offset in (-0.10, -0.05, 0.0, 0.05, 0.10):
        mask = domain & (np.abs(xyz @ normal - (value + offset)) <= 0.020)
        support[f"{offset:+.2f}"] = {
            "points_20mm": int(mask.sum()),
            "coverage_cells_10cm": cell_count(coordinate_u[mask], coordinate_v[mask]),
        }
    center = support["+0.00"]
    near_points = max(support["-0.05"]["points_20mm"], support["+0.05"]["points_20mm"])
    near_cells = max(
        support["-0.05"]["coverage_cells_10cm"],
        support["+0.05"]["coverage_cells_10cm"],
    )
    far_points = max(support["-0.10"]["points_20mm"], support["+0.10"]["points_20mm"])
    checks = {
        "minimum_support": center["points_20mm"] >= 500,
        "minimum_coverage": center["coverage_cells_10cm"] >= 50,
        "unique_vs_5cm_points": center["points_20mm"] >= near_points * 1.05,
        "unique_vs_5cm_cells": center["coverage_cells_10cm"] >= near_cells * 0.95,
        "unique_vs_10cm_points": center["points_20mm"] >= far_points * 1.25,
    }
    surface["plane_certification"] = {
        "source": "first-party sparse cloud only",
        "domain_points": int(domain.sum()),
        "offset_support": support,
        "checks": checks,
        "support_prominence_vs_5cm": center["points_20mm"] / max(near_points, 1),
        "coverage_prominence_vs_5cm": center["coverage_cells_10cm"] / max(near_cells, 1),
    }
    surface["certified_for_generation"] = all(checks.values())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud", type=Path, required=True)
    parser.add_argument("--floor-meta", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-walls", type=int, default=6)
    args = parser.parse_args()

    xyz = read_ply_xyz(args.cloud)
    floor_meta = json.loads(args.floor_meta.read_text())
    up = np.asarray(floor_meta["plane_n"], dtype=np.float64)
    up /= np.linalg.norm(up)
    raw_value = float(floor_meta["plane_d"])
    projection = xyz @ up
    plus = int((np.abs(projection - raw_value) < 0.03).sum())
    minus = int((np.abs(projection + raw_value) < 0.03).sum())
    floor_value = raw_value if plus >= minus else -raw_value
    height = projection - floor_value
    axis_u, axis_v = horizontal_basis(up)

    ceiling = None
    ceiling_fit_error = None
    try:
        ceiling, _ = fit_ceiling(xyz, height, axis_u, axis_v, floor_value, up)
    except ValueError as error:
        ceiling_fit_error = str(error)
    walls = wall_candidates(
        xyz,
        height,
        axis_u,
        axis_v,
        wall_height_limit(height, ceiling),
        args.max_walls,
    )
    for wall in walls:
        wall["basis_v"] = up.tolist()

    floor = build_floor_surface(xyz, up, floor_value, axis_u, axis_v)
    structural_surfaces = ([ceiling] if ceiling is not None else []) + walls
    for surface in structural_surfaces:
        certify_surface(surface, xyz, height, floor)

    output = {
        "schema": "aether_known_structural_planes_v2",
        "algorithm": (
            "known floor domain + deterministic sparse-cloud histogram ceiling "
            "+ optional histogram ceiling + vertical Hough walls"
        ),
        "inputs": {
            "sparse_cloud": {"path": str(args.cloud), "sha256": sha256(args.cloud)},
            "floor_plane": {"path": str(args.floor_meta), "sha256": sha256(args.floor_meta)},
            "forbidden_matcher_outputs_consumed": False,
        },
        "floor": floor,
        "surfaces": structural_surfaces,
        "ceiling_fit": {
            "release_blocking": False,
            "status": "fitted" if ceiling is not None else "not_observed",
            "reason": ceiling_fit_error,
        },
        "counts": {
            "floor": 1,
            "ceiling": int(ceiling is not None),
            "walls": len(walls),
            "certified": sum(
                surface["certified_for_generation"] for surface in [floor, *structural_surfaces]
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
