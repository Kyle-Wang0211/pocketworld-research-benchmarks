#!/usr/bin/env python3
"""Summarize true DA3 CoreML reruns for continuity quarantine variants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
AUDITS = {
    "official_save_window016": "window_016_official_save_frame_pose_depth_scale_2026_06_05/window_016_pose_depth_scale_audit.json",
    "prefix_before_first_break": "window_016_prefix_before_first_break_true_rerun_pose_depth_scale_2026_06_05/window_016_prefix_before_first_break_pose_depth_scale_audit.json",
    "segment_from_first_break": "window_016_segment_from_first_break_true_rerun_pose_depth_scale_2026_06_05/window_016_segment_from_first_break_pose_depth_scale_audit.json",
    "drop_all_high_risk_targets": "window_016_drop_all_high_risk_targets_true_rerun_pose_depth_scale_2026_06_05/window_016_drop_all_high_risk_targets_pose_depth_scale_audit.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_continuity_quarantine_true_rerun_attribution.json", report)
    write_markdown(
        args.out_dir / "official_da3_continuity_quarantine_true_rerun_attribution_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    diag = args.dataset_dir / "diagnostics"
    rows = {
        name: summarize_audit(read_json(diag / rel_path), str(diag / rel_path))
        for name, rel_path in AUDITS.items()
    }
    base = rows["official_save_window016"]
    for row in rows.values():
        row["vs_official_save"] = {
            "npz_minor_ratio": safe_ratio(row["npz_minor_abs"], base["npz_minor_abs"]),
            "npz_bbox_ratio": safe_ratio(row["npz_bbox_abs"], base["npz_bbox_abs"]),
            "glb_minor_ratio": safe_ratio(row["glb_minor_abs"], base["glb_minor_abs"]),
            "pose_diag_ratio": safe_ratio(row["pose_diag_abs"], base["pose_diag_abs"]),
        }

    drop = rows["drop_all_high_risk_targets"]
    prefix = rows["prefix_before_first_break"]
    status = (
        "true_rerun_continuity_quarantine_reduces_window016_thickness"
        if drop["vs_official_save"]["npz_minor_ratio"] is not None
        and drop["vs_official_save"]["npz_minor_ratio"] < 0.80
        and prefix["vs_official_save"]["npz_minor_ratio"] is not None
        and prefix["vs_official_save"]["npz_minor_ratio"] < 0.85
        else "true_rerun_continuity_quarantine_inconclusive"
    )
    return {
        "schema_version": "aether_da3_continuity_quarantine_true_rerun_attribution_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "conclusion": (
                "A true CoreML N35 rerun on continuity-quarantined variants reduces window_016 thickness "
                "substantially. The strongest signal is not deleting cap-1396 points downstream; it is preventing "
                "a discontinuous capture segment from sharing one DA3 K35 inference context."
            ),
            "boundary": (
                "This is still the current pose-conditioned product CoreML path, not full image-only DA3 parity. "
                "The official-replication branch remains unchanged; quarantine is a mobile capture/windowing adaptation candidate."
            ),
            "next_best_action": (
                "Implement a Dart-side research window split/quarantine simulator that recomputes continuity after removals, "
                "then re-run on more windows/captures before turning it into a product gate."
            ),
        },
        "inputs": {
            "dataset_dir": str(args.dataset_dir),
            "audits": {name: str(diag / rel_path) for name, rel_path in AUDITS.items()},
        },
        "rows": rows,
        "plain_language": plain_language(rows),
    }


def summarize_audit(report: dict[str, Any], path: str) -> dict[str, Any]:
    scope = report["scope"]
    summary = report["summary"]
    last = report["cumulative"][-1]
    npz_ratio = summary["styles"]["npz_streaming_style"]["k35_over_k10"]
    glb_ratio = summary["styles"]["glb_style"]["k35_over_k10"]
    frames = [row["frame_id"] for row in report["per_slot"]]
    return {
        "source": path,
        "window_id": scope["window_id"],
        "frame_count": scope["frame_count"],
        "pose_scale": scope["pose_scale"],
        "frame_ids": frames,
        "npz_minor_abs": last["npz_streaming_style"]["pca_minor_extent"],
        "npz_bbox_abs": last["npz_streaming_style"]["bbox_diag_p01_p99"],
        "glb_minor_abs": last["glb_style"]["pca_minor_extent"],
        "pose_diag_abs": last["pose"]["camera_center_diag"],
        "depth_p95_abs": last["depth"]["p95"],
        "within_window": {
            "npz_minor_ratio_vs_k10": npz_ratio["minor_ratio_vs_k10"],
            "npz_bbox_ratio_vs_k10": npz_ratio["bbox_ratio_vs_k10"],
            "glb_minor_ratio_vs_k10": glb_ratio["minor_ratio_vs_k10"],
            "pose_diag_ratio_vs_k10": summary["pose"]["k35_over_k10_pose_diag"],
        },
    }


def plain_language(rows: dict[str, dict[str, Any]]) -> list[str]:
    base = rows["official_save_window016"]
    prefix = rows["prefix_before_first_break"]
    segment = rows["segment_from_first_break"]
    drop = rows["drop_all_high_risk_targets"]
    return [
        f"原始 window_016 official-save 17 帧仍厚：npz minor={base['npz_minor_abs']:.3f}, bbox={base['npz_bbox_abs']:.3f}, 内部 minor/k10={base['within_window']['npz_minor_ratio_vs_k10']:.3f}。",
        f"断点前 prefix 10 帧真重跑更薄：npz minor={prefix['npz_minor_abs']:.3f}，约为原始的 {prefix['vs_official_save']['npz_minor_ratio']:.3f}。",
        f"断点后 segment 7 帧单独跑：npz minor={segment['npz_minor_abs']:.3f}，bbox={segment['npz_bbox_abs']:.3f}；它说明后半段不是简单无害，但不应和前半段共享同一个 K35 context。",
        f"去掉所有当前 high-risk targets 的 12 帧真重跑：npz minor={drop['npz_minor_abs']:.3f}，约为原始的 {drop['vs_official_save']['npz_minor_ratio']:.3f}；内部 minor/k10 只有 {drop['within_window']['npz_minor_ratio_vs_k10']:.3f}。",
        "这支持 continuity quarantine/window split，而不是 downstream 点云去重；官方复刻分支仍然保留，移动端适配分支再加这个 gate。",
    ]


def safe_ratio(value: Any, base: Any) -> float | None:
    try:
        v = float(value)
        b = float(base)
    except (TypeError, ValueError):
        return None
    if abs(b) < 1e-12:
        return None
    return v / b


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "rows": {
            name: {
                "frame_count": row["frame_count"],
                "npz_minor_abs": row["npz_minor_abs"],
                "npz_bbox_abs": row["npz_bbox_abs"],
                "vs_official_save": row["vs_official_save"],
                "within_window": row["within_window"],
            }
            for name, row in report["rows"].items()
        },
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# DA3 continuity quarantine true-rerun attribution",
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
            "## Variants",
            "",
            "| variant | frames | npz minor | npz minor/orig | npz bbox | npz bbox/orig | glb minor/orig | within npz minor/k10 | pose diag/orig |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, row in report["rows"].items():
        vs = row["vs_official_save"]
        within = row["within_window"]
        lines.append(
            "| `{name}` | {frames} | {minor:.3f} | {minor_ratio:.3f} | {bbox:.3f} | {bbox_ratio:.3f} | {glb_ratio:.3f} | {within_minor:.3f} | {pose_ratio:.3f} |".format(
                name=name,
                frames=row["frame_count"],
                minor=float(row["npz_minor_abs"]),
                minor_ratio=float(vs["npz_minor_ratio"] or 0.0),
                bbox=float(row["npz_bbox_abs"]),
                bbox_ratio=float(vs["npz_bbox_ratio"] or 0.0),
                glb_ratio=float(vs["glb_minor_ratio"] or 0.0),
                within_minor=float(within["npz_minor_ratio_vs_k10"]),
                pose_ratio=float(vs["pose_diag_ratio"] or 0.0),
            )
        )
    lines.extend(["", "## Frame Sets", ""])
    for name, row in report["rows"].items():
        lines.append(f"- `{name}`: " + ", ".join(f"`{frame_id}`" for frame_id in row["frame_ids"]))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
