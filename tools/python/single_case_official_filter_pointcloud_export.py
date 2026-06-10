#!/usr/bin/env python3
"""Export one PyTorch k-sweep case as an official-GLB-style RGB point cloud.

Reuse-only driver: loading, filtering, unprojection, alignment, downsampling,
PLY/PNG writing are all imported unchanged from
``coreml_pytorch_official_filter_pointcloud_compare`` (which itself imports the
official-filter functions from ``strict_k35_window_official_filter_micro_audit``).
This mirrors the exact PyTorch-branch behaviour of the compare script (including
its ``seed + 1`` convention) for cases where no CoreML counterpart exists.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from coreml_pytorch_official_filter_pointcloud_compare import (
    export_group,
    load_pytorch_case,
    write_json,
)
from strict_k35_window_official_filter_micro_audit import camera_center_from_w2c


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--stem", required=True)
    parser.add_argument("--glb-conf-thresh", type=float, default=1.05)
    parser.add_argument("--glb-conf-percentile", type=float, default=40.0)
    parser.add_argument("--glb-ensure-percentile", type=float, default=90.0)
    parser.add_argument("--glb-num-max-points", type=int, default=1_000_000)
    parser.add_argument("--seed", type=int, default=8121)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pytorch = load_pytorch_case(args.case_dir)
    k = int(pytorch["depth"].shape[0])
    group = {
        "slots": list(range(k)),
        "frame_ids": [str(i) for i in range(k)],
        "depth": pytorch["depth"],
        "conf": pytorch["conf"],
        "intrinsics": pytorch["intrinsics"],
        "extrinsics": pytorch["extrinsics"],
        "images": pytorch["processed_images"],
        "camera_centers": np.stack(
            [camera_center_from_w2c(ext) for ext in pytorch["extrinsics"]], axis=0
        ),
    }
    export = export_group(
        group,
        out_dir=args.out_dir,
        stem=args.stem,
        conf_thresh=args.glb_conf_thresh,
        conf_percentile=args.glb_conf_percentile,
        ensure_percentile=args.glb_ensure_percentile,
        num_max_points=args.glb_num_max_points,
        seed=args.seed,
    )
    report = {
        "schema_version": "pocketworld_single_case_official_filter_pointcloud_export_v1",
        "case_dir": str(args.case_dir),
        "parameters": {
            "glb_conf_thresh": args.glb_conf_thresh,
            "glb_conf_percentile": args.glb_conf_percentile,
            "glb_ensure_percentile": args.glb_ensure_percentile,
            "glb_num_max_points": args.glb_num_max_points,
            "seed": args.seed,
        },
        "export": export,
    }
    write_json(args.out_dir / f"{args.stem}_export_report.json", report)
    print(json.dumps(export["filter"], indent=2))
    print("ply:", export["outputs"]["ply"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
