#!/usr/bin/env python3
"""Audit why cap-1396 entered the official DA3 downstream set.

This is a read-only attribution report. It connects three layers:

1. capture metadata in photo_bundle.json,
2. official DA3 streaming window ownership in da3_k_windows.json,
3. window_016/window_017 pose-depth thickness audits.

The goal is to distinguish image-quality acceptance from motion/pose
continuity risk. It does not change capture policy or DA3 outputs.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
DEFAULT_WINDOW_AUDITS = {
    "window_016": "window_016_official_save_frame_pose_depth_scale_2026_06_05/window_016_pose_depth_scale_audit.json",
    "window_017": "window_017_official_save_frame_pose_depth_scale_2026_06_05/window_017_pose_depth_scale_audit.json",
}
CONTINUITY_THRESHOLDS = {
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
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    parser.add_argument("--frame-id", default="cap-1396")
    parser.add_argument("--window-id", default="window_016")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_cap1396_capture_continuity_acceptance_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_cap1396_capture_continuity_acceptance_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    dataset = args.dataset_dir
    capture = args.capture_dir or dataset / "capture_seq_k35_strict"
    diagnostics = dataset / "diagnostics"
    photo_bundle = read_json(capture / "photo_bundle.json")
    k_windows = read_json(capture / "da3_k_windows.json")
    audits = {
        window_id: read_json(diagnostics / rel_path)
        for window_id, rel_path in DEFAULT_WINDOW_AUDITS.items()
    }

    frames = list(photo_bundle.get("frames", []))
    frame_rows = {str(frame.get("id")): (index, frame) for index, frame in enumerate(frames)}
    if args.frame_id not in frame_rows:
        raise KeyError(f"{args.frame_id} not found in {capture}/photo_bundle.json")
    target_index, target_frame = frame_rows[args.frame_id]
    previous_frame = frames[target_index - 1] if target_index > 0 else None
    next_frame = frames[target_index + 1] if target_index + 1 < len(frames) else None

    step = continuity_step(previous_frame, target_frame, target_index)
    next_step = continuity_step(target_frame, next_frame, target_index + 1) if next_frame else None
    roles = frame_roles(k_windows, args.frame_id)
    window_context = window_downstream_context(k_windows, args.window_id, args.frame_id)
    target_quality = quality_summary(target_frame)
    breach = continuity_breach_summary(step)
    audit_context = pose_depth_context(audits, args.window_id, args.frame_id)
    window_summaries = {
        window_id: summarize_window_audit(report)
        for window_id, report in audits.items()
    }
    decision_status = derive_status(
        roles=roles,
        quality=target_quality,
        breach=breach,
        audit_context=audit_context,
        window_summaries=window_summaries,
    )

    report = {
        "schema_version": "aether_da3_cap1396_capture_continuity_acceptance_audit_v1",
        "date": args.date,
        "decision": {
            "status": decision_status,
            "goal_complete": False,
            "conclusion": (
                "cap-1396 was eligible by still-image quality and official timestamp ordering, "
                "but it violates the existing Dart continuity warning thresholds before entering "
                "window_016 official downstream."
            ),
            "official_replication_boundary": (
                "Official DA3-Streaming image-only chunking does not reject frames by AR/VIO "
                "continuity. A continuity gate is a mobile capture/product adaptation, not an "
                "official model-input requirement."
            ),
            "next_best_action": (
                "Add or simulate a Dart-side capture continuity quarantine for high-risk saved "
                "frames, then re-run DA3BASE_476x742_N35 on the same capture without using big-memory "
                "image-only export as the product gate."
            ),
        },
        "inputs": {
            "dataset_dir": str(dataset),
            "capture_dir": str(capture),
            "photo_bundle": str(capture / "photo_bundle.json"),
            "k_windows": str(capture / "da3_k_windows.json"),
            "window_audits": {
                window_id: str(diagnostics / rel_path)
                for window_id, rel_path in DEFAULT_WINDOW_AUDITS.items()
            },
        },
        "thresholds": CONTINUITY_THRESHOLDS,
        "target_frame": {
            "frame_id": args.frame_id,
            "manifest_index": target_index,
            "metadata": compact_frame(target_frame),
            "quality": target_quality,
            "window_roles": roles,
            "window_downstream_context": window_context,
        },
        "adjacent_continuity": {
            "previous_to_target": step,
            "target_to_next": next_step,
            "breach_summary": breach,
        },
        "pose_depth_context": audit_context,
        "window_summaries": window_summaries,
        "code_path_findings": [
            {
                "path": "lib/capture/dome/dome_target_points.dart",
                "finding": (
                    "Hard rejects cover image sharpness, ROI sharpness, subject focus, focus/exposure "
                    "stability, live radius outlier, angular velocity, brightness, and elevation; no "
                    "previous-retained-frame dt/translation/elevation-delta hard gate is present."
                ),
            },
            {
                "path": "lib/capture/dome/ring_buffer_cell.dart",
                "finding": (
                    "Diversity eviction includes timestamp distance in the novelty metric, so a long "
                    "pause can make a frame more retainable instead of less retainable."
                ),
            },
            {
                "path": "packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart",
                "finding": (
                    "The official DA3 window plan records continuityAudit warnings but does not filter "
                    "official timestamp-ordered chunks by those warnings."
                ),
            },
        ],
        "plain_language": plain_language(args.frame_id, step, breach, target_quality, audit_context),
    }
    return report


def derive_status(
    *,
    roles: list[dict[str, Any]],
    quality: dict[str, Any],
    breach: dict[str, Any],
    audit_context: dict[str, Any],
    window_summaries: dict[str, dict[str, Any]],
) -> str:
    in_official_downstream = any(role.get("officialDownstream") for role in roles)
    quality_pass = bool(quality.get("accepted")) and float_or_zero(quality.get("kWindowWeight")) >= 0.5
    continuity_bad = bool(breach.get("violated"))
    target_seen_in_growth = bool(audit_context.get("target_slot"))
    window016_thick = float_or_zero(
        window_summaries.get("window_016", {}).get("npz_minor_ratio_vs_k10")
    ) >= 1.10
    window017_not_thick = float_or_zero(
        window_summaries.get("window_017", {}).get("npz_minor_ratio_vs_k10")
    ) < 1.10
    if (
        in_official_downstream
        and quality_pass
        and continuity_bad
        and target_seen_in_growth
        and window016_thick
        and window017_not_thick
    ):
        return "cap1396_quality_accepted_but_continuity_breach_primary_suspect"
    if in_official_downstream and continuity_bad:
        return "cap1396_official_downstream_continuity_breach"
    return "cap1396_acceptance_attribution_incomplete"


def continuity_step(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
    current_index: int,
) -> dict[str, Any] | None:
    if previous is None or current is None:
        return None
    previous_center = camera_center(previous)
    current_center = camera_center(current)
    translation = None
    if previous_center is not None and current_center is not None:
        translation = math.sqrt(
            sum((current_center[i] - previous_center[i]) ** 2 for i in range(3))
        )
    timestamp_delta = nullable_delta(current.get("timestamp"), previous.get("timestamp"))
    azimuth_delta = angle_abs_delta(as_float(previous.get("azimuth")), as_float(current.get("azimuth")))
    elevation_delta = nullable_abs_delta(
        as_float(previous.get("elevation")),
        as_float(current.get("elevation")),
    )
    radius_delta = nullable_abs_delta(
        as_float(previous.get("cameraRadiusM")),
        as_float(current.get("cameraRadiusM")),
    )
    q = quality_summary(current)
    high_risk = (
        (timestamp_delta is not None and timestamp_delta > CONTINUITY_THRESHOLDS["timestampDeltaSecondsWarningGt"])
        or (translation is not None and translation > CONTINUITY_THRESHOLDS["translationStepMWarningGt"])
        or (azimuth_delta is not None and azimuth_delta > CONTINUITY_THRESHOLDS["azimuthDeltaRadWarningGt"])
        or (elevation_delta is not None and elevation_delta > CONTINUITY_THRESHOLDS["elevationDeltaRadWarningGt"])
        or float_or_zero(q.get("kWindowWeight")) < CONTINUITY_THRESHOLDS["qualityScoreWarningLt"]
    )
    return {
        "fromFrameID": previous.get("id"),
        "toFrameID": current.get("id"),
        "toManifestIndex": current_index,
        "timestampDeltaSeconds": timestamp_delta,
        "translationStepM": translation,
        "azimuthDeltaRad": azimuth_delta,
        "elevationDeltaRad": elevation_delta,
        "radiusDeltaM": radius_delta,
        "toQualityScore": q.get("score"),
        "toKWindowWeight": q.get("kWindowWeight"),
        "highRisk": high_risk,
        "fromMetadata": compact_frame(previous),
        "toMetadata": compact_frame(current),
    }


def continuity_breach_summary(step: dict[str, Any] | None) -> dict[str, Any]:
    if step is None:
        return {"violated": False, "violations": []}
    checks = [
        (
            "timestampDeltaSeconds",
            ">",
            CONTINUITY_THRESHOLDS["timestampDeltaSecondsWarningGt"],
            step.get("timestampDeltaSeconds"),
        ),
        (
            "translationStepM",
            ">",
            CONTINUITY_THRESHOLDS["translationStepMWarningGt"],
            step.get("translationStepM"),
        ),
        (
            "azimuthDeltaRad",
            ">",
            CONTINUITY_THRESHOLDS["azimuthDeltaRadWarningGt"],
            step.get("azimuthDeltaRad"),
        ),
        (
            "elevationDeltaRad",
            ">",
            CONTINUITY_THRESHOLDS["elevationDeltaRadWarningGt"],
            step.get("elevationDeltaRad"),
        ),
        (
            "toKWindowWeight",
            "<",
            CONTINUITY_THRESHOLDS["qualityScoreWarningLt"],
            step.get("toKWindowWeight"),
        ),
    ]
    violations = []
    for key, op, threshold, value in checks:
        if value is None:
            continue
        value_float = float(value)
        violated = value_float > threshold if op == ">" else value_float < threshold
        if violated:
            violations.append({"metric": key, "op": op, "threshold": threshold, "value": value_float})
    return {
        "violated": bool(violations),
        "violation_count": len(violations),
        "violations": violations,
        "quality_passed_despite_continuity": float_or_zero(step.get("toKWindowWeight")) >= 0.5,
    }


def pose_depth_context(
    audits: dict[str, dict[str, Any]],
    window_id: str,
    frame_id: str,
) -> dict[str, Any]:
    audit = audits.get(window_id, {})
    target_row = None
    for row in audit.get("per_slot", []):
        if str(row.get("frame_id")) == frame_id:
            target_row = row
            break
    if not target_row:
        return {"target_slot": None, "growth_rows": []}
    slot = int(target_row.get("slot", 0))
    cumulative = audit.get("cumulative", [])
    wanted_k = [max(1, slot), slot + 1, slot + 2, slot + 3]
    rows = []
    for k in wanted_k:
        if k <= 0 or k > len(cumulative):
            continue
        item = cumulative[k - 1]
        npz = item.get("npz_streaming_style", {})
        rows.append(
            {
                "k": item.get("k"),
                "last_frame_id": (item.get("frame_ids") or [None])[-1],
                "pose_diag": get_path(item, "pose.camera_center_diag"),
                "npz_bbox_diag_p01_p99": npz.get("bbox_diag_p01_p99"),
                "npz_pca_minor_extent": npz.get("pca_minor_extent"),
                "depth_p95": get_path(item, "depth.p95"),
                "confidence_median": get_path(item, "confidence.median"),
            }
        )
    return {
        "window_id": window_id,
        "target_slot": {
            "slot": target_row.get("slot"),
            "frame_index": target_row.get("frame_index"),
            "step_from_previous": target_row.get("step_from_previous"),
            "cumulative_pose_diag": target_row.get("cumulative_pose_diag"),
            "depth_p95": get_path(target_row, "depth.p95"),
            "confidence_median": get_path(target_row, "confidence.median"),
        },
        "growth_rows_around_target": rows,
    }


def summarize_window_audit(report: dict[str, Any]) -> dict[str, Any]:
    scope = report.get("scope", {})
    npz = get_path(report, "summary.styles.npz_streaming_style.k35_over_k10") or {}
    glb = get_path(report, "summary.styles.glb_style.k35_over_k10") or {}
    pose = report.get("summary", {}).get("pose", {})
    depth = report.get("summary", {}).get("depth", {})
    return {
        "frame_source": scope.get("frame_source"),
        "frame_count": scope.get("frame_count"),
        "pose_scale": scope.get("pose_scale"),
        "npz_bbox_ratio_vs_k10": npz.get("bbox_ratio_vs_k10"),
        "npz_minor_ratio_vs_k10": npz.get("minor_ratio_vs_k10"),
        "glb_bbox_ratio_vs_k10": glb.get("bbox_ratio_vs_k10"),
        "glb_minor_ratio_vs_k10": glb.get("minor_ratio_vs_k10"),
        "pose_diag_ratio_vs_k10": pose.get("k35_over_k10_pose_diag"),
        "largest_pose_step": pose.get("largest_step"),
        "depth_p95_ratio_vs_k10": depth.get("k35_over_k10_p95"),
    }


def window_downstream_context(
    k_windows: dict[str, Any],
    window_id: str,
    frame_id: str,
) -> dict[str, Any]:
    for window in k_windows.get("windows", []):
        if str(window.get("id")) != window_id:
            continue
        saved = [str(value) for value in window.get("officialSaveFrameIDs", [])]
        chunk = [str(value) for value in window.get("officialChunkFrameIDs", [])]
        if frame_id not in saved:
            return {
                "windowID": window_id,
                "officialDownstream": False,
                "officialSaveFrameCount": len(saved),
            }
        save_index = saved.index(frame_id)
        local_index = chunk.index(frame_id) if frame_id in chunk else None
        return {
            "windowID": window_id,
            "officialDownstream": True,
            "officialSaveFrameCount": len(saved),
            "saveIndex": save_index,
            "localChunkIndex": local_index,
            "previousOfficialSaveFrameID": saved[save_index - 1] if save_index > 0 else None,
            "nextOfficialSaveFrameID": saved[save_index + 1] if save_index + 1 < len(saved) else None,
            "officialSaveFrameIDs": saved,
        }
    return {"windowID": window_id, "officialDownstream": False}


def frame_roles(k_windows: dict[str, Any], frame_id: str) -> list[dict[str, Any]]:
    roles = []
    for window in k_windows.get("windows", []):
        frame_ids = [str(value) for value in window.get("frameIDs", [])]
        chunk_ids = [str(value) for value in window.get("officialChunkFrameIDs", [])]
        if frame_id not in set(frame_ids) | set(chunk_ids):
            continue
        official = set(str(value) for value in window.get("officialSaveFrameIDs", []))
        withheld = set(str(value) for value in window.get("withheldForNextOverlapFrameIDs", []))
        bridge = set(str(value) for value in window.get("bridgeFrameIDs", []))
        core = set(str(value) for value in window.get("coreFrameIDs", []))
        roles.append(
            {
                "windowID": window.get("id"),
                "localSlot": frame_ids.index(frame_id) if frame_id in frame_ids else None,
                "officialChunkSlot": chunk_ids.index(frame_id) if frame_id in chunk_ids else None,
                "officialDownstream": frame_id in official,
                "withheldForNextOverlap": frame_id in withheld,
                "bridgeFrame": frame_id in bridge,
                "coreFrame": frame_id in core,
            }
        )
    return roles


def compact_frame(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": frame.get("id"),
        "timestamp": frame.get("timestamp"),
        "azimuth": frame.get("azimuth"),
        "elevation": frame.get("elevation"),
        "cameraRadiusM": frame.get("cameraRadiusM"),
        "poseSource": frame.get("poseSource"),
        "trackingState": frame.get("trackingState"),
        "quality": quality_summary(frame),
    }


def quality_summary(frame: dict[str, Any]) -> dict[str, Any]:
    quality = frame.get("quality") if isinstance(frame, dict) else {}
    if not isinstance(quality, dict):
        quality = {}
    downstream = quality.get("downstreamWeights")
    if not isinstance(downstream, dict):
        downstream = {}
    k_weight = first_positive(
        quality.get("kWindowWeight"),
        downstream.get("kWindow"),
        quality.get("score"),
    )
    return {
        "accepted": quality.get("accepted"),
        "score": quality.get("score"),
        "kWindowWeight": k_weight,
        "laplacianVariance": quality.get("laplacianVariance"),
        "meanLuma": quality.get("meanLuma"),
        "rejectReasons": quality.get("rejectReasons") or [],
    }


def first_positive(*values: Any) -> float:
    for value in values:
        parsed = as_float(value)
        if parsed is not None and parsed > 0:
            return parsed
    return 0.0


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


def plain_language(
    frame_id: str,
    step: dict[str, Any] | None,
    breach: dict[str, Any],
    quality: dict[str, Any],
    audit_context: dict[str, Any],
) -> list[str]:
    if step is None:
        return [f"{frame_id} cannot be compared with a previous manifest frame."]
    violations = ", ".join(
        f"{item['metric']}={item['value']:.3f} {item['op']} {item['threshold']:.3f}"
        for item in breach.get("violations", [])
    )
    target_slot = audit_context.get("target_slot") or {}
    return [
        f"{frame_id} 不是因为模糊或曝光差进来的；它的 accepted={quality.get('accepted')}，kWindowWeight 约 {float_or_zero(quality.get('kWindowWeight')):.3f}。",
        f"真正危险的是上一张到它的连续性：{step.get('fromFrameID')} -> {step.get('toFrameID')}，dt={float_or_zero(step.get('timestampDeltaSeconds')):.3f}s，translation={float_or_zero(step.get('translationStepM')):.3f}m，elevation jump={float_or_zero(step.get('elevationDeltaRad')):.3f}rad。",
        f"它违反的连续性阈值是：{violations or 'none'}。",
        f"在 window_016 official downstream 审计里，它位于 slot {target_slot.get('slot')}，加入后 cumulative pose diag 到 {float_or_zero(target_slot.get('cumulative_pose_diag')):.3f}。",
        "所以现在的判断不是 DA3 downstream merge 漏了去重，而是移动端采集/保留策略允许了一个画质可用但运动连续性差的帧进入单个 K35 window。",
    ]


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "target_frame": {
            "frame_id": report["target_frame"]["frame_id"],
            "manifest_index": report["target_frame"]["manifest_index"],
            "quality": report["target_frame"]["quality"],
            "window_roles": report["target_frame"]["window_roles"],
        },
        "adjacent_continuity": report["adjacent_continuity"]["breach_summary"],
        "pose_depth_context": report["pose_depth_context"],
    }


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


def float_or_zero(value: Any) -> float:
    parsed = as_float(value)
    return 0.0 if parsed is None else parsed


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    step = report["adjacent_continuity"]["previous_to_target"] or {}
    breach = report["adjacent_continuity"]["breach_summary"]
    target = report["target_frame"]
    ctx = report["pose_depth_context"]
    lines = [
        "# DA3 cap-1396 capture continuity acceptance audit",
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
        report["decision"]["official_replication_boundary"],
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
            "## Target Frame",
            "",
            "| field | value |",
            "|---|---:|",
            f"| frame | `{target['frame_id']}` |",
            f"| manifest index | {target['manifest_index']} |",
            f"| accepted | `{target['quality'].get('accepted')}` |",
            f"| quality score | {float_or_zero(target['quality'].get('score')):.3f} |",
            f"| kWindowWeight | {float_or_zero(target['quality'].get('kWindowWeight')):.3f} |",
            f"| timestamp delta | {float_or_zero(step.get('timestampDeltaSeconds')):.3f}s |",
            f"| translation step | {float_or_zero(step.get('translationStepM')):.3f}m |",
            f"| azimuth delta | {float_or_zero(step.get('azimuthDeltaRad')):.3f}rad |",
            f"| elevation delta | {float_or_zero(step.get('elevationDeltaRad')):.3f}rad |",
            f"| high risk | `{step.get('highRisk')}` |",
            "",
            "## Violations",
            "",
            "| metric | value | threshold |",
            "|---|---:|---:|",
        ]
    )
    for item in breach.get("violations", []):
        lines.append(
            f"| `{item['metric']}` | {float(item['value']):.3f} | {item['op']} {float(item['threshold']):.3f} |"
        )
    if not breach.get("violations"):
        lines.append("| none | 0 | 0 |")
    lines.extend(
        [
            "",
            "## Pose/Depth Growth Around Target",
            "",
            "| k | last frame | pose diag | npz bbox diag | npz minor extent | depth p95 | conf median |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in ctx.get("growth_rows_around_target", []):
        lines.append(
            "| {k} | `{last}` | {pose:.3f} | {bbox:.3f} | {minor:.3f} | {depth:.3f} | {conf:.3f} |".format(
                k=row.get("k"),
                last=row.get("last_frame_id"),
                pose=float_or_zero(row.get("pose_diag")),
                bbox=float_or_zero(row.get("npz_bbox_diag_p01_p99")),
                minor=float_or_zero(row.get("npz_pca_minor_extent")),
                depth=float_or_zero(row.get("depth_p95")),
                conf=float_or_zero(row.get("confidence_median")),
            )
        )
    lines.extend(
        [
            "",
            "## Code Path Findings",
            "",
        ]
    )
    for item in report["code_path_findings"]:
        lines.append(f"- `{item['path']}`: {item['finding']}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
