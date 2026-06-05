#!/usr/bin/env python3
"""Counterfactual point metrics for DA3 continuity quarantine candidates.

This audit keeps DA3/CoreML outputs fixed and only changes which already
predicted frames are included in official-style point generation. It is not a
replacement for re-running DA3 on a quarantined window; it is a cheap signal for
whether high-risk continuity frames are directly responsible for thickness.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
DEFAULT_DA3_DIR = DEFAULT_DATASET / "da3_seq_k35_coreml_pose_dart_camera_contract_window016_cpu_official_save_postprocess_2026_06_05"
THRESHOLDS = {
    "timestampDeltaSecondsWarningGt": 2.0,
    "translationStepMWarningGt": 0.25,
    "azimuthDeltaRadWarningGt": 0.35,
    "elevationDeltaRadWarningGt": 0.25,
    "qualityScoreWarningLt": 0.5,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--capture-dir", type=Path)
    parser.add_argument("--da3-dir", type=Path, default=DEFAULT_DA3_DIR)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    parser.add_argument("--window-id", default="window_016")
    parser.add_argument("--seed", type=int, default=4416)
    parser.add_argument("--glb-conf-thresh", type=float, default=1.05)
    parser.add_argument("--glb-conf-percentile", type=float, default=40.0)
    parser.add_argument("--glb-ensure-percentile", type=float, default=90.0)
    parser.add_argument("--glb-num-max-points", type=int, default=1_000_000)
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--npz-sample-ratio", type=float, default=0.015)
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_continuity_quarantine_counterfactual_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_continuity_quarantine_counterfactual_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    strict = load_strict_module()
    dataset = args.dataset_dir
    capture = args.capture_dir or dataset / "capture_seq_k35_strict"
    photo_bundle = read_json(capture / "photo_bundle.json")
    depth_index = read_json(args.da3_dir / "depth_index.json")
    frames = sorted(
        [
            row
            for row in depth_index.get("frames", [])
            if str(row.get("windowID")) == args.window_id
        ],
        key=lambda row: int(row.get("windowSlot", 0)),
    )
    if not frames:
        raise KeyError(f"{args.window_id} not found in {args.da3_dir}/depth_index.json")

    slots = [
        strict.load_slot(frame, capture_dir=capture, da3_dir=args.da3_dir)
        for frame in frames
    ]
    frame_ids = [slot["frame_id"] for slot in slots]
    continuity_rows = continuity_for_frame_ids(photo_bundle, frame_ids)
    high_risk_ids = [
        row["toFrameID"]
        for row in continuity_rows
        if row["highRisk"] and row["toFrameID"] in frame_ids
    ]
    first_break_id = high_risk_ids[0] if high_risk_ids else None
    first_break_slot = frame_ids.index(first_break_id) if first_break_id in frame_ids else None

    variants = build_variants(frame_ids, high_risk_ids, first_break_slot)
    variant_reports = []
    for variant_index, variant in enumerate(variants):
        selected_indices = [frame_ids.index(frame_id) for frame_id in variant["frame_ids"]]
        group = strict.build_group(slots, selected_indices)
        glb_export = strict.export_glb_style_group(
            group,
            conf_thresh=args.glb_conf_thresh,
            conf_percentile=args.glb_conf_percentile,
            ensure_percentile=args.glb_ensure_percentile,
            num_max_points=args.glb_num_max_points,
            seed=args.seed + variant_index,
        )
        npz_export = strict.export_npz_streaming_style_group(
            group,
            conf_threshold_coef=args.npz_conf_threshold_coef,
            sample_ratio=args.npz_sample_ratio,
            seed=args.seed + 1000 + variant_index,
        )
        variant_reports.append(
            {
                **variant,
                "selected_slots": selected_indices,
                "frame_count": len(selected_indices),
                "pose": pose_metrics(group["camera_centers"]),
                "glb_style": summarize_metrics(strict.metrics_for_group(group, glb_export), glb_export),
                "npz_streaming_style": summarize_metrics(strict.metrics_for_group(group, npz_export), npz_export),
            }
        )

    summary = summarize_variants(variant_reports)
    return {
        "schema_version": "aether_da3_continuity_quarantine_counterfactual_audit_v1",
        "date": args.date,
        "decision": {
            "status": summary["status"],
            "goal_complete": False,
            "conclusion": summary["conclusion"],
            "boundary": (
                "This audit removes frames only at point-generation time from fixed DA3 outputs. "
                "It proves a downstream inclusion effect, not the final result of re-running DA3 "
                "with a different K35 context."
            ),
            "next_best_action": (
                "If the counterfactual reduces thickness, run a true Dart-window simulation that "
                "splits or quarantines the high-risk capture segment, then re-run the current "
                "DA3BASE_476x742_N35 CoreML path on that altered window plan."
            ),
        },
        "inputs": {
            "dataset_dir": str(dataset),
            "capture_dir": str(capture),
            "da3_dir": str(args.da3_dir),
            "window_id": args.window_id,
            "frame_source": "depth_index official-save downstream",
        },
        "thresholds": THRESHOLDS,
        "official_downstream_frame_ids": frame_ids,
        "continuity_rows": continuity_rows,
        "high_risk_frame_ids": high_risk_ids,
        "variants": variant_reports,
        "summary": summary,
        "plain_language": plain_language(summary, high_risk_ids),
    }


def build_variants(
    frame_ids: list[str],
    high_risk_ids: list[str],
    first_break_slot: int | None,
) -> list[dict[str, Any]]:
    variants = [
        {
            "id": "official_save_all_17",
            "description": "Official save-frame downstream as currently used.",
            "frame_ids": frame_ids,
            "removed_frame_ids": [],
        }
    ]
    if first_break_slot is not None:
        first_break_id = frame_ids[first_break_slot]
        variants.append(
            {
                "id": "drop_first_break_target",
                "description": f"Drop only the first high-risk continuity target ({first_break_id}).",
                "frame_ids": [fid for fid in frame_ids if fid != first_break_id],
                "removed_frame_ids": [first_break_id],
            }
        )
        variants.append(
            {
                "id": "prefix_before_first_break",
                "description": "Keep only the official downstream prefix before the first continuity break.",
                "frame_ids": frame_ids[:first_break_slot],
                "removed_frame_ids": frame_ids[first_break_slot:],
            }
        )
        variants.append(
            {
                "id": "segment_from_first_break",
                "description": "Keep only the segment after the first continuity break.",
                "frame_ids": frame_ids[first_break_slot:],
                "removed_frame_ids": frame_ids[:first_break_slot],
            }
        )
    if high_risk_ids:
        risk_set = set(high_risk_ids)
        variants.append(
            {
                "id": "drop_all_high_risk_targets",
                "description": "Drop every frame that violates the current Dart continuity warning thresholds.",
                "frame_ids": [fid for fid in frame_ids if fid not in risk_set],
                "removed_frame_ids": high_risk_ids,
            }
        )
    return [variant for variant in variants if variant["frame_ids"]]


def continuity_for_frame_ids(
    photo_bundle: dict[str, Any],
    selected_frame_ids: list[str],
) -> list[dict[str, Any]]:
    frames = photo_bundle.get("frames", [])
    by_id = {str(frame.get("id")): (index, frame) for index, frame in enumerate(frames)}
    rows = []
    selected = set(selected_frame_ids)
    for frame_id in selected_frame_ids:
        if frame_id not in by_id:
            continue
        index, frame = by_id[frame_id]
        if index <= 0:
            continue
        prev = frames[index - 1]
        row = continuity_step(prev, frame, index)
        row["inSelectedOfficialDownstream"] = frame_id in selected
        rows.append(row)
    return rows


def continuity_step(previous: dict[str, Any], current: dict[str, Any], current_index: int) -> dict[str, Any]:
    timestamp_delta = nullable_delta(current.get("timestamp"), previous.get("timestamp"))
    translation = camera_translation(previous, current)
    azimuth_delta = angle_abs_delta(as_float(previous.get("azimuth")), as_float(current.get("azimuth")))
    elevation_delta = nullable_abs_delta(
        as_float(previous.get("elevation")),
        as_float(current.get("elevation")),
    )
    quality = quality_score(current)
    high_risk = (
        (timestamp_delta is not None and timestamp_delta > THRESHOLDS["timestampDeltaSecondsWarningGt"])
        or (translation is not None and translation > THRESHOLDS["translationStepMWarningGt"])
        or (azimuth_delta is not None and azimuth_delta > THRESHOLDS["azimuthDeltaRadWarningGt"])
        or (elevation_delta is not None and elevation_delta > THRESHOLDS["elevationDeltaRadWarningGt"])
        or quality < THRESHOLDS["qualityScoreWarningLt"]
    )
    return {
        "fromFrameID": previous.get("id"),
        "toFrameID": current.get("id"),
        "toManifestIndex": current_index,
        "timestampDeltaSeconds": timestamp_delta,
        "translationStepM": translation,
        "azimuthDeltaRad": azimuth_delta,
        "elevationDeltaRad": elevation_delta,
        "toKWindowWeight": quality,
        "highRisk": high_risk,
        "violations": continuity_violations(
            timestamp_delta=timestamp_delta,
            translation=translation,
            azimuth_delta=azimuth_delta,
            elevation_delta=elevation_delta,
            quality=quality,
        ),
    }


def summarize_metrics(metrics: dict[str, Any], exported: dict[str, Any]) -> dict[str, Any]:
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
        "depth_p95": as_float(get_path(metrics, "depth.p95")),
        "confidence_median": as_float(get_path(metrics, "confidence.median")),
    }


def summarize_variants(variants: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {variant["id"]: variant for variant in variants}
    base = by_id["official_save_all_17"]
    rows = []
    for variant in variants:
        rows.append(
            {
                "id": variant["id"],
                "frame_count": variant["frame_count"],
                "removed_frame_ids": variant["removed_frame_ids"],
                "npz_minor_ratio_vs_official_all": safe_ratio(
                    variant["npz_streaming_style"]["pca_minor_extent"],
                    base["npz_streaming_style"]["pca_minor_extent"],
                ),
                "npz_bbox_ratio_vs_official_all": safe_ratio(
                    variant["npz_streaming_style"]["bbox_diag_p01_p99"],
                    base["npz_streaming_style"]["bbox_diag_p01_p99"],
                ),
                "glb_minor_ratio_vs_official_all": safe_ratio(
                    variant["glb_style"]["pca_minor_extent"],
                    base["glb_style"]["pca_minor_extent"],
                ),
                "pose_diag_ratio_vs_official_all": safe_ratio(
                    variant["pose"]["camera_center_diag"],
                    base["pose"]["camera_center_diag"],
                ),
            }
        )
    first_drop = by_id.get("drop_first_break_target")
    risk_drop = by_id.get("drop_all_high_risk_targets")
    first_drop_minor = (
        safe_ratio(
            first_drop["npz_streaming_style"]["pca_minor_extent"],
            base["npz_streaming_style"]["pca_minor_extent"],
        )
        if first_drop
        else None
    )
    risk_drop_minor = (
        safe_ratio(
            risk_drop["npz_streaming_style"]["pca_minor_extent"],
            base["npz_streaming_style"]["pca_minor_extent"],
        )
        if risk_drop
        else None
    )
    if risk_drop_minor is not None and risk_drop_minor < 0.85:
        status = "counterfactual_high_risk_quarantine_reduces_thickness"
    elif first_drop_minor is not None and first_drop_minor < 0.90:
        status = "counterfactual_first_break_drop_reduces_thickness"
    else:
        status = "counterfactual_quarantine_effect_weak_or_inconclusive"
    return {
        "status": status,
        "official_all_npz_minor": base["npz_streaming_style"]["pca_minor_extent"],
        "drop_first_break_npz_minor_ratio": first_drop_minor,
        "drop_all_high_risk_npz_minor_ratio": risk_drop_minor,
        "variant_ratios": rows,
        "conclusion": conclusion_for_status(status, first_drop_minor, risk_drop_minor),
    }


def conclusion_for_status(status: str, first_drop_minor: float | None, risk_drop_minor: float | None) -> str:
    if status == "counterfactual_high_risk_quarantine_reduces_thickness":
        return (
            "Removing all high-risk continuity targets from fixed DA3 outputs reduces npz-style minor thickness, "
            f"ratio={risk_drop_minor:.3f}. This supports a Dart-side continuity quarantine experiment."
        )
    if status == "counterfactual_first_break_drop_reduces_thickness":
        return (
            "Dropping the first continuity-break target reduces npz-style minor thickness, "
            f"ratio={first_drop_minor:.3f}. This supports a focused cap-1396 rerun experiment."
        )
    return (
        "Removing high-risk continuity targets from fixed outputs did not clearly reduce thickness. "
        "A true re-run may still be needed because DA3 predictions depend on full K-window context."
    )


def pose_metrics(camera_centers: np.ndarray) -> dict[str, Any]:
    if camera_centers.size == 0:
        return {"camera_center_diag": None}
    lo = np.min(camera_centers, axis=0)
    hi = np.max(camera_centers, axis=0)
    return {
        "camera_center_diag": float(np.linalg.norm(hi - lo)),
        "camera_center_min": [float(v) for v in lo],
        "camera_center_max": [float(v) for v in hi],
    }


def plain_language(summary: dict[str, Any], high_risk_ids: list[str]) -> list[str]:
    lines = [
        f"当前 official-save downstream 中 high-risk targets 是：{', '.join(high_risk_ids) if high_risk_ids else 'none'}。",
        "这个审计没有重跑 DA3，只是在现有预测结果上重新选择哪些帧参与官方风格点云生成。",
    ]
    first = summary.get("drop_first_break_npz_minor_ratio")
    all_risk = summary.get("drop_all_high_risk_npz_minor_ratio")
    if first is not None:
        lines.append(f"只去掉第一个断点帧后，npz minor 相对 official-all 的比例是 {first:.3f}。")
    if all_risk is not None:
        lines.append(f"去掉所有 high-risk targets 后，npz minor 相对 official-all 的比例是 {all_risk:.3f}。")
    lines.append(summary["conclusion"])
    lines.append("如果这个信号强，下一步才值得做真正的 Dart window 分段/补帧重跑，而不是改官方复刻分支。")
    return lines


def continuity_violations(
    *,
    timestamp_delta: float | None,
    translation: float | None,
    azimuth_delta: float | None,
    elevation_delta: float | None,
    quality: float,
) -> list[dict[str, Any]]:
    checks = [
        ("timestampDeltaSeconds", ">", THRESHOLDS["timestampDeltaSecondsWarningGt"], timestamp_delta),
        ("translationStepM", ">", THRESHOLDS["translationStepMWarningGt"], translation),
        ("azimuthDeltaRad", ">", THRESHOLDS["azimuthDeltaRadWarningGt"], azimuth_delta),
        ("elevationDeltaRad", ">", THRESHOLDS["elevationDeltaRadWarningGt"], elevation_delta),
        ("toKWindowWeight", "<", THRESHOLDS["qualityScoreWarningLt"], quality),
    ]
    out = []
    for metric, op, threshold, value in checks:
        if value is None:
            continue
        violated = value > threshold if op == ">" else value < threshold
        if violated:
            out.append({"metric": metric, "op": op, "threshold": threshold, "value": float(value)})
    return out


def quality_score(frame: dict[str, Any]) -> float:
    quality = frame.get("quality")
    if not isinstance(quality, dict):
        return 0.0
    direct = as_float(quality.get("kWindowWeight"))
    if direct and direct > 0:
        return direct
    downstream = quality.get("downstreamWeights")
    if isinstance(downstream, dict):
        nested = as_float(downstream.get("kWindow"))
        if nested and nested > 0:
            return nested
    return as_float(quality.get("score")) or 0.0


def camera_translation(previous: dict[str, Any], current: dict[str, Any]) -> float | None:
    a = camera_center(previous)
    b = camera_center(current)
    if a is None or b is None:
        return None
    return math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))


def camera_center(frame: dict[str, Any]) -> list[float] | None:
    values = frame.get("cameraTransform")
    if not isinstance(values, list) or len(values) != 16:
        return None
    try:
        return [float(values[12]), float(values[13]), float(values[14])]
    except (TypeError, ValueError):
        return None


def nullable_delta(value: Any, previous: Any) -> float | None:
    current = as_float(value)
    prev = as_float(previous)
    if current is None or prev is None:
        return None
    return current - prev


def nullable_abs_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return abs(a - b)


def angle_abs_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    delta = abs(a - b)
    while delta > math.pi:
        delta = abs(delta - math.pi * 2.0)
    return delta


def safe_ratio(value: Any, base: Any) -> float | None:
    v = as_float(value)
    b = as_float(base)
    if v is None or b is None or abs(b) < 1e-12:
        return None
    return v / b


def get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_strict_module() -> Any:
    path = Path(__file__).with_name("strict_k35_window_official_filter_micro_audit.py")
    spec = importlib.util.spec_from_file_location("strict_k35_window_official_filter_micro_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "high_risk_frame_ids": report["high_risk_frame_ids"],
        "summary": report["summary"],
    }


def fmt(value: Any) -> str:
    parsed = as_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.3f}"


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# DA3 continuity quarantine counterfactual audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- goal complete: `{report['decision']['goal_complete']}`",
        "",
        report["decision"]["conclusion"],
        "",
        report["decision"]["boundary"],
        "",
        report["decision"]["next_best_action"],
        "",
        "## 大白话",
        "",
    ]
    for item in report["plain_language"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## High-Risk Steps",
            "",
            "| from | to | dt | trans | az | el | kWeight | violations |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in report["continuity_rows"]:
        if not row["highRisk"]:
            continue
        violations = ", ".join(item["metric"] for item in row["violations"])
        lines.append(
            "| `{from_id}` | `{to_id}` | {dt} | {trans} | {az} | {el} | {q} | {violations} |".format(
                from_id=row.get("fromFrameID"),
                to_id=row.get("toFrameID"),
                dt=fmt(row.get("timestampDeltaSeconds")),
                trans=fmt(row.get("translationStepM")),
                az=fmt(row.get("azimuthDeltaRad")),
                el=fmt(row.get("elevationDeltaRad")),
                q=fmt(row.get("toKWindowWeight")),
                violations=violations,
            )
        )
    lines.extend(
        [
            "",
            "## Variants",
            "",
            "| variant | frames | removed | pose diag | npz minor | npz minor/all | npz bbox/all | glb minor/all |",
            "|---|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for variant in report["variants"]:
        ratio = next(
            item
            for item in report["summary"]["variant_ratios"]
            if item["id"] == variant["id"]
        )
        lines.append(
            "| `{id}` | {frames} | {removed} | {pose} | {minor} | {minor_ratio} | {bbox_ratio} | {glb_ratio} |".format(
                id=variant["id"],
                frames=variant["frame_count"],
                removed=", ".join(f"`{fid}`" for fid in variant["removed_frame_ids"]) or "none",
                pose=fmt(variant["pose"].get("camera_center_diag")),
                minor=fmt(variant["npz_streaming_style"].get("pca_minor_extent")),
                minor_ratio=fmt(ratio.get("npz_minor_ratio_vs_official_all")),
                bbox_ratio=fmt(ratio.get("npz_bbox_ratio_vs_official_all")),
                glb_ratio=fmt(ratio.get("glb_minor_ratio_vs_official_all")),
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
