#!/usr/bin/env python3
"""Generate cross-platform sparse wall proposals from an auto-selected floor.

The selected floor and sparse XYZ are the only geometric inputs.  Image
evidence is deliberately deferred to the pure-A plane-sweep birth gate; these
proposals alone never authorize product points.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

import verify_structural_plane_fit_c_abi as abi


def selected_floor(path: Path) -> dict:
    result = json.loads(path.read_text())
    selection = result["selection"]
    if not selection["decisive"] or not selection["winner_surface_id"]:
        raise RuntimeError("floor selection is not decisive")
    winner_id = selection["winner_surface_id"]
    for candidate in result["candidates"]:
        if candidate["proposal"]["surface_id"] == winner_id:
            return candidate["proposal"]
    raise RuntimeError(f"selected floor {winner_id!r} is absent from candidates")


def serialize_wall(wall: abi.Wall) -> dict:
    return {
        "surface_id": f"wall_proposal_{wall.wall_index}",
        "kind": "wall",
        "proposal_only": True,
        "certified_for_generation": bool(wall.certified),
        "sparse_structural_certified": bool(wall.certified),
        "theta_deg_in_horizontal_basis": wall.theta_deg,
        "support_points_35mm": wall.support_points_35mm,
        "coverage_cells_10cm": wall.coverage_cells_10cm,
        "domain_points": wall.domain_points,
        "support_points_20mm_offsets_minus10_to_plus10cm": list(
            wall.support_points_20mm
        ),
        "support_cells_10cm_offsets_minus10_to_plus10cm": list(
            wall.support_cells_10cm
        ),
        "normal": list(wall.normal_xyz),
        "basis_u": list(wall.basis_u_xyz),
        "basis_v": list(wall.basis_v_xyz),
        "plane_value_n_dot_x": wall.plane_value_n_dot_x,
        "bounds_u_m": list(wall.bounds_u_m),
        "bounds_height_m": list(wall.bounds_height_m),
        "score": wall.score,
        "support_prominence_vs_5cm": wall.support_prominence_vs_5cm,
        "coverage_prominence_vs_5cm": wall.coverage_prominence_vs_5cm,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--metric-cloud", type=Path, required=True)
    parser.add_argument("--floor-selection", type=Path, required=True)
    parser.add_argument("--maximum-walls", type=int, default=6)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = (
        args.aether_root.resolve()
        / "aether_cpp/src/pipeline/aether_structural_plane_fit_c.cpp"
    )
    include = args.aether_root.resolve() / "aether_cpp/include"
    xyz = np.ascontiguousarray(np.load(args.metric_cloud)["xyz"], np.float32)
    floor = selected_floor(args.floor_selection)
    compile_command: list[str]
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pw_wall_proposals_") as temp:
        library = Path(temp) / "libstructural_plane_fit.dylib"
        compile_command = [
            "clang++",
            "-std=c++20",
            "-O2",
            "-fno-exceptions",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-dynamiclib",
            "-I",
            str(include),
            str(source),
            "-o",
            str(library),
        ]
        subprocess.run(compile_command, check=True)
        api = abi.configure_api(library)
        options = abi.FitOptions()
        api.aether_structural_plane_fit_options_default(ctypes.byref(options))
        if args.maximum_walls <= 0:
            raise ValueError("maximum-walls must be positive")
        options.max_walls = args.maximum_walls
        output_walls = (abi.Wall * options.max_walls)()
        output_count = ctypes.c_int32()
        normal = (ctypes.c_double * 3)(*floor["normal"])
        fit_started = time.perf_counter()
        rc = api.aether_structural_fit_walls(
            xyz.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            len(xyz),
            normal,
            floor["plane_value_n_dot_x"],
            ctypes.byref(options),
            output_walls,
            options.max_walls,
            ctypes.byref(output_count),
        )
        fit_elapsed_ms = (time.perf_counter() - fit_started) * 1000.0

    walls = [serialize_wall(output_walls[i]) for i in range(output_count.value)]
    result = {
        "schema": "aether_sparse_wall_proposals_c_abi_v1",
        "method": "gravity_floor_conditioned_sparse_hough_proposals",
        "forbidden_inputs_consumed": {
            "images": False,
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
            "reference_plane": False,
        },
        "birth_authority": False,
        "inputs": {
            "metric_cloud": {
                "path": str(args.metric_cloud),
                "sha256": abi.sha256(args.metric_cloud),
                "point_count": len(xyz),
            },
            "floor_selection": {
                "path": str(args.floor_selection),
                "sha256": abi.sha256(args.floor_selection),
            },
        },
        "implementation": {"source": str(source), "sha256": abi.sha256(source)},
        "compile_command": compile_command,
        "floor": floor,
        "fit_options": {
            name: getattr(options, name) for name, _ in options._fields_
        },
        "rc": rc,
        "wall_count": output_count.value,
        "fit_elapsed_ms": fit_elapsed_ms,
        "elapsed_s": time.perf_counter() - started,
        "walls": walls,
        "surfaces": walls,
        "verdict": "PASS_PROPOSALS_ONLY" if rc == 0 else "FAIL_CLOSED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
