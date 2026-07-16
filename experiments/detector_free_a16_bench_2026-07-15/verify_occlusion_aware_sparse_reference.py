#!/usr/bin/env python3
"""Re-score detector-free births against locally supported sparse surfaces.

The original exact-pixel z-buffer metric can compare a visible foreground
candidate with a single, farther sparse projection at an occlusion boundary.
This diagnostic keeps the reference independent of the candidate: an exact
pixel sparse depth is comparable only when at least ``minimum_support`` sparse
samples in its local window agree with that exact depth.  Unsupported samples
are reported as non-comparable; no candidate-dependent nearest surface is
selected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def depth_from_npz(data: np.lib.npyio.NpzFile, depth_count: int) -> np.ndarray:
    if "product_depth_m" in data.files:
        return np.asarray(data["product_depth_m"], dtype=np.float64)
    if "depth_m" in data.files:
        return np.asarray(data["depth_m"], dtype=np.float64)
    inverse_depths = np.linspace(
        1.0 / 4.3, 1.0 / 0.8, depth_count, dtype=np.float32
    )
    index = np.asarray(data["best_index"], dtype=np.int64)
    if np.any(index < 0) or np.any(index >= depth_count):
        raise ValueError(
            f"best_index outside frozen {depth_count}-layer inverse-depth grid"
        )
    return 1.0 / inverse_depths[index].astype(np.float64)


def locally_supported_sparse_depth(
    sparse_depth: np.ndarray,
    *,
    radius: int,
    minimum_support: int,
    absolute_tolerance_m: float,
    relative_tolerance: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return candidate-independent local cluster median and support count.

    Every cluster is anchored to the exact-pixel sparse z-buffer sample.  A
    neighboring depth joins only when it agrees with that anchor, so a tested
    candidate can neither choose nor move its reference surface.
    """

    height, width = sparse_depth.shape
    supported = np.full((height, width), np.inf, dtype=np.float64)
    support_count = np.zeros((height, width), dtype=np.uint16)
    for y in range(height):
        y0 = max(0, y - radius)
        y1 = min(height, y + radius + 1)
        for x in range(width):
            anchor = float(sparse_depth[y, x])
            if not np.isfinite(anchor):
                continue
            x0 = max(0, x - radius)
            x1 = min(width, x + radius + 1)
            local = sparse_depth[y0:y1, x0:x1]
            finite = local[np.isfinite(local)].astype(np.float64, copy=False)
            tolerance = max(absolute_tolerance_m, relative_tolerance * anchor)
            cluster = finite[np.abs(finite - anchor) <= tolerance]
            support_count[y, x] = len(cluster)
            if len(cluster) >= minimum_support:
                supported[y, x] = float(np.median(cluster))
    return supported, support_count


def error_summary(
    mask: np.ndarray, depth_map: np.ndarray, reference_depth: np.ndarray
) -> dict[str, float | int]:
    comparable = np.asarray(mask, dtype=bool) & np.isfinite(reference_depth)
    values = np.abs(depth_map[comparable] - reference_depth[comparable])
    if values.size == 0:
        return {"count": 0}
    return {
        "count": int(values.size),
        "median_m": float(np.median(values)),
        "p90_m": float(np.percentile(values, 90)),
        "p95_m": float(np.percentile(values, 95)),
        "max_m": float(np.max(values)),
        "within_0_05_m": float(np.mean(values <= 0.05)),
        "within_0_10_m": float(np.mean(values <= 0.10)),
        "within_0_20_m": float(np.mean(values <= 0.20)),
    }


def parse_run_root(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected LABEL=PATH")
    label, raw_path = value.split("=", 1)
    path = Path(raw_path)
    if not label or not path.is_dir():
        raise argparse.ArgumentTypeError(f"invalid run root: {value}")
    return label, path


def score_npz(path: Path, args: argparse.Namespace) -> dict:
    with np.load(path) as data:
        sparse = np.asarray(data["sparse_depth_m"], dtype=np.float64)
        depth_map = depth_from_npz(data, args.depth_count)
        baseline_mask = np.asarray(data["accepted"], dtype=bool)
        final_mask = np.asarray(data["final_birth"], dtype=bool)
    supported, support_count = locally_supported_sparse_depth(
        sparse,
        radius=args.radius,
        minimum_support=args.minimum_support,
        absolute_tolerance_m=args.absolute_tolerance_m,
        relative_tolerance=args.relative_tolerance,
    )
    return {
        "artifact": str(path),
        "artifact_sha256": sha256(path),
        "baseline_births": int(np.count_nonzero(baseline_mask)),
        "final_births": int(np.count_nonzero(final_mask)),
        "exact_pixel_baseline_error": error_summary(
            baseline_mask, depth_map, sparse
        ),
        "exact_pixel_final_error": error_summary(final_mask, depth_map, sparse),
        "supported_surface_baseline_error": error_summary(
            baseline_mask, depth_map, supported
        ),
        "supported_surface_final_error": error_summary(
            final_mask, depth_map, supported
        ),
        "supported_sparse_pixels": int(np.count_nonzero(np.isfinite(supported))),
        "maximum_local_support": int(np.max(support_count)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", action="append", type=parse_run_root, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--minimum-support", type=int, default=3)
    parser.add_argument("--absolute-tolerance-m", type=float, default=0.08)
    parser.add_argument("--relative-tolerance", type=float, default=0.05)
    parser.add_argument("--depth-count", type=int, default=48)
    args = parser.parse_args()

    runs = []
    for label, root in args.run_root:
        references = [score_npz(path, args) for path in sorted(root.glob("*.npz"))]
        if not references:
            references = [
                score_npz(path, args)
                for path in sorted((root / "artifacts").glob("*.npz"))
            ]
        if not references:
            raise FileNotFoundError(f"no NPZ artifacts under {root}")
        runs.append(
            {
                "label": label,
                "root": str(root),
                "references": references,
                "totals": {
                    "baseline_births": sum(r["baseline_births"] for r in references),
                    "final_births": sum(r["final_births"] for r in references),
                    "supported_comparable_final": sum(
                        r["supported_surface_final_error"]["count"]
                        for r in references
                    ),
                },
            }
        )

    result = {
        "schema": "pocketworld_occlusion_aware_sparse_reference_v1",
        "contract": {
            "candidate_independent": True,
            "exact_pixel_sparse_anchor_required": True,
            "radius_pixels": args.radius,
            "window": 2 * args.radius + 1,
            "minimum_cluster_support": args.minimum_support,
            "absolute_cluster_tolerance_m": args.absolute_tolerance_m,
            "relative_cluster_tolerance": args.relative_tolerance,
            "unsupported_exact_pixel_samples": "non_comparable",
            "birth_count_remains_separate_coverage_metric": True,
        },
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
