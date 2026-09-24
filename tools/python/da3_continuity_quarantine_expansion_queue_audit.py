#!/usr/bin/env python3
"""Rank DA3 continuity-quarantine windows for the next true-rerun expansion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
CAPTURE_DIR_NAME = "capture_seq_k35_strict"
VARIANT_SUFFIXES = (
    "prefix_before_first_break",
    "segment_from_first_break",
    "drop_all_high_risk_targets",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    parser.add_argument("--top-n", type=int, default=8)
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_continuity_quarantine_expansion_queue_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_continuity_quarantine_expansion_queue_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    capture_dir = args.dataset_dir / CAPTURE_DIR_NAME
    quarantine_path = capture_dir / "da3_k_windows_continuity_quarantine.json"
    official_path = capture_dir / "da3_k_windows.json"
    quarantine = read_json(quarantine_path)
    official = read_json(official_path)
    official_by_id = {str(item.get("id")): item for item in official.get("windows", [])}
    variants_by_source = variants_by_source_window(quarantine)

    rows = []
    for source in quarantine.get("riskySourceWindows", []):
        source_id = str(source.get("sourceWindowID"))
        official_window = official_by_id.get(source_id, {})
        variants = variants_by_source.get(source_id, {})
        rows.append(summarize_source_window(source, official_window, variants))

    rows.sort(key=lambda row: (-row["priority_score"], row["source_window_id"]))
    for index, row in enumerate(rows, start=1):
        row["priority_rank"] = index
        row["recommendation"] = recommendation_for(row, index)
        row["research_capture_manifest"] = capture_manifest_status(args.dataset_dir, row["source_window_id"], args.date)

    top_candidates = rows[: max(0, args.top_n)]
    recommended_batch = [
        row
        for row in rows
        if row["recommendation"] == "next_true_rerun_candidate"
    ][: max(0, min(args.top_n, 5))]
    already_tested = [row for row in rows if row["source_window_id"] == "window_016"]
    manifest_ready_count = sum(
        1 for row in recommended_batch if row["research_capture_manifest"]["exists"]
    )
    status = (
        "expansion_queue_and_manifest_batch_ready_true_reruns_needed"
        if recommended_batch and manifest_ready_count == len(recommended_batch)
        else "expansion_queue_ready_manifest_generation_needed"
        if recommended_batch
        else "expansion_queue_ready_more_true_reruns_needed"
        if rows and top_candidates
        else "expansion_queue_missing"
    )
    next_best_action = (
        "Run the same current DA3BASE_476x742_N35_pose CoreML path on the prepared research capture "
        "manifests, then compare official-save thickness against the prefix/segment/drop-high-risk variants."
        if recommended_batch and manifest_ready_count == len(recommended_batch)
        else "Create research capture manifests for the recommended candidates, rerun the same current "
        "DA3BASE_476x742_N35_pose CoreML path, and compare official-save thickness against the "
        "prefix/segment/drop-high-risk variants."
    )

    return {
        "schema_version": "aether_da3_continuity_quarantine_expansion_queue_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "product_ready": False,
            "conclusion": (
                "The Dart quarantine plan has enough information to rank risky source windows for the next "
                "true CoreML rerun batch. The queue keeps official DA3 replication separate from the mobile "
                "continuity adaptation candidate."
            ),
            "boundary": (
                "This ranking is not a geometry pass/fail result. It only chooses the next windows to rerun "
                "because full thickness attribution still requires actual CoreML outputs and downstream audits."
            ),
            "next_best_action": next_best_action,
        },
        "inputs": {
            "dataset_dir": str(args.dataset_dir),
            "official_window_plan": str(official_path),
            "dart_quarantine_window_plan": str(quarantine_path),
        },
        "metrics": {
            "official_window_count": official.get("windowCount"),
            "risky_source_window_count": len(rows),
            "quarantine_variant_count": quarantine.get("windowCount"),
            "top_n": args.top_n,
            "already_true_rerun_window_ids": [row["source_window_id"] for row in already_tested],
            "recommended_batch_window_ids": [row["source_window_id"] for row in recommended_batch],
            "recommended_batch_manifest_ready_count": manifest_ready_count,
        },
        "priority_formula": priority_formula(),
        "top_candidates": top_candidates,
        "recommended_true_rerun_batch": recommended_batch,
        "all_risky_windows": rows,
        "plain_language": plain_language(top_candidates, recommended_batch),
    }


def variants_by_source_window(quarantine: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for window in quarantine.get("windows", []):
        source_id = str(window.get("sourceWindowID") or "")
        window_id = str(window.get("id") or "")
        if not source_id or not window_id:
            continue
        for suffix in VARIANT_SUFFIXES:
            if window_id.endswith(suffix):
                result.setdefault(source_id, {})[suffix] = window
    return result


def summarize_source_window(
    source: dict[str, Any],
    official_window: dict[str, Any],
    variants: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    high_risk_steps = [
        step for step in source.get("continuitySteps", []) if isinstance(step, dict) and step.get("highRisk")
    ]
    source_id = str(source.get("sourceWindowID"))
    official_ids = [str(value) for value in source.get("officialSaveFrameIDs", [])]
    if not official_ids:
        official_ids = [str(value) for value in official_window.get("downstreamFrameIDs", [])]
    high_risk_ids = [str(value) for value in source.get("highRiskFrameIDs", [])]
    first_break_id = str(source.get("firstBreakFrameID") or "")
    first_break_slot = official_ids.index(first_break_id) if first_break_id in official_ids else None

    variant_summary = {
        suffix: summarize_variant(variants.get(suffix, {}))
        for suffix in VARIANT_SUFFIXES
    }
    max_dt = max_float(high_risk_steps, "timestampDeltaSeconds")
    max_translation = max_float(high_risk_steps, "translationStepM")
    max_azimuth = max_float(high_risk_steps, "azimuthDeltaRad")
    max_elevation = max_float(high_risk_steps, "elevationDeltaRad")
    min_quality = min_float(high_risk_steps, "toQualityScore")
    priority_score = risk_score(
        high_risk_count=len(high_risk_ids),
        max_dt=max_dt,
        max_translation=max_translation,
        max_azimuth=max_azimuth,
        max_elevation=max_elevation,
        min_quality=min_quality,
        variant_summary=variant_summary,
        source_id=source_id,
    )
    return {
        "source_window_id": source_id,
        "official_save_frame_count": len(official_ids),
        "first_break_frame_id": first_break_id or None,
        "first_break_slot": first_break_slot,
        "high_risk_frame_count": len(high_risk_ids),
        "high_risk_frame_ids": high_risk_ids,
        "max_timestamp_delta_seconds": max_dt,
        "max_translation_step_m": max_translation,
        "max_azimuth_delta_rad": max_azimuth,
        "max_elevation_delta_rad": max_elevation,
        "min_high_risk_quality_score": min_quality,
        "priority_score": priority_score,
        "variants": variant_summary,
        "top_high_risk_steps": sorted(
            high_risk_steps,
            key=lambda item: (
                -float_or_zero(item.get("timestampDeltaSeconds")),
                -float_or_zero(item.get("translationStepM")),
            ),
        )[:5],
    }


def summarize_variant(window: dict[str, Any]) -> dict[str, Any]:
    if not window:
        return {
            "exists": False,
            "real_frame_count": 0,
            "runtime_padding_frame_count": 0,
            "continuity_status": None,
            "residual_high_risk_step_count": None,
            "removed_frame_count": 0,
            "downstream_frame_ids": [],
            "removed_frame_ids": [],
        }
    return {
        "exists": True,
        "real_frame_count": window.get("realFrameCount"),
        "runtime_padding_frame_count": window.get("runtimePaddingFrameCount")
        or len(window.get("runtimePaddingFrameIDs") or []),
        "continuity_status": get_path(window, "continuityAudit.status"),
        "residual_high_risk_step_count": get_path(window, "continuityAudit.highRiskStepCount"),
        "removed_frame_count": len(window.get("removedFrameIDs") or []),
        "downstream_frame_ids": [str(value) for value in window.get("downstreamFrameIDs", [])],
        "removed_frame_ids": [str(value) for value in window.get("removedFrameIDs", [])],
    }


def risk_score(
    *,
    high_risk_count: int,
    max_dt: float | None,
    max_translation: float | None,
    max_azimuth: float | None,
    max_elevation: float | None,
    min_quality: float | None,
    variant_summary: dict[str, dict[str, Any]],
    source_id: str,
) -> float:
    score = high_risk_count * 10.0
    score += excess(max_dt, 2.0) * 1.5
    score += excess(max_translation, 0.25) * 16.0
    score += excess(max_azimuth, 0.35) * 10.0
    score += excess(max_elevation, 0.25) * 10.0
    if min_quality is not None:
        score += max(0.0, 0.50 - min_quality) * 20.0
    drop = variant_summary.get("drop_all_high_risk_targets", {})
    drop_count = int(drop.get("real_frame_count") or 0)
    residual = drop.get("residual_high_risk_step_count")
    if drop_count >= 10:
        score += 5.0
    if residual == 0:
        score += 3.0
    if source_id == "window_016":
        score -= 8.0
    return round(score, 3)


def recommendation_for(row: dict[str, Any], rank: int) -> str:
    if row["source_window_id"] == "window_016":
        return "already_true_rerun_baseline"
    drop = row["variants"].get("drop_all_high_risk_targets", {})
    prefix = row["variants"].get("prefix_before_first_break", {})
    segment = row["variants"].get("segment_from_first_break", {})
    if rank <= 5 and int(drop.get("real_frame_count") or 0) >= 10:
        return "next_true_rerun_candidate"
    if int(prefix.get("real_frame_count") or 0) < 4 or int(segment.get("real_frame_count") or 0) < 4:
        return "lower_priority_short_segment"
    return "queue_candidate"


def capture_manifest_status(dataset_dir: Path, source_window_id: str, date: str) -> dict[str, Any]:
    compact_id = source_window_id.replace("_", "")
    capture_dir = dataset_dir / f"capture_seq_k35_continuity_quarantine_{compact_id}_{date.replace('-', '_')}"
    k_windows_path = capture_dir / "da3_k_windows.json"
    if not k_windows_path.exists():
        return {
            "exists": False,
            "capture_dir": str(capture_dir),
            "window_count": 0,
            "window_ids": [],
        }
    try:
        k_windows = read_json(k_windows_path)
    except json.JSONDecodeError:
        return {
            "exists": False,
            "capture_dir": str(capture_dir),
            "window_count": 0,
            "window_ids": [],
            "error": "invalid_json",
        }
    window_ids = [str(window.get("id")) for window in k_windows.get("windows", [])]
    return {
        "exists": True,
        "capture_dir": str(capture_dir),
        "window_count": len(window_ids),
        "window_ids": window_ids,
    }


def priority_formula() -> dict[str, str]:
    return {
        "intent": "Rank windows for the next true rerun, not declare geometry quality.",
        "high_risk_count": "+10 per high-risk target frame",
        "timestamp": "+1.5 per second above 2.0s",
        "translation": "+16 per meter above 0.25m",
        "azimuth": "+10 per radian above 0.35rad",
        "elevation": "+10 per radian above 0.25rad",
        "quality": "+20 per score below 0.50",
        "drop_variant": "+5 when drop-high-risk keeps at least 10 real frames; +3 when residual high-risk is zero",
        "window016": "-8 because it is already the true-rerun baseline",
    }


def plain_language(
    top_candidates: list[dict[str, Any]],
    recommended_batch: list[dict[str, Any]],
) -> list[str]:
    items = [
        "这不是新算法结论，只是下一批真重跑的排队表：先挑官方 downstream 内 continuity 风险最大、且变体仍有足够真帧的 window。",
        "window_016 已经有 true rerun 证据，所以它在队列里保留为 baseline，不再作为第一优先级重复跑。",
    ]
    for row in top_candidates[:5]:
        items.append(
            "{rank}. {window}: high-risk={risk}, max_dt={dt:.2f}s, max_trans={trans:.3f}m, "
            "drop_real={drop_real}, recommendation={rec}".format(
                rank=row["priority_rank"],
                window=row["source_window_id"],
                risk=row["high_risk_frame_count"],
                dt=float_or_zero(row["max_timestamp_delta_seconds"]),
                trans=float_or_zero(row["max_translation_step_m"]),
                drop_real=row["variants"]["drop_all_high_risk_targets"]["real_frame_count"],
                rec=row["recommendation"],
            )
        )
    if recommended_batch:
        items.append(
            "建议下一批先跑："
            + ", ".join(f"`{row['source_window_id']}`" for row in recommended_batch)
            + "。这些 window 的风险足够高，同时 drop-high-risk 变体仍保留至少 10 个真帧。"
        )
    items.append(
        "下一步应生成这些 candidate 的研究 capture manifest，再跑同一条 DA3BASE_476x742_N35_pose CoreML + official postprocess 厚度审计。"
    )
    return items


def max_float(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(value) for row in rows if (value := row.get(key)) is not None]
    return max(values) if values else None


def min_float(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(value) for row in rows if (value := row.get(key)) is not None]
    return min(values) if values else None


def excess(value: float | None, threshold: float) -> float:
    if value is None:
        return 0.0
    return max(0.0, value - threshold)


def float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "metrics": report["metrics"],
        "top_candidates": [
            {
                "rank": row["priority_rank"],
                "source_window_id": row["source_window_id"],
                "score": row["priority_score"],
                "recommendation": row["recommendation"],
                "high_risk_frame_count": row["high_risk_frame_count"],
                "max_dt": row["max_timestamp_delta_seconds"],
                "max_translation": row["max_translation_step_m"],
                "drop_real": row["variants"]["drop_all_high_risk_targets"]["real_frame_count"],
                "drop_residual_risk": row["variants"]["drop_all_high_risk_targets"][
                    "residual_high_risk_step_count"
                ],
            }
            for row in report["top_candidates"]
        ],
        "recommended_true_rerun_batch": [
            {
                "source_window_id": row["source_window_id"],
                "rank": row["priority_rank"],
                "score": row["priority_score"],
                "high_risk_frame_count": row["high_risk_frame_count"],
                "drop_real": row["variants"]["drop_all_high_risk_targets"]["real_frame_count"],
                "manifest_ready": row["research_capture_manifest"]["exists"],
            }
            for row in report["recommended_true_rerun_batch"]
        ],
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# DA3 continuity quarantine expansion queue audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- goal complete: `{report['decision']['goal_complete']}`",
        f"- product ready: `{report['decision']['product_ready']}`",
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
            "## Top Candidates",
            "",
            "| rank | source window | score | recommendation | high-risk frames | max dt/s | max trans/m | min quality | drop real | drop residual risk |",
            "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in report["top_candidates"]:
        drop = row["variants"]["drop_all_high_risk_targets"]
        lines.append(
            "| {rank} | `{window}` | {score:.3f} | `{rec}` | {risk} | {dt:.3f} | {trans:.3f} | {quality:.3f} | {drop_real} | {drop_risk} |".format(
                rank=row["priority_rank"],
                window=row["source_window_id"],
                score=row["priority_score"],
                rec=row["recommendation"],
                risk=row["high_risk_frame_count"],
                dt=float_or_zero(row["max_timestamp_delta_seconds"]),
                trans=float_or_zero(row["max_translation_step_m"]),
                quality=float_or_zero(row["min_high_risk_quality_score"]),
                drop_real=drop["real_frame_count"],
                drop_risk=drop["residual_high_risk_step_count"],
            )
        )

    lines.extend(
        [
            "",
            "## Recommended True-Rerun Batch",
            "",
            "| source window | rank | score | high-risk frames | drop real | reason |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in report["recommended_true_rerun_batch"]:
        drop = row["variants"]["drop_all_high_risk_targets"]
        manifest = row["research_capture_manifest"]
        reason = (
            f"manifest ready: `{manifest['capture_dir']}`"
            if manifest["exists"]
            else "manifest pending"
        )
        lines.append(
            "| `{window}` | {rank} | {score:.3f} | {risk} | {drop_real} | {reason} |".format(
                window=row["source_window_id"],
                rank=row["priority_rank"],
                score=row["priority_score"],
                risk=row["high_risk_frame_count"],
                drop_real=drop["real_frame_count"],
                reason=reason,
            )
        )

    lines.extend(
        [
            "",
            "## Variant Summary",
            "",
            "| source window | prefix real/risk | segment real/risk | drop real/risk | first break | high-risk IDs |",
            "|---|---:|---:|---:|---|---|",
        ]
    )
    for row in report["all_risky_windows"]:
        prefix = row["variants"]["prefix_before_first_break"]
        segment = row["variants"]["segment_from_first_break"]
        drop = row["variants"]["drop_all_high_risk_targets"]
        lines.append(
            "| `{window}` | {prefix_real}/{prefix_risk} | {segment_real}/{segment_risk} | {drop_real}/{drop_risk} | `{first}` | {ids} |".format(
                window=row["source_window_id"],
                prefix_real=prefix["real_frame_count"],
                prefix_risk=prefix["residual_high_risk_step_count"],
                segment_real=segment["real_frame_count"],
                segment_risk=segment["residual_high_risk_step_count"],
                drop_real=drop["real_frame_count"],
                drop_risk=drop["residual_high_risk_step_count"],
                first=row["first_break_frame_id"],
                ids=", ".join(f"`{frame_id}`" for frame_id in row["high_risk_frame_ids"]),
            )
        )

    lines.extend(
        [
            "",
            "## Inputs",
            "",
        ]
    )
    for key, value in report["inputs"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
