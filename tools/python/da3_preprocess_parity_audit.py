#!/usr/bin/env python3
"""Audit DA3 image preprocessing parity for the fixed K35@476x742 target."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--research-repo", type=Path, required=True)
    parser.add_argument("--app-repo", type=Path, required=True)
    parser.add_argument("--capture-services-dir", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_preprocess_parity_audit.json", report)
    write_markdown(args.out_dir / "official_da3_preprocess_parity_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official = inspect_official(args.official_da3_repo)
    current = inspect_current(args)
    decision = derive_decision(official, current)
    return {
        "schema_version": "aether_official_da3_preprocess_parity_audit_v1",
        "date": args.date,
        "purpose": (
            "Separate official DA3 API preprocessing from the fixed CoreML "
            "K35@476x742 same-input parity path."
        ),
        "fixed_target": {
            "window_size": 35,
            "height": 476,
            "width": 742,
            "patch_size": 14,
            "patch_grid": [34, 53],
            "shape_is_patch_aligned": True,
            "dimension_sweep": "disabled",
        },
        "official": official,
        "current_project": current,
        "decision": decision,
    }


def inspect_official(repo: Path) -> dict[str, Any]:
    input_processor = repo / "src/depth_anything_3/utils/io/input_processor.py"
    api = repo / "src/depth_anything_3/api.py"
    return {
        "api_defaults": {
            "process_res": source_hit(api, "process_res: int = 504"),
            "process_res_method": source_hit(api, 'process_res_method: str = "upper_bound_resize"'),
        },
        "input_processor": {
            "pipeline_doc": source_hit(input_processor, "Boundary resize (upper/lower bound, preserving aspect ratio)"),
            "patch_size": source_hit(input_processor, "PATCH_SIZE = 14"),
            "normalize": source_hit(input_processor, "NORMALIZE = T.Normalize"),
            "load_rgb": source_hit(input_processor, 'return Image.open(img).convert("RGB")'),
            "longest_side_resize": source_hit(input_processor, "return self._resize_longest_side(img, target_size)"),
            "cv2_interpolation": source_hit(input_processor, "interpolation = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA"),
            "make_divisible_resize": source_hit(input_processor, "pil_img = self._make_divisible_by_resize(pil_img, self.PATCH_SIZE)"),
            "nearest_multiple": source_hit(input_processor, "def nearest_multiple(x: int, p: int) -> int:"),
        },
        "meaning": (
            "Official model.inference defaults to upper_bound_resize: preserve aspect "
            "ratio, round dimensions to a 14-pixel patch multiple, convert to RGB, "
            "ToTensor, then ImageNet normalize."
        ),
    }


def inspect_current(args: argparse.Namespace) -> dict[str, Any]:
    app_native = args.app_repo / "ios/Runner/Da3DepthPlugin.swift"
    app_runner = args.app_repo / "lib/pipeline/local_pipeline_runner.dart"
    policy = args.capture_services_dir / "lib/src/photo_bundle_pipeline_policy_service.dart"
    research_export = args.research_repo / "tools/python/da3_mac_window_export.py"
    manifest_builder = args.research_repo / "tools/python/make_official_pytorch_window_manifest.py"
    da3_manifest = read_json_or_empty(args.capture_dir / "da3_input_manifest.json")
    model_policy = read_json_or_empty(args.capture_dir / "model_policy.json")
    frame0 = (da3_manifest.get("frames") or [{}])[0]
    return {
        "capture_dir": str(args.capture_dir),
        "manifest_frame0": summarize_frame(frame0),
        "model_policy_selected": (model_policy.get("selectedDepthModel") or {}),
        "app_policy": {
            "fixed_model": source_hit(policy, "static const da3BaseK35_476x742"),
            "resize_contract": source_hit(policy, "dart_photos_depth_direct_stretch"),
            "normalization_contract": source_hit(policy, "'normalization': 'imagenet_rgb'"),
        },
        "app_native": {
            "requires_already_fixed": source_hit(app_native, "DA3 imagePath must already be"),
            "cgcontext_srgb": source_hit(app_native, "CGColorSpace(name: CGColorSpace.sRGB)"),
            "normalize_mean": source_hit(app_native, "let meanR: Float = 0.485"),
            "normalize_write": source_hit(app_native, "ptr[viewBase + 0 * planeSize + dst] = (r - meanR) / stdR"),
        },
        "research_exporter": {
            "pil_exif_rgb": source_hit(research_export, "ImageOps.exif_transpose(image).convert(\"RGB\")"),
            "bicubic_resize": source_hit(research_export, "image.resize((width, height), Image.Resampling.BICUBIC)"),
            "imagenet_normalize": source_hit(research_export, "arr = (arr - IMAGENET_MEAN) / IMAGENET_STD"),
        },
        "pytorch_manifest": {
            "photos_depth_role": source_hit(manifest_builder, "photos_depth uses the APP fixed 742x476 input"),
            "photos_highres_role": source_hit(manifest_builder, "photos_highres lets official PyTorch do dynamic upper_bound_resize"),
            "fixed_contract": source_hit(manifest_builder, "already_fixed_742x476_then_upper_bound_resize_no_shape_change"),
            "highres_contract": source_hit(manifest_builder, "official_dynamic_aspect_ratio_reference"),
        },
    }


def summarize_frame(frame: dict[str, Any]) -> dict[str, Any]:
    transform = frame.get("transform") or {}
    intr = frame.get("intrinsicsTransform") or {}
    resize = frame.get("resize") or {}
    return {
        "id": frame.get("id"),
        "sourceWidth": frame.get("sourceWidth"),
        "sourceHeight": frame.get("sourceHeight"),
        "inputWidth": frame.get("inputWidth"),
        "inputHeight": frame.get("inputHeight"),
        "depthImageRelativePath": frame.get("depthImageRelativePath"),
        "resize": resize,
        "transform": transform,
        "intrinsicsTransform": intr,
        "scaleX": transform.get("scaleX"),
        "scaleY": transform.get("scaleY"),
        "aspect_preserving": same_float(transform.get("scaleX"), transform.get("scaleY")),
    }


def derive_decision(official: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    frame0 = current.get("manifest_frame0") or {}
    return {
        "official_api_preprocess": "aspect_preserving_upper_bound_resize_then_patch14_then_imagenet",
        "fixed_coreml_preprocess": "photos_depth_direct_stretch_742x476_then_imagenet",
        "shape_parity": "pass_476x742_is_patch14_aligned",
        "tensor_parity_risk": (
            "photos_depth direct_stretch is not identical to official API "
            "upper_bound_resize from highres images"
        ),
        "current_frame0_aspect_preserving": frame0.get("aspect_preserving"),
        "current_frame0_scale_x": frame0.get("scaleX"),
        "current_frame0_scale_y": frame0.get("scaleY"),
        "baseline_rule": (
            "Use photos_depth for CoreML-vs-PyTorch same-input parity; use photos_highres "
            "only when asking what official API dynamic preprocessing would do."
        ),
        "impact_on_thickness_test": (
            "The image-only overlap regression gate must state which preprocessing "
            "baseline produced the image tensor. Mixing photos_depth and photos_highres "
            "can make a thickness comparison inconclusive."
        ),
        "do_next": [
            "Keep DA3BASE_476x742_N35 fixed for APP/CoreML parity.",
            "When target image-only CoreML exists, run overlap regression on photos_depth same-input parity first.",
            "Separately run official PyTorch image-only on photos_highres/dynamic preprocessing if memory allows, and label it as official API reference, not same-input CoreML parity.",
            "Do not claim exact official API preprocessing parity for direct_stretch photos_depth.",
        ],
    }


def source_hit(path: Path, needle: str) -> dict[str, Any]:
    text = read_text(path)
    for index, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return {
                "path": str(path),
                "line": index,
                "needle": needle,
                "text": line.strip(),
            }
    return {
        "path": str(path),
        "line": None,
        "needle": needle,
        "text": None,
    }


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "fixed_target": report["fixed_target"],
        "decision": report["decision"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    fixed = report["fixed_target"]
    official = report["official"]
    current = report["current_project"]
    decision = report["decision"]
    frame0 = current["manifest_frame0"]
    lines = [
        "# Official DA3 preprocess parity audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        "- `DA3BASE_476x742_N35` 固定目标本身是 patch-aligned：476 和 742 都能被 14 整除。",
        "- 官方 API 默认预处理是 aspect-preserving `upper_bound_resize`，再 round 到 patch-14 multiple，再 ImageNet normalize。",
        "- 当前 APP/CoreML 固定输入使用 `photos_depth`：从高分图直接拉伸到 `742x476`，再 ImageNet normalize。",
        "- 因此 `photos_depth` 是 CoreML/PyTorch same-input parity baseline；它不是官方 API dynamic preprocessing 的百分百等价物。",
        "- 厚层回归实验必须标明使用 `photos_depth` 还是 `photos_highres`，不能混着比较。",
        "",
        "## 固定目标",
        "",
        f"- window size: `{fixed['window_size']}`",
        f"- shape: `{fixed['height']}x{fixed['width']}`",
        f"- patch size: `{fixed['patch_size']}`",
        f"- patch grid: `{fixed['patch_grid'][0]}x{fixed['patch_grid'][1]}`",
        f"- dimension sweep: `{fixed['dimension_sweep']}`",
        "",
        "## 官方预处理证据",
        "",
        hit_line(official["api_defaults"]["process_res"]),
        hit_line(official["api_defaults"]["process_res_method"]),
        hit_line(official["input_processor"]["pipeline_doc"]),
        hit_line(official["input_processor"]["patch_size"]),
        hit_line(official["input_processor"]["longest_side_resize"]),
        hit_line(official["input_processor"]["cv2_interpolation"]),
        hit_line(official["input_processor"]["make_divisible_resize"]),
        hit_line(official["input_processor"]["normalize"]),
        "",
        "## 当前输入证据",
        "",
        f"- frame0 source: `{frame0.get('sourceWidth')}x{frame0.get('sourceHeight')}`",
        f"- frame0 input: `{frame0.get('inputWidth')}x{frame0.get('inputHeight')}`",
        f"- frame0 resize: `{json.dumps(frame0.get('resize'), ensure_ascii=False)}`",
        f"- frame0 scaleX/scaleY: `{frame0.get('scaleX')}` / `{frame0.get('scaleY')}`",
        f"- aspect preserving: `{frame0.get('aspect_preserving')}`",
        "",
        hit_line(current["app_policy"]["resize_contract"]),
        hit_line(current["app_native"]["requires_already_fixed"]),
        hit_line(current["app_native"]["normalize_write"]),
        hit_line(current["research_exporter"]["bicubic_resize"]),
        hit_line(current["research_exporter"]["imagenet_normalize"]),
        "",
        "## Research 已经区分的两种基线",
        "",
        hit_line(current["pytorch_manifest"]["photos_depth_role"]),
        hit_line(current["pytorch_manifest"]["photos_highres_role"]),
        hit_line(current["pytorch_manifest"]["fixed_contract"]),
        hit_line(current["pytorch_manifest"]["highres_contract"]),
        "",
        "## 判读规则",
        "",
        f"- official API preprocess: `{decision['official_api_preprocess']}`",
        f"- fixed CoreML preprocess: `{decision['fixed_coreml_preprocess']}`",
        f"- shape parity: `{decision['shape_parity']}`",
        f"- tensor parity risk: `{decision['tensor_parity_risk']}`",
        f"- baseline rule: `{decision['baseline_rule']}`",
        f"- impact on thickness test: `{decision['impact_on_thickness_test']}`",
        "",
        "## 下一步",
        "",
    ]
    for index, item in enumerate(decision["do_next"], start=1):
        lines.append(f"{index}. {item}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def hit_line(hit: dict[str, Any]) -> str:
    if hit.get("line") is None:
        return f"- `{hit.get('path')}`: missing `{hit.get('needle')}`"
    return f"- `{hit.get('path')}:{hit.get('line')}`: `{hit.get('text')}`"


def same_float(a: Any, b: Any, eps: float = 1e-9) -> bool | None:
    try:
        return abs(float(a) - float(b)) <= eps
    except (TypeError, ValueError):
        return None


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
