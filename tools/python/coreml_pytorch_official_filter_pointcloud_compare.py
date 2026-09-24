#!/usr/bin/env python3
"""Compare CoreML and official PyTorch point clouds with official GLB rules."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from strict_k35_window_official_filter_micro_audit import (
    build_group,
    camera_center_from_w2c,
    cloud_metrics,
    load_slot,
    official_depths_to_world_points_with_colors,
    official_glb_alignment_transform,
    official_glb_conf_threshold,
    official_glb_filter_and_downsample,
    pca_metrics,
    transform_points,
    write_point_cloud,
    write_views_png,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--coreml-dir", type=Path, required=True)
    parser.add_argument("--pytorch-case-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_000")
    parser.add_argument("--case-name", default="k05_res742_mps")
    parser.add_argument("--glb-conf-thresh", type=float, default=1.05)
    parser.add_argument("--glb-conf-percentile", type=float, default=40.0)
    parser.add_argument("--glb-ensure-percentile", type=float, default=90.0)
    parser.add_argument("--glb-num-max-points", type=int, default=1_000_000)
    parser.add_argument("--seed", type=int, default=8120)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    frames = load_coreml_frames(args.coreml_dir, args.window_id)
    pytorch = load_pytorch_case(args.pytorch_case_dir)
    k = int(pytorch["depth"].shape[0])
    if k > len(frames):
        raise ValueError(f"{args.case_name} needs {k} CoreML frames, only {len(frames)} available")

    coreml_slots = [
        load_slot(frame, capture_dir=args.capture_dir, da3_dir=args.coreml_dir)
        for frame in frames[:k]
    ]
    coreml_group = build_group(coreml_slots, list(range(k)))
    pytorch_group = {
        "slots": list(range(k)),
        "frame_ids": [str(frame.get("frameID")) for frame in frames[:k]],
        "depth": pytorch["depth"],
        "conf": pytorch["conf"],
        "intrinsics": pytorch["intrinsics"],
        "extrinsics": pytorch["extrinsics"],
        "images": pytorch["processed_images"],
        "camera_centers": np.stack([camera_center_from_w2c(ext) for ext in pytorch["extrinsics"]], axis=0),
    }

    coreml_export = export_group(
        coreml_group,
        out_dir=args.out_dir,
        stem=f"{args.case_name}_coreml",
        conf_thresh=args.glb_conf_thresh,
        conf_percentile=args.glb_conf_percentile,
        ensure_percentile=args.glb_ensure_percentile,
        num_max_points=args.glb_num_max_points,
        seed=args.seed,
    )
    pytorch_export = export_group(
        pytorch_group,
        out_dir=args.out_dir,
        stem=f"{args.case_name}_pytorch",
        conf_thresh=args.glb_conf_thresh,
        conf_percentile=args.glb_conf_percentile,
        ensure_percentile=args.glb_ensure_percentile,
        num_max_points=args.glb_num_max_points,
        seed=args.seed + 1,
    )
    comparison_png = args.out_dir / f"{args.case_name}_coreml_vs_pytorch_glb_style.png"
    write_side_by_side(
        comparison_png,
        Path(coreml_export["outputs"]["views_png"]),
        Path(pytorch_export["outputs"]["views_png"]),
    )

    report = {
        "schema_version": "pocketworld_coreml_pytorch_official_filter_pointcloud_compare_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "coreml_dir": str(args.coreml_dir),
            "pytorch_case_dir": str(args.pytorch_case_dir),
            "window_id": args.window_id,
            "case_name": args.case_name,
        },
        "parameters": {
            "glb_conf_thresh": args.glb_conf_thresh,
            "glb_conf_percentile": args.glb_conf_percentile,
            "glb_ensure_percentile": args.glb_ensure_percentile,
            "glb_num_max_points": args.glb_num_max_points,
            "seed": args.seed,
        },
        "outputs": {
            "comparison_png": str(comparison_png),
        },
        "datasets": {
            "coreml": coreml_export,
            "pytorch": pytorch_export,
        },
        "comparison": compare_exports(coreml_export, pytorch_export),
        "interpretation": interpret(coreml_export, pytorch_export),
    }
    write_json(args.out_dir / f"{args.case_name}_official_filter_pointcloud_compare.json", report)
    write_markdown(args.out_dir / f"{args.case_name}_official_filter_pointcloud_compare_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def load_coreml_frames(coreml_dir: Path, window_id: str) -> list[dict[str, Any]]:
    reports = read_json(coreml_dir / "mac_da3_window_reports.json")
    windows = {str(row["windowID"]): row for row in reports.get("windows", [])}
    if window_id not in windows:
        raise KeyError(f"{window_id} not found in {coreml_dir / 'mac_da3_window_reports.json'}")
    return sorted(windows[window_id].get("frames", []), key=lambda row: int(row.get("windowSlot", 0)))


def load_pytorch_case(case_dir: Path) -> dict[str, np.ndarray]:
    return {
        "depth": np.load(case_dir / "pytorch_depth.npy").astype(np.float32, copy=False),
        "conf": np.load(case_dir / "pytorch_conf.npy").astype(np.float32, copy=False),
        "intrinsics": np.load(case_dir / "pytorch_intrinsics.npy").astype(np.float32, copy=False),
        "extrinsics": np.load(case_dir / "pytorch_extrinsics.npy").astype(np.float32, copy=False),
        "processed_images": np.load(case_dir / "pytorch_processed_images.npy").astype(np.uint8, copy=False),
    }


def export_group(
    group: dict[str, Any],
    *,
    out_dir: Path,
    stem: str,
    conf_thresh: float,
    conf_percentile: float,
    ensure_percentile: float,
    num_max_points: int,
    seed: int,
) -> dict[str, Any]:
    threshold = official_glb_conf_threshold(
        group["conf"],
        conf_thresh=conf_thresh,
        conf_thresh_percentile=conf_percentile,
        ensure_thresh_percentile=ensure_percentile,
    )
    points, colors = official_depths_to_world_points_with_colors(
        group["depth"],
        group["intrinsics"],
        group["extrinsics"],
        group["images"],
        group["conf"],
        threshold,
    )
    valid_count = int(points.shape[0])
    transform = official_glb_alignment_transform(group["extrinsics"][0], points)
    points = transform_points(points, transform)
    points, colors = official_glb_filter_and_downsample(
        points,
        colors,
        num_max=num_max_points,
        seed=seed,
    )
    ply_path = out_dir / f"{stem}_rgb.ply"
    png_path = out_dir / f"{stem}_views.png"
    write_point_cloud(ply_path, points, colors)
    write_views_png(png_path, points, colors, title=f"{stem} official GLB style")
    return {
        "outputs": {
            "ply": str(ply_path),
            "views_png": str(png_path),
        },
        "filter": {
            "conf_threshold": float(threshold),
            "valid_point_count_before_downsample": valid_count,
            "sampled_point_count": int(points.shape[0]),
            "valid_fraction_of_pixels": float(valid_count / max(np.prod(group["conf"].shape), 1)),
        },
        "point_cloud": cloud_metrics(points) if points.shape[0] else {"point_count": 0},
        "pca": pca_metrics(points) if points.shape[0] >= 3 else {"status": "not_enough_points"},
        "confidence": summarize_array(group["conf"].reshape(-1)),
        "depth": summarize_array(group["depth"].reshape(-1)),
    }


def compare_exports(coreml: dict[str, Any], pytorch: dict[str, Any]) -> dict[str, Any]:
    c_cloud = coreml.get("point_cloud", {})
    p_cloud = pytorch.get("point_cloud", {})
    c_pca = coreml.get("pca", {})
    p_pca = pytorch.get("pca", {})
    return {
        "bbox_diag_ratio_coreml_over_pytorch": safe_div(
            c_cloud.get("bbox_diag_p01_p99"),
            p_cloud.get("bbox_diag_p01_p99"),
        ),
        "pca_minor_ratio_coreml_over_pytorch": safe_div(
            c_pca.get("minor_extent"),
            p_pca.get("minor_extent"),
        ),
        "valid_fraction_ratio_coreml_over_pytorch": safe_div(
            coreml.get("filter", {}).get("valid_fraction_of_pixels"),
            pytorch.get("filter", {}).get("valid_fraction_of_pixels"),
        ),
        "conf_threshold_ratio_coreml_over_pytorch": safe_div(
            coreml.get("filter", {}).get("conf_threshold"),
            pytorch.get("filter", {}).get("conf_threshold"),
        ),
    }


def interpret(coreml: dict[str, Any], pytorch: dict[str, Any]) -> str:
    c_bbox = coreml.get("point_cloud", {}).get("bbox_diag_p01_p99")
    p_bbox = pytorch.get("point_cloud", {}).get("bbox_diag_p01_p99")
    c_minor = coreml.get("pca", {}).get("minor_extent")
    p_minor = pytorch.get("pca", {}).get("minor_extent")
    c_valid = coreml.get("filter", {}).get("valid_fraction_of_pixels")
    p_valid = pytorch.get("filter", {}).get("valid_fraction_of_pixels")
    return (
        "同 K、同图、同 official GLB-style filter 下比较点云。"
        f"CoreML/PyTorch valid fraction={format_float(c_valid)}/{format_float(p_valid)}，"
        f"bbox diag={format_float(c_bbox)}/{format_float(p_bbox)}，"
        f"PCA minor={format_float(c_minor)}/{format_float(p_minor)}。"
        "如果两边都出现类似厚层/暗部片状保留，漂浮更像官方模型/导出规则在这组图上的表现；"
        "如果 PyTorch 明显干净而 CoreML 更厚，再回头查 CoreML export parity。"
    )


def write_side_by_side(path: Path, left_path: Path, right_path: Path) -> None:
    left = Image.open(left_path).convert("RGB")
    right = Image.open(right_path).convert("RGB")
    width = max(left.width, right.width)
    if left.width != width:
        left = left.resize((width, int(left.height * width / left.width)), Image.Resampling.LANCZOS)
    if right.width != width:
        right = right.resize((width, int(right.height * width / right.width)), Image.Resampling.LANCZOS)
    label_h = 44
    out = Image.new("RGB", (width, left.height + right.height + label_h * 2), "white")
    draw = ImageDraw.Draw(out)
    draw.rectangle([0, 0, width, label_h], fill=(245, 245, 245))
    draw.text((20, 14), left_path.stem, fill=(20, 20, 20))
    out.paste(left, (0, label_h))
    y = label_h + left.height
    draw.rectangle([0, y, width, y + label_h], fill=(245, 245, 245))
    draw.text((20, y + 14), right_path.stem, fill=(20, 20, 20))
    out.paste(right, (0, y + label_h))
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path, quality=95)


def summarize_array(values: np.ndarray) -> dict[str, float | int]:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"count": 0}
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "p05": float(np.percentile(arr, 5)),
        "p40": float(np.percentile(arr, 40)),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "max": float(np.max(arr)),
    }


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "outputs": report["outputs"],
        "comparison": report["comparison"],
        "interpretation": report["interpretation"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    coreml = report["datasets"]["coreml"]
    pytorch = report["datasets"]["pytorch"]
    comparison = report["comparison"]
    lines = [
        "# CoreML / PyTorch Official Filter Pointcloud Compare",
        "",
        "## 范围",
        "",
        "- 同 K、同图、同 official GLB-style confidence/backprojection/alignment 规则。",
        "- 不做自研过滤，不做 graph patch，不做 loop，不做 mesh。",
        "",
        "## Outputs",
        "",
        f"- comparison png: `{report['outputs']['comparison_png']}`",
        f"- CoreML views: `{coreml['outputs']['views_png']}`",
        f"- PyTorch views: `{pytorch['outputs']['views_png']}`",
        "",
        "## Metrics",
        "",
        "| dataset | conf threshold | valid frac | points | bbox diag | PCA minor | minor/major |",
        "|---|---:|---:|---:|---:|---:|---:|",
        dataset_row("CoreML", coreml),
        dataset_row("PyTorch", pytorch),
        "",
        "## Ratios",
        "",
        f"- bbox diag CoreML/PyTorch: `{format_float(comparison.get('bbox_diag_ratio_coreml_over_pytorch'))}`",
        f"- PCA minor CoreML/PyTorch: `{format_float(comparison.get('pca_minor_ratio_coreml_over_pytorch'))}`",
        f"- valid fraction CoreML/PyTorch: `{format_float(comparison.get('valid_fraction_ratio_coreml_over_pytorch'))}`",
        f"- conf threshold CoreML/PyTorch: `{format_float(comparison.get('conf_threshold_ratio_coreml_over_pytorch'))}`",
        "",
        "## 初步判读",
        "",
        report["interpretation"],
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dataset_row(name: str, row: dict[str, Any]) -> str:
    return "| {name} | {thr} | {valid} | {points} | {bbox} | {minor} | {ratio} |".format(
        name=name,
        thr=format_float(row.get("filter", {}).get("conf_threshold")),
        valid=format_float(row.get("filter", {}).get("valid_fraction_of_pixels")),
        points=row.get("filter", {}).get("sampled_point_count"),
        bbox=format_float(row.get("point_cloud", {}).get("bbox_diag_p01_p99")),
        minor=format_float(row.get("pca", {}).get("minor_extent")),
        ratio=format_float(row.get("pca", {}).get("minor_to_major_ratio")),
    )


def safe_div(num: Any, den: Any) -> float:
    try:
        n = float(num)
        d = float(den)
    except (TypeError, ValueError):
        return math.nan
    if abs(d) <= 1e-12:
        return math.nan
    return n / d


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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
