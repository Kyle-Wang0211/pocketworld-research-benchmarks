#!/usr/bin/env python3
"""Audit DA3 upstream geometry alignment across official, Research, and APP code."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from da3_mac_window_export import (  # noqa: E402
    camera_transform_to_opencv_w2c,
    scale_intrinsics,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--official-postprocess-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--app-repo", type=Path, required=True)
    parser.add_argument("--research-repo", type=Path, required=True)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--coreml-model", type=Path)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_upstream_geometry_alignment.json", report)
    write_markdown(
        args.out_dir / "official_da3_upstream_geometry_alignment_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    bundle = read_json(args.capture_dir / "photo_bundle.json")
    input_manifest = maybe_read_json(args.capture_dir / "da3_input_manifest.json")
    depth_index = read_json(args.official_postprocess_dir / "depth_index.json")

    frames_by_id = {str(frame["id"]): frame for frame in bundle.get("frames", [])}
    input_by_id = {
        str(frame["id"]): frame for frame in input_manifest.get("frames", [])
    }
    completed_rows = [
        row
        for row in depth_index.get("frames", [])
        if row.get("status") == "completed" and row.get("predExtrinsicsPath")
    ]

    camera_evidence = audit_camera_convention(
        rows=completed_rows,
        frames_by_id=frames_by_id,
        official_postprocess_dir=args.official_postprocess_dir,
    )
    intrinsics_evidence = audit_intrinsics(
        frames_by_id=frames_by_id,
        input_by_id=input_by_id,
    )
    coreml_evidence = inspect_coreml_signature(args.coreml_model)

    return {
        "schema_version": "aether_official_da3_upstream_geometry_alignment_v1",
        "date": args.date,
        "purpose": (
            "Start upstream DA3 geometry consistency alignment after downstream "
            "overlap-frame duplication was ruled out as the primary K35 thickness cause."
        ),
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "official_postprocess_dir": str(args.official_postprocess_dir),
            "app_repo": str(args.app_repo),
            "research_repo": str(args.research_repo),
            "official_da3_repo": str(args.official_da3_repo),
        },
        "source_evidence": source_evidence(args),
        "numeric_evidence": {
            "camera_convention": camera_evidence,
            "intrinsics": intrinsics_evidence,
            "coreml_signature": coreml_evidence,
        },
        "alignment_matrix": alignment_matrix(
            args, camera_evidence, intrinsics_evidence, coreml_evidence
        ),
        "decision": derive_decision(camera_evidence, intrinsics_evidence, coreml_evidence),
        "next_probes": next_probes(),
    }


def audit_camera_convention(
    *,
    rows: list[dict[str, Any]],
    frames_by_id: dict[str, dict[str, Any]],
    official_postprocess_dir: Path,
) -> dict[str, Any]:
    pred_vs_converted: list[float] = []
    pred_vs_raw_row_major: list[float] = []
    pred_vs_raw_col_major_c2w: list[float] = []
    samples: list[dict[str, Any]] = []

    for row in rows:
        frame_id = str(row["frameID"])
        capture_frame = frames_by_id[frame_id]
        pred = np.fromfile(
            official_postprocess_dir / str(row["predExtrinsicsPath"]),
            dtype="<f4",
        ).reshape(3, 4)
        raw_values = capture_frame["cameraTransform"]
        converted = camera_transform_to_opencv_w2c(raw_values)[:3, :]
        raw_row_major = np.asarray(raw_values, dtype=np.float32).reshape(4, 4)[:3, :]
        raw_col_major_c2w = np.asarray(raw_values, dtype=np.float32).reshape(
            4, 4, order="F"
        )[:3, :]

        converted_diff = max_abs(pred, converted)
        raw_row_diff = max_abs(pred, raw_row_major)
        raw_col_diff = max_abs(pred, raw_col_major_c2w)
        pred_vs_converted.append(converted_diff)
        pred_vs_raw_row_major.append(raw_row_diff)
        pred_vs_raw_col_major_c2w.append(raw_col_diff)

        if len(samples) < 3:
            samples.append(
                {
                    "frameID": frame_id,
                    "pred_first_row": rounded_list(pred[0]),
                    "converted_first_row": rounded_list(converted[0]),
                    "raw_row_major_first_row": rounded_list(raw_row_major[0]),
                    "raw_col_major_c2w_first_row": rounded_list(raw_col_major_c2w[0]),
                    "pred_vs_converted_max_abs": converted_diff,
                    "pred_vs_raw_row_major_max_abs": raw_row_diff,
                    "pred_vs_raw_col_major_c2w_max_abs": raw_col_diff,
                }
            )

    return {
        "completed_rows": len(rows),
        "pred_vs_converted_opencv_w2c_max_abs_max": safe_max(pred_vs_converted),
        "pred_vs_converted_opencv_w2c_max_abs_median": safe_median(pred_vs_converted),
        "pred_vs_raw_row_major_max_abs_median": safe_median(pred_vs_raw_row_major),
        "pred_vs_raw_col_major_c2w_max_abs_median": safe_median(
            pred_vs_raw_col_major_c2w
        ),
        "research_official_postprocess_matches_opencv_w2c": (
            safe_max(pred_vs_converted) is not None
            and safe_max(pred_vs_converted) <= 1e-6
        ),
        "raw_camera_transform_is_not_equivalent_to_official_w2c": (
            safe_median(pred_vs_raw_row_major) is not None
            and safe_median(pred_vs_raw_row_major) > 1e-2
            and safe_median(pred_vs_raw_col_major_c2w) is not None
            and safe_median(pred_vs_raw_col_major_c2w) > 1e-2
        ),
        "samples": samples,
    }


def audit_intrinsics(
    *,
    frames_by_id: dict[str, dict[str, Any]],
    input_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    diffs: list[float] = []
    transform_summary = {
        key: []
        for key in (
            "fxScale",
            "fyScale",
            "cxScale",
            "cyScale",
            "cxOffset",
            "cyOffset",
        )
    }

    for frame_id, frame in frames_by_id.items():
        input_frame = input_by_id.get(frame_id, {})
        height = int(input_frame.get("inputHeight") or 476)
        width = int(input_frame.get("inputWidth") or 742)
        research_ixt = scale_intrinsics(frame, input_frame, height, width)
        app_ixt = app_native_intrinsics_formula(frame, height, width)
        diffs.append(max_abs(research_ixt, app_ixt))

        transform = input_frame.get("intrinsicsTransform") or {}
        for key in transform_summary:
            default = 0.0 if key.endswith("Offset") else 1.0
            transform_summary[key].append(float(transform.get(key, default)))

    return {
        "frame_count": len(frames_by_id),
        "research_scale_intrinsics_vs_app_formula_max_abs_max": safe_max(diffs),
        "research_scale_intrinsics_vs_app_formula_max_abs_median": safe_median(diffs),
        "app_formula_matches_current_direct_stretch_manifest": (
            safe_max(diffs) is not None and safe_max(diffs) <= 1e-6
        ),
        "intrinsics_transform_summary": {
            key: numeric_summary(values)
            for key, values in transform_summary.items()
        },
        "conditional_risk": (
            "APP native makeIntrinsics ignores da3_input_manifest intrinsicsTransform "
            "offsets; current direct_stretch sample has zero offsets, but crop/letterbox "
            "would require explicit transform use."
        ),
    }


def inspect_coreml_signature(model_path: Path | None) -> dict[str, Any]:
    if model_path is None:
        return {
            "model_path": None,
            "available": False,
            "reason": "no --coreml-model provided",
        }
    if not model_path.exists():
        return {
            "model_path": str(model_path),
            "available": False,
            "reason": "model path does not exist",
        }

    try:
        with tempfile.TemporaryDirectory(prefix="da3_coreml_signature_") as tmp:
            out_dir = Path(tmp)
            subprocess.run(
                ["xcrun", "coremlcompiler", "compile", str(model_path), str(out_dir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            metadata_paths = list(out_dir.glob("*.mlmodelc/metadata.json"))
            if not metadata_paths:
                raise FileNotFoundError("compiled metadata.json not found")
            metadata = read_json(metadata_paths[0])
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "model_path": str(model_path),
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    entry = metadata[0] if isinstance(metadata, list) and metadata else {}
    input_schema = list(entry.get("inputSchema") or [])
    output_schema = list(entry.get("outputSchema") or [])
    input_names = [str(row.get("name")) for row in input_schema]
    output_names = [str(row.get("name")) for row in output_schema]
    required_inputs = [
        str(row.get("name"))
        for row in input_schema
        if str(row.get("isOptional")) in ("0", "False", "false", "")
    ]
    return {
        "model_path": str(model_path),
        "available": True,
        "generated_class_name": entry.get("generatedClassName"),
        "input_names": input_names,
        "output_names": output_names,
        "required_inputs": required_inputs,
        "input_shapes": {
            str(row.get("name")): row.get("shape") for row in input_schema
        },
        "output_shapes": {
            str(row.get("name")): row.get("shape") for row in output_schema
        },
        "requires_external_camera_inputs": (
            "extrinsics" in required_inputs and "intrinsics" in required_inputs
        ),
        "is_pose_conditioned_coreml_signature": (
            "image" in required_inputs
            and "extrinsics" in required_inputs
            and "intrinsics" in required_inputs
        ),
    }


def app_native_intrinsics_formula(
    frame: dict[str, Any],
    height: int,
    width: int,
) -> np.ndarray:
    values = frame.get("intrinsics") or []
    original_width = float(frame.get("imageWidth") or width)
    original_height = float(frame.get("imageHeight") or height)
    sx = float(width) / max(original_width, 1.0)
    sy = float(height) / max(original_height, 1.0)

    if len(values) == 9:
        mat = np.asarray(values, dtype=np.float32).reshape(3, 3).copy()
        mat[0, :] *= sx
        mat[1, :] *= sy
        return mat
    if len(values) >= 4:
        fx, fy, cx, cy = [float(value) for value in values[:4]]
        return np.asarray(
            [[fx * sx, 0.0, cx * sx], [0.0, fy * sy, cy * sy], [0.0, 0.0, 1.0]],
            dtype=np.float32,
        )
    return np.asarray(
        [[float(width), 0.0, float(width) * 0.5], [0.0, float(height), float(height) * 0.5], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def source_evidence(args: argparse.Namespace) -> dict[str, list[str]]:
    return {
        "official_da3": [
            str(args.official_da3_repo / "README.md")
            + ":20-21 DA3 supports arbitrary visual inputs with or without known camera poses",
            str(args.official_da3_repo / "docs/API.md")
            + ":200-209 extrinsics/intrinsics are optional pose-conditioned inputs",
            str(args.official_da3_repo / "da3_streaming/da3_streaming.py")
            + ":253-274 DA3-Streaming calls model.inference(images, ref_view_strategy=...) without external cameras",
            str(args.official_da3_repo / "da3_streaming/da3_streaming.py")
            + ":880-915 DA3-Streaming CLI accepts image_dir/config/output_dir, not AR/VIO camera files",
            str(args.official_da3_repo / "src/depth_anything_3/api.py")
            + ":195-218 preprocess -> prepare -> normalize extrinsics -> forward -> align to input camera",
            str(args.official_da3_repo / "src/depth_anything_3/api.py")
            + ":327-339 first-frame inverse + median camera-distance normalization",
            str(args.official_da3_repo / "src/depth_anything_3/api.py")
            + ":341-365 Umeyama alignment, ransac for >=10 views, depth divided by pose scale",
            str(args.official_da3_repo / "src/depth_anything_3/utils/io/input_processor.py")
            + ":219-257 resize, patch-size alignment, intrinsics resize/crop, ImageNet normalization",
            str(args.official_da3_repo / "src/depth_anything_3/model/dinov2/vision_transformer.py")
            + ":314-338 saddle_balanced reference selection and alternating local/global attention",
        ],
        "research": [
            str(args.research_repo / "tools/python/da3_mac_window_export.py")
            + ":311-315 camera_transform_to_opencv_w2c",
            str(args.research_repo / "tools/python/da3_mac_window_export.py")
            + ":318-352 scale_intrinsics using intrinsicsTransform when present",
            str(args.research_repo / "tools/python/make_official_pytorch_window_manifest.py")
            + ":104-114 writes cameraExtrinsic4x4 with extrinsicConvention=opencv_w2c",
            str(args.research_repo / "tools/python/coreml_official_postprocess_export.py")
            + ":66-85 mirrors official Umeyama + depth scale postprocess",
        ],
        "app": [
            str(args.app_repo / "lib/pipeline/local_pipeline_runner.dart")
            + ":2451-2465 copies photo_bundle cameraTransform/intrinsics into Da3DepthFrameSpec",
            str(args.app_repo / "ios/Runner/Da3DepthPlugin.swift")
            + ":595-623 makeExtrinsics copies frames[].cameraTransform as-is",
            str(args.app_repo / "ios/Runner/Da3DepthPlugin.swift")
            + ":625-671 makeIntrinsics scales by original image size to locked input size",
            str(args.app_repo / "ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage")
            + " CoreML signature requires image/extrinsics/intrinsics",
            str(args.app_repo / "lib/capture/dome/captured_frame_sample.dart")
            + ":105-115 ARKit/IMU pose is guidance metadata; reconstruction pose should be solved from images independently",
            str(args.app_repo / "lib/pipeline/local_pipeline_runner.dart")
            + ":2953-2961 declares photos_depth direct_stretch fixed input preprocessing",
        ],
    }


def alignment_matrix(
    args: argparse.Namespace,
    camera_evidence: dict[str, Any],
    intrinsics_evidence: dict[str, Any],
    coreml_evidence: dict[str, Any],
) -> list[dict[str, str]]:
    _ = args
    official_streaming_status = (
        "open_high_risk"
        if coreml_evidence.get("is_pose_conditioned_coreml_signature")
        else "needs_coreml_signature"
    )
    intrinsics_status = (
        "currently_matched_for_direct_stretch"
        if intrinsics_evidence.get("app_formula_matches_current_direct_stretch_manifest")
        else "open"
    )
    return [
        {
            "official_step": "DA3-Streaming inference input contract",
            "official_behavior": "image paths only; model.inference(images, ref_view_strategy=...) lets DA3 estimate pose/intrinsics",
            "research_state": "current Mac/CoreML exporter follows the existing pose-conditioned CoreML model",
            "app_state": "current CoreML model requires image/extrinsics/intrinsics and APP supplies ARKit metadata",
            "status": official_streaming_status,
            "next_probe": "export/use image-only DA3-BASE CoreML for official streaming parity, or label pose-conditioned CoreML as a non-default DA3 mode",
        },
        {
            "official_step": "image preprocessing",
            "official_behavior": "upper_bound_resize/crop variants, patch-14 divisibility, ImageNet RGB normalization",
            "research_state": "fixed photos_depth parity path and highres official dynamic path both documented",
            "app_state": "locked K35@476x742 photos_depth direct_stretch + native sRGB/ImageNet tensor",
            "status": "intentional_mobile_difference",
            "next_probe": "pixel/tensor parity between photos_depth, native CoreGraphics decode, and official InputProcessor for the same frame",
        },
        {
            "official_step": "camera extrinsics input",
            "official_behavior": "official streaming default does not provide external extrinsics; optional API pose-conditioned mode expects world-to-camera extrinsics",
            "research_state": "if pose-conditioned mode is intentionally used, Research conversion to OpenCV w2c is correct",
            "app_state": "native makeExtrinsics copies ARKit camera-to-world metadata as-is",
            "status": "not_official_streaming_default",
            "next_probe": "remove external camera inputs from the official baseline; conversion is only relevant for a separately labeled pose-conditioned experiment",
        },
        {
            "official_step": "intrinsics input",
            "official_behavior": "official streaming default predicts intrinsics; optional API pose-conditioned mode accepts intrinsics",
            "research_state": "scale_intrinsics honors da3_input_manifest.intrinsicsTransform",
            "app_state": "native makeIntrinsics scales by source image size and fixed input size",
            "status": intrinsics_status,
            "next_probe": "do not feed ARKit intrinsics in official streaming baseline; keep intrinsics only as metadata or pose-conditioned experiment input",
        },
        {
            "official_step": "reference view and attention",
            "official_behavior": "saddle_balanced reference view selection and alternating local/global attention",
            "research_state": "PyTorch low-res probes exist; full same-resolution K35 blocked by local MPS memory",
            "app_state": "sealed CoreML graph behavior is not directly inspectable",
            "status": "blocked_by_fullres_reference_gate",
            "next_probe": "run full same-resolution PyTorch K35 on larger CUDA memory or wait for official memory-efficient path",
        },
        {
            "official_step": "pose/depth scale postprocess",
            "official_behavior": "image-only streaming keeps DA3-predicted camera outputs, then aligns chunks by Sim3; input-camera Umeyama only applies to optional pose-conditioned API mode",
            "research_state": "coreml_official_postprocess_export mirrors pose-conditioned API semantics, not streaming default semantics",
            "app_state": "APP downstream currently consumes pose-conditioned CoreML outputs",
            "status": "must_rebaseline_for_streaming_default",
            "next_probe": "build image-only DA3 reference outputs and rerun core-frame npz downstream before judging product cleanup",
        },
    ]


def derive_decision(
    camera_evidence: dict[str, Any],
    intrinsics_evidence: dict[str, Any],
    coreml_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "start_upstream_geometry_alignment_now": True,
        "thickness_current_attribution": "within_window_upstream_geometry_consistency",
        "official_streaming_default_uses_external_camera_inputs": False,
        "official_api_supports_optional_pose_conditioned_mode": True,
        "current_app_coreml_is_pose_conditioned": coreml_evidence.get(
            "is_pose_conditioned_coreml_signature"
        ),
        "highest_priority_gap": "app_pose_conditioned_coreml_vs_official_streaming_image_only_contract",
        "research_camera_path_matches_official_converted_input": camera_evidence.get(
            "research_official_postprocess_matches_opencv_w2c"
        ),
        "raw_camera_transform_not_equal_to_official_w2c": camera_evidence.get(
            "raw_camera_transform_is_not_equivalent_to_official_w2c"
        ),
        "current_intrinsics_formula_matches_direct_stretch_manifest": intrinsics_evidence.get(
            "app_formula_matches_current_direct_stretch_manifest"
        ),
        "camera_transform_conversion_only_relevant_if_pose_conditioned_mode_is_intentional": True,
        "required_official_baseline_action": (
            "Export/use an image-only DA3-BASE CoreML path matching official DA3-Streaming, "
            "or keep the current CoreML path explicitly labeled as optional pose-conditioned DA3 mode."
        ),
        "do_not_add_product_cleanup_yet": True,
        "not_complete_reason": (
            "full same-resolution PyTorch K35 hard parity is still blocked, and APP/Research "
            "currently use a pose-conditioned CoreML model rather than the official DA3-Streaming "
            "image-only default input contract."
        ),
    }


def next_probes() -> list[str]:
    return [
        "Export or obtain a DA3-BASE K35@476x742 image-only CoreML model whose signature does not require extrinsics/intrinsics.",
        "Run a same-window image-only PyTorch reference and compare it against current pose-conditioned CoreML to quantify how much AR/VIO conditioning changes thickness.",
        "Keep ARKit/VIO data in photo_bundle metadata only; do not feed it into the official DA3-Streaming baseline.",
        "If a pose-conditioned experiment is retained, label it separately and convert ARKit camera-to-world to OpenCV world-to-camera before model input.",
        "Pixel/tensor preprocessing parity: compare APP photos_depth/CoreGraphics normalized tensor to official InputProcessor output for the same fixed image.",
        "Full same-resolution PyTorch K35 reference gate on larger CUDA memory or official memory-efficient attention.",
    ]


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines: list[str] = []
    decision = report["decision"]
    cam = report["numeric_evidence"]["camera_convention"]
    intr = report["numeric_evidence"]["intrinsics"]
    coreml = report["numeric_evidence"]["coreml_signature"]

    lines.extend(
        [
            "# Official DA3 upstream geometry alignment audit",
            "",
            f"日期：{report['date']}",
            "",
            "## 当前结论",
            "",
            "可以开始查 DA3 上游几何一致性，而且现在就应该查。",
            "",
            "下游 overlap-frame duplicate 不是主因之后，单个 K35 window 内同一表面变厚，当前最像 upstream depth/pose/scale/camera consistency 问题。根据官方 DA3-Streaming 默认入口，最高优先级不是把 ARKit 矩阵转成另一个坐标系，而是先把 DA3 inference 输入契约改回官方 image-only streaming baseline。",
            "",
            "官方 DA3 API 支持两种模式：不提供相机时走标准 depth/pose estimation；提供 `extrinsics/intrinsics` 时走 pose-conditioned mode。官方 DA3-Streaming 默认代码调用的是 `model.inference(images, ref_view_strategy=...)`，CLI 也只收 `--image_dir`，没有 AR/VIO/camera 文件输入。",
            "",
            "本次 audit 的最强信号：当前 APP/CoreML 不是官方 streaming 默认入口。`DA3BASE_476x742_N35_pose.mlpackage` 的 CoreML signature 必填 `image/extrinsics/intrinsics`，而 APP native 会把 ARKit `cameraTransform` 作为 `extrinsics` 输入。这只能算 pose-conditioned DA3 派生实验，不能继续冒充官方 DA3-Streaming baseline。",
            "",
            "## 数字证据",
            "",
            "| Check | Result | Interpretation |",
            "|---|---:|---|",
            f"| completed rows checked | {cam['completed_rows']} | 全序列官方 postprocess 样本 |",
            f"| pred extrinsics vs converted OpenCV w2c max abs max | {fmt(cam['pred_vs_converted_opencv_w2c_max_abs_max'])} | Research official postprocess 等于转换后的相机 |",
            f"| pred extrinsics vs raw row-major cameraTransform median max abs | {fmt(cam['pred_vs_raw_row_major_max_abs_median'])} | raw 矩阵不等于官方相机输入 |",
            f"| pred extrinsics vs raw column-major c2w median max abs | {fmt(cam['pred_vs_raw_col_major_c2w_max_abs_median'])} | ARKit c2w 也不能直接当官方 w2c |",
            f"| intrinsics Research vs APP formula max abs max | {fmt(intr['research_scale_intrinsics_vs_app_formula_max_abs_max'])} | 当前 direct_stretch 样本 intrinsics 对齐 |",
            f"| current CoreML required inputs | {', '.join(coreml.get('required_inputs') or [])} | 当前模型是 pose-conditioned signature |",
            "",
            "camera conversion 证据仍然有用，但它的适用范围变窄了：如果我们故意跑 pose-conditioned DA3，Research 的 OpenCV w2c 转换才是正确方向；如果我们复刻官方 DA3-Streaming 默认算法，就不应该把 ARKit/VIO 相机喂给 DA3。",
            "",
            "intrinsics 这项当前不是最大嫌疑：`intrinsicsTransform` 的 offset 全是 0，APP 原图尺寸缩放公式与 Research `scale_intrinsics` 完全一致。但 official streaming baseline 应该让 DA3 自己预测 intrinsics；ARKit intrinsics 只能作为 metadata 或 pose-conditioned experiment 输入。",
            "",
            "## Source Evidence",
            "",
        ]
    )
    for group, rows in report["source_evidence"].items():
        lines.append(f"### {group}")
        lines.append("")
        for row in rows:
            lines.append(f"- `{row}`")
        lines.append("")

    lines.extend(
        [
            "## Alignment Matrix",
            "",
            "| Official step | Research state | APP state | Status | Next probe |",
            "|---|---|---|---|---|",
        ]
    )
    for row in report["alignment_matrix"]:
        lines.append(
            "| {official_step} | {research_state} | {app_state} | {status} | {next_probe} |".format(
                **{key: escape_table(str(value)) for key, value in row.items()}
            )
        )

    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- `start_upstream_geometry_alignment_now`: `{decision['start_upstream_geometry_alignment_now']}`",
            f"- `thickness_current_attribution`: `{decision['thickness_current_attribution']}`",
            f"- `official_streaming_default_uses_external_camera_inputs`: `{decision['official_streaming_default_uses_external_camera_inputs']}`",
            f"- `current_app_coreml_is_pose_conditioned`: `{decision['current_app_coreml_is_pose_conditioned']}`",
            f"- `highest_priority_gap`: `{decision['highest_priority_gap']}`",
            f"- `research_camera_path_matches_official_converted_input`: `{decision['research_camera_path_matches_official_converted_input']}`",
            f"- `raw_camera_transform_not_equal_to_official_w2c`: `{decision['raw_camera_transform_not_equal_to_official_w2c']}`",
            f"- `current_intrinsics_formula_matches_direct_stretch_manifest`: `{decision['current_intrinsics_formula_matches_direct_stretch_manifest']}`",
            f"- `required_official_baseline_action`: `{decision['required_official_baseline_action']}`",
            f"- `do_not_add_product_cleanup_yet`: `{decision['do_not_add_product_cleanup_yet']}`",
            "",
            "目标仍不能 complete：full same-resolution PyTorch K35 hard parity 还没关闭，并且 APP/Research 当前用的是 pose-conditioned CoreML，不是官方 DA3-Streaming image-only 默认输入契约。",
            "",
            "## Next Probes",
            "",
        ]
    )
    for idx, probe in enumerate(report["next_probes"], start=1):
        lines.append(f"{idx}. {probe}")

    lines.extend(
        [
            "",
            "## 大白话",
            "",
            "现在的问题不像是“点云最后合并时多加了几层”，而更像是“模型上游几帧对同一面墙的深度/相机没有完全压到同一个几何面”。",
            "",
            "你这个纠正是对的：如果官方 DA3-Streaming 原生算法不带 AR mode 采集数据，我们就不应该带。当前 APP 把 ARKit pose 喂进 CoreML，不是“更官方”，而是切到了官方 API 支持的另一个 pose-conditioned mode。",
            "",
            "所以下一刀很明确：先拿到 image-only DA3-BASE CoreML 或用 PyTorch image-only reference 重跑 K35，再判断厚层是不是官方 DA3 本身的限制。ARKit/VIO 先退回 metadata 和后处理产品层。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "camera_convention": {
            key: report["numeric_evidence"]["camera_convention"][key]
            for key in (
                "completed_rows",
                "pred_vs_converted_opencv_w2c_max_abs_max",
                "pred_vs_raw_row_major_max_abs_median",
                "pred_vs_raw_col_major_c2w_max_abs_median",
                "research_official_postprocess_matches_opencv_w2c",
                "raw_camera_transform_is_not_equivalent_to_official_w2c",
            )
        },
        "coreml_signature": report["numeric_evidence"]["coreml_signature"],
        "intrinsics": {
            key: report["numeric_evidence"]["intrinsics"][key]
            for key in (
                "research_scale_intrinsics_vs_app_formula_max_abs_max",
                "app_formula_matches_current_direct_stretch_manifest",
            )
        },
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def maybe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def max_abs(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.max(np.abs(left - right)))


def safe_max(values: list[float]) -> float | None:
    return max(values) if values else None


def safe_median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.median(np.asarray(values, dtype=np.float64)))


def numeric_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"min": None, "max": None, "unique_first5": []}
    return {
        "min": min(values),
        "max": max(values),
        "unique_first5": sorted({round(value, 8) for value in values})[:5],
    }


def rounded_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.round(values.astype(np.float64), 5).tolist()]


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.9g}"
    return str(value)


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
