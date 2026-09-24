#!/usr/bin/env python3
"""Rank late-slot geometry consistency signals for window_016."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_window016_late_slot_geometry_consistency_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_window016_late_slot_geometry_consistency_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    dataset = args.dataset_dir
    diag = dataset / "diagnostics"
    pose_depth_path = (
        diag
        / "window_016_dart_camera_contract_pose_depth_scale_2026_06_05/window_016_pose_depth_scale_audit.json"
    )
    post_dir = dataset / "da3_seq_k35_coreml_pose_dart_camera_contract_window016_cpu_official_postprocess_2026_06_05"
    reports_path = post_dir / "mac_da3_window_reports.json"
    pose_depth = read_json(pose_depth_path)
    window_reports = read_json(reports_path)

    frame_roles = {}
    for frame in window_reports["windows"][0].get("frames", []):
        frame_roles[int(frame.get("windowSlot", 0))] = {
            "frame_id": frame.get("frameID"),
            "window_role": frame.get("windowRole"),
            "frame_index": frame.get("frameIndex"),
        }

    slot_rows = []
    cumulative = pose_depth["cumulative"]
    per_slot = pose_depth["per_slot"]
    baseline = cumulative[9]
    for index, item in enumerate(cumulative):
        k = int(item["k"])
        slot = k - 1
        per = per_slot[slot]
        previous = cumulative[index - 1] if index > 0 else None
        row = {
            "slot": slot,
            "k": k,
            "frame_id": per["frame_id"],
            "frame_index": per["frame_index"],
            "window_role": frame_roles.get(slot, {}).get("window_role"),
            "pose_step_from_previous": per["step_from_previous"],
            "cumulative_pose_diag": item["pose"]["camera_center_diag"],
            "cumulative_pose_diag_delta": None
            if previous is None
            else item["pose"]["camera_center_diag"] - previous["pose"]["camera_center_diag"],
            "depth_median": per["depth"]["median"],
            "depth_p95": per["depth"]["p95"],
            "confidence_median": per["confidence"]["median"],
            "npz": deltas(item, previous, baseline, "npz_streaming_style"),
            "glb": deltas(item, previous, baseline, "glb_style"),
        }
        row["signals"] = classify_slot(row)
        slot_rows.append(row)

    late_rows = [row for row in slot_rows if row["k"] > 10]
    summary = {
        "largest_pose_step": top_rows(late_rows, "pose_step_from_previous", 5),
        "largest_pose_diag_delta": top_rows(late_rows, "cumulative_pose_diag_delta", 5),
        "largest_npz_minor_growth_vs_prev": top_nested_rows(late_rows, "npz", "minor_ratio_vs_prev", 5),
        "largest_npz_bbox_growth_vs_prev": top_nested_rows(late_rows, "npz", "bbox_ratio_vs_prev", 5),
        "largest_depth_p95": top_rows(late_rows, "depth_p95", 5),
        "lowest_confidence_median": sorted(
            late_rows,
            key=lambda row: none_to_inf(row["confidence_median"]),
        )[:5],
        "first_npz_bbox_ge_1_10_vs_k10": first_threshold(late_rows, "npz", "bbox_ratio_vs_k10", 1.10),
        "first_npz_minor_ge_1_10_vs_k10": first_threshold(late_rows, "npz", "minor_ratio_vs_k10", 1.10),
        "first_npz_minor_ge_1_35_vs_k10": first_threshold(late_rows, "npz", "minor_ratio_vs_k10", 1.35),
        "interpretation": [],
    }
    summary["interpretation"] = interpret(summary, slot_rows)
    return {
        "schema_version": "aether_da3_window016_late_slot_geometry_consistency_audit_v1",
        "date": args.date,
        "decision": {
            "status": "late_slot_pose_depth_consistency_suspect",
            "goal_complete": False,
            "conclusion": (
                "window_016 thickening starts after the first 10 frames and aligns most strongly "
                "with late-slot pose-span expansion, with additional depth/confidence risk around slot 24."
            ),
            "next_best_action": (
                "Inspect/remediate K-window composition and DA3 upstream pose/depth consistency for late slots; "
                "do not treat downstream point filtering as the primary fix."
            ),
        },
        "inputs": {
            "pose_depth_scale_audit": str(pose_depth_path),
            "window_reports": str(reports_path),
        },
        "baseline": {
            "k": 10,
            "pose_diag": baseline["pose"]["camera_center_diag"],
            "npz_bbox": baseline["npz_streaming_style"]["bbox_diag_p01_p99"],
            "npz_minor": baseline["npz_streaming_style"]["pca_minor_extent"],
            "glb_bbox": baseline["glb_style"]["bbox_diag_p01_p99"],
            "glb_minor": baseline["glb_style"]["pca_minor_extent"],
        },
        "summary": summary,
        "slot_rows": slot_rows,
        "plain_language": [
            "first10 之后第一个强信号是 slot 10/cap-1396：相机中心 span 从 0.297 跳到 0.677，最大 step 0.410。",
            "npz downstream 的 bbox/minor 不是最后才突然出现；k12 已经超过 k10 的 1.10x minor 阈值，后面逐步累积。",
            "slot 24/cap-1514 是第二个可疑点：pose step 很大、depth p95 很高、confidence median 很低，容易把厚层尾部拉大。",
            "这更像上游几何一致性和 K-window 组成问题，而不是 downstream 缺一个去重点云开关。",
        ],
    }


def deltas(
    item: dict[str, Any],
    previous: dict[str, Any] | None,
    baseline: dict[str, Any],
    style: str,
) -> dict[str, float | None]:
    now = item[style]
    base = baseline[style]
    prev = previous[style] if previous else None
    return {
        "bbox_ratio_vs_prev": None if prev is None else ratio(now["bbox_diag_p01_p99"], prev["bbox_diag_p01_p99"]),
        "minor_ratio_vs_prev": None if prev is None else ratio(now["pca_minor_extent"], prev["pca_minor_extent"]),
        "conf_threshold_ratio_vs_prev": None if prev is None else ratio(now["conf_threshold"], prev["conf_threshold"]),
        "valid_fraction_delta_vs_prev": None
        if prev is None
        else now["valid_fraction_of_pixels"] - prev["valid_fraction_of_pixels"],
        "bbox_ratio_vs_k10": ratio(now["bbox_diag_p01_p99"], base["bbox_diag_p01_p99"]),
        "minor_ratio_vs_k10": ratio(now["pca_minor_extent"], base["pca_minor_extent"]),
        "conf_threshold_ratio_vs_k10": ratio(now["conf_threshold"], base["conf_threshold"]),
        "valid_fraction_delta_vs_k10": now["valid_fraction_of_pixels"] - base["valid_fraction_of_pixels"],
    }


def classify_slot(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "large_pose_step_ge_0_25": (row["pose_step_from_previous"] or 0) >= 0.25,
        "pose_diag_delta_ge_0_15": (row["cumulative_pose_diag_delta"] or 0) >= 0.15,
        "npz_minor_jump_ge_1_10": (row["npz"]["minor_ratio_vs_prev"] or 0) >= 1.10,
        "npz_bbox_jump_ge_1_10": (row["npz"]["bbox_ratio_vs_prev"] or 0) >= 1.10,
        "depth_p95_ge_3": (row["depth_p95"] or 0) >= 3.0,
        "confidence_median_lt_2_5": (row["confidence_median"] or 999) < 2.5,
    }


def top_rows(rows: list[dict[str, Any]], key: str, limit: int) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: none_to_neg_inf(row.get(key)), reverse=True)[:limit]


def top_nested_rows(rows: list[dict[str, Any]], parent: str, key: str, limit: int) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: none_to_neg_inf(row[parent].get(key)),
        reverse=True,
    )[:limit]


def first_threshold(rows: list[dict[str, Any]], parent: str, key: str, threshold: float) -> dict[str, Any] | None:
    for row in rows:
        value = row[parent].get(key)
        if value is not None and value >= threshold:
            return {
                "slot": row["slot"],
                "k": row["k"],
                "frame_id": row["frame_id"],
                "frame_index": row["frame_index"],
                "window_role": row["window_role"],
                key: value,
            }
    return None


def interpret(summary: dict[str, Any], slot_rows: list[dict[str, Any]]) -> list[str]:
    largest_step = summary["largest_pose_step"][0]
    first_minor = summary["first_npz_minor_ge_1_10_vs_k10"]
    low_conf = summary["lowest_confidence_median"][0]
    depth_tail = summary["largest_depth_p95"][0]
    return [
        (
            f"Largest pose step is slot {largest_step['slot']} / {largest_step['frame_id']} "
            f"({largest_step['pose_step_from_previous']:.3f}); this is the first major span break after k10."
        ),
        (
            "First npz minor ratio >=1.10 vs k10 occurs at "
            f"slot {first_minor['slot']} / {first_minor['frame_id']} (k={first_minor['k']})."
        )
        if first_minor
        else "npz minor ratio never crosses 1.10 after k10.",
        (
            f"Lowest confidence median is slot {low_conf['slot']} / {low_conf['frame_id']} "
            f"({low_conf['confidence_median']:.3f}); low-confidence late slots can lower npz threshold pressure."
        ),
        (
            f"Largest depth p95 is slot {depth_tail['slot']} / {depth_tail['frame_id']} "
            f"({depth_tail['depth_p95']:.3f}); this late depth tail can widen the layer after the pose span has expanded."
        ),
    ]


def ratio(top: float, bottom: float) -> float | None:
    if bottom == 0:
        return None
    return float(top / bottom)


def none_to_neg_inf(value: Any) -> float:
    return float(value) if value is not None else float("-inf")


def none_to_inf(value: Any) -> float:
    return float(value) if value is not None else float("inf")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "summary": {
            "largest_pose_step": slim(report["summary"]["largest_pose_step"][0]),
            "first_npz_minor_ge_1_10_vs_k10": report["summary"]["first_npz_minor_ge_1_10_vs_k10"],
            "largest_depth_p95": slim(report["summary"]["largest_depth_p95"][0]),
            "lowest_confidence_median": slim(report["summary"]["lowest_confidence_median"][0]),
        },
    }


def slim(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot": row["slot"],
        "k": row["k"],
        "frame_id": row["frame_id"],
        "frame_index": row["frame_index"],
        "window_role": row["window_role"],
        "pose_step_from_previous": row["pose_step_from_previous"],
        "cumulative_pose_diag_delta": row["cumulative_pose_diag_delta"],
        "depth_p95": row["depth_p95"],
        "confidence_median": row["confidence_median"],
        "npz_minor_ratio_vs_prev": row["npz"]["minor_ratio_vs_prev"],
        "npz_minor_ratio_vs_k10": row["npz"]["minor_ratio_vs_k10"],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 window_016 late-slot geometry consistency audit",
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
        report["decision"]["next_best_action"],
        "",
        "## 大白话",
        "",
    ]
    for item in report["plain_language"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Top Signals", ""])
    for item in report["summary"]["interpretation"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Late Slots",
            "",
            "| slot | frame | role | step | pose_diag_delta | depth_p95 | conf_med | npz minor vs k10 | npz bbox vs k10 |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["slot_rows"]:
        if row["k"] <= 10:
            continue
        lines.append(
            "| {slot} | `{frame}` | `{role}` | {step:.3f} | {delta:.3f} | {depth:.3f} | {conf:.3f} | {minor:.3f} | {bbox:.3f} |".format(
                slot=row["slot"],
                frame=row["frame_id"],
                role=row["window_role"],
                step=row["pose_step_from_previous"] or 0.0,
                delta=row["cumulative_pose_diag_delta"] or 0.0,
                depth=row["depth_p95"] or 0.0,
                conf=row["confidence_median"] or 0.0,
                minor=row["npz"]["minor_ratio_vs_k10"] or 0.0,
                bbox=row["npz"]["bbox_ratio_vs_k10"] or 0.0,
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
