#!/usr/bin/env python3
"""Assemble the non-device B/C/D speed preflight without overclaiming A16."""

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


def identity(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, action="append", required=True)
    parser.add_argument("--jpeg", type=Path, action="append", required=True)
    parser.add_argument("--d-quality", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    quality = json.loads(args.quality.read_text())
    runtimes = [json.loads(path.read_text()) for path in args.runtime]
    jpegs = [json.loads(path.read_text()) for path in args.jpeg]
    d_quality = json.loads(args.d_quality.read_text())

    quality_pass = quality["decision"] == "PASS_BCD_FOUR_SCENE_QUALITY_ONLY"
    runtime_pass = len(runtimes) >= 2 and all(
        item["decision"] == "PASS_HOST_DAWN_GEOMETRY_AND_CLIQUE_RGB_EXACT_PARITY"
        and item["sessions_deterministic"]
        and item["accepted_rgb_exact"]
        and item["warm_create_median_ms"] < item["cold_create_ms"]
        for item in runtimes
    )
    jpeg_pass = len(jpegs) >= 2 and all(
        item["decision"] == "PASS_EXACT_PARITY_AND_MULTISCALE_JPEG_SPEED"
        and item["single_vs_multi_results_and_rgb_exact"]
        and item["speed_non_regression"]
        and item["add_speedup_ratio"] > 1.0
        for item in jpegs
    )
    d_timing = d_quality["c_abi"]["timing_ms"]
    d_pass = (
        d_quality["c_abi"]["all_masks_exact"]
        and d_timing["total_birth_ownership"] < 400.0
        and d_quality["totals"]["c_abi_birth_mismatches"] == 0
    )
    passed = quality_pass and runtime_pass and jpeg_pass and d_pass
    result = {
        "schema": "pocketworld_bcd_host_speed_preflight_v1",
        "decision": (
            "PASS_BCD_HOST_SPEED_PREFLIGHT"
            if passed
            else "FAIL_BCD_HOST_SPEED_PREFLIGHT"
        ),
        "quality_still_passing": quality_pass,
        "component_gates": {
            "shared_dawn_runtime_exact_and_faster": runtime_pass,
            "one_decode_all_scales_exact_and_faster": jpeg_pass,
            "d_birth_ownership_exact_and_under_400ms_four_scenes": d_pass,
        },
        "measurements": {
            "runtime": [
                {
                    "cold_create_ms": item["cold_create_ms"],
                    "warm_create_median_ms": item["warm_create_median_ms"],
                    "saved_percent": (
                        1.0
                        - item["warm_create_median_ms"] / item["cold_create_ms"]
                    )
                    * 100.0,
                }
                for item in runtimes
            ],
            "jpeg": [
                {
                    "old_add_median_ms": item[
                        "single_decode_per_scale_add_median_ms"
                    ],
                    "new_add_median_ms": item[
                        "one_decode_all_scales_add_median_ms"
                    ],
                    "speedup_ratio": item["add_speedup_ratio"],
                    "saved_percent": item["add_time_saved_percent"],
                }
                for item in jpegs
            ],
            "d_birth_ownership_four_scenes_ms": d_timing,
        },
        "device_speed_gate": "PENDING_A16_AFTER_PRODUCT_ORCHESTRATION",
        "production_integration_authorized": False,
        "inputs": {
            "quality": identity(args.quality),
            "runtime": [identity(path) for path in args.runtime],
            "jpeg": [identity(path) for path in args.jpeg],
            "d_quality": identity(args.d_quality),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
