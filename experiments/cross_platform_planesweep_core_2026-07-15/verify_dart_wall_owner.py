#!/usr/bin/env python3
"""Verify Dart wall-family ownership on all four frozen product scenes."""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import time
from pathlib import Path

import verify_envelope_wall_c_abi as abi
import verify_envelope_wall_product_selection as product


ROOT = Path(__file__).resolve().parents[2]


def current_strict_cache(scene: dict, baseline: dict) -> dict[str, dict]:
    cache = product.strict_cache(baseline)
    for family in scene.get("strict_diagnostics", []):
        for assessment in family["assessments"]:
            cache[assessment["surface_id"]] = assessment
    return cache


def dart_candidate(surface: dict, metrics: dict, strict: dict | None) -> dict:
    result = {
        "candidate_id": surface["surface_id"],
        "theta_deg": surface["theta_deg_in_horizontal_basis"],
        "plane_value": surface["plane_value_n_dot_x"],
        "sparse_score": surface.get("score", 0.0),
        "sparse_support_points": surface.get("support_points_35mm", 0),
        "accepted": int(metrics["accepted"]),
        "coverage_cells_5cm": int(metrics["coverage_cells_5cm"]),
        "median_ncc": float(metrics["zncc_median"] or 0.0),
        "ncc_p10": float(metrics["zncc_p10"] or 0.0),
        "incumbent": bool(
            surface.get("candidate_source_certified_for_generation", False)
        ),
        "strict": None,
    }
    if strict is not None:
        merged = strict["merged_metrics"]
        result["strict"] = {
            "eligible": bool(strict["eligible"]),
            "accepted": int(merged["accepted"]),
            "coverage_cells_5cm": int(merged["coverage_cells_5cm"]),
            "median_ncc": float(merged["zncc_median"] or 0.0),
            "ncc_p10": float(merged["zncc_p10"] or 0.0),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aether-root", type=Path, required=True)
    parser.add_argument("--product-root", type=Path, required=True)
    parser.add_argument("--targeted", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    aether_root = args.aether_root.resolve()
    product_root = args.product_root.resolve()
    library = aether_root / "aether_cpp/build/libaether3d_ffi.dylib"
    api = abi.configure(library)
    targeted = json.loads(args.targeted.read_text())
    targeted_by_capture = {row["capture"]: row for row in targeted["captures"]}
    captures = []
    for capture, paths in product.SCENES.items():
        envelope = json.loads(paths["envelope"].read_text())
        selection = json.loads(paths["selection"].read_text())
        strict_baseline = json.loads(paths["strict"].read_text())
        targeted_scene = targeted_by_capture[capture]
        native = product.native_walls(api, envelope, len(envelope["walls"]))
        changed = set(targeted_scene["changed_candidate_indices"])
        current_envelope = {
            f"wall_envelope_{index}": product.wall_dict(native[index], expected)
            for index, expected in enumerate(envelope["walls"])
        }
        changed_metrics = targeted_scene["changed_candidate_metrics"]
        strict = current_strict_cache(targeted_scene, strict_baseline)
        candidates = []
        for row in selection["candidates"]:
            surface = dict(row["surface"])
            source_id = surface.get("candidate_source_surface_id")
            surface_id = surface["surface_id"]
            if (
                source_id is not None
                and source_id.startswith("wall_envelope_")
                and int(source_id.rsplit("_", 1)[1]) in changed
            ):
                preserved = {
                    key: value
                    for key, value in surface.items()
                    if key.startswith("candidate_source_")
                    or key
                    in {"surface_id", "certified_for_generation", "proposal_only"}
                }
                surface = {**current_envelope[source_id], **preserved}
            metrics = changed_metrics.get(surface_id, row["metrics"])
            candidates.append(dart_candidate(surface, metrics, strict.get(surface_id)))
        command = ["dart", "run", "tool/bcd_wall_owner_check.dart"]
        process = subprocess.run(
            command,
            cwd=product_root,
            input=json.dumps({"candidates": candidates}) + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
        marker = "BCD_RESULT="
        marker_offset = process.stdout.rfind(marker)
        decision = (
            json.loads(process.stdout[marker_offset + len(marker) :].strip())
            if marker_offset >= 0
            else None
        )
        selected_exact = decision is not None and set(
            decision["selected_candidate_ids"]
        ) == set(targeted_scene["expected_final_selected_surface_ids"])
        passed = (
            process.returncode == 0
            and selected_exact
            and decision["required_strict_candidate_ids"] == []
        )
        captures.append(
            {
                "capture": capture,
                "changed_candidate_indices": sorted(changed),
                "dart_exit_code": process.returncode,
                "dart_stdout": process.stdout,
                "dart_stderr": process.stderr,
                "decision": decision,
                "expected_selected_candidate_ids": targeted_scene[
                    "expected_final_selected_surface_ids"
                ],
                "selected_set_exact": selected_exact,
                "verdict": "PASS_DART_WALL_OWNER" if passed else "FAIL",
            }
        )
        print(f"{capture}: {captures[-1]['verdict']}", flush=True)
    passed = all(row["verdict"].startswith("PASS") for row in captures)
    dart_tool = product_root / "tool/bcd_wall_owner_check.dart"
    dart_owner = product_root / "lib/capture/bcd_finalize_coordinator.dart"
    result = {
        "schema": "pocketworld_dart_wall_owner_four_scene_v1",
        "implementation": {
            "native_library": {"path": str(library), "sha256": abi.sha256(library)},
            "dart_tool": {"path": str(dart_tool), "sha256": abi.sha256(dart_tool)},
            "dart_owner": {"path": str(dart_owner), "sha256": abi.sha256(dart_owner)},
            "targeted_product_replay": {
                "path": str(args.targeted),
                "sha256": abi.sha256(args.targeted),
            },
        },
        "captures": captures,
        "elapsed_s": time.perf_counter() - started,
        "forbidden_inputs_consumed": {
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
            "reference_plane": False,
        },
        "verdict": (
            "PASS_CAP40_41_50_51_DART_WALL_OWNER"
            if passed
            else "FAIL"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["verdict"], flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
