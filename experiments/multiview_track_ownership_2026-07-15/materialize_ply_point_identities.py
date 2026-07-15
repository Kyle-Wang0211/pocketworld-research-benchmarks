#!/usr/bin/env python3
"""Materialize the same published point identities from a candidate model.

The control PLY defines membership, order, and color. Point IDs are recovered
against the control COLMAP model once, then their coordinates are read from a
candidate model that must contain every same ID. No point is selected, rejected,
or substituted based on the candidate geometry.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pycolmap

from constrained_surface_refine import (
    published_point_order,
    read_ply,
    sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("control_model", type=Path)
    parser.add_argument("control_ply", type=Path)
    parser.add_argument("candidate_model", type=Path)
    parser.add_argument("output_ply", type=Path)
    args = parser.parse_args()

    if args.output_ply.exists():
        raise FileExistsError(f"refusing to overwrite {args.output_ply}")

    control = pycolmap.Reconstruction(args.control_model)
    candidate = pycolmap.Reconstruction(args.candidate_model)
    header, rows, control_xyz = read_ply(args.control_ply)
    point_ids, mapping = published_point_order(control, control_xyz)
    missing = [
        int(point_id)
        for point_id in point_ids
        if int(point_id) not in candidate.points3D
    ]
    if missing:
        raise RuntimeError(
            f"candidate model is missing {len(missing)} published point IDs"
        )

    candidate_xyz = np.asarray(
        [candidate.points3D[int(point_id)].xyz for point_id in point_ids],
        dtype=np.float64,
    )
    rows["x"] = candidate_xyz[:, 0].astype(np.float32)
    rows["y"] = candidate_xyz[:, 1].astype(np.float32)
    rows["z"] = candidate_xyz[:, 2].astype(np.float32)
    args.output_ply.write_bytes(header + rows.tobytes())

    print(
        json.dumps(
            {
                "schema": "pocketworld_fixed_published_identity_ply_v1",
                "identity_policy": "control PLY membership/order/color only",
                "published_points": int(len(point_ids)),
                "candidate_internal_points": int(len(candidate.points3D)),
                "mapping": mapping,
                "control_ply_sha256": sha256(args.control_ply),
                "candidate_points3D_sha256": sha256(
                    args.candidate_model / "points3D.bin"
                ),
                "output_ply_sha256": sha256(args.output_ply),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
