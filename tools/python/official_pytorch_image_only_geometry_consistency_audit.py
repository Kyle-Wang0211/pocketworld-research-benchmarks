#!/usr/bin/env python3
"""Projective geometry consistency audit for official PyTorch image-only DA3.

This script is read-only with respect to model outputs. It loads one official
PyTorch image-only window export and checks whether depth/pose predictions are
geometrically self-consistent inside the same K-window:

1. Backproject sampled high-confidence pixels from a source frame to world.
2. Project those world points into previous/prefix target frames.
3. Compare projected target-camera z against the target frame's predicted depth.

The metric is upstream of PLY/export policy. It asks whether the model's own
depth, intrinsics, and cam_dec poses put overlapping observations on the same
surface before downstream point-cloud merging gets involved.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytorch-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_016")
    parser.add_argument("--pose-depth-audit", type=Path)
    parser.add_argument("--stride", type=int, default=6)
    parser.add_argument("--conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--max-prefix-refs", type=int, default=12)
    parser.add_argument("--relative-risk-threshold", type=float, default=0.10)
    args = parser.parse_args()

    manifest = read_json(args.manifest)
    export_report = read_optional_json(args.pytorch_dir / "official_pytorch_window_000_export_report.json")
    pose_depth_audit = read_optional_json(args.pose_depth_audit) if args.pose_depth_audit else {}

    depth = np.load(args.pytorch_dir / "pytorch_depth.npy").astype(np.float32, copy=False)
    conf_raw = np.load(args.pytorch_dir / "pytorch_conf.npy").astype(np.float32, copy=False)
    intrinsics = np.load(args.pytorch_dir / "pytorch_intrinsics.npy").astype(np.float32, copy=False)
    extrinsics = np.load(args.pytorch_dir / "pytorch_extrinsics.npy").astype(np.float32, copy=False)
    validate_shapes(depth, conf_raw, intrinsics, extrinsics)

    frames = list(manifest.get("frames") or [])
    if len(frames) != int(depth.shape[0]):
        raise ValueError(f"manifest frames={len(frames)} but depth N={depth.shape[0]}")

    conf_streaming = np.maximum(conf_raw - 1.0, 0.0).astype(np.float32, copy=False)
    centers = camera_centers(extrinsics)
    cumulative_rows = cumulative_lookup(pose_depth_audit)

    slot_rows = []
    for source_idx in range(1, int(depth.shape[0])):
        threshold = float(np.mean(conf_streaming[: source_idx + 1]) * args.conf_threshold_coef)
        source_samples = source_grid_samples(
            depth[source_idx],
            conf_streaming[source_idx],
            threshold=threshold,
            stride=args.stride,
        )
        previous_pair = pair_projective_residual(
            source_idx=source_idx,
            target_idx=source_idx - 1,
            samples=source_samples,
            depth=depth,
            conf=conf_streaming,
            intrinsics=intrinsics,
            extrinsics=extrinsics,
            threshold=threshold,
        )
        prefix_refs = choose_prefix_refs(source_idx, centers, max_refs=args.max_prefix_refs)
        prefix_best = prefix_best_residual(
            source_idx=source_idx,
            target_indices=prefix_refs,
            samples=source_samples,
            depth=depth,
            conf=conf_streaming,
            intrinsics=intrinsics,
            extrinsics=extrinsics,
            threshold=threshold,
        )

        frame_gap = frame_index(frames[source_idx], source_idx) - frame_index(
            frames[source_idx - 1], source_idx - 1
        )
        step = float(np.linalg.norm(centers[source_idx] - centers[source_idx - 1]))
        cumulative = cumulative_rows.get(source_idx + 1, {})
        slot_rows.append(
            {
                "slot": source_idx,
                "frame_id": frame_id(frames[source_idx], source_idx),
                "previous_frame_id": frame_id(frames[source_idx - 1], source_idx - 1),
                "frame_index": frame_index(frames[source_idx], source_idx),
                "frame_gap_from_previous": int(frame_gap),
                "camera_step_from_previous": step,
                "cumulative_pose_diag": float(camera_diag(centers[: source_idx + 1])),
                "streaming_conf_threshold": threshold,
                "source_sample_count": int(source_samples["count"]),
                "previous_pair": previous_pair,
                "best_prefix": prefix_best,
                "cumulative_npz": cumulative.get("npz_streaming_style_conf_minus_one", {}),
                "cumulative_glb": cumulative.get("glb_style_raw_conf", {}),
                "risk_flags": risk_flags(
                    previous_pair=previous_pair,
                    prefix_best=prefix_best,
                    threshold=args.relative_risk_threshold,
                    cumulative=cumulative,
                ),
            }
        )

    summary = build_summary(slot_rows, threshold=args.relative_risk_threshold)
    report = {
        "schema_version": "pocketworld_official_pytorch_image_only_geometry_consistency_audit_v1",
        "scope": {
            "window_id": args.window_id,
            "pytorch_dir": str(args.pytorch_dir),
            "manifest": str(args.manifest),
            "pose_depth_audit": str(args.pose_depth_audit) if args.pose_depth_audit else None,
            "frame_count": int(depth.shape[0]),
            "processed_shape_nhw": [int(v) for v in depth.shape],
            "camera_mode": get_path(export_report, "parameters.camera_mode"),
            "ref_view_strategy": get_path(export_report, "parameters.ref_view_strategy"),
            "process_res": get_path(export_report, "parameters.process_res"),
            "process_res_method": get_path(export_report, "parameters.process_res_method"),
            "note": (
                "Official PyTorch image-only cam_dec output. Projective residuals are "
                "computed before point-cloud export, so they are upstream geometry evidence."
            ),
        },
        "parameters": {
            "stride": args.stride,
            "conf_threshold_coef": args.conf_threshold_coef,
            "confidence_convention": "max(raw prediction.conf - 1.0, 0.0), matching DA3-Streaming results_output",
            "max_prefix_refs": args.max_prefix_refs,
            "relative_risk_threshold": args.relative_risk_threshold,
        },
        "summary": summary,
        "slots": slot_rows,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / f"{args.window_id}_official_pytorch_image_only_geometry_consistency_audit.json", report)
    write_markdown(
        args.out_dir / f"{args.window_id}_official_pytorch_image_only_geometry_consistency_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def validate_shapes(
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
) -> None:
    if depth.ndim != 3:
        raise ValueError(f"Expected depth NHW, got {depth.shape}")
    if conf.shape != depth.shape:
        raise ValueError(f"Conf shape {conf.shape} does not match depth {depth.shape}")
    if intrinsics.shape != (depth.shape[0], 3, 3):
        raise ValueError(f"Expected intrinsics (N,3,3), got {intrinsics.shape}")
    if extrinsics.shape not in {(depth.shape[0], 3, 4), (depth.shape[0], 4, 4)}:
        raise ValueError(f"Expected extrinsics (N,3,4) or (N,4,4), got {extrinsics.shape}")


def source_grid_samples(
    depth: np.ndarray,
    conf: np.ndarray,
    *,
    threshold: float,
    stride: int,
) -> dict[str, Any]:
    h, w = depth.shape
    ys = np.arange(stride // 2, h, stride, dtype=np.int32)
    xs = np.arange(stride // 2, w, stride, dtype=np.int32)
    grid_x, grid_y = np.meshgrid(xs, ys)
    u = grid_x.reshape(-1).astype(np.float32)
    v = grid_y.reshape(-1).astype(np.float32)
    z = depth[grid_y.reshape(-1), grid_x.reshape(-1)].astype(np.float32, copy=False)
    c = conf[grid_y.reshape(-1), grid_x.reshape(-1)].astype(np.float32, copy=False)
    mask = np.isfinite(z) & (z > 1e-6) & np.isfinite(c) & (c >= threshold) & (c > 1e-5)
    return {
        "u": u[mask],
        "v": v[mask],
        "z": z[mask],
        "conf": c[mask],
        "count": int(np.count_nonzero(mask)),
        "candidate_count": int(z.size),
    }


def pair_projective_residual(
    *,
    source_idx: int,
    target_idx: int,
    samples: dict[str, Any],
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    if samples["count"] == 0:
        return empty_pair(target_idx)

    target_depth, target_conf, target_z, valid = project_source_samples(
        source_idx=source_idx,
        target_idx=target_idx,
        samples=samples,
        depth=depth,
        conf=conf,
        intrinsics=intrinsics,
        extrinsics=extrinsics,
    )
    valid &= np.isfinite(target_conf) & (target_conf >= threshold) & (target_conf > 1e-5)
    if not np.any(valid):
        return empty_pair(target_idx, source_count=samples["count"])

    signed = target_z[valid] - target_depth[valid]
    abs_z = np.abs(signed)
    rel = abs_z / np.maximum(np.abs(target_depth[valid]), 1e-6)
    return residual_stats(
        target_idx=target_idx,
        source_count=samples["count"],
        compared_count=int(abs_z.size),
        signed=signed,
        abs_z=abs_z,
        rel=rel,
    )


def prefix_best_residual(
    *,
    source_idx: int,
    target_indices: list[int],
    samples: dict[str, Any],
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    if samples["count"] == 0 or not target_indices:
        return {
            "target_indices": target_indices,
            "source_count": int(samples.get("count", 0)),
            "compared_count": 0,
            "any_overlap_fraction": 0.0,
        }

    best_abs = np.full(samples["count"], np.inf, dtype=np.float32)
    best_rel = np.full(samples["count"], np.inf, dtype=np.float32)
    best_signed = np.zeros(samples["count"], dtype=np.float32)
    best_target = np.full(samples["count"], -1, dtype=np.int32)
    pair_summaries = []

    for target_idx in target_indices:
        target_depth, target_conf, target_z, valid = project_source_samples(
            source_idx=source_idx,
            target_idx=target_idx,
            samples=samples,
            depth=depth,
            conf=conf,
            intrinsics=intrinsics,
            extrinsics=extrinsics,
        )
        valid &= np.isfinite(target_conf) & (target_conf >= threshold) & (target_conf > 1e-5)
        if not np.any(valid):
            pair_summaries.append(empty_pair(target_idx, source_count=samples["count"]))
            continue
        signed = target_z[valid] - target_depth[valid]
        abs_z = np.abs(signed)
        rel = abs_z / np.maximum(np.abs(target_depth[valid]), 1e-6)
        pair_summaries.append(
            residual_stats(
                target_idx=target_idx,
                source_count=samples["count"],
                compared_count=int(abs_z.size),
                signed=signed,
                abs_z=abs_z,
                rel=rel,
            )
        )
        valid_indices = np.flatnonzero(valid)
        improve = rel < best_rel[valid_indices]
        chosen = valid_indices[improve]
        best_abs[chosen] = abs_z[improve]
        best_rel[chosen] = rel[improve]
        best_signed[chosen] = signed[improve]
        best_target[chosen] = int(target_idx)

    matched = np.isfinite(best_rel)
    if not np.any(matched):
        return {
            "target_indices": target_indices,
            "source_count": int(samples["count"]),
            "compared_count": 0,
            "any_overlap_fraction": 0.0,
            "pair_summaries": pair_summaries,
        }

    best_counts = {}
    for idx in best_target[matched]:
        best_counts[str(int(idx))] = best_counts.get(str(int(idx)), 0) + 1
    summary = residual_stats(
        target_idx=None,
        source_count=samples["count"],
        compared_count=int(np.count_nonzero(matched)),
        signed=best_signed[matched],
        abs_z=best_abs[matched],
        rel=best_rel[matched],
    )
    summary.update(
        {
            "target_indices": target_indices,
            "any_overlap_fraction": float(np.count_nonzero(matched) / max(samples["count"], 1)),
            "best_target_counts": best_counts,
            "pair_summaries": sorted(
                pair_summaries,
                key=lambda row: none_to_inf(row.get("rel_median")),
            )[:5],
        }
    )
    return summary


def project_source_samples(
    *,
    source_idx: int,
    target_idx: int,
    samples: dict[str, Any],
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    source_k = intrinsics[source_idx]
    target_k = intrinsics[target_idx]
    source_w2c = as_4x4(extrinsics[source_idx])
    target_w2c = as_4x4(extrinsics[target_idx])
    source_c2w = np.linalg.inv(source_w2c)

    u = samples["u"].astype(np.float32, copy=False)
    v = samples["v"].astype(np.float32, copy=False)
    z = samples["z"].astype(np.float32, copy=False)
    x = (u - source_k[0, 2]) / max(float(source_k[0, 0]), 1e-6) * z
    y = (v - source_k[1, 2]) / max(float(source_k[1, 1]), 1e-6) * z
    source_cam = np.stack([x, y, z, np.ones_like(z)], axis=1)
    world = (source_c2w @ source_cam.T).T
    target_cam = (target_w2c @ world.T).T[:, :3]

    z_t = target_cam[:, 2]
    u_t = target_k[0, 0] * (target_cam[:, 0] / np.maximum(z_t, 1e-6)) + target_k[0, 2]
    v_t = target_k[1, 1] * (target_cam[:, 1] / np.maximum(z_t, 1e-6)) + target_k[1, 2]

    h, w = depth.shape[1:]
    valid = np.isfinite(u_t) & np.isfinite(v_t) & np.isfinite(z_t) & (z_t > 1e-6)
    valid &= (u_t >= 0.0) & (u_t <= w - 2.0) & (v_t >= 0.0) & (v_t <= h - 2.0)
    sampled_depth = np.full(z_t.shape, np.nan, dtype=np.float32)
    sampled_conf = np.full(z_t.shape, np.nan, dtype=np.float32)
    if np.any(valid):
        sampled_depth[valid] = bilinear_sample(depth[target_idx], u_t[valid], v_t[valid])
        sampled_conf[valid] = bilinear_sample(conf[target_idx], u_t[valid], v_t[valid])
        valid &= np.isfinite(sampled_depth) & (sampled_depth > 1e-6)
    return sampled_depth, sampled_conf, z_t.astype(np.float32, copy=False), valid


def bilinear_sample(image: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    x0 = np.floor(u).astype(np.int32)
    y0 = np.floor(v).astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1
    wx = u - x0
    wy = v - y0
    top = image[y0, x0] * (1.0 - wx) + image[y0, x1] * wx
    bottom = image[y1, x0] * (1.0 - wx) + image[y1, x1] * wx
    return (top * (1.0 - wy) + bottom * wy).astype(np.float32, copy=False)


def residual_stats(
    *,
    target_idx: int | None,
    source_count: int,
    compared_count: int,
    signed: np.ndarray,
    abs_z: np.ndarray,
    rel: np.ndarray,
) -> dict[str, Any]:
    return {
        "target_idx": target_idx,
        "source_count": int(source_count),
        "compared_count": int(compared_count),
        "overlap_fraction": float(compared_count / max(source_count, 1)),
        "signed_median": percentile_or_none(signed, 50),
        "signed_mean": mean_or_none(signed),
        "abs_median": percentile_or_none(abs_z, 50),
        "abs_p75": percentile_or_none(abs_z, 75),
        "abs_p90": percentile_or_none(abs_z, 90),
        "abs_p95": percentile_or_none(abs_z, 95),
        "relative_median": percentile_or_none(rel, 50),
        "relative_p75": percentile_or_none(rel, 75),
        "relative_p90": percentile_or_none(rel, 90),
        "relative_p95": percentile_or_none(rel, 95),
        "relative_gt_0_05_fraction": fraction_gt(rel, 0.05),
        "relative_gt_0_10_fraction": fraction_gt(rel, 0.10),
        "relative_gt_0_20_fraction": fraction_gt(rel, 0.20),
    }


def empty_pair(target_idx: int | None, source_count: int = 0) -> dict[str, Any]:
    return {
        "target_idx": target_idx,
        "source_count": int(source_count),
        "compared_count": 0,
        "overlap_fraction": 0.0,
        "signed_median": None,
        "signed_mean": None,
        "abs_median": None,
        "abs_p75": None,
        "abs_p90": None,
        "abs_p95": None,
        "relative_median": None,
        "relative_p75": None,
        "relative_p90": None,
        "relative_p95": None,
        "relative_gt_0_05_fraction": None,
        "relative_gt_0_10_fraction": None,
        "relative_gt_0_20_fraction": None,
    }


def choose_prefix_refs(source_idx: int, centers: np.ndarray, *, max_refs: int) -> list[int]:
    candidates = list(range(source_idx))
    if len(candidates) <= max_refs:
        return candidates
    previous = list(range(max(0, source_idx - max_refs // 2), source_idx))
    remaining = [idx for idx in candidates if idx not in previous]
    nearest = sorted(
        remaining,
        key=lambda idx: float(np.linalg.norm(centers[source_idx] - centers[idx])),
    )[: max_refs - len(previous)]
    return sorted(set(previous + nearest))


def risk_flags(
    *,
    previous_pair: dict[str, Any],
    prefix_best: dict[str, Any],
    threshold: float,
    cumulative: dict[str, Any],
) -> list[str]:
    flags = []
    if none_to_zero(previous_pair.get("relative_median")) >= threshold:
        flags.append("previous_pair_relative_median_ge_threshold")
    if none_to_zero(previous_pair.get("relative_p90")) >= threshold * 2.0:
        flags.append("previous_pair_relative_p90_high")
    if none_to_zero(prefix_best.get("relative_median")) >= threshold:
        flags.append("best_prefix_relative_median_ge_threshold")
    npz = get_path(cumulative, "npz_streaming_style_conf_minus_one.minor_ratio_vs_k10")
    if isinstance(npz, (int, float)) and npz >= 1.10:
        flags.append("cumulative_npz_minor_ge_1_10_vs_k10")
    if isinstance(npz, (int, float)) and npz >= 1.35:
        flags.append("cumulative_npz_minor_ge_1_35_vs_k10")
    return flags


def build_summary(rows: list[dict[str, Any]], *, threshold: float) -> dict[str, Any]:
    risky = [
        row
        for row in rows
        if none_to_zero(row["previous_pair"].get("relative_median")) >= threshold
        or none_to_zero(row["best_prefix"].get("relative_median")) >= threshold
        or "previous_pair_relative_p90_high" in row["risk_flags"]
        or "cumulative_npz_minor_ge_1_35_vs_k10" in row["risk_flags"]
    ]
    first_npz_110 = first_with_flag(rows, "cumulative_npz_minor_ge_1_10_vs_k10")
    first_npz_135 = first_with_flag(rows, "cumulative_npz_minor_ge_1_35_vs_k10")
    top_previous = sorted(
        rows,
        key=lambda row: none_to_neg_inf(row["previous_pair"].get("relative_p90")),
        reverse=True,
    )[:8]
    top_prefix = sorted(
        rows,
        key=lambda row: none_to_neg_inf(row["best_prefix"].get("relative_median")),
        reverse=True,
    )[:8]
    first_geometry_spike = first_geometry_spike_row(rows, threshold=threshold)
    return {
        "status": "official_image_only_upstream_geometry_residuals_measured",
        "first_geometry_spike": slim_slot(first_geometry_spike) if first_geometry_spike else None,
        "first_cumulative_npz_minor_ge_1_10": slim_slot(first_npz_110) if first_npz_110 else None,
        "first_cumulative_npz_minor_ge_1_35": slim_slot(first_npz_135) if first_npz_135 else None,
        "top_previous_pair_relative_p90": [slim_slot(row) for row in top_previous],
        "top_best_prefix_relative_median": [slim_slot(row) for row in top_prefix],
        "risky_slot_count": len(risky),
        "risky_slots": [slim_slot(row) for row in risky[:12]],
        "interpretation": interpret_summary(first_geometry_spike, first_npz_110, first_npz_135),
    }


def first_geometry_spike_row(rows: list[dict[str, Any]], *, threshold: float) -> dict[str, Any] | None:
    for row in rows:
        prev_med = none_to_zero(row["previous_pair"].get("relative_median"))
        prev_p90 = none_to_zero(row["previous_pair"].get("relative_p90"))
        prefix_med = none_to_zero(row["best_prefix"].get("relative_median"))
        if prev_med >= threshold or prefix_med >= threshold or prev_p90 >= threshold * 2.0:
            return row
    return None


def first_with_flag(rows: list[dict[str, Any]], flag: str) -> dict[str, Any] | None:
    for row in rows:
        if flag in row["risk_flags"]:
            return row
    return None


def slim_slot(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    npz = row.get("cumulative_npz", {})
    return {
        "slot": row["slot"],
        "frame_id": row["frame_id"],
        "previous_frame_id": row["previous_frame_id"],
        "frame_gap_from_previous": row["frame_gap_from_previous"],
        "camera_step_from_previous": row["camera_step_from_previous"],
        "previous_relative_median": row["previous_pair"].get("relative_median"),
        "previous_relative_p90": row["previous_pair"].get("relative_p90"),
        "best_prefix_relative_median": row["best_prefix"].get("relative_median"),
        "best_prefix_relative_p90": row["best_prefix"].get("relative_p90"),
        "npz_minor_ratio_vs_k10": npz.get("minor_ratio_vs_k10"),
        "npz_bbox_ratio_vs_k10": npz.get("bbox_ratio_vs_k10"),
        "risk_flags": row.get("risk_flags", []),
    }


def interpret_summary(
    first_geometry: dict[str, Any] | None,
    first_npz_110: dict[str, Any] | None,
    first_npz_135: dict[str, Any] | None,
) -> str:
    if first_geometry and first_npz_110:
        return (
            f"First measured upstream projective residual spike is slot {first_geometry['slot']} "
            f"({first_geometry['frame_id']}); first NPZ minor growth >=1.10x is slot "
            f"{first_npz_110['slot']} ({first_npz_110['frame_id']}). This supports an upstream "
            "depth/pose consistency explanation rather than a pure point-cloud merge explanation."
        )
    if first_npz_110:
        return (
            f"NPZ minor growth starts at slot {first_npz_110['slot']} "
            f"({first_npz_110['frame_id']}), but this audit did not find a projective residual "
            "spike with the configured threshold."
        )
    if first_npz_135:
        return f"Large NPZ minor growth starts at slot {first_npz_135['slot']} ({first_npz_135['frame_id']})."
    return "No clear upstream residual spike was found with the configured threshold."


def cumulative_lookup(report: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = {}
    styles = get_path(report, "summary.styles") or {}
    if isinstance(styles, dict):
        for style_name, style_report in styles.items():
            if not isinstance(style_report, dict):
                continue
            for item in style_report.get("rows", []) or []:
                try:
                    k = int(item["k"])
                except (KeyError, TypeError, ValueError):
                    continue
                rows.setdefault(k, {})[style_name] = item
    if rows:
        return rows
    for item in report.get("cumulative", []) or []:
        try:
            k = int(item["k"])
        except (KeyError, TypeError, ValueError):
            continue
        rows[k] = item
    return rows


def camera_centers(extrinsics: np.ndarray) -> np.ndarray:
    return np.stack([camera_center_from_w2c(ext) for ext in extrinsics], axis=0)


def camera_center_from_w2c(ext: np.ndarray) -> np.ndarray:
    w2c = as_4x4(ext)
    c2w = np.linalg.inv(w2c)
    return c2w[:3, 3].astype(np.float32, copy=False)


def as_4x4(ext: np.ndarray) -> np.ndarray:
    if ext.shape == (4, 4):
        return ext.astype(np.float32, copy=False)
    if ext.shape == (3, 4):
        out = np.eye(4, dtype=np.float32)
        out[:3, :4] = ext
        return out
    raise ValueError(f"Expected (3,4) or (4,4), got {ext.shape}")


def camera_diag(centers: np.ndarray) -> float:
    if centers.size == 0:
        return 0.0
    extent = np.max(centers, axis=0) - np.min(centers, axis=0)
    return float(np.linalg.norm(extent))


def frame_id(frame: dict[str, Any], default: int) -> str:
    return str(frame.get("frameId") or frame.get("frameID") or f"slot-{default:03d}")


def frame_index(frame: dict[str, Any], default: int) -> int:
    fid = frame_id(frame, default)
    tail = fid.rsplit("-", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return int(default)


def percentile_or_none(values: np.ndarray, pct: float) -> float | None:
    if values.size == 0:
        return None
    return float(np.percentile(values, pct))


def mean_or_none(values: np.ndarray) -> float | None:
    if values.size == 0:
        return None
    return float(np.mean(values))


def fraction_gt(values: np.ndarray, threshold: float) -> float | None:
    if values.size == 0:
        return None
    return float(np.count_nonzero(values > threshold) / values.size)


def none_to_inf(value: Any) -> float:
    return math.inf if value is None else float(value)


def none_to_neg_inf(value: Any) -> float:
    return -math.inf if value is None else float(value)


def none_to_zero(value: Any) -> float:
    return 0.0 if value is None else float(value)


def get_path(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def read_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return read_json(path)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        "# Official PyTorch image-only geometry consistency audit",
        "",
        f"window: `{report['scope']['window_id']}`",
        "",
        "## 结论",
        "",
        f"- status: `{summary['status']}`",
        f"- first geometry spike: `{format_slim(summary['first_geometry_spike'])}`",
        f"- first NPZ minor >= 1.10x: `{format_slim(summary['first_cumulative_npz_minor_ge_1_10'])}`",
        f"- first NPZ minor >= 1.35x: `{format_slim(summary['first_cumulative_npz_minor_ge_1_35'])}`",
        f"- interpretation: {summary['interpretation']}",
        "",
        "## 大白话",
        "",
        "- 这个审计不生成点云，也不改 DA3 输出；它直接检查官方 image-only 的深度、内参、cam_dec 位姿在同一个 window 内是否互相投得上。",
        "- 如果某一帧投到前面帧时，同一个空间点在目标帧深度上差很多，那厚层就已经是上游几何一致性问题，下游 PLY 只是把它显出来。",
        "- `previous_*` 是当前帧投到前一帧；`best_prefix_*` 是当前帧投到前缀若干帧里取最好的重叠残差。",
        "",
        "## Top Previous-Pair Residuals",
        "",
        "| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary["top_previous_pair_relative_p90"]:
        lines.append(markdown_slot_row(row))
    lines.extend(
        [
            "",
            "## Top Best-Prefix Residuals",
            "",
            "| slot | frame | prev | gap | cam step | prev rel med | prev rel p90 | best prefix med | npz minor/k10 | flags |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in summary["top_best_prefix_relative_median"]:
        lines.append(markdown_slot_row(row))
    lines.extend(
        [
            "",
            "## Parameters",
            "",
            f"- stride: `{report['parameters']['stride']}`",
            f"- confidence: `{report['parameters']['confidence_convention']}`",
            f"- conf_threshold_coef: `{report['parameters']['conf_threshold_coef']}`",
            f"- relative_risk_threshold: `{report['parameters']['relative_risk_threshold']}`",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def markdown_slot_row(row: dict[str, Any]) -> str:
    return (
        f"| {row['slot']} | `{row['frame_id']}` | `{row['previous_frame_id']}` | "
        f"{row['frame_gap_from_previous']} | {fmt(row['camera_step_from_previous'])} | "
        f"{fmt(row['previous_relative_median'])} | {fmt(row['previous_relative_p90'])} | "
        f"{fmt(row['best_prefix_relative_median'])} | {fmt(row['npz_minor_ratio_vs_k10'])} | "
        f"{', '.join(row['risk_flags'])} |"
    )


def format_slim(row: dict[str, Any] | None) -> str:
    if row is None:
        return "None"
    return (
        f"slot {row['slot']} {row['frame_id']} prev={row['previous_frame_id']} "
        f"prev_rel_med={fmt(row['previous_relative_median'])} "
        f"npz_minor/k10={fmt(row['npz_minor_ratio_vs_k10'])}"
    )


def fmt(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{float(value):.4f}"


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "scope": report["scope"],
        "summary": report["summary"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
