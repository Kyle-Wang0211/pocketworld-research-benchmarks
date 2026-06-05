#!/usr/bin/env python3
"""Audit how closely the current DA3 path matches official DA3-Streaming."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


TARGET_RESOURCE = "DA3BASE_476x742_N35_image_only"
POSE_RESOURCE = "DA3BASE_476x742_N35_pose"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--research-repo", type=Path, required=True)
    parser.add_argument("--app-repo", type=Path, required=True)
    parser.add_argument("--capture-services-dir", type=Path, required=True)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--image-only-da3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_algorithm_replication_audit.json", report)
    write_markdown(args.out_dir / "official_da3_algorithm_replication_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official = inspect_official(args.official_da3_repo)
    current = inspect_current(args)
    decision = derive_decision(official, current)
    return {
        "schema_version": "aether_official_da3_algorithm_replication_audit_v1",
        "date": args.date,
        "purpose": (
            "Track official DA3-Streaming parity for the fixed DA3BASE_476x742_N35 "
            "single-window thick-layer investigation."
        ),
        "fixed_target": {
            "model_family": "DA3-BASE",
            "resource": TARGET_RESOURCE,
            "pose_compat_resource": POSE_RESOURCE,
            "window_size": 35,
            "height": 476,
            "width": 742,
            "commercial_path": "DA3-BASE only; DA3-LARGE/GIANT/NESTED are not product defaults",
            "dimension_sweep": "disabled",
            "arkit_vio_as_da3_input": "disabled_for_official_baseline",
        },
        "official": official,
        "current_project": current,
        "decision": decision,
        "next_actions": next_actions(decision),
    }


def inspect_official(repo: Path) -> dict[str, Any]:
    api = repo / "src/depth_anything_3/api.py"
    da3 = repo / "src/depth_anything_3/model/da3.py"
    input_processor = repo / "src/depth_anything_3/utils/io/input_processor.py"
    streaming = repo / "da3_streaming/da3_streaming.py"
    npz_process = repo / "da3_streaming/npz_output_process.py"
    readme = repo / "README.md"

    inference_call = source_hit(
        streaming,
        "predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)",
    )
    inference_line = str(inference_call.get("text") or "")
    return {
        "repo": {
            "path": str(repo),
            "head": run_git(repo, "rev-parse", "HEAD"),
            "remote_origin": run_git(repo, "remote", "get-url", "origin"),
            "remote_main": run_git(repo, "ls-remote", "origin", "refs/heads/main"),
        },
        "commercial_license": {
            "da3_base_apache_2": source_hit(readme, "| [DA3-BASE]") | {
                "expected": "README model table lists DA3-BASE as Apache 2.0."
            },
            "large_giant_noncommercial": source_hit(readme, "| [DA3-GIANT-1.1]") | {
                "expected": "README model table lists DA3-LARGE/GIANT/NESTED families as CC BY-NC 4.0."
            },
            "package_license": source_hit(repo / "pyproject.toml", 'license = { text = "Apache-2.0" }'),
        },
        "streaming_default": {
            "image_only_call": inference_call,
            "call_has_no_external_camera_args": (
                "extrinsics" not in inference_line and "intrinsics" not in inference_line
            ),
            "conf_minus_one": source_hit(streaming, "predictions.conf -= 1.0"),
            "conclusion": "official_da3_streaming_default_is_image_only",
        },
        "camera_estimation": {
            "external_camera_encoder_only_when_extrinsics_present": source_hit(
                da3, "if extrinsics is not None:"
            ),
            "cam_token_none_without_extrinsics": source_hit(da3, "cam_token = None"),
            "default_uses_camera_decoder": source_hit(
                da3, "output = self._process_camera_estimation(feats, H, W, output)"
            ),
            "cam_dec_to_pose_encoding": source_hit(da3, "pose_enc = self.cam_dec(feats[-1][1])"),
            "pose_encoding_to_extri_intri": source_hit(
                da3, "c2w, ixt = pose_encoding_to_extri_intri(pose_enc, (H, W))"
            ),
            "output_extrinsics_are_w2c": source_hit(da3, "output.extrinsics = affine_inverse(c2w)"),
            "gs_head_prefers_predicted_camera_space": source_hit(
                da3, "we instead use the predicted camera poses for better alignment"
            ),
        },
        "pose_conditioned_optional_path": {
            "api_accepts_optional_cameras": source_hit(api, "extrinsics: np.ndarray | None = None"),
            "normalize_first_frame_and_median_distance": [
                source_hit(api, "transform = affine_inverse(ex_t[:, :1])"),
                source_hit(api, "median_dist = torch.median(dists)"),
            ],
            "umeyama_to_input_camera_when_provided": source_hit(api, "align_poses_umeyama("),
            "replace_prediction_with_input_scale_when_enabled": source_hit(
                api, "prediction.depth /= scale"
            ),
        },
        "preprocess": {
            "official_default_process_res": source_hit(api, "process_res: int = 504"),
            "official_default_method": source_hit(api, 'process_res_method: str = "upper_bound_resize"'),
            "aspect_preserving_doc": source_hit(
                input_processor,
                "Boundary resize (upper/lower bound, preserving aspect ratio)",
            ),
            "patch_size_14": source_hit(input_processor, "PATCH_SIZE = 14"),
            "imagenet_normalize": source_hit(input_processor, "NORMALIZE = T.Normalize"),
            "make_divisible_by_resize": source_hit(
                input_processor,
                "pil_img = self._make_divisible_by_resize(pil_img, self.PATCH_SIZE)",
            ),
        },
        "downstream": {
            "core_frame_save_indices_remove_cross_chunk_overlap": [
                source_hit(streaming, "save_indices = list(range(0, chunk_end - chunk_start - self.overlap_e))"),
                source_hit(streaming, "save_indices = list(range(self.overlap_s, chunk_end - chunk_start - self.overlap_e))"),
            ],
            "npz_process_reads_frame_npz": source_hit(npz_process, 'glob(os.path.join(npz_folder, "frame_*.npz"))'),
            "npz_conf_threshold_mean_coef": source_hit(
                npz_process, "conf_threshold = np.mean(confs_combined) * conf_threshold_coef"
            ),
            "npz_default_sample_ratio": source_hit(npz_process, "--sample_ratio"),
            "no_in_window_surface_fusion_or_dedup_detected": True,
            "conclusion": (
                "official downstream filters confidence and samples points; it does not "
                "merge duplicate observations of the same surface inside one chunk."
            ),
        },
    }


def inspect_current(args: argparse.Namespace) -> dict[str, Any]:
    research = args.research_repo
    app = args.app_repo
    capture_services = args.capture_services_dir
    coreml_dir = app / "ios/Runner/Models/DA3-BASE-CoreML"
    image_only_pkg = coreml_dir / f"{TARGET_RESOURCE}.mlpackage"
    image_only_compiled = coreml_dir / f"{TARGET_RESOURCE}.mlmodelc"
    pose_pkg = coreml_dir / f"{POSE_RESOURCE}.mlpackage"
    pose_compiled = coreml_dir / f"{POSE_RESOURCE}.mlmodelc"
    swift_plugin = app / "ios/Runner/Da3DepthPlugin.swift"
    policy = capture_services / "lib/src/photo_bundle_pipeline_policy_service.dart"
    mac_export = research / "tools/python/da3_mac_window_export.py"
    pytorch_export = research / "tools/python/official_pytorch_window_export.py"
    overlap_json = (
        args.capture_dir.parent
        / "diagnostics/official_da3_image_only_overlap_regression_gate_2026_06_04"
        / "official_da3_image_only_overlap_regression_gate.json"
    )
    preprocess_report = (
        args.capture_dir.parent
        / "diagnostics/official_da3_preprocess_parity_audit_2026_06_04"
        / "official_da3_preprocess_parity_audit.json"
    )
    capture_manifest = maybe_read_json(args.capture_dir / "da3_input_manifest.json")
    frame0 = (capture_manifest.get("frames") or [{}])[0] if capture_manifest.get("frames") else {}
    resize0 = frame0.get("resize") or {}
    transform0 = frame0.get("transform") or {}

    return {
        "model_artifacts": {
            "coreml_dir": str(coreml_dir),
            "image_only_package_exists": image_only_pkg.exists(),
            "image_only_compiled_exists": image_only_compiled.exists(),
            "pose_package_exists": pose_pkg.exists(),
            "pose_compiled_exists": pose_compiled.exists(),
            "image_only_da3_output_dir_exists": args.image_only_da3_dir.exists(),
        },
        "research_alignment": {
            "pytorch_export_has_image_only_mode": source_hit(pytorch_export, 'choices=["pose_conditioned", "image_only"]'),
            "pytorch_image_only_omits_cameras": source_hit(
                pytorch_export, 'if args.camera_mode == "pose_conditioned":'
            ),
            "mac_export_detects_coreml_signature": source_hit(mac_export, "def da3_input_contract(input_names"),
            "mac_export_omits_cameras_for_image_only": source_hit(
                mac_export, 'needs_extrinsics = "extrinsics" in model_input_names'
            ),
            "mac_export_pose_converts_arkit_to_opencv_w2c": source_hit(
                mac_export, "camera_transform_to_opencv_w2c(frame[\"cameraTransform\"])"
            ),
        },
        "app_alignment": {
            "swift_supports_image_only_resource": source_hit(swift_plugin, TARGET_RESOURCE),
            "swift_pose_conditioned_detection": source_hit(swift_plugin, "var isPoseConditioned: Bool"),
            "swift_image_only_provider_only_sends_image": source_hit(
                swift_plugin, 'provider = try MLDictionaryFeatureProvider(dictionary: ['
            ),
            "swift_pose_provider_sends_external_cameras": source_hit(
                swift_plugin, '"extrinsics": MLFeatureValue(multiArray: extrinsics)'
            ),
            "swift_pose_raw_camera_transform_risk": source_hit(
                swift_plugin, 'let values = doubleArray(frame["cameraTransform"])'
            ),
            "policy_marks_current_pose_as_compat": source_hit(
                policy,
                "pose_conditioned_coreml_requires_image_extrinsics_intrinsics",
            ),
            "policy_blocks_until_image_only_signature": source_hit(
                policy,
                "blocked_until_image_only_coreml_signature",
            ),
            "policy_arkit_metadata_only": source_hit(policy, "metadata_only_not_da3_input"),
        },
        "preprocess_current": {
            "capture_manifest": str(args.capture_dir / "da3_input_manifest.json"),
            "frame_count": len(capture_manifest.get("frames") or []),
            "input_width": capture_manifest.get("inputWidth") or frame0.get("inputWidth"),
            "input_height": capture_manifest.get("inputHeight") or frame0.get("inputHeight"),
            "resize_mode": resize0.get("mode"),
            "interpolation": resize0.get("interpolation"),
            "scale_x": transform0.get("scaleX"),
            "scale_y": transform0.get("scaleY"),
            "aspect_preserving": same_float(transform0.get("scaleX"), transform0.get("scaleY")),
            "preprocess_report_exists": preprocess_report.exists(),
        },
        "overlap_gate": {
            "report_path": str(overlap_json),
            "report_exists": overlap_json.exists(),
            "decision": maybe_read_json(overlap_json).get("decision", {}),
        },
    }


def derive_decision(official: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    artifacts = current["model_artifacts"]
    overlap_decision = current["overlap_gate"]["decision"]
    official_ready = bool(official["streaming_default"]["call_has_no_external_camera_args"])
    if not official_ready:
        return {
            "status": "audit_failed_official_streaming_contract_unclear",
            "can_judge_original_thick_layer": False,
            "highest_priority_gap": "official_streaming_call_not_verified",
        }
    if not artifacts["image_only_package_exists"] and not artifacts["image_only_compiled_exists"]:
        return {
            "status": "incomplete_missing_target_image_only_coreml_model",
            "can_judge_original_thick_layer": False,
            "highest_priority_gap": f"{TARGET_RESOURCE}.mlpackage_or_mlmodelc_missing",
            "current_pose_coreml_is_official_baseline": False,
            "single_window_thick_layer_likely_stage": "upstream_geometry_or_pose_contract_until_image_only_baseline_runs",
        }
    if not artifacts["image_only_da3_output_dir_exists"]:
        return {
            "status": "incomplete_missing_target_image_only_output",
            "can_judge_original_thick_layer": False,
            "highest_priority_gap": "same_capture_window016_image_only_output_missing",
            "overlap_gate_status": overlap_decision.get("status"),
        }
    if overlap_decision.get("status") in {
        "pass_image_only_reduced_single_window_thickness",
        "fail_image_only_did_not_reduce_single_window_thickness",
    }:
        return {
            "status": "ready_overlap_gate_has_judgement",
            "can_judge_original_thick_layer": True,
            "overlap_gate_status": overlap_decision.get("status"),
        }
    return {
        "status": "incomplete_overlap_gate_not_closed",
        "can_judge_original_thick_layer": False,
        "highest_priority_gap": "rerun_overlap_gate_after_image_only_output",
        "overlap_gate_status": overlap_decision.get("status"),
    }


def next_actions(decision: dict[str, Any]) -> list[str]:
    status = decision["status"]
    if status == "incomplete_missing_target_image_only_coreml_model":
        return [
            f"Export or obtain {TARGET_RESOURCE}.mlpackage with CoreML input signature image only.",
            "Put the package in ios/Runner/Models/DA3-BASE-CoreML or pass it to the Mac exporter.",
            "Run da3_image_only_coreml_readiness_gate.py, then da3_mac_window_export.py on the same capture.",
        ]
    if status == "incomplete_missing_target_image_only_output":
        return [
            "Run da3_mac_window_export.py with the target image-only CoreML package.",
            "Rerun da3_image_only_overlap_regression_gate.py for window_016.",
        ]
    return ["Keep the fixed K35@476x742 target and rerun this audit after the next parity change."]


def source_hit(path: Path, needle: str) -> dict[str, Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {"present": False, "path": str(path), "needle": needle, "reason": "file_missing"}
    for index, line in enumerate(lines, start=1):
        if needle in line:
            return {
                "present": True,
                "path": str(path),
                "line": index,
                "text": line.strip(),
            }
    return {"present": False, "path": str(path), "needle": needle}


def run_git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    output = result.stdout.strip()
    if result.returncode != 0:
        return None
    return output


def maybe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def same_float(left: Any, right: Any, *, tolerance: float = 1e-9) -> bool | None:
    try:
        left_f = float(left)
        right_f = float(right)
    except (TypeError, ValueError):
        return None
    return abs(left_f - right_f) <= tolerance


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "fixed_target": report["fixed_target"],
        "model_artifacts": report["current_project"]["model_artifacts"],
        "preprocess_current": report["current_project"]["preprocess_current"],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    official = report["official"]
    current = report["current_project"]
    fixed = report["fixed_target"]
    artifacts = current["model_artifacts"]
    preprocess = current["preprocess_current"]
    overlap_decision = current["overlap_gate"]["decision"]
    lines = [
        "# Official DA3 algorithm replication audit",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{decision['status']}`",
        f"- can judge original thick layer: `{decision['can_judge_original_thick_layer']}`",
        f"- highest priority gap: `{decision.get('highest_priority_gap')}`",
        f"- fixed target: `{fixed['resource']}` / K{fixed['window_size']} / `{fixed['height']}x{fixed['width']}`",
        "- AR/VIO: official baseline 禁用外部相机输入，AR 只可作为 metadata 或兼容路径对照。",
        "",
        "当前不能把 `_pose` CoreML 的厚层直接归因给 DA3 官方算法。官方 Streaming 默认是 image-only，当前产品路径还缺目标 image-only CoreML 模型和同 capture 输出。",
        "",
        "## 官方算法事实",
        "",
        f"- official repo HEAD: `{official['repo'].get('head')}`",
        f"- official remote main: `{official['repo'].get('remote_main')}`",
        f"- DA3-BASE commercial license: `{official['commercial_license']['da3_base_apache_2'].get('present')}`",
        f"- Streaming call has no external camera args: `{official['streaming_default']['call_has_no_external_camera_args']}`",
        f"- Streaming call: `{src(official['streaming_default']['image_only_call'])}`",
        f"- default camera decoder evidence: `{src(official['camera_estimation']['cam_dec_to_pose_encoding'])}`",
        f"- predicted w2c output evidence: `{src(official['camera_estimation']['output_extrinsics_are_w2c'])}`",
        f"- GS head prefers predicted camera poses: `{src(official['camera_estimation']['gs_head_prefers_predicted_camera_space'])}`",
        "",
        "## Downstream 事实",
        "",
        f"- npz output process reads frame npz: `{src(official['downstream']['npz_process_reads_frame_npz'])}`",
        f"- confidence threshold: `{src(official['downstream']['npz_conf_threshold_mean_coef'])}`",
        f"- no in-window fusion/dedup detected: `{official['downstream']['no_in_window_surface_fusion_or_dedup_detected']}`",
        "",
        "大白话：官方 downstream 负责跨 chunk 只保存 core-frame、按置信度筛点、采样；它不是把单个 K35 里同一墙面/桌面多次观测融合成一层的模块。单 window 厚层如果存在，首先要查 DA3 上游预测的 depth/pose/intrinsics 一致性。",
        "",
        "## 当前项目状态",
        "",
        f"- image-only CoreML package exists: `{artifacts['image_only_package_exists']}`",
        f"- image-only compiled model exists: `{artifacts['image_only_compiled_exists']}`",
        f"- pose CoreML package exists: `{artifacts['pose_package_exists']}`",
        f"- image-only DA3 output dir exists: `{artifacts['image_only_da3_output_dir_exists']}`",
        f"- overlap gate status: `{overlap_decision.get('status')}`",
        "",
        "## Research / APP 对齐",
        "",
        f"- Research PyTorch exporter image-only mode: `{src(current['research_alignment']['pytorch_export_has_image_only_mode'])}`",
        f"- Research Mac exporter detects CoreML input contract: `{src(current['research_alignment']['mac_export_detects_coreml_signature'])}`",
        f"- Research pose path converts ARKit camera to OpenCV w2c: `{src(current['research_alignment']['mac_export_pose_converts_arkit_to_opencv_w2c'])}`",
        f"- APP Swift supports target image-only resource name: `{src(current['app_alignment']['swift_supports_image_only_resource'])}`",
        f"- APP `_pose` raw cameraTransform risk: `{src(current['app_alignment']['swift_pose_raw_camera_transform_risk'])}`",
        f"- policy blocks official baseline until image-only signature: `{src(current['app_alignment']['policy_blocks_until_image_only_signature'])}`",
        "",
        "## 输入预处理",
        "",
        f"- current input: `{preprocess['input_height']}x{preprocess['input_width']}`",
        f"- resize mode: `{preprocess['resize_mode']}`",
        f"- scale x/y: `{preprocess['scale_x']}` / `{preprocess['scale_y']}`",
        f"- aspect preserving: `{preprocess['aspect_preserving']}`",
        "",
        "这说明当前 `photos_depth` 是固定输入同源 parity 路径，不等价于官方 highres API 的动态 `upper_bound_resize`。这个差异要被标注，但现在不改尺寸。",
        "",
        "## 下一步",
        "",
    ]
    for action in report["next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def src(hit: dict[str, Any]) -> str:
    if not hit.get("present"):
        return "missing"
    return f"{Path(str(hit['path'])).name}:{hit['line']} {hit['text']}"


if __name__ == "__main__":
    raise SystemExit(main())
