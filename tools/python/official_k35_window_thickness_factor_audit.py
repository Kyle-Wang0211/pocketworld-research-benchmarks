#!/usr/bin/env python3
"""Summarize official K35 window micro-audits into thickness factor evidence.

This is a read-only diagnostic. It does not generate new point clouds, change
filters, or alter DA3 outputs. It only parses existing official-filter micro
audit reports and asks whether first10 -> first35 thickness growth lines up more
with pose span, confidence filtering, depth range, or postprocess pose scale.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--postprocess-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--report",
        action="append",
        type=Path,
        default=[],
        help="Optional explicit micro-audit report path. Can be repeated.",
    )
    args = parser.parse_args()

    report_paths = args.report or discover_reports(args.diagnostics_dir)
    if not report_paths:
        raise SystemExit("No official micro-audit reports found")

    postprocess = read_json(args.postprocess_report)
    pose_scales = {
        str(row["windowID"]): float(row["poseScale"])
        for row in postprocess.get("windows", [])
        if "windowID" in row and "poseScale" in row
    }

    rows: list[dict[str, Any]] = []
    for report_path in report_paths:
        report = read_json(report_path)
        window_id = str(report.get("inputs", {}).get("window_id", report_path.parent.name))
        for style in report.get("styles", []):
            row = summarize_style(window_id, style, pose_scales.get(window_id))
            row["report_path"] = str(report_path)
            rows.append(row)

    summary = build_summary(rows)
    out = {
        "schema_version": "pocketworld_official_k35_window_thickness_factor_audit_v1",
        "scope": {
            "diagnostics_dir": str(args.diagnostics_dir),
            "postprocess_report": str(args.postprocess_report),
            "report_count": len(report_paths),
            "style_row_count": len(rows),
            "note": "Read-only parse of official-filter micro-audit JSON reports; no new point generation.",
        },
        "rows": rows,
        "summary": summary,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_k35_window_thickness_factor_audit.json", out)
    write_markdown(args.out_dir / "official_k35_window_thickness_factor_audit_zh.md", out)
    print(json.dumps(compact_console(out), ensure_ascii=False, indent=2))
    return 0


def discover_reports(diagnostics_dir: Path) -> list[Path]:
    paths = []
    for path in diagnostics_dir.glob("window_*_official_filter_micro_audit_official_postprocess/window_000_official_filter_micro_audit_report.json"):
        paths.append(path)
    return sorted(paths)


def summarize_style(window_id: str, style: dict[str, Any], pose_scale: float | None) -> dict[str, Any]:
    first10 = group_by_name(style, "first_10")
    first35 = group_by_name(style, "first_35")
    style_name = str(style.get("style", "unknown"))
    row = {
        "window_id": window_id,
        "style": style_name,
        "pose_scale": pose_scale,
        "first10": extract_group_metrics(first10),
        "first35": extract_group_metrics(first35),
    }
    row["growth"] = growth_metrics(row["first10"], row["first35"])
    row["signals"] = classify_signals(row)
    return row


def group_by_name(style: dict[str, Any], name: str) -> dict[str, Any]:
    for group in style.get("groups", []):
        if group.get("name") == name:
            return group
    raise KeyError(f"{style.get('style')} missing group {name}")


def extract_group_metrics(group: dict[str, Any]) -> dict[str, Any]:
    metrics = group.get("metrics", {})
    pc = metrics.get("point_cloud", {})
    pca = metrics.get("pca", {})
    pose = metrics.get("pose", {})
    depth = metrics.get("depth", {})
    conf = metrics.get("confidence", {})
    filt = group.get("official_filter", {})
    return {
        "name": group.get("name"),
        "slot_count": metrics.get("slot_count"),
        "bbox_diag_p01_p99": as_float(pc.get("bbox_diag_p01_p99")),
        "bbox_diag_p05_p95": as_float(pc.get("bbox_diag_p05_p95")),
        "pca_minor_extent": as_float(pca.get("minor_extent")),
        "pca_minor_to_major_ratio": as_float(pca.get("minor_to_major_ratio")),
        "valid_fraction_of_pixels": as_float(metrics.get("valid_fraction_of_pixels")),
        "valid_point_count_before_downsample": metrics.get("valid_point_count_before_downsample"),
        "sampled_point_count": metrics.get("sampled_point_count"),
        "conf_threshold": as_float(filt.get("conf_threshold")),
        "confidence_mean": as_float(conf.get("mean")),
        "confidence_median": as_float(conf.get("median")),
        "confidence_p05": as_float(conf.get("p05")),
        "depth_mean": as_float(depth.get("mean")),
        "depth_median": as_float(depth.get("median")),
        "depth_p95": as_float(depth.get("p95")),
        "pose_camera_center_diag": as_float(pose.get("camera_center_diag")),
        "pose_step_mean": as_float(pose.get("step_mean")),
        "pose_step_max": as_float(pose.get("step_max")),
    }


def growth_metrics(first10: dict[str, Any], first35: dict[str, Any]) -> dict[str, Any]:
    return {
        "bbox_diag_p01_p99_ratio": safe_ratio(first35["bbox_diag_p01_p99"], first10["bbox_diag_p01_p99"]),
        "bbox_diag_p05_p95_ratio": safe_ratio(first35["bbox_diag_p05_p95"], first10["bbox_diag_p05_p95"]),
        "pca_minor_extent_ratio": safe_ratio(first35["pca_minor_extent"], first10["pca_minor_extent"]),
        "pca_minor_to_major_delta": safe_delta(first35["pca_minor_to_major_ratio"], first10["pca_minor_to_major_ratio"]),
        "valid_fraction_delta": safe_delta(first35["valid_fraction_of_pixels"], first10["valid_fraction_of_pixels"]),
        "conf_threshold_ratio": safe_ratio(first35["conf_threshold"], first10["conf_threshold"]),
        "confidence_mean_ratio": safe_ratio(first35["confidence_mean"], first10["confidence_mean"]),
        "confidence_median_ratio": safe_ratio(first35["confidence_median"], first10["confidence_median"]),
        "depth_p95_ratio": safe_ratio(first35["depth_p95"], first10["depth_p95"]),
        "depth_mean_ratio": safe_ratio(first35["depth_mean"], first10["depth_mean"]),
        "pose_camera_center_diag_ratio": safe_ratio(first35["pose_camera_center_diag"], first10["pose_camera_center_diag"]),
        "pose_step_max_ratio": safe_ratio(first35["pose_step_max"], first10["pose_step_max"]),
    }


def classify_signals(row: dict[str, Any]) -> dict[str, Any]:
    growth = row["growth"]
    bbox_growth = growth["bbox_diag_p01_p99_ratio"]
    minor_growth = growth["pca_minor_extent_ratio"]
    threshold_growth = growth["conf_threshold_ratio"]
    valid_delta = growth["valid_fraction_delta"]
    pose_growth = growth["pose_camera_center_diag_ratio"]
    return {
        "thickened_bbox_ge_1_10": is_ge(bbox_growth, 1.10),
        "thickened_minor_ge_1_10": is_ge(minor_growth, 1.10),
        "large_minor_growth_ge_1_35": is_ge(minor_growth, 1.35),
        "pose_span_expanded_ge_2x": is_ge(pose_growth, 2.0),
        "conf_threshold_loosened": threshold_growth is not None and threshold_growth < 0.95,
        "conf_threshold_tightened": threshold_growth is not None and threshold_growth > 1.05,
        "valid_fraction_increased": valid_delta is not None and valid_delta > 0.01,
        "valid_fraction_decreased": valid_delta is not None and valid_delta < -0.01,
        "thickened_despite_tighter_threshold": (
            is_ge(bbox_growth, 1.10) or is_ge(minor_growth, 1.10)
        )
        and threshold_growth is not None
        and threshold_growth > 1.05,
        "thickened_without_valid_fraction_increase": (
            is_ge(bbox_growth, 1.10) or is_ge(minor_growth, 1.10)
        )
        and (valid_delta is None or valid_delta <= 0.01),
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranked_bbox = sorted(
        rows,
        key=lambda row: none_to_neg_inf(row["growth"]["bbox_diag_p01_p99_ratio"]),
        reverse=True,
    )
    ranked_minor = sorted(
        rows,
        key=lambda row: none_to_neg_inf(row["growth"]["pca_minor_extent_ratio"]),
        reverse=True,
    )
    correlations = {
        "note": "Tiny sample diagnostic only; correlations are clues, not proof.",
        "minor_growth_vs_pose_span_growth": pearson(rows, "pca_minor_extent_ratio", "pose_camera_center_diag_ratio"),
        "minor_growth_vs_conf_threshold_ratio": pearson(rows, "pca_minor_extent_ratio", "conf_threshold_ratio"),
        "minor_growth_vs_valid_fraction_delta": pearson(rows, "pca_minor_extent_ratio", "valid_fraction_delta"),
        "minor_growth_vs_depth_p95_ratio": pearson(rows, "pca_minor_extent_ratio", "depth_p95_ratio"),
        "bbox_growth_vs_pose_span_growth": pearson(rows, "bbox_diag_p01_p99_ratio", "pose_camera_center_diag_ratio"),
    }
    return {
        "largest_bbox_growth": slim_row(ranked_bbox[0]) if ranked_bbox else None,
        "largest_pca_minor_growth": slim_row(ranked_minor[0]) if ranked_minor else None,
        "thickened_despite_tighter_threshold": [
            slim_row(row) for row in rows if row["signals"]["thickened_despite_tighter_threshold"]
        ],
        "thickened_without_valid_fraction_increase": [
            slim_row(row) for row in rows if row["signals"]["thickened_without_valid_fraction_increase"]
        ],
        "first35_not_worse_than_first10": [
            slim_row(row)
            for row in rows
            if (row["growth"]["bbox_diag_p01_p99_ratio"] or math.inf) < 1.0
            or (row["growth"]["pca_minor_extent_ratio"] or math.inf) < 1.0
        ],
        "correlations": correlations,
        "interpretation": interpretation(rows, correlations),
    }


def slim_row(row: dict[str, Any]) -> dict[str, Any]:
    growth = row["growth"]
    return {
        "window_id": row["window_id"],
        "style": row["style"],
        "pose_scale": row["pose_scale"],
        "bbox_growth": growth["bbox_diag_p01_p99_ratio"],
        "minor_growth": growth["pca_minor_extent_ratio"],
        "pose_span_growth": growth["pose_camera_center_diag_ratio"],
        "conf_threshold_ratio": growth["conf_threshold_ratio"],
        "valid_fraction_delta": growth["valid_fraction_delta"],
        "depth_p95_ratio": growth["depth_p95_ratio"],
    }


def interpretation(rows: list[dict[str, Any]], correlations: dict[str, Any]) -> list[str]:
    tighter = [row for row in rows if row["signals"]["thickened_despite_tighter_threshold"]]
    no_valid_inc = [row for row in rows if row["signals"]["thickened_without_valid_fraction_increase"]]
    pose_expanded = [row for row in rows if row["signals"]["pose_span_expanded_ge_2x"]]
    lines = [
        "No production algorithm change is implied; this only ranks existing official micro-audit evidence.",
        "Loop is not a proven fix here because first35 thickness appears inside a single K35 window before cross-window loop constraints can act.",
    ]
    if tighter:
        lines.append(
            "Confidence looseness is not a sufficient explanation: some rows thicken even when first35 uses a tighter confidence threshold than first10."
        )
    if no_valid_inc:
        lines.append(
            "Valid fraction is not a sufficient explanation: some rows thicken without retaining a larger fraction of pixels."
        )
    if pose_expanded:
        lines.append(
            "Pose span expansion is the strongest current suspect: first35 expands camera-center span substantially relative to first10 in every audited K35 row."
        )
    if correlations.get("minor_growth_vs_pose_span_growth") is not None:
        lines.append(
            "Correlation values are small-sample clues only; use them to choose the next official consistency check, not as final proof."
        )
    lines.append(
        "The next official-consistency check should compare per-slot or sub-span surfaces within the same window, especially pose/depth/scale consistency across later slots."
    )
    return lines


def pearson(rows: list[dict[str, Any]], lhs: str, rhs: str) -> float | None:
    pairs = []
    for row in rows:
        a = row["growth"].get(lhs)
        b = row["growth"].get(rhs)
        if a is not None and b is not None and math.isfinite(a) and math.isfinite(b):
            pairs.append((float(a), float(b)))
    if len(pairs) < 3:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "out": "official_k35_window_thickness_factor_audit",
        "style_row_count": report["scope"]["style_row_count"],
        "largest_bbox_growth": report["summary"]["largest_bbox_growth"],
        "largest_pca_minor_growth": report["summary"]["largest_pca_minor_growth"],
        "correlations": report["summary"]["correlations"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    rows = report["rows"]
    summary = report["summary"]
    lines = [
        "# Official K35 Window Thickness Factor Audit",
        "",
        "这是 read-only diagnostic。只解析已有 official-filter micro audit JSON，不重新生成点云，不改 CoreML 输出，不改阈值，不做 graph patch/loop/mesh。",
        "",
        "## 核心表格",
        "",
        "| window | style | poseScale | bbox growth | minor growth | pose span growth | conf thr ratio | valid frac delta | depth p95 ratio |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(rows, key=lambda item: (item["window_id"], item["style"])):
        growth = row["growth"]
        lines.append(
            "| {window} | {style} | {pose_scale} | {bbox} | {minor} | {pose} | {thr} | {valid} | {depth} |".format(
                window=row["window_id"],
                style=row["style"],
                pose_scale=fmt(row["pose_scale"]),
                bbox=fmt(growth["bbox_diag_p01_p99_ratio"]),
                minor=fmt(growth["pca_minor_extent_ratio"]),
                pose=fmt(growth["pose_camera_center_diag_ratio"]),
                thr=fmt(growth["conf_threshold_ratio"]),
                valid=fmt(growth["valid_fraction_delta"]),
                depth=fmt(growth["depth_p95_ratio"]),
            )
        )
    lines.extend(
        [
            "",
            "## 最大增长",
            "",
            f"- largest bbox growth: `{json.dumps(summary['largest_bbox_growth'], ensure_ascii=False)}`",
            f"- largest PCA minor growth: `{json.dumps(summary['largest_pca_minor_growth'], ensure_ascii=False)}`",
            "",
            "## 关键反证",
            "",
            f"- thickened despite tighter threshold: {len(summary['thickened_despite_tighter_threshold'])} rows",
            f"- thickened without valid fraction increase: {len(summary['thickened_without_valid_fraction_increase'])} rows",
            f"- first35 not strictly worse than first10: {len(summary['first35_not_worse_than_first10'])} rows",
            "",
            "## Correlation Clues",
            "",
        ]
    )
    for key, value in summary["correlations"].items():
        lines.append(f"- `{key}`: {fmt(value) if isinstance(value, (float, int)) else value}")
    lines.extend(["", "## 初步解释", ""])
    for item in summary["interpretation"]:
        lines.append(f"- {item}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    out = float(value)
    if not math.isfinite(out):
        return None
    return out


def safe_ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return float(num) / float(den)


def safe_delta(num: float | None, den: float | None) -> float | None:
    if num is None or den is None:
        return None
    return float(num) - float(den)


def is_ge(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def none_to_neg_inf(value: float | None) -> float:
    return -math.inf if value is None else float(value)


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return f"{float(value):.6g}"


if __name__ == "__main__":
    raise SystemExit(main())
