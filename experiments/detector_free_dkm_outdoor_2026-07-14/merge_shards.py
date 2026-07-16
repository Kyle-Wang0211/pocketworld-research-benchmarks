#!/usr/bin/env python3
"""Merge independently executed DKM matcher shards with strict identity checks."""

from __future__ import annotations

import argparse
import hashlib
import json
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
    parser.add_argument("--shards-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-pairs", type=int, required=True)
    args = parser.parse_args()

    metric_paths = list(args.shards_dir.glob("shard_*/metrics.json"))
    if not metric_paths:
        raise RuntimeError("no shard metrics found")
    documents = [(path, json.loads(path.read_text())) for path in metric_paths]
    documents.sort(key=lambda row: row[1]["pair_selection"]["pair_start"])

    identity_fields = (
        "route",
        "dkm_revision",
        "dkm_source_sha256",
        "dkm_model_runtime_sha256",
        "dkm_weight_registry_sha256",
        "dkm_outdoor_training_recipe_sha256",
        "clean_inference_wrapper_sha256",
        "gpl_geometry_utils_imported",
        "dkm_license_sha256",
        "weights_sha256",
        "weights_bytes",
        "capture_metadata_sha256",
        "input_image_count",
        "input_classes",
        "forbidden_noncommercial_matcher_outputs_consumed",
        "device",
        "torch_version",
        "model_resolution",
        "confidence_threshold",
        "grid_px",
        "sampson_threshold_px",
    )
    baseline = documents[0][1]
    for path, document in documents[1:]:
        for field in identity_fields:
            if document[field] != baseline[field]:
                raise RuntimeError(f"shard identity mismatch for {field}: {path}")

    arrays: dict[str, np.ndarray] = {}
    pairs: list[dict] = []
    source_shards: list[dict] = []
    expected_start = 0
    for metrics_path, document in documents:
        selection = document["pair_selection"]
        start, stop = selection["pair_start"], selection["pair_stop"]
        if start != expected_start or stop <= start:
            raise RuntimeError(
                f"non-contiguous shard range {start}:{stop}, expected start {expected_start}"
            )
        if len(document["pairs"]) != stop - start:
            raise RuntimeError(f"pair count mismatch: {metrics_path}")
        matches_path = metrics_path.with_name("matches.npz")
        with np.load(matches_path) as archive:
            for key in archive.files:
                if key in arrays:
                    raise RuntimeError(f"duplicate match array: {key}")
                arrays[key] = archive[key]
        pairs.extend(document["pairs"])
        source_shards.append(
            {
                "range": [start, stop],
                "metrics_sha256": sha256(metrics_path),
                "matches_sha256": sha256(matches_path),
            }
        )
        expected_start = stop

    if expected_start != args.expected_pairs or len(pairs) != args.expected_pairs:
        raise RuntimeError(
            f"incomplete merge: stop={expected_start}, pairs={len(pairs)}, "
            f"expected={args.expected_pairs}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    matches_output = args.output_dir / "matches.npz"
    np.savez_compressed(matches_output, **arrays)
    counts = [row["grid_unique_matches"] for row in pairs]
    arkit_ratios = [row["sampson_inlier_ratio"] for row in pairs]
    robust_ratios = [row["magsac_inlier_ratio"] for row in pairs]
    merged = {field: baseline[field] for field in identity_fields}
    merged.update(
        {
            "merge_mode": "process_isolated_mps_shards",
            "source_shards": source_shards,
            "pair_selection": {
                **baseline["pair_selection"],
                "selected_count": len(pairs),
                "pre_slice_selected_count": len(pairs),
                "pair_start": 0,
                "pair_stop": len(pairs),
            },
            "model_load_seconds_sum": float(
                sum(document["model_load_seconds"] for _, document in documents)
            ),
            "match_wall_seconds_sum": float(
                sum(document["match_wall_seconds"] for _, document in documents)
            ),
            "peak_mps_bytes_max": int(
                max(document["peak_mps_bytes"] for _, document in documents)
            ),
            "available_gb_initial_min": float(
                min(document["available_gb_initial"] for _, document in documents)
            ),
            "grid_matches_total": int(sum(counts)),
            "grid_matches_median": float(np.median(counts)),
            "arkit_sampson_inlier_ratio_median": float(np.median(arkit_ratios)),
            "magsac_inlier_ratio_median": float(np.median(robust_ratios)),
            "pairs": pairs,
        }
    )
    metrics_output = args.output_dir / "metrics.json"
    metrics_output.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    print(f"MERGED_PAIRS={len(pairs)}")
    print(f"MATCHES_SHA256={sha256(matches_output)}")
    print(f"METRICS_SHA256={sha256(metrics_output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
