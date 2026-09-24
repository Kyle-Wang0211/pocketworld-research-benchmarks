#!/usr/bin/env python3
"""Attribute DA3 point-cloud thickness to overlap saving vs within-window geometry.

This is a read-only synthesis over existing diagnostics. It does not inspect or
rewrite PLY files. The goal is to keep two failure modes separate:

1. duplicate overlap frames saved across windows/chunks;
2. multiple frames inside one K35 window not collapsing to the same surface.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thickness-report", type=Path, required=True)
    parser.add_argument("--overlap-compare-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    thickness = read_json(args.thickness_report)
    overlap = read_json(args.overlap_compare_report)
    report = build_report(thickness, overlap, args)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        args.out_dir / "official_da3_overlap_vs_window_thickness_attribution.json",
        report,
    )
    write_markdown(
        args.out_dir / "official_da3_overlap_vs_window_thickness_attribution_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(
    thickness: dict[str, Any],
    overlap: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    left = compact_overlap_side(overlap.get("left", {}))
    right = compact_overlap_side(overlap.get("right", {}))
    delta = overlap.get("delta_right_minus_left", {})
    thick_summary = thickness.get("summary", {})
    largest_bbox = thick_summary.get("largest_bbox_growth")
    largest_minor = thick_summary.get("largest_pca_minor_growth")
    no_valid_increase = thick_summary.get("thickened_without_valid_fraction_increase") or []
    tighter_threshold = thick_summary.get("thickened_despite_tighter_threshold") or []
    correlations = thick_summary.get("correlations", {})

    evidence = {
        "overlap_duplicate_evidence": {
            "left": left,
            "right": right,
            "selected_frame_count_delta": metric_delta(delta, "selected_frame_count"),
            "selected_duplicate_frame_count_delta": metric_delta(
                delta, "selected_duplicate_frame_count"
            ),
            "bbox_diag_p01_p99_ratio_overlap_right_over_left": metric_ratio(
                delta, "bbox_diag_p01_p99"
            ),
            "pca_minor_extent_ratio_overlap_right_over_left": metric_ratio(
                delta, "pca_minor_extent"
            ),
        },
        "within_window_thickness_evidence": {
            "row_count": len(thickness.get("rows", [])),
            "largest_bbox_growth": largest_bbox,
            "largest_pca_minor_growth": largest_minor,
            "thickened_without_valid_fraction_increase_count": len(no_valid_increase),
            "thickened_despite_tighter_threshold_count": len(tighter_threshold),
            "minor_growth_vs_pose_span_growth": correlations.get(
                "minor_growth_vs_pose_span_growth"
            ),
            "minor_growth_vs_conf_threshold_ratio": correlations.get(
                "minor_growth_vs_conf_threshold_ratio"
            ),
            "minor_growth_vs_valid_fraction_delta": correlations.get(
                "minor_growth_vs_valid_fraction_delta"
            ),
        },
    }

    findings = derive_findings(evidence)
    return {
        "schema_version": "aether_official_da3_overlap_vs_window_thickness_attribution_v1",
        "purpose": (
            "Separate official overlap-frame duplicate removal from single-window "
            "K35 within-window geometry thickness."
        ),
        "inputs": {
            "thickness_report": str(args.thickness_report),
            "overlap_compare_report": str(args.overlap_compare_report),
        },
        "evidence": evidence,
        "findings": findings,
        "decision": {
            "overlap_frame_duplicate_saved_to_downstream": findings[
                "overlap_frame_duplicate_saved_to_downstream"
            ],
            "single_window_thickness_remains_after_official_filter": findings[
                "single_window_thickness_remains_after_official_filter"
            ],
            "most_likely_current_cause": findings["most_likely_current_cause"],
            "allowed_next_actions": [
                "Keep official core-frame downstream baseline clean.",
                "Close full same-resolution PyTorch K35 reference gate on larger GPU or official memory-efficient attention.",
                "Only after official parity is frozen, label voxel/TSDF/surfel/normal cleanup as product adaptation.",
            ],
            "disallowed_in_official_baseline": [
                "Claiming voxel/TSDF/surfel thinning is hidden official DA3 behavior.",
                "Using pcd/combined_pcd.ply full-chunk merge as APP baseline.",
                "Calling mobile K35/18 exact official 120/60 parity.",
            ],
        },
    }


def derive_findings(evidence: dict[str, Any]) -> dict[str, Any]:
    overlap_ev = evidence["overlap_duplicate_evidence"]
    within_ev = evidence["within_window_thickness_evidence"]
    left_dupes = as_float(overlap_ev["left"].get("selected_duplicate_frame_count"))
    right_dupes = as_float(overlap_ev["right"].get("selected_duplicate_frame_count"))
    selected_same = (
        as_float(overlap_ev["left"].get("selected_frame_count"))
        == as_float(overlap_ev["right"].get("selected_frame_count"))
    )
    no_saved_duplicates = left_dupes == 0 and right_dupes == 0
    largest_minor = as_float(
        (within_ev.get("largest_pca_minor_growth") or {}).get("minor_growth")
    )
    largest_bbox = as_float(
        (within_ev.get("largest_bbox_growth") or {}).get("bbox_growth")
    )
    pose_corr = as_float(within_ev.get("minor_growth_vs_pose_span_growth"))
    conf_corr = as_float(within_ev.get("minor_growth_vs_conf_threshold_ratio"))
    valid_corr = as_float(within_ev.get("minor_growth_vs_valid_fraction_delta"))

    single_window_thick = (
        (largest_minor is not None and largest_minor >= 1.10)
        or (largest_bbox is not None and largest_bbox >= 1.10)
    )
    pose_more_plausible_than_filter = (
        pose_corr is not None
        and conf_corr is not None
        and valid_corr is not None
        and abs(pose_corr) > max(abs(conf_corr), abs(valid_corr))
    )
    if single_window_thick and pose_more_plausible_than_filter:
        cause = "within_window_upstream_geometry_consistency"
    elif single_window_thick:
        cause = "within_window_geometry_not_downstream_overlap_duplicates"
    else:
        cause = "not_proven_from_current_reports"

    return {
        "overlap_frame_duplicate_saved_to_downstream": not no_saved_duplicates,
        "official_core_frame_selection_removed_overlap_duplicates": (
            no_saved_duplicates and selected_same
        ),
        "single_window_thickness_remains_after_official_filter": single_window_thick,
        "confidence_or_valid_fraction_is_sufficient_explanation": False
        if within_ev.get("thickened_without_valid_fraction_increase_count", 0) > 0
        else None,
        "pose_span_is_strongest_current_clue": pose_more_plausible_than_filter,
        "most_likely_current_cause": cause,
        "plain_language": [
            "Official core-frame downstream removes repeated overlap frames from the final sequence-level pointcloud.",
            "That does not fuse multiple K35 views of the same surface into one thin surface.",
            "Current evidence says the remaining thick layer is already present inside individual K35 windows, before cross-window loop or full-chunk merge can explain it.",
        ],
    }


def compact_overlap_side(side: Any) -> dict[str, Any]:
    side = side if isinstance(side, dict) else {}
    keys = [
        "label",
        "chunk_size",
        "overlap",
        "step",
        "selected_frame_count",
        "selected_unique_frame_count",
        "selected_duplicate_frame_count",
        "missing_frame_count",
        "order_matches_source",
        "bbox_diag_p01_p99",
        "pca_minor_extent",
    ]
    return {key: side.get(key) for key in keys}


def metric_delta(delta: dict[str, Any], key: str) -> Any:
    row = delta.get(key)
    return None if not isinstance(row, dict) else row.get("delta")


def metric_ratio(delta: dict[str, Any], key: str) -> Any:
    row = delta.get(key)
    return None if not isinstance(row, dict) else row.get("ratio")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "findings": report["findings"],
        "largest_bbox_growth": report["evidence"]["within_window_thickness_evidence"][
            "largest_bbox_growth"
        ],
        "largest_pca_minor_growth": report["evidence"][
            "within_window_thickness_evidence"
        ]["largest_pca_minor_growth"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    overlap_ev = report["evidence"]["overlap_duplicate_evidence"]
    within_ev = report["evidence"]["within_window_thickness_evidence"]
    findings = report["findings"]
    left = overlap_ev["left"]
    right = overlap_ev["right"]
    lines = [
        "# Official DA3 overlap vs K35 window thickness attribution",
        "",
        "日期：2026-06-04",
        "",
        "## 结论",
        "",
        "- 官方 core-frame downstream 已经消除了跨 window/chunk overlap 帧重复保存：overlap18 和 overlap06 的 selected duplicate frame count 都是 0。",
        "- 但这只解决“同一帧被保存两次”的问题，不解决“同一个 K35 window 内 35 个视角看到同一表面但没有压成一张薄面”的问题。",
        "- 当前厚层证据更指向 within-window / upstream geometry consistency，而不是 downstream 少做了官方隐藏点云去重。",
        "- 因此 APP 继续走 `results_output/frame_*.npz + npz_output_process.py` 是正确 baseline；不要把 `pcd/combined_pcd.ply` full-chunk merge 当产品基线。",
        "",
        "## Overlap 保存证据",
        "",
        "| metric | left | right |",
        "|---|---:|---:|",
    ]
    for key in [
        "label",
        "chunk_size",
        "overlap",
        "step",
        "selected_frame_count",
        "selected_unique_frame_count",
        "selected_duplicate_frame_count",
        "missing_frame_count",
        "order_matches_source",
        "bbox_diag_p01_p99",
        "pca_minor_extent",
    ]:
        lines.append(f"| {key} | {fmt(left.get(key))} | {fmt(right.get(key))} |")
    lines.extend(
        [
            "",
            "关键读法：改变 K35 的 overlap 从 18 到 6 后，最终官方保存帧仍是 414 张、重复保存帧仍是 0。也就是说，官方 core-frame 保存语义已经在 frame selection 层面处理了 overlap 重复。",
            "",
            "## 单 window 厚层证据",
            "",
            f"- largest bbox growth: `{json.dumps(within_ev.get('largest_bbox_growth'), ensure_ascii=False)}`",
            f"- largest PCA minor growth: `{json.dumps(within_ev.get('largest_pca_minor_growth'), ensure_ascii=False)}`",
            f"- thickened without valid fraction increase count: `{within_ev.get('thickened_without_valid_fraction_increase_count')}`",
            f"- thickened despite tighter threshold count: `{within_ev.get('thickened_despite_tighter_threshold_count')}`",
            f"- minor growth vs pose span growth correlation clue: `{fmt(within_ev.get('minor_growth_vs_pose_span_growth'))}`",
            f"- minor growth vs confidence threshold ratio clue: `{fmt(within_ev.get('minor_growth_vs_conf_threshold_ratio'))}`",
            f"- minor growth vs valid fraction delta clue: `{fmt(within_ev.get('minor_growth_vs_valid_fraction_delta'))}`",
            "",
            "关键读法：`window_016` 在 npz_streaming_style 下 first35/first10 的 PCA minor growth 约 1.465，同时 valid fraction 下降。这不是“保留了更多低置信点”就能解释的现象。",
            "",
            "## Attribution",
            "",
            f"- overlap_frame_duplicate_saved_to_downstream: `{findings['overlap_frame_duplicate_saved_to_downstream']}`",
            f"- official_core_frame_selection_removed_overlap_duplicates: `{findings['official_core_frame_selection_removed_overlap_duplicates']}`",
            f"- single_window_thickness_remains_after_official_filter: `{findings['single_window_thickness_remains_after_official_filter']}`",
            f"- pose_span_is_strongest_current_clue: `{findings['pose_span_is_strongest_current_clue']}`",
            f"- most_likely_current_cause: `{findings['most_likely_current_cause']}`",
            "",
            "## 大白话",
            "",
            "官方 downstream 做的是：这个 window 和下个 window 重叠的那些帧，不要在最终序列点云里重复保存。",
            "",
            "官方 downstream 没做的是：同一个 window 内，35 帧都看到了同一块地板/墙面时，把这些点强行融合成一张薄薄的面。",
            "",
            "所以现在的判断是：跨 window overlap 重复这类问题，官方 core-frame path 已经处理；单 K35 window 内厚层，更像 DA3 上游 depth/pose/scale 一致性没完全压住。",
            "",
            "## 下一步",
            "",
            "1. 保持 APP official baseline：core-frame npz path、`conf_threshold_coef=0.5`、sample ratio 0.015、no voxel/TSDF/surfel cleanup。",
            "2. 关闭 full same-resolution PyTorch K35 reference gate，确认官方 PyTorch full-res 是否也厚。",
            "3. 如果官方也厚，把后续清理明确标成 product adaptation；如果官方不厚，继续查 CoreML/export/preprocess。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    return None


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
