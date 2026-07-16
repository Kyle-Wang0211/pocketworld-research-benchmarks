#!/usr/bin/env python3
"""Bind the frozen B oracle to exact Dart/C++ four-scene replays.

The oracle verdict retains the independently established structural plane
identities consumed by D ownership.  A product replay may only strengthen that
evidence: every scene must preserve the sparse cloud and registered views,
select the expected owners, and publish the exact expected additive births.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


CAPTURES = {"cap40", "cap41", "cap50", "cap51"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--dart-result", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")

    oracle_path = args.oracle.resolve()
    oracle = json.loads(oracle_path.read_text())
    if oracle.get("quality_pass") is not True:
        raise RuntimeError("frozen B oracle is not passing")
    if set(oracle.get("scenes", {})) != CAPTURES:
        raise RuntimeError("frozen B oracle does not contain the exact scene set")

    replays: dict[str, tuple[Path, dict]] = {}
    for raw_path in args.dart_result:
        path = raw_path.resolve()
        replay = json.loads(path.read_text())
        capture = replay.get("capture")
        if capture not in CAPTURES:
            raise RuntimeError(f"unexpected Dart replay capture: {capture!r}")
        if capture in replays:
            raise RuntimeError(f"duplicate Dart replay capture: {capture}")
        replays[capture] = (path, replay)
    if set(replays) != CAPTURES:
        raise RuntimeError("Dart replays do not contain the exact scene set")

    scenes = {}
    all_passed = True
    for capture in sorted(CAPTURES):
        path, replay = replays[capture]
        oracle_scene = oracle["scenes"][capture]
        expected = replay.get("expected", {})
        births = replay.get("birth_points", {})
        forbidden = replay.get("forbidden_inputs_consumed", {})
        gates = {
            "quality_passed": replay.get("quality_passed") is True,
            "expected_owners_exact": (
                replay.get("expected_owners_matched_exact") is True
            ),
            "expected_births_exact": (
                replay.get("expected_birth_count_matched_exact") is True
            ),
            "original_sparse_untouched_exact": (
                replay.get("original_sparse_untouched_exact") is True
            ),
            "registered_views_exact": (
                replay.get("registered_views")
                == oracle_scene["walls"]["registered_frames"]
            ),
            "wall_births_match_embedded_contract": (
                births.get("wall") == expected.get("wall_births")
            ),
            "floor_births_match_embedded_contract": (
                births.get("floor") == expected.get("floor_births")
            ),
            "structural_total_match_embedded_contract": (
                births.get("structural_total")
                == expected.get("structural_birth_points")
            ),
            "forbidden_inputs_all_false": (
                forbidden
                == {
                    "learned_matcher": False,
                    "lidar": False,
                    "scene_depth": False,
                }
            ),
        }
        scene_passed = all(gates.values())
        all_passed = all_passed and scene_passed
        scene = dict(oracle_scene)
        scene["dart_product_replay"] = {
            "path": str(path),
            "sha256": sha256(path),
            "quality_pass": scene_passed,
            "gates": gates,
            "original_sparse_points": replay.get("original_sparse_points"),
            "registered_views": replay.get("registered_views"),
            "floor_births": births.get("floor"),
            "wall_births": births.get("wall"),
            "structural_birth_points": births.get("structural_total"),
            "floor_winner_proposal_index": replay.get("floor", {}).get(
                "winner_proposal_index"
            ),
            "wall_selected_candidate_ids": replay.get("walls", {}).get(
                "selected_candidate_ids"
            ),
            "elapsed_ms": replay.get("elapsed_ms"),
        }
        scene["quality_pass"] = oracle_scene.get("quality_pass") is True and scene_passed
        scenes[capture] = scene

    result = {
        "schema": "pocketworld_bcd_dart_product_quality_four_scene_v1",
        "scope": "B/C Dart orchestration and shared C++/WGSL exact quality replay",
        "oracle": {"path": str(oracle_path), "sha256": sha256(oracle_path)},
        "fixed_scene_set_exact": True,
        "original_sparse_points_removed": 0,
        "forbidden_inputs": {
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
        },
        "production_integration_authorized": False,
        "scenes": scenes,
        "quality_pass": all_passed and all(
            scene["quality_pass"] for scene in scenes.values()
        ),
    }
    result["verdict"] = (
        "PASS_BC_DART_PRODUCT_QUALITY_BEGIN_D_JOINT_GATE"
        if result["quality_pass"]
        else "FAIL_BC_DART_PRODUCT_QUALITY"
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
                    capture: {
                        "quality_pass": scene["quality_pass"],
                        "floor_births": scene["dart_product_replay"]["floor_births"],
                        "wall_births": scene["dart_product_replay"]["wall_births"],
                    }
                    for capture, scene in scenes.items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["quality_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
