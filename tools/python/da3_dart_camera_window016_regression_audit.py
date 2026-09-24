#!/usr/bin/env python3
"""Summarize the runnable DA3 pose/CoreML window_016 Dart-camera regression."""

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
    write_json(args.out_dir / "official_da3_dart_camera_window016_regression_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_dart_camera_window016_regression_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    dataset = args.dataset_dir
    capture = dataset / "capture_seq_k35_strict"
    raw = dataset / "da3_seq_k35_coreml_pose_dart_camera_contract_window016_cpu_2026_06_05"
    post = dataset / "da3_seq_k35_coreml_pose_dart_camera_contract_window016_cpu_official_postprocess_2026_06_05"
    diag = dataset / "diagnostics"
    micro = diag / "window_016_dart_camera_contract_official_postprocess_2026_06_05/window_000_official_filter_micro_audit_report.json"
    pose_depth = diag / "window_016_dart_camera_contract_pose_depth_scale_2026_06_05/window_016_pose_depth_scale_audit.json"

    input_manifest = read_json(capture / "da3_input_manifest.json")
    raw_reports = read_json(raw / "mac_da3_window_reports.json")
    post_report = read_json(post / "official_postprocess_report.json")
    micro_report = read_json(micro)
    pose_depth_report = read_json(pose_depth)

    frames = input_manifest.get("frames", [])
    field_counts = {
        "frame_count": len(frames),
        "cameraExtrinsicOpenCvW2c4x4_count": sum(
            1 for frame in frames if len(frame.get("cameraExtrinsicOpenCvW2c4x4", [])) == 16
        ),
        "cameraIntrinsic3x3_count": sum(
            1 for frame in frames if len(frame.get("cameraIntrinsic3x3", [])) == 9
        ),
        "camera_contract_schema": input_manifest.get("cameraContract", {}).get("schemaVersion"),
    }
    raw_window = raw_reports["windows"][0]
    post_window = post_report["windows"][0]
    glb = style_growth(micro_report, "glb_style")
    npz = style_growth(micro_report, "npz_streaming_style")
    pose_summary = pose_depth_report["summary"]
    checks = [
        check(
            "dart_camera_fields_present",
            field_counts["frame_count"] == field_counts["cameraExtrinsicOpenCvW2c4x4_count"]
            == field_counts["cameraIntrinsic3x3_count"]
            == 414,
            "All 414 frames carry Dart-owned OpenCV w2c and 3x3 intrinsics.",
        ),
        check(
            "single_window_coreml_rerun_completed",
            raw_window.get("windowID") == "window_016"
            and raw_window.get("status") == "completed"
            and len(raw_window.get("frames", [])) == 35,
            f"window_016 CoreML CPU rerun wrote {len(raw_window.get('frames', []))} frames.",
        ),
        check(
            "official_postprocess_completed",
            post_window.get("windowID") == "window_016"
            and post_window.get("poseScale") is not None,
            f"official postprocess poseScale={post_window.get('poseScale')}",
        ),
        check(
            "npz_streaming_thickness_persists",
            npz["bbox_ratio_vs_k10"] >= 1.10 and npz["minor_ratio_vs_k10"] >= 1.10,
            f"npz k35/k10 bbox={npz['bbox_ratio_vs_k10']:.3f}, minor={npz['minor_ratio_vs_k10']:.3f}",
            status_when_true="fail",
        ),
        check(
            "glb_style_thickness_persists",
            glb["bbox_ratio_vs_k10"] >= 1.10 or glb["minor_ratio_vs_k10"] >= 1.10,
            f"glb k35/k10 bbox={glb['bbox_ratio_vs_k10']:.3f}, minor={glb['minor_ratio_vs_k10']:.3f}",
            status_when_true="warning",
        ),
        check(
            "pose_span_expands_more_than_depth",
            pose_summary["pose"]["k35_over_k10_pose_diag"] >= 3.0
            and pose_summary["depth"]["k35_over_k10_p95"] < 1.20,
            (
                f"pose span={pose_summary['pose']['k35_over_k10_pose_diag']:.3f}x, "
                f"depth p95={pose_summary['depth']['k35_over_k10_p95']:.3f}x"
            ),
        ),
    ]
    status = "thickness_persists_after_dart_camera_contract_pose_coreml"
    return {
        "schema_version": "aether_da3_dart_camera_window016_regression_audit_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "product_path": "DA3BASE_476x742_N35_pose CoreML CPU rerun with Dart-owned camera tensors",
            "conclusion": (
                "Single-window thickness still persists after Dart camera contract, "
                "current runnable CoreML rerun, and official postprocess."
            ),
            "next_best_action": (
                "Inspect DA3 upstream pose/depth/scale consistency inside window_016, especially later slots; "
                "do not route this back to A100/large-memory image-only export as product blocker."
            ),
        },
        "paths": {
            "capture": str(capture),
            "raw_coreml": str(raw),
            "official_postprocess": str(post),
            "micro_audit": str(micro),
            "pose_depth_scale_audit": str(pose_depth),
        },
        "field_counts": field_counts,
        "runtime": {
            "compute_unit": raw_window.get("telemetry", {}).get("computeUnit"),
            "predict_ms": raw_window.get("telemetry", {}).get("predictMs"),
            "rss_after_predict_mb": raw_window.get("telemetry", {}).get("rssAfterPredictMB"),
            "frame_count": len(raw_window.get("frames", [])),
        },
        "official_postprocess": {
            "pose_scale": post_window.get("poseScale"),
            "raw_depth_mean": post_window.get("rawDepth", {}).get("mean"),
            "post_depth_mean": post_window.get("postDepth", {}).get("mean"),
        },
        "thickness": {
            "glb_style_k35_over_k10": glb,
            "npz_streaming_style_k35_over_k10": npz,
            "pose_span_k35_over_k10": pose_summary["pose"]["k35_over_k10_pose_diag"],
            "depth_p95_k35_over_k10": pose_summary["depth"]["k35_over_k10_p95"],
        },
        "checks": checks,
        "plain_language": [
            "当前能在 Mac/Apple 路线跑的 DA3-BASE pose CoreML 已经按 Dart camera contract 重跑了 window_016。",
            "官方 postprocess 之后，npz downstream 风格下 first35 仍比 first10 明显变厚。",
            "这说明厚层不是大内存导出问题，也不是官方 downstream 里有一个隐藏去厚步骤没跑。",
            "下一步应该继续查 DA3 上游几何一致性：同一 K35 window 后段 slot 的 pose/depth/scale 是否互相打架。",
        ],
    }


def style_growth(report: dict[str, Any], style_name: str) -> dict[str, float]:
    for style in report.get("styles", []):
        if style.get("style") != style_name:
            continue
        groups = {group["name"]: group for group in style.get("groups", [])}
        first10 = extract_metrics(groups["first_10"])
        first35 = extract_metrics(groups["first_35"])
        return {
            "bbox_ratio_vs_k10": ratio(first35["bbox_diag_p01_p99"], first10["bbox_diag_p01_p99"]),
            "minor_ratio_vs_k10": ratio(first35["pca_minor_extent"], first10["pca_minor_extent"]),
            "conf_threshold_ratio_vs_k10": ratio(first35["conf_threshold"], first10["conf_threshold"]),
            "valid_fraction_delta_vs_k10": first35["valid_fraction"] - first10["valid_fraction"],
        }
    raise KeyError(style_name)


def extract_metrics(group: dict[str, Any]) -> dict[str, float]:
    metrics = group["metrics"]
    return {
        "valid_fraction": float(metrics["valid_fraction_of_pixels"]),
        "bbox_diag_p01_p99": float(metrics["point_cloud"]["bbox_diag_p01_p99"]),
        "pca_minor_extent": float(metrics["pca"]["minor_extent"]),
        "conf_threshold": float(group["official_filter"]["conf_threshold"]),
    }


def ratio(top: float, bottom: float) -> float:
    return float(top / bottom) if bottom else float("nan")


def check(
    check_id: str,
    passed: bool,
    evidence: str,
    *,
    status_when_true: str = "pass",
    status_when_false: str = "fail",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status_when_true if passed else status_when_false,
        "evidence": evidence,
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "thickness": report["thickness"],
        "non_pass_checks": [
            {"id": item["id"], "status": item["status"], "evidence": item["evidence"]}
            for item in report["checks"]
            if item["status"] != "pass"
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 Dart-camera window_016 regression audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- product path: `{report['decision']['product_path']}`",
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
    t = report["thickness"]
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            f"- npz bbox k35/k10: `{t['npz_streaming_style_k35_over_k10']['bbox_ratio_vs_k10']:.3f}`",
            f"- npz PCA minor k35/k10: `{t['npz_streaming_style_k35_over_k10']['minor_ratio_vs_k10']:.3f}`",
            f"- glb bbox k35/k10: `{t['glb_style_k35_over_k10']['bbox_ratio_vs_k10']:.3f}`",
            f"- glb PCA minor k35/k10: `{t['glb_style_k35_over_k10']['minor_ratio_vs_k10']:.3f}`",
            f"- pose span k35/k10: `{t['pose_span_k35_over_k10']:.3f}`",
            f"- depth p95 k35/k10: `{t['depth_p95_k35_over_k10']:.3f}`",
            "",
            "## Checks",
            "",
            "| check | status | evidence |",
            "|---|---:|---|",
        ]
    )
    for item in report["checks"]:
        lines.append(f"| `{item['id']}` | `{item['status']}` | {item['evidence']} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
