#!/usr/bin/env python3
"""Photometrically certify that each structural plane has one unique depth mode."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from fr_planesweep_wall_ceiling import SweepConfig, load_frames, sweep_surface


OFFSETS_M = (-0.10, -0.05, 0.0, 0.05, 0.10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame-meta", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--planes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--surface-id", action="append")
    parser.add_argument("--max-graze-deg", type=float, default=72.0)
    parser.add_argument("--min-views", type=int, default=4)
    parser.add_argument("--ncc-min", type=float, default=0.80)
    parser.add_argument("--min-parallax-deg", type=float, default=10.0)
    args = parser.parse_args()

    document = json.loads(args.planes.read_text())
    frames = load_frames(args.frame_meta, args.ledger, args.photos)
    config = SweepConfig(
        grid_m=0.20,
        patch_n=9,
        patch_radius_m=0.03,
        min_std=6.0,
        ncc_min=args.ncc_min,
        min_views=args.min_views,
        min_parallax_deg=args.min_parallax_deg,
        max_views=10,
        tile_points=64,
        max_graze_deg=args.max_graze_deg,
    )
    calibrated_surfaces = []
    evidence = []
    for original in document["surfaces"]:
        if args.surface_id and original["surface_id"] not in set(args.surface_id):
            continue
        if not original.get("certified_for_generation", False):
            evidence.append(
                {
                    "surface_id": original["surface_id"],
                    "photometric_certified": False,
                    "reason": "sparse_plane_not_certified",
                    "offsets": [],
                }
            )
            continue
        rows = []
        for offset in OFFSETS_M:
            _, _, _, metrics = sweep_surface(
                original,
                document["floor"],
                frames,
                config,
                offset,
            )
            rows.append(metrics)
            print(json.dumps(metrics, sort_keys=True), flush=True)
        ranked = sorted(
            rows,
            key=lambda row: (
                row["accepted"],
                row["zncc_median"] if row["zncc_median"] is not None else -1.0,
                row["coverage_cells_5cm"],
            ),
            reverse=True,
        )
        best, second = ranked[:2]
        minimum_points = 3 if original["kind"] == "ceiling" else 5
        unique_count_peak = (
            best["accepted"] >= minimum_points
            and best["accepted"] >= second["accepted"] + 3
            and best["accepted"] >= second["accepted"] * 1.20
        )
        sparse_support = original["plane_certification"]["offset_support"]
        sparse_key = f"{best['plane_offset_m']:+.2f}"
        selected_sparse_points = sparse_support[sparse_key]["points_20mm"]
        center_sparse_points = sparse_support["+0.00"]["points_20mm"]
        sparse_agrees = selected_sparse_points >= center_sparse_points * 0.50
        certified = unique_count_peak and sparse_agrees and abs(best["plane_offset_m"]) <= 0.05
        reason = "unique_sparse_supported_depth_peak" if certified else "ambiguous_or_unsupported_depth_peak"
        row = {
            "surface_id": original["surface_id"],
            "kind": original["kind"],
            "photometric_certified": certified,
            "reason": reason,
            "best_offset_m": best["plane_offset_m"],
            "best_accepted": best["accepted"],
            "second_accepted": second["accepted"],
            "unique_count_peak": unique_count_peak,
            "sparse_agrees": sparse_agrees,
            "offsets": rows,
        }
        evidence.append(row)
        if certified:
            surface = deepcopy(original)
            surface["plane_value_n_dot_x"] += best["plane_offset_m"]
            surface["photometric_plane_certification"] = row
            surface["certified_for_generation"] = True
            calibrated_surfaces.append(surface)

    output = deepcopy(document)
    output["schema"] = "aether_known_structural_planes_zncc_certified_v1"
    output["surfaces"] = calibrated_surfaces
    output["photometric_calibration"] = {
        "offsets_m": list(OFFSETS_M),
        "config": config.__dict__,
        "evidence": evidence,
        "accepted_surface_ids": [surface["surface_id"] for surface in calibrated_surfaces],
        "rejected_surface_ids": [
            row["surface_id"] for row in evidence if not row["photometric_certified"]
        ],
    }
    output["counts"]["photometric_certified"] = len(calibrated_surfaces)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "accepted": output["photometric_calibration"]["accepted_surface_ids"],
                "rejected": output["photometric_calibration"]["rejected_surface_ids"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
