#!/usr/bin/env python3
"""Replay only changed shared-C wall candidates through product ownership."""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

import verify_envelope_wall_c_abi as abi


ROOT = Path(__file__).resolve().parents[2]
SCENES = {
    "cap40": {
        "envelope": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap40_bed_scene_20260716/wall_envelope_proposals_tls_v3.json",
        "selection": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap40_bed_scene_20260716/wall_owner_union_selection_v3.json",
        "strict": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap40_bed_scene_20260716/wall_owner_strict_adjudication_v1.json",
        "photos": ROOT / "data/pocketworld_captures/cap40/device_2026-07-16/photos_highres",
    },
    "cap41": {
        "envelope": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap41_bed_scene_20260716/wall_envelope_proposals_tls_v3.json",
        "selection": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap41_bed_scene_20260716/wall_owner_union_selection_v3.json",
        "strict": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap41_bed_scene_20260716/wall_owner_strict_adjudication_v1.json",
        "photos": ROOT / "data/pocketworld_captures/cap41/device_2026-07-16/photos_highres",
    },
    "cap50": {
        "envelope": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap50_wall_envelope_proposals_tls_v3.json",
        "selection": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap50_wall_owner_incumbent_selection_v3.json",
        "strict": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap50_wall_owner_strict_adjudication_v1.json",
        "photos": ROOT / "data/pocketworld_captures/cap50/raw/photos_highres",
    },
    "cap51": {
        "envelope": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap51_wall_envelope_proposals_tls_v3.json",
        "selection": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap51_wall_owner_incumbent_selection_v3.json",
        "strict": ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/runs/cap51_wall_owner_strict_adjudication_v1.json",
        "photos": ROOT / "data/pocketworld_captures/cap51/photos_highres_device_2026-07-16",
    },
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def native_walls(api, envelope: dict, maximum: int) -> list[abi.Wall]:
    cloud = ROOT / envelope["inputs"]["metric_cloud"]["path"]
    floor_path = ROOT / envelope["inputs"]["floor_selection"]["path"]
    frame_path = ROOT / envelope["inputs"]["frame_meta"]["path"]
    xyz = np.ascontiguousarray(np.load(cloud)["xyz"], dtype=np.float32)
    cameras = abi.camera_centers(frame_path)
    floor = abi.selected_floor(floor_path)
    options = abi.Options()
    api.aether_structural_envelope_wall_options_default(ctypes.byref(options))
    options.maximum_candidates = maximum
    walls = (abi.Wall * maximum)()
    count = ctypes.c_int32()
    normal = (ctypes.c_double * 3)(*floor["normal"])
    rc = api.aether_structural_propose_envelope_walls(
        xyz.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        len(xyz),
        cameras.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        len(cameras),
        normal,
        floor["plane_value_n_dot_x"],
        ctypes.byref(options),
        walls,
        maximum,
        ctypes.byref(count),
    )
    if rc != 0 or count.value != maximum:
        raise RuntimeError(f"shared-C envelope failed rc={rc}, count={count.value}")
    return [walls[index] for index in range(count.value)]


def wall_dict(wall: abi.Wall, reference: dict) -> dict:
    result = dict(reference)
    result.update(
        {
            "support_points_35mm": wall.support_points_35mm,
            "coverage_cells_10cm": wall.coverage_cells_10cm,
            "theta_deg_in_horizontal_basis": wall.theta_deg,
            "normal": list(wall.normal_xyz),
            "basis_u": list(wall.basis_u_xyz),
            "basis_v": list(wall.basis_v_xyz),
            "plane_value_n_dot_x": wall.plane_value_n_dot_x,
            "bounds_u_m": list(wall.bounds_u_m),
            "bounds_height_m": list(wall.bounds_height_m),
            "score": wall.score,
            "camera_distance_min_m": wall.camera_distance_min_m,
            "camera_distance_max_m": wall.camera_distance_max_m,
            "camera_clearance_min_abs_m": wall.camera_clearance_min_abs_m,
        }
    )
    return result


def recompute_base(selector, surfaces: list[dict], rows: list[dict]) -> tuple[list[str], list[dict]]:
    selected_ids: list[str] = []
    families = []
    for family_index, indices in enumerate(selector.competing_families(surfaces)):
        ranking = sorted(
            indices,
            key=lambda index: (
                rows[index]["winner_score"],
                rows[index]["metrics"]["accepted"],
            ),
            reverse=True,
        )
        evidence_winner = rows[ranking[0]]
        evidence_runner = rows[ranking[1]] if len(ranking) > 1 else None
        incumbent_rows = [
            rows[index] for index in indices if selector.is_incumbent(surfaces[index])
        ]
        incumbent = max(
            (row for row in incumbent_rows if selector.passes_birth_minimum(row)),
            key=lambda row: row["winner_score"],
            default=None,
        )
        if incumbent is None:
            winner = evidence_winner
            decisive = selector.decisively_beats(
                winner, evidence_runner, allow_dual_evidence=True
            )
        elif evidence_winner is incumbent:
            winner = incumbent
            decisive = True
        elif selector.decisively_beats(evidence_winner, incumbent):
            winner = evidence_winner
            decisive = True
        else:
            winner = incumbent
            decisive = True
        winner_id = winner["surface"]["surface_id"] if decisive else None
        if winner_id is not None:
            selected_ids.append(winner_id)
        families.append(
            {
                "family_index": family_index,
                "candidate_surface_ids": [
                    surfaces[index]["surface_id"] for index in indices
                ],
                "winner_surface_id": winner_id,
            }
        )
    return selected_ids, families


def strict_cache(document: dict) -> dict[str, dict]:
    return {
        assessment["surface_id"]: assessment
        for adjudication in document["adjudications"]
        for assessment in adjudication["assessments"]
    }


def main() -> int:
    started_at = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    aether_root = args.aether_root.resolve()
    library = aether_root / "aether_cpp/build/libaether3d_ffi.dylib"
    api = abi.configure(library)
    selector = load_module(
        "aether_targeted_wall_selector",
        ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/select_wall_plane_candidates.py",
    )
    adjudicator = load_module(
        "aether_targeted_wall_adjudicator",
        ROOT / "experiments/cross_platform_planesweep_core_2026-07-15/adjudicate_ambiguous_wall_families.py",
    )
    runner = selector.load_runner()
    results = []
    for capture, paths in SCENES.items():
        print(f"{capture}: loading frozen evidence", flush=True)
        envelope = json.loads(paths["envelope"].read_text())
        baseline = json.loads(paths["selection"].read_text())
        strict_baseline = json.loads(paths["strict"].read_text())
        native = native_walls(api, envelope, len(envelope["walls"]))
        changed_indices = [
            index
            for index, (actual, expected) in enumerate(zip(native, envelope["walls"]))
            if not abi.compare(actual, expected, index)["pass"]
        ]
        changed_ids = {f"envelope__wall_envelope_{index}" for index in changed_indices}
        actual_envelope = {
            f"wall_envelope_{index}": wall_dict(native[index], expected)
            for index, expected in enumerate(envelope["walls"])
        }
        frame_path = ROOT / baseline["inputs"]["frame_meta"]["path"]
        ledger_path = ROOT / baseline["inputs"]["ledger"]["path"]
        frames = runner.load_frames(frame_path, ledger_path, paths["photos"])
        config_values = dict(baseline["config"]["sweep"])
        config_values["depth_competition_offsets_m"] = tuple(
            config_values["depth_competition_offsets_m"]
        )
        config = runner.SweepConfig(**config_values)
        surfaces = []
        rows = []
        changed_metrics = {}
        for baseline_row in baseline["candidates"]:
            surface = dict(baseline_row["surface"])
            source_id = surface.get("candidate_source_surface_id")
            if surface["surface_id"] in changed_ids:
                replacement = actual_envelope[source_id]
                preserved = {
                    key: value
                    for key, value in surface.items()
                    if key.startswith("candidate_source_")
                    or key in {"surface_id", "certified_for_generation", "proposal_only"}
                }
                surface = {**replacement, **preserved}
                print(f"{capture}: replay base {surface['surface_id']}", flush=True)
                _, _, _, metrics = runner.sweep_surface(
                    surface, baseline["floor"], frames, config, 0.0
                )
                changed_metrics[surface["surface_id"]] = metrics
            else:
                metrics = baseline_row["metrics"]
            row = {
                "surface": surface,
                "metrics": metrics,
                "winner_score": selector.candidate_score(metrics),
            }
            surfaces.append(surface)
            rows.append(row)
        base_selected, families = recompute_base(selector, surfaces, rows)
        row_by_id = {row["surface"]["surface_id"]: row for row in rows}
        final_selected = list(base_selected)
        final_set = set(final_selected)
        cached = strict_cache(strict_baseline)
        rerun_strict = []
        strict_diagnostics = []
        for family in families:
            if family["winner_surface_id"] is not None:
                continue
            contenders = [
                row_by_id[surface_id]
                for surface_id in family["candidate_surface_ids"]
                if selector.passes_birth_minimum(row_by_id[surface_id])
            ]
            if len(contenders) < 2:
                continue
            assessments = []
            for row in contenders:
                surface_id = row["surface"]["surface_id"]
                if surface_id in changed_ids or surface_id not in cached:
                    print(f"{capture}: replay strict {surface_id}", flush=True)
                    assessment = adjudicator.strict_assessment(
                        runner, row["surface"], baseline["floor"], frames, config
                    )
                    rerun_strict.append(surface_id)
                else:
                    assessment = cached[surface_id]
                assessments.append(assessment)
            eligible = sorted(
                (row for row in assessments if row["eligible"]),
                key=lambda row: (
                    row["winner_score"],
                    int(row["merged_metrics"]["accepted"]),
                ),
                reverse=True,
            )
            winner_id = None
            if len(eligible) == 1:
                winner_id = eligible[0]["surface_id"]
            elif len(eligible) >= 2:
                winner, runner_up = eligible[:2]
                if (
                    winner["winner_score"] >= runner_up["winner_score"] * 1.25
                    and int(winner["merged_metrics"]["accepted"])
                    >= int(runner_up["merged_metrics"]["accepted"]) + 3
                ):
                    winner_id = winner["surface_id"]
            if winner_id is not None and winner_id not in final_set:
                final_selected.append(winner_id)
                final_set.add(winner_id)
            strict_diagnostics.append(
                {
                    "family_index": family["family_index"],
                    "winner_surface_id": winner_id,
                    "assessments": assessments,
                }
            )
        expected_base = baseline["selected_surface_ids"]
        expected_final = strict_baseline["selected_surface_ids"]
        base_exact = set(base_selected) == set(expected_base)
        final_exact = set(final_selected) == set(expected_final)
        scene_pass = base_exact and final_exact
        results.append(
            {
                "capture": capture,
                "changed_candidate_indices": changed_indices,
                "changed_candidate_metrics": changed_metrics,
                "rerun_strict_surface_ids": rerun_strict,
                "strict_diagnostics": strict_diagnostics,
                "base_selected_surface_ids": base_selected,
                "expected_base_selected_surface_ids": expected_base,
                "final_selected_surface_ids": final_selected,
                "expected_final_selected_surface_ids": expected_final,
                "base_selected_set_exact": base_exact,
                "final_selected_set_exact": final_exact,
                "verdict": "PASS_PRODUCT_WALL_OWNERS_UNCHANGED" if scene_pass else "FAIL",
            }
        )
        print(f"{capture}: {results[-1]['verdict']}", flush=True)
    passed = all(row["verdict"].startswith("PASS") for row in results)
    result = {
        "schema": "pocketworld_envelope_wall_targeted_product_selection_v1",
        "method": "exact_candidates_reuse_frozen_evidence_changed_candidates_replay",
        "implementation": {
            "library": {"path": str(library), "sha256": abi.sha256(library)},
        },
        "captures": results,
        "forbidden_inputs_consumed": {
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
            "reference_plane": False,
        },
        "elapsed_s": time.perf_counter() - started_at,
        "verdict": "PASS_CAP40_41_50_51_PRODUCT_WALL_OWNERS_UNCHANGED" if passed else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"verdict": result["verdict"]}, sort_keys=True), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
