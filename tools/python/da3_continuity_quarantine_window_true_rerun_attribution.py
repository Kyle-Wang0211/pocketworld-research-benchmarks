#!/usr/bin/env python3
"""Attribute one DA3 continuity-quarantine true rerun against its source window."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
VARIANTS = (
    "prefix_before_first_break",
    "segment_from_first_break",
    "drop_all_high_risk_targets",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--source-window-id", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output_stem = f"official_da3_continuity_quarantine_{args.source_window_id}_true_rerun_attribution"
    write_json(args.out_dir / f"{output_stem}.json", report)
    write_markdown(args.out_dir / f"{output_stem}_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    diag = args.dataset_dir / "diagnostics"
    source_window_id = args.source_window_id
    rows: dict[str, dict[str, Any]] = {
        "official_save_source": summarize_audit(
            read_json(
                diag
                / f"{source_window_id}_official_save_frame_pose_depth_scale_2026_06_05"
                / f"{source_window_id}_pose_depth_scale_audit.json"
            ),
            str(
                diag
                / f"{source_window_id}_official_save_frame_pose_depth_scale_2026_06_05"
                / f"{source_window_id}_pose_depth_scale_audit.json"
            ),
        )
    }
    for suffix in VARIANTS:
        variant_window_id = f"{source_window_id}_{suffix}"
        audit_path = (
            diag
            / f"{variant_window_id}_true_rerun_pose_depth_scale_2026_06_05"
            / f"{variant_window_id}_pose_depth_scale_audit.json"
        )
        if audit_path.exists():
            rows[suffix] = summarize_audit(read_json(audit_path), str(audit_path))
        else:
            rows[suffix] = missing_variant_row(variant_window_id, str(audit_path))

    base = rows["official_save_source"]
    for row in rows.values():
        row["vs_official_save"] = {
            "npz_minor_ratio": safe_ratio(row["npz_minor_abs"], base["npz_minor_abs"]),
            "npz_bbox_ratio": safe_ratio(row["npz_bbox_abs"], base["npz_bbox_abs"]),
            "glb_minor_ratio": safe_ratio(row["glb_minor_abs"], base["glb_minor_abs"]),
            "glb_bbox_ratio": safe_ratio(row["glb_bbox_abs"], base["glb_bbox_abs"]),
            "pose_diag_ratio": safe_ratio(row["pose_diag_abs"], base["pose_diag_abs"]),
        }

    source_is_thick = (
        base["within_window"]["npz_minor_ratio_vs_k10"] >= 1.10
        or base["within_window"]["npz_bbox_ratio_vs_k10"] >= 1.10
        or base["within_window"]["glb_minor_ratio_vs_k10"] >= 1.10
    )
    drop = rows["drop_all_high_risk_targets"]
    drop_reduces = (
        drop["vs_official_save"]["npz_minor_ratio"] is not None
        and drop["vs_official_save"]["npz_minor_ratio"] < 0.85
    )
    if source_is_thick and drop_reduces:
        status = "true_rerun_continuity_quarantine_reduces_source_thickness"
    elif not source_is_thick:
        status = "source_window_not_thick_continuity_quarantine_negative_control"
    else:
        status = "true_rerun_continuity_quarantine_inconclusive_for_source"

    return {
        "schema_version": "aether_da3_continuity_quarantine_window_true_rerun_attribution_v1",
        "date": args.date,
        "source_window_id": source_window_id,
        "decision": {
            "status": status,
            "goal_complete": False,
            "source_is_thick": source_is_thick,
            "drop_variant_reduces_npz_minor": drop_reduces,
            "conclusion": conclusion_for(status, source_window_id),
            "boundary": (
                "This is still the current pose-conditioned DA3BASE_476x742_N35 CoreML product path. "
                "It tests a mobile continuity/windowing adaptation candidate, not official image-only parity."
            ),
            "next_best_action": (
                "Continue the same true-rerun attribution on the remaining prepared candidates, then decide "
                "whether continuity quarantine should be a hard product gate, a warning gate, or only a capture-quality signal."
            ),
        },
        "inputs": {
            "dataset_dir": str(args.dataset_dir),
            "diagnostics_dir": str(diag),
        },
        "rows": rows,
        "plain_language": plain_language(source_window_id, rows, status),
    }


def summarize_audit(report: dict[str, Any], path: str) -> dict[str, Any]:
    scope = report["scope"]
    summary = report["summary"]
    last = report["cumulative"][-1]
    npz_ratio = summary["styles"]["npz_streaming_style"]["k35_over_k10"]
    glb_ratio = summary["styles"]["glb_style"]["k35_over_k10"]
    frames = [row["frame_id"] for row in report["per_slot"]]
    return {
        "status": "completed",
        "source": path,
        "window_id": scope["window_id"],
        "frame_count": scope["frame_count"],
        "pose_scale": scope["pose_scale"],
        "frame_ids": frames,
        "npz_minor_abs": last["npz_streaming_style"]["pca_minor_extent"],
        "npz_bbox_abs": last["npz_streaming_style"]["bbox_diag_p01_p99"],
        "glb_minor_abs": last["glb_style"]["pca_minor_extent"],
        "glb_bbox_abs": last["glb_style"]["bbox_diag_p01_p99"],
        "pose_diag_abs": last["pose"]["camera_center_diag"],
        "depth_p95_abs": last["depth"]["p95"],
        "within_window": {
            "npz_minor_ratio_vs_k10": npz_ratio["minor_ratio_vs_k10"],
            "npz_bbox_ratio_vs_k10": npz_ratio["bbox_ratio_vs_k10"],
            "glb_minor_ratio_vs_k10": glb_ratio["minor_ratio_vs_k10"],
            "glb_bbox_ratio_vs_k10": glb_ratio["bbox_ratio_vs_k10"],
            "pose_diag_ratio_vs_k10": summary["pose"]["k35_over_k10_pose_diag"],
        },
    }


def missing_variant_row(window_id: str, path: str) -> dict[str, Any]:
    return {
        "status": "missing_or_skipped",
        "source": path,
        "window_id": window_id,
        "frame_count": 0,
        "pose_scale": None,
        "frame_ids": [],
        "npz_minor_abs": None,
        "npz_bbox_abs": None,
        "glb_minor_abs": None,
        "glb_bbox_abs": None,
        "pose_diag_abs": None,
        "depth_p95_abs": None,
        "within_window": {
            "npz_minor_ratio_vs_k10": None,
            "npz_bbox_ratio_vs_k10": None,
            "glb_minor_ratio_vs_k10": None,
            "glb_bbox_ratio_vs_k10": None,
            "pose_diag_ratio_vs_k10": None,
        },
    }


def conclusion_for(status: str, source_window_id: str) -> str:
    if status == "true_rerun_continuity_quarantine_reduces_source_thickness":
        return (
            f"{source_window_id} behaves like window_016: the source official-save window is thick, and a true CoreML "
            "rerun on continuity-quarantined variants reduces thickness."
        )
    if status == "source_window_not_thick_continuity_quarantine_negative_control":
        return (
            f"{source_window_id} is a negative/control sample: it has continuity risk, but the source official-save "
            "window is not thick by the current npz/glb growth metrics. Continuity risk alone is not enough to prove "
            "single-window thickening."
        )
    return (
        f"{source_window_id} remains inconclusive: the source window is thick or borderline, but the true rerun did "
        "not show a clear quarantine reduction."
    )


def plain_language(source_window_id: str, rows: dict[str, dict[str, Any]], status: str) -> list[str]:
    base = rows["official_save_source"]
    prefix = rows["prefix_before_first_break"]
    segment = rows["segment_from_first_break"]
    drop = rows["drop_all_high_risk_targets"]
    return [
        f"{source_window_id} 原始 official-save {base['frame_count']} 帧：npz minor/k10={base['within_window']['npz_minor_ratio_vs_k10']:.3f}, bbox/k10={base['within_window']['npz_bbox_ratio_vs_k10']:.3f}。",
        variant_sentence("prefix", prefix),
        variant_sentence("segment", segment),
        variant_sentence("drop-high-risk", drop),
        (
            "这不是 window_016 那种阳性减薄样本；它更像 negative/control，提醒我们 continuity gate 需要结合实际几何厚度，不能只看时间/位移/质量阈值。"
            if status == "source_window_not_thick_continuity_quarantine_negative_control"
            else "这个样本继续支持 quarantine 方向，但还要和其它候选一起看。"
        ),
    ]


def variant_sentence(label: str, row: dict[str, Any]) -> str:
    minor = get_path(row, "vs_official_save.npz_minor_ratio")
    bbox = get_path(row, "vs_official_save.npz_bbox_ratio")
    if minor is None or bbox is None:
        return f"{label} 未生成有效审计：通常是帧数太少或官方 Umeyama 对齐退化。"
    return f"{label} {row['frame_count']} 帧：npz minor/orig={minor:.3f}, bbox/orig={bbox:.3f}。"


def safe_ratio(value: Any, base: Any) -> float | None:
    try:
        v = float(value)
        b = float(base)
    except (TypeError, ValueError):
        return None
    if abs(b) < 1e-12:
        return None
    return v / b


def get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "source_window_id": report["source_window_id"],
        "decision": report["decision"],
        "rows": {
            name: {
                "frame_count": row["frame_count"],
                "npz_minor_abs": row["npz_minor_abs"],
                "npz_bbox_abs": row["npz_bbox_abs"],
                "within_window": row["within_window"],
                "vs_official_save": row["vs_official_save"],
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
        f"source window：`{report['source_window_id']}`",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- goal complete: `{report['decision']['goal_complete']}`",
        f"- source is thick: `{report['decision']['source_is_thick']}`",
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
            "| variant | frames | pose scale | npz minor | npz minor/k10 | npz minor/orig | npz bbox/orig | glb minor/orig | pose diag/orig |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, row in report["rows"].items():
        vs = row["vs_official_save"]
        within = row["within_window"]
        if row.get("status") == "missing_or_skipped":
            lines.append(f"| `{name}` | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
            continue
        lines.append(
            "| `{name}` | {frames} | {pose_scale:.3f} | {minor:.3f} | {minor_k10:.3f} | {minor_ratio:.3f} | {bbox_ratio:.3f} | {glb_ratio:.3f} | {pose_ratio:.3f} |".format(
                name=name,
                frames=row["frame_count"],
                pose_scale=float(row["pose_scale"]),
                minor=float(row["npz_minor_abs"]),
                minor_k10=float(within["npz_minor_ratio_vs_k10"]),
                minor_ratio=float(vs["npz_minor_ratio"] or 0.0),
                bbox_ratio=float(vs["npz_bbox_ratio"] or 0.0),
                glb_ratio=float(vs["glb_minor_ratio"] or 0.0),
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
