#!/usr/bin/env python3
"""Attribute official DA3 preprocess parity gaps by pipeline stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STD = {
    "R": 0.229,
    "G": 0.224,
    "B": 0.225,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_preprocess_stage_attribution_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_preprocess_stage_attribution_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    diag = args.diagnostics_dir
    sources = {
        "source_decode": load_report(
            diag
            / "official_da3_source_decode_parity_audit_2026_06_05"
            / "official_da3_source_decode_parity_audit.json"
        ),
        "full_highres_preprocess": load_report(
            diag
            / "official_da3_preprocess_pixel_parity_audit_2026_06_05"
            / "official_da3_preprocess_pixel_parity_audit.json"
        ),
        "canonical_source_resize": load_report(
            diag
            / "official_da3_canonical_source_probe_2026_06_05"
            / "official_da3_preprocess_pixel_parity_audit.json"
        ),
        "runtime_tensor_boundary": load_report(
            diag
            / "official_da3_tensor_boundary_parity_audit_2026_06_05"
            / "official_da3_preprocess_pixel_parity_audit.json"
        ),
    }
    rows = [
        source_decode_row(sources["source_decode"]),
        preprocess_row(
            "full_highres_preprocess",
            "官方 PIL/libjpeg source decode + OpenCV resize/patch-align 全链路，对比 Dart source decode + Dart OpenCV-like resize 写出的 runtime tensor。",
            sources["full_highres_preprocess"],
        ),
        preprocess_row(
            "canonical_source_resize",
            "把 JPEG decode 固定为 Dart 已解出的 lossless RGB PNG 后，只看官方 OpenCV resize/patch-align 与 Dart OpenCV-like resize 的剩余差异。",
            sources["canonical_source_resize"],
        ),
        preprocess_row(
            "runtime_tensor_boundary",
            "官方 InputProcessor 从同一张 photos_depth PNG 读入后，对比 Swift/CoreML 实际消费的 Dart float32 CHW tensor。",
            sources["runtime_tensor_boundary"],
        ),
    ]
    decision = derive_decision(rows)
    return {
        "schema_version": "aether_official_da3_preprocess_stage_attribution_audit_v1",
        "date": args.date,
        "diagnostics_dir": str(diag),
        "decision": decision,
        "rows": rows,
        "sources": {
            key: {
                "path": value["path"],
                "loaded": value["loaded"],
            }
            for key, value in sources.items()
        },
        "plain_language": plain_language(decision, rows),
    }


def source_decode_row(report: dict[str, Any]) -> dict[str, Any]:
    data = report.get("data", {})
    decision = data.get("decision", {})
    total = decision.get("total_values")
    nonzero = decision.get("nonzero_values")
    nonzero_ratio = None
    if isinstance(total, int) and total > 0 and isinstance(nonzero, int):
        nonzero_ratio = nonzero / total
    return {
        "id": "source_jpeg_decode",
        "requirement": "Dart source JPEG decode 必须 byte-exact 复刻官方 PIL/libjpeg source load。",
        "status": "pass" if decision.get("byte_exact") is True else "warning",
        "evidence": {
            "status": decision.get("status"),
            "shape_match": decision.get("shape_match"),
            "byte_exact": decision.get("byte_exact"),
            "max_abs_uint8": decision.get("max_abs_uint8"),
            "mean_abs_uint8": decision.get("mean_abs_uint8"),
            "nonzero_values": nonzero,
            "total_values": total,
            "nonzero_ratio": nonzero_ratio,
        },
        "source": report["path"],
        "interpretation": (
            "这是当前最大的输入像素差异源；只修 resize 不能关闭官方 high-res source parity。"
            if decision.get("byte_exact") is not True
            else "source JPEG decode byte-exact。"
        ),
    }


def preprocess_row(check_id: str, requirement: str, report: dict[str, Any]) -> dict[str, Any]:
    data = report.get("data", {})
    decision = data.get("decision", {})
    max_abs_norm = decision.get("max_abs_normalized")
    return {
        "id": check_id,
        "requirement": requirement,
        "status": "pass" if decision.get("exact_tensor_match") is True else "warning",
        "evidence": {
            "status": decision.get("status"),
            "sample_count": data.get("sample_count"),
            "shape_match": decision.get("shape_match"),
            "tensor_cache": decision.get("tensor_cache"),
            "png_lossless_cache": decision.get("png_lossless_cache"),
            "exact_tensor_match": decision.get("exact_tensor_match"),
            "max_abs_normalized": max_abs_norm,
            "mean_abs_normalized_mean": decision.get("mean_abs_normalized_mean"),
            "approx_max_abs_uint8_equiv_by_channel": uint8_equiv_by_channel(max_abs_norm),
        },
        "source": report["path"],
        "interpretation": interpretation_for_preprocess(check_id, decision),
    }


def interpretation_for_preprocess(check_id: str, decision: dict[str, Any]) -> str:
    if decision.get("exact_tensor_match") is True:
        return "这段边界已经 exact；native/CoreML 不再引入额外 decode 差异。"
    if check_id == "canonical_source_resize":
        return "JPEG decode 被固定后仍有约 1 个 uint8 级别的 resize/rounding residual；这是小差异但仍不是官方 byte-exact。"
    if check_id == "full_highres_preprocess":
        return "这里混合了 source JPEG decode 与 resize residual；不能用它单独判断 resize。"
    return "这段仍未 exact。"


def uint8_equiv_by_channel(max_abs_norm: Any) -> dict[str, float] | None:
    if not isinstance(max_abs_norm, (int, float)):
        return None
    return {
        channel: float(max_abs_norm) * std * 255.0
        for channel, std in STD.items()
    }


def derive_decision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {row["id"]: row for row in rows}
    source = by_id["source_jpeg_decode"]["evidence"]
    full_highres = by_id["full_highres_preprocess"]["evidence"]
    canonical = by_id["canonical_source_resize"]["evidence"]
    runtime = by_id["runtime_tensor_boundary"]["evidence"]
    source_max = source.get("max_abs_uint8")
    canonical_equiv = canonical.get("approx_max_abs_uint8_equiv_by_channel") or {}
    canonical_max_equiv = (
        max(canonical_equiv.values())
        if isinstance(canonical_equiv, dict) and canonical_equiv
        else None
    )
    hard_gaps = [
        row["id"]
        for row in rows
        if row["status"] != "pass"
    ]
    if source_max is not None and canonical_max_equiv is not None and source_max > canonical_max_equiv:
        dominant_gap = "source_jpeg_decode"
    elif canonical_max_equiv is not None and canonical_max_equiv > 0:
        dominant_gap = "canonical_source_resize"
    else:
        dominant_gap = hard_gaps[0] if hard_gaps else None
    product_preprocess_exact = (
        full_highres.get("exact_tensor_match") is True
        and runtime.get("exact_tensor_match") is True
    )
    product_hard_gaps = []
    if full_highres.get("exact_tensor_match") is not True:
        product_hard_gaps.append("full_highres_preprocess")
    if runtime.get("exact_tensor_match") is not True:
        product_hard_gaps.append("runtime_tensor_boundary")
    return {
        "status": (
            "pass_product_preprocess_stage_parity_with_native_kernel"
            if product_preprocess_exact
            else "not_closed_product_preprocess_stage_parity_has_gaps"
        ),
        "goal_complete": False,
        "hard_gaps": product_hard_gaps,
        "fallback_probe_gaps": hard_gaps,
        "dominant_observed_gap": None if product_preprocess_exact else dominant_gap,
        "dominant_fallback_probe_gap": dominant_gap,
        "product_source_highres_preprocess_exact": product_preprocess_exact,
        "full_highres_preprocess_exact": full_highres.get("exact_tensor_match") is True,
        "runtime_tensor_boundary_exact": runtime.get("exact_tensor_match") is True,
        "source_jpeg_decode_byte_exact": source.get("byte_exact") is True,
        "source_jpeg_decode_max_abs_uint8": source_max,
        "canonical_resize_max_abs_uint8_equiv_upper": canonical_max_equiv,
        "next_action": (
            "产品 official preprocess 已由 C++ OpenCV/libjpeg kernel 闭合；"
            "下一步是把 APP 平台包默认接到该 kernel，并继续补 image-only CoreML artifact/signature。"
            if product_preprocess_exact
            else "继续把 source_highres 输入缓存迁到 C++ OpenCV/libjpeg kernel，直到 full_highres_preprocess 与 runtime tensor boundary 都 exact。"
        ),
    }


def plain_language(decision: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    source = next(row for row in rows if row["id"] == "source_jpeg_decode")
    canonical = next(row for row in rows if row["id"] == "canonical_source_resize")
    full = next(row for row in rows if row["id"] == "full_highres_preprocess")
    runtime = next(row for row in rows if row["id"] == "runtime_tensor_boundary")
    if decision["product_source_highres_preprocess_exact"]:
        return [
            "产品 official preprocess 主路径已经闭合：source_highres -> C++ OpenCV/libjpeg -> photos_depth/photos_depth_tensor 与官方 Python InputProcessor exact match。",
            (
                f"full_highres_preprocess 当前 max_abs_normalized={full['evidence']['max_abs_normalized']}，"
                f"runtime tensor boundary max_abs_normalized={runtime['evidence']['max_abs_normalized']}。"
            ),
            "Dart package:image source decode probe 仍然不是 byte-exact，但它现在只是 fallback 风险，不是产品 official preprocess 主路径。",
            (
                "canonical_source_rgb probe 仍记录 Dart fallback resize/rounding residual，"
                f"上界约 {decision['canonical_resize_max_abs_uint8_equiv_upper']} 个 uint8。"
            ),
            f"下一步：{decision['next_action']}",
        ]
    return [
        "源 JPEG 解码没有解决：官方用 PIL/libjpeg，Dart package:image 解同一张 JPEG 不是 byte-exact。",
        (
            f"源 JPEG decode 当前最大差异是 {source['evidence']['max_abs_uint8']} 个 uint8；"
            f"平均差异是 {source['evidence']['mean_abs_uint8']}。"
        ),
        (
            "把 JPEG decode 固定成同一份 lossless RGB 后，resize/rounding residual 还在，"
            f"但上界约 {decision['canonical_resize_max_abs_uint8_equiv_upper']} 个 uint8。"
        ),
        (
            "从 photos_depth PNG 到 native/CoreML float32 CHW tensor 的 runtime 边界已经 exact。"
            if runtime["status"] == "pass"
            else "runtime tensor 边界也还没 exact。"
        ),
        "所以现在不是“官方预处理完全复刻好了”，而是“运行入口稳定了，source decode 与 full high-res preprocess 还没闭合”。",
        f"下一步：{decision['next_action']}",
    ]


def load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "loaded": False,
            "data": {},
            "error": "missing_report",
        }
    return {
        "path": str(path),
        "loaded": True,
        "data": json.loads(path.read_text(encoding="utf-8")),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    lines = [
        "# Official DA3 preprocess stage attribution audit",
        "",
        f"- status: `{decision['status']}`",
        f"- dominant observed gap: `{decision['dominant_observed_gap']}`",
        f"- runtime tensor boundary exact: `{decision['runtime_tensor_boundary_exact']}`",
        f"- source JPEG decode byte-exact: `{decision['source_jpeg_decode_byte_exact']}`",
        f"- source JPEG max abs uint8: `{decision['source_jpeg_decode_max_abs_uint8']}`",
        f"- canonical resize max abs uint8 equiv upper: `{decision['canonical_resize_max_abs_uint8_equiv_upper']}`",
        "",
        "## 大白话",
        "",
    ]
    lines.extend(f"- {item}" for item in report["plain_language"])
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| stage | status | key evidence | interpretation |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in report["rows"]:
        evidence = row["evidence"]
        if row["id"] == "source_jpeg_decode":
            key = (
                f"byte_exact={evidence['byte_exact']}; "
                f"max_abs_uint8={evidence['max_abs_uint8']}; "
                f"mean_abs_uint8={evidence['mean_abs_uint8']}"
            )
        else:
            key = (
                f"exact={evidence['exact_tensor_match']}; "
                f"max_abs_norm={evidence['max_abs_normalized']}; "
                f"sample_count={evidence['sample_count']}"
            )
        lines.append(
            f"| `{row['id']}` | `{row['status']}` | {key} | {row['interpretation']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
