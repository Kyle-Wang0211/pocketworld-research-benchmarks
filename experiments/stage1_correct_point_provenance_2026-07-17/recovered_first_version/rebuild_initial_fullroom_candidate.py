#!/usr/bin/env python3
"""Rebuild the original cap50/cap51 full-room visual candidates.

The candidates intentionally predate the later 1 cm structural publication and
all subsequent sparse-cloud birth gates.  Each output is strictly additive:

  immutable device sparse + frozen first B/C structural births + frozen D births

No original point is filtered, deduplicated, recoloured, or moved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np


EXPERIMENTS = Path(__file__).resolve().parents[2]
REPOSITORY = EXPERIMENTS.parent
sys.path.insert(0, str(EXPERIMENTS / "full_stack_visual_2026-07-16"))

from assemble_full_stack import (  # noqa: E402
    AssemblyError,
    Cloud,
    canonical_payload,
    read_rgb_ply,
    sha256_file,
    umeyama,
)


CAPTURES = {
    "cap50": {
        "original": REPOSITORY
        / "data/pocketworld_captures/cap50/sfm/sfm_sparse.ply",
        "original_sha256": "a41bd10f9d5832f9f98bbbaf8d566890d21d2bffa7d3142da27db0bfdb8f36df",
        "original_points": 92849,
        "bc": Path(__file__).resolve().parent / "cap50_bc_176_metric_exact.ply",
        "bc_sha256": "e4d07c4e03e48c4bb46e1cba19f8a8a107f73fee71a5564a686b0ed54048be5f",
        "bc_total_points": 93025,
        "bc_births": 176,
        "d": Path(__file__).resolve().parent / "cap50_d_27124_raw_exact.ply",
        "d_sha256": "8e999468b7a0e2960b6a23879e16b47ddbdf742c8cba54cc645bbac51c4c0e7e",
        "d_births": 27124,
        "total_points": 120149,
    },
    "cap51": {
        "original": REPOSITORY
        / "data/pocketworld_captures/cap51/sfm/sfm_sparse.ply",
        "original_sha256": "fb2db1e1ee89692ed47b0bd3d38773fc42f37ecb94ccd485fc7a1952b13fe3f7",
        "original_points": 64392,
        "bc": Path(__file__).resolve().parent / "cap51_bc_182_metric_exact.ply",
        "bc_sha256": "eb435998415ac118187ceba9e7992f38083b87891c9cea9453f5cf90f53972e6",
        "bc_total_points": 64574,
        "bc_births": 182,
        "d": Path(__file__).resolve().parent / "cap51_d_16483_raw_exact.ply",
        "d_sha256": "96e0283cbebcedac925320f40e10418452fc1e3ca4f274f1d1ff6e99812d138c",
        "d_births": 16483,
        "total_points": 81057,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", choices=sorted(CAPTURES))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def checked(path: Path, expected_sha256: str, label: str) -> Cloud:
    observed = sha256_file(path)
    if observed != expected_sha256:
        raise AssemblyError(
            f"{label} SHA mismatch: expected {expected_sha256}, observed {observed}"
        )
    return read_rgb_ply(path)


def main() -> None:
    args = parse_args()
    contract = CAPTURES[args.capture]
    original = checked(
        contract["original"], contract["original_sha256"], "device original"
    )
    bc = checked(contract["bc"], contract["bc_sha256"], "first B/C")
    d = checked(contract["d"], contract["d_sha256"], "first D")

    original_points = int(contract["original_points"])
    if len(original.xyz) != original_points:
        raise AssemblyError("device original point count changed")
    if len(bc.xyz) != int(contract["bc_total_points"]):
        raise AssemblyError("first B/C point count changed")
    if len(d.xyz) != int(contract["d_births"]):
        raise AssemblyError("first D point count changed")
    if not np.array_equal(original.rgb, bc.rgb[:original_points]):
        raise AssemblyError("B/C metric prefix RGB/order differs from device original")

    sim3 = umeyama(bc.xyz[:original_points], original.xyz)
    predicted = sim3.apply(bc.xyz[:original_points])
    residual = np.linalg.norm(predicted - original.xyz, axis=1)
    tolerance = max(
        8.0
        * np.finfo(np.float32).eps
        * max(1.0, float(np.max(np.abs(original.xyz)))),
        8e-7,
    )
    residual_max = float(np.max(residual))
    if not math.isfinite(residual_max) or residual_max > tolerance:
        raise AssemblyError(
            f"metric-to-device Sim3 residual {residual_max} exceeds {tolerance}"
        )

    b_raw = Cloud(sim3.apply(bc.xyz[original_points:]), bc.rgb[original_points:])
    total = len(original.xyz) + len(b_raw.xyz) + len(d.xyz)
    if total != int(contract["total_points"]):
        raise AssemblyError(f"reconstructed total changed: {total}")

    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"comment PocketWorld recovered initial full-room candidate {args.capture}\n"
        "comment order device_original_exact_then_first_BC_raw_then_first_D_raw\n"
        "comment no_filter no_dedup no_recolour no_1cm_dense_publication\n"
        f"comment original_sha256 {contract['original_sha256']}\n"
        f"comment bc_metric_sha256 {contract['bc_sha256']}\n"
        f"comment d_raw_sha256 {contract['d_sha256']}\n"
        f"element vertex {total}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    output_bytes = (
        header + canonical_payload(original) + canonical_payload(b_raw) + canonical_payload(d)
    )
    output_sha256 = hashlib.sha256(output_bytes).hexdigest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_bytes)
    manifest = {
        "schema": "pocketworld_recovered_initial_fullroom_candidate_v1",
        "decision": "PASS_EXACT_FROZEN_LAYER_RECONSTRUCTION",
        "capture": args.capture,
        "counts": {
            "original": original_points,
            "b_c_births": len(b_raw.xyz),
            "d_births": len(d.xyz),
            "total": total,
        },
        "proof": {
            "original_sparse_prefix_preserved": True,
            "points_filtered": 0,
            "points_deduplicated": 0,
            "points_recoloured": 0,
            "later_1cm_publication_used": False,
            "sim3_residual_max": residual_max,
            "sim3_tolerance": float(tolerance),
            "output_sha256": output_sha256,
        },
        "inputs": {
            "original": {
                "path": str(contract["original"]),
                "sha256": contract["original_sha256"],
            },
            "b_c_metric": {
                "path": str(contract["bc"]),
                "sha256": contract["bc_sha256"],
            },
            "d_raw": {
                "path": str(contract["d"]),
                "sha256": contract["d_sha256"],
                "known_asset_limitation": "24 historical JPEG/sidecar pairs unavailable",
            },
        },
        "output": str(args.output),
    }
    manifest_path = args.output.with_suffix(args.output.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
