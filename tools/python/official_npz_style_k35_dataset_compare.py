#!/usr/bin/env python3
"""Compare K35 datasets with DA3-Streaming npz_output_process-style rules."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from strict_k35_window_official_filter_micro_audit import (
    build_group,
    camera_center_from_w2c,
    cloud_metrics,
    export_npz_streaming_style_group,
    load_slot,
    pca_metrics,
    pose_metrics,
    summarize_array,
    write_contact_sheet,
    write_point_cloud,
    write_views_png,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--coreml-dir", type=Path, required=True)
    parser.add_argument("--pytorch-fixed-dir", type=Path, required=True)
    parser.add_argument("--pytorch-highres-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_016")
    parser.add_argument("--conf-offset", type=float, default=-1.0)
    parser.add_argument("--conf-threshold-coef", type=float, default=0.5)
    parser.add_argument("--sample-ratio", type=float, default=0.015)
    parser.add_argument("--seed", type=int, default=9160)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    coreml = load_coreml_group(args.capture_dir, args.coreml_dir, args.window_id)
    fixed = load_pytorch_group(args.pytorch_fixed_dir, coreml["frame_ids"], "pytorch_fixed_photos_depth")
    highres = load_pytorch_group(
        args.pytorch_highres_dir,
        coreml["frame_ids"],
        "pytorch_highres_official_dynamic",
    )

    datasets = [
        export_dataset(
            "coreml_official_postprocess",
            coreml,
            args.out_dir,
            conf_offset=args.conf_offset,
            conf_threshold_coef=args.conf_threshold_coef,
            sample_ratio=args.sample_ratio,
            seed=args.seed,
        ),
        export_dataset(
            "pytorch_fixed_photos_depth",
            fixed,
            args.out_dir,
            conf_offset=args.conf_offset,
            conf_threshold_coef=args.conf_threshold_coef,
            sample_ratio=args.sample_ratio,
            seed=args.seed + 1,
        ),
        export_dataset(
            "pytorch_highres_official_dynamic",
            highres,
            args.out_dir,
            conf_offset=args.conf_offset,
            conf_threshold_coef=args.conf_threshold_coef,
            sample_ratio=args.sample_ratio,
            seed=args.seed + 2,
        ),
    ]
    contact_sheet = args.out_dir / f"{args.window_id}_npz_style_contact_sheet.png"
    write_contact_sheet(contact_sheet, [Path(row["outputs"]["views_png"]) for row in datasets])

    report = {
        "schema_version": "pocketworld_official_npz_style_k35_dataset_compare_v1",
        "window_id": args.window_id,
        "official_path": "DA3-Streaming results_output/frame_*.npz + npz_output_process.py + save_confident_pointcloud_batch",
        "parameters": {
            "conf_offset": args.conf_offset,
            "conf_offset_reason": "DA3-Streaming process_single_chunk applies predictions.conf -= 1.0 before save_depth_conf_result.",
            "conf_threshold_coef": args.conf_threshold_coef,
            "conf_threshold_coef_reason": "npz_output_process.py CLI default is 0.5; DA3-Streaming Pointcloud_Save config uses 0.75 for full-chunk pcd export.",
            "sample_ratio": args.sample_ratio,
            "seed": args.seed,
        },
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "coreml_dir": str(args.coreml_dir),
            "pytorch_fixed_dir": str(args.pytorch_fixed_dir),
            "pytorch_highres_dir": str(args.pytorch_highres_dir),
        },
        "outputs": {
            "contact_sheet": str(contact_sheet),
        },
        "datasets": {row["name"]: row for row in datasets},
        "comparison": compare_datasets(datasets),
    }
    report["interpretation"] = interpret(report)
    write_json(args.out_dir / f"{args.window_id}_npz_style_k35_dataset_compare.json", report)
    write_markdown(args.out_dir / f"{args.window_id}_npz_style_k35_dataset_compare_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def load_coreml_group(capture_dir: Path, coreml_dir: Path, window_id: str) -> dict[str, Any]:
    frames = load_coreml_frames(coreml_dir, window_id)
    slots = [load_slot(frame, capture_dir=capture_dir, da3_dir=coreml_dir) for frame in frames]
    group = build_group(slots, list(range(len(slots))))
    group["source"] = "CoreML official postprocess output"
    group["processed_shape_nhwc"] = [
        int(group["depth"].shape[0]),
        int(group["depth"].shape[1]),
        int(group["depth"].shape[2]),
        3,
    ]
    return group


def load_coreml_frames(coreml_dir: Path, window_id: str) -> list[dict[str, Any]]:
    reports = read_json(coreml_dir / "mac_da3_window_reports.json")
    windows = {str(row["windowID"]): row for row in reports.get("windows", [])}
    if window_id not in windows:
        raise KeyError(f"{window_id} not found in {coreml_dir / 'mac_da3_window_reports.json'}")
    return sorted(windows[window_id].get("frames", []), key=lambda row: int(row.get("windowSlot", 0)))


def load_pytorch_group(case_dir: Path, frame_ids: list[str], source: str) -> dict[str, Any]:
    depth = np.load(case_dir / "pytorch_depth.npy").astype(np.float32, copy=False)
    conf = np.load(case_dir / "pytorch_conf.npy").astype(np.float32, copy=False)
    intrinsics = np.load(case_dir / "pytorch_intrinsics.npy").astype(np.float32, copy=False)
    extrinsics = np.load(case_dir / "pytorch_extrinsics.npy").astype(np.float32, copy=False)
    images = np.load(case_dir / "pytorch_processed_images.npy").astype(np.uint8, copy=False)
    if depth.shape[0] != len(frame_ids):
        raise ValueError(f"{case_dir} has {depth.shape[0]} frames, expected {len(frame_ids)}")
    return {
        "source": source,
        "slots": list(range(depth.shape[0])),
        "frame_ids": list(frame_ids),
        "depth": depth,
        "conf": conf,
        "intrinsics": intrinsics,
        "extrinsics": extrinsics,
        "images": images,
        "camera_centers": np.stack([camera_center_from_w2c(ext) for ext in extrinsics], axis=0),
        "processed_shape_nhwc": [int(v) for v in images.shape],
    }


def export_dataset(
    name: str,
    group: dict[str, Any],
    out_dir: Path,
    *,
    conf_offset: float,
    conf_threshold_coef: float,
    sample_ratio: float,
    seed: int,
) -> dict[str, Any]:
    adjusted = dict(group)
    adjusted["conf"] = np.maximum(group["conf"].astype(np.float32) + np.float32(conf_offset), 0.0)
    exported = export_npz_streaming_style_group(
        adjusted,
        conf_threshold_coef=conf_threshold_coef,
        sample_ratio=sample_ratio,
        seed=seed,
    )
    ply_path = out_dir / f"{name}_npz_style_rgb.ply"
    png_path = out_dir / f"{name}_npz_style_views.png"
    write_point_cloud(ply_path, exported["points"], exported["colors"])
    write_views_png(png_path, exported["points"], exported["colors"], title=f"{name} official npz-style")
    points = exported["points"]
    pixel_count = int(np.prod(adjusted["conf"].shape))
    valid_count = int(exported["filter"]["valid_point_count_before_downsample"])
    return {
        "name": name,
        "source": group.get("source"),
        "frame_count": int(adjusted["depth"].shape[0]),
        "processed_shape_nhwc": group.get("processed_shape_nhwc"),
        "outputs": {
            "ply": str(ply_path),
            "views_png": str(png_path),
        },
        "filter": {
            **exported["filter"],
            "valid_fraction_of_pixels": float(valid_count / max(pixel_count, 1)),
        },
        "point_cloud": cloud_metrics(points) if points.shape[0] else {"point_count": 0},
        "pca": pca_metrics(points) if points.shape[0] >= 3 else {"status": "not_enough_points"},
        "depth": summarize_array(adjusted["depth"].reshape(-1)),
        "confidence_raw": summarize_array(group["conf"].reshape(-1)),
        "confidence_after_offset": summarize_array(adjusted["conf"].reshape(-1)),
        "pose": pose_metrics(adjusted["camera_centers"]),
    }


def compare_datasets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {row["name"]: row for row in rows}
    return {
        "coreml_over_pytorch_fixed": compare_pair(
            by_name["coreml_official_postprocess"],
            by_name["pytorch_fixed_photos_depth"],
        ),
        "coreml_over_pytorch_highres": compare_pair(
            by_name["coreml_official_postprocess"],
            by_name["pytorch_highres_official_dynamic"],
        ),
        "pytorch_fixed_over_highres": compare_pair(
            by_name["pytorch_fixed_photos_depth"],
            by_name["pytorch_highres_official_dynamic"],
        ),
    }


def compare_pair(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    return {
        "bbox_diag_ratio": safe_div(
            a.get("point_cloud", {}).get("bbox_diag_p01_p99"),
            b.get("point_cloud", {}).get("bbox_diag_p01_p99"),
        ),
        "pca_minor_ratio": safe_div(
            a.get("pca", {}).get("minor_extent"),
            b.get("pca", {}).get("minor_extent"),
        ),
        "valid_fraction_ratio": safe_div(
            a.get("filter", {}).get("valid_fraction_of_pixels"),
            b.get("filter", {}).get("valid_fraction_of_pixels"),
        ),
        "conf_threshold_ratio": safe_div(
            a.get("filter", {}).get("conf_threshold"),
            b.get("filter", {}).get("conf_threshold"),
        ),
        "depth_median_ratio": safe_div(
            a.get("depth", {}).get("median"),
            b.get("depth", {}).get("median"),
        ),
    }


def interpret(report: dict[str, Any]) -> str:
    datasets = report["datasets"]
    comp = report["comparison"]
    params = report["parameters"]
    core = datasets["coreml_official_postprocess"]
    fixed = datasets["pytorch_fixed_photos_depth"]
    high = datasets["pytorch_highres_official_dynamic"]
    return (
        "按 DA3-Streaming npz downstream 口径先做 conf -= 1.0，"
        f"再用 mean(conf)*{fmt(params.get('conf_threshold_coef'))} 和 sample_ratio={fmt(params.get('sample_ratio'))}。"
        f"CoreML/PyTorch fixed bbox diag={fmt(core['point_cloud'].get('bbox_diag_p01_p99'))}/{fmt(fixed['point_cloud'].get('bbox_diag_p01_p99'))}，"
        f"PCA minor={fmt(core['pca'].get('minor_extent'))}/{fmt(fixed['pca'].get('minor_extent'))}，"
        f"CoreML/fixed bbox ratio={fmt(comp['coreml_over_pytorch_fixed'].get('bbox_diag_ratio'))}。"
        f"PyTorch fixed/highres bbox ratio={fmt(comp['pytorch_fixed_over_highres'].get('bbox_diag_ratio'))}，"
        f"highres bbox diag={fmt(high['point_cloud'].get('bbox_diag_p01_p99'))}。"
        "如果这个口径下 CoreML 仍没有相对 PyTorch 成倍变厚，就继续支持“厚层主要是 K35 上游几何一致性限制，而不是下游漏了官方去重”。"
    )


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    rows = list(report["datasets"].values())
    lines = [
        "# Official npz-style K35 Dataset Compare",
        "",
        "日期：2026-06-04",
        "",
        "## 范围",
        "",
        "- 模拟 DA3-Streaming `results_output/frame_*.npz + npz_output_process.py` downstream 口径。",
        "- 对所有数据显式应用 `conf += -1.0`，对应官方 `predictions.conf -= 1.0`。",
        "- 使用 `mean(conf) * 0.75` 和 `sample_ratio=0.015`。",
        "- 不做 voxel、TSDF、surfel、mesh、法线过滤或自研去重。",
        "",
        "## Outputs",
        "",
        f"- contact sheet: `{report['outputs']['contact_sheet']}`",
        "",
        "## Metrics",
        "",
        "| dataset | shape | threshold | valid frac | points | bbox diag | PCA minor | minor/major | conf median after offset |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend(dataset_row(row) for row in rows)
    lines.extend(
        [
            "",
            "## Ratios",
            "",
            ratio_line("CoreML / PyTorch fixed", report["comparison"]["coreml_over_pytorch_fixed"]),
            ratio_line("CoreML / PyTorch highres", report["comparison"]["coreml_over_pytorch_highres"]),
            ratio_line("PyTorch fixed / highres", report["comparison"]["pytorch_fixed_over_highres"]),
            "",
            "## 初步判读",
            "",
            report["interpretation"],
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dataset_row(row: dict[str, Any]) -> str:
    shape = "x".join(str(v) for v in row.get("processed_shape_nhwc") or [])
    return "| {name} | {shape} | {thr} | {valid} | {points} | {bbox} | {minor} | {ratio} | {conf} |".format(
        name=row["name"],
        shape=shape,
        thr=fmt(row.get("filter", {}).get("conf_threshold")),
        valid=fmt(row.get("filter", {}).get("valid_fraction_of_pixels")),
        points=row.get("filter", {}).get("exported_point_count"),
        bbox=fmt(row.get("point_cloud", {}).get("bbox_diag_p01_p99")),
        minor=fmt(row.get("pca", {}).get("minor_extent")),
        ratio=fmt(row.get("pca", {}).get("minor_to_major_ratio")),
        conf=fmt(row.get("confidence_after_offset", {}).get("median")),
    )


def ratio_line(label: str, row: dict[str, Any]) -> str:
    return (
        f"- {label}: bbox `{fmt(row.get('bbox_diag_ratio'))}`, "
        f"PCA minor `{fmt(row.get('pca_minor_ratio'))}`, "
        f"valid fraction `{fmt(row.get('valid_fraction_ratio'))}`, "
        f"threshold `{fmt(row.get('conf_threshold_ratio'))}`"
    )


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "outputs": report["outputs"],
        "comparison": report["comparison"],
        "interpretation": report["interpretation"],
    }


def safe_div(num: Any, den: Any) -> float:
    try:
        n = float(num)
        d = float(den)
    except (TypeError, ValueError):
        return math.nan
    if abs(d) <= 1e-12:
        return math.nan
    return n / d


def fmt(value: Any) -> str:
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
