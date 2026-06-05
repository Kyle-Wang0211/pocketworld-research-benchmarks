#!/usr/bin/env python3
"""Audit Dart official-window continuity-risk metadata for DA3 image-only input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
CAPTURE_DIR_NAME = "capture_seq_k35_strict"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    parser.add_argument("--window-id", default="window_016")
    parser.add_argument("--expected-first-risk-frame-id", default="cap-1396")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        args.out_dir / "official_da3_dart_input_continuity_risk_contract_audit.json",
        report,
    )
    write_markdown(
        args.out_dir / "official_da3_dart_input_continuity_risk_contract_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    capture_dir = args.dataset_dir / CAPTURE_DIR_NAME
    official_path = capture_dir / "da3_k_windows.json"
    quarantine_path = capture_dir / "da3_k_windows_continuity_quarantine.json"
    official = read_json(official_path)
    quarantine = read_json(quarantine_path)
    window = window_by_id(official, args.window_id)
    risk = as_dict(window.get("da3ImageOnlyInputContinuityRisk"))
    save_audit = as_dict(window.get("officialSaveContinuityAudit"))
    full_audit = as_dict(window.get("continuityAudit"))

    save_frames = list_of_str(window.get("officialSaveFrameIDs"))
    downstream_frames = list_of_str(window.get("downstreamFrameIDs"))
    first_high_risk = first_dict(full_audit.get("highRiskSteps"))
    expected_first = args.expected_first_risk_frame_id

    checks: list[dict[str, Any]] = []
    add_check(
        checks,
        "official_plan_schema_unchanged",
        official.get("schemaVersion") == "aether_da3_k_windows_v1"
        and get_path(official, "windowingPolicy.officialStreamingDefaultMatch") is True
        and official.get("windowCount") == 24,
        "da3_k_windows.json is still the strict official timestamp sliding-window plan.",
    )
    add_check(
        checks,
        "risk_schema_present",
        risk.get("schemaVersion") == "aether_da3_image_only_input_continuity_risk_v1",
        "Official windows expose a DA3 image-only input continuity-risk contract.",
    )
    add_check(
        checks,
        "risk_warns_on_window016",
        risk.get("status") == "warning",
        f"{args.window_id} carries warning status for saved-frame continuity risk.",
    )
    add_check(
        checks,
        "official_frame_set_preserved",
        risk.get("officialPlanFrameSetPreserved") is True
        and save_frames == downstream_frames
        and len(save_frames) == int(window.get("officialSaveFrameCount") or 0),
        "The risk metadata does not alter officialSaveFrameIDs/downstreamFrameIDs.",
    )
    add_check(
        checks,
        "first_saved_risk_is_expected_frame",
        risk.get("firstOfficialSaveHighRiskFrameID") == expected_first
        and expected_first in list_of_str(risk.get("officialSaveHighRiskTargetFrameIDs")),
        f"The first saved high-risk target is {expected_first}.",
    )
    add_check(
        checks,
        "expected_frame_is_official_saved_core_frame",
        expected_first in save_frames and save_frames.index(expected_first) == 10,
        f"{expected_first} is an official saved frame at local index 10, not only a withheld tail frame.",
    )
    add_check(
        checks,
        "continuity_audit_exposes_break_metrics",
        first_high_risk.get("toFrameID") == expected_first
        and float_or_nan(first_high_risk.get("timestampDeltaSeconds")) > 2.0
        and float_or_nan(first_high_risk.get("translationStepM")) > 0.25
        and float_or_nan(first_high_risk.get("elevationDeltaRad")) > 0.25,
        "The first high-risk step exceeds timestamp, translation, and elevation thresholds.",
    )
    add_check(
        checks,
        "quarantine_plan_remains_separate",
        quarantine.get("schemaVersion") == "aether_da3_continuity_quarantine_windows_v1"
        and get_path(quarantine, "windowingPolicy.officialStreamingDefaultMatch") is False
        and quarantine_path.name != official_path.name,
        "Continuity quarantine remains a separate research/product-candidate file.",
    )

    required_checks_pass = all(item["status"] == "pass" for item in checks)
    status = (
        "dart_official_window_plan_flags_image_only_input_continuity_risk_without_changing_official_frames"
        if required_checks_pass
        else "dart_official_window_plan_continuity_risk_contract_mismatch"
    )

    return {
        "schema_version": "aether_da3_dart_input_continuity_risk_contract_audit_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "product_ready": False,
            "conclusion": (
                f"Dart now labels {args.window_id} as a DA3 image-only input continuity-risk window, "
                f"with {expected_first} as the first saved high-risk target, while preserving the official "
                "timestamp streaming frame set."
            ),
            "boundary": (
                "This is not a downstream point-cloud cleanup and it is not a replacement for official DA3 parity. "
                "It is metadata that makes the upstream input-risk visible before a product/research split policy is applied."
            ),
            "next_best_action": (
                "Use this field as the Dart-side hard signal for product-candidate window split/quarantine experiments, "
                "and keep official da3_k_windows.json as the immutable parity baseline."
            ),
        },
        "inputs": {
            "dataset_dir": str(args.dataset_dir),
            "official_window_plan": str(official_path),
            "continuity_quarantine_window_plan": str(quarantine_path),
        },
        "metrics": {
            "official_window_count": official.get("windowCount"),
            "quarantine_window_count": quarantine.get("windowCount"),
            "risky_source_window_count": quarantine.get("riskySourceWindowCount"),
            "audited_window_id": args.window_id,
            "official_save_frame_count": len(save_frames),
            "official_save_high_risk_step_count": risk.get("officialSaveHighRiskStepCount"),
            "chunk_high_risk_step_count": risk.get("chunkHighRiskStepCount"),
            "first_official_save_high_risk_frame_id": risk.get("firstOfficialSaveHighRiskFrameID"),
        },
        "window": {
            "id": window.get("id"),
            "frame_count": window.get("frameCount"),
            "official_save_frame_ids": save_frames,
            "downstream_frame_ids": downstream_frames,
            "risk": risk,
            "official_save_continuity_audit": save_audit,
            "first_high_risk_step": first_high_risk,
        },
        "checks": checks,
        "plain_language": plain_language(args.window_id, expected_first, risk, first_high_risk),
    }


def plain_language(
    window_id: str,
    expected_first: str,
    risk: dict[str, Any],
    first_high_risk: dict[str, Any],
) -> list[str]:
    return [
        f"{window_id} 的官方 downstream 帧集没有被改；Dart 只是新增了输入连续性风险字段。",
        (
            f"第一个 official-save high-risk target 是 {expected_first}；它在官方保存帧里，"
            "不是 withheld overlap 尾巴里才出现的帧。"
        ),
        (
            f"第一处断点是 {first_high_risk.get('fromFrameID')} -> {first_high_risk.get('toFrameID')}："
            f"dt={float_or_nan(first_high_risk.get('timestampDeltaSeconds')):.3f}s，"
            f"translation={float_or_nan(first_high_risk.get('translationStepM')):.3f}m，"
            f"elevation={float_or_nan(first_high_risk.get('elevationDeltaRad')):.3f}rad。"
        ),
        (
            f"official-save high-risk step count={risk.get('officialSaveHighRiskStepCount')}，"
            f"full chunk high-risk step count={risk.get('chunkHighRiskStepCount')}。"
        ),
        "结论：厚层的第一嫌疑不是点云导出，而是官方 image-only 输入窗口里混入几何连续性断点后，上游 pose/depth 一致性开始漂。",
    ]


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, evidence: str) -> None:
    checks.append({"id": check_id, "status": "pass" if passed else "fail", "evidence": evidence})


def window_by_id(report: dict[str, Any], window_id: str) -> dict[str, Any]:
    for item in report.get("windows", []):
        if isinstance(item, dict) and item.get("id") == window_id:
            return item
    return {}


def first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def float_or_nan(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def get_path(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 Dart input continuity-risk contract audit",
        "",
        f"- 日期：{report['date']}",
        f"- 状态：`{get_path(report, 'decision.status')}`",
        f"- 结论：{get_path(report, 'decision.conclusion')}",
        f"- 边界：{get_path(report, 'decision.boundary')}",
        "",
        "## 大白话",
        "",
    ]
    lines.extend(f"- {item}" for item in report["plain_language"])
    lines.extend(
        [
            "",
            "## 核心指标",
            "",
        ]
    )
    metrics = report["metrics"]
    for key, value in metrics.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | status | evidence |",
            "| --- | --- | --- |",
        ]
    )
    for check in report["checks"]:
        lines.append(f"| `{check['id']}` | `{check['status']}` | {check['evidence']} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "metrics": report["metrics"],
        "failed_checks": [item for item in report["checks"] if item["status"] != "pass"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
