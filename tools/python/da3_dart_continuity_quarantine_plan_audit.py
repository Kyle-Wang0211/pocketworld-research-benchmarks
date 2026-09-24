#!/usr/bin/env python3
"""Validate Dart-generated DA3 continuity-quarantine windows against true reruns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/data/official_da3_base_k35_strict_seq_2026_06_02"
)
CAPTURE_DIR_NAME = "capture_seq_k35_strict"
TRUE_RERUN_REPORT = (
    "official_da3_continuity_quarantine_true_rerun_attribution_2026_06_05/"
    "official_da3_continuity_quarantine_true_rerun_attribution.json"
)
WINDOW016_VARIANTS = {
    "window_016_prefix_before_first_break": "prefix_before_first_break",
    "window_016_segment_from_first_break": "segment_from_first_break",
    "window_016_drop_all_high_risk_targets": "drop_all_high_risk_targets",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_dart_continuity_quarantine_plan_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_dart_continuity_quarantine_plan_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    capture_dir = args.dataset_dir / CAPTURE_DIR_NAME
    official_path = capture_dir / "da3_k_windows.json"
    quarantine_path = capture_dir / "da3_k_windows_continuity_quarantine.json"
    true_rerun_path = args.dataset_dir / "diagnostics" / TRUE_RERUN_REPORT

    official = read_json(official_path)
    quarantine = read_json(quarantine_path)
    true_rerun = read_json(true_rerun_path)

    official_w16 = window_by_id(official, "window_016")
    checks: list[dict[str, Any]] = []
    variants = {
        variant_id: summarize_variant(
            variant_id=variant_id,
            true_key=true_key,
            official_window=official_w16,
            quarantine_window=window_by_id(quarantine, variant_id),
            true_rerun_row=get_path(true_rerun, f"rows.{true_key}") or {},
            checks=checks,
        )
        for variant_id, true_key in WINDOW016_VARIANTS.items()
    }

    add_check(
        checks,
        "official_default_plan_unchanged",
        official.get("schemaVersion") == "aether_da3_k_windows_v1"
        and get_path(official, "windowingPolicy.officialStreamingDefaultMatch") is True
        and official.get("windowCount") == 24,
        "da3_k_windows.json remains the official timestamp sliding-window plan.",
    )
    add_check(
        checks,
        "quarantine_plan_is_separate_research_file",
        quarantine.get("schemaVersion") == "aether_da3_continuity_quarantine_windows_v1"
        and get_path(quarantine, "windowingPolicy.officialStreamingDefaultMatch") is False
        and quarantine_path.name != official_path.name,
        "Continuity quarantine is emitted as a separate research/product-candidate plan.",
    )
    add_check(
        checks,
        "quarantine_plan_scope",
        quarantine.get("windowCount") == 63
        and quarantine.get("riskySourceWindowCount") == 21
        and quarantine.get("sourceOfficialWindowCount") == official.get("windowCount"),
        "Dart generated 63 variants from 24 official windows, with 21 risky source windows.",
    )
    add_check(
        checks,
        "window016_source_downstream_still_official_save",
        official_w16.get("officialSaveFrameIDs") == official_w16.get("downstreamFrameIDs")
        and official_w16.get("officialSaveFrameCount") == 17,
        "Source window_016 downstream remains the official save-frame set.",
    )

    required_checks_pass = all(item["status"] == "pass" for item in checks)
    status = (
        "dart_continuity_quarantine_plan_matches_window016_true_rerun_variants"
        if required_checks_pass
        else "dart_continuity_quarantine_plan_mismatch"
    )

    return {
        "schema_version": "aether_da3_dart_continuity_quarantine_plan_audit_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "product_ready": False,
            "conclusion": (
                "Dart can now generate a separate continuity-quarantine K35 plan whose window_016 variants "
                "match the true CoreML rerun frame sets. This makes the window split/quarantine candidate "
                "portable enough for the APP policy layer, while leaving the official default plan intact."
            ),
            "boundary": (
                "This is not official DA3 image-only parity and it is not enabled as the product gate yet. "
                "It is a research/product adaptation candidate that still needs more windows and captures."
            ),
            "next_best_action": (
                "Run the quarantine plan on additional risky windows/captures, compare thickness deltas, "
                "then decide the smallest Dart-side acceptance gate that avoids single-window discontinuity."
            ),
        },
        "inputs": {
            "dataset_dir": str(args.dataset_dir),
            "official_window_plan": str(official_path),
            "dart_quarantine_window_plan": str(quarantine_path),
            "true_rerun_attribution": str(true_rerun_path),
        },
        "metrics": {
            "official_window_count": official.get("windowCount"),
            "quarantine_window_count": quarantine.get("windowCount"),
            "risky_source_window_count": quarantine.get("riskySourceWindowCount"),
            "window_size": quarantine.get("windowSize"),
            "source_window016_official_save_frame_count": official_w16.get("officialSaveFrameCount"),
        },
        "checks": checks,
        "window016_variants": variants,
        "plain_language": plain_language(variants),
    }


def summarize_variant(
    *,
    variant_id: str,
    true_key: str,
    official_window: dict[str, Any],
    quarantine_window: dict[str, Any],
    true_rerun_row: dict[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    downstream = list(quarantine_window.get("downstreamFrameIDs") or [])
    true_frames = list(true_rerun_row.get("frame_ids") or [])
    real_frame_count = quarantine_window.get("realFrameCount")
    frame_count = quarantine_window.get("frameCount")
    padding = list(quarantine_window.get("runtimePaddingFrameIDs") or [])
    source_downstream = list(official_window.get("downstreamFrameIDs") or [])
    removed_expected = ordered_difference(source_downstream, downstream)
    removed_actual = list(quarantine_window.get("removedFrameIDs") or [])
    pad_expected = max(0, int(frame_count or 0) - int(real_frame_count or 0))

    add_check(
        checks,
        f"{variant_id}_matches_true_rerun_frames",
        downstream == true_frames,
        f"{variant_id} downstream frame set matches true rerun {true_key}.",
    )
    add_check(
        checks,
        f"{variant_id}_preserves_fixed_n35_runtime_shape",
        frame_count == 35
        and real_frame_count == len(downstream)
        and len(padding) == pad_expected
        and (not padding or padding[-1] == downstream[-1]),
        f"{variant_id} keeps CoreML N35 shape through runtime padding only.",
    )
    add_check(
        checks,
        f"{variant_id}_removed_frames_are_source_difference",
        removed_actual == removed_expected,
        f"{variant_id} removedFrameIDs equals source official downstream minus retained downstream.",
    )

    return {
        "id": variant_id,
        "source_window_id": quarantine_window.get("sourceWindowID"),
        "true_rerun_key": true_key,
        "frame_count": frame_count,
        "real_frame_count": real_frame_count,
        "runtime_padding_frame_count": len(padding),
        "downstream_frame_ids": downstream,
        "removed_frame_ids": removed_actual,
        "continuity_status": get_path(quarantine_window, "continuityAudit.status"),
        "high_risk_step_count": get_path(quarantine_window, "continuityAudit.highRiskStepCount"),
        "true_rerun": {
            "frame_count": true_rerun_row.get("frame_count"),
            "npz_minor_abs": true_rerun_row.get("npz_minor_abs"),
            "npz_bbox_abs": true_rerun_row.get("npz_bbox_abs"),
            "npz_minor_ratio_vs_official_save": get_path(
                true_rerun_row, "vs_official_save.npz_minor_ratio"
            ),
            "npz_bbox_ratio_vs_official_save": get_path(
                true_rerun_row, "vs_official_save.npz_bbox_ratio"
            ),
        },
    }


def ordered_difference(source: list[str], retained: list[str]) -> list[str]:
    retained_set = set(retained)
    return [frame_id for frame_id in source if frame_id not in retained_set]


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, evidence: str) -> None:
    checks.append({"id": check_id, "status": "pass" if passed else "fail", "evidence": evidence})


def window_by_id(report: dict[str, Any], window_id: str) -> dict[str, Any]:
    for item in report.get("windows", []):
        if isinstance(item, dict) and item.get("id") == window_id:
            return item
    return {}


def plain_language(variants: dict[str, dict[str, Any]]) -> list[str]:
    prefix = variants["window_016_prefix_before_first_break"]
    segment = variants["window_016_segment_from_first_break"]
    drop = variants["window_016_drop_all_high_risk_targets"]
    return [
        "官方默认 window 文件没有被替换；quarantine 是单独输出的研究/产品候选计划。",
        "Dart 侧已经能把 window_016 拆成断点前、断点后、去掉所有 high-risk targets 三组候选，并保持 CoreML N35 固定输入形状。",
        f"prefix 变体保留 {prefix['real_frame_count']} 帧，true rerun 后 npz minor/orig={ratio_text(prefix)}。",
        f"segment 变体保留 {segment['real_frame_count']} 帧，true rerun 后 npz minor/orig={ratio_text(segment)}。",
        f"drop-high-risk 变体保留 {drop['real_frame_count']} 帧，true rerun 后 npz minor/orig={ratio_text(drop)}。",
        "这说明当前最实际的产品方向是 Dart 侧 continuity gate/window split，而不是追 89GiB image-only 导出或 downstream 点云去重。",
    ]


def ratio_text(variant: dict[str, Any]) -> str:
    value = get_path(variant, "true_rerun.npz_minor_ratio_vs_official_save")
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "metrics": report["metrics"],
        "failed_checks": [item for item in report["checks"] if item["status"] != "pass"],
        "window016_variants": {
            key: {
                "real_frame_count": value["real_frame_count"],
                "runtime_padding_frame_count": value["runtime_padding_frame_count"],
                "continuity_status": value["continuity_status"],
                "high_risk_step_count": value["high_risk_step_count"],
                "npz_minor_ratio_vs_official_save": get_path(
                    value, "true_rerun.npz_minor_ratio_vs_official_save"
                ),
            }
            for key, value in report["window016_variants"].items()
        },
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# DA3 Dart continuity quarantine plan audit",
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
            "## Metrics",
            "",
            "| metric | value |",
            "|---|---:|",
        ]
    )
    for key, value in report["metrics"].items():
        lines.append(f"| `{key}` | `{value}` |")

    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | status | evidence |",
            "|---|---:|---|",
        ]
    )
    for item in report["checks"]:
        lines.append(
            "| `{id}` | `{status}` | {evidence} |".format(
                id=item["id"],
                status=item["status"],
                evidence=escape_md(str(item["evidence"])),
            )
        )

    lines.extend(
        [
            "",
            "## Window 016 Variants",
            "",
            "| variant | real frames | padding | continuity | high-risk steps | npz minor/orig | npz bbox/orig |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for variant_id, item in report["window016_variants"].items():
        true = item["true_rerun"]
        lines.append(
            "| `{variant}` | {real} | {padding} | `{status}` | {risk} | {minor} | {bbox} |".format(
                variant=variant_id,
                real=item["real_frame_count"],
                padding=item["runtime_padding_frame_count"],
                status=item["continuity_status"],
                risk=item["high_risk_step_count"],
                minor=format_optional_float(true["npz_minor_ratio_vs_official_save"]),
                bbox=format_optional_float(true["npz_bbox_ratio_vs_official_save"]),
            )
        )

    lines.extend(["", "## Frame Sets", ""])
    for variant_id, item in report["window016_variants"].items():
        lines.append(f"- `{variant_id}` downstream: " + ", ".join(f"`{x}`" for x in item["downstream_frame_ids"]))
        lines.append(f"- `{variant_id}` removed: " + ", ".join(f"`{x}`" for x in item["removed_frame_ids"]))
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


def format_optional_float(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
