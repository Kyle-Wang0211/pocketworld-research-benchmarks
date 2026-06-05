#!/usr/bin/env python3
"""Audit whether fixed 476x742 CoreML input can equal official DA3 resize semantics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_RESEARCH_REPO = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks"
)
DEFAULT_CAPTURE_DIR = (
    DEFAULT_RESEARCH_REPO
    / "data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict"
)
DEFAULT_STAGE_SCRIPTS = Path("/Users/kaidongwang/Developer/Aether3D-cross/scripts/da3_official_stage")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE_DIR)
    parser.add_argument("--stage-scripts-dir", type=Path, default=DEFAULT_STAGE_SCRIPTS)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_fixed_shape_preprocess_authority_audit.json", report)
    write_markdown(args.out_dir / "official_da3_fixed_shape_preprocess_authority_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = args.capture_dir / "da3_input_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames = [frame for frame in manifest.get("frames", []) if isinstance(frame, dict)]
    input_w = int(manifest.get("inputWidth") or frames[0].get("inputWidth") or 0)
    input_h = int(manifest.get("inputHeight") or frames[0].get("inputHeight") or 0)
    process_res = max(input_w, input_h)
    source_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    scale_ratios: list[float] = []
    examples: list[dict[str, Any]] = []
    for frame in frames:
        source_w = int(frame.get("sourceWidth") or 0)
        source_h = int(frame.get("sourceHeight") or 0)
        source_key = f"{source_w}x{source_h}"
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        mode = str((frame.get("resize") or {}).get("mode") or "unknown")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        transform = frame.get("transform") or {}
        scale_x = float(transform.get("scaleX") or 0.0)
        scale_y = float(transform.get("scaleY") or 0.0)
        if scale_x > 0.0:
            scale_ratios.append(scale_y / scale_x)
    for source_key, count in sorted(source_counts.items()):
        source_w, source_h = parse_size(source_key)
        examples.append(
            {
                "source_size": source_key,
                "frame_count": count,
                "source_aspect": source_w / source_h if source_h else None,
                "current_fixed_input": f"{input_w}x{input_h}",
                "current_fixed_aspect": input_w / input_h if input_h else None,
                "official_upper_bound_process_res": process_res,
                "official_upper_bound_resize_shape": official_upper_bound_resize_shape(
                    source_w,
                    source_h,
                    process_res,
                ),
                "official_long_side_needed_to_match_height": official_long_side_for_target_height(
                    source_w,
                    source_h,
                    input_h,
                ),
                "shape_can_be_exact_aspect_preserving_resize": aspect_close(
                    source_w / source_h,
                    input_w / input_h,
                )
                if source_h and input_h
                else False,
            }
        )
    exact_possible = all(item["shape_can_be_exact_aspect_preserving_resize"] for item in examples)
    local_sweep_evidence = script_evidence(args.stage_scripts_dir)
    status = (
        "fixed_476x742_shape_not_exact_official_preprocess_for_16x9_sources"
        if not exact_possible and mode_counts.get("direct_stretch") == len(frames)
        else "fixed_shape_preprocess_authority_needs_manual_review"
    )
    return {
        "schema_version": "aether_da3_fixed_shape_preprocess_authority_audit_v1",
        "date": args.date,
        "decision": {
            "status": status,
            "goal_complete": False,
            "official_algorithm_blame_supported": False,
            "fixed_shape_can_equal_official_aspect_preserving_resize": exact_possible,
            "current_manifest_all_direct_stretch": mode_counts.get("direct_stretch") == len(frames),
            "fixed_shape_source": "local_coreml_quality_sweep_not_official_api_default",
            "conclusion": (
                "For this strict capture, the fixed 742x476 CoreML image tensor cannot be the exact output of "
                "official aspect-preserving upper_bound_resize for 16:9 source frames. Official long-side-742 "
                "resize lands at 742x420 after patch rounding, while the current manifest uses direct_stretch "
                "to 742x476. This keeps the product-selected fixed model shape runnable, but it is not an "
                "official preprocessing authority."
            ),
            "next_best_action": (
                "Do not sweep more sizes. Treat DA3BASE_476x742_N35 as the product fixed-shape compatibility path, "
                "and isolate official-parity work around image-only cam_dec plus a clearly labeled official-style "
                "preprocess path."
            ),
        },
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "stage_scripts_dir": str(args.stage_scripts_dir),
            "manifest": str(manifest_path),
        },
        "manifest": {
            "frame_count": len(frames),
            "input_size": f"{input_w}x{input_h}",
            "input_aspect": input_w / input_h if input_h else None,
            "mode_counts": mode_counts,
            "source_size_counts": source_counts,
            "median_y_over_x_stretch": median(scale_ratios),
        },
        "official_resize_examples": examples,
        "local_sweep_evidence": local_sweep_evidence,
        "plain_language": [
            "476x742 是一个固定 CoreML 输入形状；它能跑，不等于它就是官方 API 的 preprocess 输出。",
            "这批源图基本是 16:9，官方等比 upper_bound_resize 不会把 16:9 变成 742x476。",
            "当前 Dart manifest 是 direct_stretch，所以 Y 方向相对 X 方向被额外拉伸；这是上游输入合同差异。",
            "因此当前厚层仍不能证明官方原生 DA3 算法有问题；它首先证明我们跑的是固定形状兼容路径。",
            "下一步不要再测尺寸，把 476x742 当产品约束，继续查 image-only cam_dec 和官方 preprocess 的权威路径。",
        ],
    }


def official_upper_bound_resize_shape(source_w: int, source_h: int, process_res: int) -> str:
    if source_w <= 0 or source_h <= 0 or process_res <= 0:
        return "unknown"
    scale = process_res / float(max(source_w, source_h))
    resized_w = max(1, int(round(source_w * scale)))
    resized_h = max(1, int(round(source_h * scale)))
    return f"{nearest_multiple(resized_w, 14)}x{nearest_multiple(resized_h, 14)}"


def official_long_side_for_target_height(source_w: int, source_h: int, target_h: int) -> dict[str, Any]:
    if source_w <= 0 or source_h <= 0 or target_h <= 0:
        return {"process_res": None, "shape": "unknown"}
    process_res = int(round(target_h * max(source_w, source_h) / float(source_h)))
    return {
        "process_res": process_res,
        "shape": official_upper_bound_resize_shape(source_w, source_h, process_res),
    }


def nearest_multiple(value: int, patch: int) -> int:
    down = (value // patch) * patch
    up = down + patch
    return up if abs(up - value) <= abs(value - down) else down


def aspect_close(left: float, right: float, tolerance: float = 1e-3) -> bool:
    return abs(left - right) <= tolerance


def parse_size(raw: str) -> tuple[int, int]:
    width, height = raw.split("x", maxsplit=1)
    return int(width), int(height)


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) * 0.5


def script_evidence(stage_scripts_dir: Path) -> dict[str, Any]:
    files = [
        stage_scripts_dir / "export_da3_pose_coreml.py",
        stage_scripts_dir / "run_476742_neighborhood_sweep_20260525.sh",
    ]
    evidence = []
    for path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        hits = []
        for needle in ("--height", "--width", "K35_476x742", "compare_coreml_quality_rectangular.py"):
            line = find_line(text, needle)
            if line is not None:
                hits.append({"needle": needle, "line": line})
        evidence.append({"path": str(path), "hits": hits})
    return {"files": evidence}


def find_line(text: str, needle: str) -> int | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return index
    return None


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "manifest": report["manifest"],
        "official_resize_examples": report["official_resize_examples"],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 fixed-shape preprocess authority audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['decision']['status']}`",
        f"- exact aspect-preserving resize possible: `{report['decision']['fixed_shape_can_equal_official_aspect_preserving_resize']}`",
        f"- all direct_stretch: `{report['decision']['current_manifest_all_direct_stretch']}`",
        f"- official algorithm blame supported: `{report['decision']['official_algorithm_blame_supported']}`",
        "",
        report["decision"]["conclusion"],
        "",
        "## 大白话",
        "",
    ]
    for item in report["plain_language"]:
        lines.append(f"- {item}")
    manifest = report["manifest"]
    lines.extend(
        [
            "",
            "## Manifest",
            "",
            f"- frame_count: `{manifest['frame_count']}`",
            f"- input_size: `{manifest['input_size']}`",
            f"- input_aspect: `{manifest['input_aspect']:.6f}`",
            f"- median_y_over_x_stretch: `{manifest['median_y_over_x_stretch']:.6f}`",
            f"- mode_counts: `{manifest['mode_counts']}`",
            f"- source_size_counts: `{manifest['source_size_counts']}`",
            "",
            "## Official Resize Examples",
            "",
            "| source | count | current fixed | current aspect | official long-side 742 | long-side needed for height 476 | exact aspect-preserving? |",
            "|---|---:|---:|---:|---:|---|---:|",
        ]
    )
    for item in report["official_resize_examples"]:
        needed = item["official_long_side_needed_to_match_height"]
        lines.append(
            "| {source} | {count} | {fixed} | {aspect:.6f} | {official} | {needed_res}->{needed_shape} | `{exact}` |".format(
                source=item["source_size"],
                count=item["frame_count"],
                fixed=item["current_fixed_input"],
                aspect=item["current_fixed_aspect"],
                official=item["official_upper_bound_resize_shape"],
                needed_res=needed["process_res"],
                needed_shape=needed["shape"],
                exact=item["shape_can_be_exact_aspect_preserving_resize"],
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
