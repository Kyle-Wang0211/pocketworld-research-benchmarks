#!/usr/bin/env python3
"""Verify shared structural candidate preparation against the Python oracle."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = (
    ROOT
    / "experiments/floor_plane_sweep_densifier_2026-07-13/"
    "fr_planesweep_wall_ceiling.py"
)
FULL_HELPER_PATH = Path(__file__).resolve().parent / "verify_full_wall_product_c_abi.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class GridSpec(ctypes.Structure):
    _fields_ = [
        ("normal_xyz", ctypes.c_double * 3),
        ("basis_u_xyz", ctypes.c_double * 3),
        ("basis_v_xyz", ctypes.c_double * 3),
        ("plane_value_n_dot_x", ctypes.c_double),
        ("basis_v_origin_value", ctypes.c_double),
        ("u_min", ctypes.c_double),
        ("u_max", ctypes.c_double),
        ("v_min", ctypes.c_double),
        ("v_max", ctypes.c_double),
        ("grid_m", ctypes.c_double),
    ]


class Frame(ctypes.Structure):
    _fields_ = [
        ("projection_row_major_3x4", ctypes.c_double * 12),
        ("camera_center_xyz", ctypes.c_double * 3),
        ("width", ctypes.c_int32),
        ("height", ctypes.c_int32),
    ]


class ViewOptions(ctypes.Structure):
    _fields_ = [
        ("maximum_views", ctypes.c_int32),
        ("image_margin_px", ctypes.c_double),
        ("maximum_graze_deg", ctypes.c_double),
        ("mode", ctypes.c_int32),
    ]


def pointer(values: np.ndarray, scalar):
    return values.ctypes.data_as(ctypes.POINTER(scalar))


def compile_library(aether_root: Path, output: Path) -> list[str]:
    command = [
        "/usr/bin/clang++",
        "-std=c++20",
        "-O2",
        "-fPIC",
        "-dynamiclib",
        "-I",
        str(aether_root / "aether_cpp/include"),
        str(aether_root / "aether_cpp/src/pipeline/aether_structural_candidate_c.cpp"),
        "-o",
        str(output),
    ]
    subprocess.run(command, check=True)
    return command


def load_api(path: Path):
    api = ctypes.CDLL(str(path))
    api.aether_structural_grid_count.argtypes = [
        ctypes.POINTER(GridSpec),
        ctypes.POINTER(ctypes.c_int32),
    ]
    api.aether_structural_grid_count.restype = ctypes.c_int32
    api.aether_structural_grid_build.argtypes = [
        ctypes.POINTER(GridSpec),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int32,
    ]
    api.aether_structural_grid_build.restype = ctypes.c_int32
    api.aether_structural_prepare_views.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int32,
        ctypes.POINTER(Frame),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ViewOptions),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_int32,
    ]
    api.aether_structural_prepare_views.restype = ctypes.c_int32
    return api


def surface_spec(surface: dict, floor: dict, grid_m: float) -> GridSpec:
    normal = np.asarray(surface["normal"], dtype=np.float64)
    basis_u = np.asarray(surface["basis_u"], dtype=np.float64)
    if surface["kind"] == "wall":
        basis_v = np.asarray(floor["normal"], dtype=np.float64)
        v_bounds = surface["bounds_height_m"]
        v_origin = float(floor["plane_value_n_dot_x"])
    else:
        basis_v = np.asarray(surface["basis_v"], dtype=np.float64)
        v_bounds = surface["bounds_v_m"]
        v_origin = 0.0
    return GridSpec(
        (ctypes.c_double * 3)(*normal),
        (ctypes.c_double * 3)(*basis_u),
        (ctypes.c_double * 3)(*basis_v),
        float(surface["plane_value_n_dot_x"]),
        v_origin,
        float(surface["bounds_u_m"][0]),
        float(surface["bounds_u_m"][1]),
        float(v_bounds[0]),
        float(v_bounds[1]),
        float(grid_m),
    )


def c_grid(api, surface: dict, floor: dict, config):
    spec = surface_spec(surface, floor, config.grid_m)
    count = ctypes.c_int32()
    rc = api.aether_structural_grid_count(ctypes.byref(spec), ctypes.byref(count))
    if rc != 0:
        raise RuntimeError(f"grid_count failed: {rc}")
    offsets = np.ascontiguousarray(
        (0.0, *tuple(config.depth_competition_offsets_m)), dtype=np.float64
    )
    centers = np.empty((count.value, 3), dtype=np.float64)
    points = np.empty((count.value * len(offsets), 3), dtype=np.float64)
    rc = api.aether_structural_grid_build(
        ctypes.byref(spec),
        pointer(offsets, ctypes.c_double),
        len(offsets),
        pointer(centers, ctypes.c_double),
        centers.size,
        pointer(points, ctypes.c_double),
        points.size,
    )
    if rc != 0:
        raise RuntimeError(f"grid_build failed: {rc}")
    return centers, points, offsets


def c_frames(frames: list) -> ctypes.Array:
    output = (Frame * len(frames))()
    for index, source in enumerate(frames):
        projection = source.K @ np.column_stack([source.R, source.t])
        output[index].projection_row_major_3x4[:] = projection.reshape(-1)
        output[index].camera_center_xyz[:] = source.C
        output[index].width = source.width
        output[index].height = source.height
    return output


def c_views(
    api,
    centers: np.ndarray,
    points: np.ndarray,
    frames: list,
    normal: np.ndarray,
    config,
    mode: int,
):
    maximum = int(config.max_views)
    native_frames = c_frames(frames)
    options = ViewOptions(
        maximum,
        float(config.image_margin_px),
        float(config.max_graze_deg),
        mode,
    )
    visible = np.zeros((len(points), len(frames)), dtype=np.uint8)
    selected = np.full((len(centers), maximum), -1, dtype=np.int32)
    counts = np.zeros(len(centers), dtype=np.int32)
    unit_normal = np.ascontiguousarray(normal, dtype=np.float64)
    rc = api.aether_structural_prepare_views(
        pointer(np.ascontiguousarray(centers), ctypes.c_double),
        len(centers),
        pointer(np.ascontiguousarray(points), ctypes.c_double),
        len(points),
        native_frames,
        len(frames),
        pointer(unit_normal, ctypes.c_double),
        ctypes.byref(options),
        pointer(visible, ctypes.c_uint8),
        visible.size,
        pointer(selected, ctypes.c_int32),
        selected.size,
        pointer(counts, ctypes.c_int32),
        counts.size,
    )
    if rc != 0:
        raise RuntimeError(f"prepare_views failed: {rc}")
    return visible, selected, counts


def compare_grid(reference, api, surface, floor, config) -> tuple[dict, np.ndarray, np.ndarray]:
    expected_centers = reference.surface_grid(surface, floor, config.grid_m, 0.0)
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    offsets = np.asarray(
        (0.0, *tuple(config.depth_competition_offsets_m)), dtype=np.float64
    )
    expected_points = (
        expected_centers[:, None, :]
        + normal[None, None, :] * offsets[None, :, None]
    ).reshape(-1, 3)
    actual_centers, actual_points, _ = c_grid(api, surface, floor, config)
    return (
        {
            "candidate_count_exact": len(actual_centers) == len(expected_centers),
            "center_max_abs_error": float(
                np.max(np.abs(actual_centers - expected_centers), initial=0.0)
            ),
            "hypothesis_max_abs_error": float(
                np.max(np.abs(actual_points - expected_points), initial=0.0)
            ),
        },
        actual_centers,
        actual_points,
    )


def compare_floor(reference, helper, api, selection_path: Path, photo_dir: Path) -> dict:
    document = json.loads(selection_path.read_text())
    selected = document["selection"]
    winner = next(
        row
        for row in document["candidates"]
        if row["proposal"]["surface_id"] == selected["winner_surface_id"]
    )
    stage = selected["stage"]
    raw_config = (
        document["config"]["fine_top2"]
        if stage.startswith("fine_")
        else document["config"]["coarse"]
    )
    config = helper.config_from_stats(reference, raw_config)
    frames = reference.load_frames(
        ROOT / document["inputs"]["frame_meta"]["path"],
        ROOT / document["inputs"]["ledger"]["path"],
        photo_dir,
    )
    surface = winner["proposal"]
    grid, centers, points = compare_grid(
        reference, api, surface, surface, config
    )
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    actual_visible, actual_selected, actual_counts = c_views(
        api, centers, points, frames, normal, config, 0
    )
    expected_visible, _, _ = reference.project_centers(
        points, frames, normal, config
    )
    center_visible, center_head_on, _ = reference.project_centers(
        centers, frames, normal, config
    )
    expected = [
        reference.select_point_views(
            center_visible[:, index], center_head_on[:, index], config.max_views
        )
        for index in range(len(centers))
    ]
    selected_exact = True
    for index, views in enumerate(expected):
        if actual_counts[index] != len(views) or not np.array_equal(
            actual_selected[index, : len(views)], views
        ):
            selected_exact = False
            break
    return {
        "surface_id": surface["surface_id"],
        "frame_count": len(frames),
        "grid": grid,
        "hypothesis_visibility_exact": np.array_equal(
            actual_visible, expected_visible.T.astype(np.uint8)
        ),
        "selected_views_exact": selected_exact,
    }


def compare_wall(
    reference,
    helper,
    api,
    product_result: dict,
    photo_dir: Path,
) -> dict:
    stats_path = Path(product_result["stats_path"])
    stats = json.loads(stats_path.read_text())
    config = helper.config_from_stats(reference, stats["config"])
    planes = json.loads((ROOT / stats["inputs"]["planes"]["path"]).read_text())
    floor = planes["floor"]
    wanted = {row["surface_id"] for row in product_result["surfaces"]}
    surfaces = [
        surface
        for surface in reference.select_surfaces(planes, None, False)
        if surface["surface_id"] in wanted
    ]
    frames = reference.load_frames(
        ROOT / stats["inputs"]["frame_meta"]["path"],
        ROOT / stats["inputs"]["ledger"]["path"],
        photo_dir,
    )
    surface_rows = []
    for surface in surfaces:
        grid, centers, points = compare_grid(reference, api, surface, floor, config)
        normal = np.asarray(surface["normal"], dtype=np.float64)
        normal /= np.linalg.norm(normal)
        hypotheses = len(config.depth_competition_offsets_m) + 1
        visibility_exact = True
        selected_exact = True
        tile_count = 0
        for start in range(0, len(centers), config.tile_points):
            tile_count += 1
            tile_centers = centers[start : start + config.tile_points]
            tile_points = points[
                start * hypotheses : (start + len(tile_centers)) * hypotheses
            ]
            actual_visible, actual_selected, actual_counts = c_views(
                api, tile_centers, tile_points, frames, normal, config, 1
            )
            expected_visible, _, _ = reference.project_centers(
                tile_points, frames, normal, config
            )
            center_visible, center_head_on, _ = reference.project_centers(
                tile_centers, frames, normal, config
            )
            views = reference.select_tile_views(
                center_visible, center_head_on, config.max_views
            )
            visibility_exact &= np.array_equal(
                actual_visible, expected_visible.T.astype(np.uint8)
            )
            selected_exact &= bool(
                np.all(actual_counts == len(views))
                and all(
                    np.array_equal(row[: len(views)], views)
                    for row in actual_selected
                )
            )
        surface_rows.append(
            {
                "surface_id": surface["surface_id"],
                "tile_count": tile_count,
                "grid": grid,
                "hypothesis_visibility_exact": visibility_exact,
                "selected_views_exact": selected_exact,
            }
        )
    return {"frame_count": len(frames), "surfaces": surface_rows}


def capture_name(path: str) -> str:
    for candidate in ("cap40", "cap41", "cap50", "cap51"):
        if candidate in path:
            return candidate
    raise RuntimeError(f"capture not found in {path}")


def row_passes(row: dict) -> bool:
    return (
        row["grid"]["candidate_count_exact"]
        and row["grid"]["center_max_abs_error"] <= 1e-12
        and row["grid"]["hypothesis_max_abs_error"] <= 1e-12
        and row["hypothesis_visibility_exact"]
        and row["selected_views_exact"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--quality-verdict", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    reference = load_module("pw_candidate_reference", REFERENCE_PATH)
    helper = load_module("pw_candidate_helper", FULL_HELPER_PATH)
    quality = json.loads(args.quality_verdict.read_text())
    photo_dirs: dict[str, Path] = {}
    floor_cases: list[tuple[Path, Path]] = []
    for entry in quality["inputs"]["c_floor"]:
        product = json.loads(Path(entry["path"]).read_text())
        for case in product["cases"]:
            name = case["capture"]
            photo_dirs[name] = Path(case["photo_dir"])
            floor_cases.append((Path(case["selection_path"]), Path(case["photo_dir"])))
    with tempfile.TemporaryDirectory(prefix="pw_structural_candidate_") as temp:
        library = Path(temp) / "libstructural_candidate.dylib"
        compile_command = compile_library(args.aether_root.resolve(), library)
        api = load_api(library)
        floors = []
        for selection, photos in floor_cases:
            name = capture_name(str(selection))
            floors.append(
                {
                    "capture": name,
                    **compare_floor(reference, helper, api, selection, photos),
                }
            )
        walls = []
        for entry in quality["inputs"]["c_wall"]:
            product = json.loads(Path(entry["path"]).read_text())
            name = capture_name(product["stats_path"])
            walls.append(
                {
                    "capture": name,
                    **compare_wall(reference, helper, api, product, photo_dirs[name]),
                }
            )
    passed = all(row_passes(row) for row in floors) and all(
        row_passes(surface)
        for wall in walls
        for surface in wall["surfaces"]
    )
    source = (
        args.aether_root.resolve()
        / "aether_cpp/src/pipeline/aether_structural_candidate_c.cpp"
    )
    result = {
        "schema": "pocketworld_structural_candidate_c_abi_parity_v1",
        "decision": (
            "PASS_STRUCTURAL_CANDIDATE_C_ABI_EXACT_PARITY"
            if passed
            else "FAIL_STRUCTURAL_CANDIDATE_C_ABI_PARITY"
        ),
        "quality_verdict": str(args.quality_verdict.resolve()),
        "compile_command": compile_command,
        "source": str(source),
        "source_sha256": sha256(source),
        "elapsed_s": time.perf_counter() - started,
        "floor_cases": floors,
        "wall_cases": walls,
        "forbidden_inputs_consumed": {
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
