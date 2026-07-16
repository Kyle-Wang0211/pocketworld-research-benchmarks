#!/usr/bin/env python3
"""Evaluate reliable-frame graph coverage across compatible DKM runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frame-count", type=int, required=True)
    parser.add_argument("--min-inliers", type=int, default=50)
    parser.add_argument("--min-inlier-ratio", type=float, default=0.8)
    args = parser.parse_args()

    documents = [json.loads(path.read_text()) for path in args.metrics]
    identity_fields = (
        "route",
        "dkm_revision",
        "dkm_license_sha256",
        "weights_sha256",
        "weights_bytes",
        "capture_metadata_sha256",
        "forbidden_noncommercial_matcher_outputs_consumed",
        "device",
        "model_resolution",
        "confidence_threshold",
        "grid_px",
        "sampson_threshold_px",
    )
    baseline = documents[0]
    for document in documents[1:]:
        for field in identity_fields:
            if document[field] != baseline[field]:
                raise RuntimeError(f"incompatible metrics field: {field}")

    # For a repeated pair, retain the observation with the most independently
    # verified MAGSAC inliers.  Failed/empty edges remain in the audit counts.
    pair_map: dict[tuple[int, int], dict] = {}
    observation_count = 0
    for document in documents:
        for row in document["pairs"]:
            observation_count += 1
            key = (int(row["i"]), int(row["j"]))
            prior = pair_map.get(key)
            if prior is None or row["magsac_inliers"] > prior["magsac_inliers"]:
                pair_map[key] = row
    pairs = list(pair_map.values())
    reliable = [
        row
        for row in pairs
        if row["magsac_inliers"] >= args.min_inliers
        and row["magsac_inlier_ratio"] >= args.min_inlier_ratio
    ]

    adjacency = [set() for _ in range(args.frame_count)]
    degree = Counter()
    inlier_support = Counter()
    for row in reliable:
        left, right = int(row["i"]), int(row["j"])
        adjacency[left].add(right)
        adjacency[right].add(left)
        degree[left] += 1
        degree[right] += 1
        inlier_support[left] += int(row["magsac_inliers"])
        inlier_support[right] += int(row["magsac_inliers"])

    seen: set[int] = set()
    components: list[list[int]] = []
    for start in range(args.frame_count):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component: list[int] = []
        while stack:
            frame = stack.pop()
            component.append(frame)
            for neighbor in adjacency[frame]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    components.sort(key=len, reverse=True)
    isolated = [frame for frame in range(args.frame_count) if not adjacency[frame]]
    degrees = [degree[frame] for frame in range(args.frame_count)]

    output = {
        "decision": (
            "PASS_RELIABLE_GRAPH_ALL_FRAMES_CONNECTED"
            if len(components) == 1 and not isolated
            else "FAIL_RELIABLE_GRAPH_COVERAGE"
        ),
        "production_readiness": False,
        "production_blockers_remaining": [
            "CoreML conversion and on-device A16 validation are not complete",
            "matches are not yet integrated into the production SfM/BA graph",
            "training-image provenance remains separate from the explicit MIT model grant",
        ],
        "frame_count": args.frame_count,
        "observation_count": observation_count,
        "unique_pair_count": len(pairs),
        "zero_match_pair_count": sum(row["grid_unique_matches"] == 0 for row in pairs),
        "reliable_edge_gate": {
            "min_magsac_inliers": args.min_inliers,
            "min_magsac_inlier_ratio": args.min_inlier_ratio,
        },
        "reliable_edge_count": len(reliable),
        "covered_frame_count": args.frame_count - len(isolated),
        "isolated_frames": isolated,
        "component_sizes": [len(component) for component in components],
        "degree_min": int(min(degrees)),
        "degree_median": float(np.median(degrees)),
        "degree_max": int(max(degrees)),
        "low_degree_frames": [
            {
                "frame": frame,
                "degree": degree[frame],
                "magsac_inlier_support": inlier_support[frame],
            }
            for frame in range(args.frame_count)
            if degree[frame] < 2
        ],
        "identity": {field: baseline[field] for field in identity_fields},
        "source_metrics": [
            {"path": str(path), "sha256": sha256(path)} for path in args.metrics
        ],
        "forbidden_noncommercial_matcher_outputs_consumed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))
    print(f"OUTPUT_SHA256={sha256(args.output)}")
    return 0 if output["decision"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
