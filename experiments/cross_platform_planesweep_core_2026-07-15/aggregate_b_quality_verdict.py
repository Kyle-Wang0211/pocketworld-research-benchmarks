#!/usr/bin/env python3
"""Aggregate the fixed four-scene B quality gate before speed optimization."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_scene(value: str) -> tuple[str, Path, Path, Path]:
    fields = value.split("|", 3)
    if len(fields) != 4:
        raise ValueError(
            "--scene must be CAPTURE|FLOOR_SELECTION|WALL_STATS|WALL_OWNERSHIP"
        )
    return fields[0], Path(fields[1]), Path(fields[2]), Path(fields[3])


def all_false(values: dict) -> bool:
    return all(value is False for value in values.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")

    scenes = {}
    for capture, floor_path, wall_path, owner_path in map(parse_scene, args.scene):
        floor = json.loads(floor_path.read_text())
        wall = json.loads(wall_path.read_text())
        ownership = json.loads(owner_path.read_text())
        wall_ply = Path(wall["output"]["ply"])
        evidence = Path(wall["output"]["birth_evidence"])
        floor_forbidden = floor["forbidden_inputs_consumed"]
        floor_gates = {
            "decisive_image_only_selection": bool(floor["selection"]["decisive"]),
            "selected_floor_within_3cm_reference": bool(
                floor["evaluation"]["pass_within_3cm"]
            ),
            "reference_read_only_after_selection": bool(
                floor["evaluation"]["reference_read_after_selection"]
            ),
            "forbidden_floor_inputs_all_false": all_false(floor_forbidden),
            "pass_verdict": str(floor["verdict"]).startswith("PASS_"),
        }
        wall_gates = {
            "plane_sweep_consumed_no_matcher_output": wall[
                "forbidden_matcher_outputs_consumed"
            ]
            is False,
            "wall_ply_hash_matches": sha256(wall_ply) == wall["output"]["sha256"],
            "birth_evidence_hash_matches": sha256(evidence)
            == wall["output"]["birth_evidence_sha256"],
            "birth_owner_quality_pass": ownership["quality_pass"] is True,
            "all_registered_input_frames_retained": ownership["quality_gates"][
                "all_registered_frames_retained"
            ]
            is True,
            "certified_image_coverage_exact": ownership["quality_gates"][
                "image_cell_coverage_exact"
            ]
            is True,
            "exact_site_conflicts_after_zero": ownership["counts"][
                "parallel_layer_conflict_pairs_after"
            ]
            == 0,
            "no_wall_birth_count_loss": ownership["counts"]["published_wall_births"]
            == ownership["counts"]["input_wall_births"],
        }
        scene_pass = all(floor_gates.values()) and all(wall_gates.values())
        scenes[capture] = {
            "quality_pass": scene_pass,
            "inputs": {
                "floor_selection": {
                    "path": str(floor_path),
                    "sha256": sha256(floor_path),
                },
                "wall_stats": {"path": str(wall_path), "sha256": sha256(wall_path)},
                "wall_ownership": {
                    "path": str(owner_path),
                    "sha256": sha256(owner_path),
                },
            },
            "floor": {
                "winner_surface_id": floor["selection"]["winner_surface_id"],
                "accepted": floor["selection"]["accepted"],
                "runner_up_accepted": floor["selection"]["runner_up_accepted"],
                "absolute_reference_error_m": floor["evaluation"][
                    "absolute_value_error_m"
                ],
                "elapsed_python_oracle_s": floor["elapsed_s"],
                "gates": floor_gates,
            },
            "walls": {
                "surface_count": len(wall["surfaces"]),
                "published_births": ownership["counts"]["published_wall_births"],
                "registered_frames": ownership["counts"]["registered_frames"],
                "certified_near_ray_pairs_8px_diagnostic": ownership["counts"][
                    "certified_near_ray_conflict_pairs"
                ],
                "exact_site_conflicts_before": ownership["counts"][
                    "parallel_layer_conflict_pairs_before"
                ],
                "exact_site_conflicts_after": ownership["counts"][
                    "parallel_layer_conflict_pairs_after"
                ],
                "elapsed_python_oracle_s": wall["totals"]["elapsed_s"],
                "gates": wall_gates,
            },
        }

    expected = {"cap40", "cap41", "cap50", "cap51"}
    result = {
        "schema": "pocketworld_b_quality_four_scene_verdict_v1",
        "scope": "B pure-A known-plane floor and wall birth quality only",
        "speed_gate_deferred": True,
        "production_integration_authorized": False,
        "fixed_scene_set_exact": set(scenes) == expected,
        "forbidden_inputs": {
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
        },
        "scenes": scenes,
    }
    result["quality_pass"] = result["fixed_scene_set_exact"] and all(
        row["quality_pass"] for row in scenes.values()
    )
    result["verdict"] = (
        "PASS_B_QUALITY_BEGIN_C_SPEED_GATE"
        if result["quality_pass"]
        else "FAIL_B_QUALITY_DO_NOT_OPTIMIZE_OR_INTEGRATE"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "quality_pass": result["quality_pass"],
                "verdict": result["verdict"],
                "scenes": {
                    name: {
                        "quality_pass": row["quality_pass"],
                        "floor_accepted": row["floor"]["accepted"],
                        "wall_births": row["walls"]["published_births"],
                        "diagnostic_8px_pairs": row["walls"][
                            "certified_near_ray_pairs_8px_diagnostic"
                        ],
                        "exact_site_conflicts": row["walls"][
                            "exact_site_conflicts_after"
                        ],
                    }
                    for name, row in scenes.items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["quality_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
