#!/usr/bin/env python3
"""Summarize product official-downstream image-only overlap gates across windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_WINDOWS = (
    "window_004",
    "window_006",
    "window_007",
    "window_016",
    "window_017",
    "window_021",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    parser.add_argument("--window-id", action="append", default=[])
    args = parser.parse_args()

    windows = tuple(args.window_id or DEFAULT_WINDOWS)
    report = build_report(args, windows)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_only_multi_window_overlap_summary.json", report)
    write_markdown(
        args.out_dir / "official_da3_image_only_multi_window_overlap_summary_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace, windows: tuple[str, ...]) -> dict[str, Any]:
    rows = [build_window_row(args.diagnostics_dir, window_id) for window_id in windows]
    decision = derive_decision(rows)
    return {
        "schema_version": "aether_da3_image_only_multi_window_overlap_summary_v1",
        "date": args.date,
        "purpose": (
            "Aggregate fixed DA3BASE_280x504_N35_image_only CoreML overlap gates. "
            "Product acceptance uses official_downstream_over_first10; full K35 remains diagnostic only."
        ),
        "product_acceptance_metric": "official_downstream_over_first10.pca_minor_growth",
        "full_k35_diagnostic_metric": "first35_over_first10.pca_minor_growth",
        "diagnostics_dir": str(args.diagnostics_dir),
        "windows": rows,
        "decision": decision,
    }


def build_window_row(diagnostics_dir: Path, window_id: str) -> dict[str, Any]:
    report_path = (
        diagnostics_dir
        / f"official_da3_image_only_overlap_regression_{window_id}_2026_06_05"
        / "official_da3_image_only_overlap_regression_gate.json"
    )
    report = read_json_or_empty(report_path)
    decision = report.get("decision") or {}
    acceptance = decision.get("acceptance") or {}
    threshold = as_float(acceptance.get("max_acceptable_image_only_minor_growth"))
    product = acceptance.get("image_only_official_downstream_over_first10") or {}
    full = acceptance.get("image_only_first35_over_first10") or {}
    product_minor = as_float(product.get("pca_minor_growth"))
    full_minor = as_float(full.get("pca_minor_growth"))
    product_pass = (
        product_minor is not None
        and threshold is not None
        and product_minor <= threshold
    )
    full_pass = (
        full_minor is not None
        and threshold is not None
        and full_minor <= threshold
    )
    return {
        "window_id": window_id,
        "report_path": str(report_path),
        "report_exists": report_path.exists(),
        "status": decision.get("status"),
        "product_official_downstream_pca_minor_growth": product_minor,
        "full_k35_diagnostic_pca_minor_growth": full_minor,
        "product_official_downstream_bbox_diag_growth": as_float(product.get("bbox_diag_growth")),
        "full_k35_diagnostic_bbox_diag_growth": as_float(full.get("bbox_diag_growth")),
        "threshold": threshold,
        "product_acceptance_pass": product_pass,
        "full_k35_diagnostic_pass": full_pass,
        "full_k35_diagnostic_exceeds_threshold": (
            full_minor is not None
            and threshold is not None
            and full_minor > threshold
        ),
        "pose_reference_warning": acceptance.get("pose_reference_warning"),
    }


def derive_decision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [row["window_id"] for row in rows if not row["report_exists"]]
    product_failures = [
        row["window_id"] for row in rows if row["report_exists"] and not row["product_acceptance_pass"]
    ]
    product_passes = [
        row["window_id"] for row in rows if row["report_exists"] and row["product_acceptance_pass"]
    ]
    full_k35_warnings = [
        row["window_id"] for row in rows if row["full_k35_diagnostic_exceeds_threshold"]
    ]
    product_values = [
        row["product_official_downstream_pca_minor_growth"]
        for row in rows
        if row["product_official_downstream_pca_minor_growth"] is not None
    ]
    full_values = [
        row["full_k35_diagnostic_pca_minor_growth"]
        for row in rows
        if row["full_k35_diagnostic_pca_minor_growth"] is not None
    ]
    metric_pass_all = not missing and not product_failures
    if missing:
        status = "blocked_missing_window_overlap_reports"
    elif product_failures:
        status = "fail_product_official_downstream_overlap_regression"
    elif full_k35_warnings:
        status = "warning"
    else:
        status = "pass_product_official_downstream_overlap_regression"
    return {
        "status": status,
        "metric_status": (
            "product_official_downstream_metric_pass_full_k35_visual_review_required"
            if full_k35_warnings and metric_pass_all
            else "product_official_downstream_metric_pass"
            if metric_pass_all
            else "product_official_downstream_metric_fail"
        ),
        "window_count": len(rows),
        "product_pass_count": len(product_passes),
        "product_failure_windows": product_failures,
        "missing_windows": missing,
        "full_k35_diagnostic_warning_windows": full_k35_warnings,
        "max_product_official_downstream_pca_minor_growth": max(product_values) if product_values else None,
        "max_full_k35_diagnostic_pca_minor_growth": max(full_values) if full_values else None,
        "can_judge_product_overlap": not missing,
        "visual_thickness_review_required": bool(full_k35_warnings),
        "do_not_claim_thick_layer_fully_solved": bool(full_k35_warnings),
        "goal_complete": False,
        "plain_language": plain_language(status, product_failures, full_k35_warnings),
    }


def plain_language(
    status: str,
    product_failures: list[str],
    full_k35_warnings: list[str],
) -> str:
    if status == "blocked_missing_window_overlap_reports":
        return "还缺某些 window 的 image-only overlap gate 报告，不能做 multi-window 结论。"
    if status == "fail_product_official_downstream_overlap_regression":
        return f"产品 official_downstream 口径仍有 window 超阈值：{', '.join(product_failures)}。"
    if status == "warning":
        return (
            "产品 official_downstream metric 全部通过，但完整 K35 诊断仍有尾帧超阈值，"
            f"需要保留为视觉/上游诊断警告：{', '.join(full_k35_warnings)}；不能写成厚层完全根治。"
        )
    return "产品 official_downstream 口径全部通过，完整 K35 诊断也没有超阈值。"


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "windows": [
            {
                "window_id": row["window_id"],
                "product": row["product_official_downstream_pca_minor_growth"],
                "full_k35": row["full_k35_diagnostic_pca_minor_growth"],
                "product_pass": row["product_acceptance_pass"],
                "full_k35_warning": row["full_k35_diagnostic_exceeds_threshold"],
            }
            for row in report["windows"]
        ],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    lines = [
        "# DA3 image-only multi-window overlap summary",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{decision['status']}`",
        f"- metric status: `{decision['metric_status']}`",
        f"- product pass: `{decision['product_pass_count']}/{decision['window_count']}`",
        f"- max product official_downstream PCA minor growth: `{fmt_float(decision['max_product_official_downstream_pca_minor_growth'])}`",
        f"- max full K35 diagnostic PCA minor growth: `{fmt_float(decision['max_full_k35_diagnostic_pca_minor_growth'])}`",
        f"- full K35 diagnostic warning windows: `{', '.join(decision['full_k35_diagnostic_warning_windows'])}`",
        f"- visual thickness review required: `{decision['visual_thickness_review_required']}`",
        f"- do not claim fully solved: `{decision['do_not_claim_thick_layer_fully_solved']}`",
        "",
        decision["plain_language"],
        "",
        "`official_downstream` 是产品验收口径；`full K35` 是诊断口径，用来提示 withheld/tail 帧是否仍有几何漂移。",
        "",
        "## Windows",
        "",
        "| window | product downstream PCA | full K35 PCA | product pass | full K35 warning |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["windows"]:
        lines.append(
            "| {window} | {product} | {full} | {product_pass} | {full_warn} |".format(
                window=row["window_id"],
                product=fmt_float(row["product_official_downstream_pca_minor_growth"]),
                full=fmt_float(row["full_k35_diagnostic_pca_minor_growth"]),
                product_pass=row["product_acceptance_pass"],
                full_warn=row["full_k35_diagnostic_exceeds_threshold"],
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def fmt_float(value: Any) -> str:
    raw = as_float(value)
    if raw is None:
        return "-"
    return f"{raw:.6g}"


if __name__ == "__main__":
    raise SystemExit(main())
