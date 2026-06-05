#!/usr/bin/env python3
"""Audit DA3 image tensor preprocessing parity between official code and APP."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_OFFICIAL_REPO = Path(
    "/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3"
)
DEFAULT_DART_PACKAGE = Path(
    "/Users/kaidongwang/Documents/progecttwo/packages/aether_capture_services"
)
DEFAULT_APP_REPO = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter")
DEFAULT_RESEARCH_REPO = Path(__file__).resolve().parents[2]
DEFAULT_CAPTURE_DIR = (
    DEFAULT_RESEARCH_REPO
    / "data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-repo", type=Path, default=DEFAULT_OFFICIAL_REPO)
    parser.add_argument("--dart-package", type=Path, default=DEFAULT_DART_PACKAGE)
    parser.add_argument("--app-repo", type=Path, default=DEFAULT_APP_REPO)
    parser.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE_DIR)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_tensor_contract_parity_audit.json", report)
    write_markdown(args.out_dir / "official_da3_image_tensor_contract_parity_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official_input = args.official_repo / "src/depth_anything_3/utils/io/input_processor.py"
    dart_derivation = args.dart_package / "lib/src/photo_bundle_derivation_service.dart"
    swift_plugin = args.app_repo / "ios/Runner/Da3DepthPlugin.swift"
    manifest_summary = manifest_preprocess_summary(args.capture_dir)
    checks = [
        check_contains(
            "official_default_upper_bound_resize",
            official_input,
            'process_res_method: str = "upper_bound_resize"',
            "官方默认 process_res_method 是 upper_bound_resize。",
        ),
        check_contains(
            "official_preserves_aspect_by_longest_side",
            official_input,
            "scale = target_size / float(longest)",
            "官方 upper_bound_resize 先按最长边等比缩放。",
        ),
        check_contains(
            "official_rounds_to_patch_multiple",
            official_input,
            "nearest_multiple(w, patch)",
            "官方 resize 后还会把宽高调整到 patch size 的倍数。",
        ),
        check_contains(
            "official_imagenet_normalization",
            official_input,
            "NORMALIZE = T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])",
            "官方输入 tensor 使用 ImageNet mean/std normalization。",
        ),
        check_contains(
            "app_dart_photos_depth_direct_stretch",
            dart_derivation,
            "'mode': 'direct_stretch'",
            "Dart photos_depth 固定输入是 direct_stretch 到模型尺寸；这和官方等比 upper_bound_resize 不是同一 preprocess。",
            pass_means_parity=False,
        ),
        check_contains(
            "app_swift_requires_pre_resized_photos_depth",
            swift_plugin,
            "DA3 imagePath must already be",
            "Swift 不执行官方 boundary resize；它要求 Dart/photos_depth 已经是固定尺寸。",
            pass_means_parity=False,
        ),
        check_contains(
            "app_swift_imagenet_mean_matches_official",
            swift_plugin,
            "let meanR: Float = 0.485",
            "Swift image tensor 使用与官方一致的 ImageNet mean。",
        ),
        check_contains(
            "app_swift_imagenet_std_matches_official",
            swift_plugin,
            "let stdR: Float = 0.229",
            "Swift image tensor 使用与官方一致的 ImageNet std。",
        ),
        check_contains(
            "app_swift_writes_nchw_float32",
            swift_plugin,
            "ptr[viewBase + 0 * planeSize + dst] = (r - meanR) / stdR",
            "Swift 写入 NCHW float32 normalized tensor，通道顺序与官方 RGB tensor 对齐。",
        ),
        {
            "id": "strict_capture_manifest_all_direct_stretch",
            "status": "parity_gap"
            if manifest_summary.get("all_frames_direct_stretch")
            else "unknown",
            "path": str(args.capture_dir / "da3_input_manifest.json"),
            "line": None,
            "needle": "resize.mode",
            "evidence": strict_capture_manifest_evidence(manifest_summary),
        },
    ]
    resize_gap = any(
        item["id"] in {"app_dart_photos_depth_direct_stretch", "app_swift_requires_pre_resized_photos_depth"}
        and item["status"] == "parity_gap"
        for item in checks
    )
    normalization_ok = all(
        item["status"] == "pass"
        for item in checks
        if item["id"].startswith("app_swift_imagenet") or item["id"] == "app_swift_writes_nchw_float32"
    )
    status = (
        "image_tensor_normalization_matches_but_resize_contract_differs"
        if resize_gap and normalization_ok
        else "image_tensor_contract_needs_manual_review"
    )
    return {
        "schema_version": "aether_da3_image_tensor_contract_parity_audit_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "normalization_parity": normalization_ok,
            "resize_contract_parity": not resize_gap,
            "official_algorithm_blame_supported": False,
            "conclusion": (
                "APP Swift normalization matches official ImageNet RGB/NCHW tensor semantics, but the image resize "
                "contract still differs: official code does aspect-preserving upper_bound_resize plus patch rounding, "
                "while current Dart photos_depth uses direct_stretch to the fixed 742x476 model size. In the strict "
                "capture, a 16:9 source frame would become 742x420 under an official long-side-742 upper_bound_resize "
                "contract, but the current manifest stores it as 742x476."
            ),
            "next_best_action": (
                "Treat image normalization as closed for the current audit. Keep resize/preprocess as an upstream "
                "parity gap until an official-style fixed-size preprocessing path is tested against the same window."
            ),
        },
        "inputs": {
            "official_repo": str(args.official_repo),
            "dart_package": str(args.dart_package),
            "app_repo": str(args.app_repo),
            "capture_dir": str(args.capture_dir),
        },
        "manifest_preprocess": manifest_summary,
        "checks": checks,
        "plain_language": [
            "Swift 喂给 CoreML 的 RGB/NCHW/ImageNet normalization 和官方一致，这一点先不要再怀疑。",
            "但 APP 当前没有在 Swift 里做官方 boundary resize；它依赖 Dart 预生成固定尺寸 photos_depth。",
            "Dart 的固定尺寸生成是 direct_stretch，不是官方默认的等比 upper_bound_resize + patch multiple。",
            "这批 strict capture 的源图主要是 4224x2376；当前变成 742x476，Y 方向相对 X 方向多拉伸约 14%。",
            "如果按官方 upper_bound_resize 并把长边设成 742，同一 16:9 源图会落到 742x420，而不是 742x476。",
            "所以 image-side 仍有未复刻点，但它集中在 resize/preprocess contract，不是 normalization。",
        ],
    }


def manifest_preprocess_summary(capture_dir: Path) -> dict[str, Any]:
    manifest_path = capture_dir / "da3_input_manifest.json"
    if not manifest_path.exists():
        return {"exists": False, "path": str(manifest_path)}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = [frame for frame in manifest.get("frames", []) if isinstance(frame, dict)]
    mode_counts: dict[str, int] = {}
    source_size_counts: dict[str, int] = {}
    input_size_counts: dict[str, int] = {}
    anisotropy_values: list[float] = []
    for frame in frames:
        mode = str((frame.get("resize") or {}).get("mode") or "unknown")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        source_w = int(frame.get("sourceWidth") or 0)
        source_h = int(frame.get("sourceHeight") or 0)
        input_w = int(frame.get("inputWidth") or manifest.get("inputWidth") or 0)
        input_h = int(frame.get("inputHeight") or manifest.get("inputHeight") or 0)
        source_size_counts[f"{source_w}x{source_h}"] = (
            source_size_counts.get(f"{source_w}x{source_h}", 0) + 1
        )
        input_size_counts[f"{input_w}x{input_h}"] = (
            input_size_counts.get(f"{input_w}x{input_h}", 0) + 1
        )
        transform = frame.get("transform") or {}
        scale_x = float(transform.get("scaleX") or 0.0)
        scale_y = float(transform.get("scaleY") or 0.0)
        if scale_x > 0:
            anisotropy_values.append(scale_y / scale_x)
    target_w, target_h = most_common_size(input_size_counts)
    official_process_res = max(target_w, target_h)
    official_shape_by_source = {
        key: {
            "frame_count": count,
            "official_upper_bound_resize_long_side": official_upper_bound_shape(
                key, official_process_res
            ),
            "current_direct_stretch_input": f"{target_w}x{target_h}",
        }
        for key, count in sorted(source_size_counts.items())
    }
    return {
        "exists": True,
        "path": str(manifest_path),
        "frame_count": len(frames),
        "mode_counts": mode_counts,
        "source_size_counts": source_size_counts,
        "input_size_counts": input_size_counts,
        "all_frames_direct_stretch": len(frames) > 0
        and mode_counts.get("direct_stretch") == len(frames),
        "official_process_res_assumption": (
            "max(current fixed CoreML input width/height); used only to quantify resize-contract mismatch"
        ),
        "official_process_res": official_process_res,
        "official_shape_by_source": official_shape_by_source,
        "stretch_anisotropy_y_over_x_min": min(anisotropy_values)
        if anisotropy_values
        else None,
        "stretch_anisotropy_y_over_x_max": max(anisotropy_values)
        if anisotropy_values
        else None,
        "stretch_anisotropy_y_over_x_median": median(anisotropy_values)
        if anisotropy_values
        else None,
    }


def most_common_size(size_counts: dict[str, int]) -> tuple[int, int]:
    if not size_counts:
        return 0, 0
    raw = max(size_counts.items(), key=lambda item: item[1])[0]
    width, height = raw.split("x", maxsplit=1)
    return int(width), int(height)


def official_upper_bound_shape(source_size: str, process_res: int) -> str:
    width, height = [int(part) for part in source_size.split("x", maxsplit=1)]
    if width <= 0 or height <= 0 or process_res <= 0:
        return "unknown"
    scale = process_res / float(max(width, height))
    resized_w = max(1, int(round(width * scale)))
    resized_h = max(1, int(round(height * scale)))
    return f"{nearest_multiple(resized_w, 14)}x{nearest_multiple(resized_h, 14)}"


def nearest_multiple(value: int, patch: int) -> int:
    down = (value // patch) * patch
    up = down + patch
    return up if abs(up - value) <= abs(value - down) else down


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) * 0.5


def strict_capture_manifest_evidence(summary: dict[str, Any]) -> str:
    if not summary.get("exists"):
        return "Strict capture da3_input_manifest.json could not be read."
    shapes = summary.get("official_shape_by_source") or {}
    shape_bits = []
    for source, info in list(shapes.items())[:3]:
        shape_bits.append(
            f"{source}->{info.get('current_direct_stretch_input')} current, "
            f"{info.get('official_upper_bound_resize_long_side')} official-like"
        )
    return (
        f"frames={summary.get('frame_count')}, modes={summary.get('mode_counts')}; "
        f"source resize examples: {'; '.join(shape_bits)}; "
        f"median y/x stretch={float_or_nan(summary.get('stretch_anisotropy_y_over_x_median')):.3f}."
    )


def float_or_nan(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def check_contains(
    check_id: str,
    path: Path,
    needle: str,
    evidence: str,
    *,
    pass_means_parity: bool = True,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    present = needle in text
    if not present:
        status = "missing"
    elif pass_means_parity:
        status = "pass"
    else:
        status = "parity_gap"
    return {
        "id": check_id,
        "status": status,
        "path": str(path),
        "line": find_line(text, needle) if present else None,
        "needle": needle,
        "evidence": evidence,
    }


def find_line(text: str, needle: str) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return None


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "parity_gaps": [
            {
                "id": item["id"],
                "status": item["status"],
                "line": item.get("line"),
                "evidence": item["evidence"],
            }
            for item in report["checks"]
            if item["status"] in {"parity_gap", "missing", "fail"}
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 image tensor contract parity audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- normalization parity: `{report['decision']['normalization_parity']}`",
        f"- resize contract parity: `{report['decision']['resize_contract_parity']}`",
        f"- official algorithm blame supported: `{report['decision']['official_algorithm_blame_supported']}`",
        "",
        report["decision"]["conclusion"],
        "",
        "## 大白话",
        "",
    ]
    for item in report["plain_language"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | status | line | evidence | path |",
            "|---|---:|---:|---|---|",
        ]
    )
    for item in report["checks"]:
        lines.append(
            "| `{id}` | `{status}` | {line} | {evidence} | `{path}` |".format(
                id=item["id"],
                status=item["status"],
                line=item.get("line") or "",
                evidence=escape_md(item["evidence"]),
                path=Path(item["path"]).name,
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
