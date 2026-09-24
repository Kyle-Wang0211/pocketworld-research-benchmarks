#!/usr/bin/env python3
"""Micro-audit cumulative slots inside one strict DA3 K35 window."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageOps

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


GROUPS = [
    ("slot_00", [0]),
    ("slots_00_01", [0, 1]),
    ("slots_00_02", [0, 1, 2]),
    ("first_05", list(range(5))),
    ("first_10", list(range(10))),
    ("first_35", list(range(35))),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--da3-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_000")
    parser.add_argument("--sample-ratio", type=float, default=0.012)
    parser.add_argument("--conf-threshold-coef", type=float, default=0.75)
    parser.add_argument("--seed", type=int, default=3500)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    reports = read_json(args.da3_dir / "mac_da3_window_reports.json")
    window_reports = {str(row["windowID"]): row for row in reports.get("windows", [])}
    if args.window_id not in window_reports:
        raise KeyError(f"{args.window_id} not found in {args.da3_dir / 'mac_da3_window_reports.json'}")

    frames = sorted(
        window_reports[args.window_id].get("frames", []),
        key=lambda row: int(row.get("windowSlot", 0)),
    )
    slot_exports = [
        export_slot(
            frame,
            capture_dir=args.capture_dir,
            da3_dir=args.da3_dir,
            sample_ratio=args.sample_ratio,
            conf_threshold_coef=args.conf_threshold_coef,
            seed=args.seed + int(frame.get("windowSlot", 0)),
        )
        for frame in frames
    ]

    group_reports: list[dict[str, Any]] = []
    for name, slots in GROUPS:
        group_slots = [slot for slot in slots if slot < len(slot_exports)]
        if not group_slots:
            continue
        points = np.concatenate([slot_exports[slot]["points"] for slot in group_slots], axis=0)
        colors = np.concatenate([slot_exports[slot]["colors"] for slot in group_slots], axis=0)
        frame_ids = [str(slot_exports[slot]["frame_id"]) for slot in group_slots]
        centers = np.stack([slot_exports[slot]["camera_center"] for slot in group_slots], axis=0)

        ply_path = args.out_dir / f"{name}_rgb.ply"
        png_path = args.out_dir / f"{name}_views.png"
        write_point_cloud(ply_path, points, colors)
        write_views_png(png_path, points, colors, title=f"{args.window_id} {name}")

        group_report = {
            "name": name,
            "slots": group_slots,
            "frame_ids": frame_ids,
            "outputs": {
                "ply": str(ply_path),
                "views_png": str(png_path),
            },
            "metrics": {
                "slot_count": len(group_slots),
                "sampled_point_count": int(points.shape[0]),
                "valid_point_count_before_sampling": int(
                    sum(int(slot_exports[slot]["valid_point_count_before_sampling"]) for slot in group_slots)
                ),
                "point_cloud": cloud_metrics(points),
                "pca": pca_metrics(points),
                "depth": summarize_array(
                    np.concatenate([slot_exports[slot]["depth_values"] for slot in group_slots], axis=0)
                ),
                "confidence": summarize_array(
                    np.concatenate([slot_exports[slot]["conf_values"] for slot in group_slots], axis=0)
                ),
                "pose": pose_metrics(centers),
            },
        }
        group_reports.append(group_report)

    contact_sheet = args.out_dir / "window_000_micro_audit_contact_sheet.png"
    write_contact_sheet(contact_sheet, [Path(row["outputs"]["views_png"]) for row in group_reports])

    report = {
        "schema_version": "pocketworld_strict_k35_window_micro_audit_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "da3_dir": str(args.da3_dir),
            "window_id": args.window_id,
        },
        "parameters": {
            "sample_ratio": args.sample_ratio,
            "conf_threshold_coef": args.conf_threshold_coef,
            "seed": args.seed,
            "groups": GROUPS,
        },
        "outputs": {
            "contact_sheet": str(contact_sheet),
        },
        "groups": group_reports,
        "per_slot": [
            {
                key: value
                for key, value in slot.items()
                if key
                not in {
                    "points",
                    "colors",
                    "depth_values",
                    "conf_values",
                }
            }
            for slot in slot_exports
        ],
        "interpretation": interpret_groups(group_reports),
    }
    write_json(args.out_dir / "window_000_micro_audit_report.json", report)
    write_markdown(args.out_dir / "window_000_micro_audit_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def export_slot(
    frame: dict[str, Any],
    *,
    capture_dir: Path,
    da3_dir: Path,
    sample_ratio: float,
    conf_threshold_coef: float,
    seed: int,
) -> dict[str, Any]:
    height = int(frame["depthHeight"])
    width = int(frame["depthWidth"])
    depth = np.fromfile(da3_dir / str(frame["relativeDepthPath"]), dtype="<f4").reshape(height, width)
    conf = np.fromfile(da3_dir / str(frame["confidencePath"]), dtype="<f4").reshape(height, width)
    intrinsics = np.fromfile(da3_dir / str(frame["predIntrinsicsPath"]), dtype="<f4").reshape(3, 3)
    extrinsics = np.fromfile(da3_dir / str(frame["predExtrinsicsPath"]), dtype="<f4").reshape(3, 4)

    point_map = depth_to_point_map(depth, intrinsics, extrinsics)
    flat_points = point_map.reshape(-1, 3)
    flat_conf = conf.reshape(-1)
    threshold = float(np.nanmean(conf)) * conf_threshold_coef
    valid_mask = (
        np.isfinite(flat_points).all(axis=1)
        & np.isfinite(flat_conf)
        & (flat_conf >= threshold)
        & (flat_conf > 1e-5)
    )
    valid_indices = np.flatnonzero(valid_mask)
    sample_count = max(1, int(valid_indices.size * sample_ratio)) if valid_indices.size else 0
    if sample_count and sample_count < valid_indices.size:
        rng = np.random.default_rng(seed)
        selected = rng.choice(valid_indices, size=sample_count, replace=False)
    else:
        selected = valid_indices

    colors = load_frame_colors(frame, capture_dir).reshape(-1, 3)[selected].astype(np.uint8)
    points = flat_points[selected].astype(np.float32)
    finite = np.isfinite(points).all(axis=1)
    points = points[finite]
    colors = colors[finite]
    center = camera_center_from_w2c(extrinsics)
    finite_depth = depth[np.isfinite(depth)].astype(np.float32)
    finite_conf = conf[np.isfinite(conf)].astype(np.float32)
    return {
        "window_slot": int(frame.get("windowSlot", 0)),
        "frame_id": str(frame.get("frameID")),
        "frame_index": int(frame.get("frameIndex", -1)),
        "image_relative_path": str(frame.get("imageRelativePath")),
        "points": points,
        "colors": colors,
        "depth_values": finite_depth,
        "conf_values": finite_conf,
        "valid_point_count_before_sampling": int(valid_indices.size),
        "sampled_point_count": int(points.shape[0]),
        "depth": summarize_array(finite_depth),
        "confidence": summarize_array(finite_conf),
        "camera_center": center,
        "camera_center_list": [float(v) for v in center],
        "pred_intrinsics": {
            "fx": float(intrinsics[0, 0]),
            "fy": float(intrinsics[1, 1]),
            "cx": float(intrinsics[0, 2]),
            "cy": float(intrinsics[1, 2]),
        },
        "conf_threshold": threshold,
        "point_cloud": cloud_metrics(points) if points.size else {"point_count": 0},
        "pca": pca_metrics(points) if points.shape[0] >= 3 else {"status": "not_enough_points"},
    }


def depth_to_point_map(depth: np.ndarray, intrinsics: np.ndarray, extrinsics: np.ndarray) -> np.ndarray:
    height, width = depth.shape
    u, v = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    pixels = np.stack([u, v, np.ones_like(u)], axis=-1).reshape(-1, 3)
    rays = pixels @ np.linalg.inv(intrinsics.astype(np.float64)).T
    camera_points = rays * depth.reshape(-1, 1).astype(np.float64)
    camera_points_h = np.concatenate([camera_points, np.ones((camera_points.shape[0], 1))], axis=1)
    w2c = np.eye(4, dtype=np.float64)
    w2c[:3, :4] = extrinsics.astype(np.float64)
    c2w = np.linalg.inv(w2c)
    world_points = camera_points_h @ c2w.T
    return world_points[:, :3].reshape(height, width, 3)


def camera_center_from_w2c(extrinsics: np.ndarray) -> np.ndarray:
    rotation = extrinsics[:3, :3].astype(np.float64)
    translation = extrinsics[:3, 3].astype(np.float64)
    return (-rotation.T @ translation).astype(np.float32)


def load_frame_colors(frame: dict[str, Any], capture_dir: Path) -> np.ndarray:
    width = int(frame["depthWidth"])
    height = int(frame["depthHeight"])
    with Image.open(capture_dir / str(frame["imageRelativePath"])) as image:
        image = ImageOps.exif_transpose(image).convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
        return np.asarray(image, dtype=np.uint8)


def write_point_cloud(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    colors_u8 = np.clip(colors, 0, 255).astype(np.uint8)
    points_f32 = points.astype("<f4", copy=False)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {points_f32.shape[0]}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")
    with path.open("wb") as handle:
        handle.write(header)
        for point, color in zip(points_f32, colors_u8):
            handle.write(
                struct.pack(
                    "<fffBBB",
                    float(point[0]),
                    float(point[1]),
                    float(point[2]),
                    int(color[0]),
                    int(color[1]),
                    int(color[2]),
                )
            )


def write_views_png(path: Path, points: np.ndarray, colors: np.ndarray, *, title: str) -> None:
    rng = np.random.default_rng(123)
    pts = points.astype(np.float64)
    cols = np.clip(colors.astype(np.float64) / 255.0, 0.0, 1.0)
    lo = np.percentile(pts, 1.0, axis=0)
    hi = np.percentile(pts, 99.0, axis=0)
    mask = np.all((pts >= lo) & (pts <= hi), axis=1)
    pts = pts[mask]
    cols = cols[mask]
    if pts.shape[0] > 180_000:
        idx = rng.choice(pts.shape[0], size=180_000, replace=False)
        pts = pts[idx]
        cols = cols[idx]
    views = [("front XY", (0, 1)), ("top XZ", (0, 2)), ("side YZ", (1, 2))]
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), facecolor="white")
    fig.suptitle(title)
    for ax, (view_name, (a, b)) in zip(axes, views):
        ax.scatter(pts[:, a], pts[:, b], s=0.35, c=cols, linewidths=0)
        ax.set_aspect("equal", "box")
        ax.set_title(view_name)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)


def write_contact_sheet(path: Path, png_paths: list[Path]) -> None:
    images = [Image.open(png_path).convert("RGB") for png_path in png_paths]
    if not images:
        return
    width = max(image.width for image in images)
    label_h = 48
    rows = []
    for png_path, image in zip(png_paths, images):
        if image.width != width:
            height = int(image.height * width / image.width)
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        row = Image.new("RGB", (width, image.height + label_h), "white")
        draw = ImageDraw.Draw(row)
        draw.rectangle([0, 0, width, label_h], fill=(245, 245, 245))
        draw.text((20, 16), png_path.stem, fill=(20, 20, 20))
        row.paste(image, (0, label_h))
        rows.append(row)
    sheet = Image.new("RGB", (width, sum(row.height for row in rows)), "white")
    y = 0
    for row in rows:
        sheet.paste(row, (0, y))
        y += row.height
    sheet.save(path, quality=95)


def cloud_metrics(points: np.ndarray) -> dict[str, Any]:
    lo = np.percentile(points, 1.0, axis=0)
    hi = np.percentile(points, 99.0, axis=0)
    lo95 = np.percentile(points, 5.0, axis=0)
    hi95 = np.percentile(points, 95.0, axis=0)
    extent = hi - lo
    extent95 = hi95 - lo95
    std = np.std(points, axis=0)
    return {
        "point_count": int(points.shape[0]),
        "bbox_p01": [float(v) for v in lo],
        "bbox_p99": [float(v) for v in hi],
        "bbox_extent_p01_p99": [float(v) for v in extent],
        "bbox_diag_p01_p99": float(np.linalg.norm(extent)),
        "bbox_extent_p05_p95": [float(v) for v in extent95],
        "bbox_diag_p05_p95": float(np.linalg.norm(extent95)),
        "std_xyz": [float(v) for v in std],
    }


def pca_metrics(points: np.ndarray) -> dict[str, Any]:
    pts = points.astype(np.float64)
    centered = pts - np.mean(pts, axis=0)
    cov = (centered.T @ centered) / max(points.shape[0] - 1, 1)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]
    projected = centered @ eigvecs
    lo = np.percentile(projected, 1.0, axis=0)
    hi = np.percentile(projected, 99.0, axis=0)
    extent = hi - lo
    return {
        "eigenvalues_desc": [float(v) for v in eigvals],
        "extent_p01_p99_desc": [float(v) for v in extent],
        "major_extent": float(extent[0]),
        "middle_extent": float(extent[1]),
        "minor_extent": float(extent[2]),
        "minor_to_major_ratio": float(extent[2] / max(extent[0], 1e-12)),
    }


def pose_metrics(centers: np.ndarray) -> dict[str, Any]:
    lo = np.min(centers, axis=0)
    hi = np.max(centers, axis=0)
    extent = hi - lo
    if centers.shape[0] > 1:
        steps = np.linalg.norm(np.diff(centers, axis=0), axis=1)
    else:
        steps = np.zeros((0,), dtype=np.float32)
    return {
        "camera_center_min": [float(v) for v in lo],
        "camera_center_max": [float(v) for v in hi],
        "camera_center_extent": [float(v) for v in extent],
        "camera_center_diag": float(np.linalg.norm(extent)),
        "step_mean": None if steps.size == 0 else float(np.mean(steps)),
        "step_max": None if steps.size == 0 else float(np.max(steps)),
    }


def summarize_array(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"count": 0}
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p05": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
    }


def interpret_groups(groups: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    prev_diag = None
    prev_minor = None
    first_large_diag_jump = None
    first_large_minor_jump = None
    for group in groups:
        metrics = group["metrics"]
        diag = float(metrics["point_cloud"]["bbox_diag_p01_p99"])
        minor = float(metrics["pca"]["minor_extent"])
        ratio = float(metrics["pca"]["minor_to_major_ratio"])
        diag_growth = None if prev_diag is None else diag / max(prev_diag, 1e-12)
        minor_growth = None if prev_minor is None else minor / max(prev_minor, 1e-12)
        if first_large_diag_jump is None and diag_growth is not None and diag_growth >= 1.35:
            first_large_diag_jump = group["name"]
        if first_large_minor_jump is None and minor_growth is not None and minor_growth >= 1.35:
            first_large_minor_jump = group["name"]
        rows.append(
            {
                "name": group["name"],
                "slots": group["slots"],
                "bbox_diag_p01_p99": diag,
                "bbox_diag_growth_from_previous_group": diag_growth,
                "pca_minor_extent": minor,
                "pca_minor_growth_from_previous_group": minor_growth,
                "pca_minor_to_major_ratio": ratio,
                "camera_center_diag": metrics["pose"]["camera_center_diag"],
            }
        )
        prev_diag = diag
        prev_minor = minor
    return {
        "summary_rows": rows,
        "first_large_bbox_diag_jump_ge_1_35": first_large_diag_jump,
        "first_large_pca_minor_jump_ge_1_35": first_large_minor_jump,
        "note": "Growth thresholds are heuristics for triage; final judgment should combine PNG inspection and per-slot metrics.",
    }


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "out_dir": str(Path(report["outputs"]["contact_sheet"]).parent),
        "contact_sheet": report["outputs"]["contact_sheet"],
        "interpretation": report["interpretation"],
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    json_path = path.parent / "window_000_micro_audit_report.json"
    lines = [
        "# Window 000 Micro Audit",
        "",
        "## 输出",
        "",
        f"- contact sheet: `{report['outputs']['contact_sheet']}`",
        f"- report JSON: `{json_path}`",
        "",
        "## 累积组指标",
        "",
        "| group | slots | frames | points | bbox diag | bbox growth | PCA minor | minor growth | minor/major | camera diag |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    rows = {row["name"]: row for row in report["interpretation"]["summary_rows"]}
    for group in report["groups"]:
        metrics = group["metrics"]
        row = rows[group["name"]]
        lines.append(
            "| {name} | {slots} | {frames} | {points} | {diag:.4f} | {diag_growth} | {minor:.4f} | {minor_growth} | {ratio:.4f} | {cam:.4f} |".format(
                name=group["name"],
                slots=",".join(str(v) for v in group["slots"]),
                frames=",".join(group["frame_ids"]),
                points=metrics["sampled_point_count"],
                diag=row["bbox_diag_p01_p99"],
                diag_growth=fmt_optional(row["bbox_diag_growth_from_previous_group"]),
                minor=row["pca_minor_extent"],
                minor_growth=fmt_optional(row["pca_minor_growth_from_previous_group"]),
                ratio=row["pca_minor_to_major_ratio"],
                cam=row["camera_center_diag"],
            )
        )
    interp = report["interpretation"]
    lines.extend(
        [
            "",
            "## 自动标记",
            "",
            f"- first bbox diag jump >= 1.35x: `{interp['first_large_bbox_diag_jump_ge_1_35']}`",
            f"- first PCA minor jump >= 1.35x: `{interp['first_large_pca_minor_jump_ge_1_35']}`",
            "",
            "注：阈值只是 triage heuristic，最终判断需要结合 PNG 肉眼检查和 per-slot 指标。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fmt_optional(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.3f}x"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
