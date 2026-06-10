#!/usr/bin/env python3
"""Experiment B: per-frame multiplicative depth-scale correction (standard primitive).

Standard depth-alignment primitive (median scaling / DN-Splatter-style per-image
scale, here against window consensus instead of external sparse depth):

1. For frame pairs (i, j) within an adjacency band, project frame i's
   high-conf sampled depths into frame j (geometry imported verbatim from
   official_pytorch_image_only_geometry_consistency_audit) and take
   m_ij = median(D_j_sampled / z_projected) ~= a_i / a_j.
2. Solve weighted least squares in log space for per-frame log-scales x_i
   (gauge: mean(x) = 0, preserving the window's umeyama metric scale).
3. Corrected depth: D_i' = exp(x_i) * D_i. Optionally iterate.

Only pytorch_depth.npy changes; conf/intrinsics/extrinsics/images are copied
through untouched so the standard audit/export tools run on the output dir.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from official_pytorch_image_only_geometry_consistency_audit import (  # noqa: E402
    project_source_samples,
    source_grid_samples,
)


def measure_pair_log_ratio(
    source_idx: int,
    target_idx: int,
    depth: np.ndarray,
    conf_streaming: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    threshold: float,
    stride: int,
) -> tuple[float, int]:
    samples = source_grid_samples(
        depth[source_idx], conf_streaming[source_idx], threshold=threshold, stride=stride
    )
    if samples["count"] == 0:
        return 0.0, 0
    target_depth, target_conf, target_z, valid = project_source_samples(
        source_idx=source_idx,
        target_idx=target_idx,
        samples=samples,
        depth=depth,
        conf=conf_streaming,
        intrinsics=intrinsics,
        extrinsics=extrinsics,
    )
    valid &= np.isfinite(target_conf) & (target_conf >= threshold)
    n = int(np.count_nonzero(valid))
    if n < 50:
        return 0.0, 0
    ratio = target_depth[valid] / np.maximum(target_z[valid], 1e-6)
    ratio = ratio[np.isfinite(ratio) & (ratio > 0.5) & (ratio < 2.0)]
    if ratio.size < 50:
        return 0.0, 0
    return float(np.log(np.median(ratio))), int(ratio.size)


def solve_log_scales(n_frames: int, edges: list[tuple[int, int, float, int]]) -> np.ndarray:
    rows, rhs, weights = [], [], []
    for i, j, log_m, count in edges:
        row = np.zeros(n_frames, dtype=np.float64)
        row[i] = 1.0
        row[j] = -1.0
        rows.append(row)
        rhs.append(log_m)
        weights.append(np.sqrt(count))
    a_mat = np.asarray(rows) * np.asarray(weights)[:, None]
    b_vec = np.asarray(rhs) * np.asarray(weights)
    x, *_ = np.linalg.lstsq(a_mat, b_vec, rcond=None)
    return x - float(np.mean(x))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--band", type=int, default=3)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--conf-coef", type=float, default=0.5)
    parser.add_argument("--iters", type=int, default=2)
    args = parser.parse_args()

    depth = np.load(args.case_dir / "pytorch_depth.npy").astype(np.float32)
    conf_raw = np.load(args.case_dir / "pytorch_conf.npy").astype(np.float32)
    intrinsics = np.load(args.case_dir / "pytorch_intrinsics.npy").astype(np.float32)
    extrinsics = np.load(args.case_dir / "pytorch_extrinsics.npy").astype(np.float32)
    n = int(depth.shape[0])

    conf_streaming = np.maximum(conf_raw - 1.0, 0.0)
    threshold = float(np.mean(conf_streaming) * args.conf_coef)

    total_log = np.zeros(n, dtype=np.float64)
    report_iters = []
    for it in range(args.iters):
        edges = []
        for i in range(n):
            for dj in range(1, args.band + 1):
                j = i + dj
                if j >= n:
                    continue
                log_m, cnt = measure_pair_log_ratio(
                    i, j, depth, conf_streaming, intrinsics, extrinsics, threshold, args.stride
                )
                if cnt > 0:
                    edges.append((i, j, log_m, cnt))
        x = solve_log_scales(n, edges)
        depth = (depth * np.exp(x)[:, None, None]).astype(np.float32)
        total_log += x
        report_iters.append(
            {
                "iter": it,
                "edges": len(edges),
                "scale_correction_pct_minmax": [
                    float((np.exp(x).min() - 1) * 100),
                    float((np.exp(x).max() - 1) * 100),
                ],
                "scale_correction_pct_absmean": float(np.mean(np.abs(np.exp(x) - 1)) * 100),
            }
        )
        print(f"iter {it}: edges={len(edges)} 校正幅度 |mean|={report_iters[-1]['scale_correction_pct_absmean']:.2f}% "
              f"range=[{report_iters[-1]['scale_correction_pct_minmax'][0]:+.2f}%, {report_iters[-1]['scale_correction_pct_minmax'][1]:+.2f}%]")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    np.save(args.out_dir / "pytorch_depth.npy", depth)
    for name in ["pytorch_conf.npy", "pytorch_intrinsics.npy", "pytorch_extrinsics.npy", "pytorch_processed_images.npy"]:
        src = args.case_dir / name
        if src.exists():
            shutil.copy2(src, args.out_dir / name)

    scales = np.exp(total_log)
    report = {
        "schema_version": "pocketworld_expB_per_frame_scale_correction_v1",
        "case_dir": str(args.case_dir),
        "parameters": {
            "band": args.band,
            "stride": args.stride,
            "conf_coef": args.conf_coef,
            "iters": args.iters,
            "threshold": threshold,
        },
        "iterations": report_iters,
        "total_scale_per_frame": [float(s) for s in scales],
        "total_scale_pct_absmean": float(np.mean(np.abs(scales - 1)) * 100),
        "total_scale_pct_max": float(np.max(np.abs(scales - 1)) * 100),
    }
    (args.out_dir / "expB_scale_correction_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(f"总校正: |mean| {report['total_scale_pct_absmean']:.2f}%  max {report['total_scale_pct_max']:.2f}%")
    print("per-frame scales:", [round(float(s), 4) for s in scales])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
