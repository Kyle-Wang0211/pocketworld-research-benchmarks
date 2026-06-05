#!/usr/bin/env python3
"""Read-only thickness audit for official PyTorch DA3 image-only window output.

The input is produced by official_pytorch_window_export.py in image_only mode.
This script does not run DA3 and does not change model outputs. It rebuilds the
same slot structure used by the existing official GLB/NPZ-style point metrics,
then measures cumulative K growth inside one window.

Important confidence convention:
- raw API prediction.conf is used for GLB-style export diagnostics.
- DA3-Streaming subtracts 1.0 before writing results_output/frame_*.npz, so the
  NPZ-streaming-style diagnostic uses max(raw_conf - 1.0, 0.0).
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
    parser.add_argument("--pytorch-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_016")
    parser.add_argument("--seed", type=int, default=50435)
    parser.add_argument("--glb-conf-thresh", type=float, default=1.05)
    parser.add_argument("--glb-conf-percentile", type=float, default=40.0)
    parser.add_argument("--glb-ensure-percentile", type=float, default=90.0)
    parser.add_argument("--glb-num-max-points", type=int, default=1_000_000)
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--npz-sample-ratio", type=float, default=0.015)
    args = parser.parse_args()

    strict = load_strict_micro_audit_module()
    manifest = read_json(args.manifest)
    export_report_path = args.pytorch_dir / "official_pytorch_window_000_export_report.json"
    export_report = read_json(export_report_path) if export_report_path.exists() else {}

    depth = np.load(args.pytorch_dir / "pytorch_depth.npy").astype(np.float32, copy=False)
    conf_raw = np.load(args.pytorch_dir / "pytorch_conf.npy").astype(np.float32, copy=False)
    intrinsics = np.load(args.pytorch_dir / "pytorch_intrinsics.npy").astype(np.float32, copy=False)
    extrinsics = np.load(args.pytorch_dir / "pytorch_extrinsics.npy").astype(np.float32, copy=False)
    images = np.load(args.pytorch_dir / "pytorch_processed_images.npy").astype(np.uint8, copy=False)
    validate_shapes(depth, conf_raw, intrinsics, extrinsics, images)

    frame_rows = list(manifest.get("frames") or [])
    if len(frame_rows) != int(depth.shape[0]):
        raise ValueError(
            f"Manifest frame count {len(frame_rows)} does not match PyTorch output {depth.shape[0]}"
        )

    conf_streaming = np.maximum(conf_raw - 1.0, 0.0).astype(np.float32, copy=False)
    raw_slots = build_slots(
        frame_rows,
        depth=depth,
        conf=conf_raw,
        intrinsics=intrinsics,
        extrinsics=extrinsics,
        images=images,
        strict=strict,
    )
    streaming_slots = build_slots(
        frame_rows,
        depth=depth,
        conf=conf_streaming,
        intrinsics=intrinsics,
        extrinsics=extrinsics,
        images=images,
        strict=strict,
    )

    cumulative = []
    for k in range(1, len(raw_slots) + 1):
        group_slots = list(range(k))
        raw_group = strict.build_group(raw_slots, group_slots)
        streaming_group = strict.build_group(streaming_slots, group_slots)
        cumulative.append(
            {
                "k": k,
                "frame_ids": raw_group["frame_ids"],
                "pose": pose_metrics(raw_group["camera_centers"]),
                "depth": summarize(depth[:k]),
                "confidence_raw": summarize(conf_raw[:k]),
                "confidence_streaming_npz": summarize(conf_streaming[:k]),
                "glb_style_raw_conf": export_metrics(
                    strict,
                    raw_group,
                    style="glb_style",
                    seed=args.seed + k,
                    args=args,
                ),
                "npz_streaming_style_conf_minus_one": export_metrics(
                    strict,
                    streaming_group,
                    style="npz_streaming_style",
                    seed=args.seed + 1000 + k,
                    args=args,
                ),
            }
        )

    report = {
        "schema_version": "pocketworld_official_pytorch_image_only_window_pose_depth_scale_audit_v1",
        "scope": {
            "pytorch_dir": str(args.pytorch_dir),
            "manifest": str(args.manifest),
            "export_report": str(export_report_path) if export_report_path.exists() else None,
            "window_id": args.window_id,
            "source_window_id": manifest.get("sourceWindowID"),
            "frame_count": int(depth.shape[0]),
            "processed_shape_nhwc": [int(v) for v in images.shape],
            "camera_mode": export_report.get("parameters", {}).get("camera_mode"),
            "ref_view_strategy": export_report.get("parameters", {}).get("ref_view_strategy"),
            "process_res": export_report.get("parameters", {}).get("process_res"),
            "process_res_method": export_report.get("parameters", {}).get("process_res_method"),
            "runtime": export_report.get("runtime"),
            "note": (
                "Official PyTorch image-only authority path. No AR/input cameras; poses come from "
                "DA3 cam_dec. This audit measures window-internal K growth only."
            ),
        },
        "parameters": {
            "seed": args.seed,
            "glb_style_raw_conf": {
                "conf_thresh": args.glb_conf_thresh,
                "conf_thresh_percentile": args.glb_conf_percentile,
                "ensure_thresh_percentile": args.glb_ensure_percentile,
                "num_max_points": args.glb_num_max_points,
                "confidence_convention": "raw prediction.conf from DepthAnything3.inference",
            },
            "npz_streaming_style_conf_minus_one": {
                "conf_threshold_coef": args.npz_conf_threshold_coef,
                "sample_ratio": args.npz_sample_ratio,
                "confidence_convention": (
                    "DA3-Streaming writes frame_*.npz after predictions.conf -= 1.0; "
                    "this audit uses max(raw_conf - 1.0, 0.0)."
                ),
            },
        },
        "per_slot": per_slot_metrics(raw_slots),
        "cumulative": cumulative,
    }
    report["summary"] = summarize_cumulative(report)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / f"{args.window_id}_official_pytorch_image_only_pose_depth_scale_audit.json", report)
    write_markdown(
        args.out_dir / f"{args.window_id}_official_pytorch_image_only_pose_depth_scale_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def validate_shapes(
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    images: np.ndarray,
) -> None:
    if depth.ndim != 3:
        raise ValueError(f"Expected depth NHW, got {depth.shape}")
    if conf.shape != depth.shape:
        raise ValueError(f"Conf shape {conf.shape} does not match depth {depth.shape}")
    if intrinsics.shape != (depth.shape[0], 3, 3):
        raise ValueError(f"Expected intrinsics (N,3,3), got {intrinsics.shape}")
    if extrinsics.shape not in {(depth.shape[0], 3, 4), (depth.shape[0], 4, 4)}:
        raise ValueError(f"Expected extrinsics (N,3,4) or (N,4,4), got {extrinsics.shape}")
    if images.shape != (depth.shape[0], depth.shape[1], depth.shape[2], 3):
        raise ValueError(f"Expected images NHW3 matching depth, got {images.shape}")


def build_slots(
    frame_rows: list[dict[str, Any]],
    *,
    depth: np.ndarray,
    conf: np.ndarray,
    intrinsics: np.ndarray,
    extrinsics: np.ndarray,
    images: np.ndarray,
    strict: Any,
) -> list[dict[str, Any]]:
    slots = []
    for index, frame in enumerate(frame_rows):
        ext = extrinsics[index]
        if ext.shape == (4, 4):
            ext = ext[:3, :4]
        slots.append(
            {
                "window_slot": index,
                "frame_id": str(frame.get("frameId") or frame.get("frameID") or index),
                "frame_index": parse_frame_index(frame.get("frameId"), default=index),
                "image_relative_path": str(frame.get("jpegPath") or ""),
                "depth": depth[index].astype(np.float32, copy=False),
                "conf": conf[index].astype(np.float32, copy=False),
                "intrinsics": intrinsics[index].astype(np.float32, copy=False),
                "extrinsics": ext.astype(np.float32, copy=False),
                "image": images[index].astype(np.uint8, copy=False),
                "camera_center": strict.camera_center_from_w2c(ext),
            }
        )
    return slots


def parse_frame_index(frame_id: Any, *, default: int) -> int:
    if not isinstance(frame_id, str):
        return default
    tail = frame_id.rsplit("-", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return default


def load_strict_micro_audit_module() -> Any:
    path = Path(__file__).with_name("strict_k35_window_official_filter_micro_audit.py")
    spec = importlib.util.spec_from_file_location("strict_k35_window_official_filter_micro_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def per_slot_metrics(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    centers = np.stack([slot["camera_center"] for slot in slots], axis=0)
    rows = []
    for index, slot in enumerate(slots):
        step = None
        if index > 0:
            step = float(np.linalg.norm(centers[index] - centers[index - 1]))
        rows.append(
            {
                "slot": index,
                "frame_id": slot["frame_id"],
                "frame_index": slot["frame_index"],
                "depth": summarize(slot["depth"]),
                "confidence_raw": summarize(slot["conf"]),
                "camera_center": [float(v) for v in centers[index]],
                "step_from_previous": step,
                "cumulative_pose_diag": camera_center_diag(centers[: index + 1]),
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
        "checkpoints": {},
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
        "styles": {},
    }
    for k in [10, 17, 35]:
        if len(cumulative) >= k:
            out["checkpoints"][f"k{k}"] = checkpoint_summary(cumulative[k - 1], baseline)
    for style in ["glb_style_raw_conf", "npz_streaming_style_conf_minus_one"]:
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
    out["decision"] = decision(out)
    return out


def checkpoint_summary(item: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "k": item["k"],
        "pose_diag": item["pose"]["camera_center_diag"],
        "pose_ratio_vs_k10": safe_ratio(
            item["pose"]["camera_center_diag"],
            baseline["pose"]["camera_center_diag"],
        ),
        "depth_p95": item["depth"]["p95"],
        "depth_p95_ratio_vs_k10": safe_ratio(item["depth"]["p95"], baseline["depth"]["p95"]),
        "glb_bbox_ratio_vs_k10": safe_ratio(
            item["glb_style_raw_conf"]["bbox_diag_p01_p99"],
            baseline["glb_style_raw_conf"]["bbox_diag_p01_p99"],
        ),
        "glb_minor_ratio_vs_k10": safe_ratio(
            item["glb_style_raw_conf"]["pca_minor_extent"],
            baseline["glb_style_raw_conf"]["pca_minor_extent"],
        ),
        "npz_bbox_ratio_vs_k10": safe_ratio(
            item["npz_streaming_style_conf_minus_one"]["bbox_diag_p01_p99"],
            baseline["npz_streaming_style_conf_minus_one"]["bbox_diag_p01_p99"],
        ),
        "npz_minor_ratio_vs_k10": safe_ratio(
            item["npz_streaming_style_conf_minus_one"]["pca_minor_extent"],
            baseline["npz_streaming_style_conf_minus_one"]["pca_minor_extent"],
        ),
    }


def decision(summary: dict[str, Any]) -> dict[str, Any]:
    npz_minor = summary["styles"]["npz_streaming_style_conf_minus_one"]["k35_over_k10"][
        "minor_ratio_vs_k10"
    ]
    glb_minor = summary["styles"]["glb_style_raw_conf"]["k35_over_k10"]["minor_ratio_vs_k10"]
    if npz_minor is None or glb_minor is None:
        label = "insufficient_points"
    elif npz_minor >= 1.35 or glb_minor >= 1.35:
        label = "official_image_only_k35_shows_window_internal_thickening"
    elif npz_minor >= 1.10 or glb_minor >= 1.10:
        label = "official_image_only_k35_has_mild_window_internal_growth"
    else:
        label = "official_image_only_k35_no_major_window_internal_thickening"
    return {
        "label": label,
        "basis": (
            "Uses official PyTorch image-only cam_dec poses, official process_res=504 preprocess, "
            "and official GLB/NPZ-style cumulative point metrics."
        ),
    }


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


def first_k(rows: list[dict[str, Any]], key: str, threshold: float) -> dict[str, Any] | None:
    for row in rows:
        if row["k"] <= 10:
            continue
        value = row.get(key)
        if value is not None and value >= threshold:
            return {"k": row["k"], key: value, "pose_diag": row["pose_diag"]}
    return None


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    runtime = report["scope"].get("runtime") or {}
    lines = [
        f"# {report['scope']['window_id']} Official PyTorch Image-Only Thickness Audit",
        "",
        "这是官方 image-only 权威路径的只读厚层审计：不输入 AR/camera，不跑 CoreML pose-conditioned 兼容路径，不改 DA3 输出。",
        "",
        "## Scope",
        "",
        f"- camera_mode: `{report['scope']['camera_mode']}`",
        f"- process_res: `{report['scope']['process_res']}`",
        f"- process_res_method: `{report['scope']['process_res_method']}`",
        f"- processed shape NHWC: `{report['scope']['processed_shape_nhwc']}`",
        f"- RSS after: `{fmt(runtime.get('rss_after_mb'))} MB`",
        f"- run_ms: `{fmt(runtime.get('run_ms'))}`",
        f"- decision: `{summary['decision']['label']}`",
        "",
        "## Confidence Convention",
        "",
        "- `glb_style_raw_conf` 使用 DepthAnything3 API 的 raw `prediction.conf`。",
        "- `npz_streaming_style_conf_minus_one` 复刻 DA3-Streaming 保存 `frame_*.npz` 前的 `predictions.conf -= 1.0`。",
        "",
        "## Summary",
        "",
        f"- k10 pose diag: `{fmt(summary['pose']['k10_pose_diag'])}`",
        f"- k35 pose diag: `{fmt(summary['pose']['k35_pose_diag'])}`",
        f"- k35/k10 pose diag: `{fmt(summary['pose']['k35_over_k10_pose_diag'])}`",
        f"- k10 depth p95: `{fmt(summary['depth']['k10_p95'])}`",
        f"- k35 depth p95: `{fmt(summary['depth']['k35_p95'])}`",
        f"- k35/k10 depth p95: `{fmt(summary['depth']['k35_over_k10_p95'])}`",
        "",
        "## Checkpoints",
        "",
        "| checkpoint | pose/k10 | depth p95/k10 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, item in summary["checkpoints"].items():
        lines.append(
            f"| {name} | {fmt(item['pose_ratio_vs_k10'])} | {fmt(item['depth_p95_ratio_vs_k10'])} | "
            f"{fmt(item['glb_bbox_ratio_vs_k10'])} | {fmt(item['glb_minor_ratio_vs_k10'])} | "
            f"{fmt(item['npz_bbox_ratio_vs_k10'])} | {fmt(item['npz_minor_ratio_vs_k10'])} |"
        )
    lines.extend(
        [
            "",
            "## Official Point Metric Growth",
            "",
            "| style | first bbox >=1.10 | first minor >=1.10 | first minor >=1.35 | k35/k10 bbox | k35/k10 minor | k35/k10 conf thr | valid frac delta |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
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
        glb = summary["styles"]["glb_style_raw_conf"]["rows"][k - 1]
        npz = summary["styles"]["npz_streaming_style_conf_minus_one"]["rows"][k - 1]
        lines.append(
            f"| {k} | {fmt(item['pose']['camera_center_diag'])} | {fmt(item['depth']['p95'])} | "
            f"{fmt(glb['bbox_ratio_vs_k10'])} | {fmt(glb['minor_ratio_vs_k10'])} | "
            f"{fmt(npz['bbox_ratio_vs_k10'])} | {fmt(npz['minor_ratio_vs_k10'])} |"
        )
    lines.extend(
        [
            "",
            "## 判读",
            "",
            f"- `{summary['decision']['label']}`",
            f"- {summary['decision']['basis']}",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    return {
        "window_id": report["scope"]["window_id"],
        "camera_mode": report["scope"]["camera_mode"],
        "process_res": report["scope"]["process_res"],
        "processed_shape_nhwc": report["scope"]["processed_shape_nhwc"],
        "decision": summary["decision"]["label"],
        "k35_over_k10_pose_diag": summary["pose"]["k35_over_k10_pose_diag"],
        "k35_over_k10_depth_p95": summary["depth"]["k35_over_k10_p95"],
        "glb_k35_over_k10": summary["styles"]["glb_style_raw_conf"]["k35_over_k10"],
        "npz_k35_over_k10": summary["styles"]["npz_streaming_style_conf_minus_one"]["k35_over_k10"],
        "out_dir": str(Path(report["scope"]["pytorch_dir"]).parent / "diagnostics"),
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
