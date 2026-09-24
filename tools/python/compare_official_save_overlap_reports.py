#!/usr/bin/env python3
"""Compare two official-save sequence point-cloud reports."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-report", type=Path, required=True)
    parser.add_argument("--left-label", default="overlap18")
    parser.add_argument("--right-report", type=Path, required=True)
    parser.add_argument("--right-label", default="overlap06")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    left = read_json(args.left_report)
    right = read_json(args.right_report)
    report = {
        "schema_version": "pocketworld_official_save_overlap_compare_v1",
        "left": compact(args.left_label, left),
        "right": compact(args.right_label, right),
        "delta_right_minus_left": diff(compact(args.left_label, left), compact(args.right_label, right)),
        "inputs": {
            "left_report": str(args.left_report),
            "right_report": str(args.right_report),
        },
    }
    write_json(args.out_dir / "official_save_overlap_compare_report.json", report)
    write_markdown(args.out_dir / "official_save_overlap_compare_report_zh.md", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def compact(label: str, report: dict[str, Any]) -> dict[str, Any]:
    filt = report["official_filter"]
    sel = report["selection"]
    pc = report["metrics"]["point_cloud"]
    pca = report["metrics"]["pca"]
    policy = report.get("windowing", {})
    return {
        "label": label,
        "chunk_size": policy.get("chunkSize"),
        "overlap": policy.get("overlap"),
        "step": policy.get("step"),
        "selected_frame_count": sel.get("selectedFrameCount"),
        "selected_unique_frame_count": sel.get("selectedUniqueFrameCount"),
        "selected_duplicate_frame_count": sel.get("selectedDuplicateFrameCount"),
        "missing_frame_count": len(sel.get("missingFrameIDs") or []),
        "order_matches_source": sel.get("orderMatchesSource"),
        "conf_threshold": filt.get("conf_threshold"),
        "valid_point_count_before_downsample": filt.get("valid_point_count_before_downsample"),
        "valid_fraction_of_pixels": filt.get("valid_fraction_of_pixels"),
        "exported_point_count": filt.get("exported_point_count"),
        "bbox_diag_p01_p99": pc.get("bbox_diag_p01_p99"),
        "bbox_extent_p01_p99": pc.get("bbox_extent_p01_p99"),
        "bbox_diag_p05_p95": pc.get("bbox_diag_p05_p95"),
        "pca_minor_extent": pca.get("minor_extent"),
        "pca_minor_to_major_ratio": pca.get("minor_to_major_ratio"),
        "ply": report["outputs"].get("ply"),
        "views_png": report["outputs"].get("views_png"),
    }


def diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "selected_frame_count",
        "selected_duplicate_frame_count",
        "missing_frame_count",
        "conf_threshold",
        "valid_point_count_before_downsample",
        "valid_fraction_of_pixels",
        "exported_point_count",
        "bbox_diag_p01_p99",
        "bbox_diag_p05_p95",
        "pca_minor_extent",
        "pca_minor_to_major_ratio",
    ]
    out: dict[str, Any] = {}
    for key in keys:
        out[key] = numeric_delta(left.get(key), right.get(key))
    return out


def numeric_delta(left: Any, right: Any) -> dict[str, Any]:
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return {"left": left, "right": right, "delta": None, "ratio": None}
    delta = float(right) - float(left)
    ratio = None if abs(float(left)) <= 1e-12 else float(right) / float(left)
    return {"left": left, "right": right, "delta": delta, "ratio": ratio}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    left = report["left"]
    right = report["right"]
    delta = report["delta_right_minus_left"]
    lines = [
        "# Official Save Overlap Compare",
        "",
        "## 一句话",
        "",
        "这份对比只比较官方保存语义 + 官方 streaming pointcloud filter/sample 下的 overlap 差异；没有清理、Poisson、mesh 或自研融合。",
        "",
        "## 基本检查",
        "",
        "| metric | {left} | {right} |".format(left=left["label"], right=right["label"]),
        "|---|---:|---:|",
    ]
    for key in [
        "chunk_size",
        "overlap",
        "step",
        "selected_frame_count",
        "selected_duplicate_frame_count",
        "missing_frame_count",
        "order_matches_source",
    ]:
        lines.append(f"| {key} | {left.get(key)} | {right.get(key)} |")
    lines.extend(
        [
            "",
            "## 点云指标",
            "",
            "| metric | {left} | {right} | right-left | ratio |".format(
                left=left["label"],
                right=right["label"],
            ),
            "|---|---:|---:|---:|---:|",
        ]
    )
    for key in [
        "conf_threshold",
        "valid_fraction_of_pixels",
        "exported_point_count",
        "bbox_diag_p01_p99",
        "bbox_diag_p05_p95",
        "pca_minor_extent",
        "pca_minor_to_major_ratio",
    ]:
        row = delta[key]
        lines.append(
            "| {key} | {left} | {right} | {d} | {r} |".format(
                key=key,
                left=fmt(row["left"]),
                right=fmt(row["right"]),
                d=fmt(row["delta"]),
                r=fmt(row["ratio"]),
            )
        )
    lines.extend(
        [
            "",
            "## 输出",
            "",
            f"- {left['label']} PLY: `{left['ply']}`",
            f"- {left['label']} views: `{left['views_png']}`",
            f"- {right['label']} PLY: `{right['ply']}`",
            f"- {right['label']} views: `{right['views_png']}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return f"{value:.8g}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
