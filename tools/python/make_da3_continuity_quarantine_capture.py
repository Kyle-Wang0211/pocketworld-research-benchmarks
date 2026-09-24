#!/usr/bin/env python3
"""Create research-only DA3 K35 capture manifests for continuity quarantine reruns.

The output directory contains copied JSON manifests only. Image files remain in
the source capture and should be provided to da3_mac_window_export.py through
--image-root.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
THRESHOLDS = {
    "timestampDeltaSecondsWarningGt": 2.0,
    "translationStepMWarningGt": 0.25,
    "azimuthDeltaRadWarningGt": 0.35,
    "elevationDeltaRadWarningGt": 0.25,
    "qualityScoreWarningLt": 0.5,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-capture-dir",
        type=Path,
        default=DEFAULT_DATASET / "capture_seq_k35_strict",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--source-window-id", default="window_016")
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = create_capture(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def create_capture(args: argparse.Namespace) -> dict[str, Any]:
    src = args.source_capture_dir
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    for filename in ("photo_bundle.json", "da3_input_manifest.json", "model_policy.json", "view_graph.json"):
        source = src / filename
        if source.exists():
            shutil.copyfile(source, out / filename)

    photo_bundle = read_json(src / "photo_bundle.json")
    source_k = read_json(src / "da3_k_windows.json")
    source_window = find_window(source_k, args.source_window_id)
    official_ids = [str(value) for value in source_window.get("officialSaveFrameIDs", [])]
    if not official_ids:
        official_ids = [str(value) for value in source_window.get("downstreamFrameIDs", [])]
    if not official_ids:
        raise ValueError(f"{args.source_window_id} has no official downstream frame ids")

    quarantine_plan_path = src / "da3_k_windows_continuity_quarantine.json"
    if quarantine_plan_path.exists():
        quarantine_plan = read_json(quarantine_plan_path)
        source_summary = find_risky_source_window(quarantine_plan, args.source_window_id)
        continuity_rows = list(source_summary.get("continuitySteps") or [])
        high_risk_ids = [str(value) for value in source_summary.get("highRiskFrameIDs", [])]
        windows = [
            dict(window)
            for window in quarantine_plan.get("windows", [])
            if str(window.get("sourceWindowID")) == args.source_window_id
        ]
        if not windows:
            raise ValueError(f"{quarantine_plan_path} has no variants for {args.source_window_id}")
        variants = [
            {
                "id": str(window.get("id")),
                "frame_ids": [str(value) for value in window.get("downstreamFrameIDs", [])],
                "removed_frame_ids": [str(value) for value in window.get("removedFrameIDs", [])],
            }
            for window in windows
        ]
    else:
        continuity_rows = continuity_for_frame_ids(photo_bundle, official_ids)
        high_risk_ids = [
            str(row["toFrameID"])
            for row in continuity_rows
            if row["highRisk"] and str(row["toFrameID"]) in official_ids
        ]
        first_break_id = high_risk_ids[0] if high_risk_ids else None
        first_break_slot = official_ids.index(first_break_id) if first_break_id in official_ids else None
        variants = build_variants(args.source_window_id, official_ids, high_risk_ids, first_break_slot)
        windows = [
            build_window(
                variant=variant,
                source_window=source_window,
                source_window_id=args.source_window_id,
                window_size=int(source_k.get("windowSize") or 35),
            )
            for variant in variants
        ]
    k_windows = {
        **source_k,
        "sourceCaptureDir": str(src),
        "schemaVersion": source_k.get("schemaVersion", "aether_da3_k_windows_v1"),
        "windowingPolicy": {
            **dict(source_k.get("windowingPolicy") or {}),
            "kind": "research_continuity_quarantine_counterfactual_v1",
            "policy": "official_k35_runtime_with_continuity_quarantine_variants",
            "officialReplicationBoundary": (
                "Research-only product adaptation candidate. Official source window is preserved in sourceCaptureDir; "
                "these windows keep DA3 N35 runtime shape but alter which real frames are fed before padding."
            ),
        },
        "windows": windows,
        "bridgeGraph": [],
        "loopCandidates": [],
        "uncoveredFrameIDs": [],
        "variantReport": {
            "schema_version": "aether_da3_continuity_quarantine_capture_v1",
            "date": args.date,
            "source_window_id": args.source_window_id,
            "source_official_downstream_frame_ids": official_ids,
            "high_risk_frame_ids": high_risk_ids,
            "continuity_rows": continuity_rows,
            "variants": [
                {
                    "id": variant["id"],
                    "frame_ids": variant["frame_ids"],
                    "removed_frame_ids": variant["removed_frame_ids"],
                }
                for variant in variants
            ],
        },
    }
    write_json(out / "da3_k_windows.json", k_windows)
    write_json(out / "continuity_quarantine_capture_report.json", k_windows["variantReport"])
    write_markdown(out / "continuity_quarantine_capture_report_zh.md", k_windows)
    return {
        "status": "created",
        "out_dir": str(out),
        "window_ids": [window["id"] for window in windows],
        "high_risk_frame_ids": high_risk_ids,
    }


def build_variants(
    source_window_id: str,
    official_ids: list[str],
    high_risk_ids: list[str],
    first_break_slot: int | None,
) -> list[dict[str, Any]]:
    variants = []
    if first_break_slot is not None and first_break_slot > 0:
        variants.append(
            {
                "id": f"{source_window_id}_prefix_before_first_break",
                "description": "True rerun candidate: only frames before the first high-risk continuity break, padded to N35.",
                "frame_ids": official_ids[:first_break_slot],
                "removed_frame_ids": official_ids[first_break_slot:],
            }
        )
        variants.append(
            {
                "id": f"{source_window_id}_segment_from_first_break",
                "description": "True rerun candidate: only the segment starting at the first high-risk continuity break, padded to N35.",
                "frame_ids": official_ids[first_break_slot:],
                "removed_frame_ids": official_ids[:first_break_slot],
            }
        )
    if high_risk_ids:
        risk = set(high_risk_ids)
        kept = [frame_id for frame_id in official_ids if frame_id not in risk]
        if kept:
            variants.append(
                {
                    "id": f"{source_window_id}_drop_all_high_risk_targets",
                    "description": "True rerun candidate: official downstream frames except all current high-risk continuity targets, padded to N35.",
                    "frame_ids": kept,
                    "removed_frame_ids": high_risk_ids,
                }
            )
    return variants


def build_window(
    *,
    variant: dict[str, Any],
    source_window: dict[str, Any],
    source_window_id: str,
    window_size: int,
) -> dict[str, Any]:
    real_ids = list(variant["frame_ids"])
    if not real_ids:
        raise ValueError(f"{variant['id']} has no frames")
    padding_count = max(0, window_size - len(real_ids))
    runtime_ids = real_ids + [real_ids[-1]] * padding_count
    if len(runtime_ids) != window_size:
        raise ValueError(f"{variant['id']} runtime length is {len(runtime_ids)}, expected {window_size}")
    return {
        "id": variant["id"],
        "sourceWindowID": source_window_id,
        "selectionMode": "research_continuity_quarantine_counterfactual",
        "modelTag": source_window.get("modelTag"),
        "modelResourceName": source_window.get("modelResourceName"),
        "frameIDs": runtime_ids,
        "officialChunkFrameIDs": real_ids,
        "officialSaveLocalIndices": list(range(len(real_ids))),
        "officialSaveFrameIDs": real_ids,
        "downstreamFrameIDs": real_ids,
        "uniqueFrameIDs": list(dict.fromkeys(real_ids)),
        "coreFrameIDs": real_ids,
        "bridgeFrameIDs": [],
        "withheldForNextOverlapFrameIDs": [],
        "runtimePaddingFrameIDs": [real_ids[-1]] * padding_count,
        "seedFrameID": real_ids[0],
        "frameCount": len(runtime_ids),
        "realFrameCount": len(real_ids),
        "officialChunkFrameCount": len(real_ids),
        "uniqueFrameCount": len(set(real_ids)),
        "coreFrameCount": len(real_ids),
        "bridgeFrameCount": 0,
        "officialSaveFrameCount": len(real_ids),
        "runtimePaddingFrameCount": padding_count,
        "chunkStartIndex": None,
        "chunkEndIndexExclusive": None,
        "bridgeTargetFrameCount": 0,
        "bridgeRule": "none_research_quarantine_variant",
        "officialDownstreamRule": "DA3 N35 runtime padded; downstream keeps only real quarantine frames",
        "paddedToWindowSize": padding_count > 0,
        "variantDescription": variant["description"],
        "removedFrameIDs": variant["removed_frame_ids"],
        "inputHeight": source_window.get("inputHeight"),
        "inputWidth": source_window.get("inputWidth"),
    }


def find_window(k_windows: dict[str, Any], window_id: str) -> dict[str, Any]:
    for window in k_windows.get("windows", []):
        if str(window.get("id")) == window_id:
            return window
    raise KeyError(window_id)


def find_risky_source_window(k_windows: dict[str, Any], window_id: str) -> dict[str, Any]:
    for window in k_windows.get("riskySourceWindows", []):
        if str(window.get("sourceWindowID")) == window_id:
            return window
    raise KeyError(window_id)


def continuity_for_frame_ids(
    photo_bundle: dict[str, Any],
    selected_frame_ids: list[str],
) -> list[dict[str, Any]]:
    frames = photo_bundle.get("frames", [])
    by_id = {str(frame.get("id")): (index, frame) for index, frame in enumerate(frames)}
    rows = []
    for frame_id in selected_frame_ids:
        if frame_id not in by_id:
            continue
        index, frame = by_id[frame_id]
        if index <= 0:
            continue
        rows.append(continuity_step(frames[index - 1], frame, index))
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
    violations = continuity_violations(
        timestamp_delta=timestamp_delta,
        translation=translation,
        azimuth_delta=azimuth_delta,
        elevation_delta=elevation_delta,
        quality=quality,
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
        "highRisk": bool(violations),
        "violations": violations,
    }


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


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, k_windows: dict[str, Any]) -> None:
    report = k_windows["variantReport"]
    lines = [
        "# DA3 continuity quarantine capture manifest",
        "",
        f"日期：{report['date']}",
        "",
        "## 说明",
        "",
        "这是研究用 custom capture manifest，不替代官方复刻分支。它保持 DA3 N35 runtime shape，真实帧不足时重复最后一帧 padding；postprocess 用 `realFrameCount` 只对真实帧做 Umeyama scale。",
        "",
        "## High-Risk Frames",
        "",
        ", ".join(f"`{frame_id}`" for frame_id in report["high_risk_frame_ids"]) or "none",
        "",
        "## Variants",
        "",
        "| window | frames | removed |",
        "|---|---:|---|",
    ]
    for item in report["variants"]:
        lines.append(
            "| `{id}` | {count} | {removed} |".format(
                id=item["id"],
                count=len(item["frame_ids"]),
                removed=", ".join(f"`{frame_id}`" for frame_id in item["removed_frame_ids"]) or "none",
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
