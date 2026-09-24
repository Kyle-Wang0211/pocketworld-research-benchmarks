#!/usr/bin/env python3
"""Gate whether the fixed official image-only DA3 path keeps K35 thickness controlled.

This is intentionally target-only. It does not search for a smaller runnable
resolution. The product contract is DA3BASE_280x504_N35_image_only, and the
question is whether the official image-only CoreML path still produces the
single-window same-surface thick layer.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from strict_k35_window_official_filter_micro_audit import (
    build_group,
    export_npz_streaming_style_group,
    load_slot,
    metrics_for_group,
)


GROUPS = {
    "slot_00": [0],
    "first_10": list(range(10)),
    "first_35": list(range(35)),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--pose-da3-dir", type=Path, required=True)
    parser.add_argument("--image-only-da3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_016")
    parser.add_argument("--target-resource", default="DA3BASE_280x504_N35_image_only")
    parser.add_argument("--window-size", type=int, default=35)
    parser.add_argument("--height", type=int, default=280)
    parser.add_argument("--width", type=int, default=504)
    parser.add_argument(
        "--preprocess-baseline",
        choices=["photos_depth_same_input", "photos_highres_official_api_reference"],
        default="photos_depth_same_input",
        help=(
            "Label and verify the image tensor baseline. photos_depth_same_input is "
            "the fixed 742x476 CoreML/PyTorch parity path; photos_highres_official_api_reference "
            "is the dynamic official API preprocessing reference and is not the current CoreML gate."
        ),
    )
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--npz-sample-ratio", type=float, default=0.015)
    parser.add_argument("--min-minor-growth-improvement", type=float, default=0.15)
    parser.add_argument("--max-acceptable-image-only-minor-growth", type=float, default=1.15)
    parser.add_argument("--date", default="2026-06-04")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_image_only_overlap_regression_gate.json", report)
    write_markdown(
        args.out_dir / "official_da3_image_only_overlap_regression_gate_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    preprocess_inspection = inspect_preprocess_baseline(args.capture_dir, args)
    pose_inspection = inspect_da3_output(
        args.pose_da3_dir,
        expected_contract="pose_conditioned",
        args=args,
    )
    image_only_inspection = inspect_da3_output(
        args.image_only_da3_dir,
        expected_contract="image_only",
        args=args,
    )

    can_compute_image_only = bool(
        image_only_inspection["ready_for_window_metrics"]
    ) and bool(preprocess_inspection["ready_for_this_gate"])
    can_compare = (
        can_compute_image_only
        and bool(pose_inspection["ready_for_window_metrics"])
    )
    datasets: dict[str, Any] = {}
    comparison: dict[str, Any] | None = None
    if pose_inspection["ready_for_window_metrics"]:
        datasets["pose_conditioned_reference"] = compute_window_metrics(
            args.capture_dir,
            args.pose_da3_dir,
            args.window_id,
            args,
        )
    if can_compute_image_only:
        datasets["image_only_candidate"] = compute_window_metrics(
            args.capture_dir,
            args.image_only_da3_dir,
            args.window_id,
            args,
        )
    if can_compare:
        comparison = compare_datasets(
            datasets["pose_conditioned_reference"],
            datasets["image_only_candidate"],
            args,
        )

    decision = derive_decision(
        preprocess_inspection=preprocess_inspection,
        pose_inspection=pose_inspection,
        image_only_inspection=image_only_inspection,
        can_compute_image_only=can_compute_image_only,
        can_compare=can_compare,
        image_only_dataset=datasets.get("image_only_candidate"),
        comparison=comparison,
        args=args,
    )
    return {
        "schema_version": "aether_official_da3_image_only_overlap_regression_gate_v1",
        "date": args.date,
        "purpose": (
            "Fixed-target DA3BASE_280x504_N35_image_only regression gate for the "
            "single-K35-window same-surface overlap/thick-layer problem."
        ),
        "fixed_contract": {
            "resource": args.target_resource,
            "window_size": args.window_size,
            "height": args.height,
            "width": args.width,
            "camera_policy": "official_image_only_no_arkit_vio_inputs",
            "preprocess_baseline": args.preprocess_baseline,
            "comparison_policy": "old_pose_conditioned_is_reference_only",
            "not_a_dimension_sweep": True,
        },
        "official_downstream_parameters": {
            "path": "results_output/frame_*.npz + npz_output_process.py",
            "conf_threshold_coef": args.npz_conf_threshold_coef,
            "sample_ratio": args.npz_sample_ratio,
            "cleanup": "none",
        },
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "pose_da3_dir": str(args.pose_da3_dir),
            "image_only_da3_dir": str(args.image_only_da3_dir),
            "window_id": args.window_id,
        },
        "preprocess_baseline": preprocess_inspection,
        "inspections": {
            "pose_conditioned_reference": pose_inspection,
            "image_only_candidate": image_only_inspection,
        },
        "datasets": datasets,
        "comparison": comparison,
        "decision": decision,
        "next_run_command": build_next_run_command(args),
    }


def inspect_preprocess_baseline(capture_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = capture_dir / "da3_input_manifest.json"
    bundle_path = capture_dir / "photo_bundle.json"
    manifest = read_json_or_empty(manifest_path)
    bundle = read_json_or_empty(bundle_path)
    if args.preprocess_baseline == "photos_depth_same_input":
        frames = list(manifest.get("frames") or [])
        frame0 = dict(frames[0]) if frames else {}
        missing_depth_images = []
        for row in frames:
            rel = row.get("depthImageRelativePath")
            if rel is None or not (capture_dir / str(rel)).exists():
                missing_depth_images.append(str(row.get("id") or rel))
                if len(missing_depth_images) >= 20:
                    break
        shape_matches = (
            int(manifest.get("inputWidth") or frame0.get("inputWidth") or -1) == args.width
            and int(manifest.get("inputHeight") or frame0.get("inputHeight") or -1) == args.height
        )
        resize = dict(frame0.get("resize") or {})
        transform = dict(frame0.get("transform") or {})
        official_process_res = (
            resize.get("mode") == "upper_bound_resize_patch_align"
            and int(resize.get("processRes") or -1) == 504
            and resize.get("processResMethod") == "upper_bound_resize"
        )
        ready = (
            manifest_path.exists()
            and bool(frames)
            and shape_matches
            and official_process_res
            and not missing_depth_images
        )
        return {
            "baseline": args.preprocess_baseline,
            "ready_for_this_gate": ready,
            "manifest_path": str(manifest_path),
            "manifest_exists": manifest_path.exists(),
            "frame_count": len(frames),
            "shape_matches_fixed_target": shape_matches,
            "expected_tensor_source": "photos_depth official process_res=504 upper_bound_resize patch-aligned images",
            "official_api_preprocess_equivalent": True,
            "coreml_same_input_parity": True,
            "resize_mode": resize.get("mode"),
            "process_res": resize.get("processRes"),
            "process_res_method": resize.get("processResMethod"),
            "interpolation": resize.get("interpolation"),
            "scale_x": transform.get("scaleX"),
            "scale_y": transform.get("scaleY"),
            "aspect_preserving": same_float(transform.get("scaleX"), transform.get("scaleY")),
            "missing_depth_image_count_capped": len(missing_depth_images),
            "missing_depth_images_sample": missing_depth_images,
            "blocking_reasons": preprocess_blocking_reasons(
                manifest_path.exists(),
                bool(frames),
                shape_matches,
                official_process_res,
                not missing_depth_images,
            ),
        }

    frames = list(bundle.get("frames") or [])
    missing_highres = []
    for row in frames:
        rel = row.get("highresFilename") or row.get("previewFilename")
        if rel is None:
            missing_highres.append(str(row.get("id") or "unknown"))
            continue
        path = capture_dir / "photos_highres" / str(rel)
        if not path.exists():
            missing_highres.append(str(row.get("id") or rel))
        if len(missing_highres) >= 20:
            break
    return {
        "baseline": args.preprocess_baseline,
        "ready_for_this_gate": False,
        "manifest_path": str(bundle_path),
        "manifest_exists": bundle_path.exists(),
        "frame_count": len(frames),
        "expected_tensor_source": "photos_highres through official DepthAnything3 upper_bound_resize",
        "official_api_preprocess_equivalent": True,
        "coreml_same_input_parity": False,
        "missing_highres_count_capped": len(missing_highres),
        "missing_highres_sample": missing_highres,
        "blocking_reasons": [
            "current_overlap_gate_reads CoreML output dirs produced from photos_depth",
            "use official PyTorch window export for photos_highres dynamic API reference",
        ],
    }


def preprocess_blocking_reasons(
    manifest_exists: bool,
    has_frames: bool,
    shape_matches: bool,
    official_process_res: bool,
    images_exist: bool,
) -> list[str]:
    reasons = []
    if not manifest_exists:
        reasons.append("da3_input_manifest_missing")
    if not has_frames:
        reasons.append("da3_input_manifest_has_no_frames")
    if not shape_matches:
        reasons.append("photos_depth_shape_not_fixed_target")
    if not official_process_res:
        reasons.append("photos_depth_not_official_process_res504_upper_bound_resize")
    if not images_exist:
        reasons.append("photos_depth_images_missing")
    return reasons


def inspect_da3_output(
    da3_dir: Path,
    *,
    expected_contract: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    depth_index_path = da3_dir / "depth_index.json"
    reports_path = da3_dir / "mac_da3_window_reports.json"
    exists = da3_dir.exists()
    depth_index = read_json_or_empty(depth_index_path)
    reports = read_json_or_empty(reports_path)
    contract = extract_contract(depth_index)
    resource = extract_resource(depth_index)
    dimensions = extract_dimensions(depth_index)
    window = find_window(reports, args.window_id)
    frame_rows = [] if window is None else sorted(
        list(window.get("frames") or []),
        key=lambda row: int(row.get("windowSlot", 0)),
    )
    outputs_exist = all_frame_outputs_exist(da3_dir, frame_rows)
    shape_matches = (
        dimensions.get("window_size") == args.window_size
        and dimensions.get("height") == args.height
        and dimensions.get("width") == args.width
    )
    if dimensions.get("window_size") is None and frame_rows:
        shape_matches = (
            len(frame_rows) == args.window_size
            and int(frame_rows[0].get("depthHeight", -1)) == args.height
            and int(frame_rows[0].get("depthWidth", -1)) == args.width
        )
    if expected_contract == "image_only":
        contract_matches = contract == "image_only"
        resource_matches = resource in (None, args.target_resource)
    elif expected_contract == "pose_conditioned":
        contract_matches = contract in (
            None,
            "pose_conditioned",
            "pose_conditioned_coreml_requires_image_extrinsics_intrinsics",
        )
        resource_matches = True
    else:
        contract_matches = False
        resource_matches = False

    missing_reasons = []
    if not exists:
        missing_reasons.append("da3_output_dir_missing")
    if not depth_index_path.exists():
        missing_reasons.append("depth_index_missing")
    if not reports_path.exists():
        missing_reasons.append("mac_da3_window_reports_missing")
    if window is None:
        missing_reasons.append("window_missing")
    if frame_rows and len(frame_rows) < args.window_size:
        missing_reasons.append("window_has_too_few_frames")
    if frame_rows and not outputs_exist:
        missing_reasons.append("frame_output_bins_missing")
    if exists and depth_index_path.exists() and not contract_matches:
        missing_reasons.append("da3_input_contract_not_expected")
    if expected_contract == "image_only" and resource is not None and not resource_matches:
        missing_reasons.append("resource_not_target_image_only")
    if depth_index_path.exists() and not shape_matches:
        missing_reasons.append("shape_not_fixed_target")

    ready = (
        exists
        and depth_index_path.exists()
        and reports_path.exists()
        and window is not None
        and len(frame_rows) >= args.window_size
        and outputs_exist
        and contract_matches
        and resource_matches
        and shape_matches
    )
    return {
        "dir": str(da3_dir),
        "exists": exists,
        "depth_index_exists": depth_index_path.exists(),
        "mac_da3_window_reports_exists": reports_path.exists(),
        "expected_contract": expected_contract,
        "detected_contract": contract,
        "detected_resource": resource,
        "dimensions": dimensions,
        "window_id": args.window_id,
        "window_present": window is not None,
        "window_frame_count": len(frame_rows),
        "all_frame_outputs_exist": outputs_exist,
        "contract_matches": contract_matches,
        "resource_matches": resource_matches,
        "shape_matches_fixed_target": shape_matches,
        "ready_for_window_metrics": ready,
        "missing_or_blocking_reasons": missing_reasons,
    }


def compute_window_metrics(
    capture_dir: Path,
    da3_dir: Path,
    window_id: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    reports = read_json_or_empty(da3_dir / "mac_da3_window_reports.json")
    window = find_window(reports, window_id)
    if window is None:
        raise KeyError(f"{window_id} not found in {da3_dir}")
    frames = sorted(
        list(window.get("frames") or []),
        key=lambda row: int(row.get("windowSlot", 0)),
    )
    slots = [
        load_slot(frame, capture_dir=capture_dir, da3_dir=da3_dir)
        for frame in frames[: args.window_size]
    ]
    group_reports = {}
    raw_group_map = dict(GROUPS)
    downstream_slots = [
        idx for idx, frame in enumerate(frames[: args.window_size])
        if bool(frame.get("officialDownstreamFrame"))
    ]
    if downstream_slots:
        raw_group_map["official_downstream"] = downstream_slots

    for group_name, raw_slots in raw_group_map.items():
        group_slots = [slot for slot in raw_slots if slot < len(slots)]
        group = build_group(slots, group_slots)
        exported = export_npz_streaming_style_group(
            group,
            conf_threshold_coef=args.npz_conf_threshold_coef,
            sample_ratio=args.npz_sample_ratio,
            seed=9100 + len(group_slots),
        )
        group_reports[group_name] = {
            "slots": group_slots,
            "frame_ids": group["frame_ids"],
            "official_filter": exported["filter"],
            "metrics": metrics_for_group(group, exported),
        }

    return {
        "dir": str(da3_dir),
        "window_id": window_id,
        "style": "official_npz_streaming",
        "groups": group_reports,
        "summary": summarize_groups(group_reports),
    }


def summarize_groups(group_reports: dict[str, Any]) -> dict[str, Any]:
    rows = {
        name: summarize_group(row)
        for name, row in group_reports.items()
    }
    first10 = rows.get("first_10", {})
    first35 = rows.get("first_35", {})
    downstream = rows.get("official_downstream", {})
    return {
        "rows": rows,
        "first35_over_first10": {
            "bbox_diag_growth": safe_div(
                first35.get("bbox_diag_p01_p99"),
                first10.get("bbox_diag_p01_p99"),
            ),
            "pca_minor_growth": safe_div(
                first35.get("pca_minor_extent"),
                first10.get("pca_minor_extent"),
            ),
            "valid_fraction_delta": safe_sub(
                first35.get("valid_fraction_of_pixels"),
                first10.get("valid_fraction_of_pixels"),
            ),
            "conf_threshold_ratio": safe_div(
                first35.get("conf_threshold"),
                first10.get("conf_threshold"),
            ),
            "pose_span_growth": safe_div(
                first35.get("camera_center_diag"),
                first10.get("camera_center_diag"),
            ),
        },
        "official_downstream_over_first10": {
            "bbox_diag_growth": safe_div(
                downstream.get("bbox_diag_p01_p99"),
                first10.get("bbox_diag_p01_p99"),
            ),
            "pca_minor_growth": safe_div(
                downstream.get("pca_minor_extent"),
                first10.get("pca_minor_extent"),
            ),
            "valid_fraction_delta": safe_sub(
                downstream.get("valid_fraction_of_pixels"),
                first10.get("valid_fraction_of_pixels"),
            ),
            "conf_threshold_ratio": safe_div(
                downstream.get("conf_threshold"),
                first10.get("conf_threshold"),
            ),
            "pose_span_growth": safe_div(
                downstream.get("camera_center_diag"),
                first10.get("camera_center_diag"),
            ),
        },
    }


def summarize_group(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row["metrics"]
    return {
        "slot_count": metrics["slot_count"],
        "valid_fraction_of_pixels": metrics["valid_fraction_of_pixels"],
        "sampled_point_count": metrics["sampled_point_count"],
        "conf_threshold": row["official_filter"]["conf_threshold"],
        "bbox_diag_p01_p99": metrics["point_cloud"]["bbox_diag_p01_p99"],
        "pca_minor_extent": metrics["pca"]["minor_extent"],
        "pca_minor_to_major_ratio": metrics["pca"]["minor_to_major_ratio"],
        "camera_center_diag": metrics["pose"]["camera_center_diag"],
    }


def compare_datasets(
    pose_reference: dict[str, Any],
    image_only: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    pose_growth = pose_reference["summary"]["first35_over_first10"]
    image_growth = image_only["summary"]["first35_over_first10"]
    pose_downstream_growth = pose_reference["summary"].get(
        "official_downstream_over_first10",
        {},
    )
    image_downstream_growth = image_only["summary"].get(
        "official_downstream_over_first10",
        {},
    )
    pose_minor = pose_growth.get("pca_minor_growth")
    image_minor = image_growth.get("pca_minor_growth")
    improvement = safe_improvement(pose_minor, image_minor)
    return {
        "pose_first35_over_first10": pose_growth,
        "image_only_first35_over_first10": image_growth,
        "pose_official_downstream_over_first10": pose_downstream_growth,
        "image_only_official_downstream_over_first10": image_downstream_growth,
        "image_only_vs_pose": {
            "pca_minor_growth_improvement_fraction": improvement,
            "bbox_diag_growth_improvement_fraction": safe_improvement(
                pose_growth.get("bbox_diag_growth"),
                image_growth.get("bbox_diag_growth"),
            ),
            "image_only_minor_growth_within_acceptance": (
                as_float(image_minor) is not None
                and as_float(image_minor) <= args.max_acceptable_image_only_minor_growth
            ),
            "image_only_official_downstream_minor_growth_within_acceptance": (
                as_float(image_downstream_growth.get("pca_minor_growth")) is not None
                and as_float(image_downstream_growth.get("pca_minor_growth"))
                <= args.max_acceptable_image_only_minor_growth
            ),
            "image_only_minor_growth_improved_enough": (
                improvement is not None
                and improvement >= args.min_minor_growth_improvement
            ),
        },
    }


def derive_decision(
    *,
    preprocess_inspection: dict[str, Any],
    pose_inspection: dict[str, Any],
    image_only_inspection: dict[str, Any],
    can_compute_image_only: bool,
    can_compare: bool,
    image_only_dataset: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    args: argparse.Namespace,
) -> dict[str, Any]:
    if not image_only_inspection["ready_for_window_metrics"]:
        return {
            "status": "blocked_missing_image_only_target_output",
            "can_judge_original_thick_layer": False,
            "reason": (
                "Need DA3BASE_280x504_N35_image_only CoreML output for the same "
                "capture/window before testing whether overlap thickness is removed."
            ),
            "highest_priority_gap": first_reason(image_only_inspection),
            "do_not_change_dimension": True,
            "do_not_use_arkit_vio_as_da3_input": True,
            "do_not_claim_downstream_cleanup_fixed_upstream_overlap": True,
        }
    if not pose_inspection["ready_for_window_metrics"]:
        pose_reference_warning = first_reason(pose_inspection)
    else:
        pose_reference_warning = None
    if not preprocess_inspection["ready_for_this_gate"]:
        return {
            "status": "blocked_preprocess_baseline_not_ready",
            "can_judge_original_thick_layer": False,
            "reason": (
                "Need a ready photos_depth same-input CoreML baseline for this gate, "
                "or use a separate official PyTorch highres API reference gate."
            ),
            "highest_priority_gap": first_blocking_reason(preprocess_inspection),
            "do_not_change_dimension": True,
            "do_not_mix_photos_depth_and_photos_highres": True,
        }
    if not can_compute_image_only or image_only_dataset is None:
        return {
            "status": "blocked_unexpected_image_only_metric_gap",
            "can_judge_original_thick_layer": False,
            "reason": "Image-only inspection passed but metrics were not produced.",
            "do_not_change_dimension": True,
        }

    image_growth = image_only_dataset["summary"]["first35_over_first10"]
    image_downstream_growth = image_only_dataset["summary"].get(
        "official_downstream_over_first10",
        {},
    )
    image_minor = as_float(image_growth.get("pca_minor_growth"))
    downstream_minor = as_float(image_downstream_growth.get("pca_minor_growth"))
    full_accepted = (
        image_minor is not None
        and image_minor <= args.max_acceptable_image_only_minor_growth
    )
    downstream_accepted = (
        downstream_minor is not None
        and downstream_minor <= args.max_acceptable_image_only_minor_growth
    )
    verdict = comparison["image_only_vs_pose"] if comparison is not None else {}
    if downstream_minor is None:
        status = "blocked_missing_official_downstream_core_frame_group"
    elif downstream_accepted:
        status = "pass_image_only_within_single_window_thickness_threshold"
    else:
        status = "fail_image_only_still_exceeds_single_window_thickness_threshold"
    return {
        "status": status,
        "can_judge_original_thick_layer": True,
        "image_only_reduced_thick_layer": status.startswith("pass"),
        "acceptance": {
            "max_acceptable_image_only_minor_growth": args.max_acceptable_image_only_minor_growth,
            "min_minor_growth_improvement": args.min_minor_growth_improvement,
            "image_only_first35_over_first10": image_growth,
            "image_only_official_downstream_over_first10": image_downstream_growth,
            "product_acceptance_metric":
                "image_only_official_downstream_over_first10.pca_minor_growth",
            "product_acceptance_value": downstream_minor,
            "full_k35_diagnostic_metric":
                "image_only_first35_over_first10.pca_minor_growth",
            "full_k35_diagnostic_value": image_minor,
            "image_only_minor_growth_within_acceptance": full_accepted,
            "image_only_official_downstream_minor_growth_within_acceptance":
                downstream_accepted,
            "pose_reference_warning": pose_reference_warning,
            "can_compare_to_pose_reference": can_compare,
            **verdict,
        },
        "do_not_change_dimension": True,
        "do_not_use_arkit_vio_as_da3_input": True,
        "downstream_cleanup_allowed_as_product_adaptation_only_after_this_gate": True,
    }


def build_next_run_command(args: argparse.Namespace) -> list[str]:
    return [
        "python3.11",
        "tools/python/da3_mac_window_export.py",
        "--capture-dir",
        str(args.capture_dir),
        "--out-dir",
        str(args.image_only_da3_dir),
        "--model",
        "<path-to-DA3BASE_280x504_N35_image_only.mlpackage>",
        "--compute-unit",
        "all",
        "--resume",
    ]


def extract_contract(depth_index: dict[str, Any]) -> str | None:
    geometry = depth_index.get("geometry_contract") or {}
    executor = depth_index.get("mac_research_executor") or {}
    raw = (
        geometry.get("da3_input_contract")
        or executor.get("da3_input_contract")
        or depth_index.get("da3InputContract")
    )
    if raw is None:
        return None
    raw = str(raw)
    if raw == "pose_conditioned_coreml_requires_image_extrinsics_intrinsics":
        return raw
    return raw


def extract_resource(depth_index: dict[str, Any]) -> str | None:
    geometry = depth_index.get("geometry_contract") or {}
    model = depth_index.get("model") or {}
    raw = geometry.get("model_resource") or model.get("resourceName")
    if raw is None:
        return None
    return str(raw).removesuffix(".mlpackage").removesuffix(".mlmodelc")


def extract_dimensions(depth_index: dict[str, Any]) -> dict[str, int | None]:
    model = depth_index.get("model") or {}
    return {
        "window_size": as_int(model.get("windowSize") or depth_index.get("window_size")),
        "height": as_int(model.get("inputHeight") or depth_index.get("input_height")),
        "width": as_int(model.get("inputWidth") or depth_index.get("input_width")),
    }


def find_window(reports: dict[str, Any], window_id: str) -> dict[str, Any] | None:
    for row in reports.get("windows") or []:
        if str(row.get("windowID")) == window_id:
            return row
    return None


def all_frame_outputs_exist(da3_dir: Path, frame_rows: list[dict[str, Any]]) -> bool:
    if not frame_rows:
        return False
    keys = (
        "relativeDepthPath",
        "confidencePath",
        "predExtrinsicsPath",
        "predIntrinsicsPath",
    )
    for row in frame_rows:
        for key in keys:
            rel = row.get(key)
            if rel is None or not (da3_dir / str(rel)).exists():
                return False
    return True


def first_reason(inspection: dict[str, Any]) -> str | None:
    reasons = inspection.get("missing_or_blocking_reasons") or []
    return None if not reasons else str(reasons[0])


def first_blocking_reason(inspection: dict[str, Any]) -> str | None:
    reasons = inspection.get("blocking_reasons") or []
    return None if not reasons else str(reasons[0])


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "fixed_contract": report["fixed_contract"],
        "preprocess_baseline": report["preprocess_baseline"],
        "comparison": report["comparison"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    fixed = report["fixed_contract"]
    params = report["official_downstream_parameters"]
    preprocess = report["preprocess_baseline"]
    inspections = report["inspections"]
    datasets = report["datasets"]
    comparison = report["comparison"]
    lines = [
        "# Official DA3 image-only overlap regression gate",
        "",
        f"日期：{report['date']}",
        "",
        "## 结论",
        "",
        f"- status: `{decision['status']}`",
        f"- can judge original thick layer: `{decision['can_judge_original_thick_layer']}`",
        f"- highest priority gap: `{decision.get('highest_priority_gap')}`",
        "",
        "这个 gate 只回答原始问题：固定 `DA3BASE_280x504_N35_image_only` 后，官方 image-only 路径是否控制住单个 K35 window 内多帧看到同一表面造成的厚层。",
        "",
        "## 固定前提",
        "",
        f"- resource: `{fixed['resource']}`",
        f"- window size: `{fixed['window_size']}`",
        f"- input: `{fixed['height']}x{fixed['width']}`",
        f"- camera policy: `{fixed['camera_policy']}`",
        f"- preprocess baseline: `{fixed['preprocess_baseline']}`",
        f"- old `_pose` role: `{fixed['comparison_policy']}`",
        "- dimension sweep: `disabled`",
        "",
        "## 输入预处理基线",
        "",
        f"- baseline: `{preprocess['baseline']}`",
        f"- ready for this gate: `{preprocess['ready_for_this_gate']}`",
        f"- expected tensor source: `{preprocess.get('expected_tensor_source')}`",
        f"- official API preprocess equivalent: `{preprocess.get('official_api_preprocess_equivalent')}`",
        f"- CoreML same-input parity: `{preprocess.get('coreml_same_input_parity')}`",
        f"- shape matches fixed target: `{preprocess.get('shape_matches_fixed_target')}`",
        f"- resize mode: `{preprocess.get('resize_mode')}`",
        f"- scale x/y: `{fmt_float(preprocess.get('scale_x'))}` / `{fmt_float(preprocess.get('scale_y'))}`",
        f"- aspect preserving: `{preprocess.get('aspect_preserving')}`",
        f"- blocking reasons: `{', '.join(preprocess.get('blocking_reasons') or [])}`",
        "",
        "`photos_depth_same_input` 现在来自官方 process_res=504 upper_bound_resize + patch-align 的缓存；厚层回归比较不能把它和旧 742x476/direct_stretch 输入路径混用。",
        "",
        "## 官方 downstream 参数",
        "",
        f"- path: `{params['path']}`",
        f"- conf threshold coef: `{params['conf_threshold_coef']}`",
        f"- sample ratio: `{params['sample_ratio']}`",
        f"- cleanup: `{params['cleanup']}`",
        "",
        "## 输出检查",
        "",
        "| dataset | ready | contract | resource | shape ok | window frames | reasons |",
        "|---|---:|---|---|---:|---:|---|",
    ]
    for name, row in inspections.items():
        lines.append(
            "| {name} | {ready} | {contract} | {resource} | {shape} | {frames} | {reasons} |".format(
                name=name,
                ready=row["ready_for_window_metrics"],
                contract=fmt(row.get("detected_contract")),
                resource=fmt(row.get("detected_resource")),
                shape=row["shape_matches_fixed_target"],
                frames=row["window_frame_count"],
                reasons=", ".join(row.get("missing_or_blocking_reasons") or []),
            )
        )

    image_only_dataset = datasets.get("image_only_candidate") or {}
    image_summary = image_only_dataset.get("summary") or {}
    if image_summary:
        full = image_summary.get("first35_over_first10") or {}
        downstream = image_summary.get("official_downstream_over_first10") or {}
        lines.extend(
            [
                "",
                "## Image-only 厚层指标",
                "",
                "| metric | full K35 diagnostic first35/first10 | product official_downstream/first10 |",
                "|---|---:|---:|",
                f"| PCA minor growth | {fmt_float(full.get('pca_minor_growth'))} | {fmt_float(downstream.get('pca_minor_growth'))} |",
                f"| bbox diag growth | {fmt_float(full.get('bbox_diag_growth'))} | {fmt_float(downstream.get('bbox_diag_growth'))} |",
                f"| valid fraction delta | {fmt_float(full.get('valid_fraction_delta'))} | {fmt_float(downstream.get('valid_fraction_delta'))} |",
                f"| pose span growth | {fmt_float(full.get('pose_span_growth'))} | {fmt_float(downstream.get('pose_span_growth'))} |",
                "",
                "`full K35` 是诊断项；产品验收看 `official_downstream`，也就是官方 results_output/frame_*.npz 下游实际消费的 core frames。",
            ]
        )

    if comparison is not None:
        pose = comparison["pose_first35_over_first10"]
        image = comparison["image_only_first35_over_first10"]
        verdict = comparison["image_only_vs_pose"]
        lines.extend(
            [
                "",
                "## 厚层对照",
                "",
                "| metric | old `_pose` first35/first10 | image-only first35/first10 |",
                "|---|---:|---:|",
                f"| PCA minor growth | {fmt_float(pose.get('pca_minor_growth'))} | {fmt_float(image.get('pca_minor_growth'))} |",
                f"| bbox diag growth | {fmt_float(pose.get('bbox_diag_growth'))} | {fmt_float(image.get('bbox_diag_growth'))} |",
                f"| valid fraction delta | {fmt_float(pose.get('valid_fraction_delta'))} | {fmt_float(image.get('valid_fraction_delta'))} |",
                f"| pose span growth | {fmt_float(pose.get('pose_span_growth'))} | {fmt_float(image.get('pose_span_growth'))} |",
                "",
                "## Verdict Inputs",
                "",
                f"- PCA minor improvement fraction: `{fmt_float(verdict.get('pca_minor_growth_improvement_fraction'))}`",
                f"- bbox improvement fraction: `{fmt_float(verdict.get('bbox_diag_growth_improvement_fraction'))}`",
                f"- image-only minor growth within acceptance: `{verdict.get('image_only_minor_growth_within_acceptance')}`",
                f"- image-only minor growth improved enough: `{verdict.get('image_only_minor_growth_improved_enough')}`",
            ]
        )
    elif not image_summary:
        lines.extend(
            [
                "",
                "## 当前为什么不能判断厚层是否消失",
                "",
                zh_reason(decision.get("reason", "")),
                "",
                "需要先产出同一 capture、同一 `window_016`、同一 `280x504/N35` 的 image-only DA3 输出。没有这个输出时，不能用尺寸、AR/VIO 或 downstream cleanup 来替代这个实验。",
            ]
        )

    lines.extend(
        [
            "",
            "## 下一次运行",
            "",
            "```bash",
            " ".join(report["next_run_command"]),
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def same_float(left: Any, right: Any, *, tolerance: float = 1e-9) -> bool | None:
    left_f = as_float(left)
    right_f = as_float(right)
    if left_f is None or right_f is None:
        return None
    return abs(left_f - right_f) <= tolerance


def safe_div(num: Any, den: Any) -> float | None:
    n = as_float(num)
    d = as_float(den)
    if n is None or d is None or abs(d) <= 1e-12:
        return None
    return n / d


def safe_sub(left: Any, right: Any) -> float | None:
    a = as_float(left)
    b = as_float(right)
    if a is None or b is None:
        return None
    return a - b


def safe_improvement(old: Any, new: Any) -> float | None:
    old_f = as_float(old)
    new_f = as_float(new)
    if old_f is None or new_f is None or abs(old_f) <= 1e-12:
        return None
    return (old_f - new_f) / old_f


def fmt(value: Any) -> str:
    return "-" if value is None else str(value)


def fmt_float(value: Any) -> str:
    raw = as_float(value)
    if raw is None:
        return "-"
    return f"{raw:.6g}"


def zh_reason(reason: Any) -> str:
    text = str(reason)
    if "Need DA3BASE_280x504_N35_image_only CoreML output" in text:
        return (
            "还缺同一 capture/window 的 `DA3BASE_280x504_N35_image_only` CoreML 输出，"
            "所以现在不能判断 image-only 是否消除了原始厚层问题。"
        )
    return text


if __name__ == "__main__":
    raise SystemExit(main())
