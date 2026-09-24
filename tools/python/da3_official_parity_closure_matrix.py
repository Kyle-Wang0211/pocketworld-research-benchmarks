#!/usr/bin/env python3
"""Aggregate current DA3 official-parity gates into one closure matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_parity_closure_matrix.json", report)
    write_markdown(args.out_dir / "official_da3_parity_closure_matrix_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    diag = args.diagnostics_dir
    sources = {
        "algorithm": load_report(
            diag / "official_da3_algorithm_replication_audit_2026_06_04/official_da3_algorithm_replication_audit.json"
        ),
        "remote_source_freshness": load_report(
            diag / "official_da3_remote_source_freshness_audit_2026_06_05/official_da3_remote_source_freshness_audit.json"
        ),
        "coreml_target_export": load_report(
            diag / "official_da3_image_only_coreml_target_export_gate_2026_06_05/official_da3_image_only_coreml_target_export_gate.json"
        ),
        "coreml_readiness": load_report(
            diag / "official_da3_image_only_coreml_readiness_gate_2026_06_05/official_da3_image_only_coreml_readiness_gate.json"
        ),
        "overlap_regression": load_report(
            diag / "official_da3_image_only_overlap_regression_gate_2026_06_05/official_da3_image_only_overlap_regression_gate.json"
        ),
        "multi_window_overlap_summary": load_report(
            diag
            / "official_da3_image_only_multi_window_overlap_summary_2026_06_05/official_da3_image_only_multi_window_overlap_summary.json"
        ),
        "window007_visual_review": load_report(
            diag
            / "official_da3_image_only_visual_review_window_007_2026_06_05/visual_review_summary.json"
        ),
        "image_only_cam_dec_contract": load_report(
            diag
            / "official_da3_image_only_cam_dec_contract_audit_2026_06_05/official_da3_image_only_cam_dec_contract_audit.json"
        ),
        "copy_paste_parity_ledger": load_report(
            diag
            / "official_da3_copy_paste_parity_ledger_2026_06_05/official_da3_copy_paste_parity_ledger.json"
        ),
        "preprocess_pixel_parity": load_report(
            diag
            / "official_da3_preprocess_pixel_parity_audit_2026_06_05/official_da3_preprocess_pixel_parity_audit.json"
        ),
        "tensor_boundary_parity": load_report(
            diag
            / "official_da3_tensor_boundary_parity_audit_2026_06_05/official_da3_preprocess_pixel_parity_audit.json"
        ),
        "canonical_source_probe": load_report(
            diag
            / "official_da3_canonical_source_probe_2026_06_05/official_da3_preprocess_pixel_parity_audit.json"
        ),
        "source_decode_parity": load_report(
            diag
            / "official_da3_source_decode_parity_audit_2026_06_05/official_da3_source_decode_parity_audit.json"
        ),
        "opencv_native_preprocess_parity": load_report(
            diag
            / "official_da3_opencv_native_preprocess_parity_audit_2026_06_05/official_da3_opencv_native_preprocess_parity_audit.json"
        ),
        "cpp_preprocess_kernel_parity": load_report(
            diag
            / "official_da3_cpp_preprocess_kernel_parity_audit_2026_06_05/official_da3_cpp_preprocess_kernel_parity_audit.json"
        ),
        "preprocess_prebuilt_matrix": load_report(
            diag
            / "official_da3_preprocess_prebuilt_matrix_2026_06_05/official_da3_preprocess_prebuilt_matrix.json"
        ),
        "preprocess_stage_attribution": load_report(
            diag
            / "official_da3_preprocess_stage_attribution_audit_2026_06_05/official_da3_preprocess_stage_attribution_audit.json"
        ),
        "preprocess": load_report(
            diag / "official_da3_preprocess_parity_audit_2026_06_04/official_da3_preprocess_parity_audit.json"
        ),
        "image_tensor_contract": load_report(
            diag / "official_da3_image_tensor_contract_parity_audit_2026_06_05/official_da3_image_tensor_contract_parity_audit.json"
        ),
        "fixed_shape_preprocess_authority": load_report(
            diag
            / "official_da3_fixed_shape_preprocess_authority_audit_2026_06_05/official_da3_fixed_shape_preprocess_authority_audit.json"
        ),
        "external_camera_branch": load_report(
            diag / "official_da3_external_camera_branch_parity_audit_2026_06_05/official_da3_external_camera_branch_parity_audit.json"
        ),
        "coordinate": load_report(
            diag / "official_da3_coordinate_convention_audit_2026_06_04/official_da3_coordinate_convention_audit.json"
        ),
        "geometry_path": load_report(
            diag / "official_da3_image_only_geometry_path_audit_2026_06_04/official_da3_image_only_geometry_path_audit.json"
        ),
        "upstream_path_parity": load_report(
            diag / "official_da3_upstream_path_parity_audit_2026_06_05/official_da3_upstream_path_parity_audit.json"
        ),
        "official_pytorch_image_only_pose_depth": load_report(
            diag
            / "window_016_official_pytorch_image_only_k35_504_pose_depth_scale_2026_06_05/window_016_official_pytorch_image_only_pose_depth_scale_audit.json"
        ),
        "official_pytorch_image_only_geometry_consistency": load_report(
            diag
            / "window_016_official_pytorch_image_only_geometry_consistency_2026_06_05/window_016_official_pytorch_image_only_geometry_consistency_audit.json"
        ),
        "official_downstream_core_vs_full_chunk": load_report(
            diag
            / "official_downstream_core_vs_full_chunk_audit_2026_06_05/official_downstream_core_vs_full_chunk_audit.json"
        ),
        "dart_downstream_policy_alignment": load_text_report(
            diag
            / "official_da3_dart_downstream_policy_alignment_2026_06_05/official_da3_dart_downstream_policy_alignment_zh.md"
        ),
        "app_pointcloud_execution_layer": load_text_report(
            diag
            / "official_da3_app_pointcloud_execution_layer_audit_2026_06_05/official_da3_app_pointcloud_execution_layer_audit_zh.md"
        ),
        "mobile_viability": load_report(
            diag / "official_da3_mobile_viability_gate_2026_06_04/mobile_viability_gate_research_sample_report.json"
        ),
        "product_runtime_alignment": load_report(
            diag / "official_da3_product_runtime_alignment_audit_2026_06_05/official_da3_product_runtime_alignment_audit.json"
        ),
        "dart_camera_window016_regression": load_report(
            diag / "official_da3_dart_camera_window016_regression_audit_2026_06_05/official_da3_dart_camera_window016_regression_audit.json"
        ),
        "late_slot_geometry": load_report(
            diag / "official_da3_window016_late_slot_geometry_consistency_audit_2026_06_05/official_da3_window016_late_slot_geometry_consistency_audit.json"
        ),
        "save_frame_downstream": load_report(
            diag / "official_da3_save_frame_downstream_audit_2026_06_05/official_da3_save_frame_downstream_audit.json"
        ),
        "official_save_pose_depth": load_report(
            diag / "window_016_official_save_frame_pose_depth_scale_2026_06_05/window_016_pose_depth_scale_audit.json"
        ),
        "official_pre_norm_pose_depth": load_report(
            diag
            / "window_016_official_pre_norm_official_postprocess_pose_depth_scale_audit_2026_06_05/window_016_pose_depth_scale_audit.json"
        ),
        "save_window_ownership": load_report(
            diag / "official_da3_save_window_ownership_attribution_2026_06_05/official_da3_save_window_ownership_attribution.json"
        ),
        "cap1396_acceptance": load_report(
            diag / "official_da3_cap1396_capture_continuity_acceptance_audit_2026_06_05/official_da3_cap1396_capture_continuity_acceptance_audit.json"
        ),
        "continuity_quarantine_true_rerun": load_report(
            diag / "official_da3_continuity_quarantine_true_rerun_attribution_2026_06_05/official_da3_continuity_quarantine_true_rerun_attribution.json"
        ),
        "dart_continuity_quarantine_plan": load_report(
            diag / "official_da3_dart_continuity_quarantine_plan_audit_2026_06_05/official_da3_dart_continuity_quarantine_plan_audit.json"
        ),
        "dart_input_continuity_risk_contract": load_report(
            diag
            / "official_da3_dart_input_continuity_risk_contract_audit_2026_06_05/official_da3_dart_input_continuity_risk_contract_audit.json"
        ),
        "continuity_quarantine_expansion_queue": load_report(
            diag / "official_da3_continuity_quarantine_expansion_queue_audit_2026_06_05/official_da3_continuity_quarantine_expansion_queue_audit.json"
        ),
        "continuity_quarantine_window021_attribution": load_report(
            diag / "official_da3_continuity_quarantine_window021_true_rerun_attribution_2026_06_05/official_da3_continuity_quarantine_window_021_true_rerun_attribution.json"
        ),
        "continuity_quarantine_window004_attribution": load_report(
            diag / "official_da3_continuity_quarantine_window004_true_rerun_attribution_2026_06_05/official_da3_continuity_quarantine_window_004_true_rerun_attribution.json"
        ),
        "continuity_quarantine_window006_attribution": load_report(
            diag / "official_da3_continuity_quarantine_window006_true_rerun_attribution_2026_06_05/official_da3_continuity_quarantine_window_006_true_rerun_attribution.json"
        ),
        "continuity_quarantine_window007_attribution": load_report(
            diag / "official_da3_continuity_quarantine_window007_true_rerun_attribution_2026_06_05/official_da3_continuity_quarantine_window_007_true_rerun_attribution.json"
        ),
        "external_light_refresh": load_text_report(
            diag / "official_da3_external_light_refresh_2026_06_05/official_da3_external_light_refresh_zh.md"
        ),
        "target_export_runbook": load_text_report(
            diag / "official_da3_image_only_coreml_target_export_runbook_2026_06_04/official_da3_image_only_coreml_target_export_runbook_zh.md"
        ),
    }
    rows = build_rows(sources)
    status = derive_overall_status(rows)
    return {
        "schema_version": "aether_official_da3_parity_closure_matrix_v1",
        "date": args.date,
        "purpose": (
            "Single place to distinguish official DA3 parity facts from missing "
            "target artifacts, research-only blockers, and future product adaptation."
        ),
        "diagnostics_dir": str(diag),
        "overall": status,
        "rows": rows,
        "sources": source_index(sources),
        "plain_language": plain_language(status, rows),
    }


def build_rows(sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    algorithm = sources["algorithm"].get("data", {})
    remote_source_freshness = sources["remote_source_freshness"].get("data", {})
    target = sources["coreml_target_export"].get("data", {})
    readiness = sources["coreml_readiness"].get("data", {})
    overlap = sources["overlap_regression"].get("data", {})
    multi_window_overlap = sources["multi_window_overlap_summary"].get("data", {})
    window007_visual_review = sources["window007_visual_review"].get("data", {})
    image_only_cam_dec_contract = sources["image_only_cam_dec_contract"].get("data", {})
    copy_paste_parity_ledger = sources["copy_paste_parity_ledger"].get("data", {})
    preprocess = sources["preprocess"].get("data", {})
    image_tensor_contract = sources["image_tensor_contract"].get("data", {})
    fixed_shape_preprocess = sources["fixed_shape_preprocess_authority"].get("data", {})
    external_camera_branch = sources["external_camera_branch"].get("data", {})
    coordinate = sources["coordinate"].get("data", {})
    geometry = sources["geometry_path"].get("data", {})
    upstream_path_parity = sources["upstream_path_parity"].get("data", {})
    official_pytorch_image_only_pose_depth = sources["official_pytorch_image_only_pose_depth"].get("data", {})
    official_pytorch_image_only_geometry_consistency = sources["official_pytorch_image_only_geometry_consistency"].get("data", {})
    official_downstream_core_vs_full_chunk = sources["official_downstream_core_vs_full_chunk"].get("data", {})
    mobile = sources["mobile_viability"].get("data", {})
    product = sources["product_runtime_alignment"].get("data", {})
    dart_regression = sources["dart_camera_window016_regression"].get("data", {})
    late_slot = sources["late_slot_geometry"].get("data", {})
    save_frame = sources["save_frame_downstream"].get("data", {})
    official_save_pose_depth = sources["official_save_pose_depth"].get("data", {})
    official_pre_norm_pose_depth = sources["official_pre_norm_pose_depth"].get("data", {})
    save_window_ownership = sources["save_window_ownership"].get("data", {})
    cap1396_acceptance = sources["cap1396_acceptance"].get("data", {})
    continuity_quarantine_true_rerun = sources["continuity_quarantine_true_rerun"].get("data", {})
    dart_continuity_quarantine_plan = sources["dart_continuity_quarantine_plan"].get("data", {})
    dart_input_continuity_risk_contract = sources["dart_input_continuity_risk_contract"].get("data", {})
    continuity_quarantine_expansion_queue = sources["continuity_quarantine_expansion_queue"].get("data", {})
    continuity_quarantine_window021_attribution = sources["continuity_quarantine_window021_attribution"].get("data", {})
    continuity_quarantine_window004_attribution = sources["continuity_quarantine_window004_attribution"].get("data", {})
    continuity_quarantine_window006_attribution = sources["continuity_quarantine_window006_attribution"].get("data", {})
    continuity_quarantine_window007_attribution = sources["continuity_quarantine_window007_attribution"].get("data", {})
    preprocess_pixel_parity = sources["preprocess_pixel_parity"].get("data", {})
    tensor_boundary_parity = sources["tensor_boundary_parity"].get("data", {})
    canonical_source_probe = sources["canonical_source_probe"].get("data", {})
    source_decode_parity = sources["source_decode_parity"].get("data", {})
    opencv_native_preprocess_parity = sources["opencv_native_preprocess_parity"].get("data", {})
    cpp_preprocess_kernel_parity = sources["cpp_preprocess_kernel_parity"].get("data", {})
    preprocess_prebuilt_matrix = sources["preprocess_prebuilt_matrix"].get("data", {})
    preprocess_stage_attribution = sources["preprocess_stage_attribution"].get("data", {})
    official_preprocess_shape_copied = (
        copy_paste_row_status(copy_paste_parity_ledger, "api_preprocess_resize")
        in {"copied", "copied_shape_contract_only"}
    )

    return [
        row(
            "commercial_model_policy",
            "商用 checkpoint 只走 DA3-BASE / Apache-2.0。",
            "pass" if bool_path(algorithm, "official.commercial_license.da3_base_apache_2.present") else "unknown",
            "DA3-BASE license evidence exists; LARGE/GIANT/NESTED remain non-commercial or unresolved for product path.",
            sources["algorithm"]["path"],
        ),
        row(
            "official_streaming_image_only_semantics",
            "官方 DA3-Streaming baseline 是 image-only，不输入 AR/VIO/camera matrices。",
            "pass" if bool_path(algorithm, "official.streaming_default.call_has_no_external_camera_args") else "fail",
            "Official call is model.inference(images, ref_view_strategy=...), and cam_dec predicts camera.",
            sources["algorithm"]["path"],
        ),
        row(
            "official_source_freshness",
            "本地官方 Depth-Anything-3 源码是否与公开 GitHub main 一致。",
            status_from_decision(remote_source_freshness, default="unknown"),
            source_freshness_evidence(remote_source_freshness),
            sources["remote_source_freshness"]["path"],
        ),
        row(
            "official_image_only_cam_dec_contract",
            "官方 image-only 路径的相机/位姿是否来自模型 cam_dec，而当前 APP CoreML 是否仍未复刻这条路径。",
            status_from_image_only_cam_dec_contract(image_only_cam_dec_contract),
            image_only_cam_dec_contract_evidence(image_only_cam_dec_contract),
            sources["image_only_cam_dec_contract"]["path"],
        ),
        row(
            "copy_paste_parity_ledger",
            "按官方源码逐段找不同后，是否只剩 K35 允许差异，以及明确列出的硬复制缺口。",
            "pass"
            if str_path(copy_paste_parity_ledger, "decision.status")
            == "copy_paste_parity_rows_closed"
            else (
                "warning"
                if str_path(copy_paste_parity_ledger, "decision.status")
                == "not_closed_copy_paste_parity_has_hard_gaps"
                else status_from_decision(copy_paste_parity_ledger, default="unknown")
            ),
            copy_paste_parity_ledger_evidence(copy_paste_parity_ledger),
            sources["copy_paste_parity_ledger"]["path"],
        ),
        row(
            "official_upstream_path_parity",
            "当前可运行 APP/Research 输出能否代表官方 image-only 上游路径。",
            status_from_upstream_path_parity(upstream_path_parity),
            upstream_path_parity_evidence(upstream_path_parity),
            sources["upstream_path_parity"]["path"],
        ),
        row(
            "official_pytorch_image_only_window016_thickness",
            "官方 PyTorch image-only + 官方 preprocess 在同一 window_016/K35 下是否也测到 window 内厚层增长。",
            "warning"
            if official_image_only_thickness_observed(official_pytorch_image_only_pose_depth)
            else status_from_report(official_pytorch_image_only_pose_depth, default="unknown"),
            official_pytorch_image_only_pose_depth_evidence(official_pytorch_image_only_pose_depth),
            sources["official_pytorch_image_only_pose_depth"]["path"],
        ),
        row(
            "official_image_only_upstream_geometry_consistency_window016",
            "官方 PyTorch image-only 的深度/内参/cam_dec 位姿在 window_016 内是否已经出现 upstream projective residual spike。",
            "warning"
            if official_image_only_geometry_spike_observed(official_pytorch_image_only_geometry_consistency)
            else status_from_report(official_pytorch_image_only_geometry_consistency, default="unknown"),
            official_image_only_geometry_consistency_evidence(official_pytorch_image_only_geometry_consistency),
            sources["official_pytorch_image_only_geometry_consistency"]["path"],
        ),
        row(
            "official_downstream_core_vs_full_chunk_attribution",
            "官方 core-frame results_output/npz 路径是否能关闭 window_016 厚层，还是 full-chunk merge 只做小幅放大。",
            "warning"
            if str_path(official_downstream_core_vs_full_chunk, "decision.status")
            == "core_frame_downstream_does_not_close_window016_thickness"
            else status_from_decision(official_downstream_core_vs_full_chunk, default="unknown"),
            official_downstream_core_vs_full_chunk_evidence(official_downstream_core_vs_full_chunk),
            sources["official_downstream_core_vs_full_chunk"]["path"],
        ),
        row(
            "official_downstream_no_hidden_in_window_dedup",
            "官方 downstream 只做 core-frame/置信度/采样，不做单 window 表面融合去厚。",
            "pass" if bool_path(algorithm, "official.downstream.no_in_window_surface_fusion_or_dedup_detected") else "unknown",
            "Single-window thickness must be judged through upstream geometry unless a later official path adds fusion.",
            sources["algorithm"]["path"],
        ),
        row(
            "fixed_preprocess_contract_labeled",
            "当前固定 photos_depth 输入与官方 highres API preprocess 已分开标注。",
            "pass"
            if official_preprocess_shape_copied
            else ("pass" if bool_path(preprocess, "fixed_target.shape_is_patch_aligned") else "unknown"),
            "Dart photos_depth default now follows official process_res=504 upper_bound_resize + nearest patch-align shape contract; legacy direct_stretch is compat-only."
            if official_preprocess_shape_copied
            else "K35@476x742 is patch-aligned; current photos_depth is direct_stretch same-input parity, not dynamic upper_bound_resize.",
            sources["copy_paste_parity_ledger"]["path"]
            if official_preprocess_shape_copied
            else sources["preprocess"]["path"],
        ),
        row(
            "official_preprocess_pixel_parity",
            "Dart DA3 runtime tensor 是否已和官方 PIL/OpenCV InputProcessor 完全等价。",
            "warning"
            if str_path(preprocess_pixel_parity, "decision.status").startswith("warning_")
            else status_from_decision(preprocess_pixel_parity, default="unknown"),
            preprocess_pixel_parity_evidence(preprocess_pixel_parity),
            sources["preprocess_pixel_parity"]["path"],
        ),
        row(
            "runtime_tensor_boundary_parity",
            "Swift/CoreML 实际消费的 Dart float32 CHW tensor 是否等于官方 InputProcessor 读取同一 photos_depth PNG 后的 tensor。",
            status_from_decision(tensor_boundary_parity, default="unknown"),
            preprocess_pixel_parity_evidence(tensor_boundary_parity),
            sources["tensor_boundary_parity"]["path"],
        ),
        row(
            "canonical_source_rgb_probe",
            "如果官方 InputProcessor 从 Dart 解码后的 lossless RGB PNG 开始，是否还能看到高分辨率 preprocess tensor 差异。",
            "warning"
            if str_path(canonical_source_probe, "decision.status").startswith("warning_")
            else status_from_decision(canonical_source_probe, default="unknown"),
            preprocess_pixel_parity_evidence(canonical_source_probe),
            sources["canonical_source_probe"]["path"],
        ),
        row(
            "official_source_decode_parity",
            "Dart fallback source JPEG decode 是否已和官方 PIL/libjpeg source load byte-exact。",
            "warning"
            if str_path(source_decode_parity, "decision.status")
            == "warning_source_decode_not_byte_exact"
            else status_from_decision(source_decode_parity, default="unknown"),
            source_decode_parity_evidence(source_decode_parity),
            sources["source_decode_parity"]["path"],
        ),
        row(
            "opencv_native_preprocess_parity",
            "跨平台 native OpenCV/libjpeg 预处理能否 byte-exact 复刻官方 PIL/OpenCV InputProcessor。",
            "pass"
            if str_path(opencv_native_preprocess_parity, "decision.status")
            == "pass_cv2_native_matches_official_input_processor"
            else status_from_decision(opencv_native_preprocess_parity, default="unknown"),
            opencv_native_preprocess_parity_evidence(opencv_native_preprocess_parity),
            sources["opencv_native_preprocess_parity"]["path"],
        ),
        row(
            "cpp_preprocess_kernel_parity",
            "实际 C++/OpenCV/libjpeg kernel 输出是否 byte-exact 复刻官方 PIL/OpenCV InputProcessor。",
            "pass"
            if str_path(cpp_preprocess_kernel_parity, "decision.status")
            == "pass_cpp_kernel_matches_official_input_processor"
            else status_from_decision(cpp_preprocess_kernel_parity, default="unknown"),
            cpp_preprocess_kernel_parity_evidence(cpp_preprocess_kernel_parity),
            sources["cpp_preprocess_kernel_parity"]["path"],
        ),
        row(
            "native_preprocess_prebuilt_matrix",
            "C++ OpenCV/libjpeg preprocess kernel 是否已按 iOS/Android/Harmony/Windows/Linux/macOS 跨端预编译并安全打包。",
            preprocess_prebuilt_matrix_status(preprocess_prebuilt_matrix),
            preprocess_prebuilt_matrix_evidence(preprocess_prebuilt_matrix),
            sources["preprocess_prebuilt_matrix"]["path"],
        ),
        row(
            "official_preprocess_stage_attribution",
            "当前官方输入差异主要来自 source JPEG decode、resize residual，还是 runtime tensor 边界。",
            "warning"
            if str_path(preprocess_stage_attribution, "decision.status")
            == "not_closed_preprocess_stage_parity_has_gaps"
            else status_from_decision(preprocess_stage_attribution, default="unknown"),
            preprocess_stage_attribution_evidence(preprocess_stage_attribution),
            sources["preprocess_stage_attribution"]["path"],
        ),
        row(
            "image_tensor_contract_parity",
            "APP/CoreML image tensor 是否复刻官方 normalize/resize 输入契约。",
            "pass"
            if official_preprocess_shape_copied
            else (
                "warning"
                if str_path(image_tensor_contract, "decision.status")
                == "image_tensor_normalization_matches_but_resize_contract_differs"
                else status_from_decision(image_tensor_contract, default="unknown")
            ),
            "Dart photos_depth_tensor now writes ImageNet-normalized float32 CHW runtime tensors after official process_res=504 upper_bound_resize + patch-align shape contract; Swift loads the pre-normalized tensor. Byte-exact PIL/OpenCV parity is tracked as a separate warning."
            if official_preprocess_shape_copied
            else image_tensor_contract_evidence(image_tensor_contract),
            sources["copy_paste_parity_ledger"]["path"]
            if official_preprocess_shape_copied
            else sources["image_tensor_contract"]["path"],
        ),
        row(
            "fixed_shape_preprocess_authority",
            "DA3BASE_476x742_N35 固定输入是否能等同官方 aspect-preserving preprocess 输出。",
            "pass"
            if official_preprocess_shape_copied
            else (
                "warning"
                if str_path(fixed_shape_preprocess, "decision.status")
                == "fixed_476x742_shape_not_exact_official_preprocess_for_16x9_sources"
                else status_from_decision(fixed_shape_preprocess, default="unknown")
            ),
            "Fixed 742x476/direct_stretch is no longer the default parity target; current strict capture da3_input_manifest is official-preprocess 504x280."
            if official_preprocess_shape_copied
            else fixed_shape_preprocess_evidence(fixed_shape_preprocess),
            sources["copy_paste_parity_ledger"]["path"]
            if official_preprocess_shape_copied
            else sources["fixed_shape_preprocess_authority"]["path"],
        ),
        row(
            "external_camera_branch_parity",
            "当前 CoreML pose path 是否复刻官方 external-camera API 的 forward 前/后相机处理顺序。",
            external_camera_branch_status(external_camera_branch),
            external_camera_branch_evidence(external_camera_branch),
            sources["external_camera_branch"]["path"],
        ),
        row(
            "external_camera_pre_norm_window016_rerun",
            "把官方 pre-forward extrinsics normalization 加到 CoreML pose 输入后，window_016 厚层是否关闭。",
            "warning"
            if official_save_thickness_persists(official_pre_norm_pose_depth)
            else status_from_report(official_pre_norm_pose_depth, default="unknown"),
            external_camera_pre_norm_rerun_evidence(
                official_save_pose_depth,
                official_pre_norm_pose_depth,
            ),
            sources["official_pre_norm_pose_depth"]["path"],
        ),
        row(
            "coordinate_convention_risk_labeled",
            "OpenCV w2c / ARKit / GLB/PLY convention 风险已被标注。",
            "pass"
            if str_path(coordinate, "decision.current_project_alignment.app_pose_branch")
            == "compat_only_raw_cameraTransform_risk"
            else "unknown",
            "Research pose path converts ARKit cameraTransform to OpenCV w2c; APP _pose raw cameraTransform remains compat-only risk.",
            sources["coordinate"]["path"],
        ),
        row(
            "official_product_coreml_path",
            "产品默认 DA3 路径必须指向官方 process_res=504 的 DA3BASE_280x504_N35_image_only；旧 pose CoreML 只能是兼容 fallback。",
            "warning"
            if str_path(readiness, "decision.selected_policy_resource") == "DA3BASE_280x504_N35_image_only"
            and bool_path(readiness, "decision.current_bundle_is_pose_conditioned_only")
            else status_from_decision(readiness, default="unknown"),
            (
                f"selected_policy_resource={str_path(readiness, 'decision.selected_policy_resource')}; "
                f"has_image_only_signature={bool_path(readiness, 'decision.has_image_only_coreml_signature')}; "
                f"current_bundle_pose_only={bool_path(readiness, 'decision.current_bundle_is_pose_conditioned_only')}; "
                "旧 DA3BASE_476x742_N35_pose 不再是 official mainline。"
            ),
            sources["product_runtime_alignment"]["path"],
        ),
        row(
            "native_image_only_input_contract_guard",
            "Native DA3 runner 必须在模型加载前拒绝非 image-only resource/contract。",
            "pass"
            if product_check_passed(product, "swift_native_rejects_non_image_only_contract")
            else "unknown",
            "Swift native adapter hard-rejects unsupported DA3 resources and non-image-only input contracts before model loading.",
            sources["product_runtime_alignment"]["path"],
        ),
        row(
            "dart_depth_stage_resource_allowlist_guard",
            "Dart DepthStage 只允许官方 DA3BASE_280x504_N35_image_only 资源进入 Stage 1。",
            "pass"
            if product_check_passed(
                product,
                "dart_depth_stage_allows_only_target_image_only_resource",
            )
            else "unknown",
            "Dart DepthStage DA3 resource allowlist contains only the official DA3BASE_280x504_N35_image_only target.",
            sources["product_runtime_alignment"]["path"],
        ),
        row(
            "dart_method_channel_image_only_tensor_payload_guard",
            "APP MethodChannel 传给 native 的必须是官方 image-only tensor 文件，不是旧 pose/camera 输入。",
            "pass"
            if product_check_passed(
                product,
                "dart_method_channel_payload_carries_image_only_tensor_input",
            )
            else "unknown",
            "Flutter MethodChannel ABI test proves the native call carries DA3BASE_280x504_N35_image_only, da3InputContract=image_only, requiredExternalCameraInputs=false, and a real float32 CHW tensor of W*H*3*4 bytes.",
            sources["product_runtime_alignment"]["path"],
        ),
        row(
            "app_static_probe_resource_route_guard",
            "APP 资源、loader、native allowlist 和 Dart runner 不能路由 DA3BASE_static_* probe 包。",
            "pass"
            if product_check_passed(
                product,
                "static_probe_resources_not_packaged_or_routable",
            )
            else "unknown",
            "APP Xcode resources, ModelLoader, Swift native allowlist, Dart runner, and resource guard test do not reference DA3BASE_static_* probe packages.",
            sources["product_runtime_alignment"]["path"],
        ),
        row(
            "dart_owned_da3_camera_contract",
            "DA3 camera convention conversion 尽量前移到 Dart，Native 只消费 tensor。",
            "pass" if product_check_passed(product, "dart_camera_contract_helper")
            and product_check_passed(product, "dart_manifest_writes_da3_camera_fields")
            and product_check_passed(product, "dart_app_payload_carries_da3_camera_fields")
            and product_check_passed(product, "swift_native_consumes_precomputed_camera")
            and product_check_passed(product, "mac_exporter_consumes_same_camera_contract")
            else "unknown",
            "Dart manifest/payload now owns cameraExtrinsicOpenCvW2c4x4 and cameraIntrinsic3x3; Swift and Mac exporter prefer those fields.",
            sources["product_runtime_alignment"]["path"],
        ),
        row(
            "same_capture_runnable_pose_window016_regression",
            "同一 strict capture/window_016 在当前可运行 pose CoreML + Dart camera contract 下是否仍厚。",
            "fail"
            if str_path(dart_regression, "decision.status")
            == "thickness_persists_after_dart_camera_contract_pose_coreml"
            else "unknown",
            str_path(dart_regression, "decision.conclusion")
            or "Dart-camera window_016 regression report could not be read.",
            sources["dart_camera_window016_regression"]["path"],
        ),
        row(
            "late_slot_geometry_consistency_suspect",
            "window_016 后段 slots 是否呈现 pose/depth/confidence 一致性风险。",
            "warning"
            if str_path(late_slot, "decision.status")
            == "late_slot_pose_depth_consistency_suspect"
            else "unknown",
            late_slot_evidence(late_slot),
            sources["late_slot_geometry"]["path"],
        ),
        row(
            "official_save_frame_downstream_selection",
            "官方 results_output/save_depth_conf_result 选帧是否已经按 officialSaveFrameIDs/downstreamFrameIDs 落到 Dart/Research。",
            "pass"
            if str_path(save_frame, "decision.status")
            == "official_save_frame_downstream_aligned"
            else "unknown",
            save_frame_evidence(save_frame),
            sources["save_frame_downstream"]["path"],
        ),
        row(
            "confidence_minus_one_downstream_contract",
            "官方 DA3-Streaming 的 predictions.conf -= 1.0 是否已锁进 APP downstream contract。",
            "pass"
            if copy_paste_row_status(
                copy_paste_parity_ledger,
                "confidence_minus_one",
            )
            == "copied_in_native_and_downstream_executor_smoke_passed"
            else "unknown",
            "Research NPZ path and APP depth_index/PointCloudStage contract require official_da3_streaming_confidence_minus_one and forbid raw depth_conf; Swift native now applies conf -= 1.0 before writing confidencePath, and Dart pointcloud executor smoke passed.",
            sources["copy_paste_parity_ledger"]["path"],
        ),
        row(
            "npz_output_process_pointcloud_filter_contract",
            "官方 npz_output_process.py 点云 filter 参数是否已锁进 APP PointCloudStage contract。",
            "pass"
            if copy_paste_row_status(
                copy_paste_parity_ledger,
                "npz_output_process_pointcloud_filter",
            )
            == "official_python_oracle_with_mobile_replay_smoke"
            else "unknown",
            "Official Research/desktop downstream authority remains the Python npz_output_process.py. APP PointCloudStage is only a mobile replay: image=processed frames[].imageRelativePath, depth=relativeDepthPath, intrinsics=[3,3], extrinsics=OpenCV w2c, conf_threshold=mean(confs)*0.5, valid mask conf>=threshold && conf>1e-5, sample_ratio=0.015, binary little-endian PLY. Synthetic smoke passed.",
            sources["copy_paste_parity_ledger"]["path"],
        ),
        row(
            "dart_downstream_policy_executable_smoke",
            "Dart capture package 的 officialSaveFrameIDs/downstreamFrameIDs 策略是否有可执行 smoke 证明。",
            "pass" if sources["dart_downstream_policy_alignment"]["exists"] else "unknown",
            "Dart smoke commands passed: official streaming K35/overlap18 window plan and continuity quarantine counterfactual plan. Report also states APP actual pointcloud consumers are not over-claimed.",
            sources["dart_downstream_policy_alignment"]["path"],
        ),
        row(
            "app_pointcloud_execution_layer_status",
            "APP 主仓库实际点云生成层是否已经实现，并且是否按 depth_index/downstreamFrameIDs 消费。",
            "pass"
            if copy_paste_row_status(
                copy_paste_parity_ledger,
                "npz_output_process_pointcloud_filter",
            )
            == "official_python_oracle_with_mobile_replay_smoke"
            else "unknown",
            "DepthStage filters native window outputs through downstreamFrameIDs before depth_index.json. Research/desktop must use official Python npz_output_process.py as oracle; APP PointCloudStage is a mobile replay when complete depth_index payloads are present, and falls back to contract-only only for missing/zero-size synthetic inputs. dart analyze, Flutter focused test, and Swift parse passed.",
            sources["copy_paste_parity_ledger"]["path"],
        ),
        row(
            "official_save_window016_thickness_persists",
            "按官方 save-frame downstream 只看 window_016 的 17 帧后，厚层是否仍未关闭。",
            "warning"
            if official_save_thickness_persists(official_save_pose_depth)
            else "unknown",
            official_save_pose_depth_evidence(official_save_pose_depth),
            sources["official_save_pose_depth"]["path"],
        ),
        row(
            "official_save_window_ownership_attribution",
            "相邻 window_017 official downstream 是否排除 cap-1514/cap-1529 为当前主因。",
            "pass"
            if str_path(save_window_ownership, "decision.status")
            == "window016_official_save_thickness_cap1396_primary"
            else "unknown",
            save_window_ownership_evidence(save_window_ownership),
            sources["save_window_ownership"]["path"],
        ),
        row(
            "cap1396_capture_continuity_acceptance",
            "cap-1396 为什么能进 window_016 official downstream，以及它是否违反移动端连续性阈值。",
            "warning"
            if str_path(cap1396_acceptance, "decision.status")
            == "cap1396_quality_accepted_but_continuity_breach_primary_suspect"
            else "unknown",
            cap1396_acceptance_evidence(cap1396_acceptance),
            sources["cap1396_acceptance"]["path"],
        ),
        row(
            "dart_official_window_input_continuity_risk_contract",
            "Dart 官方 window plan 是否已经把 image-only 输入连续性风险显式暴露，同时保持官方帧集不变。",
            "pass"
            if str_path(dart_input_continuity_risk_contract, "decision.status")
            == "dart_official_window_plan_flags_image_only_input_continuity_risk_without_changing_official_frames"
            else "unknown",
            dart_input_continuity_risk_contract_evidence(dart_input_continuity_risk_contract),
            sources["dart_input_continuity_risk_contract"]["path"],
        ),
        row(
            "continuity_quarantine_true_rerun_attribution",
            "把 continuity 断层隔离成研究 window 后，当前可运行 DA3BASE_476x742_N35_pose CoreML 真重跑是否减薄。",
            "pass"
            if str_path(continuity_quarantine_true_rerun, "decision.status")
            == "true_rerun_continuity_quarantine_reduces_window016_thickness"
            else "unknown",
            continuity_quarantine_evidence(continuity_quarantine_true_rerun),
            sources["continuity_quarantine_true_rerun"]["path"],
        ),
        row(
            "dart_continuity_quarantine_simulator_ready",
            "Dart 侧是否已经能生成单独的 continuity quarantine K35 计划，并匹配 window_016 真重跑帧集合。",
            "pass"
            if str_path(dart_continuity_quarantine_plan, "decision.status")
            == "dart_continuity_quarantine_plan_matches_window016_true_rerun_variants"
            else "unknown",
            dart_continuity_quarantine_plan_evidence(dart_continuity_quarantine_plan),
            sources["dart_continuity_quarantine_plan"]["path"],
        ),
        row(
            "continuity_quarantine_expansion_queue_ready",
            "Dart quarantine 是否已从 window_016 个案扩展成全量 risky-window 队列，并准备好下一批研究 manifest。",
            "pass"
            if str_path(continuity_quarantine_expansion_queue, "decision.status")
            == "expansion_queue_and_manifest_batch_ready_true_reruns_needed"
            else "unknown",
            continuity_quarantine_expansion_queue_evidence(continuity_quarantine_expansion_queue),
            sources["continuity_quarantine_expansion_queue"]["path"],
        ),
        row(
            "continuity_quarantine_window021_negative_control",
            "下一批候选中 window_021 真重跑是否说明 continuity risk 不能单独等价为厚层。",
            "pass"
            if str_path(continuity_quarantine_window021_attribution, "decision.status")
            == "source_window_not_thick_continuity_quarantine_negative_control"
            else "unknown",
            continuity_quarantine_window_attribution_evidence(continuity_quarantine_window021_attribution),
            sources["continuity_quarantine_window021_attribution"]["path"],
        ),
        row(
            "continuity_quarantine_window004_negative_control",
            "下一批候选中 window_004 真重跑是否再次说明 continuity risk 不能单独等价为厚层。",
            "pass"
            if str_path(continuity_quarantine_window004_attribution, "decision.status")
            == "source_window_not_thick_continuity_quarantine_negative_control"
            else "unknown",
            continuity_quarantine_window_attribution_evidence(continuity_quarantine_window004_attribution),
            sources["continuity_quarantine_window004_attribution"]["path"],
        ),
        row(
            "continuity_quarantine_window006_borderline_control",
            "下一批候选中 window_006 是否显示 continuity quarantine 有改善但不足以作为硬门槛。",
            "warning"
            if str_path(continuity_quarantine_window006_attribution, "decision.status")
            == "true_rerun_continuity_quarantine_inconclusive_for_source"
            else "unknown",
            continuity_quarantine_window_attribution_evidence(continuity_quarantine_window006_attribution),
            sources["continuity_quarantine_window006_attribution"]["path"],
        ),
        row(
            "continuity_quarantine_window007_negative_control",
            "下一批候选中 window_007 是否进一步说明 continuity risk 不能单独等价为厚层。",
            "pass"
            if str_path(continuity_quarantine_window007_attribution, "decision.status")
            == "source_window_not_thick_continuity_quarantine_negative_control"
            else "unknown",
            continuity_quarantine_window_attribution_evidence(continuity_quarantine_window007_attribution),
            sources["continuity_quarantine_window007_attribution"]["path"],
        ),
        row(
            "target_image_only_coreml_artifact",
            "官方 process_res=504/upper_bound_resize 对应的 DA3BASE_280x504_N35_image_only CoreML 包是否存在。",
            "warning"
            if str_path(target, "decision.status") == "fail_local_target_conversion_preflight"
            else status_from_decision(target, default="unknown"),
            str_path(target, "decision.highest_priority_gap")
            or "Target image-only package status could not be read.",
            sources["coreml_target_export"]["path"],
        ),
        row(
            "static_probe_not_product_target_guard",
            "Research 低分辨率 static image-only probe 包不能冒充产品 DA3BASE_280x504_N35_image_only。",
            "pass"
            if str_path(target, "probe_substitution_guard.status")
            == "pass_static_probes_are_research_only_not_product_target"
            else (
                "warning"
                if str_path(target, "probe_substitution_guard.status")
                == "warning_exact_target_package_outside_app_model_dir"
                else "unknown"
            ),
            (
                f"status={str_path(target, 'probe_substitution_guard.status')}; "
                f"package_count={get_path(target, 'probe_substitution_guard.package_count')}; "
                f"exact_target_package_count={get_path(target, 'probe_substitution_guard.exact_target_package_count')}; "
                f"passed_static_conversion_probe_count={get_path(target, 'probe_substitution_guard.passed_static_conversion_probe_count')}; "
                f"do_not_accept_probe_as_product_target={get_path(target, 'probe_substitution_guard.do_not_accept_probe_as_product_target')}."
            ),
            sources["coreml_target_export"]["path"],
        ),
        row(
            "target_coreml_export_resource_gate",
            "本机是否适合继续硬转官方 504x280/K35 image-only CoreML；这是 artifact 生成门槛，不是移动端运行门槛。",
            "warning"
            if bool_path(target, "decision.local_memory_insufficient_for_attention_floor")
            or (
                num_path(target, "decision.rough_target_conversion_peak_from_failed_probe_gib")
                > num_path(target, "decision.local_physical_memory_gib")
            )
            else "pass",
            (
                f"Target fp16 attention score floor is {num_path(target, 'decision.target_fp16_attention_score_buffer_gib'):.2f} GiB; "
                f"rough conversion peak is {num_path(target, 'decision.rough_target_conversion_peak_from_failed_probe_gib'):.2f} GiB; "
                f"local memory is {num_path(target, 'decision.local_physical_memory_gib'):.2f} GiB."
            ),
            sources["coreml_target_export"]["path"],
        ),
        row(
            "app_image_only_coreml_readiness",
            "APP bundle 中 official image-only CoreML signature readiness；这是当前 official mainline 的硬门槛。",
            "warning"
            if status_from_decision(readiness, default="unknown") == "fail"
            else status_from_decision(readiness, default="unknown"),
            str_path(readiness, "decision.highest_priority_gap")
            or str_path(readiness, "decision.status")
            or "Readiness status could not be read.",
            sources["coreml_readiness"]["path"],
        ),
        row(
            "same_capture_image_only_overlap_regression",
            "同一 capture/window_016 的 official image-only 输出是否已能判断厚层。",
            "warning"
            if str_path(overlap, "decision.status") == "blocked_missing_image_only_target_output"
            else status_from_decision(overlap, default="unknown"),
            (
                "Need DA3BASE_280x504_N35_image_only CoreML output for the same capture/window "
                "before the APP-side image-only overlap regression can run."
            )
            if str_path(overlap, "decision.status") == "blocked_missing_image_only_target_output"
            else (
                f"status={str_path(overlap, 'decision.status')}; "
                f"pca_minor_growth={num_path(overlap, 'decision.acceptance.image_only_first35_over_first10.pca_minor_growth'):.3f}; "
                f"bbox_diag_growth={num_path(overlap, 'decision.acceptance.image_only_first35_over_first10.bbox_diag_growth'):.3f}; "
                f"threshold={num_path(overlap, 'decision.acceptance.max_acceptable_image_only_minor_growth'):.3f}; "
                f"pose_reference_warning={str_path(overlap, 'decision.acceptance.pose_reference_warning')}"
            ),
            sources["overlap_regression"]["path"],
        ),
        row(
            "multi_window_image_only_overlap_regression",
            "高风险 windows 的 official image-only 产品口径厚层回归是否通过。",
            status_from_decision(multi_window_overlap, default="unknown"),
            (
                f"status={str_path(multi_window_overlap, 'decision.status')}; "
                f"metric_status={str_path(multi_window_overlap, 'decision.metric_status')}; "
                f"product_pass={num_path(multi_window_overlap, 'decision.product_pass_count'):.0f}/"
                f"{num_path(multi_window_overlap, 'decision.window_count'):.0f}; "
                f"max_product_downstream_pca_minor_growth="
                f"{num_path(multi_window_overlap, 'decision.max_product_official_downstream_pca_minor_growth'):.3f}; "
                f"max_full_k35_diagnostic_pca_minor_growth="
                f"{num_path(multi_window_overlap, 'decision.max_full_k35_diagnostic_pca_minor_growth'):.3f}; "
                f"visual_review_required={str_path(multi_window_overlap, 'decision.visual_thickness_review_required')}; "
                f"do_not_claim_fully_solved={str_path(multi_window_overlap, 'decision.do_not_claim_thick_layer_fully_solved')}; "
                f"full_k35_warning_windows="
                f"{', '.join(get_path(multi_window_overlap, 'decision.full_k35_diagnostic_warning_windows') or [])}"
            ),
            sources["multi_window_overlap_summary"]["path"],
        ),
        row(
            "window007_visual_thickness_review",
            "window_007 PLY/PNG 肉眼厚层验收是否已关闭。",
            window007_visual_review_status(window007_visual_review),
            window007_visual_review_evidence(window007_visual_review),
            sources["window007_visual_review"]["path"],
        ),
        row(
            "image_only_geometry_path",
            "官方 image-only 相机路径是否来自 DA3 内部 camera decoder。",
            "pass"
            if str_path(geometry, "decision.official_pose_source")
            == "network_cam_dec_from_images_not_arkit_vio"
            else "unknown",
            "Official pose source is network_cam_dec_from_images_not_arkit_vio; thickness reduction, if any, must come from upstream depth/pose/scale consistency.",
            sources["geometry_path"]["path"],
        ),
        row(
            "mobile_product_viability",
            "手机/平板/笔记本产品可行性是否已由真机 telemetry 证明。",
            status_from_report(mobile, default="unknown"),
            "Research sample can warn/pass research checks, but product pass requires real-device telemetry and explicit thresholds.",
            sources["mobile_viability"]["path"],
        ),
        row(
            "external_official_status_refresh",
            "官方 issue/PR/社区轻量刷新是否发现已合入修复或 hidden cleanup。",
            "pass" if sources["external_light_refresh"]["exists"] else "unknown",
            "Issue #254 remains open with 0 comments; PR #256 remains open; no official hidden single-window cleanup path found.",
            sources["external_light_refresh"]["path"],
        ),
        row(
            "target_export_runbook_ready",
            "目标 image-only CoreML 包的导出/验收/回归 runbook 是否已写清楚。",
            "pass" if sources["target_export_runbook"]["exists"] else "unknown",
            "Runbook defines the fixed target export command, readiness gate, Mac export, overlap regression gate, and forbidden fallbacks.",
            sources["target_export_runbook"]["path"],
        ),
    ]


def derive_overall_status(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {item["id"]: item for item in rows}
    product_path_ready = by_id["official_product_coreml_path"]["status"] == "pass"
    copy_paste_ledger_ready = by_id["copy_paste_parity_ledger"]["status"] == "pass"
    upstream_path_not_official = by_id["official_upstream_path_parity"]["status"] in {"fail", "warning"}
    official_image_only_thick = by_id["official_pytorch_image_only_window016_thickness"]["status"] == "warning"
    official_image_only_geometry_spike = (
        by_id["official_image_only_upstream_geometry_consistency_window016"]["status"] == "warning"
    )
    official_core_frame_still_thick = (
        by_id["official_downstream_core_vs_full_chunk_attribution"]["status"] == "warning"
    )
    dart_camera_ready = by_id["dart_owned_da3_camera_contract"]["status"] == "pass"
    dart_regression_fail = by_id["same_capture_runnable_pose_window016_regression"]["status"] == "fail"
    save_frame_aligned = by_id["official_save_frame_downstream_selection"]["status"] == "pass"
    native_preprocess_ready = (
        by_id["opencv_native_preprocess_parity"]["status"] == "pass"
        and by_id["cpp_preprocess_kernel_parity"]["status"] == "pass"
        and by_id["official_preprocess_stage_attribution"]["status"] == "pass"
    )
    native_preprocess_cross_platform_prebuilts_ready = (
        by_id["native_preprocess_prebuilt_matrix"]["status"] == "pass"
    )
    preprocess_pixel_gap = by_id["official_preprocess_pixel_parity"]["status"] == "warning"
    tensor_boundary_ready = by_id["runtime_tensor_boundary_parity"]["status"] == "pass"
    canonical_source_probe_gap = by_id["canonical_source_rgb_probe"]["status"] == "warning" and not native_preprocess_ready
    source_decode_gap = by_id["official_source_decode_parity"]["status"] == "warning" and not native_preprocess_ready
    dart_fallback_source_decode_gap = by_id["official_source_decode_parity"]["status"] == "warning"
    official_save_thick = by_id["official_save_window016_thickness_persists"]["status"] == "warning"
    same_capture_image_only_pass = (
        by_id["same_capture_image_only_overlap_regression"]["status"] == "pass"
    )
    multi_window_image_only_pass = (
        by_id["multi_window_image_only_overlap_regression"]["status"] == "pass"
    )
    visual_thickness_review_pending = (
        by_id["window007_visual_thickness_review"]["status"] == "warning"
    )
    external_pre_norm_still_thick = (
        by_id["external_camera_pre_norm_window016_rerun"]["status"] == "warning"
    )
    ownership_attributed = by_id["official_save_window_ownership_attribution"]["status"] == "pass"
    cap1396_attributed = by_id["cap1396_capture_continuity_acceptance"]["status"] == "warning"
    dart_input_risk_contract_ready = (
        by_id["dart_official_window_input_continuity_risk_contract"]["status"] == "pass"
    )
    quarantine_true_rerun_pass = by_id["continuity_quarantine_true_rerun_attribution"]["status"] == "pass"
    dart_quarantine_plan_ready = by_id["dart_continuity_quarantine_simulator_ready"]["status"] == "pass"
    quarantine_expansion_queue_ready = by_id["continuity_quarantine_expansion_queue_ready"]["status"] == "pass"
    window021_negative_control = by_id["continuity_quarantine_window021_negative_control"]["status"] == "pass"
    window004_negative_control = by_id["continuity_quarantine_window004_negative_control"]["status"] == "pass"
    window006_borderline_control = by_id["continuity_quarantine_window006_borderline_control"]["status"] == "warning"
    window007_negative_control = by_id["continuity_quarantine_window007_negative_control"]["status"] == "pass"
    target_missing = by_id["target_image_only_coreml_artifact"]["status"] in {"fail", "warning"}
    research_export_warning = by_id["target_coreml_export_resource_gate"]["status"] == "warning"
    if visual_thickness_review_pending:
        status = "not_closed_product_image_only_metric_pass_visual_thickness_review_pending"
    elif multi_window_image_only_pass and not native_preprocess_cross_platform_prebuilts_ready:
        status = "not_closed_product_image_only_multiwindow_passed_needs_cross_platform_prebuilts_and_telemetry"
    elif multi_window_image_only_pass:
        status = "not_closed_product_image_only_multiwindow_passed_needs_real_device_telemetry"
    elif same_capture_image_only_pass and not native_preprocess_cross_platform_prebuilts_ready:
        status = "not_closed_product_image_only_window016_passed_needs_cross_platform_prebuilts_and_telemetry"
    elif same_capture_image_only_pass:
        status = "not_closed_product_image_only_window016_passed_needs_multicapture_validation"
    elif official_image_only_thick:
        status = "not_closed_official_image_only_k35_window_internal_thickening_observed"
    elif upstream_path_not_official:
        status = "not_closed_current_outputs_not_official_image_only_authority"
    elif (
        quarantine_true_rerun_pass
        and dart_quarantine_plan_ready
        and quarantine_expansion_queue_ready
        and window021_negative_control
        and window004_negative_control
        and window006_borderline_control
        and window007_negative_control
    ):
        status = "not_closed_quarantine_evidence_secondary_to_official_upstream_parity"
    elif (
        quarantine_true_rerun_pass
        and dart_quarantine_plan_ready
        and quarantine_expansion_queue_ready
        and window021_negative_control
        and window004_negative_control
        and window006_borderline_control
    ):
        status = "not_closed_quarantine_evidence_needs_official_upstream_parity_first"
    elif (
        quarantine_true_rerun_pass
        and dart_quarantine_plan_ready
        and quarantine_expansion_queue_ready
        and window021_negative_control
        and window004_negative_control
    ):
        status = "not_closed_quarantine_has_positive_and_two_negative_controls_needs_rule_refinement"
    elif quarantine_true_rerun_pass and dart_quarantine_plan_ready and quarantine_expansion_queue_ready and window021_negative_control:
        status = "not_closed_quarantine_has_positive_and_negative_control_needs_more_candidates"
    elif quarantine_true_rerun_pass and dart_quarantine_plan_ready and quarantine_expansion_queue_ready:
        status = "not_closed_quarantine_multirun_batch_ready_needs_coreml_outputs"
    elif quarantine_true_rerun_pass and dart_quarantine_plan_ready:
        status = "not_closed_dart_continuity_quarantine_simulator_ready_needs_multicapture_validation"
    elif quarantine_true_rerun_pass:
        status = "not_closed_continuity_quarantine_true_rerun_reduces_window016_thickness"
    elif cap1396_attributed:
        status = "not_closed_cap1396_capture_continuity_acceptance_primary_suspect"
    elif official_save_thick:
        status = "not_closed_official_save_downstream_thickness_persists"
    elif dart_regression_fail and save_frame_aligned:
        status = "not_closed_official_save_downstream_attribution_pending"
    elif dart_regression_fail:
        status = "not_closed_thickness_persists_after_dart_camera_contract"
    elif product_path_ready and dart_camera_ready:
        status = "not_closed_current_runnable_pose_geometry_regression_pending"
    else:
        status = "not_closed_product_runtime_contract_incomplete"
    return {
        "status": status,
        "goal_complete": False,
        "product_path_ready": product_path_ready,
        "copy_paste_parity_ledger_ready": copy_paste_ledger_ready,
        "current_outputs_not_official_image_only_authority": upstream_path_not_official,
        "official_image_only_k35_window_internal_thickening_observed": official_image_only_thick,
        "official_image_only_upstream_geometry_spike_observed": official_image_only_geometry_spike,
        "official_core_frame_downstream_still_thick": official_core_frame_still_thick,
        "official_preprocess_pixel_parity_gap": preprocess_pixel_gap,
        "runtime_tensor_boundary_parity_ready": tensor_boundary_ready,
        "native_preprocess_kernel_ready_for_capture_package": native_preprocess_ready,
        "native_preprocess_cross_platform_prebuilts_ready": native_preprocess_cross_platform_prebuilts_ready,
        "canonical_source_rgb_probe_gap": canonical_source_probe_gap,
        "official_source_decode_parity_gap": source_decode_gap,
        "dart_fallback_source_decode_gap": dart_fallback_source_decode_gap,
        "dart_camera_contract_ready": dart_camera_ready,
        "dart_camera_window016_regression_failed": dart_regression_fail,
        "same_capture_image_only_window016_passed": same_capture_image_only_pass,
        "multi_window_image_only_risky_windows_passed": multi_window_image_only_pass,
        "window007_visual_thickness_review_pending": visual_thickness_review_pending,
        "official_save_frame_downstream_aligned": save_frame_aligned,
        "official_save_window016_thickness_persists": official_save_thick,
        "external_pre_norm_window016_still_thick": external_pre_norm_still_thick,
        "official_save_window_ownership_attributed": ownership_attributed,
        "cap1396_capture_continuity_attributed": cap1396_attributed,
        "dart_official_window_input_continuity_risk_contract_ready": dart_input_risk_contract_ready,
        "continuity_quarantine_true_rerun_passed": quarantine_true_rerun_pass,
        "dart_continuity_quarantine_simulator_ready": dart_quarantine_plan_ready,
        "continuity_quarantine_expansion_queue_ready": quarantine_expansion_queue_ready,
        "continuity_quarantine_window021_negative_control": window021_negative_control,
        "continuity_quarantine_window004_negative_control": window004_negative_control,
        "continuity_quarantine_window006_borderline_control": window006_borderline_control,
        "continuity_quarantine_window007_negative_control": window007_negative_control,
        "target_missing": target_missing,
        "overlap_gate_blocked": False,
        "local_target_export_preflight_failed": research_export_warning,
        "research_image_only_gap": target_missing,
        "next_best_action": (
            "产品侧 DA3BASE_280x504_N35_image_only CoreML 已落地，APP/native image-only regression "
            "已经扩展到 6 个 risky windows；产品 official_downstream metric 全部通过，max PCA minor growth "
            "约 1.132，低于 1.15 阈值。但 window_007 的 PLY/PNG 视觉核验显示 official_downstream_core17 "
            "只是比 full35 收敛，不能写成厚层完全根治；完整 K35 诊断仍有 tail-frame 超阈值。下一步先按肉眼/PLY "
            "确认视觉厚层是否可接受，再继续追上游/下游差异；同时补齐 C++ OpenCV/libjpeg preprocess kernel 的跨端预编译打包矩阵。"
        ),
    }


def row(check_id: str, requirement: str, status: str, evidence: str, source: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "requirement": requirement,
        "status": normalize_status(status),
        "evidence": evidence,
        "source": source,
    }


def source_freshness_evidence(report: dict[str, Any]) -> str:
    return (
        f"remote_main={str_path(report, 'official_remote.main_sha')}; "
        f"local_head={str_path(report, 'local_official_repo.head_sha')}; "
        f"local_source_stale={bool_path(report, 'decision.local_source_stale')}; "
        f"interpretation={str_path(report, 'decision.interpretation')}"
    )


def normalize_status(status: str) -> str:
    if status in {"pass", "warning", "fail", "blocked", "unknown"}:
        return status
    if status.startswith("pass"):
        return "pass"
    if status.startswith("fail"):
        return "fail"
    if status.startswith("blocked") or status.startswith("incomplete") or status.startswith("not_"):
        return "blocked"
    return "unknown"


def status_from_decision(report: dict[str, Any], *, default: str) -> str:
    return normalize_status(str_path(report, "decision.status") or default)


def status_from_report(report: dict[str, Any], *, default: str) -> str:
    return normalize_status(str_path(report, "status") or str_path(report, "overall.status") or default)


def product_check_passed(report: dict[str, Any], check_id: str) -> bool:
    for item in report.get("checks", []):
        if isinstance(item, dict) and item.get("id") == check_id:
            return item.get("status") == "pass"
    return False


def copy_paste_row_status(report: dict[str, Any], row_id: str) -> str:
    for item in report.get("rows", []):
        if isinstance(item, dict) and item.get("id") == row_id:
            return str(item.get("status") or "")
    return ""


def late_slot_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Late-slot geometry report could not be read."
    largest = first_dict(get_path(report, "summary.largest_pose_step"))
    low_conf = first_dict(get_path(report, "summary.lowest_confidence_median"))
    return (
        f"Largest pose step: slot {largest.get('slot')} / {largest.get('frame_id')} "
        f"({float_or_nan(largest.get('pose_step_from_previous')):.3f}); "
        f"lowest confidence median: slot {low_conf.get('slot')} / {low_conf.get('frame_id')} "
        f"({float_or_nan(low_conf.get('confidence_median')):.3f})."
    )


def save_frame_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official save-frame downstream report could not be read."
    comparison = get_path(report, "depth_index_comparison") or {}
    window016 = get_path(report, "window016") or {}
    return (
        f"window_016 full CoreML slots={window016.get('frameCount')}, "
        f"official downstream={window016.get('officialSaveFrameCount')}; "
        f"old depth_index frames={comparison.get('old_full_chunk_frame_count')}, "
        f"new official-save frames={comparison.get('new_official_save_frame_count')}."
    )


def official_save_thickness_persists(report: dict[str, Any]) -> bool:
    if not report:
        return False
    minor = num_path(report, "summary.styles.npz_streaming_style.k35_over_k10.minor_ratio_vs_k10")
    bbox = num_path(report, "summary.styles.npz_streaming_style.k35_over_k10.bbox_ratio_vs_k10")
    return minor >= 1.10 or bbox >= 1.10


def official_image_only_thickness_observed(report: dict[str, Any]) -> bool:
    if not report:
        return False
    decision = str_path(report, "summary.decision.label")
    if decision == "official_image_only_k35_shows_window_internal_thickening":
        return True
    minor = num_path(
        report,
        "summary.styles.npz_streaming_style_conf_minus_one.k35_over_k10.minor_ratio_vs_k10",
    )
    bbox = num_path(
        report,
        "summary.styles.npz_streaming_style_conf_minus_one.k35_over_k10.bbox_ratio_vs_k10",
    )
    return minor >= 1.10 or bbox >= 1.10


def official_image_only_geometry_spike_observed(report: dict[str, Any]) -> bool:
    if not report:
        return False
    first = get_path(report, "summary.first_geometry_spike") or {}
    first_npz = get_path(report, "summary.first_cumulative_npz_minor_ge_1_10") or {}
    return bool(first) and bool(first_npz)


def official_image_only_geometry_consistency_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official PyTorch image-only geometry consistency report could not be read."
    scope = get_path(report, "scope") or {}
    first = get_path(report, "summary.first_geometry_spike") or {}
    first_110 = get_path(report, "summary.first_cumulative_npz_minor_ge_1_10") or {}
    first_135 = get_path(report, "summary.first_cumulative_npz_minor_ge_1_35") or {}
    interpretation = str_path(report, "summary.interpretation")
    return (
        f"camera_mode={scope.get('camera_mode')}, ref_view_strategy={scope.get('ref_view_strategy')}, "
        f"process_res={scope.get('process_res')}; "
        f"first geometry spike={compact_slot(first)}; "
        f"first npz minor>=1.10={compact_slot(first_110)}; "
        f"first npz minor>=1.35={compact_slot(first_135)}; "
        f"interpretation={interpretation}"
    )


def compact_slot(row: dict[str, Any]) -> str:
    if not row:
        return "none"
    return (
        f"slot {row.get('slot')} {row.get('frame_id')} prev={row.get('previous_frame_id')} "
        f"gap={row.get('frame_gap_from_previous')}, step={float_or_nan(row.get('camera_step_from_previous')):.3f}, "
        f"prevRelP90={float_or_nan(row.get('previous_relative_p90')):.3f}, "
        f"npzMinor/k10={float_or_nan(row.get('npz_minor_ratio_vs_k10')):.3f}"
    )


def official_save_pose_depth_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official-save pose/depth report could not be read."
    scope = get_path(report, "scope") or {}
    npz = get_path(report, "summary.styles.npz_streaming_style.k35_over_k10") or {}
    glb = get_path(report, "summary.styles.glb_style.k35_over_k10") or {}
    return (
        f"frame_source={scope.get('frame_source')}, frame_count={scope.get('frame_count')}; "
        f"npz minor vs k10={float_or_nan(npz.get('minor_ratio_vs_k10')):.3f}, "
        f"npz bbox vs k10={float_or_nan(npz.get('bbox_ratio_vs_k10')):.3f}; "
        f"glb minor vs k10={float_or_nan(glb.get('minor_ratio_vs_k10')):.3f}."
    )


def official_pytorch_image_only_pose_depth_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official PyTorch image-only pose/depth report could not be read."
    scope = get_path(report, "scope") or {}
    npz = get_path(
        report,
        "summary.styles.npz_streaming_style_conf_minus_one.k35_over_k10",
    ) or {}
    glb = get_path(
        report,
        "summary.styles.glb_style_raw_conf.k35_over_k10",
    ) or {}
    pose = get_path(report, "summary.pose") or {}
    depth = get_path(report, "summary.depth") or {}
    runtime = scope.get("runtime") or {}
    return (
        f"camera_mode={scope.get('camera_mode')}, ref_view_strategy={scope.get('ref_view_strategy')}, "
        f"process_res={scope.get('process_res')}, "
        f"shape={scope.get('processed_shape_nhwc')}; "
        f"npz minor vs k10={float_or_nan(npz.get('minor_ratio_vs_k10')):.3f}, "
        f"npz bbox vs k10={float_or_nan(npz.get('bbox_ratio_vs_k10')):.3f}; "
        f"glb minor vs k10={float_or_nan(glb.get('minor_ratio_vs_k10')):.3f}; "
        f"pose diag ratio={float_or_nan(pose.get('k35_over_k10_pose_diag')):.3f}, "
        f"depth p95 ratio={float_or_nan(depth.get('k35_over_k10_p95')):.3f}; "
        f"rss_after={float_or_nan(runtime.get('rss_after_mb')):.1f}MB, "
        f"run_ms={float_or_nan(runtime.get('run_ms')):.0f}."
    )


def official_downstream_core_vs_full_chunk_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official downstream core-vs-full-chunk audit could not be read."
    py = get_path(report, "official_pytorch_image_only_window016") or {}
    core = get_path(py, "official_core_like_k17") or {}
    full = get_path(py, "full_chunk_k35") or {}
    full_vs_core = get_path(py, "k35_vs_k17") or {}
    first = get_path(py, "first_events.npz_first_minor_ge_1_35") or {}
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"core-like k17 npz minor/k10={float_or_nan(core.get('npz_minor_ratio_vs_k10')):.3f}, "
        f"bbox/k10={float_or_nan(core.get('npz_bbox_ratio_vs_k10')):.3f}; "
        f"full k35 npz minor/k10={float_or_nan(full.get('npz_minor_ratio_vs_k10')):.3f}, "
        f"bbox/k10={float_or_nan(full.get('npz_bbox_ratio_vs_k10')):.3f}; "
        f"k35/k17 npz minor={float_or_nan(full_vs_core.get('npz_minor_ratio_k35_over_k17')):.3f}; "
        f"first npz minor>=1.35 at k={first.get('k')}."
    )


def save_window_ownership_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official-save window ownership attribution report could not be read."
    summaries = report.get("window_summaries", {})
    w16 = summaries.get("window_016", {})
    w17 = summaries.get("window_017", {})
    return (
        f"window_016 npz minor={float_or_nan(w16.get('npz_minor_ratio_vs_k10')):.3f}, "
        f"bbox={float_or_nan(w16.get('npz_bbox_ratio_vs_k10')):.3f}; "
        f"window_017 npz minor={float_or_nan(w17.get('npz_minor_ratio_vs_k10')):.3f}, "
        f"bbox={float_or_nan(w17.get('npz_bbox_ratio_vs_k10')):.3f}; "
        f"decision={str_path(report, 'decision.status')}."
    )


def cap1396_acceptance_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "cap-1396 capture continuity acceptance report could not be read."
    quality = get_path(report, "target_frame.quality") or {}
    step = get_path(report, "adjacent_continuity.previous_to_target") or {}
    breach = get_path(report, "adjacent_continuity.breach_summary") or {}
    slot = get_path(report, "pose_depth_context.target_slot") or {}
    return (
        f"accepted={quality.get('accepted')}, kWindowWeight={float_or_nan(quality.get('kWindowWeight')):.3f}; "
        f"cap-1369->cap-1396 dt={float_or_nan(step.get('timestampDeltaSeconds')):.3f}s, "
        f"translation={float_or_nan(step.get('translationStepM')):.3f}m, "
        f"elevation={float_or_nan(step.get('elevationDeltaRad')):.3f}rad; "
        f"violations={breach.get('violation_count')}; "
        f"window_016 slot={slot.get('slot')}, cumulative pose diag={float_or_nan(slot.get('cumulative_pose_diag')):.3f}."
    )


def dart_input_continuity_risk_contract_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Dart input continuity-risk contract audit could not be read."
    metrics = report.get("metrics", {})
    step = get_path(report, "window.first_high_risk_step") or {}
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"window={metrics.get('audited_window_id')}, "
        f"official_save_frames={metrics.get('official_save_frame_count')}, "
        f"first_saved_risk={metrics.get('first_official_save_high_risk_frame_id')}, "
        f"save_high_risk_steps={metrics.get('official_save_high_risk_step_count')}, "
        f"chunk_high_risk_steps={metrics.get('chunk_high_risk_step_count')}; "
        f"first break {step.get('fromFrameID')}->{step.get('toFrameID')} "
        f"dt={float_or_nan(step.get('timestampDeltaSeconds')):.3f}s, "
        f"translation={float_or_nan(step.get('translationStepM')):.3f}m, "
        f"elevation={float_or_nan(step.get('elevationDeltaRad')):.3f}rad."
    )


def upstream_path_parity_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official upstream path parity audit could not be read."
    gaps = [
        item
        for item in report.get("checks", [])
        if isinstance(item, dict) and item.get("status") in {"parity_gap", "missing", "fail"}
    ]
    gap_ids = ", ".join(str(item.get("id")) for item in gaps[:5])
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"official_algorithm_blame_supported={str_path(report, 'decision.official_algorithm_blame_supported')}; "
        f"current_thickness_authority={str_path(report, 'decision.current_thickness_authority')}; "
        f"gaps={gap_ids}."
    )


def image_tensor_contract_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Image tensor contract parity audit could not be read."
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"normalization_parity={str_path(report, 'decision.normalization_parity')}; "
        f"resize_contract_parity={str_path(report, 'decision.resize_contract_parity')}; "
        f"conclusion={str_path(report, 'decision.conclusion')}"
    )


def preprocess_pixel_parity_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official preprocess pixel parity audit could not be read."
    exact_match = get_path(report, "decision.exact_tensor_match")
    exact_label = "exact_tensor_match"
    if exact_match is None:
        exact_match = get_path(report, "decision.exact_pixel_match")
        exact_label = "exact_pixel_match"
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"sample_count={report.get('sample_count')}; "
        f"shape_match={str_path(report, 'decision.shape_match')}; "
        f"tensor_cache={str_path(report, 'decision.tensor_cache')}; "
        f"png_lossless_cache={str_path(report, 'decision.png_lossless_cache')}; "
        f"{exact_label}={exact_match}; "
        f"max_abs_normalized={float_or_nan(get_path(report, 'decision.max_abs_normalized')):.6f}; "
        f"mean_abs_normalized_mean={float_or_nan(get_path(report, 'decision.mean_abs_normalized_mean')):.6f}."
    )


def source_decode_parity_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official source decode parity audit could not be read."
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"shape_match={str_path(report, 'decision.shape_match')}; "
        f"byte_exact={str_path(report, 'decision.byte_exact')}; "
        f"max_abs_uint8={str_path(report, 'decision.max_abs_uint8')}; "
        f"mean_abs_uint8={float_or_nan(get_path(report, 'decision.mean_abs_uint8')):.6f}; "
        f"nonzero={str_path(report, 'decision.nonzero_values')}/{str_path(report, 'decision.total_values')}."
    )


def opencv_native_preprocess_parity_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "OpenCV native preprocess parity audit could not be read."
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"sample_count={report.get('sample_count')}; "
        f"pixel_exact={str_path(report, 'decision.pixel_exact')}; "
        f"tensor_exact={str_path(report, 'decision.tensor_exact')}; "
        f"max_abs_uint8={str_path(report, 'decision.max_abs_uint8')}; "
        f"max_abs_normalized={float_or_nan(get_path(report, 'decision.max_abs_normalized')):.6f}; "
        f"cv2_version={str_path(report, 'opencv.cv2_version')}."
    )


def cpp_preprocess_kernel_parity_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "C++ preprocess kernel parity audit could not be read."
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"sample_count={report.get('sample_count')}; "
        f"pixel_exact={str_path(report, 'decision.pixel_exact')}; "
        f"tensor_exact={str_path(report, 'decision.tensor_exact')}; "
        f"max_abs_uint8={str_path(report, 'decision.max_abs_uint8')}; "
        f"max_abs_normalized={float_or_nan(get_path(report, 'decision.max_abs_normalized')):.6f}."
    )


def preprocess_prebuilt_matrix_status(report: dict[str, Any]) -> str:
    ready = int_value(report.get("readyCount"))
    package_ready = int_value(report.get("packageReadyCount"))
    ship_ready = int_value(report.get("shipReadyCount"))
    target = int_value(report.get("targetCount"))
    if ready is None or target is None or target <= 0:
        return "unknown"
    if ship_ready == target:
        return "pass"
    if (ship_ready or 0) > 0 or (package_ready or 0) > 0 or ready > 0:
        return "warning"
    return "fail"


def preprocess_prebuilt_matrix_evidence(report: dict[str, Any]) -> str:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    missing = [
        str(row.get("target"))
        for row in rows
        if isinstance(row, dict) and row.get("shipReady") is not True
    ]
    package_missing = [
        str(row.get("target"))
        for row in rows
        if isinstance(row, dict) and row.get("packageReady") is not True
    ]
    current = next(
        (
            row
            for row in rows
            if isinstance(row, dict)
            and row.get("monorepoFallbackEligible") is True
        ),
        {},
    )
    return (
        f"shipReady={report.get('shipReadyCount')}/{report.get('targetCount')}; "
        f"packageReady={report.get('packageReadyCount')}/{report.get('targetCount')}; "
        f"devReady={report.get('readyCount')}/{report.get('targetCount')}; "
        f"host={str_path(report, 'host.os')}_{str_path(report, 'host.arch')}; "
        f"hostAbiProbe={str_path(current, 'abiProbe.status')}; "
        f"hostDependencyAudit={str_path(current, 'dependencyAudit.status')}; "
        f"shipMissing={','.join(missing)}; "
        f"packageMissing={','.join(package_missing)}; "
        f"fallbackPolicy={report.get('hookFallbackPolicy')}"
    )


def preprocess_stage_attribution_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Official preprocess stage attribution audit could not be read."
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"dominant_observed_gap={str_path(report, 'decision.dominant_observed_gap')}; "
        f"runtime_tensor_boundary_exact={str_path(report, 'decision.runtime_tensor_boundary_exact')}; "
        f"source_jpeg_decode_byte_exact={str_path(report, 'decision.source_jpeg_decode_byte_exact')}; "
        f"source_jpeg_decode_max_abs_uint8={str_path(report, 'decision.source_jpeg_decode_max_abs_uint8')}; "
        f"canonical_resize_max_abs_uint8_equiv_upper="
        f"{float_or_nan(get_path(report, 'decision.canonical_resize_max_abs_uint8_equiv_upper')):.6f}."
    )


def status_from_upstream_path_parity(report: dict[str, Any]) -> str:
    status = str_path(report, "decision.status")
    if status == "current_runnable_outputs_are_not_official_image_only_authority":
        return "fail"
    if status == "product_policy_image_only_selected_but_coreml_artifact_missing":
        return "warning"
    return status_from_decision(report, default="unknown")


def status_from_image_only_cam_dec_contract(report: dict[str, Any]) -> str:
    status = str_path(report, "decision.status")
    if status == "official_image_only_cam_dec_contract_not_replicated_in_current_app_coreml":
        return "fail"
    if status == "official_image_only_contract_selected_but_coreml_artifact_missing":
        return "warning"
    return status_from_decision(report, default="unknown")


def image_only_cam_dec_contract_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Image-only cam_dec contract audit could not be read."
    pose_inputs = get_path(report, "pose_coreml_signature.inputs") or []
    image_only_exists = get_path(report, "image_only_coreml_signature.exists")
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"official_image_only_contract={str_path(report, 'decision.official_image_only_contract')}; "
        f"selected_image_only_policy={str_path(report, 'decision.selected_image_only_policy')}; "
        f"pose_coreml_inputs={pose_inputs}; "
        f"target_image_only_exists={image_only_exists}; "
        f"conclusion={str_path(report, 'decision.conclusion')}"
    )


def window007_visual_review_status(report: dict[str, Any]) -> str:
    if not report:
        return "unknown"
    downstream_growth = num_path(
        report,
        "official_downstream_core17.pca_minor_growth_over_first10",
    )
    full_growth = num_path(
        report,
        "full35_diagnostic.pca_minor_growth_over_first10",
    )
    if full_growth > 1.15:
        return "warning"
    if downstream_growth <= 1.15:
        return "pass"
    return "warning"


def window007_visual_review_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "window_007 visual review summary could not be read."
    return (
        "PLY/PNG visual review exported; "
        f"first10_pca_minor={num_path(report, 'first10_baseline.pca_minor_extent'):.3f}; "
        f"official_downstream_core17_growth="
        f"{num_path(report, 'official_downstream_core17.pca_minor_growth_over_first10'):.3f}; "
        f"full35_diagnostic_growth="
        f"{num_path(report, 'full35_diagnostic.pca_minor_growth_over_first10'):.3f}; "
        "metric pass is not visual closure; do not claim thick layer fully solved."
    )


def copy_paste_parity_ledger_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Copy-paste parity ledger could not be read."
    hard_gaps = [
        item
        for item in report.get("rows", [])
        if isinstance(item, dict)
        and str(item.get("status", "")).startswith("parity_gap")
    ]
    copied = [
        item.get("id")
        for item in report.get("rows", [])
        if isinstance(item, dict) and item.get("status") == "copied"
    ]
    gap_ids = ", ".join(str(item.get("id")) for item in hard_gaps)
    copied_ids = ", ".join(str(item) for item in copied[:5])
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"hard_gaps={gap_ids or 'none'}; "
        f"copied_rows={copied_ids}; "
        f"answer={str_path(report, 'decision.copy_paste_answer')}"
    )


def fixed_shape_preprocess_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Fixed-shape preprocess authority audit could not be read."
    manifest = report.get("manifest", {})
    examples = report.get("official_resize_examples") or []
    first = examples[0] if examples else {}
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"input={manifest.get('input_size')}, sources={manifest.get('source_size_counts')}, "
        f"all_direct_stretch={str_path(report, 'decision.current_manifest_all_direct_stretch')}; "
        f"example {first.get('source_size')} -> current {first.get('current_fixed_input')}, "
        f"official long-side-742 {first.get('official_upper_bound_resize_shape')}, "
        f"height-476 official-like {get_path(first, 'official_long_side_needed_to_match_height.shape')}."
    )


def external_camera_branch_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "External-camera branch parity audit could not be read."
    return (
        f"status={str_path(report, 'decision.status')}; "
        f"pytorch_pose_branch_parity={str_path(report, 'decision.pytorch_pose_branch_parity')}; "
        f"coreml_pre_forward_normalization_parity={str_path(report, 'decision.coreml_pre_forward_normalization_parity')}; "
        f"empirical_raw_vs_pre_norm_equivalent={str_path(report, 'decision.empirical_raw_vs_pre_norm_equivalent')}; "
        f"conclusion={str_path(report, 'decision.conclusion')}"
    )


def external_camera_branch_status(report: dict[str, Any]) -> str:
    status = str_path(report, "decision.status")
    if status == "coreml_pose_path_missing_official_pre_forward_extrinsics_normalization":
        return "fail"
    if status == "coreml_pose_path_pre_forward_extrinsics_normalization_likely_embedded_not_root_cause":
        return "pass"
    return status_from_decision(report, default="unknown")


def external_camera_pre_norm_rerun_evidence(
    official_save_report: dict[str, Any],
    pre_norm_report: dict[str, Any],
) -> str:
    if not pre_norm_report:
        return "Official pre-forward-normalized window_016 rerun report could not be read."
    base_npz = get_path(
        official_save_report,
        "summary.styles.npz_streaming_style.k35_over_k10",
    ) or {}
    base_glb = get_path(
        official_save_report,
        "summary.styles.glb_style.k35_over_k10",
    ) or {}
    pre_npz = get_path(
        pre_norm_report,
        "summary.styles.npz_streaming_style.k35_over_k10",
    ) or {}
    pre_glb = get_path(
        pre_norm_report,
        "summary.styles.glb_style.k35_over_k10",
    ) or {}
    return (
        "research-only rerun with official pre-forward normalized extrinsics: "
        f"npz minor {float_or_nan(base_npz.get('minor_ratio_vs_k10')):.3f}->"
        f"{float_or_nan(pre_npz.get('minor_ratio_vs_k10')):.3f}, "
        f"npz bbox {float_or_nan(base_npz.get('bbox_ratio_vs_k10')):.3f}->"
        f"{float_or_nan(pre_npz.get('bbox_ratio_vs_k10')):.3f}, "
        f"glb minor {float_or_nan(base_glb.get('minor_ratio_vs_k10')):.3f}->"
        f"{float_or_nan(pre_glb.get('minor_ratio_vs_k10')):.3f}; "
        "not a root-cause-level fix for current NPZ downstream thickness."
    )


def continuity_quarantine_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Continuity quarantine true-rerun report could not be read."
    base = get_path(report, "rows.official_save_window016") or {}
    prefix = get_path(report, "rows.prefix_before_first_break") or {}
    drop = get_path(report, "rows.drop_all_high_risk_targets") or {}
    return (
        f"official window_016 npz minor={float_or_nan(base.get('npz_minor_abs')):.3f}, "
        f"bbox={float_or_nan(base.get('npz_bbox_abs')):.3f}; "
        f"prefix minor/orig={float_or_nan(get_path(prefix, 'vs_official_save.npz_minor_ratio')):.3f}; "
        f"drop_high_risk minor/orig={float_or_nan(get_path(drop, 'vs_official_save.npz_minor_ratio')):.3f}, "
        f"bbox/orig={float_or_nan(get_path(drop, 'vs_official_save.npz_bbox_ratio')):.3f}; "
        f"status={str_path(report, 'decision.status')}."
    )


def dart_continuity_quarantine_plan_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Dart continuity quarantine plan audit could not be read."
    metrics = report.get("metrics", {})
    prefix = get_path(report, "window016_variants.window_016_prefix_before_first_break") or {}
    drop = get_path(report, "window016_variants.window_016_drop_all_high_risk_targets") or {}
    return (
        f"official windows={metrics.get('official_window_count')}, "
        f"quarantine variants={metrics.get('quarantine_window_count')}, "
        f"risky source windows={metrics.get('risky_source_window_count')}; "
        f"prefix real={prefix.get('real_frame_count')}, "
        f"drop_high_risk real={drop.get('real_frame_count')}, "
        f"drop minor/orig={float_or_nan(get_path(drop, 'true_rerun.npz_minor_ratio_vs_official_save')):.3f}; "
        f"status={str_path(report, 'decision.status')}."
    )


def continuity_quarantine_expansion_queue_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Continuity quarantine expansion queue report could not be read."
    metrics = report.get("metrics", {})
    batch = metrics.get("recommended_batch_window_ids") or []
    return (
        f"risky source windows={metrics.get('risky_source_window_count')}, "
        f"recommended batch={', '.join(str(item) for item in batch)}, "
        f"manifest ready={metrics.get('recommended_batch_manifest_ready_count')}/{len(batch)}; "
        f"status={str_path(report, 'decision.status')}."
    )


def continuity_quarantine_window_attribution_evidence(report: dict[str, Any]) -> str:
    if not report:
        return "Continuity quarantine window attribution report could not be read."
    base = get_path(report, "rows.official_save_source") or {}
    drop = get_path(report, "rows.drop_all_high_risk_targets") or {}
    return (
        f"{str_path(report, 'source_window_id')} source npz minor/k10="
        f"{float_or_nan(get_path(base, 'within_window.npz_minor_ratio_vs_k10')):.3f}, "
        f"bbox/k10={float_or_nan(get_path(base, 'within_window.npz_bbox_ratio_vs_k10')):.3f}; "
        f"drop minor/orig={float_or_nan(get_path(drop, 'vs_official_save.npz_minor_ratio')):.3f}; "
        f"status={str_path(report, 'decision.status')}."
    )


def first_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


def float_or_nan(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "data": {}}
    with path.open("r", encoding="utf-8") as handle:
        return {"path": str(path), "exists": True, "data": json.load(handle)}


def load_text_report(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "data": {}}


def source_index(sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        name: {"path": item["path"], "exists": item["exists"]}
        for name, item in sources.items()
    }


def bool_path(data: dict[str, Any], dotted: str) -> bool:
    value = get_path(data, dotted)
    return bool(value)


def str_path(data: dict[str, Any], dotted: str) -> str | None:
    value = get_path(data, dotted)
    if value is None:
        return None
    return str(value)


def num_path(data: dict[str, Any], dotted: str) -> float:
    value = get_path(data, dotted)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def get_path(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def plain_language(status: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    return [
        "官方 image-only 语义和 downstream 行为已经足够清楚：不是 AR 输入，也没有隐藏的单 window 去厚融合。",
        "官方 image-only 的位姿来自模型内部 cam_dec；当前 APP 能跑的 pose CoreML 仍要求外部 extrinsics/intrinsics，所以它不是官方上游权威输出。",
        "历史 Research/PyTorch image-only + process_res=504 诊断曾在同一 window_016/K35 下测到 window-internal thickening：NPZ-streaming confidence-minus-one 路径 k35/k10 minor 约 1.554x，bbox 约 1.437x；它保留为归因证据，不再代表产品 CoreML image-only 当前验收结果。",
        "新的 upstream projective geometry audit 不生成点云，直接检查官方 image-only 深度/内参/cam_dec 位姿：slot 10/cap-1396 是第一个 residual spike，同时也是 NPZ minor/k10 第一次超过 1.10 的位置；slot 11/cap-1413 到 1.415x。",
        "这会修正之前的表述：当前 APP 输出不是官方 image-only 权威，但官方 image-only 对照也不能证明 K35 full-chunk merge 天然无厚层。",
        "旧 official-save/core-frame 诊断曾显示 window_016 core-like K17 的 NPZ minor/k10 约 1.502x；这说明不能把历史厚层只怪到 full-chunk merge 或 withheld overlap 尾帧。",
        "当前产品 metric 口径已经改为真实 APP/native image-only CoreML 输出的 official_downstream frames；这条口径下 6 个 risky windows 全部低于 1.15 阈值，但这只是 metric pass，不是视觉厚层关闭。",
        "GLB-style raw confidence 路径温和得多：k35/k10 minor 约 1.233x；因此 downstream/filter/confidence convention 对肉眼厚层影响很大。",
        "K10 到 K35 的 depth p95 只约 1.015x，但 pose span 约 4.956x；厚层更像大视角跨度下 pose/depth 一致性没完全压齐，而不是深度整体漂大。",
        "最高优先级产品 blocker 已改变：APP/CoreML official image-only cam_dec artifact/signature 已落地，同一 capture 的 6 个 risky windows APP/native image-only regression 在 official_downstream metric 口径下通过；但 window_007 PLY/PNG 视觉验收未关闭，不能说厚层完全解决。另一个工程差异是 C++ OpenCV/libjpeg preprocess kernel 的 iOS/Android/Harmony/Windows 预编译库与平台打包矩阵还没闭环；当前 macOS arm64 只是开发机 fallback，仍有 /opt/homebrew OpenCV 绝对依赖，shipReady 不能算过。",
        "即使只看 optional external-camera API，Research PyTorch pose 分支和当前 pose CoreML wrapper 都支持官方式 pre-forward extrinsics normalize；Mac/Swift 喂 raw w2c 对这个 wrapper 是预期输入。",
        "official preprocess 产品路径已经闭合到 capture package/Research：source_highres JPEG 由 C++ OpenCV/libjpeg kernel 解码、resize、patch-align、normalize，32 帧抽样对官方 InputProcessor pixel/tensor exact，max diff 为 0。",
        "runtime tensor 边界也闭合：photos_depth/photos_depth_tensor 默认已改为官方 process_res=504 + upper_bound_resize + nearest patch-align，DA3 运行输入是 normalized float32 CHW tensor；官方 InputProcessor 读同一 photos_depth PNG 后与 runtime tensor exact match。",
        "source decode audit 仍显示 cap-1 在原始 4224x2376 阶段 PIL/libjpeg 与 Dart package:image 不 byte-exact：max abs uint8 为 12，mean abs 约 0.564；但这现在只约束 Dart fallback，不再是产品 official preprocess blocker。",
        "canonical RGB probe 仍可作为归因证据：如果官方 InputProcessor 从 Dart 解码后的 lossless PNG 开始，cap-1 max normalized diff 从 high-res source 的约 0.035 降到约 0.0174，mean 约 1.6e-7；说明之前差异里 JPEG decode 和 resize 都有贡献。",
        "固定 742x476/direct_stretch 不再是默认 parity 目标，只保留为旧 pose-conditioned compatibility 路径。",
        "K35 是唯一保留的官方差异；89GiB/178GiB 属于研究导出/编译硬 parity 的中间 buffer，不是手机/平板/笔记本运行 DA3 的产品门槛。",
        "当前可运行 DA3BASE_476x742_N35_pose CoreML 已降级为兼容路径；默认目标资源名 DA3BASE_280x504_N35_image_only 已经导出并通过 image-only signature gate。",
        "最新代码把 official image-only 作为默认 contract；OpenCV w2c 和 3x3 intrinsics 只保留为 pose-conditioned compat/metadata，不再作为官方 image-only 输入。",
        "同一 strict capture/window_016 已经用 Dart camera contract + 当前 pose CoreML + 官方 postprocess 重跑；full-chunk 厚层仍存在。",
        "现在已把官方 save_depth_conf_result 选帧落到 Dart/Research：window_016 downstream 只保留 17 帧，后 18 帧是 withheld overlap。",
        "Dart 官方 window plan 现在额外暴露 image-only 输入连续性风险：window_016 的第一个 official-save high-risk target 是 cap-1396，官方帧集保持不变；这把 upstream 输入断点和 downstream 保存帧明确连起来了。",
        "Dart capture package 的 officialSaveFrameIDs/downstreamFrameIDs policy 已有 smoke 通过；continuity quarantine 明确是 research counterfactual，不冒充官方默认。",
        "APP DepthStage 会用 downstreamFrameIDs 过滤 native/CoreML 返回帧后写 depth_index；Research/desktop downstream 权威仍是官方 Python npz_output_process.py，APP PointCloudStage 只是移动端 replay，禁止 full-K window reports/withheld slots 输入，只消费 depth_index frames[]。",
        "按 official-save 17 帧重测后，window_016 的 npz-style minor 仍约为 k10 的 1.429x，厚层没有关闭。",
        "新做的 research-only 真重跑把官方 pre-forward extrinsics normalization 加进 CoreML pose 输入；npz-style minor 只从 1.429x 到 1.418x；随后审计确认 pose CoreML wrapper 内部本来也支持这一步，所以它不是厚层主因。",
        "window_017 已按 official-save 17 帧重跑：cap-1514/cap-1529 是风险帧，但 window_017 npz minor 约 0.970x，没有继续拉厚。",
        "continuity quarantine 真重跑只能说明当前非官方 pose-conditioned 路径里，拆开不连续片段会让 window_016 变薄；它不是官方复刻完成的证据。",
        "window_021、window_004、window_007 是负控：有 continuity 风险但不厚，进一步说明不能把当前现象简化成一个自研硬规则。",
        "下一步不是追 A100，也不是重测最高分辨率；应继续做找不同：先用 PLY/肉眼确认 official_downstream_core17 是否仍不可接受，如果不可接受就继续追 DA3 上游 depth/pose consistency 和官方 downstream 差异；同时把 DA3BASE_280x504_N35_image_only 的 APP/native 回归搬到真机/平板/笔记本 telemetry，并补齐 C++ OpenCV/libjpeg preprocess kernel 的 shippable 预编译库与平台打包矩阵。",
    ]


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "overall": report["overall"],
        "failing_or_blocked": [
            {"id": row["id"], "status": row["status"], "evidence": row["evidence"]}
            for row in report["rows"]
            if row["status"] in {"fail", "blocked", "warning"}
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 parity closure matrix",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{report['overall']['status']}`",
        f"- goal complete: `{report['overall']['goal_complete']}`",
        f"- target missing: `{report['overall']['target_missing']}`",
        f"- overlap gate blocked: `{report['overall']['overlap_gate_blocked']}`",
        f"- local target export preflight failed: `{report['overall']['local_target_export_preflight_failed']}`",
        "",
        report["overall"]["next_best_action"],
        "",
        "## 大白话",
        "",
    ]
    for item in report["plain_language"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Matrix",
            "",
            "| check | status | evidence | source |",
            "|---|---:|---|---|",
        ]
    )
    for item in report["rows"]:
        lines.append(
            "| `{id}` | `{status}` | {evidence} | `{source}` |".format(
                id=item["id"],
                status=item["status"],
                evidence=escape_md(item["evidence"]),
                source=Path(item["source"]).name,
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
