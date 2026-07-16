#!/usr/bin/env python3
"""Test whether same-dispatch all-view dissent safely separates bad births."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent


def load_reference_helper():
    path = HERE / "verify_occlusion_aware_sparse_reference.py"
    spec = importlib.util.spec_from_file_location("pw_occlusion_reference", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def distribution(values: np.ndarray) -> dict:
    if values.size == 0:
        return {"count": 0}
    return {
        "count": int(values.size),
        "minimum": float(np.min(values)),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "maximum": float(np.max(values)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reference = load_reference_helper()

    good_parts = []
    bad_parts = []
    references = []
    for root in args.artifact_root:
        for path in sorted(root.glob("*.npz")):
            with np.load(path) as data:
                sparse = np.asarray(data["sparse_depth_m"], dtype=np.float64)
                supported, _ = reference.locally_supported_sparse_depth(
                    sparse,
                    radius=2,
                    minimum_support=3,
                    absolute_tolerance_m=0.08,
                    relative_tolerance=0.05,
                )
                depth = np.asarray(data["product_depth_m"], dtype=np.float64)
                final = np.asarray(data["final_birth"], dtype=bool)
                dissent = np.asarray(data["all_view_dissent"], dtype=np.float64)
            comparable = final & np.isfinite(supported)
            error = np.abs(depth - supported)
            good = dissent[comparable & (error <= 0.10)]
            bad = dissent[comparable & (error > 0.20)]
            good_parts.append(good)
            bad_parts.append(bad)
            references.append(
                {
                    "artifact": str(path),
                    "good_dissent": distribution(good),
                    "bad_dissent": distribution(bad),
                }
            )

    good = np.concatenate(good_parts)
    bad = np.concatenate(bad_parts)
    zero_good_loss_candidates = []
    for threshold in np.unique(np.concatenate([good, bad])):
        rejected_good = int(np.count_nonzero(good > threshold))
        rejected_bad = int(np.count_nonzero(bad > threshold))
        if rejected_good == 0 and rejected_bad > 0:
            zero_good_loss_candidates.append(
                {
                    "threshold_exclusive": float(threshold),
                    "rejected_good": rejected_good,
                    "rejected_bad": rejected_bad,
                }
            )
    result = {
        "schema": "pocketworld_detector_free_view_dissent_v1",
        "contract": {
            "same_dispatch": True,
            "depth_winner_or_birth_changed_by_diagnostic": False,
            "good_error_max_m": 0.10,
            "bad_error_exclusive_min_m": 0.20,
            "occlusion_reference": {
                "window": 5,
                "minimum_support": 3,
                "absolute_tolerance_m": 0.08,
                "relative_tolerance": 0.05,
                "candidate_independent": True,
            },
        },
        "good_dissent": distribution(good),
        "bad_dissent": distribution(bad),
        "zero_good_loss_thresholds": zero_good_loss_candidates,
        "decision": (
            "PASS_SELECTIVE_DISSENT_TAIL"
            if zero_good_loss_candidates
            else "FAIL_NO_ZERO_GOOD_LOSS_DISSENT_THRESHOLD"
        ),
        "references": references,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in (
        "decision", "good_dissent", "bad_dissent", "zero_good_loss_thresholds"
    )}, indent=2, sort_keys=True))
    return 0 if zero_good_loss_candidates else 1


if __name__ == "__main__":
    raise SystemExit(main())
