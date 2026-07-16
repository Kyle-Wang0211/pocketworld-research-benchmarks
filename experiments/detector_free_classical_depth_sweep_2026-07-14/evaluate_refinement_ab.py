#!/usr/bin/env python3
"""Judge a depth-refinement A/B under PocketWorld's zero-regression rule.

The candidate is allowed to move already-born points only.  It passes only if
point-birth state is bit-identical, every comparable sparse-reference error is
non-increasing, and at least one comparable pixel improves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


ERROR_EPSILON_M = 1e-9
BIRTH_ARRAY_KEYS = (
    "accepted",
    "discrete_depth_m",
    "best_ncc",
    "second_ncc",
    "views",
    "consistency_views",
)
THRESHOLDS_M = (0.05, 0.10, 0.20, 0.50)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_sort_key(path: Path) -> tuple[int, str]:
    suffix = path.name.removeprefix("ref")
    return (int(suffix), path.name) if suffix.isdigit() else (2**31 - 1, path.name)


def _error_summary(errors: np.ndarray) -> dict[str, object]:
    if errors.size == 0:
        return {"count": 0}
    result: dict[str, object] = {
        "count": int(errors.size),
        "mean_m": float(np.mean(errors)),
        "median_m": float(np.median(errors)),
        "p90_m": float(np.percentile(errors, 90)),
        "p95_m": float(np.percentile(errors, 95)),
        "p99_m": float(np.percentile(errors, 99)),
        "max_m": float(np.max(errors)),
    }
    for threshold in THRESHOLDS_M:
        result[f"within_{threshold:.2f}_m"] = float(np.mean(errors <= threshold))
    return result


def _load_run(path: Path) -> tuple[dict[str, object], dict[str, np.ndarray]]:
    metrics_path = path / "metrics.json"
    arrays_path = path / "depth_sweep.npz"
    if not metrics_path.is_file() or not arrays_path.is_file():
        raise FileNotFoundError(f"incomplete run: {path}")
    metrics = json.loads(metrics_path.read_text())
    with np.load(arrays_path) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    return metrics, arrays


def evaluate_runs(
    runs_root: Path,
    baseline_name: str,
    candidate_name: str,
    error_epsilon_m: float = ERROR_EPSILON_M,
) -> dict[str, object]:
    reference_dirs = sorted(
        (path for path in runs_root.iterdir() if path.is_dir() and path.name.startswith("ref")),
        key=_reference_sort_key,
    )
    if not reference_dirs:
        raise ValueError(f"no ref* directories under {runs_root}")

    references: list[dict[str, object]] = []
    total_improved = 0
    total_regressed = 0
    total_unchanged = 0
    all_birth_identical = True
    all_sparse_truth_identical = True

    for reference_dir in reference_dirs:
        baseline_metrics, baseline = _load_run(reference_dir / baseline_name)
        candidate_metrics, candidate = _load_run(reference_dir / candidate_name)

        missing = [
            key
            for key in (*BIRTH_ARRAY_KEYS, "depth_m", "sparse_depth_eval_m")
            if key not in baseline or key not in candidate
        ]
        if missing:
            raise KeyError(f"{reference_dir.name}: missing arrays {missing}")

        birth_identity = {
            key: bool(np.array_equal(baseline[key], candidate[key]))
            for key in BIRTH_ARRAY_KEYS
        }
        sparse_truth_identical = bool(
            np.array_equal(
                baseline["sparse_depth_eval_m"],
                candidate["sparse_depth_eval_m"],
                equal_nan=True,
            )
        )
        all_birth_identical &= all(birth_identity.values())
        all_sparse_truth_identical &= sparse_truth_identical

        baseline_comparable = baseline["accepted"] & np.isfinite(
            baseline["sparse_depth_eval_m"]
        )
        candidate_comparable = candidate["accepted"] & np.isfinite(
            candidate["sparse_depth_eval_m"]
        )
        comparable_identity = bool(np.array_equal(baseline_comparable, candidate_comparable))
        common = baseline_comparable & candidate_comparable

        baseline_errors = np.abs(
            baseline["depth_m"][common] - baseline["sparse_depth_eval_m"][common]
        ).astype(np.float64)
        candidate_errors = np.abs(
            candidate["depth_m"][common] - candidate["sparse_depth_eval_m"][common]
        ).astype(np.float64)
        error_delta = candidate_errors - baseline_errors
        improved = int(np.count_nonzero(error_delta < -error_epsilon_m))
        regressed = int(np.count_nonzero(error_delta > error_epsilon_m))
        unchanged = int(error_delta.size - improved - regressed)
        total_improved += improved
        total_regressed += regressed
        total_unchanged += unchanged

        references.append(
            {
                "reference": reference_dir.name,
                "baseline": {
                    "metrics_sha256": sha256(reference_dir / baseline_name / "metrics.json"),
                    "npz_sha256": sha256(reference_dir / baseline_name / "depth_sweep.npz"),
                    "error": _error_summary(baseline_errors),
                },
                "candidate": {
                    "metrics_sha256": sha256(reference_dir / candidate_name / "metrics.json"),
                    "npz_sha256": sha256(reference_dir / candidate_name / "depth_sweep.npz"),
                    "error": _error_summary(candidate_errors),
                },
                "birth_identity": birth_identity,
                "sparse_truth_identical": sparse_truth_identical,
                "comparable_mask_identical": comparable_identity,
                "improved_pixels": improved,
                "regressed_pixels": regressed,
                "unchanged_pixels": unchanged,
                "worst_error_increase_m": (
                    float(np.max(error_delta)) if error_delta.size else None
                ),
                "best_error_reduction_m": (
                    float(-np.min(error_delta)) if error_delta.size else None
                ),
                "run_config": {
                    "baseline": baseline_metrics.get("config"),
                    "candidate": candidate_metrics.get("config"),
                },
            }
        )

    if not all_birth_identical or not all_sparse_truth_identical:
        verdict = "FAIL_BIRTH_OR_INPUT_IDENTITY"
    elif total_regressed:
        verdict = "FAIL_REGRESSION"
    elif not total_improved:
        verdict = "FAIL_NO_MEASURED_BENEFIT"
    else:
        verdict = "PASS_ZERO_REGRESSION"

    return {
        "schema": "pocketworld_depth_refinement_zero_regression_ab_v1",
        "rule": {
            "birth_arrays_bit_identical": list(BIRTH_ARRAY_KEYS),
            "sparse_truth_bit_identical": True,
            "per_comparable_pixel_error_must_not_increase": True,
            "minimum_improved_pixels": 1,
            "error_epsilon_m": error_epsilon_m,
        },
        "runs_root": str(runs_root),
        "baseline_name": baseline_name,
        "candidate_name": candidate_name,
        "reference_count": len(references),
        "totals": {
            "improved_pixels": total_improved,
            "regressed_pixels": total_regressed,
            "unchanged_pixels": total_unchanged,
        },
        "verdict": verdict,
        "references": references,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--baseline-name", default="off")
    parser.add_argument("--candidate-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--error-epsilon-m", type=float, default=ERROR_EPSILON_M)
    args = parser.parse_args()

    result = evaluate_runs(
        args.runs_root,
        args.baseline_name,
        args.candidate_name,
        args.error_epsilon_m,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["totals"], sort_keys=True))
    print(result["verdict"])


if __name__ == "__main__":
    main()
