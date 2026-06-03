#!/usr/bin/env python3
"""Read-only pose/depth/scale audit for one official-postprocessed K35 window.

The diagnostic answers: when first10 grows to first35, do official point-cloud
thickness metrics track pose span, depth distribution, confidence filtering, or
postprocess pose scale?

It does not write PLYs, change thresholds, run loop, or alter DA3 outputs.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--da3-dir", type=Path, required=True)
    parser.add_argument("--postprocess-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_016")
    parser.add_argument("--seed", type=int, default=4316)
    parser.add_argument("--glb-conf-thresh", type=float, default=1.05)
    parser.add_argument("--glb-conf-percentile", type=float, default=40.0)
    parser.add_argument("--glb-ensure-percentile", type=float, default=90.0)
    parser.add_argument("--glb-num-max-points", type=int, default=1_000_000)
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.75)
    parser.add_argument("--npz-sample-ratio", type=float, default=0.015)
    args = parser.parse_args()

    strict = load_strict_micro_audit_module()
    reports = read_json(args.da3_dir / "mac_da3_window_reports.json")
    window_reports = {str(row["windowID"]): row for row in reports.get("windows", [])}
    if args.window_id not in window_reports:
        raise KeyError(f"{args.window_id} not found in {args.da3_dir}")

    frames = sorted(
        window_reports[args.window_id].get("frames", []),
        key=lambda row: int(row.get("windowSlot", 0)),
    )
    slots = [
        strict.load_slot(frame, capture_dir=args.capture_dir, da3_dir=args.da3_dir)
        for frame in frames
    ]
    pose_scale = find_pose_scale(args.postprocess_report, args.window_id)
    per_slot = per_slot_metrics(slots)
    cumulative = []
    for k in range(1, len(slots) + 1):
        group = strict.build_group(slots, list(range(k)))
        cumulative.append(
            {
                "k": k,
                "frame_ids": group["frame_ids"],
                "pose": pose_metrics(group["camera_centers"]),
                "depth": summarize(group["depth"]),
                "confidence": summarize(group["conf"]),
                "glb_style": export_metrics(
                    strict,
                    group,
                    style="glb_style",
                    seed=args.seed + k,
                    args=args,
                ),
                "npz_streaming_style": export_metrics(
                    strict,
                    group,
                    style="npz_streaming_style",
                    seed=args.seed + 1000 + k,
                    args=args,
                ),
            }
        )

    report = {
        "schema_version": "pocketworld_official_k35_window_pose_depth_scale_audit_v1",
        "scope": {
            "capture_dir": str(args.capture_dir),
            "da3_dir": str(args.da3_dir),
            "postprocess_report": str(args.postprocess_report),
            "window_id": args.window_id,
            "pose_scale": pose_scale,
            "note": "Read-only diagnostic. Uses official-postprocessed CoreML outputs and official GLB/NPZ-style point metrics; writes no PLYs.",
        },
        "parameters": {
            "seed": args.seed,
            "glb_style": {
                "conf_thresh": args.glb_conf_thresh,
                "conf_thresh_percentile": args.glb_conf_percentile,
                "ensure_thresh_percentile": args.glb_ensure_percentile,
                "num_max_points": args.glb_num_max_points,
            },
            "npz_streaming_style": {
                "conf_threshold_coef": args.npz_conf_threshold_coef,
                "sample_ratio": args.npz_sample_ratio,
            },
        },
        "per_slot": per_slot,
        "cumulative": cumulative,
    }
    report["summary"] = summarize_cumulative(report)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / f"{args.window_id}_pose_depth_scale_audit.json", report)
    write_markdown(args.out_dir / f"{args.window_id}_pose_depth_scale_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def load_strict_micro_audit_module() -> Any:
    path = Path(__file__).with_name("strict_k35_window_official_filter_micro_audit.py")
    spec = importlib.util.spec_from_file_location("strict_k35_window_official_filter_micro_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_pose_scale(postprocess_report: Path, window_id: str) -> float | None:
    report = read_json(postprocess_report)
    for row in report.get("windows", []):
        if str(row.get("windowID")) == window_id:
            return as_float(row.get("poseScale"))
    return None


def per_slot_metrics(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    centers = np.stack([slot["camera_center"] for slot in slots], axis=0)
    for index, slot in enumerate(slots):
        cumulative_centers = centers[: index + 1]
        step = None
        if index > 0:
            step = float(np.linalg.norm(centers[index] - centers[index - 1]))
        rows.append(
            {
                "slot": index,
                "frame_id": slot["frame_id"],
                "frame_index": slot["frame_index"],
                "depth": summarize(slot["depth"]),
                "confidence": summarize(slot["conf"]),
                "camera_center": [float(v) for v in centers[index]],
                "step_from_previous": step,
                "cumulative_pose_diag": camera_center_diag(cumulative_centers),
            }
        )
    return rows


def export_metrics(strict: Any, group: dict[str, Any], *, style: str, seed: int, args: Any) -> dict[str, Any]:
    if style == "glb_style":
        exported = strict.export_glb_style_group(
            group,
            conf_thresh=args.glb_conf_thresh,
            conf_percentile=args.glb_conf_percentile,
            ensure_percentile=args.glb_ensure_percentile,
            num_max_points=args.glb_num_max_points,
            seed=seed,
        )
    elif style == "npz_streaming_style":
        exported = strict.export_npz_streaming_style_group(
            group,
            conf_threshold_coef=args.npz_conf_threshold_coef,
            sample_ratio=args.npz_sample_ratio,
            seed=seed,
        )
    else:
        raise ValueError(style)
    metrics = strict.metrics_for_group(group, exported)
    pc = metrics.get("point_cloud", {})
    pca = metrics.get("pca", {})
    return {
        "conf_threshold": as_float(exported.get("filter", {}).get("conf_threshold")),
        "valid_fraction_of_pixels": as_float(metrics.get("valid_fraction_of_pixels")),
        "valid_point_count_before_downsample": metrics.get("valid_point_count_before_downsample"),
        "sampled_point_count": metrics.get("sampled_point_count"),
        "bbox_diag_p01_p99": as_float(pc.get("bbox_diag_p01_p99")),
        "bbox_diag_p05_p95": as_float(pc.get("bbox_diag_p05_p95")),
        "pca_minor_extent": as_float(pca.get("minor_extent")),
        "pca_minor_to_major_ratio": as_float(pca.get("minor_to_major_ratio")),
    }


def summarize_cumulative(report: dict[str, Any]) -> dict[str, Any]:
    cumulative = report["cumulative"]
    baseline = cumulative[9] if len(cumulative) >= 10 else cumulative[-1]
    out = {
        "baseline_k": baseline["k"],
        "k35": cumulative[-1],
        "styles": {},
        "pose": {
            "k10_pose_diag": baseline["pose"]["camera_center_diag"],
            "k35_pose_diag": cumulative[-1]["pose"]["camera_center_diag"],
            "k35_over_k10_pose_diag": safe_ratio(
                cumulative[-1]["pose"]["camera_center_diag"],
                baseline["pose"]["camera_center_diag"],
            ),
            "largest_step": max(
                (
                    row["step_from_previous"]
                    for row in report["per_slot"]
                    if row["step_from_previous"] is not None
                ),
                default=None,
            ),
        },
        "depth": {
            "k10_p95": baseline["depth"]["p95"],
            "k35_p95": cumulative[-1]["depth"]["p95"],
            "k35_over_k10_p95": safe_ratio(cumulative[-1]["depth"]["p95"], baseline["depth"]["p95"]),
        },
    }
    for style in ["glb_style", "npz_streaming_style"]:
        base = baseline[style]
        rows = []
        for item in cumulative:
            row = {
                "k": item["k"],
                "pose_diag": item["pose"]["camera_center_diag"],
                "bbox_ratio_vs_k10": safe_ratio(item[style]["bbox_diag_p01_p99"], base["bbox_diag_p01_p99"]),
                "minor_ratio_vs_k10": safe_ratio(item[style]["pca_minor_extent"], base["pca_minor_extent"]),
                "conf_threshold_ratio_vs_k10": safe_ratio(item[style]["conf_threshold"], base["conf_threshold"]),
                "valid_fraction_delta_vs_k10": safe_delta(
                    item[style]["valid_fraction_of_pixels"],
                    base["valid_fraction_of_pixels"],
                ),
            }
            rows.append(row)
        out["styles"][style] = {
            "k35_over_k10": rows[-1],
            "first_bbox_ratio_ge_1_10_after_k10": first_k(rows, "bbox_ratio_vs_k10", 1.10),
            "first_minor_ratio_ge_1_10_after_k10": first_k(rows, "minor_ratio_vs_k10", 1.10),
            "first_minor_ratio_ge_1_35_after_k10": first_k(rows, "minor_ratio_vs_k10", 1.35),
            "rows": rows,
        }
    out["interpretation"] = interpret_summary(out)
    return out


def interpret_summary(summary: dict[str, Any]) -> list[str]:
    lines = [
        "K35 first35 thickening is measured before any cross-window loop can act, so loop is not the direct producer of this window-internal layer.",
    ]
    pose_ratio = summary["pose"]["k35_over_k10_pose_diag"]
    if pose_ratio is not None and pose_ratio >= 3.0:
        lines.append(
            f"Pose span expands strongly from k10 to k35 ({pose_ratio:.3f}x camera-center bbox diag), so later-slot view span is the strongest current suspect."
        )
    depth_ratio = summary["depth"]["k35_over_k10_p95"]
    if depth_ratio is not None:
        lines.append(
            f"Depth p95 changes by {depth_ratio:.3f}x from k10 to k35; this is smaller than the pose-span expansion and does not alone explain the thick layer."
        )
    for style, data in summary["styles"].items():
        k35 = data["k35_over_k10"]
        lines.append(
            f"{style}: k35/k10 bbox={fmt(k35['bbox_ratio_vs_k10'])}, minor={fmt(k35['minor_ratio_vs_k10'])}, conf_threshold={fmt(k35['conf_threshold_ratio_vs_k10'])}, valid_delta={fmt(k35['valid_fraction_delta_vs_k10'])}."
        )
    lines.append(
        "Next official-consistency check should inspect late-slot pose/depth consistency inside window_016, not VPR replacement."
    )
    return lines


def first_k(rows: list[dict[str, Any]], key: str, threshold: float) -> dict[str, Any] | None:
    for row in rows:
        if row["k"] <= 10:
            continue
        value = row.get(key)
        if value is not None and value >= threshold:
            return {"k": row["k"], key: value, "pose_diag": row["pose_diag"]}
    return None


def pose_metrics(centers: np.ndarray) -> dict[str, Any]:
    steps = np.linalg.norm(np.diff(centers, axis=0), axis=1) if len(centers) > 1 else np.array([])
    return {
        "camera_center_diag": camera_center_diag(centers),
        "step_mean": float(np.mean(steps)) if len(steps) else None,
        "step_max": float(np.max(steps)) if len(steps) else None,
    }


def camera_center_diag(centers: np.ndarray) -> float:
    if len(centers) == 0:
        return 0.0
    extent = np.max(centers, axis=0) - np.min(centers, axis=0)
    return float(np.linalg.norm(extent))


def summarize(array: np.ndarray) -> dict[str, Any]:
    values = np.asarray(array, dtype=np.float64).reshape(-1)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"count": 0}
    return {
        "count": int(values.size),
        "min": float(np.min(values)),
        "p05": float(np.percentile(values, 5)),
        "median": float(np.median(values)),
        "mean": float(np.mean(values)),
        "p95": float(np.percentile(values, 95)),
        "max": float(np.max(values)),
        "std": float(np.std(values)),
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        f"# {report['scope']['window_id']} Pose / Depth / Scale Audit",
        "",
        "这是 read-only diagnostic。输入是 official-postprocessed CoreML K35 window 输出；不生成 PLY，不改阈值，不做 loop/graph patch/mesh。",
        "",
        "## Summary",
        "",
        f"- pose_scale: `{fmt(report['scope']['pose_scale'])}`",
        f"- k10 pose diag: `{fmt(summary['pose']['k10_pose_diag'])}`",
        f"- k35 pose diag: `{fmt(summary['pose']['k35_pose_diag'])}`",
        f"- k35/k10 pose diag: `{fmt(summary['pose']['k35_over_k10_pose_diag'])}`",
        f"- k10 depth p95: `{fmt(summary['depth']['k10_p95'])}`",
        f"- k35 depth p95: `{fmt(summary['depth']['k35_p95'])}`",
        f"- k35/k10 depth p95: `{fmt(summary['depth']['k35_over_k10_p95'])}`",
        "",
        "## Official Point Metric Growth",
        "",
        "| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for style, data in summary["styles"].items():
        k35 = data["k35_over_k10"]
        lines.append(
            "| {style} | {bbox_k} | {minor_k} | {minor35_k} | {bbox} | {minor} | {thr} | {valid} |".format(
                style=style,
                bbox_k=fmt_event(data["first_bbox_ratio_ge_1_10_after_k10"]),
                minor_k=fmt_event(data["first_minor_ratio_ge_1_10_after_k10"]),
                minor35_k=fmt_event(data["first_minor_ratio_ge_1_35_after_k10"]),
                bbox=fmt(k35["bbox_ratio_vs_k10"]),
                minor=fmt(k35["minor_ratio_vs_k10"]),
                thr=fmt(k35["conf_threshold_ratio_vs_k10"]),
                valid=fmt(k35["valid_fraction_delta_vs_k10"]),
            )
        )
    lines.extend(["", "## Cumulative K Table", ""])
    lines.append(
        "| k | pose diag | depth p95 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    for item in report["cumulative"]:
        k = item["k"]
        glb = summary["styles"]["glb_style"]["rows"][k - 1]
        npz = summary["styles"]["npz_streaming_style"]["rows"][k - 1]
        lines.append(
            f"| {k} | {fmt(item['pose']['camera_center_diag'])} | {fmt(item['depth']['p95'])} | {fmt(glb['bbox_ratio_vs_k10'])} | {fmt(glb['minor_ratio_vs_k10'])} | {fmt(npz['bbox_ratio_vs_k10'])} | {fmt(npz['minor_ratio_vs_k10'])} |"
        )
    lines.extend(["", "## 初步解释", ""])
    for item in summary["interpretation"]:
        lines.append(f"- {item}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    return {
        "window_id": report["scope"]["window_id"],
        "pose_scale": report["scope"]["pose_scale"],
        "k35_over_k10_pose_diag": summary["pose"]["k35_over_k10_pose_diag"],
        "k35_over_k10_depth_p95": summary["depth"]["k35_over_k10_p95"],
        "glb": summary["styles"]["glb_style"]["k35_over_k10"],
        "npz": summary["styles"]["npz_streaming_style"]["k35_over_k10"],
        "out_dir": str(Path(report["scope"]["da3_dir"]).parent / "diagnostics"),
    }


def fmt_event(event: dict[str, Any] | None) -> str:
    if event is None:
        return "-"
    return f"k={event['k']} ({fmt(next(v for k, v in event.items() if k.endswith('_vs_k10')))})"


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.6g}"


def safe_ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return float(num) / float(den)


def safe_delta(num: float | None, den: float | None) -> float | None:
    if num is None or den is None:
        return None
    return float(num) - float(den)


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    out = float(value)
    if not math.isfinite(out):
        return None
    return out


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
