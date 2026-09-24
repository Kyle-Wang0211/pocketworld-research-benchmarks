#!/usr/bin/env python3
"""Audit official DA3 downstream core-frame vs full-chunk point-cloud paths.

This is a read-only attribution report. It does not run DA3. It combines:
- official DA3-Streaming source-code evidence,
- the official PyTorch image-only K35 thickness audit, and
- the current CoreML official-save downstream audit when available.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--official-pytorch-audit", type=Path, required=True)
    parser.add_argument("--coreml-official-save-audit", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    source = source_evidence(args.official_root)
    pytorch = read_json(args.official_pytorch_audit)
    coreml = read_json(args.coreml_official_save_audit) if args.coreml_official_save_audit else {}
    report = {
        "schema_version": "pocketworld_da3_official_downstream_core_vs_full_chunk_audit_v1",
        "date": args.date,
        "inputs": {
            "official_root": str(args.official_root),
            "official_pytorch_audit": str(args.official_pytorch_audit),
            "coreml_official_save_audit": str(args.coreml_official_save_audit)
            if args.coreml_official_save_audit
            else None,
        },
        "official_source_evidence": source,
        "official_pytorch_image_only_window016": pytorch_summary(pytorch),
        "current_coreml_pose_official_save_window016": coreml_summary(coreml),
    }
    report["decision"] = decision(report)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_downstream_core_vs_full_chunk_audit.json", report)
    write_markdown(args.out_dir / "official_downstream_core_vs_full_chunk_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def source_evidence(root: Path) -> dict[str, Any]:
    streaming = root / "da3_streaming/da3_streaming.py"
    readme = root / "da3_streaming/README.md"
    npz = root / "da3_streaming/npz_output_process.py"
    base_config = root / "da3_streaming/configs/base_config.yaml"
    return {
        "confidence_convention": find_line(streaming, "predictions.conf -= 1.0"),
        "core_frame_save_indices_first_chunk": find_line(
            streaming,
            "save_indices = list(range(0, chunk_end - chunk_start - self.overlap_e))",
        ),
        "core_frame_save_indices_middle_chunk": find_line(
            streaming,
            "save_indices = list(range(self.overlap_s, chunk_end - chunk_start - self.overlap_e))",
        ),
        "full_chunk_pcd_first_chunk_save": find_line(streaming, 'ply_path_first = os.path.join(self.pcd_dir, "0_pcd.ply")'),
        "full_chunk_pcd_aligned_chunk_save": find_line(streaming, 'ply_path = os.path.join(self.pcd_dir, f"{chunk_idx+1}_pcd.ply")'),
        "combined_pcd_readme": find_line(readme, "combined_pcd.ply"),
        "results_output_readme": find_line(readme, "results_output"),
        "npz_verify_command_readme": find_line(readme, "npz_output_process.py"),
        "npz_default_conf_threshold_coef": find_line(npz, '--conf_threshold_coef", type=float, default=0.5'),
        "npz_default_sample_ratio": find_line(npz, '--sample_ratio", type=float, default=0.015'),
        "streaming_default_pointcloud_coef": find_line(base_config, "conf_threshold_coef: 0.75"),
        "streaming_default_sample_ratio": find_line(base_config, "sample_ratio: 0.015"),
    }


def pytorch_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary", {})
    checkpoints = summary.get("checkpoints", {})
    k10 = checkpoints.get("k10") or checkpoint_from_cumulative(report, 10)
    k17 = checkpoints.get("k17") or checkpoint_from_cumulative(report, 17)
    k35 = checkpoints.get("k35") or checkpoint_from_cumulative(report, 35)
    out = {
        "scope": report.get("scope", {}),
        "k10": k10,
        "official_core_like_k17": k17,
        "full_chunk_k35": k35,
        "k17_vs_k10": k17,
        "k35_vs_k10": k35,
        "k35_vs_k17": ratio_pair(k35, k17),
        "first_events": {
            "npz_first_minor_ge_1_10": get_path(
                summary,
                "styles.npz_streaming_style_conf_minus_one.first_minor_ratio_ge_1_10_after_k10",
            ),
            "npz_first_minor_ge_1_35": get_path(
                summary,
                "styles.npz_streaming_style_conf_minus_one.first_minor_ratio_ge_1_35_after_k10",
            ),
            "glb_first_minor_ge_1_10": get_path(
                summary,
                "styles.glb_style_raw_conf.first_minor_ratio_ge_1_10_after_k10",
            ),
            "glb_first_minor_ge_1_35": get_path(
                summary,
                "styles.glb_style_raw_conf.first_minor_ratio_ge_1_35_after_k10",
            ),
        },
        "pose": summary.get("pose", {}),
        "depth": summary.get("depth", {}),
    }
    return out


def checkpoint_from_cumulative(report: dict[str, Any], k: int) -> dict[str, Any]:
    cumulative = report.get("cumulative") or []
    if len(cumulative) < k:
        return {}
    base = cumulative[9] if len(cumulative) >= 10 else cumulative[0]
    item = cumulative[k - 1]
    return {
        "k": k,
        "pose_ratio_vs_k10": safe_ratio(
            get_path(item, "pose.camera_center_diag"),
            get_path(base, "pose.camera_center_diag"),
        ),
        "depth_p95_ratio_vs_k10": safe_ratio(
            get_path(item, "depth.p95"),
            get_path(base, "depth.p95"),
        ),
        "glb_bbox_ratio_vs_k10": safe_ratio(
            get_path(item, "glb_style_raw_conf.bbox_diag_p01_p99"),
            get_path(base, "glb_style_raw_conf.bbox_diag_p01_p99"),
        ),
        "glb_minor_ratio_vs_k10": safe_ratio(
            get_path(item, "glb_style_raw_conf.pca_minor_extent"),
            get_path(base, "glb_style_raw_conf.pca_minor_extent"),
        ),
        "npz_bbox_ratio_vs_k10": safe_ratio(
            get_path(item, "npz_streaming_style_conf_minus_one.bbox_diag_p01_p99"),
            get_path(base, "npz_streaming_style_conf_minus_one.bbox_diag_p01_p99"),
        ),
        "npz_minor_ratio_vs_k10": safe_ratio(
            get_path(item, "npz_streaming_style_conf_minus_one.pca_minor_extent"),
            get_path(base, "npz_streaming_style_conf_minus_one.pca_minor_extent"),
        ),
    }


def ratio_pair(num: dict[str, Any], den: dict[str, Any]) -> dict[str, Any]:
    return {
        "pose_ratio_k35_over_k17": safe_ratio(num.get("pose_ratio_vs_k10"), den.get("pose_ratio_vs_k10")),
        "depth_p95_ratio_k35_over_k17": safe_ratio(
            num.get("depth_p95_ratio_vs_k10"),
            den.get("depth_p95_ratio_vs_k10"),
        ),
        "glb_bbox_ratio_k35_over_k17": safe_ratio(
            num.get("glb_bbox_ratio_vs_k10"),
            den.get("glb_bbox_ratio_vs_k10"),
        ),
        "glb_minor_ratio_k35_over_k17": safe_ratio(
            num.get("glb_minor_ratio_vs_k10"),
            den.get("glb_minor_ratio_vs_k10"),
        ),
        "npz_bbox_ratio_k35_over_k17": safe_ratio(
            num.get("npz_bbox_ratio_vs_k10"),
            den.get("npz_bbox_ratio_vs_k10"),
        ),
        "npz_minor_ratio_k35_over_k17": safe_ratio(
            num.get("npz_minor_ratio_vs_k10"),
            den.get("npz_minor_ratio_vs_k10"),
        ),
    }


def coreml_summary(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {}
    summary = report.get("summary", {})
    return {
        "scope": report.get("scope", {}),
        "npz_k35_over_k10": get_path(summary, "styles.npz_streaming_style.k35_over_k10") or {},
        "glb_k35_over_k10": get_path(summary, "styles.glb_style.k35_over_k10") or {},
        "pose": summary.get("pose", {}),
        "depth": summary.get("depth", {}),
    }


def decision(report: dict[str, Any]) -> dict[str, Any]:
    pytorch = report["official_pytorch_image_only_window016"]
    k17_npz_minor = get_path(pytorch, "official_core_like_k17.npz_minor_ratio_vs_k10")
    k35_npz_minor = get_path(pytorch, "full_chunk_k35.npz_minor_ratio_vs_k10")
    k35_over_k17_npz_minor = get_path(pytorch, "k35_vs_k17.npz_minor_ratio_k35_over_k17")
    glb_k17_minor = get_path(pytorch, "official_core_like_k17.glb_minor_ratio_vs_k10")
    first_npz_135 = get_path(pytorch, "first_events.npz_first_minor_ge_1_35")

    if k17_npz_minor is not None and k17_npz_minor >= 1.35:
        status = "core_frame_downstream_does_not_close_window016_thickness"
    elif k35_npz_minor is not None and k35_npz_minor >= 1.35:
        status = "full_chunk_merge_primary_thickness_amplifier"
    else:
        status = "no_major_official_downstream_thickness_observed"

    return {
        "status": status,
        "plain_language": [
            "官方有两条容易混淆的 downstream：pcd/combined_pcd.ply 是把每个 chunk 的点云文件合并；results_output/frame_*.npz + npz_output_process.py 是用保存下来的 core-frame NPZ 再融合。",
            "core-frame 的作用主要是跨 chunk 去掉 overlap 帧，不是同一 window 内的表面融合/去重算法。",
            (
                f"同一官方 PyTorch image-only 输出里，core-like K17 的 NPZ minor/k10 已经是 {fmt(k17_npz_minor)}，"
                f"full K35 是 {fmt(k35_npz_minor)}，K35/K17 只有 {fmt(k35_over_k17_npz_minor)}。"
            ),
            (
                f"GLB-style 在 K17 的 minor/k10 是 {fmt(glb_k17_minor)}，明显比 NPZ-style 温和；"
                "所以 confidence/filter/export style 会影响厚层外观，但 core-frame 不是根治。"
            ),
            (
                f"首次 NPZ minor >=1.35 出现在 {fmt_event(first_npz_135)}；"
                "跳变发生在核心区间内，不能只归因给 withheld overlap/full-chunk 尾部。"
            ),
        ],
    }


def find_line(path: Path, pattern: str) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "pattern": pattern}
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines, start=1):
        if pattern in line:
            return {
                "path": str(path),
                "exists": True,
                "line": index,
                "pattern": pattern,
                "text": line.strip(),
            }
    return {"path": str(path), "exists": True, "line": None, "pattern": pattern}


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    d = report["decision"]
    py = report["official_pytorch_image_only_window016"]
    src = report["official_source_evidence"]
    coreml = report["current_coreml_pose_official_save_window016"]
    lines = [
        "# Official Downstream Core-Frame vs Full-Chunk Audit",
        "",
        f"- date: `{report['date']}`",
        f"- status: `{d['status']}`",
        "",
        "## 结论",
        "",
    ]
    for item in d["plain_language"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 官方代码证据",
            "",
            "| evidence | file:line | text |",
            "|---|---|---|",
        ]
    )
    for key, item in src.items():
        lines.append(
            f"| `{key}` | `{Path(item.get('path', '')).name}:{item.get('line')}` | `{item.get('text') or item.get('pattern')}` |"
        )
    lines.extend(
        [
            "",
            "## Official PyTorch Image-Only Window 016",
            "",
            "| selection | pose/k10 | depth p95/k10 | glb bbox/k10 | glb minor/k10 | npz bbox/k10 | npz minor/k10 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for label, item in [
        ("k10 baseline", py.get("k10") or {}),
        ("core-like k17", py.get("official_core_like_k17") or {}),
        ("full-chunk k35", py.get("full_chunk_k35") or {}),
    ]:
        lines.append(
            f"| {label} | {fmt(item.get('pose_ratio_vs_k10'))} | {fmt(item.get('depth_p95_ratio_vs_k10'))} | "
            f"{fmt(item.get('glb_bbox_ratio_vs_k10'))} | {fmt(item.get('glb_minor_ratio_vs_k10'))} | "
            f"{fmt(item.get('npz_bbox_ratio_vs_k10'))} | {fmt(item.get('npz_minor_ratio_vs_k10'))} |"
        )
    k35_vs_k17 = py.get("k35_vs_k17") or {}
    lines.extend(
        [
            "",
            "## K35 vs Core K17",
            "",
            f"- npz minor K35/K17: `{fmt(k35_vs_k17.get('npz_minor_ratio_k35_over_k17'))}`",
            f"- npz bbox K35/K17: `{fmt(k35_vs_k17.get('npz_bbox_ratio_k35_over_k17'))}`",
            f"- glb minor K35/K17: `{fmt(k35_vs_k17.get('glb_minor_ratio_k35_over_k17'))}`",
            f"- pose span K35/K17: `{fmt(k35_vs_k17.get('pose_ratio_k35_over_k17'))}`",
            "",
            "## Current CoreML Pose Official-Save Context",
            "",
        ]
    )
    if coreml:
        npz = coreml.get("npz_k35_over_k10") or {}
        glb = coreml.get("glb_k35_over_k10") or {}
        lines.extend(
            [
                f"- frame_source: `{get_path(coreml, 'scope.frame_source')}`",
                f"- frame_count: `{get_path(coreml, 'scope.frame_count')}`",
                f"- CoreML official-save npz minor/k10: `{fmt(npz.get('minor_ratio_vs_k10'))}`",
                f"- CoreML official-save npz bbox/k10: `{fmt(npz.get('bbox_ratio_vs_k10'))}`",
                f"- CoreML official-save glb minor/k10: `{fmt(glb.get('minor_ratio_vs_k10'))}`",
            ]
        )
    else:
        lines.append("- CoreML official-save report not provided.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    py = report["official_pytorch_image_only_window016"]
    return {
        "status": report["decision"]["status"],
        "pytorch_core_like_k17_npz_minor_vs_k10": get_path(
            py,
            "official_core_like_k17.npz_minor_ratio_vs_k10",
        ),
        "pytorch_full_k35_npz_minor_vs_k10": get_path(
            py,
            "full_chunk_k35.npz_minor_ratio_vs_k10",
        ),
        "pytorch_k35_over_k17_npz_minor": get_path(
            py,
            "k35_vs_k17.npz_minor_ratio_k35_over_k17",
        ),
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def safe_ratio(num: Any, den: Any) -> float | None:
    try:
        n = float(num)
        d = float(den)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or not math.isfinite(d) or d == 0.0:
        return None
    return n / d


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return str(value)


def fmt_event(value: Any) -> str:
    if not isinstance(value, dict):
        return "-"
    if "k" in value:
        metric = next((v for k, v in value.items() if k.endswith("_vs_k10")), None)
        return f"k={value['k']} ({fmt(metric)})"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
