#!/usr/bin/env python3
"""Assign product birth identity to multi-view-certified wall points.

This is a non-destructive publication gate.  The input PLY and every internal
plane-sweep hypothesis remain untouched.  A point loses only its product-point
identity when a stronger point from a different, near-parallel wall surface
occupies the same image ray in at least two registered views while disagreeing
by 12--100 mm in surface-normal depth.

The policy extends the validated sparse-cloud multi-view depth-conflict owner
to known-plane births.  It deliberately excludes wall corners: only pairs with
near-parallel source normals and normal-dominant separation are eligible.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree


FLIP_ARKIT_TO_CV = np.diag([1.0, -1.0, -1.0])


@dataclass(frozen=True)
class Frame:
    frame_id: int
    K: np.ndarray
    R: np.ndarray
    t: np.ndarray
    width: int
    height: int


@dataclass(frozen=True)
class PointEvidence:
    index: int
    surface_id: str
    xyz: np.ndarray
    normal: np.ndarray
    nviews: float
    parallax_deg: float
    zncc_median: float

    @property
    def owner_rank(self) -> tuple[float, float, float, int]:
        # Same ordering principle as the sparse-cloud owner: the independently
        # certified hypothesis with the strongest multi-view support gets first
        # refusal.  The final index tie-break makes the manifest deterministic.
        return (self.nviews, self.zncc_median, self.parallax_deg, -self.index)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def read_ascii_ply(path: Path) -> dict[str, np.ndarray]:
    with path.open("r", encoding="ascii") as stream:
        first = stream.readline().strip()
        if first != "ply":
            raise ValueError(f"{path}: not a PLY file")
        vertex_count = None
        properties: list[str] = []
        in_vertex = False
        while True:
            line = stream.readline()
            if not line:
                raise ValueError(f"{path}: missing end_header")
            fields = line.strip().split()
            if fields[:2] == ["format", "ascii"]:
                pass
            elif fields[:2] == ["element", "vertex"]:
                vertex_count = int(fields[2])
                in_vertex = True
            elif fields and fields[0] == "element":
                in_vertex = False
            elif fields and fields[0] == "property" and in_vertex:
                properties.append(fields[-1])
            elif fields == ["end_header"]:
                break
        if vertex_count is None:
            raise ValueError(f"{path}: missing vertex count")
        rows = []
        for _ in range(vertex_count):
            line = stream.readline()
            if not line:
                raise ValueError(f"{path}: truncated vertex payload")
            values = line.split()
            if len(values) != len(properties):
                raise ValueError(f"{path}: malformed vertex row")
            rows.append([float(value) for value in values])
        trailing = [line for line in stream if line.strip()]
        if trailing:
            raise ValueError(f"{path}: unexpected trailing payload")
    matrix = np.asarray(rows, dtype=np.float64).reshape(vertex_count, len(properties))
    return {name: matrix[:, index] for index, name in enumerate(properties)}


def selected_surfaces(document: dict) -> list[dict]:
    for key in ("selected_surfaces", "surfaces", "selected"):
        value = document.get(key)
        if isinstance(value, list):
            return value
    output = document.get("output")
    if isinstance(output, dict) and isinstance(output.get("surfaces"), list):
        return output["surfaces"]
    raise ValueError("plane document has no selected surface list")


def load_points(stats: dict, planes: dict, ply: dict[str, np.ndarray]) -> list[PointEvidence]:
    required = {"x", "y", "z", "nviews", "parallax_deg", "zncc_median"}
    missing = required - set(ply)
    if missing:
        raise ValueError(f"PLY missing properties: {sorted(missing)}")
    definitions = {row["surface_id"]: row for row in selected_surfaces(planes)}
    points: list[PointEvidence] = []
    offset = 0
    for result in stats["surfaces"]:
        surface_id = result["surface_id"]
        count = int(result["accepted"])
        if surface_id not in definitions:
            raise ValueError(f"missing surface definition for {surface_id}")
        normal = np.asarray(definitions[surface_id]["normal"], dtype=np.float64)
        normal /= max(float(np.linalg.norm(normal)), 1e-15)
        for index in range(offset, offset + count):
            points.append(
                PointEvidence(
                    index=index,
                    surface_id=surface_id,
                    xyz=np.asarray([ply["x"][index], ply["y"][index], ply["z"][index]]),
                    normal=normal,
                    nviews=float(ply["nviews"][index]),
                    parallax_deg=float(ply["parallax_deg"][index]),
                    zncc_median=float(ply["zncc_median"][index]),
                )
            )
        offset += count
    if offset != len(ply["x"]):
        raise ValueError(f"surface counts total {offset}, PLY has {len(ply['x'])} points")
    return points


def load_frames(meta_path: Path, ledger_path: Path, photo_dir: Path) -> list[Frame]:
    meta = json.loads(meta_path.read_text())
    ledger_by_name = {}
    for line in ledger_path.read_text().splitlines():
        if line:
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
        K = np.asarray(
            [
                [float(row["fx"]) * scale_x, 0.0, float(row["cx"]) * scale_x],
                [0.0, float(row["fy"]) * scale_y, float(row["cy"]) * scale_y],
                [0.0, 0.0, 1.0],
            ]
        )
        camera_to_world_arkit = np.asarray(row["extrinsic"], dtype=np.float64).reshape(4, 4).T
        center = camera_to_world_arkit[:3, 3]
        camera_to_world_cv = camera_to_world_arkit[:3, :3] @ FLIP_ARKIT_TO_CV
        R = camera_to_world_cv.T
        t = -R @ center
        ledger_center = np.asarray(ledger["arkitCameraCenterWorld"], dtype=np.float64)
        if np.linalg.norm(ledger_center - center) > 1e-4:
            raise ValueError(f"pose center mismatch for {source_name}")
        frames.append(Frame(int(ledger["frameId"]), K, R, t, width, height))
    frames.sort(key=lambda frame: frame.frame_id)
    if len(frames) < 3:
        raise ValueError("fewer than three usable first-party frames")
    return frames


def load_certified_views(
    path: Path, points: list[PointEvidence]
) -> dict[int, frozenset[int]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    if len(rows) != len(points):
        raise ValueError(
            f"birth evidence has {len(rows)} rows, expected {len(points)}"
        )
    result = {}
    for expected_index, (row, point) in enumerate(zip(rows, points, strict=True)):
        if int(row["point_index"]) != expected_index:
            raise ValueError("birth evidence point indices are not contiguous")
        if row["surface_id"] != point.surface_id:
            raise ValueError(f"birth evidence surface mismatch at {expected_index}")
        if np.linalg.norm(np.asarray(row["xyz"], dtype=np.float64) - point.xyz) > 1e-5:
            raise ValueError(f"birth evidence coordinate mismatch at {expected_index}")
        frame_ids = frozenset(int(value) for value in row["clique_frame_ids"])
        if len(frame_ids) != int(round(point.nviews)):
            raise ValueError(f"birth evidence view-count mismatch at {expected_index}")
        result[expected_index] = frame_ids
    return result


def layer_geometry(first: PointEvidence, second: PointEvidence) -> dict[str, float]:
    normal1 = first.normal.copy()
    normal2 = second.normal.copy()
    dot = float(np.clip(abs(normal1 @ normal2), 0.0, 1.0))
    if normal1 @ normal2 < 0.0:
        normal2 = -normal2
    normal = normal1 + normal2
    normal /= max(float(np.linalg.norm(normal)), 1e-15)
    delta_mm = (first.xyz - second.xyz) * 1000.0
    normal_separation = abs(float(normal @ delta_mm))
    total = float(np.linalg.norm(delta_mm))
    tangent = math.sqrt(max(0.0, total * total - normal_separation * normal_separation))
    return {
        "normal_angle_deg": math.degrees(math.acos(dot)),
        "normal_separation_mm": normal_separation,
        "tangent_separation_mm": tangent,
        "point_distance_mm": total,
    }


def find_conflicts(
    points: list[PointEvidence],
    frames: list[Frame],
    radius_px: float,
    min_gap_mm: float,
    max_gap_mm: float,
    min_views: int,
    max_normal_angle_deg: float,
    certified_views: dict[int, frozenset[int]] | None = None,
) -> tuple[dict[tuple[int, int], dict], dict[tuple[int, int], dict]]:
    xyz = np.asarray([point.xyz for point in points], dtype=np.float64)
    near_ray: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"frame_ids": set(), "pixel_distances_px": [], "depth_gaps_mm": []}
    )
    eligible: dict[tuple[int, int], dict] = defaultdict(
        lambda: {"frame_ids": set(), "pixel_distances_px": [], "depth_gaps_mm": []}
    )
    geometry_cache: dict[tuple[int, int], dict[str, float]] = {}
    for frame in frames:
        camera = (frame.R @ xyz.T).T + frame.t
        depth = camera[:, 2]
        valid = depth > 0.0
        uv = np.empty((len(points), 2), dtype=np.float64)
        uv[:] = np.nan
        projected = (frame.K @ camera[valid].T).T
        uv[valid] = projected[:, :2] / projected[:, 2:3]
        valid &= (
            (uv[:, 0] >= 0.0)
            & (uv[:, 0] < frame.width)
            & (uv[:, 1] >= 0.0)
            & (uv[:, 1] < frame.height)
        )
        indices = np.flatnonzero(valid)
        if len(indices) < 2:
            continue
        local_uv = uv[indices]
        for local_first, local_second in cKDTree(local_uv).query_pairs(radius_px):
            first_index = int(indices[local_first])
            second_index = int(indices[local_second])
            first, second = points[first_index], points[second_index]
            if first.surface_id == second.surface_id:
                continue
            if certified_views is not None and (
                frame.frame_id not in certified_views[first_index]
                or frame.frame_id not in certified_views[second_index]
            ):
                continue
            pair = (min(first_index, second_index), max(first_index, second_index))
            depth_gap_mm = abs(float(depth[first_index] - depth[second_index])) * 1000.0
            if depth_gap_mm < min_gap_mm or depth_gap_mm > max_gap_mm:
                continue
            pixel_distance = float(np.linalg.norm(uv[first_index] - uv[second_index]))
            row = near_ray[pair]
            row["frame_ids"].add(frame.frame_id)
            row["pixel_distances_px"].append(pixel_distance)
            row["depth_gaps_mm"].append(depth_gap_mm)
            geometry = geometry_cache.setdefault(pair, layer_geometry(first, second))
            if (
                geometry["normal_angle_deg"] <= max_normal_angle_deg
                and min_gap_mm <= geometry["normal_separation_mm"] <= max_gap_mm
                and geometry["tangent_separation_mm"] <= geometry["normal_separation_mm"]
            ):
                owned = eligible[pair]
                owned["frame_ids"].add(frame.frame_id)
                owned["pixel_distances_px"].append(pixel_distance)
                owned["depth_gaps_mm"].append(depth_gap_mm)

    def persistent(source: dict[tuple[int, int], dict]) -> dict[tuple[int, int], dict]:
        result = {}
        for pair, row in source.items():
            if len(row["frame_ids"]) < min_views:
                continue
            result[pair] = {
                "frame_ids": sorted(row["frame_ids"]),
                "pixel_distance_px_max": max(row["pixel_distances_px"]),
                "depth_gap_mm_min": min(row["depth_gaps_mm"]),
                "depth_gap_mm_max": max(row["depth_gaps_mm"]),
                **geometry_cache[pair],
            }
        return result

    return persistent(near_ray), persistent(eligible)


def greedy_birth_owner(
    points: list[PointEvidence], conflicts: dict[tuple[int, int], dict]
) -> tuple[list[int], list[dict]]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    for first, second in conflicts:
        adjacency[first].add(second)
        adjacency[second].add(first)
    accepted: set[int] = set()
    withheld: list[dict] = []
    for point in sorted(points, key=lambda item: item.owner_rank, reverse=True):
        blocking = sorted(adjacency[point.index] & accepted)
        if blocking:
            owner = max(blocking, key=lambda index: points[index].owner_rank)
            withheld.append(
                {
                    "point_index": point.index,
                    "surface_id": point.surface_id,
                    "owner_point_index": owner,
                    "owner_surface_id": points[owner].surface_id,
                    "point_rank": list(point.owner_rank),
                    "owner_rank": list(points[owner].owner_rank),
                    "conflict": conflicts[(min(point.index, owner), max(point.index, owner))],
                }
            )
            continue
        accepted.add(point.index)
    return sorted(accepted), sorted(withheld, key=lambda row: row["point_index"])


def remaining_conflicts(
    conflicts: dict[tuple[int, int], dict], accepted: list[int]
) -> int:
    accepted_set = set(accepted)
    return sum(first in accepted_set and second in accepted_set for first, second in conflicts)


def coverage(
    points: list[PointEvidence],
    frames: list[Frame],
    indices: list[int],
    certified_views: dict[int, frozenset[int]],
) -> dict:
    if not indices:
        return {"per_frame_32x18": [], "median": 0.0, "p10": 0.0, "min": 0}
    xyz = np.asarray([points[index].xyz for index in indices], dtype=np.float64)
    counts = []
    for frame in frames:
        certified_rows = [
            row
            for row, point_index in enumerate(indices)
            if frame.frame_id in certified_views[point_index]
        ]
        if not certified_rows:
            counts.append(0)
            continue
        certified_xyz = xyz[np.asarray(certified_rows, dtype=np.int64)]
        camera = (frame.R @ certified_xyz.T).T + frame.t
        valid = camera[:, 2] > 0.0
        projected = (frame.K @ camera[valid].T).T
        uv = projected[:, :2] / projected[:, 2:3]
        uv = uv[
            (uv[:, 0] >= 0.0)
            & (uv[:, 0] < frame.width)
            & (uv[:, 1] >= 0.0)
            & (uv[:, 1] < frame.height)
        ]
        cells = {
            (
                min(31, max(0, int(x * 32 / frame.width))),
                min(17, max(0, int(y * 18 / frame.height))),
            )
            for x, y in uv
        }
        counts.append(len(cells))
    values = np.asarray(counts, dtype=np.float64)
    return {
        "per_frame_32x18": counts,
        "median": float(np.median(values)),
        "p10": float(np.percentile(values, 10)),
        "min": int(np.min(values)),
    }


def serialize_pairs(
    conflicts: dict[tuple[int, int], dict], points: list[PointEvidence]
) -> list[dict]:
    return [
        {
            "point_indices": [first, second],
            "surface_ids": [points[first].surface_id, points[second].surface_id],
            **row,
        }
        for (first, second), row in sorted(conflicts.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stats", type=Path)
    parser.add_argument("photo_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument(
        "--radius-px",
        type=float,
        default=8.0,
        help="diagnostic near-ray radius; never grants birth authority",
    )
    parser.add_argument(
        "--birth-radius-px",
        type=float,
        default=0.5,
        help="same certified observation-site radius used by the birth owner",
    )
    parser.add_argument("--min-gap-mm", type=float, default=12.0)
    parser.add_argument("--max-gap-mm", type=float, default=100.0)
    parser.add_argument("--min-views", type=int, default=2)
    parser.add_argument("--max-normal-angle-deg", type=float, default=30.0)
    args = parser.parse_args()

    root = (args.repo_root or Path(__file__).resolve().parents[2]).resolve()
    stats_path = resolve(root, args.stats).resolve()
    stats = json.loads(stats_path.read_text())
    ply_path = resolve(root, stats["output"]["ply"]).resolve()
    planes_path = resolve(root, stats["inputs"]["planes"]["path"]).resolve()
    meta_path = resolve(root, stats["inputs"]["frame_meta"]["path"]).resolve()
    ledger_path = resolve(root, stats["inputs"]["ledger"]["path"]).resolve()
    photo_dir = resolve(root, args.photo_dir).resolve()
    output_path = resolve(root, args.output).resolve()
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")

    ply = read_ascii_ply(ply_path)
    planes = json.loads(planes_path.read_text())
    points = load_points(stats, planes, ply)
    frames = load_frames(meta_path, ledger_path, photo_dir)
    evidence_value = stats["output"].get("birth_evidence")
    if not evidence_value:
        raise ValueError(
            "stats has no product birth-evidence sidecar; rerun the unchanged "
            "plane sweep with evidence output before assigning ownership"
        )
    evidence_path = resolve(root, evidence_value).resolve()
    certified_views = load_certified_views(evidence_path, points)
    all_visible_near_ray, all_visible_parallel = find_conflicts(
        points,
        frames,
        args.radius_px,
        args.min_gap_mm,
        args.max_gap_mm,
        args.min_views,
        args.max_normal_angle_deg,
    )
    certified_near_ray, certified_parallel_diagnostic = find_conflicts(
        points,
        frames,
        args.radius_px,
        args.min_gap_mm,
        args.max_gap_mm,
        args.min_views,
        args.max_normal_angle_deg,
        certified_views,
    )
    _, eligible = find_conflicts(
        points,
        frames,
        args.birth_radius_px,
        args.min_gap_mm,
        args.max_gap_mm,
        args.min_views,
        args.max_normal_angle_deg,
        certified_views,
    )
    published, withheld = greedy_birth_owner(points, eligible)
    before_coverage = coverage(
        points, frames, list(range(len(points))), certified_views
    )
    after_coverage = coverage(points, frames, published, certified_views)
    coverage_exact = before_coverage["per_frame_32x18"] == after_coverage["per_frame_32x18"]
    result = {
        "schema": "pocketworld_multiview_wall_birth_ownership_v1",
        "method": "non_destructive_product_birth_identity",
        "internal_hypotheses_unchanged": True,
        "input_ply_unchanged": True,
        "inputs": {
            "stats": {"path": str(stats_path.relative_to(root)), "sha256": sha256(stats_path)},
            "ply": {"path": str(ply_path.relative_to(root)), "sha256": sha256(ply_path)},
            "planes": {"path": str(planes_path.relative_to(root)), "sha256": sha256(planes_path)},
            "frame_meta": {"path": str(meta_path.relative_to(root)), "sha256": sha256(meta_path)},
            "ledger": {"path": str(ledger_path.relative_to(root)), "sha256": sha256(ledger_path)},
            "photo_dir": str(photo_dir.relative_to(root)),
            "birth_evidence": {
                "path": str(evidence_path.relative_to(root)),
                "sha256": sha256(evidence_path),
            },
        },
        "contract": {
            "cross_surface_only": True,
            "diagnostic_radius_px": args.radius_px,
            "birth_radius_px": args.birth_radius_px,
            "depth_gap_mm": [args.min_gap_mm, args.max_gap_mm],
            "min_distinct_registered_views": args.min_views,
            "max_normal_angle_deg": args.max_normal_angle_deg,
            "normal_dominant_separation": True,
            "owner_rank_desc": ["nviews", "zncc_median", "parallax_deg", "lowest_point_index"],
        },
        "counts": {
            "registered_frames": len(frames),
            "input_wall_births": len(points),
            "all_visible_near_ray_pairs_diagnostic": len(all_visible_near_ray),
            "all_visible_parallel_pairs_diagnostic": len(all_visible_parallel),
            "certified_near_ray_conflict_pairs": len(certified_near_ray),
            "certified_parallel_pairs_diagnostic": len(
                certified_parallel_diagnostic
            ),
            "parallel_layer_conflict_pairs_before": len(eligible),
            "withheld_product_identities": len(withheld),
            "published_wall_births": len(published),
            "parallel_layer_conflict_pairs_after": remaining_conflicts(eligible, published),
        },
        "coverage_32x18": {
            "before": before_coverage,
            "after": after_coverage,
            "per_frame_exact": coverage_exact,
        },
        "all_visible_near_ray_conflicts_diagnostic": serialize_pairs(
            all_visible_near_ray, points
        ),
        "all_visible_parallel_conflicts_diagnostic": serialize_pairs(
            all_visible_parallel, points
        ),
        "certified_near_ray_conflicts": serialize_pairs(certified_near_ray, points),
        "certified_parallel_conflicts_diagnostic": serialize_pairs(
            certified_parallel_diagnostic, points
        ),
        "parallel_layer_conflicts": serialize_pairs(eligible, points),
        "published_point_indices": published,
        "withheld_product_identities": withheld,
        "quality_gates": {
            "all_registered_frames_retained": len(frames) == int(stats["inputs"]["photo_count"]),
            "internal_hypotheses_unchanged": True,
            "input_ply_hash_unchanged": sha256(ply_path) == stats["output"]["sha256"],
            "birth_evidence_hash_unchanged": sha256(evidence_path)
            == stats["output"]["birth_evidence_sha256"],
            "parallel_layer_conflicts_after_zero": remaining_conflicts(eligible, published) == 0,
            "image_cell_coverage_exact": coverage_exact,
        },
    }
    result["quality_pass"] = all(result["quality_gates"].values())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "quality_pass": result["quality_pass"],
                **result["counts"],
                "coverage_exact": coverage_exact,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["quality_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
