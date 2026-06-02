#!/usr/bin/env python3
"""Audit CoreML/PyTorch confidence semantics and edge alignment.

This is a diagnostics-only script. It does not introduce a new point filter or
fusion rule; it compares existing official-postprocessed CoreML outputs with
saved official PyTorch reference arrays on the same window/cases.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image, ImageOps

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


DEFAULT_CASES = ["k05_res742_mps", "k03_res742_mps", "k10_res476_mps"]
IMAGENET_MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--coreml-dir", type=Path, required=True)
    parser.add_argument("--pytorch-sweep-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_000")
    parser.add_argument("--cases", nargs="+", default=DEFAULT_CASES)
    parser.add_argument("--sample-limit", type=int, default=500_000)
    parser.add_argument("--seed", type=int, default=9021)
    parser.add_argument("--glb-conf-thresh", type=float, default=1.05)
    parser.add_argument("--glb-conf-percentile", type=float, default=40.0)
    parser.add_argument("--glb-ensure-percentile", type=float, default=90.0)
    parser.add_argument("--npz-conf-threshold-coef", type=float, default=0.75)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    frames = load_coreml_frames(args.coreml_dir, args.window_id)
    preprocess_report = audit_preprocess_contract(args.capture_dir, args.pytorch_sweep_dir)

    case_reports = []
    for case_name in args.cases:
        case_dir = args.pytorch_sweep_dir / case_name
        if not case_dir.exists():
            case_reports.append({"case": case_name, "status": "missing", "path": str(case_dir)})
            continue
        case_reports.append(
            audit_case(
                case_name=case_name,
                case_dir=case_dir,
                frames=frames,
                capture_dir=args.capture_dir,
                coreml_dir=args.coreml_dir,
                out_dir=args.out_dir,
                sample_limit=args.sample_limit,
                seed=args.seed + stable_case_offset(case_name),
                glb_conf_thresh=args.glb_conf_thresh,
                glb_conf_percentile=args.glb_conf_percentile,
                glb_ensure_percentile=args.glb_ensure_percentile,
                npz_conf_threshold_coef=args.npz_conf_threshold_coef,
            )
        )

    report = {
        "schema_version": "pocketworld_coreml_pytorch_confidence_edge_audit_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "coreml_dir": str(args.coreml_dir),
            "pytorch_sweep_dir": str(args.pytorch_sweep_dir),
            "window_id": args.window_id,
        },
        "parameters": {
            "cases": args.cases,
            "sample_limit": args.sample_limit,
            "glb_conf_thresh": args.glb_conf_thresh,
            "glb_conf_percentile": args.glb_conf_percentile,
            "glb_ensure_percentile": args.glb_ensure_percentile,
            "npz_conf_threshold_coef": args.npz_conf_threshold_coef,
        },
        "preprocess_contract": preprocess_report,
        "cases": case_reports,
        "interpretation": interpret_report(case_reports, preprocess_report),
    }
    write_json(args.out_dir / "coreml_pytorch_confidence_edge_audit_report.json", report)
    write_markdown(args.out_dir / "coreml_pytorch_confidence_edge_audit_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def load_coreml_frames(coreml_dir: Path, window_id: str) -> list[dict[str, Any]]:
    reports = read_json(coreml_dir / "mac_da3_window_reports.json")
    windows = {str(row["windowID"]): row for row in reports.get("windows", [])}
    if window_id not in windows:
        raise KeyError(f"{window_id} not found in {coreml_dir / 'mac_da3_window_reports.json'}")
    return sorted(windows[window_id].get("frames", []), key=lambda row: int(row.get("windowSlot", 0)))


def audit_case(
    *,
    case_name: str,
    case_dir: Path,
    frames: list[dict[str, Any]],
    capture_dir: Path,
    coreml_dir: Path,
    out_dir: Path,
    sample_limit: int,
    seed: int,
    glb_conf_thresh: float,
    glb_conf_percentile: float,
    glb_ensure_percentile: float,
    npz_conf_threshold_coef: float,
) -> dict[str, Any]:
    pytorch = load_pytorch_case(case_dir)
    k = int(pytorch["depth"].shape[0])
    if k > len(frames):
        raise ValueError(f"{case_name} needs {k} CoreML frames, only {len(frames)} available")
    coreml = load_coreml_stack(frames[:k], capture_dir, coreml_dir)
    direct_shape_match = tuple(coreml["depth"].shape) == tuple(pytorch["depth"].shape)

    comparison_coreml = coreml
    comparison_mode = "direct_pixel" if direct_shape_match else "resized_coreml_weak"
    if not direct_shape_match:
        target_hw = tuple(pytorch["depth"].shape[1:])
        comparison_coreml = {
            **coreml,
            "depth": resize_stack(coreml["depth"], target_hw),
            "conf": resize_stack(coreml["conf"], target_hw),
            "images": resize_image_stack(coreml["images"], target_hw),
        }

    depth_scale = fit_scale(
        comparison_coreml["depth"].reshape(-1).astype(np.float64),
        pytorch["depth"].reshape(-1).astype(np.float64),
    )
    scaled_coreml_depth = comparison_coreml["depth"] * float(depth_scale)
    confidence_pair = array_pair_metrics(
        comparison_coreml["conf"],
        pytorch["conf"],
        sample_limit=sample_limit,
        seed=seed,
    )
    image_pair = image_pair_metrics(comparison_coreml["images"], pytorch["processed_images"])
    threshold_report = threshold_metrics(
        coreml_conf=comparison_coreml["conf"],
        pytorch_conf=pytorch["conf"],
        glb_conf_thresh=glb_conf_thresh,
        glb_conf_percentile=glb_conf_percentile,
        glb_ensure_percentile=glb_ensure_percentile,
        npz_conf_threshold_coef=npz_conf_threshold_coef,
    )
    region_report = region_confidence_metrics(
        coreml_images=comparison_coreml["images"],
        pytorch_images=pytorch["processed_images"],
        coreml_conf=comparison_coreml["conf"],
        pytorch_conf=pytorch["conf"],
        thresholds=threshold_report,
    )
    edge_report = edge_alignment_metrics(
        coreml_images=comparison_coreml["images"],
        pytorch_images=pytorch["processed_images"],
        coreml_depth=scaled_coreml_depth,
        pytorch_depth=pytorch["depth"],
        coreml_conf=comparison_coreml["conf"],
        pytorch_conf=pytorch["conf"],
        thresholds=threshold_report,
    )

    png_path = out_dir / f"{case_name}_confidence_edge_audit.png"
    write_case_figure(
        png_path,
        case_name=case_name,
        coreml=comparison_coreml,
        pytorch=pytorch,
        scaled_coreml_depth=scaled_coreml_depth,
        comparison_mode=comparison_mode,
    )

    return {
        "case": case_name,
        "status": "compared",
        "parsed": parse_case_name(case_name),
        "k": k,
        "coreml_shape": list(coreml["depth"].shape),
        "pytorch_shape": list(pytorch["depth"].shape),
        "comparison_shape": list(comparison_coreml["depth"].shape),
        "comparison_mode": comparison_mode,
        "direct_shape_match": direct_shape_match,
        "outputs": {"confidence_edge_png": str(png_path)},
        "frames": [
            {
                "slot": int(row.get("windowSlot", index)),
                "frame_id": str(row.get("frameID")),
                "image": str(row.get("imageRelativePath")),
            }
            for index, row in enumerate(frames[:k])
        ],
        "depth_scale_to_pytorch": float(depth_scale),
        "confidence_pair": confidence_pair,
        "image_pair": image_pair,
        "thresholds": threshold_report,
        "region_confidence": region_report,
        "edge_alignment": edge_report,
        "summaries": {
            "coreml_conf": summarize_array(comparison_coreml["conf"].reshape(-1)),
            "pytorch_conf": summarize_array(pytorch["conf"].reshape(-1)),
            "coreml_depth_scaled": summarize_array(scaled_coreml_depth.reshape(-1)),
            "pytorch_depth": summarize_array(pytorch["depth"].reshape(-1)),
        },
    }


def load_pytorch_case(case_dir: Path) -> dict[str, np.ndarray]:
    return {
        "depth": np.load(case_dir / "pytorch_depth.npy").astype(np.float32, copy=False),
        "conf": np.load(case_dir / "pytorch_conf.npy").astype(np.float32, copy=False),
        "intrinsics": np.load(case_dir / "pytorch_intrinsics.npy").astype(np.float32, copy=False),
        "extrinsics": np.load(case_dir / "pytorch_extrinsics.npy").astype(np.float32, copy=False),
        "processed_images": np.load(case_dir / "pytorch_processed_images.npy").astype(np.uint8, copy=False),
    }


def load_coreml_stack(frames: list[dict[str, Any]], capture_dir: Path, coreml_dir: Path) -> dict[str, np.ndarray]:
    depths, confs, images = [], [], []
    for frame in frames:
        height = int(frame["depthHeight"])
        width = int(frame["depthWidth"])
        depths.append(
            np.fromfile(coreml_dir / str(frame["relativeDepthPath"]), dtype="<f4")
            .reshape(height, width)
            .astype(np.float32, copy=False)
        )
        confs.append(
            np.fromfile(coreml_dir / str(frame["confidencePath"]), dtype="<f4")
            .reshape(height, width)
            .astype(np.float32, copy=False)
        )
        images.append(load_frame_image(capture_dir / str(frame["imageRelativePath"]), height, width))
    return {
        "depth": np.stack(depths, axis=0),
        "conf": np.stack(confs, axis=0),
        "images": np.stack(images, axis=0),
    }


def load_frame_image(path: Path, height: int, width: int) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.BICUBIC)
        return np.asarray(image, dtype=np.uint8)


def audit_preprocess_contract(capture_dir: Path, pytorch_sweep_dir: Path) -> dict[str, Any]:
    input_manifest = maybe_read_json(capture_dir / "da3_input_manifest.json")
    pytorch_report = maybe_read_json(pytorch_sweep_dir / "official_pytorch_k_sweep_report.json")
    official_manifest = maybe_read_json(pytorch_sweep_dir.parent / "strict_window_000_official_manifest.json")
    frames = list(input_manifest.get("frames") or [])
    official_rows = list(official_manifest.get("frames") or [])
    first_frame = frames[0] if frames else {}
    first_official = official_rows[0] if official_rows else {}

    source_w = int(first_frame.get("sourceWidth") or 0)
    source_h = int(first_frame.get("sourceHeight") or 0)
    input_w = int(first_frame.get("inputWidth") or input_manifest.get("inputWidth") or 0)
    input_h = int(first_frame.get("inputHeight") or input_manifest.get("inputHeight") or 0)
    process_res_values = list((pytorch_report.get("parameters") or {}).get("process_res") or [])
    process_res_method = (pytorch_report.get("parameters") or {}).get("process_res_method")
    expected_official_from_highres = {}
    for process_res in process_res_values:
        expected_official_from_highres[str(process_res)] = official_upper_bound_resize_shape(
            source_w,
            source_h,
            int(process_res),
            patch=14,
        )

    matching_saved_pytorch_input = None
    if first_official.get("jpegPath"):
        path = capture_dir / str(first_official["jpegPath"])
        if path.exists():
            with Image.open(path) as image:
                matching_saved_pytorch_input = {
                    "jpeg_path": str(first_official["jpegPath"]),
                    "size": [int(image.size[0]), int(image.size[1])],
                }

    return {
        "capture_input": {
            "frame_count": len(frames),
            "source_size": [source_w, source_h],
            "model_input_size": [input_w, input_h],
            "resize_mode": ((first_frame.get("resize") or {}).get("mode")),
            "resize_interpolation": ((first_frame.get("resize") or {}).get("interpolation")),
            "transform": first_frame.get("transform"),
            "intrinsics_transform": first_frame.get("intrinsicsTransform"),
        },
        "saved_pytorch_reference": {
            "frame_count": len(official_rows),
            "jpeg_path_kind": first_official.get("jpegPath"),
            "matching_saved_input": matching_saved_pytorch_input,
            "process_res_method": process_res_method,
            "process_res": process_res_values,
        },
        "official_highres_reference_shape": {
            "note": "If official upper_bound_resize were applied directly to the high-res 4224x2376 image, the height would preserve aspect ratio and differ from the fixed CoreML 742x476 input.",
            "expected_shapes_by_process_res": expected_official_from_highres,
        },
    }


def official_upper_bound_resize_shape(width: int, height: int, process_res: int, patch: int) -> dict[str, Any]:
    if width <= 0 or height <= 0 or process_res <= 0:
        return {}
    longest = max(width, height)
    scale = process_res / float(longest)
    resized_w = max(1, int(round(width * scale)))
    resized_h = max(1, int(round(height * scale)))

    def nearest_multiple(value: int) -> int:
        down = (value // patch) * patch
        up = down + patch
        return up if abs(up - value) <= abs(value - down) else down

    final_w = max(1, nearest_multiple(resized_w))
    final_h = max(1, nearest_multiple(resized_h))
    return {
        "after_longest_side_resize": [resized_w, resized_h],
        "after_patch_multiple_resize": [final_w, final_h],
        "scale": scale,
    }


def threshold_metrics(
    *,
    coreml_conf: np.ndarray,
    pytorch_conf: np.ndarray,
    glb_conf_thresh: float,
    glb_conf_percentile: float,
    glb_ensure_percentile: float,
    npz_conf_threshold_coef: float,
) -> dict[str, Any]:
    core_glb = glb_threshold(coreml_conf, glb_conf_thresh, glb_conf_percentile, glb_ensure_percentile)
    pt_glb = glb_threshold(pytorch_conf, glb_conf_thresh, glb_conf_percentile, glb_ensure_percentile)
    core_npz = float(np.nanmean(coreml_conf) * npz_conf_threshold_coef)
    pt_npz = float(np.nanmean(pytorch_conf) * npz_conf_threshold_coef)
    return {
        "glb_style": {
            "params": {
                "conf_thresh": glb_conf_thresh,
                "conf_thresh_percentile": glb_conf_percentile,
                "ensure_thresh_percentile": glb_ensure_percentile,
            },
            "coreml_threshold": core_glb,
            "pytorch_threshold": pt_glb,
            "coreml_valid_fraction": fraction(coreml_conf >= core_glb),
            "pytorch_valid_fraction": fraction(pytorch_conf >= pt_glb),
        },
        "npz_streaming_style": {
            "params": {"conf_threshold_coef": npz_conf_threshold_coef},
            "coreml_threshold": core_npz,
            "pytorch_threshold": pt_npz,
            "coreml_valid_fraction": fraction(coreml_conf >= core_npz),
            "pytorch_valid_fraction": fraction(pytorch_conf >= pt_npz),
        },
    }


def region_confidence_metrics(
    *,
    coreml_images: np.ndarray,
    pytorch_images: np.ndarray,
    coreml_conf: np.ndarray,
    pytorch_conf: np.ndarray,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    return {
        "coreml": dataset_region_metrics(
            images=coreml_images,
            conf=coreml_conf,
            glb_threshold=float(thresholds["glb_style"]["coreml_threshold"]),
            npz_threshold=float(thresholds["npz_streaming_style"]["coreml_threshold"]),
        ),
        "pytorch": dataset_region_metrics(
            images=pytorch_images,
            conf=pytorch_conf,
            glb_threshold=float(thresholds["glb_style"]["pytorch_threshold"]),
            npz_threshold=float(thresholds["npz_streaming_style"]["pytorch_threshold"]),
        ),
    }


def dataset_region_metrics(
    *,
    images: np.ndarray,
    conf: np.ndarray,
    glb_threshold: float,
    npz_threshold: float,
) -> dict[str, Any]:
    gray = rgb_to_gray(images)
    rgb_edge = top_percent_mask(gradient_magnitude(gray), 90.0)
    masks = {
        "all": np.ones(conf.shape, dtype=bool),
        "black_all_channels_lt16": np.all(images < 16, axis=-1),
        "white_all_channels_ge240": np.all(images >= 240, axis=-1),
        "dark_luma_lt32": gray < 32.0,
        "rgb_edge_top10": rgb_edge,
        "rgb_non_edge_bottom70": gradient_magnitude(gray) <= np.percentile(gradient_magnitude(gray), 70.0),
    }
    return {
        name: masked_conf_stats(conf, mask, glb_threshold=glb_threshold, npz_threshold=npz_threshold)
        for name, mask in masks.items()
    }


def edge_alignment_metrics(
    *,
    coreml_images: np.ndarray,
    pytorch_images: np.ndarray,
    coreml_depth: np.ndarray,
    pytorch_depth: np.ndarray,
    coreml_conf: np.ndarray,
    pytorch_conf: np.ndarray,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    core_gray = rgb_to_gray(coreml_images)
    pt_gray = rgb_to_gray(pytorch_images)
    core_rgb_grad = gradient_magnitude(core_gray)
    pt_rgb_grad = gradient_magnitude(pt_gray)
    core_depth_grad = gradient_magnitude(coreml_depth)
    pt_depth_grad = gradient_magnitude(pytorch_depth)
    core_rgb_edge = top_percent_mask(core_rgb_grad, 90.0)
    pt_rgb_edge = top_percent_mask(pt_rgb_grad, 90.0)
    core_depth_edge = top_percent_mask(core_depth_grad, 90.0)
    pt_depth_edge = top_percent_mask(pt_depth_grad, 90.0)
    depth_abs = np.abs(coreml_depth - pytorch_depth)
    depth_rel = depth_abs / np.maximum(np.abs(pytorch_depth), 1e-6)

    pair_rgb_edge = core_rgb_edge | pt_rgb_edge
    pair_non_edge = ~(core_rgb_edge | pt_rgb_edge)
    core_glb_thr = float(thresholds["glb_style"]["coreml_threshold"])
    pt_glb_thr = float(thresholds["glb_style"]["pytorch_threshold"])

    return {
        "coreml": {
            "rgb_edge_depth_edge_recall_top10": mask_recall(core_depth_edge, core_rgb_edge),
            "rgb_edge_conf": masked_conf_stats(coreml_conf, core_rgb_edge, glb_threshold=core_glb_thr, npz_threshold=math.nan),
            "non_edge_conf": masked_conf_stats(coreml_conf, ~core_rgb_edge, glb_threshold=core_glb_thr, npz_threshold=math.nan),
            "rgb_depth_grad_pearson": pearson(core_rgb_grad.reshape(-1), core_depth_grad.reshape(-1)),
        },
        "pytorch": {
            "rgb_edge_depth_edge_recall_top10": mask_recall(pt_depth_edge, pt_rgb_edge),
            "rgb_edge_conf": masked_conf_stats(pytorch_conf, pt_rgb_edge, glb_threshold=pt_glb_thr, npz_threshold=math.nan),
            "non_edge_conf": masked_conf_stats(pytorch_conf, ~pt_rgb_edge, glb_threshold=pt_glb_thr, npz_threshold=math.nan),
            "rgb_depth_grad_pearson": pearson(pt_rgb_grad.reshape(-1), pt_depth_grad.reshape(-1)),
        },
        "pair_depth_disagreement": {
            "on_rgb_edge_union": residual_summary(depth_abs[pair_rgb_edge], depth_rel[pair_rgb_edge]),
            "on_rgb_non_edge": residual_summary(depth_abs[pair_non_edge], depth_rel[pair_non_edge]),
        },
        "edge_mask_overlap": {
            "coreml_vs_pytorch_rgb_edge_iou": mask_iou(core_rgb_edge, pt_rgb_edge),
            "coreml_vs_pytorch_depth_edge_iou": mask_iou(core_depth_edge, pt_depth_edge),
        },
    }


def masked_conf_stats(
    conf: np.ndarray,
    mask: np.ndarray,
    *,
    glb_threshold: float,
    npz_threshold: float,
) -> dict[str, Any]:
    valid_mask = np.asarray(mask, dtype=bool) & np.isfinite(conf)
    values = conf[valid_mask]
    result = {
        "pixel_count": int(values.size),
        "fraction_of_pixels": fraction(valid_mask),
        "conf": summarize_array(values),
    }
    if values.size:
        result["glb_valid_fraction_inside_region"] = float(np.mean(values >= glb_threshold))
        if math.isfinite(npz_threshold):
            result["npz_valid_fraction_inside_region"] = float(np.mean(values >= npz_threshold))
    else:
        result["glb_valid_fraction_inside_region"] = math.nan
        if math.isfinite(npz_threshold):
            result["npz_valid_fraction_inside_region"] = math.nan
    return result


def array_pair_metrics(left: np.ndarray, right: np.ndarray, *, sample_limit: int, seed: int) -> dict[str, Any]:
    left_flat = np.asarray(left, dtype=np.float64).reshape(-1)
    right_flat = np.asarray(right, dtype=np.float64).reshape(-1)
    valid = np.isfinite(left_flat) & np.isfinite(right_flat)
    left_valid = left_flat[valid]
    right_valid = right_flat[valid]
    if left_valid.size == 0:
        return {"status": "no_valid_pairs"}
    if left_valid.size > sample_limit:
        rng = np.random.default_rng(seed)
        idx = rng.choice(left_valid.size, size=sample_limit, replace=False)
        left_cmp = left_valid[idx]
        right_cmp = right_valid[idx]
        sampled = True
    else:
        left_cmp = left_valid
        right_cmp = right_valid
        sampled = False
    return {
        "status": "ok",
        "valid_pair_count": int(left_valid.size),
        "sampled": sampled,
        "sample_count": int(left_cmp.size),
        "coreml_summary": summarize_array(left_valid),
        "pytorch_summary": summarize_array(right_valid),
        "raw": residual_metrics(left_cmp, right_cmp),
        "pearson": pearson(left_cmp, right_cmp),
        "mean_ratio_pytorch_over_coreml": safe_div(float(np.mean(right_cmp)), float(np.mean(left_cmp))),
    }


def image_pair_metrics(coreml_images: np.ndarray, pytorch_images: np.ndarray) -> dict[str, Any]:
    left = coreml_images.astype(np.float32)
    right = pytorch_images.astype(np.float32)
    abs_diff = np.abs(left - right)
    core_gray = rgb_to_gray(coreml_images)
    pt_gray = rgb_to_gray(pytorch_images)
    return {
        "mae_rgb": float(np.mean(abs_diff)),
        "p95_abs_rgb": float(np.percentile(abs_diff, 95)),
        "max_abs_rgb": float(np.max(abs_diff)),
        "exact_pixel_fraction": float(np.mean(np.all(coreml_images == pytorch_images, axis=-1))),
        "coreml_dark_all_channels_lt16_fraction": fraction(np.all(coreml_images < 16, axis=-1)),
        "pytorch_dark_all_channels_lt16_fraction": fraction(np.all(pytorch_images < 16, axis=-1)),
        "coreml_dark_luma_lt32_fraction": fraction(core_gray < 32.0),
        "pytorch_dark_luma_lt32_fraction": fraction(pt_gray < 32.0),
    }


def residual_metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, float]:
    diff = pred - target
    abs_diff = np.abs(diff)
    rel = abs_diff / np.maximum(np.abs(target), 1e-6)
    return {
        "mean_signed": float(np.mean(diff)),
        "mae": float(np.mean(abs_diff)),
        "rmse": float(np.sqrt(np.mean(diff * diff))),
        "median_abs": float(np.median(abs_diff)),
        "p90_abs": float(np.percentile(abs_diff, 90)),
        "p99_abs": float(np.percentile(abs_diff, 99)),
        "median_relative": float(np.median(rel)),
        "p90_relative": float(np.percentile(rel, 90)),
    }


def residual_summary(abs_values: np.ndarray, rel_values: np.ndarray) -> dict[str, Any]:
    abs_arr = np.asarray(abs_values, dtype=np.float64)
    rel_arr = np.asarray(rel_values, dtype=np.float64)
    valid = np.isfinite(abs_arr) & np.isfinite(rel_arr)
    abs_arr = abs_arr[valid]
    rel_arr = rel_arr[valid]
    if abs_arr.size == 0:
        return {"count": 0}
    return {
        "count": int(abs_arr.size),
        "abs_median": float(np.median(abs_arr)),
        "abs_p90": float(np.percentile(abs_arr, 90)),
        "relative_median": float(np.median(rel_arr)),
        "relative_p90": float(np.percentile(rel_arr, 90)),
    }


def rgb_to_gray(images: np.ndarray) -> np.ndarray:
    arr = images.astype(np.float32)
    return arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114


def gradient_magnitude(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    gy, gx = np.gradient(arr, axis=(-2, -1))
    return np.sqrt(gx * gx + gy * gy)


def top_percent_mask(values: np.ndarray, percentile: float) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros(values.shape, dtype=bool)
    threshold = float(np.percentile(finite, percentile))
    return np.isfinite(values) & (values >= threshold)


def glb_threshold(conf: np.ndarray, conf_thresh: float, conf_percentile: float, ensure_percentile: float) -> float:
    values = np.asarray(conf, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return math.nan
    lower = float(np.percentile(values, conf_percentile))
    upper = float(np.percentile(values, ensure_percentile))
    return float(min(max(conf_thresh, lower), upper))


def fit_scale(left: np.ndarray, right: np.ndarray) -> float:
    valid = np.isfinite(left) & np.isfinite(right)
    left = left[valid]
    right = right[valid]
    denom = float(np.dot(left, left))
    if denom <= 1e-12:
        return math.nan
    return float(np.dot(left, right) / denom)


def pearson(left: np.ndarray, right: np.ndarray) -> float:
    valid = np.isfinite(left) & np.isfinite(right)
    left = left[valid].astype(np.float64)
    right = right[valid].astype(np.float64)
    if left.size == 0:
        return math.nan
    left_c = left - np.mean(left)
    right_c = right - np.mean(right)
    denom = float(np.linalg.norm(left_c) * np.linalg.norm(right_c))
    if denom <= 1e-12:
        return math.nan
    return float(np.dot(left_c, right_c) / denom)


def summarize_array(values: np.ndarray) -> dict[str, float | int]:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"count": 0}
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "p05": float(np.percentile(finite, 5)),
        "p40": float(np.percentile(finite, 40)),
        "median": float(np.median(finite)),
        "mean": float(np.mean(finite)),
        "p90": float(np.percentile(finite, 90)),
        "p95": float(np.percentile(finite, 95)),
        "max": float(np.max(finite)),
        "std": float(np.std(finite)),
    }


def fraction(mask: np.ndarray) -> float:
    arr = np.asarray(mask, dtype=bool)
    if arr.size == 0:
        return math.nan
    return float(np.mean(arr))


def mask_recall(pred: np.ndarray, target: np.ndarray) -> float:
    denom = int(np.count_nonzero(target))
    if denom == 0:
        return math.nan
    return float(np.count_nonzero(pred & target) / denom)


def mask_iou(left: np.ndarray, right: np.ndarray) -> float:
    union = int(np.count_nonzero(left | right))
    if union == 0:
        return math.nan
    return float(np.count_nonzero(left & right) / union)


def safe_div(num: float, den: float) -> float:
    if abs(den) <= 1e-12:
        return math.nan
    return float(num / den)


def resize_stack(values: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    target_h, target_w = target_hw
    out = []
    for frame in values:
        image = Image.fromarray(frame.astype(np.float32), mode="F")
        resized = image.resize((target_w, target_h), Image.Resampling.BILINEAR)
        out.append(np.asarray(resized, dtype=np.float32))
    return np.stack(out, axis=0)


def resize_image_stack(values: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    target_h, target_w = target_hw
    out = []
    for frame in values:
        image = Image.fromarray(frame.astype(np.uint8), mode="RGB")
        resized = image.resize((target_w, target_h), Image.Resampling.BICUBIC)
        out.append(np.asarray(resized, dtype=np.uint8))
    return np.stack(out, axis=0)


def write_case_figure(
    path: Path,
    *,
    case_name: str,
    coreml: dict[str, np.ndarray],
    pytorch: dict[str, np.ndarray],
    scaled_coreml_depth: np.ndarray,
    comparison_mode: str,
) -> None:
    k = min(int(coreml["depth"].shape[0]), 5)
    fig, axes = plt.subplots(k, 7, figsize=(18, max(3, 2.6 * k)), squeeze=False)
    conf_abs = np.abs(coreml["conf"] - pytorch["conf"])
    depth_abs = np.abs(scaled_coreml_depth - pytorch["depth"])
    core_rgb_grad = gradient_magnitude(rgb_to_gray(coreml["images"]))
    core_depth_grad = gradient_magnitude(scaled_coreml_depth)
    for row in range(k):
        axes[row, 0].imshow(coreml["images"][row])
        axes[row, 0].set_title(f"slot {row} RGB", fontsize=8)
        draw_image(axes[row, 1], coreml["conf"][row], "CoreML conf")
        draw_image(axes[row, 2], pytorch["conf"][row], "PyTorch conf")
        draw_image(axes[row, 3], conf_abs[row], "conf abs")
        draw_image(axes[row, 4], scaled_coreml_depth[row], "CoreML depth scaled")
        draw_image(axes[row, 5], pytorch["depth"][row], "PyTorch depth")
        edge_overlay = make_edge_overlay(coreml["images"][row], core_rgb_grad[row], core_depth_grad[row])
        axes[row, 6].imshow(edge_overlay)
        axes[row, 6].set_title("RGB edge / depth edge", fontsize=8)
        for col in range(7):
            axes[row, col].axis("off")
    fig.suptitle(f"{case_name} confidence/edge audit ({comparison_mode})", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def draw_image(axis: Any, values: np.ndarray, title: str) -> None:
    finite = values[np.isfinite(values)]
    if finite.size:
        lo = float(np.percentile(finite, 2))
        hi = float(np.percentile(finite, 98))
        if hi <= lo:
            hi = lo + 1.0
    else:
        lo, hi = 0.0, 1.0
    axis.imshow(values, cmap="viridis", vmin=lo, vmax=hi)
    axis.set_title(title, fontsize=8)


def make_edge_overlay(image: np.ndarray, rgb_grad: np.ndarray, depth_grad: np.ndarray) -> np.ndarray:
    base = image.astype(np.float32) * 0.65
    rgb_edge = top_percent_mask(rgb_grad, 90.0)
    depth_edge = top_percent_mask(depth_grad, 90.0)
    overlay = base.copy()
    overlay[rgb_edge, 0] = 255.0
    overlay[rgb_edge, 1] *= 0.35
    overlay[rgb_edge, 2] *= 0.35
    overlay[depth_edge, 2] = 255.0
    overlay[depth_edge, 0] *= 0.35
    overlay[rgb_edge & depth_edge] = np.asarray([255.0, 255.0, 255.0])
    return np.clip(overlay, 0, 255).astype(np.uint8)


def parse_case_name(case_name: str) -> dict[str, Any]:
    match = re.match(r"k(?P<k>\d+)_res(?P<res>\d+)_(?P<device>.+)", case_name)
    if not match:
        return {}
    return {
        "k": int(match.group("k")),
        "process_res": int(match.group("res")),
        "device": match.group("device"),
    }


def stable_case_offset(case_name: str) -> int:
    return sum((index + 1) * ord(ch) for index, ch in enumerate(case_name))


def interpret_report(cases: list[dict[str, Any]], preprocess: dict[str, Any]) -> dict[str, Any]:
    compared = [case for case in cases if case.get("status") == "compared"]
    hard = [case for case in compared if case.get("direct_shape_match")]
    primary = next((case for case in hard if case.get("case") == "k05_res742_mps"), hard[0] if hard else None)
    summary = "没有可比较 case。"
    if primary:
        conf_mae = primary.get("confidence_pair", {}).get("raw", {}).get("mae")
        conf_pearson = primary.get("confidence_pair", {}).get("pearson")
        conf_signed = primary.get("confidence_pair", {}).get("raw", {}).get("mean_signed")
        image_mae = primary.get("image_pair", {}).get("mae_rgb")
        core_edge_recall = primary.get("edge_alignment", {}).get("coreml", {}).get("rgb_edge_depth_edge_recall_top10")
        pt_edge_recall = primary.get("edge_alignment", {}).get("pytorch", {}).get("rgb_edge_depth_edge_recall_top10")
        glb = primary.get("thresholds", {}).get("glb_style", {})
        core_valid = glb.get("coreml_valid_fraction")
        pt_valid = glb.get("pytorch_valid_fraction")
        core_thr = glb.get("coreml_threshold")
        pt_thr = glb.get("pytorch_threshold")
        core_regions = primary.get("region_confidence", {}).get("coreml", {})
        pt_regions = primary.get("region_confidence", {}).get("pytorch", {})
        core_dark = core_regions.get("dark_luma_lt32", {})
        pt_dark = pt_regions.get("dark_luma_lt32", {})
        core_edge = core_regions.get("rgb_edge_top10", {})
        pt_edge = pt_regions.get("rgb_edge_top10", {})
        summary = (
            "主信号看 k05_res742_mps：这是同图同尺寸的硬对比。"
            f"RGB 输入 MAE={format_float(image_mae)}，说明 saved PyTorch reference 与 CoreML 当前输入几乎同口径；"
            f"confidence MAE={format_float(conf_mae)}、mean_signed={format_float(conf_signed)}、pearson={format_float(conf_pearson)}，"
            "说明 confidence 数值尺度仍有明显差异，且 CoreML 整体比 PyTorch 低。"
            f"官方 GLB percentile 阈值 CoreML/PyTorch={format_float(core_thr)}/{format_float(pt_thr)}，"
            f"所以全局 valid fraction 被拉到相近的 {format_float(core_valid)}/{format_float(pt_valid)}。"
            f"暗部 luma<32 区域 GLB valid fraction CoreML/PyTorch="
            f"{format_float(core_dark.get('glb_valid_fraction_inside_region'))}/"
            f"{format_float(pt_dark.get('glb_valid_fraction_inside_region'))}，"
            "说明暗部大面积保留不是 CoreML 独有；"
            f"RGB edge GLB valid fraction CoreML/PyTorch="
            f"{format_float(core_edge.get('glb_valid_fraction_inside_region'))}/"
            f"{format_float(pt_edge.get('glb_valid_fraction_inside_region'))}，"
            f"RGB edge 与 depth edge top10 recall CoreML/PyTorch="
            f"{format_float(core_edge_recall)}/{format_float(pt_edge_recall)}。"
        )
    return {
        "primary_case": None if primary is None else primary.get("case"),
        "summary": summary,
        "preprocess_note": (
            "当前 saved PyTorch reference 使用 photos_depth/cap-*.jpg，与 CoreML 输入同源；"
            "但 capture 的 photos_depth 是 highres direct_stretch 到 742x476。"
            "如果从 highres 直接按官方 upper_bound_resize@742，会得到约 742x420，"
            "这仍是移动固定输入模型与官方动态宽高比 API 的结构性差异。"
        ),
        "suggested_next_check": (
            "下一步优先把同 K、同图、同 official GLB-style filter 的 CoreML/PyTorch 点云放一起看。"
            "如果 PyTorch 也保留类似暗部片状厚层，就不要先改 CoreML parity，而要回到官方导出规则、"
            "输入宽高比策略和移动固定尺寸适配。"
        ),
    }


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "interpretation": report["interpretation"],
        "cases": [
            {
                "case": case.get("case"),
                "status": case.get("status"),
                "mode": case.get("comparison_mode"),
                "direct": case.get("direct_shape_match"),
                "image_mae_rgb": case.get("image_pair", {}).get("mae_rgb"),
                "conf_mae": case.get("confidence_pair", {}).get("raw", {}).get("mae"),
                "conf_pearson": case.get("confidence_pair", {}).get("pearson"),
                "glb_valid_coreml": case.get("thresholds", {}).get("glb_style", {}).get("coreml_valid_fraction"),
                "glb_valid_pytorch": case.get("thresholds", {}).get("glb_style", {}).get("pytorch_valid_fraction"),
                "coreml_edge_recall": case.get("edge_alignment", {})
                .get("coreml", {})
                .get("rgb_edge_depth_edge_recall_top10"),
                "pytorch_edge_recall": case.get("edge_alignment", {})
                .get("pytorch", {})
                .get("rgb_edge_depth_edge_recall_top10"),
            }
            for case in report["cases"]
        ],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    pre = report["preprocess_contract"]
    cap = pre.get("capture_input", {})
    ref = pre.get("saved_pytorch_reference", {})
    hi = pre.get("official_highres_reference_shape", {})
    lines = [
        "# CoreML / PyTorch Confidence + Edge Audit",
        "",
        "## 范围",
        "",
        "- 不改 CoreML 输出，不改 bbox，不做 graph patch/loop/mesh。",
        "- 对比 official-postprocess CoreML 与 saved official PyTorch small-K reference。",
        "- 重点看 confidence 语义、官方 GLB/NPZ 阈值下的 valid fraction、暗部/边缘区域、RGB/depth 边缘是否错位。",
        "",
        "## Preprocess Contract",
        "",
        f"- capture 输入尺寸：source `{cap.get('source_size')}` -> model input `{cap.get('model_input_size')}`。",
        f"- capture resize：`{cap.get('resize_mode')}` / `{cap.get('resize_interpolation')}`。",
        f"- saved PyTorch reference 使用：`{ref.get('jpeg_path_kind')}`，实际图片尺寸 `{(ref.get('matching_saved_input') or {}).get('size')}`。",
        f"- saved PyTorch process_res_method：`{ref.get('process_res_method')}`，process_res `{ref.get('process_res')}`。",
        f"- 如果 highres 直接走官方 upper_bound_resize，预期尺寸：`{hi.get('expected_shapes_by_process_res')}`。",
        "",
        "读法：当前 small-K reference 是和 CoreML 同源的 `photos_depth`，所以它适合检查 CoreML/PyTorch 输出数值语义；但它不能证明 highres -> fixed 742x476 的移动端预处理已经百分百等价官方动态宽高比 API。",
        "",
        "## Case Summary",
        "",
        "| case | mode | RGB MAE | exact RGB pixel frac | conf MAE | conf pearson | GLB valid CoreML/PyTorch | edge recall CoreML/PyTorch | png |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        if case.get("status") != "compared":
            lines.append(f"| {case.get('case')} | {case.get('status')} | - | - | - | - | - | - | - |")
            continue
        image_pair = case.get("image_pair", {})
        confidence = case.get("confidence_pair", {})
        thresholds = case.get("thresholds", {}).get("glb_style", {})
        edge = case.get("edge_alignment", {})
        png = case.get("outputs", {}).get("confidence_edge_png", "-")
        lines.append(
            "| {case} | {mode} | {rgb_mae} | {exact} | {conf_mae} | {pearson} | {valid} | {edge_recall} | `{png}` |".format(
                case=case.get("case"),
                mode=case.get("comparison_mode"),
                rgb_mae=format_float(image_pair.get("mae_rgb")),
                exact=format_float(image_pair.get("exact_pixel_fraction")),
                conf_mae=format_float(confidence.get("raw", {}).get("mae")),
                pearson=format_float(confidence.get("pearson")),
                valid="{}/{}".format(
                    format_float(thresholds.get("coreml_valid_fraction")),
                    format_float(thresholds.get("pytorch_valid_fraction")),
                ),
                edge_recall="{}/{}".format(
                    format_float(edge.get("coreml", {}).get("rgb_edge_depth_edge_recall_top10")),
                    format_float(edge.get("pytorch", {}).get("rgb_edge_depth_edge_recall_top10")),
                ),
                png=png,
            )
        )

    lines.extend(
        [
            "",
            "## Region Metrics",
            "",
            "| case | dataset | black<16 frac | dark luma<32 frac | rgb edge conf mean | rgb edge GLB valid | non-edge conf mean |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for case in report["cases"]:
        if case.get("status") != "compared":
            continue
        regions = case.get("region_confidence", {})
        for dataset in ["coreml", "pytorch"]:
            row = regions.get(dataset, {})
            black = row.get("black_all_channels_lt16", {})
            dark = row.get("dark_luma_lt32", {})
            edge = row.get("rgb_edge_top10", {})
            non_edge = row.get("rgb_non_edge_bottom70", {})
            lines.append(
                "| {case} | {dataset} | {black_frac} | {dark_frac} | {edge_mean} | {edge_valid} | {non_edge_mean} |".format(
                    case=case.get("case"),
                    dataset=dataset,
                    black_frac=format_float(black.get("fraction_of_pixels")),
                    dark_frac=format_float(dark.get("fraction_of_pixels")),
                    edge_mean=format_float(edge.get("conf", {}).get("mean")),
                    edge_valid=format_float(edge.get("glb_valid_fraction_inside_region")),
                    non_edge_mean=format_float(non_edge.get("conf", {}).get("mean")),
                )
            )

    lines.extend(
        [
            "",
            "## 初步判读",
            "",
            report.get("interpretation", {}).get("summary", ""),
            "",
            report.get("interpretation", {}).get("preprocess_note", ""),
            "",
            report.get("interpretation", {}).get("suggested_next_check", ""),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_float(value: Any) -> str:
    if value is None:
        return "-"
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(raw):
        return "-"
    return f"{raw:.6g}"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def maybe_read_json(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
